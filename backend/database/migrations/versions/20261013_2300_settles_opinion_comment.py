"""The gate_scores comment says a settles verdict is kept as an opinion.

`gate_scores` can carry the verifier's `settles` verdicts as opinions with
no margin. Comment only.

Revision: f7bba722de8e
Parent:   f6f7b1880b23
Created:  2026-10-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f7bba722de8e"
down_revision: str | None = "f6f7b1880b23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    (
        "questions",
        "gate_scores",
        postgresql.JSONB(astext_type=sa.Text()),
        True,
        "One entry per measuring gate that read this question: the gate, the value it measured, the threshold it was read against and the margin between them. A gate that is a judgement rather than a measurement records nothing here, because an opinion has no number behind it. NULL for a question written before this column.",
        "One entry per measuring gate that read this question: the gate, the value it measured, the threshold it was read against and the margin between them. A judgement records nothing here, because an opinion has no number behind it, except the verifier's `settles` verdicts on a question written to have no answer: those carry opinion true and no margin, and feed no confidence. NULL for a question written before this column.",
    ),
)


def upgrade() -> None:
    """Writes the comments as they read now."""
    for table, column, kind, nullable, before, now in _COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=kind,
            existing_nullable=nullable,
            comment=now,
            existing_comment=before,
        )


def downgrade() -> None:
    """Puts back the comments as they read before."""
    for table, column, kind, nullable, before, now in _COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=kind,
            existing_nullable=nullable,
            comment=before,
            existing_comment=now,
        )
