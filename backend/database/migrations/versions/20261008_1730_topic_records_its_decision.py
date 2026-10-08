"""A topic records when a person last decided about it.

A review pull compared an answer's time with a topic's fit alone, so an
older answer overwrote a rename made on the Topics page since. The pull now
compares it with this too.

Revision: 1ff74784a860
Parent:   8213be66d5ba
Created:  2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1ff74784a860"
down_revision: str | None = "8213be66d5ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Adds topics.decided_at, NULL on every row."""
    op.add_column(
        "topics",
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When a person last named this topic or set its coverage: "
            "the time of the edit on the Topics page, or of the answer a review "
            "pull applied. Carried across a refit with the label. NULL when "
            "nobody has.",
        ),
    )


def downgrade() -> None:
    """Drops it."""
    op.drop_column("topics", "decided_at")
