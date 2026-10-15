"""Turning one topic's facts into the samples a question is written from.

Deterministic throughout: nothing draws a random number, so the same corpus
and the same settings give the same samples twice. A reference dataset whose
contents move between runs is not a reference.

A sample is an OFFER. Which facts a question is written from is the writer's
answer, not this module's: it is handed a sample and reports which facts one
question needed, and the difficulty is read off those.

Three things decide what is offered. The plan asks for a shape - one passage,
a neighbouring one, or one in another document. `size` caps the facts, and it
caps them per passage rather than by dropping a passage whole. Passages are
dealt strided over the whole topic rather than from its start, so a topic is
asked about across all of it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from enum import StrEnum
from functools import lru_cache
from itertools import groupby, zip_longest

import numpy as np

from database.qa_generator import FactKind
from nlp.analysis import content, numbers
from nlp.embedding import cosine
from question_generation.models import FactGroup, SourceFact


class Shape(StrEnum):
    """How wide a sample is.

    Each is one more scope above one, and so one more point of difficulty,
    which is what makes a band reachable at all: a question drawn from one
    passage cannot be cross-document however it is phrased.

      single  one passage                                       0 points
      cross   a passage in another document                     2 points
      bridge  one in another document AND another subject       3 points

    `cross` is two points and not one because a cross-document question is a
    multi-passage question by construction. A topic that cannot supply a
    shape gets the widest one it can: a topic sitting in one document has no
    cross-document question in it, and writing nothing about that subject is
    the worse answer.
    """

    SINGLE = "single"
    CROSS = "cross"
    BRIDGE = "bridge"


def spread(index: int, share: float) -> bool:
    """Whether the thing at this position is one of a share of them.

    Spread across the run by position instead of drawn at random, so a share
    of 0.25 picks exactly one in every four and picks the same four twice. 0
    never picks and 1 always does, without either needing a branch of its own.
    """
    return int((index + 1) * share) > int(index * share)


def overlap(left: Sequence[SourceFact], right: Sequence[SourceFact]) -> float:
    """How alike two passages are, in [0, 1].

    Cosine over `passages.embedding` where both carry one, and Jaccard over
    the content lemmas where either does not. It is what makes a pair of
    passages related rather than merely distant: pairing two passages because
    they came from different files produced questions about the first that
    carried a spread earned by the second.

    Cosine first because a lemma overlap cannot see a synonym. Two passages
    about one subject in different words share a direction and no vocabulary,
    and this corpus is full of that pair - `Testfall` against `Prüffall`,
    `Fehlerzustand` against `Defekt`. Jaccard scores those 0 and the sampler
    then pairs each of them with something genuinely unrelated instead.

    The fallback is not a transition: a corpus extracted before the column
    existed has no vectors at all, and `make extract-embed` is what gives it
    some.
    """
    near = _cosine(left[0].anchor.embedding, right[0].anchor.embedding)
    if near is not None:
        return near
    first, second = set(left[0].lemmas), set(right[0].lemmas)
    if not first or not second:
        return 0.0
    return len(first & second) / len(first | second)


def _cosine(
    left: tuple[float, ...] | None, right: tuple[float, ...] | None
) -> float | None:
    """How alike two unit vectors are, clamped to [0, 1], or None for neither.

    Clamped because every caller here reads a share: the vectors are
    normalised, so a dot product is already a cosine, and the negative half
    of its range means the same thing to a sampler as zero does.
    """
    if not left or not right:
        return None
    return max(0.0, cosine(list(left), list(right)))


@lru_cache(maxsize=8192)
def _words(statement: str, language: str | None) -> frozenset[str]:
    """The content lemmas of one statement, remembered between samples.

    The same reading `overlap` uses over a passage, taken over a fact
    instead. Cached because a passage is dealt once per round but every one
    of its facts is weighed against every candidate on the other side.
    """
    return content(statement, language)


def _restates(one: SourceFact, other: SourceFact) -> bool:
    """Whether two facts say the same thing, down to the words and the numbers.

    A copy of the same clause in a sibling document is the closest fact a
    topic holds and answers nothing the head does not. Differing numbers or
    words are different claims, so only the same content lemmas carrying the
    same numbers count.
    """
    return _words(one.statement, one.language) == _words(
        other.statement, other.language
    ) and numbers(one.statement, one.language) == numbers(
        other.statement, other.language
    )


def _relative_floor(facts: Sequence[SourceFact], share: float) -> float:
    """The cosine a second passage's fact must reach, read off the topic itself.

    The `share` closest pairs of facts from different passages mark where
    "close" sits in this topic's own vectors, so no cosine has to be tuned to
    a corpus or a language: a dense topic and a sparse one each set their own
    bar. The closest pair always clears it, so even a small topic keeps a
    pair. 0.0 where `share` is not positive or the topic holds no pair of
    embedded facts from different passages.
    """
    if share <= 0:
        return 0.0
    embedded = [fact for fact in facts if fact.embedding]
    if len(embedded) < 2:
        return 0.0
    vectors = np.array([fact.embedding for fact in embedded], dtype=float)
    ids = np.array([fact.passage_id for fact in embedded])
    pairs = np.triu(ids[:, None] != ids[None, :], k=1)
    if not pairs.any():
        return 0.0
    cosines = np.clip((vectors @ vectors.T)[pairs], 0.0, 1.0)
    return float(np.quantile(cosines, 1 - share))


def meets(chosen: Sequence[SourceFact], candidate: SourceFact) -> float:
    """How much one fact has in common with the facts already offered, in [0, 1].

    The same measure `overlap` pairs passages with, one level down: cosine
    over `facts.embedding` where the statements carry one, Jaccard over their
    content lemmas where they do not. Two passages the corpus says are about
    related things still hold facts that are about nothing in common, and
    pairing the top-ranked fact of each produced questions welding a date to
    a category: `Wodurch unterscheiden sich MT und modellbasiertes Testen
    hinsichtlich Einordnung und erstmaliger Nennung?` is two facts in a
    trenchcoat, and no honest question spans them.

    Against the closest of the chosen rather than their mean. A mean of
    several vectors points somewhere none of them is, so a third fact is
    weighed against a subject the offer does not hold; what the writer needs
    is a fact that meets ONE of the others, which is what a question spans.
    """
    near = max(
        (
            found
            for one in chosen
            if (found := _cosine(one.embedding, candidate.embedding)) is not None
        ),
        default=None,
    )
    if near is not None:
        return near
    subject = frozenset().union(
        *(_words(one.statement, one.language) for one in chosen)
    )
    other = _words(candidate.statement, candidate.language)
    if not subject or not other:
        return 0.0
    return len(subject & other) / len(subject | other)


def closest(
    chosen: Sequence[SourceFact], candidates: Sequence[SourceFact], wanted: int
) -> list[SourceFact]:
    """The candidates with most in common with what is already offered.

    Rank order when nothing is offered yet, which is the first passage of
    every sample: there is nothing to be close to, and `ranked` has already
    said which of a passage's facts is worth asking about.

    Ties go to the lower fact id, so the same corpus deals the same sample
    twice.
    """
    if not chosen or not candidates:
        return list(candidates[:wanted])
    return sorted(candidates, key=lambda one: (-meets(chosen, one), one.id))[:wanted]


#: The order the kinds are interleaved in. Atomic first because it is the
#: shape every prompt here assumes; the rest as EXTRACTION_KINDS writes them.
_KINDS = (FactKind.ATOMIC, FactKind.SUMMARY, FactKind.OUTLINE, FactKind.BRIDGE)

#: The kinds that stand in for a whole passage rather than one sentence of
#: it. Extraction calls them condensed, and holds them to a check of that
#: name.
CONDENSED = (FactKind.SUMMARY, FactKind.OUTLINE)


def condensed_first(facts: Sequence[SourceFact]) -> list[SourceFact]:
    """The same facts with the ones standing in for a whole passage first.

    What a sample is reordered by when the answer is not a bare value. A
    condensed fact is longer than an atomic claim and carries several
    predicates where one carries a single predicate, so a type whose answer
    is a reading of a passage is offered those before the single sentences.
    A `value` is not: a factoid, an entity and an aggregation
    want the fact carrying a number, which is what `ranked` already puts
    first within a kind.

    Stable within each half, so `ranked`'s orderings survive: units first
    inside a kind, and the kinds interleaved.

    The ordering does not change the supply: a passage is dealt `rounds`
    times and never with a fact twice, so every fact it holds is offered
    either way.
    """
    return sorted(facts, key=lambda one: one.kind not in CONDENSED)


def _ordered(
    facts: Sequence[SourceFact],
    condensed: bool,
    prefer: Callable[[SourceFact], bool] | None,
) -> list[SourceFact]:
    """A passage's unspent facts in the order a sample offers them.

    The condensed ones first for a reading, and ahead of either half the
    ones `prefer` accepts. Stable throughout, so `ranked`'s order survives
    inside each part. Only the head's order is read: the second passage's
    share is re-ranked by what the head offered.
    """
    ordered = condensed_first(facts) if condensed else list(facts)
    if prefer is None:
        return ordered
    return sorted(ordered, key=lambda one: not prefer(one))


def ranked(facts: Iterable[SourceFact]) -> list[SourceFact]:
    """One passage's facts, its kinds interleaved and each kind's best first.

    Two orderings in one.

    Within a kind, the facts asserting a value come first: a fact carrying a
    number, a date or an amount is what a checkable question is written
    from, so it is offered before one that carries none.

    Across kinds, one of each in turn. A passage yields far more atomic
    facts than anything else, so a sample capped at four spent all four on
    atomic claims and left the summary and the outline unoffered - and those
    two are what the types a single claim cannot answer are written from: a
    definition asks what something IS, an enumeration wants a real set, and
    neither is in one sentence of a passage.
    """
    held: dict[str, list[SourceFact]] = {}
    for fact in sorted(facts, key=lambda one: (not one.units, one.id)):
        held.setdefault(fact.kind, []).append(fact)
    ordered = [held[kind] for kind in _KINDS if kind in held]
    return [fact for row in zip_longest(*ordered) for fact in row if fact is not None]


def by_passage(facts: Iterable[SourceFact]) -> list[list[SourceFact]]:
    """Each passage's facts, ranked, the passages in corpus order."""
    ordered = sorted(
        facts, key=lambda one: (one.doc_sha256, one.ordinal, one.passage_id, one.id)
    )
    return [
        ranked(group) for _, group in groupby(ordered, key=lambda one: one.passage_id)
    ]


def interleaved(passages: list[list[SourceFact]]) -> list[list[SourceFact]]:
    """The passages, taken one document at a time in turn.

    So a run over a topic reaches every document the topic sits in before it
    reaches any document twice.
    """
    by_document: dict[str, list[list[SourceFact]]] = {}
    for passage in passages:
        by_document.setdefault(passage[0].doc_sha256, []).append(passage)
    return [
        passage
        for row in zip_longest(*by_document.values())
        for passage in row
        if passage is not None
    ]


def strided(items: list, wanted: int) -> list:
    """The items reordered so the first `wanted` are spread over all of them.

    Nothing is dropped: the rest follow in their own order, so asking for more
    than were spread still reaches them.
    """
    if wanted <= 0 or wanted >= len(items):
        return items
    step = len(items) / wanted
    taken = {int(position * step) for position in range(wanted)}
    # Built once. Spelled `not in set(picked)` inside the comprehension, it
    # was rebuilt per item, which is the whole list walked again for every
    # passage of every topic.
    rest = [index for index in range(len(items)) if index not in taken]
    return [items[index] for index in sorted(taken) + rest]


class Deal:
    """One topic's passages, handed out as samples of facts not yet used.

    A passage may be offered `rounds` times, and never twice with the same
    fact: what must not repeat is the material a question is written from,
    not the passage it sits in. A passage carrying a dozen facts holds a
    dozen questions, and offering it once was the ceiling on the whole
    stage.

    Rounds are a ceiling and the facts are the real limit: a passage runs
    out when nothing unspent is left in it, so a thin passage yields one
    sample and a dense one yields several, without either being configured.
    """

    def __init__(
        self,
        facts: Iterable[SourceFact],
        bridges: Iterable[SourceFact] = (),
        *,
        wanted: int,
        size: int,
        rounds: int = 1,
        floor: float = 0.0,
        share: float = 0.0,
    ) -> None:
        """Deals one topic's facts, strided over the whole of it.

        `floor` is QUESTIONS_MEETS_FLOOR: how much the second passage's best
        fact must have in common with the head before a second passage is
        offered at all. 0 offers one whatever it holds. `share` is
        QUESTIONS_MEETS_SHARE, the share of the topic's closest cross-passage
        fact pairs a second passage must be among; 0 sets no relative floor.
        """
        facts = list(facts)
        bridges = list(bridges)
        self._order = strided(interleaved(by_passage(facts)), wanted)
        self._bridges = interleaved(by_passage(bridges))
        #: Every passage this topic can offer, by id. `widen` reaches a
        #: passage by name rather than by turn, and a bridge's passages are
        #: in here too because a thread may have started on one.
        self._by_passage = {
            passage[0].passage_id: passage for passage in (*self._bridges, *self._order)
        }
        self._size = max(size, 1)
        self._rounds = max(rounds, 1)
        self._offered: dict[int, int] = {}
        self._spent: set[int] = set()
        self._floor = max(floor, _relative_floor([*facts, *bridges], share))
        #: Whether a floor is in force, which is when copies are refused too.
        self._ceiling = floor > 0 or share > 0

    def sample(
        self,
        shape: str = Shape.SINGLE,
        condensed: bool = False,
        prefer: Callable[[SourceFact], bool] | None = None,
    ) -> FactGroup | None:
        """The next sample of the shape asked for, or None when none is left.

        A shape the topic cannot supply falls back to a narrower one rather
        than yielding nothing: a topic sitting in one document has no
        cross-document question in it, and refusing to write anything about it
        would leave the subject uncovered.

        `condensed` offers the facts standing in for a whole passage ahead of
        the single claims - see `condensed_first`. Set from the answer form
        the plan asked for, because a value wants the claim carrying a number
        and a reading wants the paragraph.

        `prefer` deals the next passage still holding a fact it accepts, and
        offers those facts first. `holds` is what asks whether one is left.
        """
        head = self._next(prefer)
        if head is None:
            return None
        if shape == Shape.SINGLE or head[0].spans:
            # A fact that already rests on several passages is asked about
            # alone: it satisfies a wide shape by itself, and pairing it with
            # a second passage would put the sample over the budget and make
            # what the question is about impossible to read off.
            return self._group([head], condensed=condensed, prefer=prefer)

        partner = self._bridge(head) if shape == Shape.BRIDGE else self._cross(head)
        if partner and not self._clears(head, partner, condensed, prefer):
            # Nothing in the second passage meets the first well enough to
            # be worth offering. The span rules already tell the writer to
            # narrow in this case; this narrows for it, and the question
            # bands as the single-passage question it actually is.
            partner = None
        return self._group(
            [head, partner] if partner else [head], condensed=condensed, prefer=prefer
        )

    def holds(self, prefer: Callable[[SourceFact], bool]) -> bool:
        """Whether a passage still to be dealt holds a fact `prefer` accepts.

        Asked before a sample is dealt with it, so a slot the topic cannot
        supply is answered by the caller and spends nothing.
        """
        return self._next(prefer) is not None

    def _clears(
        self,
        head: list[SourceFact],
        partner: list[SourceFact],
        condensed: bool,
        prefer: Callable[[SourceFact], bool] | None = None,
    ) -> bool:
        """Whether the partner holds a fact close enough to the head to offer.

        Where a floor is in force, facts that only restate the head's are set
        aside first, and a partner holding nothing else is refused.

        Read off the BEST the partner can do rather than its average: one
        fact meeting the head is what a question spans, which is the same
        reading `meets` makes of a sample already part-chosen.

        Weighed against the head's fact `_group` will offer first, which
        `condensed` and `prefer` decide. The first in rank order is an
        atomic claim that a reading is never offered, so the floor would
        pass a pair on a fact the writer never sees.

        Abstains where either side has nothing left, because a measurement
        with nothing to measure is not evidence - the same bargain
        `on_topic` and `about` make.
        """
        offered = _ordered(self._left(head), condensed, prefer)[:1]
        candidates = self._left(partner)
        if not offered or not candidates:
            return True
        if self._ceiling:
            candidates = [one for one in candidates if not _restates(offered[0], one)]
            if not candidates:
                return False
        if self._floor <= 0:
            return True
        return max(meets(offered, one) for one in candidates) >= self._floor

    def widen(self, group: FactGroup, more: int = 1) -> FactGroup:
        """The same sample with unspent facts of the same passages added.

        What a follow-up is written from. Handed the root's own sample it
        has nothing to ask that the root did not already answer, and the
        type cycle then asks for the same fact in another shape.

        The SAME passages, because a thread that changes material is not a
        conversation - that is what `same_material` refuses at the other
        end. So this widens rather than deals: it never reaches a passage
        the root did not use.

        Rounds are not counted against the passage and `_taken` is not
        consulted, for the same reason. A thread is one subject followed
        down, not another turn of the rotation, and a passage whose rounds
        are spent is still the passage this conversation is about.

        Returns the group unchanged where the passages hold nothing
        unspent. The follow-up is then written from what the root had, and
        `asks_nothing_new` is what refuses it if it asks nothing new - a
        thread that stops because the material ran out is the honest
        outcome, not one to manufacture a turn for.
        """
        fresh: list[SourceFact] = []
        for pid in dict.fromkeys(passage.id for passage in group.resting):
            passage = self._by_passage.get(pid)
            if not passage:
                continue
            fresh.extend(closest(list(group.facts) + fresh, self._left(passage), more))
        for fact in fresh:
            self._spent.add(fact.id)
        return FactGroup((*group.facts, *fresh)) if fresh else group

    def _left(self, passage: list[SourceFact]) -> list[SourceFact]:
        """The facts of this passage no sample has taken yet, in rank order."""
        return [fact for fact in passage if fact.id not in self._spent]

    def _taken(self, passage: list[SourceFact]) -> bool:
        """Whether this passage has nothing left to offer.

        Either it has been offered its share of times, or every fact in it
        has already been written from. The second is the one that binds on
        a thin passage, and it is why `rounds` can be raised without any
        risk of dealing the same material twice.
        """
        return self._offered.get(passage[0].passage_id, 0) >= self._rounds or not (
            self._left(passage)
        )

    def _next(
        self, prefer: Callable[[SourceFact], bool] | None = None
    ) -> list[SourceFact] | None:
        """The next passage with something still to be written from.

        With `prefer`, the next one holding an unspent fact it accepts.
        """
        for passage in self._order:
            if not self._taken(passage) and (
                prefer is None or any(prefer(one) for one in self._left(passage))
            ):
                return passage
        return None

    def _cross(self, head: list[SourceFact]) -> list[SourceFact] | None:
        """A passage in another document, or the likeliest one in this document.

        Ranked by `overlap`, so the pair is two passages the corpus itself
        says are about related things. Pairing two passages because
        they came from different files produced questions about the first
        carrying a spread earned by the second.

        The fallback is the passage of the same document most like the head,
        by the same `overlap`. It is one point rather than two, and it is what
        a topic sitting in one document has.
        """
        return self._best(head, self._free(head, elsewhere=True)) or self._neighbour(
            head
        )

    def _bridge(self, head: list[SourceFact]) -> list[SourceFact] | None:
        """A bridging passage, preferably in another document.

        A bridge belongs to some other topic more strongly than to this one
        but carries this one above the weight floor, so the corpus itself says
        the two subjects meet there. One in another document is in another
        document AND another subject, which is every scope above one at once.
        """
        return (
            self._best(head, self._free(head, elsewhere=True, bridging=True))
            or self._best(head, self._free(head, bridging=True))
            or self._cross(head)
        )

    def _free(
        self,
        head: list[SourceFact],
        *,
        elsewhere: bool = False,
        bridging: bool = False,
    ) -> list[list[SourceFact]]:
        """The passages still to be had, narrowed to what a shape wants."""
        return [
            passage
            for passage in (self._bridges if bridging else self._order)
            if not self._taken(passage)
            and passage[0].passage_id != head[0].passage_id
            and (not elsewhere or passage[0].doc_sha256 != head[0].doc_sha256)
        ]

    def _best(
        self, head: list[SourceFact], candidates: list[list[SourceFact]]
    ) -> list[SourceFact] | None:
        """Whichever candidate meets the head best, or None.

        Ties go to the lower passage id, so the same corpus deals the same
        pair twice.

        The measure embeds the two passages apart and compares directions,
        which is what an index can serve and is what narrows thousands of
        passages to a handful. A cross-encoder reading the pair together is
        the better judgement and used to reorder the shortlist here.
        """
        if not candidates:
            return None
        return min(candidates, key=lambda one: (-overlap(head, one), one[0].passage_id))

    def _neighbour(self, head: list[SourceFact]) -> list[SourceFact] | None:
        """The unused passage of the same document most like the head.

        Likeness first, as `_best` ranks: a topic's passages are not
        contiguous, so the next one in reading order may be about something
        else and pairing it is the weld. Reading order breaks a tie, because
        passages are numbered as they are read and the nearest is then the
        rest of the same section.
        """
        candidates = [
            passage
            for passage in self._free(head)
            if passage[0].doc_sha256 == head[0].doc_sha256
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda one: (
                -overlap(head, one),
                abs(one[0].ordinal - head[0].ordinal),
                one[0].passage_id,
            ),
        )

    def _group(
        self,
        passages: list[list[SourceFact]],
        condensed: bool = False,
        prefer: Callable[[SourceFact], bool] | None = None,
    ) -> FactGroup:
        """Counts a round against these passages and offers unspent facts.

        The cap is divided between the passages rather than applied to the
        sample, so a wide sample offers both sides of what it is asking about
        instead of filling itself from the first passage.

        Only facts nothing has been written from, so the second round over a
        passage asks about the rest of it rather than about the same few
        sentences again. The facts taken are spent whatever the writer does
        with them: a sample is an offer, but offering it twice would put the
        dedup gate in the way of the same question twice.

        A passage a chosen fact rests on but which was not itself offered is
        used up whole - that is a bridge's second passage, which has been
        asked about once the bridge has.

        The second passage's share is the facts closest to what the first
        offered, not its own best. Its own best is what it would have given
        to a question of its own, and two passages the corpus calls related
        still hold facts with nothing between them: offering those produced
        a question welding them together with "and", which is the failure
        the span rules spend three paragraphs on.
        """
        each = max(1, self._size // len(passages))
        offered = {passage[0].passage_id for passage in passages}
        facts: list[SourceFact] = []
        for passage in passages:
            pid = passage[0].passage_id
            self._offered[pid] = self._offered.get(pid, 0) + 1
            left = _ordered(self._left(passage), condensed, prefer)
            facts.extend(closest(facts, left, each))
        for fact in facts:
            self._spent.add(fact.id)
            for one in fact.passages:
                if one.id not in offered:
                    self._offered[one.id] = self._rounds
        return FactGroup(tuple(facts))
