"""`documents.oversized` names the budget the chunker cuts to.

The comment said EMBEDDING_MAX_TOKENS. The chunker cuts to that less the
tokens the embedder adds, and counts a passage over that as oversized.
Comment only.

Revision: 2871990b2443
Parent:   a739b57cffae
Created:  2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2871990b2443"
down_revision: str | None = "a739b57cffae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BEFORE = (
    "Passages the last chunking run stored above EMBEDDING_MAX_TOKENS. Expected "
    "to be 0: the chunker splits on that budget, so anything above it means the "
    "split did not happen. A tripwire; chunking discards nothing."
)
_NOW = (
    "Passages the last chunking run stored above its token budget, "
    "EMBEDDING_MAX_TOKENS less the tokens the embedder adds. Expected to be 0: "
    "the chunker splits on that budget, so anything above it means the split "
    "did not happen. A tripwire; chunking discards nothing."
)


def upgrade() -> None:
    """Writes the comment as it reads now."""
    op.alter_column(
        "documents",
        "oversized",
        existing_type=sa.Integer(),
        existing_nullable=True,
        comment=_NOW,
        existing_comment=_BEFORE,
    )


def downgrade() -> None:
    """Puts back the comment as it read before."""
    op.alter_column(
        "documents",
        "oversized",
        existing_type=sa.Integer(),
        existing_nullable=True,
        comment=_BEFORE,
        existing_comment=_NOW,
    )
