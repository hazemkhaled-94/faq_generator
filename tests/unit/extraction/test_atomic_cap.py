"""The cap EXTRACTION_MIN_OTHER_SHARE puts on a passage's atomic facts.

A floor on the share of a passage's facts that are not atomic is a cap on
the atomic ones, because a passage yields a fixed number of digests however
much it says. This is the arithmetic of that, and which facts survive it.
"""

from __future__ import annotations

import pytest

from database.qa_generator import FactKind, Rejection
from extraction.config import atomic_cap
from extraction.models import CheckedFact, PassageToExtract
from extraction.service import over_cap
from nlp.models import Sentence


def fact(
    statement: str,
    *,
    kind: str = FactKind.ATOMIC,
    units: tuple[str, ...] = (),
    validated: bool = True,
    method: str = "llm",
) -> CheckedFact:
    """One checked fact, as the cap reads it."""
    return CheckedFact(
        statement=statement,
        evidence_text=statement,
        extraction_method=method,
        validated=validated,
        rejection_code=None if validated else Rejection.ASSERTS_NOTHING,
        validation_error=None if validated else "nothing",
        kind=kind,
        units_statement=list(units),
    )


# ── What the floor works out to ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("share", "expected"),
    [
        # Two digests beside n atomic facts is a share of 2/(n+2), so the
        # largest n holding the others at `share` is 2(1-share)/share.
        (0.10, 18),
        (0.20, 8),
        (0.25, 6),
        (0.33, 4),
        # 2 * 0.6 / 0.4 is 2.9999999999999996 in floating point.
        (0.40, 3),
        (0.50, 2),
    ],
)
def test_the_floor_becomes_a_cap_on_the_atomic_facts(share, expected) -> None:
    """The one number that decides how much of a passage becomes facts."""
    assert atomic_cap(2, share) == expected


def test_the_measured_share_of_one_corpus_reproduces_its_own_figure() -> None:
    """Two digests beside 18 atomic facts are a tenth of everything."""
    assert atomic_cap(2, 0.10) == 18


@pytest.mark.parametrize("share", [0.0, 1.0, -1.0, 2.0])
def test_a_share_that_is_not_a_share_caps_nothing(share) -> None:
    """Rather than refusing every fact, or none of them, quietly."""
    assert atomic_cap(2, share) is None


def test_a_deployment_writing_no_digests_caps_nothing() -> None:
    """There is no other kind for a share of the facts to be."""
    assert atomic_cap(0, 0.33) is None


def test_the_cap_is_never_below_one() -> None:
    """A passage read for nothing is a passage not worth the call."""
    assert atomic_cap(2, 0.99) == 1


# ── What one passage has room for ──────────────────────────────────────────

#: A lead-in and eight list items, as the chunker renders a list.
LISTED = (
    "A customer is charged a fee for:\n"
    "- a card replacement\n"
    "- a cash withdrawal abroad\n"
    "* a paper statement\n"
    "* a returned direct debit\n"
    "1. a standing order change\n"
    "2. an urgent transfer\n"
    "3) a balance confirmation\n"
    "4) an account closure"
)


def _passage(text: str, claims: int) -> PassageToExtract:
    """A passage carrying `claims` sentences with a finite verb."""
    return PassageToExtract(
        id=1,
        text=text,
        section_path=None,
        block_type="text",
        language="en",
        sentences=[
            Sentence(index=at, text=text, start=0, end=len(text), predicates=1)
            for at in range(claims)
        ],
    )


def test_a_list_passage_has_room_for_every_item() -> None:
    """The cap is never below the passage's sentences and list items."""
    listed = _passage(LISTED, claims=1)

    assert listed.items == 8
    assert listed.room(4) == 9


def test_a_short_prose_passage_keeps_the_share_based_cap() -> None:
    """Room for its two claims is within the cap the share works out to."""
    prose = _passage("The card is blocked. A new one is sent.", claims=2)

    assert prose.items == 0
    assert prose.room(4) == 4


def test_a_sentence_with_no_verb_has_room_too() -> None:
    """`Minimum amount: 10 EUR.` states a value, so every sentence counts."""
    stated = PassageToExtract(
        id=1,
        text="Minimum amount: 10 EUR. Maximum amount: 500 EUR. A fee is charged.",
        section_path=None,
        block_type="text",
        language="en",
        sentences=[
            Sentence(
                index=0, text="Minimum amount: 10 EUR.", start=0, end=23, predicates=0
            ),
            Sentence(
                index=1, text="Maximum amount: 500 EUR.", start=24, end=48, predicates=0
            ),
            Sentence(index=2, text="A fee is charged.", start=49, end=66, predicates=1),
        ],
    )

    assert stated.room(1) == 3


def test_no_cap_is_no_cap_however_long_the_passage() -> None:
    """None is EXTRACTION_MIN_OTHER_SHARE turning the cap off."""
    assert _passage(LISTED, claims=1).room(None) is None


def test_a_number_inside_a_line_is_not_a_list_item() -> None:
    """Only a bullet or a number opening a line, then a space, marks one."""
    prose = _passage("The fee is 2. 5 EUR are charged.\n-5 is no bullet.", claims=2)

    assert prose.items == 0


def test_the_service_keeps_a_fact_per_item_of_a_long_list() -> None:
    """Eight items under a cap of four are eight facts, none over the cap."""
    from drivers import Extraction, passage

    items = LISTED.splitlines()[1:]
    facts = {
        "facts": [
            {
                "sentences": [0],
                "statement": f"A customer is charged a fee for {one.split(' ', 1)[1]}.",
            }
            for one in items
        ]
    }
    run = Extraction(passage(LISTED), facts=facts, atomic_cap=4)
    run.next()

    refused = [
        one.statement
        for one in run.queue.stored[1]
        if one.rejection_code == Rejection.OVER_CAP
    ]
    assert not refused, refused


# ── Which facts it refuses ─────────────────────────────────────────────────


def test_nothing_is_refused_under_the_cap() -> None:
    """A passage that yielded few facts is left alone."""
    facts = [fact("One."), fact("Two.")]

    assert over_cap(facts, 4) == set()


def test_no_cap_refuses_nothing() -> None:
    """None is how EXTRACTION_MIN_OTHER_SHARE turns the whole thing off."""
    assert over_cap([fact(f"{n}.") for n in range(20)], None) == set()


def test_the_facts_asserting_a_value_are_the_ones_kept() -> None:
    """A fact carrying a number is what a checkable question is written from.

    The same rule question generation offers facts by, so the cap keeps what
    the writer would have reached for anyway.
    """
    facts = [
        fact("Boilerplate one."),
        fact("The device weighs 4 kg.", units=("4",)),
        fact("Boilerplate two."),
        fact("It ships in March 2026.", units=("2026",)),
    ]

    # Positions 0 and 2 carry no unit, so they are the two that go.
    assert over_cap(facts, 2) == {0, 2}


def test_ties_go_to_the_order_the_model_wrote_them_in() -> None:
    """So one passage read twice keeps the same facts."""
    facts = [fact(f"Claim {n}.") for n in range(5)]

    assert over_cap(facts, 2) == {2, 3, 4}


def test_only_the_atomic_facts_compete_for_the_budget() -> None:
    """A summary is what the floor exists to make room for."""
    facts = [
        fact("A summary.", kind=FactKind.SUMMARY),
        fact("- An outline", kind=FactKind.OUTLINE),
        fact("One."),
        fact("Two."),
        fact("Three."),
    ]

    # Only positions 2, 3 and 4 are atomic, so a cap of 2 takes one of them
    # and never touches the digests.
    assert over_cap(facts, 2) == {4}


def test_a_statement_composed_from_a_grid_does_not_compete() -> None:
    """The cap leaves room for the digests, and a table yields none.

    A table's rendered rows carry no finite verb, so `_DIGESTIBLE` is never
    met and there is no other kind for the share to be. Applying the cap
    there is arithmetic about a quantity that is zero - it kept four cells
    of a sixty-cell grid, chosen by position in the table.
    """
    cells = [
        fact(f"Device - Mass: {n} kg", units=(str(n),), method="deterministic")
        for n in range(60)
    ]

    assert over_cap(cells, 4) == set()


def test_the_model_s_own_facts_are_still_capped_beside_a_grid() -> None:
    """A passage merging a table with prose is read by both readers."""
    facts = [
        *(fact(f"Device - Mass: {n} kg", method="deterministic") for n in range(3)),
        *(fact(f"Claim {n}.") for n in range(5)),
    ]

    # Only positions 3 to 7 compete, so a cap of 2 refuses the last three.
    assert over_cap(facts, 2) == {5, 6, 7}


def test_a_fact_a_check_already_refused_is_not_refused_again() -> None:
    """It is not taking a place from anything, and its code says why it went.

    Overwriting it with `over_cap` would lose the real reason.
    """
    facts = [
        fact("Refused already.", validated=False),
        fact("One."),
        fact("Two."),
        fact("Three."),
    ]

    refused = over_cap(facts, 2)

    assert 0 not in refused
    assert refused == {3}


# ── The floor under what is worth digesting ────────────────────────────────


def test_a_passage_too_short_to_condense_is_not_digested() -> None:
    """A digest is a fixed size, so how much it condenses is the passage's.

    The prompt asks for two or three sentences whatever it is given.
    """
    from extraction.service import ExtractionService

    service = ExtractionService(
        repository=None,  # type: ignore[arg-type]
        extractors=None,  # type: ignore[arg-type]
        checker=None,  # type: ignore[arg-type]
        digest=object(),  # type: ignore[arg-type]
        digest_min_chars=800,
    )
    short = PassageToExtract(
        id=1,
        text="A short passage. It says two things.",
        section_path=None,
        block_type="text",
        language="en",
        sentences=[
            Sentence(index=0, text="A short passage.", start=0, end=16, predicates=1),
            Sentence(
                index=1, text="It says two things.", start=17, end=36, predicates=1
            ),
        ],
    )

    assert service._digested(short) == []


def test_a_passage_long_enough_is_still_digested() -> None:
    """The floor is a floor, not a way of turning digests off."""
    from extraction.service import ExtractionService

    class Digest:
        method = "llm"
        provenance = None

        def extract(self, passage):
            return ["a digest"]

    class Checker:
        def check(self, passage, candidate, method, provenance=None):
            return candidate

    service = ExtractionService(
        repository=None,  # type: ignore[arg-type]
        extractors=None,  # type: ignore[arg-type]
        checker=Checker(),  # type: ignore[arg-type]
        digest=Digest(),  # type: ignore[arg-type]
        digest_min_chars=10,
    )
    long = PassageToExtract(
        id=1,
        text="x" * 200,
        section_path=None,
        block_type="text",
        language="en",
        sentences=[
            Sentence(index=0, text="one", start=0, end=3, predicates=1),
            Sentence(index=1, text="two", start=4, end=7, predicates=1),
        ],
    )

    assert service._digested(long) == ["a digest"]
