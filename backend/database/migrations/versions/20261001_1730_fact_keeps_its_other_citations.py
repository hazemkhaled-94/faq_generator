"""A fact outlives a citation while another passage still cites it.

`delete_fact_without_passage` deleted a fact whenever one of its citations
went. It now deletes a bridge on any citation, and any other fact on its
last.

Revision: 5d1c7e2a9b40
Parent:   fcaaa00f8b88
Created:  2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "5d1c7e2a9b40"
down_revision: str | None = "fcaaa00f8b88"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Deletes a non-bridge fact only on its last citation."""
    op.execute(
        """
CREATE OR REPLACE FUNCTION delete_fact_without_passage() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM facts f
     WHERE f.id = OLD.fact_id
       AND (
           f.kind = 'bridge'
           OR NOT EXISTS (
               SELECT 1 FROM fact_passages fp WHERE fp.fact_id = f.id
           )
       );
    RETURN NULL;
END;
$$;
"""
    )


def downgrade() -> None:
    """Deletes a fact on any of its citations again."""
    op.execute(
        """
CREATE OR REPLACE FUNCTION delete_fact_without_passage() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM facts WHERE id = OLD.fact_id;
    RETURN NULL;
END;
$$;
"""
    )
