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
from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass, replace

import numpy as np

from database.qa_generator.passages import headings_of, trail_of
from extraction.models import PassageToExtract
from extraction.validation import HEADING_LABEL, label_word, numbered
from nlp.analysis import content, normalised
from nlp.embedding import cosine
from nlp.pipelines import pipeline

#: A quoted span, as two patterns by what opens it. A double mark closes at a
#: double mark and may hold apostrophes ("Customers’ rights"); a single mark
#: or an ASCII apostrophe opens at a word's edge and closes only where no
#: letter follows, so an apostrophe inside the span does not end it.
_QUOTED = (
    re.compile(
        r"[\"„“«‹›»”](?P<inner>[^\"„“”«»‹›\n]+?)[\"“”«»‹›]",
    ),
    re.compile(
        r"(?:‚|(?<!\w)[‘’'])"
        r"(?P<inner>(?:[^'\"„‚“”‘’«»‹›\n]|['’‘](?=\w))+?)"
        r"[‘’'](?!\w)"
    ),
)

#: A mark that may close a single-quoted span: one no letter follows.
_CLOSING = re.compile(r"[‘’'](?!\w)")

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
        head: The id of the passage that offered it, once `linked` dealt it.
            Shown first only on a reference it names: a sibling or a term
            link shows the earlier passage first, whichever headed it.
    """

    passages: tuple[PassageToExtract, ...]
    kind: str
    named: str
    head: int | None = None


def _segments(passage: PassageToExtract) -> list[str]:
    """The headings of a passage's trail, outermost first."""
    return [s.strip() for s in headings_of(passage.section_path) if s.strip()]


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
        #: Each passage's own heading, and per family one matrix of its
        #: vectors (a zero row where a passage has none), so a head scores
        #: its whole family in one product.
        self.last: dict[int, str] = {}
        self.matrix: dict[str, np.ndarray] = {}

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
        for at in range(len(tokens) - 1):
            word = label_word(tokens, at, words, language)
            if word is None:
                continue
            for number in numbered(tokens, at):
                named[(word, number)].add(tokens[at].sent.text)
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
            for inner in _quoted(head.text, headings)
            if (key := _plain(inner)) in headings
            and key not in mine
            and content(inner, language)
        ]
        quoted = [
            k for k in quoted if not any(k in parents[o] for o in quoted if o != k)
        ]
        for key in dict.fromkeys(quoted):
            reached = _nearest(head, [p for _, p in headings[key]])
            if reached is not None:
                label = next(s for s, p in headings[key] if p is reached)
                edges.add(head, reached, "reference", label)


def _quoted(text: str, headings: Container[str]) -> list[str]:
    """The quoted spans of a text, in the order they open.

    A single-quoted span closes at the first mark no letter follows, unless a
    later one on its line closes a longer span that is a heading: the
    possessive in ‘Customers’ fees’ closes nothing.
    """
    spans = [(m.start(), m.group("inner")) for m in _QUOTED[0].finditer(text)]
    for m in _QUOTED[1].finditer(text):
        inner = m.group("inner")
        line = text.find("\n", m.end())
        for mark in _CLOSING.finditer(text, m.end(), line if line >= 0 else len(text)):
            if _plain(longer := text[m.start("inner") : mark.start()]) in headings:
                inner = longer
        spans.append((m.start(), inner))
    return [inner for _, inner in sorted(spans)]


def _siblings(edges: _Edges, partners: Sequence[PassageToExtract]) -> None:
    """Groups the sections under one parent heading; `_best` reads the pairs."""
    for at, p in enumerate(partners):
        edges.position[p.id] = at
        trail = _segments(p)
        if len(trail) >= 2:
            edges.parent[p.id] = trail_of(trail[:-1])
            edges.family[edges.parent[p.id]].append(p)
        if trail:
            edges.last[p.id] = trail[-1]
    for parent, family in edges.family.items():
        width = next((len(p.embedding) for p in family if p.embedding), 0)
        if width:
            edges.matrix[parent] = np.array(
                [p.embedding or (0.0,) * width for p in family], dtype=np.float64
            )


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
    parent = edges.parent.get(partner.id)
    family = edges.family.get(parent, ()) if parent else ()
    near: dict[int, float] = {}
    if partner.embedding and parent in edges.matrix:
        scores = edges.matrix[parent] @ np.asarray(partner.embedding, np.float64)
        near = {
            p.id: float(score) if p.embedding else 0.0
            for p, score in zip(family, scores, strict=True)
        }
    mine = edges.last.get(partner.id)
    for other in family:
        if (
            other.id == partner.id
            or other.id in taken
            or edges.last.get(other.id) == mine
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
                -(
                    near[other]
                    if tier == _TIER["sibling"] and other in near
                    else _near(
                        partner, next(p for p in link.passages if p.id != partner.id)
                    )
                ),
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
            never offers one of them, and takes its next link instead. The
            links are dealt as if none were held, so a hold moves only the
            links on its own pairs.

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
        seen: set[frozenset[int]] = set()
        by_topic: dict[int, list[tuple[PassageToExtract, Link]]] = defaultdict(list)
        for head in (h for h in heads if (h.language or "") == language):
            topic = topic_of.get(head.id)
            if topic is None or topic in done:
                continue
            for _, link in _best(edges, head, set()):
                key = _pair(link)
                if key not in seen:
                    seen.add(key)
                    by_topic[topic].append((head, replace(link, head=head.id)))
                    break
        taken = seen | held
        for chosen in by_topic.values():
            # Grown before it is strided over: a pair that cannot reach `size`
            # must not take the slot of one that can.
            grown = [
                (head, g) for head, link in chosen if (g := _grown(edges, link, size))
            ]
            count = min(wanted, len(grown))
            step = (len(grown) - 1) / (count - 1) if count > 1 else 0
            for at in range(count):
                head, link = grown[round(at * step)]
                if _pair(link) in held:
                    link = _instead(edges, head, size, taken)
                if link is not None:
                    out.append(link)
    return out


def _pair(link: Link) -> frozenset[int]:
    """The pair a link was dealt on: its first two passages, unordered."""
    return frozenset(p.id for p in link.passages[:2])


def _instead(
    edges: _Edges, head: PassageToExtract, size: int, taken: set[frozenset[int]]
) -> Link | None:
    """A head's next link on a pair no other link takes or a bridge holds."""
    for _, link in _best(edges, head, set()):
        key = _pair(link)
        if key not in taken and (
            grown := _grown(edges, replace(link, head=head.id), size)
        ):
            taken.add(key)
            return grown
    return None


def _grown(edges: _Edges, link: Link, size: int) -> Link | None:
    """Extends a link to `size` passages through the last member's own links."""
    members = list(link.passages)
    while len(members) < size:
        taken = {p.id for p in members}
        options = _best(edges, members[-1], taken)
        if not options:
            return None
        members.append(next(p for p in options[0][1].passages if p.id not in taken))
    return Link(tuple(members), link.kind, link.named, link.head)
