"""The name a question's prompt is recorded under, where the readings overlap."""

from __future__ import annotations

import pytest

from views.questions import _sent_as


@pytest.mark.parametrize(
    ("question", "name"),
    [
        ({"answerable": False, "follows_id": 3, "kind": "compound"}, "perturb"),
        ({"follows_id": 3, "kind": "compound", "question_type": "factoid"}, "follow"),
        ({"kind": "compound", "question_type": "reason"}, "reason (compound)"),
        (
            {
                "kind": "compound",
                "question_type": "factoid",
                "planned_difficulty": "hard",
            },
            "factoid (compound)",
        ),
        ({"question_type": "reason", "planned_difficulty": "hard"}, "reason (spans)"),
        ({"question_type": "reason", "planned_difficulty": "medium"}, "reason (spans)"),
        ({"question_type": "reason", "planned_difficulty": "easy"}, "reason"),
        ({"kind": "needs_both", "question_type": "factoid"}, "factoid"),
        ({}, None),
    ],
)
def test_a_question_is_named_by_the_first_reading_that_fits(question, name) -> None:
    """Unanswerable, then follow-up, then compound, then spanning, then its type."""
    assert _sent_as(question) == name
