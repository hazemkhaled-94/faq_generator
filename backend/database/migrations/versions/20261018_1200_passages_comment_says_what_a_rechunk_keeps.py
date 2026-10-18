"""The passages comment says a re-chunk keeps every passage it cuts again.

A re-chunk keeps each stored passage whose text, heading trail, sentences and
cells come back unchanged, and replaces only the rest. Comment only.

Revision: 8f759a3a3848
Parent:   7d4e1f2a9c63
Created:  2026-10-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "8f759a3a3848"
down_revision: str | None = "7d4e1f2a9c63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    (
        "passages",
        "A document split into retrievable chunks. Immutable: re-chunking deletes and re-inserts every passage of a document.",
        "A document split into retrievable chunks. A re-chunk keeps every passage whose text, heading trail, sentences and cells come back unchanged, with its id, writing its ordinal, pages and other columns in place, and deletes and re-inserts every other passage of the document.",
    ),
)


def upgrade() -> None:
    """Writes the comment as it reads now."""
    for table, before, now in _TABLES:
        op.create_table_comment(table, now, existing_comment=before)


def downgrade() -> None:
    """Puts back the comment as it read before."""
    for table, before, now in _TABLES:
        op.create_table_comment(table, before, existing_comment=now)
