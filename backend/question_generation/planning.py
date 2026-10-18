"""What to write before anything is written: the plan for one topic.

A plan is a type, a difficulty band to aim for, the shape of sample that band
needs, and whether the question is meant to have an answer at all. It is
decided before the writer is called, because the prompt, the answer bounds
and the gates all differ by type.

Nothing here draws a random number. Two mixes are turned into an exact,
repeatable sequence of slots, so the same settings over the same corpus give
the same plan twice. The paper's categories are dealt the same way: an exact
quota per categorization, put in an order hashed from the topic, so the same
topic is told the same categories twice.

The band is a request, not a verdict. `difficulty` is still read off what the
question turned out to cite; `planned_difficulty` is this, stored beside it,
and the two disagreeing is a measurement of how often the plan was met.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from math import floor

from database.qa_generator import Difficulty, QuestionKind, QuestionType
from question_generation.models import Categorization, Category
from question_generation.selection import Shape, spread
from question_generation.types import SPECS, TypeSpec

#: The sample shape each band needs, and what each is worth. A cross-document
#: question is a multi-passage question by construction, so `cross` is the two
#: points `medium` wants; a bridging passage in another document adds the
#: third subject scope, which is `hard`.
SHAPES: dict[str, str] = {
    Difficulty.EASY: Shape.SINGLE,
    Difficulty.MEDIUM: Shape.CROSS,
    Difficulty.HARD: Shape.BRIDGE,
}

#: The kinds an unanswerable slot may be written as: those asking for one
#: detail (a value, a party, a reason) that the material can leave out while
#: saying everything around it. A set, a condition, a definition, a procedure
#: or a consequence is what a closed list, a categorical rule or a definition
#: settles, and drafts of those kinds were answered about two times in three
#: against under one in two for these.
PERTURBABLE: frozenset[str] = frozenset(
    {QuestionType.FACTOID, QuestionType.ENTITY, QuestionType.REASON}
)


@dataclass(frozen=True)
class Plan:
    """One question to write, decided before it is written."""

    spec: TypeSpec
    band: str
    shape: str
    answerable: bool
    #: What the slot is dealt to be: `single` for a one-passage slot, and
    #: for a spanning one the kind the mix chose. Looked up in `KINDS`.
    kind: str = QuestionKind.SINGLE
    #: The category of each categorization the question is written as. An
    #: unanswerable slot is dealt them too and the writer renders none: the
    #: paper asks only questions that have an answer.
    categories: tuple[Category, ...] = ()

    @property
    def spans(self) -> bool:
        """Whether the writer is told to use more than one passage."""
        return self.shape != Shape.SINGLE


def allocate(weights: Mapping[str, int], slots: int) -> list[str]:
    """Spreads `slots` over named weights, proportionally and in order.

    Highest averages: each slot goes to whichever name is furthest behind its
    share so far. Over a whole run the counts are the weights; along the run
    the names are interleaved rather than run in blocks, which matters because
    other decisions - the unanswerable share, the follow-up share - are also
    taken by position and would otherwise always land on the same name.

    A weight of zero never takes a slot, which is how a type is turned off.
    """
    wanted = {name: weight for name, weight in weights.items() if weight > 0}
    if not wanted or slots <= 0:
        return []

    order = list(wanted)
    taken = dict.fromkeys(order, 0)
    chosen: list[str] = []
    for _ in range(slots):
        name = max(
            order,
            key=lambda one: (wanted[one] / (2 * taken[one] + 1), -order.index(one)),
        )
        taken[name] += 1
        chosen.append(name)
    return chosen


def plans(
    *,
    wanted: int,
    types: Mapping[str, int],
    bands: Mapping[str, int],
    unanswerable_share: float,
    kinds: Mapping[str, int] | None = None,
    categorizations: Sequence[Categorization] = (),
    seed: str = "",
) -> list[Plan]:
    """The questions one topic is to be asked, in the order they are written.

    A slot that came up `easy` is raised to whatever floor its type declares.
    Usually that is `easy` and nothing moves. A type needing more than one
    passage cannot be easy by construction - the band is a request for a
    shape of sample and `easy` offers one passage, so a comparison drawn
    from one is a question about one thing. A type needing one passage may
    still decline the band: an `application` puts a rule in the material to
    a case that is not, which is not a lookup however little it reaches.
    Such a type is still dealt the one passage it declares, whatever band
    it carries. Its band is the work the case takes, not a wider sample, and
    handed two passages and told to use both it welds the second one on.

    An unanswerable question is planned `easy` and single whatever its slot
    said. It is written by moving one fact out of reach, so a second passage
    has nothing to do, and a chatbot declining it is not made cleverer by the
    question having spanned two documents.

    And its TYPE is swapped for a kind of the mix that asks for one detail
    (PERTURBABLE: factoid, entity, reason, those weighted above 0), because
    the writer is handed one fact to perturb: an unanswerable `comparison`
    has one side and an unanswerable `aggregation` has one number, and
    neither is the kind of question it was planned to be. The kinds are
    cycled in mix order, so the swap is spread over them rather than landing
    on one. A mix with none of them writes the slot answerable, in the kind
    it was allocated: writing nothing loses the slot, and writing a set or a
    condition unanswerable mostly writes a question the material settles.

    Every slot carries a kind. A one-passage slot is `single`; a slot whose
    type spans is `needs_both` by construction; the other spanning slots
    share out `kinds` in order, which holds `needs_both` alone when not given.

    Every slot is dealt `categorizations`, in an order keyed on `seed`; see
    `categories`.
    """
    typed = allocate(types, wanted)
    banded = allocate(bands, wanted)
    if not typed or not banded:
        return []

    dealt = categories(categorizations, len(typed), seed)
    detail = _perturbable(types)
    planned = []
    perturbed = 0
    for index, name in enumerate(typed):
        answerable = not spread(index, unanswerable_share)
        band = banded[index % len(banded)]
        if not answerable:
            if detail:
                name = detail[perturbed % len(detail)]
                perturbed += 1
            else:
                answerable = True
        planned.append(_slot(name, band, answerable, dealt[index]))
    return _kinded(planned, kinds or {QuestionKind.NEEDS_BOTH: 1})


def _kinded(planned: list[Plan], kinds: Mapping[str, int]) -> list[Plan]:
    """The plan with each spanning slot given its kind, in slot order."""
    shared = [one for one in planned if one.spans and not one.spec.spans]
    dealt = iter(allocate(kinds, len(shared)))
    kinded = []
    for one in planned:
        kind = QuestionKind.SINGLE
        if one.spans:
            kind = QuestionKind.NEEDS_BOTH if one.spec.spans else next(dealt)
        kinded.append(_dealt(one, kind))
    return kinded


def _dealt(plan: Plan, kind: str) -> Plan:
    """The slot as the kind it is dealt: a compound one is shaped apart."""
    if kind == QuestionKind.COMPOUND:
        return replace(plan, kind=kind, shape=Shape.APART)
    return replace(plan, kind=kind)


def categories(
    categorizations: Sequence[Categorization], slots: int, seed: str
) -> list[tuple[Category, ...]]:
    """The category of every categorization for each of `slots` questions.

    Each categorization's quota gives every category its share of the slots,
    rounded up or down. The quota is then put in an order of its own, hashed
    from the seed, the categorization and the place. Two categorizations in
    step would only ever pair their first categories and their second ones;
    in orders of their own every pairing occurs, as the paper's independent
    draws give. And a topic that runs out of material after its first slots
    has drawn a fair sample of the quota rather than its first category.
    """
    columns = []
    for one in categorizations:
        quota = _quota(one, slots, seed)
        order = sorted(range(slots), key=lambda place: _hashed(seed, one.name, place))
        columns.append([quota[place] for place in order])
    return [tuple(column[slot] for column in columns) for slot in range(slots)]


def _quota(categorization: Categorization, slots: int, seed: str) -> list[Category]:
    """Each category's share of the slots, rounded where the seed says.

    Systematic rounding: one offset per topic, hashed from the seed, decides
    which shares round up. Rounding the same way for every topic would hand
    the spare slot to the same category each time - at 11 slots, 6 to 5 for
    an even pair in every topic of a run.
    """
    offset = int.from_bytes(_hashed(seed, categorization.name)[:8]) / 2**64
    quota: list[Category] = []
    share = 0.0
    for category in categorization.categories[:-1]:
        share += category.probability
        quota += [category] * (floor(slots * share + offset) - len(quota))
    return quota + [categorization.categories[-1]] * (slots - len(quota))


def _hashed(seed: str, *parts: object) -> bytes:
    """A digest of the seed and the parts, which nothing random could repeat."""
    return hashlib.md5("|".join(map(str, (seed, *parts))).encode()).digest()


def instead(plan: Plan, types: Mapping[str, int], turn: int) -> Plan | None:
    """The same slot as another kind, for a kind the topic cannot supply.

    What a `reason` slot becomes where no fact left in the topic states a
    reason. The swap the unanswerable slots get, for the same reason: the
    slot was planned before the material was read, and writing the kind
    anyway gets a question its material cannot answer. Cycled over the
    mix's other kinds that do not span, by `turn`, with the slot's band.

    And with the slot's shape, and so its kind. A slot the writer declined
    has its sample dealt already: re-shaped by its band, a one-passage
    `application` slot became a two-passage factoid still dealt `single`,
    told to span a sample of one. So a spanning slot is not swapped for a
    kind dealt one passage at any band, which handed two would weld the
    second on.

    None where the mix holds no other such kind. A slot asking for what the
    topic does not have is then not written: unlike an unanswerable one, a
    reason with nothing to rest on is a question with no right answer.
    """
    others = [
        name
        for name in _alone(types)
        if name != plan.spec.name and not (plan.spans and _one_passage(SPECS[name]))
    ]
    if not others:
        return None
    other = _slot(
        others[turn % len(others)], plan.band, plan.answerable, plan.categories
    )
    other = replace(other, shape=plan.shape)
    return _dealt(other, plan.kind if other.spans else QuestionKind.SINGLE)


def _alone(types: Mapping[str, int]) -> list[str]:
    """The kinds of the mix that do not span, in mix order."""
    return [
        name for name, weight in types.items() if weight > 0 and not SPECS[name].spans
    ]


def _perturbable(types: Mapping[str, int]) -> list[str]:
    """The kinds of the mix an unanswerable slot may be written as."""
    return [name for name in _alone(types) if name in PERTURBABLE]


def _one_passage(spec: TypeSpec) -> bool:
    """Whether a kind is dealt one passage whatever band it carries."""
    return spec.least is not None and not spec.spans


def _slot(
    name: str,
    band: str,
    answerable: bool,
    categories: tuple[Category, ...] = (),
) -> Plan:
    """One slot of a kind, its band raised to the kind's floor and shaped."""
    spec = SPECS[name]
    if band == Difficulty.EASY:
        band = spec.floor
    if not answerable:
        band = Difficulty.EASY
    single = not answerable or _one_passage(spec)
    shape = Shape.SINGLE if single else SHAPES[band]
    return Plan(
        spec=spec,
        band=band,
        shape=shape,
        answerable=answerable,
        categories=categories,
    )
