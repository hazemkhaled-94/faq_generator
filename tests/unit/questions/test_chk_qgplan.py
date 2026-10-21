"""Planning and dealing: a slot keeps a band its shape can reach, a deal never offers a copy.

Bank and shop rows, German and English.
"""

from __future__ import annotations

import pytest
from factories import plan

from database.qa_generator import QuestionKind, QuestionType
from question_generation.kinds import KINDS
from question_generation.planning import instead, plans
from question_generation.selection import Shape

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


# -- NEW-qg-plan-2: a swapped slot keeps a band its shape can reach ------------


def test_a_declined_one_passage_slot_swapped_keeps_a_band_its_shape_can_reach() -> None:
    """An application slot is medium on one passage; a factoid on one passage is easy."""
    declined = plan(QuestionType.APPLICATION, band="medium", shape=Shape.SINGLE)

    other = instead(declined, {QuestionType.APPLICATION: 1, QuestionType.FACTOID: 1}, 0)

    assert other is not None
    assert (other.spec.name, other.shape) == (QuestionType.FACTOID, Shape.SINGLE)
    assert other.band == "easy", other.band
