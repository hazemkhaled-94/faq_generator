"""An answer that is empty is never checked against the passages as if it were one.

A derived question (a total, an implication) with no answer has nothing for
the passages to support, so it is refused as not recoverable rather than
put to a model; and the entailment pass that may rescue a recall failure
never rescues an empty answer, so no verifier is asked to back nothing.
"""

from __future__ import annotations

import pytest
from factories import candidate

from database.qa_generator import QuestionRejection, QuestionType
from question_generation.checker import QuestionChecker

pytestmark = pytest.mark.nlp


class Unasked:
    """A verifier the empty answer must never reach."""

    def __getattr__(self, name: str):
        """Fails any judgement asked of it."""
        raise AssertionError(f"the verifier was asked {name} about an empty answer")


def build() -> QuestionChecker:
    """A checker with entailment on and a verifier that must not be asked."""
    return QuestionChecker(
        embedder=None,
        verifier=Unasked(),
        nearest=lambda embedding, **_: None,
        threshold=0.93,
        bounds={"value": (1, 80), "list": (3, 300), "explanation": (20, 600)},
        phrasing=None,
        entail=True,
    )


@pytest.mark.parametrize("kind", [QuestionType.AGGREGATION, QuestionType.IMPLICATION])
def test_a_derived_question_with_no_answer_is_not_recoverable(kind) -> None:
    """Refused before any model is asked."""
    asked = candidate(
        question_text="How many cards does the account include in total?",
        target_answer="",
        question_type=kind,
    )

    failed = build()._computable(asked, "")

    assert failed is not None and failed[0] == QuestionRejection.NOT_RECOVERABLE


def test_the_entailment_pass_never_rescues_an_empty_answer() -> None:
    """Nothing is backed, and nothing is measured for it."""
    readings: list = []

    assert build()._backed(candidate(target_answer=""), "", readings) is False
    assert readings == []
