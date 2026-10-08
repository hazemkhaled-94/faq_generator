"""An upload record keeps its digest when its document is deleted.

`ingest_events.sha256` was a foreign key to documents, ON DELETE SET NULL:
deleting a document rewrote every record of its uploads, and the archive,
which copies deletions only, kept no trace of the digest. It is now a
plain column.

Revision: 8213be66d5ba
Parent:   04419594a51e
Created:  2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8213be66d5ba"
down_revision: str | None = "04419594a51e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KEYED = (
    "SHA-256 of the submitted bytes, and the link to the document they became. "
    "NULL for uploads refused before hashing, which is why the foreign key "
    "tolerates NULL."
)
_PLAIN = (
    "SHA-256 of the submitted bytes, which names the document they became. NULL "
    "for uploads refused before hashing. Not a foreign key, so the record keeps "
    "it after the document is deleted."
)


def upgrade() -> None:
    """Drops the foreign key, whatever it is named, and rewrites no row."""
    op.execute(
        """
DO $$
DECLARE
    named text;
BEGIN
    FOR named IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'ingest_events'::regclass
           AND confrelid = 'documents'::regclass
           AND contype = 'f'
    LOOP
        EXECUTE format('ALTER TABLE ingest_events DROP CONSTRAINT %I', named);
    END LOOP;
END;
$$;
"""
    )
    op.alter_column(
        "ingest_events",
        "sha256",
        existing_type=sa.CHAR(length=64),
        existing_nullable=True,
        comment=_PLAIN,
        existing_comment=_KEYED,
    )


def downgrade() -> None:
    """Nulls each digest no document has, as the key would have, then adds it."""
    op.execute(
        "UPDATE ingest_events e SET sha256 = NULL WHERE sha256 IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM documents d WHERE d.sha256 = e.sha256)"
    )
    op.create_foreign_key(
        "ingest_events_sha256_fkey",
        "ingest_events",
        "documents",
        ["sha256"],
        ["sha256"],
        ondelete="SET NULL",
    )
    op.alter_column(
        "ingest_events",
        "sha256",
        existing_type=sa.CHAR(length=64),
        existing_nullable=True,
        comment=_KEYED,
        existing_comment=_PLAIN,
    )
