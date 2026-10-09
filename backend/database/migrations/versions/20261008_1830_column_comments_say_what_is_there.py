"""Four column comments say what the columns hold now.

`fact_passages.passage_id` said a deleted passage takes the fact with it,
which since 5d1c7e2a9b40 holds only for a bridge and a fact cited nowhere
else. `assessment_metrics.metric` named four of the seven metrics and
`questions.question_type` eleven of the thirteen types.
`questions.settings_version` said the version names the model that wrote
the question, which bf8f2e65c149's columns now record. Comments only.

Revision: a739b57cffae
Parent:   ad14bed603d4
Created:  2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a739b57cffae"
down_revision: str | None = "ad14bed603d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (table, column, type, nullable, the comment before, the comment now)
_COMMENTS = (
    (
        "fact_passages",
        "passage_id",
        sa.BigInteger(),
        False,
        (
            "A passage the claim rests on. Deleting the passage deletes this row and "
            "the fact with it."
        ),
        (
            "A passage the claim rests on. Deleting the passage deletes this row, and "
            "a trigger deletes the fact if it is a bridge or cites no other passage."
        ),
    ),
    (
        "assessment_metrics",
        "metric",
        sa.Text(),
        False,
        (
            "hallucination | relevance | qa_correctness | summarization. Spelled as "
            "arize-phoenix-evals spells it."
        ),
        (
            "hallucination | relevance | qa_correctness | summarization | toxicity | "
            "conciseness | refusal. Spelled as arize-phoenix-evals spells it."
        ),
    ),
    (
        "questions",
        "question_type",
        sa.Text(),
        True,
        (
            "What the question asks for, enforced by a CHECK constraint: factoid, "
            "definition, entity, enumeration, condition, reason, procedure, "
            "consequence, comparison, aggregation or temporal. Requested by the plan "
            "before the question is written, not read off it afterwards. "
            "QUESTIONS_TYPE_MIX sets which are written and in what proportion."
        ),
        (
            "What the question asks for, enforced by a CHECK constraint: factoid, "
            "definition, entity, enumeration, condition, reason, procedure, "
            "consequence, comparison, aggregation, temporal, implication or "
            "application. Requested by the plan before the question is written, not "
            "read off it afterwards. QUESTIONS_TYPE_MIX sets which are written and in "
            "what proportion."
        ),
    ),
    (
        "questions",
        "settings_version",
        sa.Text(),
        True,
        (
            "The configuration this question was written under, as the digest "
            "settings.store computes, or 'environment' when nothing was "
            "overridden. Which model wrote it, what mix the plan aimed for and "
            "what bounds the gates held it to are all in the settings that "
            "version names. NULL for a question written before a setting could "
            "be changed without a restart."
        ),
        (
            "The configuration this question was written under, as the digest "
            "settings.store computes. The models that wrote and checked it are "
            "in writer_model, verifier_model and phrasing_model. NULL for a "
            "question written before a setting could be changed without a "
            "restart."
        ),
    ),
)


def upgrade() -> None:
    """Writes the comments as they read now."""
    for table, column, type_, nullable, before, now in _COMMENTS:
        op.alter_column(
            table,
            column,
            existing_type=type_,
            existing_nullable=nullable,
            comment=now,
            existing_comment=before,
        )


def downgrade() -> None:
    """Puts back the comments as they read before."""
    for table, column, type_, nullable, before, now in _COMMENTS:
        op.alter_column(
            table,
            column,
            existing_type=type_,
            existing_nullable=nullable,
            comment=before,
            existing_comment=now,
        )
