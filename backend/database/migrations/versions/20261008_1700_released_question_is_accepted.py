"""A released question is always accepted.

The code clears `release_id` whenever a status leaves `accepted`; this
makes the table refuse a row where it did not.

Revision: 3fe4226da3b6
Parent:   5d1c7e2a9b40
Created:  2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "3fe4226da3b6"
down_revision: str | None = "5d1c7e2a9b40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Adds the CHECK. Fails, changing nothing, if a row breaks it."""
    op.create_check_constraint(
        "questions_released_is_accepted",
        "questions",
        "release_id IS NULL OR status = 'accepted'",
    )


def downgrade() -> None:
    """Drops it."""
    op.drop_constraint("questions_released_is_accepted", "questions", type_="check")
