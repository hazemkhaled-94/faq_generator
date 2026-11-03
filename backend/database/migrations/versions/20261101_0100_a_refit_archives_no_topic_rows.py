"""A refit archives no topic rows.

Every fit deletes the topics of the languages it refits and, by cascade, their
memberships, and `archive_deleted_row()` archived each one: a refit of a
corpus of a hundred thousand passages wrote that many `passage_topics` rows
to `archived_rows`, which a restore does not want back, since a fit is over
the whole corpus and not a file. The function now returns early for the
tables named in the transaction's `qa.archive_skip`; the fit's store sets it
for `topics` and `passage_topics`, and every other deletion archives as before.

Taking it back out puts the function back as the first revision wrote it.

Revision: 5c1e8a3f7d20
Parent:   4a7c2e91d3b8
Created:  2026-11-01
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "5c1e8a3f7d20"
down_revision: str | None = "4a7c2e91d3b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Teaches the archive trigger to skip the tables a transaction names."""
    op.execute(
        """
CREATE OR REPLACE FUNCTION archive_deleted_row() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = ANY (
        string_to_array(current_setting('qa.archive_skip', true), ',')
    ) THEN
        RETURN NULL;
    END IF;
    INSERT INTO archived_rows (table_name, payload)
    VALUES (TG_TABLE_NAME, to_jsonb(OLD) - 'embedding');
    RETURN NULL;
END;
$$;
"""
    )


def downgrade() -> None:
    """Puts the function back as it was, archiving every deletion."""
    op.execute(
        """
CREATE OR REPLACE FUNCTION archive_deleted_row() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO archived_rows (table_name, payload)
    VALUES (TG_TABLE_NAME, to_jsonb(OLD) - 'embedding');
    RETURN NULL;
END;
$$;
"""
    )
