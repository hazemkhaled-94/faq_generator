"""Which passages the documents themselves link, for the bridge pass.

A bridge is a claim two passages make together. Two passages are worth
putting side by side when the documents say they belong together: one names
the other's heading, both sit under one parent heading, or a term almost no
other passage uses is in both. Nearness of meaning alone offers restatements
and misses the references, so it only ranks inside a kind of link.

Language-agnostic: the label words ('Section', 'Abschnitt') are learned from
the corpus's own heading trails, and everything else is read through the
spaCy pipeline of the passage's language.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from extraction.models import PassageToExtract
from extraction.validation import HEADING_LABEL
from nlp.analysis import content, normalised
from nlp.embedding import cosine
from nlp.pipelines import pipeline

_NUMBER = re.compile(r"\d+(?:\.\d+)*")

#: A quoted span: opening and closing marks of the common scripts, and an
#: ASCII apostrophe only at a word's edge.
_QUOTED = re.compile(
    r"(?:[\"„‚“‘«‹›»”’]|(?<!\w)')"
    r"(?P<inner>[^\"„‚“”‘’«»‹›\n]+?)"
    r"(?:[\"“”‘’«»‹›]|'(?!\w))"
)

#: The share of a language's passages a term may be in and still be rare.
#: Never below two, so on a small corpus a term in exactly two passages links.
_RARE_SHARE = 0.005

_TIER = {"reference": 0, "sibling": 1, "term": 2}


@dataclass(frozen=True)
class Link:
    """Passages the documents link, in the order the model is shown them.

    Attributes:
        passages: The passages. For a reference the one that names comes
            first.
        kind: 'reference', 'sibling' or 'term'.
        named: The heading, the parent heading or the term, as the corpus
            writes it.
    """

    passages: tuple[PassageToExtract, ...]
    kind: str
    named: str


def _segments(passage: PassageToExtract) -> list[str]:
    """The headings of a passage's trail, outermost first."""
    return [s.strip() for s in (passage.section_path or "").split(" > ") if s.strip()]


def _plain(text: str) -> str:
    """A heading or a quoted span as it is compared."""
    return normalised(text).strip(" .:;,*")


def _near(left: PassageToExtract, right: PassageToExtract) -> float:
    """Cosine of two passages, 0 where either has no vector."""
    if left.embedding is None or right.embedding is None:
        return 0.0
    return cosine(list(left.embedding), list(right.embedding))


def _shared_prefix(left: PassageToExtract, right: PassageToExtract) -> int:
    """How many leading headings two trails share."""
    count = 0
    for one, other in zip(_segments(left), _segments(right), strict=False):
        if one != other:
            break
        count += 1
    return count


def _nearest(
    head: PassageToExtract, targets: Sequence[PassageToExtract]
) -> PassageToExtract | None:
    """The target a reference most likely means: same document, same branch, nearest."""
    found = [t for t in targets if t.id != head.id]
    if not found:
        return None
    return min(
        found,
        key=lambda t: (
            t.doc_sha256 != head.doc_sha256,
            -_shared_prefix(head, t),
            -_near(head, t),
            t.id,
        ),
    )


class _Edges:
    """Every link of one language, keyed by the pair, strongest kind kept."""

    def __init__(self) -> None:
        self.found: dict[frozenset[int], tuple[int, Link]] = {}
        self.of: dict[int, list[frozenset[int]]] = defaultdict(list)
        #: Sections by parent heading, and each passage's place in reading
        #: order. Sibling pairs are not stored: a parent heading over N
        #: sections would hold N^2/2 of them, so a head reads its own.
        self.family: dict[str, list[PassageToExtract]] = defaultdict(list)
        self.parent: dict[int, str] = {}
        self.position: dict[int, int] = {}

    def add(
        self, first: PassageToExtract, second: PassageToExtract, kind: str, named: str
    ) -> None:
        """Records a link, keeping the strongest kind a pair has."""
        key = frozenset((first.id, second.id))
        if key not in self.found:
            self.of[first.id].append(key)
            self.of[second.id].append(key)
        elif self.found[key][0] <= _TIER[kind]:
            return
        self.found[key] = (_TIER[kind], Link((first, second), kind, named))


def _references(
    edges: _Edges, partners: Sequence[PassageToExtract], language: str | None
) -> None:
    """Adds the links a passage makes by naming a heading."""
    labels: dict[tuple[str, str], list[tuple[int, str, PassageToExtract]]] = (
        defaultdict(list)
    )
    headings: dict[str, list[tuple[str, PassageToExtract]]] = defaultdict(list)
    parents: dict[str, set[str]] = defaultdict(set)
    for p in partners:
        trail = _segments(p)
        plain = [_plain(s) for s in trail]
        for depth, segment in enumerate(trail):
            if match := HEADING_LABEL.match(segment):
                labels[(match.group(1).casefold(), match.group(2))].append(
                    (depth, segment, p)
                )
            headings[plain[depth]].append((segment, p))
            parents[plain[depth]].update(plain[:depth])
    words = {word for word, _ in labels}
    nlp = pipeline(language)
    for head in partners:
        own = {
            (m.group(1).casefold(), m.group(2))
            for s in _segments(head)
            if (m := HEADING_LABEL.match(s))
        }
        tokens = list(nlp(head.text))
        named: dict[tuple[str, str], set[str]] = defaultdict(set)
        for at, token in enumerate(tokens[:-1]):
            word = next(
                (
                    w
                    for w in (token.text.casefold(), token.lemma_.casefold())
                    if w in words
                ),
                None,
            )
            if word is None:
                continue
            nxt = at + 1
            while nxt < len(tokens) and _NUMBER.fullmatch(tokens[nxt].text.rstrip(".")):
                named[(word, tokens[nxt].text.rstrip("."))].add(tokens[at].sent.text)
                if (
                    nxt + 2 < len(tokens)
                    and tokens[nxt + 1].pos_ in ("CCONJ", "PUNCT")
                    and _NUMBER.fullmatch(tokens[nxt + 2].text.rstrip("."))
                ):
                    nxt += 2
                else:
                    break
        for key in sorted(k for k in named if k not in own):
            # A numbered reference names a section of its own document, or of
            # another whose title the sentence names.
            held = [
                h for h in labels.get(key, []) if h[2].doc_sha256 == head.doc_sha256
            ]
            if not held:
                said = content(" ".join(named[key]), language)
                held = [
                    h
                    for h in labels.get(key, [])
                    if (title := content(h[2].title or "", language)) and title <= said
                ]
            shallow = min((d for d, _, _ in held), default=0)
            reached = _nearest(head, [p for d, _, p in held if d == shallow])
            if reached is not None:
                label = next(s for d, s, p in held if p is reached and d == shallow)
                edges.add(head, reached, "reference", label)
        mine = {_plain(s) for s in _segments(head)}
        quoted = [
            key
            for m in _QUOTED.finditer(head.text)
            if (key := _plain(m.group("inner"))) in headings
            and key not in mine
            and content(m.group("inner"), language)
        ]
        quoted = [
            k for k in quoted if not any(k in parents[o] for o in quoted if o != k)
        ]
        for key in dict.fromkeys(quoted):
            reached = _nearest(head, [p for _, p in headings[key]])
            if reached is not None:
                label = next(s for s, p in headings[key] if p is reached)
                edges.add(head, reached, "reference", label)


def _siblings(edges: _Edges, partners: Sequence[PassageToExtract]) -> None:
    """Groups the sections under one parent heading; `_best` reads the pairs."""
    for at, p in enumerate(partners):
        edges.position[p.id] = at
        trail = _segments(p)
        if len(trail) >= 2:
            edges.parent[p.id] = " > ".join(trail[:-1])
            edges.family[edges.parent[p.id]].append(p)


def _terms(
    edges: _Edges, partners: Sequence[PassageToExtract], language: str | None
) -> None:
    """Adds the links of a term almost no other passage uses."""
    lemmas = {p.id: content(p.text, language) for p in partners}
    carriers: dict[str, list[PassageToExtract]] = defaultdict(list)
    for p in partners:
        for lemma in lemmas[p.id]:
            carriers[lemma].append(p)
    rare = max(2, math.ceil(_RARE_SHARE * len(partners)))
    for lemma, held in sorted(carriers.items(), key=lambda kv: (len(kv[1]), kv[0])):
        if 2 <= len(held) <= rare:
            for at, first in enumerate(held):
                for second in held[at + 1 :]:
                    edges.add(first, second, "term", lemma)


def _best(
    edges: _Edges, partner: PassageToExtract, taken: frozenset[int] | set[int]
) -> list[tuple[tuple[int, float, int], Link]]:
    """A passage's links, strongest kind first, then nearest, then lowest id."""
    found: dict[int, tuple[int, Link]] = {}
    for key in edges.of[partner.id]:
        tier, link = edges.found[key]
        other = next(p for p in link.passages if p.id != partner.id)
        if other.id not in taken:
            found[other.id] = (tier, link)
    # shortcut: `_near` is a pure-Python dot product per candidate, so a head
    # under one flat parent of N sections costs N of them and the language
    # N^2; on a corpus with vectors a flat parent of a few thousand sections
    # is minutes. Upgrade: one numpy matrix product per family.
    parent = edges.parent.get(partner.id)
    for other in edges.family.get(parent, ()) if parent else ():
        if (
            other.id == partner.id
            or other.id in taken
            or _segments(other)[-1] == _segments(partner)[-1]
            or found.get(other.id, (_TIER["sibling"] + 1, None))[0] <= _TIER["sibling"]
        ):
            continue
        pair = sorted((partner, other), key=lambda one: edges.position[one.id])
        found[other.id] = (
            _TIER["sibling"],
            Link((pair[0], pair[1]), "sibling", _segments(pair[0])[-2]),
        )
    ranked = [
        (
            (
                tier,
                -_near(partner, next(p for p in link.passages if p.id != partner.id)),
                other,
            ),
            link,
        )
        for other, (tier, link) in found.items()
    ]
    return sorted(ranked, key=lambda r: r[0])


def linked(
    heads: Sequence[PassageToExtract],
    partners: Sequence[PassageToExtract],
    topic_of: Mapping[int, int],
    wanted: int,
    size: int,
    done: frozenset[int] = frozenset(),
    held: frozenset[frozenset[int]] = frozenset(),
) -> list[Link]:
    """Pairs each head with the passage the documents link it to.

    Each head offers at most one link, its strongest (reference, then
    sibling, then term; inside a kind the nearest by vector, a tie to the
    lower id), and a pair is offered once. Each topic of the heads is worth
    up to `wanted` links, spread evenly over its linked heads in reading
    order rather than taken from its start. The partner may sit in any topic
    of its language. Two languages are never linked.

    Args:
        heads: The passages that may head a link, in reading order.
        partners: Every passage a head may be paired with; heads are among
            them.
        topic_of: Each passage's topic, by passage id.
        wanted: The most links per topic of the head.
        size: How many passages one link holds; beyond two, the last
            member's own best link adds the next.
        done: Topics whose heads are skipped.
        held: Pairs of passage ids a stored bridge already rests on; a head
            never offers one of them, and takes its next link instead.

    Returns:
        The links, per language and topic in reading order.
    """
    if size < 2 or wanted < 1:
        return []
    out: list[Link] = []
    for language in sorted({p.language or "" for p in partners}):
        mine = [p for p in partners if (p.language or "") == language]
        edges = _Edges()
        _references(edges, mine, language or None)
        _siblings(edges, mine)
        _terms(edges, mine, language or None)
        seen: set[frozenset[int]] = set(held)
        by_topic: dict[int, list[Link]] = defaultdict(list)
        for head in (h for h in heads if (h.language or "") == language):
            topic = topic_of.get(head.id)
            if topic is None or topic in done:
                continue
            for _, link in _best(edges, head, set()):
                key = frozenset(p.id for p in link.passages)
                if key not in seen:
                    seen.add(key)
                    by_topic[topic].append(link)
                    break
        for chosen in by_topic.values():
            count = min(wanted, len(chosen))
            step = (len(chosen) - 1) / (count - 1) if count > 1 else 0
            for link in (chosen[round(at * step)] for at in range(count)):
                grown = _grown(edges, link, size)
                if grown is not None:
                    out.append(grown)
    return out


def _grown(edges: _Edges, link: Link, size: int) -> Link | None:
    """Extends a link to `size` passages through the last member's own links."""
    members = list(link.passages)
    while len(members) < size:
        taken = {p.id for p in members}
        options = _best(edges, members[-1], taken)
        if not options:
            return None
        members.append(next(p for p in options[0][1].passages if p.id not in taken))
    return Link(tuple(members), link.kind, link.named)
