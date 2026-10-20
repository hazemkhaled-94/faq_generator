"""What a topic is planned to be asked, before anything is written.

The plan is what makes the set configurable: a type with no weight is never
written, and a band is a request for a shape of sample rather than a verdict
about a question. Nothing here calls a model.
"""

from __future__ import annotations

from collections import Counter

from database.qa_generator import Difficulty, QuestionKind, QuestionType
from question_generation.planning import allocate, instead, plans
from question_generation.selection import Shape, spread
from question_generation.types import SPECS

MIX = {
    QuestionType.FACTOID: 3,
    QuestionType.REASON: 2,
    QuestionType.COMPARISON: 1,
}

BANDS = {Difficulty.EASY: 2, Difficulty.MEDIUM: 2, Difficulty.HARD: 1}


def planned(**kwargs):
    """One topic's plan, with the mixes above unless a test says otherwise."""
    return plans(
        **{
            "wanted": 12,
            "types": MIX,
            "bands": BANDS,
            "unanswerable_share": 0.0,
            **kwargs,
        }
    )


# ── The allocator, which is what a mix means ──────────────────────────────


def test_the_weights_are_the_counts_over_a_whole_run() -> None:
    """3:2:1 over twelve slots is six, four and two."""
    counts = Counter(allocate(MIX, 12))

    assert counts == {
        QuestionType.FACTOID: 6,
        QuestionType.REASON: 4,
        QuestionType.COMPARISON: 2,
    }


def test_a_weight_of_zero_is_never_written() -> None:
    """Which is the switch for choosing what a run produces."""
    chosen = allocate({**MIX, QuestionType.REASON: 0}, 20)

    assert QuestionType.REASON not in chosen
    assert set(chosen) == {QuestionType.FACTOID, QuestionType.COMPARISON}


def test_the_types_are_interleaved_rather_than_run_in_blocks() -> None:
    """Other decisions are taken by position too.

    The unanswerable share and the follow-up share both read the slot number,
    so a mix run in blocks would always perturb the same type.
    """
    chosen = allocate(MIX, 12)

    assert chosen[:4] != [QuestionType.FACTOID] * 4
    assert len(set(chosen[:3])) > 1


def test_the_same_mix_allocates_the_same_slots_twice() -> None:
    """A reference dataset that moves between runs is not a reference."""
    assert allocate(MIX, 25) == allocate(MIX, 25)


def test_asking_for_nothing_allocates_nothing() -> None:
    """Zero slots and an empty mix are both answers, not failures."""
    assert allocate(MIX, 0) == []
    assert allocate({}, 10) == []


# ── The plan itself ───────────────────────────────────────────────────────


def test_every_slot_asked_for_is_planned() -> None:
    """QUESTIONS_PER_TOPIC is how many questions a topic is asked."""
    assert len(planned(wanted=12)) == 12


def test_each_band_gets_the_shape_that_makes_it_reachable() -> None:
    """A question drawn from one passage cannot be cross-document."""
    shapes = {one.band: one.shape for one in planned(wanted=30)}

    assert shapes[Difficulty.EASY] == Shape.SINGLE
    assert shapes[Difficulty.MEDIUM] == Shape.CROSS
    assert shapes[Difficulty.HARD] == Shape.BRIDGE


def test_a_type_needing_two_passages_is_never_planned_easy() -> None:
    """A comparison drawn from one passage is a question about one thing."""
    spanning = [
        one for one in planned(wanted=30, unanswerable_share=0.0) if one.spec.spans
    ]

    assert spanning
    assert all(one.band != Difficulty.EASY for one in spanning)
    assert all(one.shape != Shape.SINGLE for one in spanning)


def test_a_type_needing_one_passage_may_still_decline_easy() -> None:
    """An `application` puts a rule in the material to a case that is not.

    Needing two passages is one reason not to be easy and was being read as
    the only one, which cost this type its medium and hard slots to a band
    it should never have been planned at.
    """
    built = plans(
        wanted=30,
        types={QuestionType.APPLICATION: 1},
        bands=BANDS,
        unanswerable_share=0.0,
    )

    assert built
    assert not any(one.spec.spans for one in built), "it needs one passage"
    assert all(one.band != Difficulty.EASY for one in built)
    assert {one.band for one in built} == {Difficulty.MEDIUM, Difficulty.HARD}
    # Its band is the work the case takes, not a wider sample: it is dealt
    # the one passage it declares.
    assert all(one.shape == Shape.SINGLE for one in built)


def test_a_one_passage_type_is_not_dealt_two_passages_and_told_to_span() -> None:
    """Whatever band its slot came up, in a mix of other kinds.

    Dealt two passages and told to use both, a type whose rule sits in one
    passage welds the second one on.
    """
    built = plans(
        wanted=30,
        types={
            QuestionType.APPLICATION: 1,
            QuestionType.FACTOID: 1,
            QuestionType.COMPARISON: 1,
        },
        bands=BANDS,
        unanswerable_share=0.25,
    )

    applications = [
        one
        for one in built
        if one.spec.name == QuestionType.APPLICATION and one.answerable
    ]
    assert applications
    assert not [one for one in applications if one.spans]
    # The other kinds keep the shape their band asks for.
    assert any(one.spans for one in built if one.spec.name == QuestionType.FACTOID)


def test_a_type_declaring_no_floor_is_still_planned_easy() -> None:
    """The floor is an exception, not a new default."""
    built = plans(
        wanted=30,
        types={QuestionType.FACTOID: 1},
        bands=BANDS,
        unanswerable_share=0.0,
    )

    assert any(one.band == Difficulty.EASY for one in built)


def test_the_floor_is_read_off_the_type_rather_than_its_passage_count() -> None:
    """Both reasons reach the same field, so the planner asks once."""
    assert SPECS[QuestionType.FACTOID].floor == Difficulty.EASY
    assert SPECS[QuestionType.COMPARISON].floor == Difficulty.MEDIUM, "spans"
    assert SPECS[QuestionType.APPLICATION].floor == Difficulty.MEDIUM, "declared"


def test_an_unanswerable_question_is_planned_easy_and_from_one_passage() -> None:
    """It is written by moving one fact out of reach.

    A second passage has nothing to do with that, and a chatbot declining a
    question is not made cleverer by the question having spanned two files.
    """
    unanswerable = [one for one in planned(unanswerable_share=1.0)]

    assert unanswerable
    assert all(one.shape == Shape.SINGLE for one in unanswerable)
    assert all(one.band == Difficulty.EASY for one in unanswerable)


def test_the_unanswerable_share_lands_on_more_than_one_type() -> None:
    """The aliasing an interleaved allocation exists to prevent."""
    perturbed = {
        one.spec.name
        for one in planned(wanted=24, unanswerable_share=0.25)
        if not one.answerable
    }

    assert len(perturbed) > 1


def test_a_plan_says_whether_the_writer_is_told_to_span() -> None:
    """The instruction follows the sample, not the type.

    A factoid drawn from two documents is a cross-document factoid, and the
    writer has to be told to use both halves or it answers the first.
    """
    wide = next(one for one in planned(wanted=30) if one.shape != Shape.SINGLE)
    narrow = next(one for one in planned(wanted=30) if one.shape == Shape.SINGLE)

    assert wide.spans
    assert not narrow.spans
    assert "MORE THAN ONE" in wide.spec.system(spans=wide.spans)
    assert "MORE THAN ONE" not in SPECS[QuestionType.FACTOID].system()


def test_the_same_settings_plan_the_same_topic_twice() -> None:
    """Two runs of one corpus have to produce one dataset."""
    first = [(one.spec.name, one.band, one.shape) for one in planned()]
    second = [(one.spec.name, one.band, one.shape) for one in planned()]

    assert first == second


# ── The unanswerable slots ─────────────────────────────────────────────────


def test_an_unanswerable_slot_never_takes_a_spanning_type() -> None:
    """The writer is handed one fact to perturb.

    An unanswerable comparison has one side and an unanswerable aggregation
    has one number, and neither is the kind of question it was planned to
    be.
    """
    planned = plans(
        wanted=40,
        types={
            QuestionType.COMPARISON: 1,
            QuestionType.AGGREGATION: 1,
            QuestionType.TEMPORAL: 1,
            QuestionType.FACTOID: 1,
        },
        bands={Difficulty.EASY: 1, Difficulty.MEDIUM: 1, Difficulty.HARD: 1},
        unanswerable_share=0.25,
    )

    spanning = [one for one in planned if not one.answerable and one.spec.spans]

    assert [one.spec.name for one in planned if not one.answerable]
    assert spanning == []


def test_the_swap_is_spread_over_the_types_that_do_not_span() -> None:
    """Rather than landing every perturbation on one kind."""
    planned = plans(
        wanted=40,
        types={
            QuestionType.COMPARISON: 4,
            QuestionType.FACTOID: 1,
            QuestionType.ENTITY: 1,
        },
        bands={Difficulty.EASY: 1},
        unanswerable_share=0.25,
    )

    swapped = {one.spec.name for one in planned if not one.answerable}

    assert swapped == {QuestionType.FACTOID, QuestionType.ENTITY}


TODAYS_MIX = {
    QuestionType.FACTOID: 1,
    QuestionType.DEFINITION: 1,
    QuestionType.ENTITY: 0,
    QuestionType.ENUMERATION: 1,
    QuestionType.CONDITION: 1,
    QuestionType.REASON: 1,
    QuestionType.PROCEDURE: 1,
    QuestionType.CONSEQUENCE: 1,
    QuestionType.COMPARISON: 1,
    QuestionType.AGGREGATION: 1,
    QuestionType.TEMPORAL: 0,
    QuestionType.IMPLICATION: 1,
    QuestionType.APPLICATION: 1,
}
TODAYS_BANDS = {Difficulty.EASY: 2, Difficulty.MEDIUM: 3, Difficulty.HARD: 3}


def test_an_unanswerable_slot_takes_only_a_kind_that_asks_for_one_detail() -> None:
    """A set, a condition or a definition is what the material settles."""
    planned = plans(
        wanted=60,
        types={kind: 1 for kind in QuestionType},
        bands={Difficulty.EASY: 1, Difficulty.MEDIUM: 1, Difficulty.HARD: 1},
        unanswerable_share=0.3,
    )

    kinds = {one.spec.name for one in planned if not one.answerable}

    assert kinds == {
        QuestionType.FACTOID,
        QuestionType.ENTITY,
        QuestionType.REASON,
    }


def test_the_unanswerable_slots_alternate_over_the_detail_kinds_of_the_mix() -> None:
    """Entity has weight 0 in this mix, so it never appears."""
    planned = plans(
        wanted=120,
        types=TODAYS_MIX,
        bands=TODAYS_BANDS,
        unanswerable_share=0.30,
    )

    names = [one.spec.name for one in planned if not one.answerable]

    assert Counter(names) == {QuestionType.FACTOID: 18, QuestionType.REASON: 18}
    assert names[:4] == [
        QuestionType.FACTOID,
        QuestionType.REASON,
        QuestionType.FACTOID,
        QuestionType.REASON,
    ]


def test_the_answerable_slots_do_not_move() -> None:
    """Narrowing the unanswerable kinds frees no answerable slot."""
    planned = plans(
        wanted=120,
        types=TODAYS_MIX,
        bands=TODAYS_BANDS,
        unanswerable_share=0.30,
    )

    answerable = [one.spec.name for one in planned if one.answerable]

    assert answerable == [
        name
        for index, name in enumerate(allocate(TODAYS_MIX, 120))
        if not spread(index, 0.30)
    ]


def test_a_mix_with_no_detail_kind_writes_every_slot_answerable() -> None:
    """Writing nothing loses the slot; a set or a condition mostly gets settled."""
    spanning = plans(
        wanted=8,
        types={QuestionType.COMPARISON: 1},
        bands={Difficulty.MEDIUM: 1},
        unanswerable_share=0.25,
    )
    sets = plans(
        wanted=8,
        types={QuestionType.DEFINITION: 1, QuestionType.ENUMERATION: 1},
        bands={Difficulty.EASY: 1},
        unanswerable_share=0.25,
    )

    assert all(one.answerable for one in spanning + sets)
    assert {one.spec.name for one in spanning} == {QuestionType.COMPARISON}


# -- Kinds: every slot is dealt one ----------------------------------------

#: The default mix over 24 slots, as v0.3.19 planned it before slots had a kind.
MAIN_PLAN = [
    ("factoid", "medium", "cross", True),
    ("definition", "hard", "bridge", True),
    ("enumeration", "easy", "single", True),
    ("condition", "medium", "cross", True),
    ("reason", "hard", "bridge", True),
    ("procedure", "easy", "single", True),
    ("consequence", "medium", "cross", True),
    ("comparison", "hard", "bridge", True),
    ("aggregation", "medium", "cross", True),
    ("factoid", "easy", "single", False),
    ("application", "medium", "single", True),
    ("factoid", "medium", "cross", True),
    ("definition", "hard", "bridge", True),
    ("enumeration", "easy", "single", True),
    ("condition", "medium", "cross", True),
    ("reason", "hard", "bridge", True),
    ("procedure", "medium", "cross", True),
    ("consequence", "hard", "bridge", True),
    ("comparison", "medium", "cross", True),
    ("reason", "easy", "single", False),
    ("implication", "hard", "bridge", True),
    ("application", "medium", "single", True),
    ("factoid", "medium", "cross", True),
    ("definition", "hard", "bridge", True),
]


def _default_plan(**kwargs):
    types = {name: 1 for name in SPECS}
    types |= {QuestionType.ENTITY: 0, QuestionType.TEMPORAL: 0}
    return plans(
        wanted=24,
        types=types,
        bands={Difficulty.EASY: 2, Difficulty.MEDIUM: 3, Difficulty.HARD: 3},
        unanswerable_share=0.1,
        **kwargs,
    )


def test_every_slot_carries_a_kind() -> None:
    """A one-passage slot is single, a spanning one needs both, the plan as before."""
    built = _default_plan(kinds={QuestionKind.NEEDS_BOTH: 1})

    assert [(p.spec.name, p.band, p.shape, p.answerable) for p in built] == MAIN_PLAN
    for one in built:
        assert one.kind == (
            QuestionKind.SINGLE if one.shape == Shape.SINGLE else "needs_both"
        )


def test_no_mix_given_deals_every_spanning_slot_needs_both() -> None:
    """The default is today's plan."""
    assert _default_plan() == _default_plan(kinds={QuestionKind.NEEDS_BOTH: 1})


def test_a_kind_mix_spreads_over_the_spanning_slots() -> None:
    """Half and half, interleaved; a type that spans is needs_both whatever the mix."""
    built = plans(
        wanted=16,
        types={QuestionType.FACTOID: 1, QuestionType.COMPARISON: 1},
        bands={Difficulty.MEDIUM: 1},
        unanswerable_share=0.0,
        kinds={QuestionKind.NEEDS_BOTH: 1, QuestionKind.COMPOUND: 1},
    )

    factoids = [one.kind for one in built if one.spec.name == QuestionType.FACTOID]
    assert factoids == ["needs_both", "compound"] * 4
    assert {one.kind for one in built if one.spec.spans} == {"needs_both"}


def test_a_slot_swapped_for_another_type_keeps_its_kind() -> None:
    """Writing a reason slot as another type of question does not change the kind."""
    reason = next(
        one
        for one in plans(
            wanted=12,
            types={QuestionType.REASON: 1, QuestionType.FACTOID: 1},
            bands={Difficulty.MEDIUM: 1},
            unanswerable_share=0.0,
            kinds={QuestionKind.COMPOUND: 1},
        )
        if one.spec.name == QuestionType.REASON
    )

    other = instead(reason, {QuestionType.FACTOID: 1}, 0)

    assert other is not None
    assert (other.spec.name, other.kind) == (QuestionType.FACTOID, "compound")


# -- The kind mix names only kinds that span ---------------------------------


def _loaded(mix: str):
    import os

    from question_generation.config import Settings

    return Settings.load({**os.environ, "QUESTIONS_KIND_MIX": mix})


def test_the_kind_mix_takes_a_kind_that_spans() -> None:
    """needs_both is dealt to a spanning slot."""
    assert _loaded("needs_both:1").kind_mix == {"needs_both": 1}


def test_the_kind_mix_refuses_single_and_unknown_names() -> None:
    """A single slot gets one passage, so the mix cannot deal one to a spanning slot."""
    import pytest

    for bad in ("single:1", "other:1"):
        with pytest.raises(ValueError, match="QUESTIONS_KIND_MIX names"):
            _loaded(bad)


def test_a_compound_slot_is_dealt_the_apart_shape() -> None:
    """A passage sharing least with the head, whatever band the slot came up."""
    built = plans(
        wanted=12,
        types={QuestionType.FACTOID: 1},
        bands={Difficulty.MEDIUM: 1, Difficulty.HARD: 1},
        unanswerable_share=0.0,
        kinds={QuestionKind.NEEDS_BOTH: 1, QuestionKind.COMPOUND: 1},
    )

    compound = [one for one in built if one.kind == "compound"]
    assert compound
    assert {one.shape for one in compound} == {Shape.APART}
    assert Shape.APART not in {one.shape for one in built if one.kind == "needs_both"}
    assert all(one.spans for one in compound)


def test_a_compound_slot_swapped_for_another_type_stays_apart() -> None:
    """`instead` keeps the kind, and the shape the kind is dealt."""
    compound = next(
        one
        for one in plans(
            wanted=12,
            types={QuestionType.REASON: 1, QuestionType.FACTOID: 1},
            bands={Difficulty.MEDIUM: 1},
            unanswerable_share=0.0,
            kinds={QuestionKind.COMPOUND: 1},
        )
        if one.spec.name == QuestionType.REASON
    )

    other = instead(compound, {QuestionType.FACTOID: 1}, 0)

    assert other is not None
    assert (other.kind, other.shape) == ("compound", Shape.APART)


def test_the_kind_mix_default_deals_one_compound_slot_in_six_spanning_slots() -> None:
    """Code default: needs_both 5 to compound 1, so backend.env needs no line."""
    from question_generation.config import Settings

    mix = Settings.__dataclass_fields__["kind_mix"].default_factory()
    built = plans(
        wanted=36,
        types={QuestionType.FACTOID: 1, QuestionType.CONDITION: 1},
        bands={Difficulty.MEDIUM: 1},
        unanswerable_share=0.0,
        kinds=mix,
    )

    assert mix == {"needs_both": 5, "compound": 1}
    assert [one.kind for one in built].count("compound") == 6
