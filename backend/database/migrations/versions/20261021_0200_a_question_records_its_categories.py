"""A question records the categories its writer was told.

QUESTIONS_CATEGORIZATIONS deals each answerable slot one category of every
categorization, and the writer is told their descriptions. settings_version
cannot say which category one row drew, so the row keeps what was rendered.
One nullable column, written for new questions only; every row already
stored keeps NULL.

Revision: 626a5b07ae34
Parent:   733a3eadef7c
Created:  2026-10-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "626a5b07ae34"
down_revision: str | None = "733a3eadef7c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMENT = (
    "The categories QUESTIONS_CATEGORIZATIONS dealt this question, each as its "
    "writer was told it, one JSON object per categorization. NULL where none "
    "was rendered: an unanswerable question, a follow-up, a run with no "
    "categorizations, and every question written before this column."
)


def upgrade() -> None:
    """Adds the column, NULL on every row."""
    op.add_column(
        "questions",
        sa.Column(
            "categories",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=_COMMENT,
        ),
    )


def downgrade() -> None:
    """Drops it."""
    op.drop_column("questions", "categories")
