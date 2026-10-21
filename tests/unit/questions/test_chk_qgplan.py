"""Planning and dealing: a slot keeps a band its shape can reach, a deal never offers a copy.

Bank and shop rows, German and English.
"""

from __future__ import annotations

import pytest
from factories import plan, source

from database.qa_generator import QuestionKind, QuestionType
from question_generation.generation import QuestionWriter
from question_generation.kinds import KINDS
from question_generation.models import FactGroup
from question_generation.planning import instead, plans
from question_generation.selection import Deal, Shape

pytestmark = pytest.mark.nlp

_T = {
    "en": {
        "returns": "Goods may be returned within 30 days of receipt.",
        "refund": "A refund is paid within 14 days of the return.",
        "standard": "Standard delivery takes 3 to 5 working days.",
        "express": "Express delivery takes 1 working day.",
        "wrap": "Gift wrapping costs 3 euros.",
        "wrap_near": "Gift wrapping is not offered for standard delivery.",
        "cash": "Withdrawals at cash machines are capped at 500 euros a day.",
        "close": "An account is closed by a signed letter to the branch.",
    },
    "de": {
        "returns": "Waren können innerhalb von 30 Tagen nach Erhalt zurückgegeben werden.",
        "refund": "Eine Erstattung erfolgt innerhalb von 14 Tagen nach der Rückgabe.",
        "standard": "Die Standardlieferung dauert 3 bis 5 Werktage.",
        "express": "Die Expresslieferung dauert 1 Werktag.",
        "wrap": "Die Geschenkverpackung kostet 3 Euro.",
        "wrap_near": "Die Geschenkverpackung wird bei Standardlieferung nicht angeboten.",
        "cash": "Abhebungen am Geldautomaten sind auf 500 Euro am Tag begrenzt.",
        "close": "Ein Konto wird mit einem unterschriebenen Brief an die Filiale gekündigt.",
    },
}


# -- qg-plan-2 / BL-D1: a compound slot keeps a band its kind overrides ------


def test_a_compound_slot_is_planned_at_the_band_its_kind_fixes() -> None:
    """criteria_of bands every compound question medium, so planning one hard is a miss."""
    planned = plans(
        wanted=12,
        types={QuestionType.FACTOID: 1},
        bands={"hard": 1},
        unanswerable_share=0.0,
        kinds={QuestionKind.COMPOUND: 1},
    )
    compound = [one for one in planned if one.kind == QuestionKind.COMPOUND]

    assert compound
    assert {one.band for one in compound} == {KINDS[QuestionKind.COMPOUND].band}


# -- qg-plan-8 / BL-D1: a follow-up is always stored needs_both --------------


class _Stub:
    """A served model answering one follow-up citing both facts."""

    model = "ollama/stub"
    temperature = 0.0

    def answer(self, *, system, user, shape, prompt_version=None):
        return shape(
            question="And for a joint account?", answer="500 euros", facts=[1, 2]
        )


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_follow_up_on_a_compound_pair_is_not_stored_needs_both(language) -> None:
    """The pair was dealt because it shares least; 'needs both' is not what it is."""
    t = _T[language]
    cash = source(
        1, document="terms", passage_id=1, statement=t["cash"], language=language
    )
    close = source(
        2, document="closing", passage_id=2, statement=t["close"], language=language
    )
    root_plan = plan(kind=QuestionKind.COMPOUND, shape=Shape.APART, band="medium")

    written = QuestionWriter(_Stub()).follow_up(
        FactGroup((cash, close)), (("Q?", "A"),), root_plan
    )

    assert len(written.group.resting) == 2
    assert written.kind != QuestionKind.NEEDS_BOTH


# -- qg-plan-7: an APART partner's fact is the one closest to the head --------


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_compound_partner_offers_its_own_first_fact(language) -> None:
    """The passage is chosen for sharing least; its fact should not be re-ranked toward the head."""
    t = _T[language]
    kw = {"language": language}
    head = source(
        1,
        document="a",
        passage_id=1,
        statement=t["standard"],
        lemmas=("delivery",),
        **kw,
    )
    own_first = source(
        3,
        document="b",
        passage_id=2,
        statement=t["wrap"],
        units=("3",),
        lemmas=("gift",),
        **kw,
    )
    near_head = source(
        4, document="b", passage_id=2, statement=t["wrap_near"], lemmas=("gift",), **kw
    )
    deal = Deal([head, own_first, near_head], wanted=2, size=2)

    sample = deal.sample(Shape.APART)

    assert sample is not None
    assert [one.id for one in sample.facts] == [1, 3]


# -- NEW-qg-plan-1: closest() picks a bridge the compound slot then drops -------


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_compound_partner_holding_a_bridge_still_offers_its_own_claim(
    language,
) -> None:
    """The partner was chosen for its unspent claim; a bridge ranked first must not cost it."""
    from factories import bridge, resting

    span = {
        "en": "The return period starts on the day the delivery arrives.",
        "de": "Die Rückgabefrist beginnt am Tag der Lieferung.",
    }[language]
    own = {"en": "Returns are free of charge.", "de": "Rücksendungen sind kostenlos."}[
        language
    ]
    t = _T[language]
    head = source(
        1,
        document="a",
        passage_id=1,
        statement=t["standard"],
        lemmas=("standard", "delivery"),
        language=language,
    )
    spanning = bridge(
        resting(3, document="c", language=language),
        fact_id=2,
        passage_id=2,
        document="b",
        statement=span,
        lemmas=("return", "period"),
        language=language,
    )
    claim = source(
        4,
        document="b",
        passage_id=2,
        statement=own,
        lemmas=("return", "period"),
        language=language,
    )
    deal = Deal([head, spanning, claim], wanted=2, size=2)

    sample = deal.sample(Shape.APART)

    assert sample is not None
    assert [one.id for one in sample.facts] == [1, 4]


# -- NEW-qg-plan-2: a swapped slot keeps a band its shape can reach ------------


def test_a_declined_one_passage_slot_swapped_keeps_a_band_its_shape_can_reach() -> None:
    """An application slot is medium on one passage; a factoid on one passage is easy."""
    declined = plan(QuestionType.APPLICATION, band="medium", shape=Shape.SINGLE)

    other = instead(declined, {QuestionType.APPLICATION: 1, QuestionType.FACTOID: 1}, 0)

    assert other is not None
    assert (other.spec.name, other.shape) == (QuestionType.FACTOID, Shape.SINGLE)
    assert other.band == "easy", other.band
