"""A duplicate refusal keeps the id of the fact it repeats.

Without it the replay after a drain that replaced facts could not tell which
refusals had lost their twin, and read every duplicate refusal of the corpus.
The column is a foreign key to facts that is set NULL when the twin is
deleted, so a NULL on a refusal is what marks it for the replay. NULL on every
row already stored, which the first replay then reads once.

Revision: 7a41c9d2e8b0
Parent:   860d56b11032
Created:  2026-10-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a41c9d2e8b0"
down_revision: str | None = "860d56b11032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMENT = (
    "For a `duplicate` refusal, the fact in another passage it repeats: what "
    "it is re-checked against when that fact goes. NULL when that fact is "
    "deleted, which marks the refusal for the dedup replay; NULL too for a "
    "refusal whose twin is a fact of its own passage, and on every other row."
)


def upgrade() -> None:
    """Adds the column and its foreign key."""
    op.add_column(
        "facts",
        sa.Column("twin_id", sa.BigInteger(), nullable=True, comment=_COMMENT),
    )
    op.create_foreign_key(
        "facts_twin_id_fkey", "facts", "facts", ["twin_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    """Drops both."""
    op.drop_constraint("facts_twin_id_fkey", "facts", type_="foreignkey")
    op.drop_column("facts", "twin_id")
