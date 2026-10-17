"""Judging every stored fact again without calling the model.

This is what applies a change to the checks to facts extracted before it.
What the model wrote is the record of one extraction and is kept; what the
checks read off it is derived, and is replaced.
"""

from __future__ import annotations

import pytest
from drivers import DIGEST_SHARE, Catalogue, Kept, group, passage

from database.qa_generator import FactKind, Rejection
from extraction.models import CandidateFact, Cited, Refused
from extraction.service import _REJUDGE_BATCH, revalidate
from extraction.validation import FactChecker

pytestmark = pytest.mark.nlp


def stored(fact_id: int, statement: str, cited=(0,), kind=FactKind.ATOMIC):
    """One stored fact, as the catalogue hands it back."""
    return (
        fact_id,
        [passage()],
        CandidateFact(statement, cited, kind=kind),
        "llm",
    )


def test_nothing_stored_is_nothing_to_judge() -> None:
    """An empty corpus writes no batch at all."""
    catalog = Catalogue()

    assert revalidate(catalog, FactChecker(DIGEST_SHARE)) == 0  # type: ignore[arg-type]
    assert catalog.verdicts == []


def test_every_stored_fact_comes_back_judged() -> None:
    """One verdict per fact, keyed by the id it was read under."""
    catalog = Catalogue().holding(
        stored(1, "The device weighs 4 kg."),
        stored(2, "The device weighs 7 kg."),
    )

    assert revalidate(catalog, FactChecker(DIGEST_SHARE)) == 2  # type: ignore[arg-type]
    assert [fact_id for fact_id, _ in catalog.verdicts] == [1, 2]


def test_the_verdict_is_what_today_checks_read() -> None:
    """A fact that passes and one that does not, both re-read."""
    catalog = Catalogue().holding(
        stored(1, "The device weighs 4 kg."),
        stored(2, "The device weighs 7 kg."),
    )
    revalidate(catalog, FactChecker(DIGEST_SHARE))  # type: ignore[arg-type]

    passed, refused = (checked for _, checked in catalog.verdicts)
    assert passed.validated, passed.validation_error
    assert refused.rejection_code == Rejection.UNSUPPORTED_ADDITION


def test_a_bridge_is_judged_against_its_whole_group() -> None:
    """Its passages come back from the link table, not from its anchor."""
    offered = group(
        "Standard requests are answered within 48 hours.",
        "Urgent requests are answered within 4 hours.",
    )
    catalog = Catalogue().holding(
        (
            7,
            offered,
            CandidateFact(
                "Support response times are stated separately for both kinds.",
                (),
                kind=FactKind.BRIDGE,
                passages=(
                    Cited(position=0, sentences=(0,)),
                    Cited(position=1, sentences=(0,)),
                ),
            ),
            "llm",
        )
    )
    revalidate(catalog, FactChecker(DIGEST_SHARE))  # type: ignore[arg-type]

    ((_, checked),) = catalog.verdicts
    assert checked.kind == FactKind.BRIDGE
    assert [one.passage_id for one in checked.citations] == [one.id for one in offered]
    assert checked.validated, checked.validation_error


def test_a_fact_citing_a_second_passage_keeps_that_passage_evidence() -> None:
    """A refused duplicate's citation was added to it with its evidence."""
    offered = group(
        "The device weighs 4 kg. It ships in one box.",
        "The device weighs 4 kg. That is the compact model.",
        "Its mass is 4 kg, as stated above.",
    )
    catalog = Catalogue().holding(
        (
            7,
            offered,
            CandidateFact(
                "The device weighs 4 kg.",
                (0,),
                passages=(
                    Cited(position=0, sentences=(0,)),
                    Cited(position=1, sentences=(0,)),
                    Cited(position=2, sentences=(0,)),
                ),
            ),
            "llm",
        )
    )
    revalidate(catalog, FactChecker(DIGEST_SHARE))  # type: ignore[arg-type]

    ((_, checked),) = catalog.verdicts
    assert checked.validated, checked.validation_error
    assert checked.evidence_text == (
        "The device weighs 4 kg.\nIts mass is 4 kg, as stated above."
    )


def test_a_bridge_left_with_one_passage_is_refused_on_the_second_reading() -> None:
    """Re-chunking took the other side away."""
    offered = group("Standard requests are answered within 48 hours.")
    catalog = Catalogue().holding(
        (
            7,
            offered,
            CandidateFact(
                "Support response times are stated separately for both kinds.",
                (),
                kind=FactKind.BRIDGE,
                passages=(Cited(position=0, sentences=(0,)),),
            ),
            "llm",
        )
    )
    revalidate(catalog, FactChecker(DIGEST_SHARE))  # type: ignore[arg-type]

    ((_, checked),) = catalog.verdicts
    assert checked.rejection_code == Rejection.NOT_BRIDGING


def test_the_verdicts_are_written_in_batches() -> None:
    """A corpus of facts is not held whole in memory to write it back."""
    catalog = Catalogue().holding(
        *(stored(at, "The device weighs 4 kg.") for at in range(_REJUDGE_BATCH + 3))
    )

    assert revalidate(catalog, FactChecker(DIGEST_SHARE)) == _REJUDGE_BATCH + 3  # type: ignore[arg-type]
    assert [len(batch) for batch in catalog.rejudged] == [_REJUDGE_BATCH, 3]


def test_a_narrowing_reaches_the_read() -> None:
    """`--only` re-judges one document rather than the corpus."""
    catalog = Catalogue()
    revalidate(catalog, FactChecker(DIGEST_SHARE), "a-condition")  # type: ignore[arg-type]

    assert catalog.narrowed == ["a-condition"]


def test_a_fact_whose_citation_resolved_nothing_is_left_alone() -> None:
    """Re-judging it would overwrite the only record of what it cited.

    The numbers survive nowhere but its own message: the link rows carry
    NULL, which is what says they resolved to nothing.
    """
    catalog = Catalogue().holding(stored(1, "Anything.", cited=()))

    assert revalidate(catalog, FactChecker(DIGEST_SHARE)) == 0  # type: ignore[arg-type]
    assert catalog.verdicts == []


def test_the_share_that_judges_a_digest_is_the_caller_s() -> None:
    """Not the process environment's.

    A deployment changing EXTRACTION_DIGEST_MAX_SHARE through /settings
    stores the value rather than exporting it, so a checker built in here
    would judge against the file while the fact was stamped with the stored
    configuration's version.
    """
    digest = CandidateFact(
        "The device weighs 4 kg. It arrives in March 2026.",
        (0, 1),
        kind=FactKind.SUMMARY,
    )
    holding = (7, [passage()], digest, "llm")

    generous = Catalogue().holding(holding)
    strict = Catalogue().holding(holding)
    revalidate(generous, FactChecker(0.9))  # type: ignore[arg-type]
    revalidate(strict, FactChecker(0.2))  # type: ignore[arg-type]

    assert generous.verdicts[0][1].validated
    assert strict.verdicts[0][1].rejection_code == Rejection.NOT_CONDENSED


#: The bar the dedup gate refuses at.
BAR = 0.985

#: The vector every stored fact here lies along, so any two are twins.
ALONG = [1.0, 0.0]


def refused(fact_id: int, statement: str, passage_id: int) -> Refused:
    """One stored refusal the checks may now validate, carrying its vector."""
    return Refused(
        fact_id=fact_id,
        passage_id=passage_id,
        language="en",
        kind=FactKind.ATOMIC,
        statement=statement,
        embedding=ALONG,
    )


def _passages(condition) -> tuple[str, list]:
    """A narrowing as Postgres is asked it, and the values bound into it."""
    from sqlalchemy.dialects import postgresql

    compiled = condition.compile(dialect=postgresql.dialect())
    return str(compiled), list(compiled.params.values())


def test_two_refused_twins_validated_together_leave_one_a_duplicate() -> None:
    """The facts a pass validates are probed in id order, each against the ones before.

    Neither faced the dedup gate when it was read: a fact a check refused
    is not probed. Validated now, the first is the second's twin.
    """
    catalog = (
        Catalogue()
        .holding(
            stored(1, "The device weighs 4 kg."), stored(2, "The device weighs 4 kg.")
        )
        .refusing(
            refused(1, "The device weighs 4 kg.", passage_id=1),
            refused(2, "The device weighs 4 kg.", passage_id=2),
        )
    )

    revalidate(catalog, FactChecker(DIGEST_SHARE), threshold=BAR)  # type: ignore[arg-type]

    verdicts = dict(catalog.verdicts)
    assert verdicts[1].validated, verdicts[1].validation_error
    assert verdicts[2].rejection_code == Rejection.DUPLICATE
    assert "fact 1" in (verdicts[2].validation_error or "")


def test_a_fact_revalidated_into_a_twin_is_refused_as_duplicate() -> None:
    """A twin the corpus already holds refuses it, as it would have in flight."""
    catalog = (
        Catalogue()
        .holding(stored(2, "The device weighs 4 kg."))
        .holding_kept(Kept(1, 1, "The device weighs 4 kg.", ALONG))
        .refusing(refused(2, "The device weighs 4 kg.", passage_id=2))
    )

    revalidate(catalog, FactChecker(DIGEST_SHARE), threshold=BAR)  # type: ignore[arg-type]

    ((_, checked),) = catalog.verdicts
    assert checked.rejection_code == Rejection.DUPLICATE


def test_a_fact_that_stays_validated_is_not_probed_again() -> None:
    """It passed the gate when it was read; only a refusal validated now missed it."""
    catalog = (
        Catalogue()
        .holding(stored(2, "The device weighs 4 kg."))
        .holding_kept(Kept(1, 1, "The device weighs 4 kg.", ALONG))
    )

    revalidate(catalog, FactChecker(DIGEST_SHARE), threshold=BAR)  # type: ignore[arg-type]

    ((_, checked),) = catalog.verdicts
    assert checked.validated, checked.validation_error


def test_revalidate_recaps_the_passages_it_flipped() -> None:
    """A refusal validated now was never counted against the cap; those passages are."""
    catalog = (
        Catalogue()
        .holding(
            stored(1, "The device weighs 4 kg."), stored(2, "The device weighs 7 kg.")
        )
        .refusing(
            refused(1, "The device weighs 4 kg.", passage_id=5),
            refused(2, "The device weighs 7 kg.", passage_id=6),
        )
    )

    revalidate(catalog, FactChecker(DIGEST_SHARE), cap=4)  # type: ignore[arg-type]

    assert [(cap, _passages(within)) for cap, within in catalog.recapped] == [
        (4, ("passages.id = ANY (%(moved)s::BIGINT[])", [[5]]))
    ]


def test_a_pass_validating_no_refusal_recaps_nothing() -> None:
    """No fact moved into the cap's count, so no passage is re-capped."""
    catalog = Catalogue().holding(stored(1, "The device weighs 4 kg."))

    revalidate(catalog, FactChecker(DIGEST_SHARE), cap=4)  # type: ignore[arg-type]

    assert catalog.recapped == []
