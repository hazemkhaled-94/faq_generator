"""The verdicts a re-check reaches on stored questions, pinned as a table.

Rows docs/bugs.md quotes, each beside the code re-verify has to store for it,
and one sound row. A rule added to the checker's type gates that re-verify
does not run leaves the stored release as it was.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from database.qa_generator import AnswerForm, QuestionRejection, QuestionType
from question_generation.config import Settings
from question_generation.models import JudgedQuestion, Neighbour
from question_generation.service import _recheck

pytestmark = pytest.mark.nlp

#: (name, question, answer, type, form, expected code or None).
ROWS: tuple[tuple[str, str, str, str, str, str | None], ...] = (
    (
        "a comparison answered with two definitions",
        "How does algorithmic bias differ from area under curve (AUC)?",
        (
            "a type of bias caused by the ML algorithm, a measure of how well "
            "a classifier can distinguish between two classes"
        ),
        QuestionType.COMPARISON,
        AnswerForm.LIST,
        QuestionRejection.WRONG_TYPE,
    ),
    (
        "a why question typed as a procedure",
        "Why does the release draw whole threads?",
        "because a follow-up reads only after the turn it follows",
        QuestionType.PROCEDURE,
        AnswerForm.EXPLANATION,
        QuestionRejection.WRONG_TYPE,
    ),
    (
        "an answer that restates its question",
        (
            "Why can accurate test metrics be hard to determine for "
            "exploratory testing sessions?"
        ),
        (
            "accurate test metrics for exploratory testing sessions can be "
            "challenging to determine"
        ),
        QuestionType.REASON,
        AnswerForm.EXPLANATION,
        QuestionRejection.RESTATES_QUESTION,
    ),
    (
        "a sound reason",
        "Why does a request have to be confirmed in writing?",
        "so that the agreed response time can be evidenced later",
        QuestionType.REASON,
        AnswerForm.EXPLANATION,
        None,
    ),
)


@pytest.mark.parametrize(
    ("question", "answer", "kind", "form", "expected"),
    [row[1:] for row in ROWS],
    ids=[row[0] for row in ROWS],
)
def test_a_stored_question_is_rechecked_against_the_type_rules(
    question: str, answer: str, kind: str, form: str, expected: str | None
) -> None:
    """What re-verify stores for a row the checker would refuse today."""
    failed = _recheck(None, Settings.load(), _stored(question, answer, kind, form))  # type: ignore[arg-type]

    assert (failed[0] if failed else None) == expected, failed


class _Nearest:
    """A catalogue whose nearest accepted question is one fixed twin."""

    def __init__(self, twin: Neighbour) -> None:
        self._twin = twin

    def nearest(self, embedding, before=None, excluding=()):
        return self._twin


def test_a_twin_asking_another_thing_is_not_a_duplicate_on_re_check() -> None:
    """The `asks_the_same` veto the checker applies, applied again."""
    stored = replace(
        _stored(
            "Why does a request have to be confirmed in writing?",
            "so that the agreed response time can be evidenced later",
            QuestionType.REASON,
            AnswerForm.EXPLANATION,
        ),
        embedding=[1.0],
    )
    twin = Neighbour(
        "Which requests have to be confirmed in writing?", True, similarity=0.95
    )

    assert _recheck(_Nearest(twin), Settings.load(), stored) is None  # type: ignore[arg-type]


def _stored(question: str, answer: str, kind: str, form: str) -> JudgedQuestion:
    """One accepted, answerable English question resting on one fact."""
    return JudgedQuestion(
        id=1,
        question_text=question,
        target_answer=answer,
        answerable=True,
        difficulty="easy",
        passage_scope=None,
        document_scope=None,
        topic_scope=None,
        language="en",
        status="accepted",
        embedding=None,
        statements=("A request is answered within 48 hours.",),
        facts_validated=True,
        documents=1,
        passages=1,
        topics=1,
        follows_id=None,
        question_type=kind,
        answer_form=form,
    )


def test_a_refit_moving_the_topics_is_not_a_changed_source() -> None:
    """A refit rewrites the dominant topics under a stored question."""
    stored = replace(
        _stored(
            "Why does a request have to be confirmed in writing?",
            "so that the agreed response time can be evidenced later",
            QuestionType.REASON,
            AnswerForm.EXPLANATION,
        ),
        topic_scope="single_topic",
        topics=2,
    )

    assert _recheck(None, Settings.load(), stored) is None  # type: ignore[arg-type]
