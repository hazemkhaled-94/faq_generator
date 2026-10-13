"""What a re-check does with a question a person accepted.

No rule gate overrules a person: a question a person accepted is rejected on
re-check only when the facts it rests on no longer hold.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from database.qa_generator import QuestionRejection, ReviewVerdict
from question_generation.config import Settings
from question_generation.models import JudgedQuestion, Neighbour
from question_generation.service import _recheck, reverify


class _Twin:
    """A catalogue whose nearest accepted question is the same question."""

    def nearest(self, embedding, before=None, excluding=(), language=None):
        return Neighbour("What does the device weigh?", True, similarity=1.0)


def _stored(**columns) -> JudgedQuestion:
    """One accepted, answerable English question resting on one fact."""
    return JudgedQuestion(
        **{
            "id": 2,
            "question_text": "What does the device weigh?",
            "target_answer": "4 kg",
            "answerable": True,
            "difficulty": "easy",
            "passage_scope": None,
            "document_scope": None,
            "topic_scope": None,
            "language": "en",
            "status": "accepted",
            "embedding": None,
            "statements": ("The device weighs 4 kg.",),
            "facts_validated": True,
            "documents": 1,
            "passages": 1,
            "topics": 1,
            "follows_id": None,
            **columns,
        }
    )


#: (name, columns, catalogue, the code a rule gate stores when nobody looked).
REFUSED = (
    (
        "malformed",
        {"question_text": "What does the device weigh"},
        None,
        QuestionRejection.MALFORMED,
    ),
    (
        "scope moved",
        {"passage_scope": "multi_passage"},
        None,
        QuestionRejection.SOURCE_CHANGED,
    ),
    (
        "duplicate",
        {"embedding": [1.0]},
        _Twin(),
        QuestionRejection.DUPLICATE,
    ),
)


@pytest.mark.parametrize(
    ("columns", "catalog"),
    [row[1:3] for row in REFUSED],
    ids=[row[0] for row in REFUSED],
)
def test_no_rule_gate_rejects_a_question_a_person_accepted(columns, catalog) -> None:
    """Malformed, a moved scope and a near twin all leave it standing."""
    stored = _stored(reviewed_verdict=ReviewVerdict.ACCEPTED, **columns)

    assert _recheck(catalog, Settings.load(), stored) is None


@pytest.mark.parametrize(
    ("columns", "expected"),
    [(row[1], row[3]) for row in REFUSED[:2]],
    ids=[row[0] for row in REFUSED[:2]],
)
def test_a_rule_gate_still_rejects_a_question_nobody_reviewed(
    columns, expected
) -> None:
    """The same rows, unreviewed, are rejected as before."""
    failed = _recheck(None, Settings.load(), _stored(**columns))  # type: ignore[arg-type]

    assert failed is not None and failed[0] == expected


def test_a_question_a_person_accepted_falls_with_its_facts() -> None:
    """A fact that no longer holds rejects it, the person's accept or not."""
    stored = replace(
        _stored(reviewed_verdict=ReviewVerdict.ACCEPTED), facts_validated=False
    )

    failed = _recheck(None, Settings.load(), stored)  # type: ignore[arg-type]

    assert failed is not None and failed[0] == QuestionRejection.SOURCE_CHANGED


class _Rejected:
    """A catalogue holding one rejected question, whose probe must not run."""

    def judged(self, within=None):
        yield _stored(status="rejected", embedding=[1.0])

    def nearest(self, embedding, before=None, excluding=(), language=None):
        raise AssertionError("a rejected question was probed")

    def reject(self, verdicts) -> int:
        return len(verdicts)


def test_a_rejected_question_is_not_checked_again() -> None:
    """It can only be rejected, so the parse and the probe are skipped."""
    assert reverify(_Rejected(), Settings.load()) == 0  # type: ignore[arg-type]
