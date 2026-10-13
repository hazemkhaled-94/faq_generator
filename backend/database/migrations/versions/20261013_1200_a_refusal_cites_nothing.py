"""One comment says what a later position on a passage fact's citation is.

A duplicate refusal no longer adds its citation to the fact it repeats, so a
position above 0 on anything but a bridge is one an earlier version wrote.
Comment only.

Revision: 3c5a9d2e7b14
Parent:   f7bba722de8e
Created:  2026-10-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3c5a9d2e7b14"
down_revision: str | None = "f7bba722de8e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BEFORE = (
    "Where this passage sat in what the model was shown, from 0. 0 for the one "
    "passage of an atomic fact, a summary or an outline."
)
_NOW = (
    "Where this passage sat in what the model was shown, from 0. 0 for the one "
    "passage of an atomic fact, a summary or an outline. A higher one on any of "
    "those is a citation an earlier version's duplicate refusal added to the "
    "fact it repeated."
)


def upgrade() -> None:
    """Writes the comment as it reads now."""
    op.alter_column(
        "fact_passages",
        "position",
        existing_type=sa.Integer(),
        existing_nullable=False,
        comment=_NOW,
        existing_comment=_BEFORE,
    )


def downgrade() -> None:
    """Puts back the comment as it read before."""
    op.alter_column(
        "fact_passages",
        "position",
        existing_type=sa.Integer(),
        existing_nullable=False,
        comment=_BEFORE,
        existing_comment=_NOW,
    )
