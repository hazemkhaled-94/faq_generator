"""A citation that names sentences carries both evidence bounds.

`fact_passages_citation_complete` compared the bounds, and a comparison
with a NULL side is NULL, which a CHECK lets through: a citation could name
its sentences with no span. The check now asks for both bounds.

Added NOT VALID and then validated, so a row that breaks it fails the
upgrade by the constraint's name.

Revision: ad14bed603d4
Parent:   14432e9fd5c9
Created:  2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "ad14bed603d4"
down_revision: str | None = "14432e9fd5c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "fact_passages_citation_complete"
_WHOLE = (
    "(sentence_ids IS NULL AND evidence_start IS NULL AND evidence_end IS NULL) "
    "OR (sentence_ids IS NOT NULL AND evidence_start IS NOT NULL "
    "AND evidence_end IS NOT NULL AND evidence_end >= evidence_start)"
)
_COMPARED = (
    "(sentence_ids IS NULL AND evidence_start IS NULL AND evidence_end IS NULL) "
    "OR (sentence_ids IS NOT NULL AND evidence_end >= evidence_start)"
)


def upgrade() -> None:
    """Replaces the check, then validates every row against it."""
    op.drop_constraint(_NAME, "fact_passages", type_="check")
    op.execute(
        f"ALTER TABLE fact_passages ADD CONSTRAINT {_NAME} CHECK ({_WHOLE}) NOT VALID"
    )
    op.execute(f"ALTER TABLE fact_passages VALIDATE CONSTRAINT {_NAME}")


def downgrade() -> None:
    """Puts back the check that compares the bounds alone."""
    op.drop_constraint(_NAME, "fact_passages", type_="check")
    op.create_check_constraint(_NAME, "fact_passages", _COMPARED)
