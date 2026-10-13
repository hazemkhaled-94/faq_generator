"""Re-deciding every stored duplicate refusal without calling the model.

This is what carries a change to the dedup gate to facts extracted before it.
A refusal that today's rule would not make is given back as it was judged
when extracted; one it would still make stays. The citations an earlier
refusal folded into its twin are taken out first.
"""

from __future__ import annotations

import math

import pytest
from drivers import Catalogue, Kept

from database.qa_generator import FactKind
from extraction.models import Refused
from extraction.service import dedup

pytestmark = pytest.mark.nlp

#: The bar the replay re-decides at.
BAR = 0.985


def at(similarity: float) -> list[float]:
    """A unit vector sitting at this cosine from `ALONG`."""
    return [similarity, math.sqrt(1 - similarity**2)]


#: The direction every stored fact here is measured from.
ALONG = [1.0, 0.0]


def refusal(
    statement: str,
    *,
    fact_id: int = 10,
    passage_id: int = 2,
    language: str = "en",
    kind: str = FactKind.ATOMIC,
) -> Refused:
    """One stored refusal, lying along `ALONG`."""
    return Refused(
        fact_id=fact_id,
        passage_id=passage_id,
        language=language,
        kind=kind,
        statement=statement,
        embedding=ALONG,
    )


def test_a_refusal_still_a_twin_stays_refused() -> None:
    """The same claim at the bar is still the stored fact's duplicate."""
    catalog = (
        Catalogue()
        .holding_kept(Kept(1, 1, "The device weighs 4 kg.", at(0.99)))
        .refusing(refusal("The device has a weight of 4 kg."))
    )

    assert dedup(catalog, BAR) == 0  # type: ignore[arg-type]
    assert catalog.given_back == []


@pytest.mark.parametrize(
    ("twin", "why"),
    [
        (Kept(1, 1, "The device weighs 7 kg.", at(0.99)), "another number"),
        (Kept(1, 1, "The device weighs 4 kg.", at(0.97)), "below the bar"),
        (Kept(1, 1, "Das Gerät wiegt 4 kg.", at(0.99), language="de"), "language"),
        (
            Kept(1, 1, "The device weighs 4 kg.", at(0.99), kind=FactKind.SUMMARY),
            "another kind elsewhere",
        ),
    ],
)
def test_a_refusal_today_s_rule_would_not_make_is_given_back(twin, why) -> None:
    """Numbers, the bar, the language and the kind are all read again."""
    catalog = (
        Catalogue().holding_kept(twin).refusing(refusal("The device weighs 4 kg."))
    )

    assert dedup(catalog, BAR) == 1, why  # type: ignore[arg-type]
    assert catalog.given_back == [10]


def test_a_refusal_given_back_is_a_twin_for_the_next() -> None:
    """Two refusals of one claim against the wrong fact keep one copy, not two."""
    catalog = (
        Catalogue()
        .holding_kept(Kept(1, 1, "The device weighs 7 kg.", at(0.99)))
        .refusing(
            refusal("The device weighs 4 kg.", fact_id=10, passage_id=2),
            refusal("The device weighs 4 kg.", fact_id=11, passage_id=3),
        )
    )

    assert dedup(catalog, BAR) == 1  # type: ignore[arg-type]
    assert catalog.given_back == [10]


def test_a_refusal_is_read_against_its_own_passage_too() -> None:
    """What the passage kept is the other probe, as it is in flight."""
    catalog = (
        Catalogue()
        .holding_kept(
            Kept(1, 2, "The device weighs 4 kg.", at(0.99), kind=FactKind.SUMMARY)
        )
        .refusing(refusal("The device weighs 4 kg.", passage_id=2))
    )

    assert dedup(catalog, BAR) == 0  # type: ignore[arg-type]


def test_a_sibling_claim_of_its_own_passage_is_given_back() -> None:
    """Two atomic facts of one passage are never duplicates."""
    catalog = (
        Catalogue()
        .holding_kept(Kept(1, 2, "The device weighs 4 kg.", at(0.99)))
        .refusing(refusal("The device weighs 4 kg.", passage_id=2))
    )

    assert dedup(catalog, BAR) == 1  # type: ignore[arg-type]


def test_a_refusal_given_back_carries_the_reading_against_today_s_bar() -> None:
    """As a fact read in flight would: its nearest twin, against this bar."""
    catalog = (
        Catalogue()
        .holding_kept(Kept(1, 1, "The device weighs 4 kg.", at(0.97)))
        .refusing(refusal("The device has a weight of 4 kg."))
    )

    dedup(catalog, BAR, floor=0.75)  # type: ignore[arg-type]

    ((reading,), margin) = catalog.readings[10]
    assert (reading["gate"], reading["value"], reading["threshold"]) == (
        "duplicate",
        0.97,
        BAR,
    )
    assert margin == round((BAR - 0.97) / (BAR - 0.75), 4)


def test_a_refusal_with_no_twin_left_carries_no_reading() -> None:
    """The refusal's own margin is not a validated fact's; nothing replaces it."""
    catalog = (
        Catalogue()
        .holding_kept(Kept(1, 1, "The device weighs 7 kg.", at(0.99)))
        .refusing(refusal("The device weighs 4 kg."))
    )

    dedup(catalog, BAR, floor=0.75)  # type: ignore[arg-type]

    assert catalog.readings[10] == (None, None)


def test_the_gate_off_gives_every_refusal_back() -> None:
    """EXTRACTION_DUPLICATE_COSINE at 0 refuses nothing, in flight or here."""
    catalog = (
        Catalogue()
        .holding_kept(Kept(1, 1, "The device weighs 4 kg.", at(1.0)))
        .refusing(refusal("The device weighs 4 kg."))
    )

    assert dedup(catalog, 0.0) == 1  # type: ignore[arg-type]


def test_the_folds_are_taken_out_first_and_narrowed_alike() -> None:
    """Every fold goes before any refusal moves, under the same narrowing."""
    catalog = Catalogue().refusing(refusal("The device weighs 4 kg."))
    within = object()

    dedup(catalog, BAR, within)  # type: ignore[arg-type]

    assert catalog.unfolded == 1
    assert catalog.narrowed == [within, within]


def test_facts_whose_own_citation_is_gone_are_warned_about(caplog) -> None:
    """They keep their folds, and a pass that quietly left some cannot be read."""
    catalog = Catalogue()
    catalog.folds = (3, 2)

    dedup(catalog, BAR)  # type: ignore[arg-type]

    assert "2 fact(s)" in caplog.text
