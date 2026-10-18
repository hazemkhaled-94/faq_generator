"""assessment_metrics holds the DataMorgana paper's six question scores.

The paper's judge scores a question 1 to 3 on fluency, clarity, conciseness,
relevance, consistency and answerability in one call. Each score is a metric
row of its own, under a `rubric_` name, so the CHECK on the metric names
widens to thirteen and the column comment says what the six are. Taking it
back out deletes those rows first, since the narrower CHECK refuses them.

Revision: 733a3eadef7c
Parent:   d5b2f8a60c14
Created:  2026-10-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "733a3eadef7c"
down_revision: str | None = "d5b2f8a60c14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECK = "assessment_metrics_metric_valid"

#: The seven names phoenix-evals gives, which the CHECK held before.
_PHOENIX = (
    "hallucination",
    "relevance",
    "qa_correctness",
    "summarization",
    "toxicity",
    "conciseness",
    "refusal",
)

#: The paper's six, in its order.
_RUBRIC = (
    "rubric_fluency",
    "rubric_clarity",
    "rubric_conciseness",
    "rubric_relevance",
    "rubric_consistency",
    "rubric_answerability",
)

_BEFORE = (
    "hallucination | relevance | qa_correctness | summarization | toxicity | "
    "conciseness | refusal. Spelled as arize-phoenix-evals spells it."
)
_NOW = (
    "hallucination | relevance | qa_correctness | summarization | toxicity | "
    "conciseness | refusal, spelled as arize-phoenix-evals spells them; or "
    "rubric_fluency | rubric_clarity | rubric_conciseness | rubric_relevance | "
    "rubric_consistency | rubric_answerability, the DataMorgana paper's six "
    "scores of a question, labelled 1 to 3."
)


def _names(names: tuple[str, ...]) -> str:
    """The CHECK expression allowing exactly these metric names."""
    return f"metric IN ({', '.join(f"'{one}'" for one in names)})"


def _comment(now: str, before: str) -> None:
    """Rewrites the metric column's comment."""
    op.alter_column(
        "assessment_metrics",
        "metric",
        existing_type=sa.Text(),
        existing_nullable=False,
        comment=now,
        existing_comment=before,
    )


def upgrade() -> None:
    """Widens the CHECK to the thirteen names and says what they are."""
    op.drop_constraint(_CHECK, "assessment_metrics", type_="check")
    op.create_check_constraint(_CHECK, "assessment_metrics", _names(_PHOENIX + _RUBRIC))
    _comment(_NOW, _BEFORE)


def downgrade() -> None:
    """Deletes the rubric's rows and puts back the seven-name CHECK and comment."""
    op.execute("DELETE FROM assessment_metrics WHERE starts_with(metric, 'rubric_')")
    op.drop_constraint(_CHECK, "assessment_metrics", type_="check")
    op.create_check_constraint(_CHECK, "assessment_metrics", _names(_PHOENIX))
    _comment(_BEFORE, _NOW)
