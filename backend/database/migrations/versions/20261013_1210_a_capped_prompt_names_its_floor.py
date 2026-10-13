"""Two comments name the atomic prompt version as it is recorded now.

A capped atomic prompt is version 10, and the cap its version carries is the
one a passage stating more sentences and list items replaces with its own
count. Comment only.

Revision: 7d4e1f2a9c63
Parent:   3c5a9d2e7b14
Created:  2026-10-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7d4e1f2a9c63"
down_revision: str | None = "3c5a9d2e7b14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    (
        "facts",
        "prompt_version",
        True,
        "Version of the extraction prompt, with the cap appended when the atomic prompt carried one, as 9+cap4. The prompt decides what counts as a fact, so two prompts are two datasets.",
        "Version of the extraction prompt, with the cap appended when the atomic prompt carried one, as 10+cap4: the cap EXTRACTION_MIN_OTHER_SHARE works out to, which a passage stating more sentences and list items was asked to replace with its own count. The prompt decides what counts as a fact, so two prompts are two datasets.",
    ),
    (
        "prompts",
        "version",
        False,
        "The PROMPT_VERSION its module declared when this text was written, with the cap appended for a capped atomic extraction prompt, as 9+cap4. Indexed: resolving a question's prompt_version is the query this table is for.",
        "The PROMPT_VERSION its module declared when this text was written, with the cap appended for a capped atomic extraction prompt, as 10+cap4. Indexed: resolving a question's prompt_version is the query this table is for.",
    ),
)


def upgrade() -> None:
    """Writes the comments as they read now."""
    for table, column, nullable, before, now in _COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.Text(),
            existing_nullable=nullable,
            comment=now,
            existing_comment=before,
        )


def downgrade() -> None:
    """Puts back the comments as they read before."""
    for table, column, nullable, before, now in _COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.Text(),
            existing_nullable=nullable,
            comment=before,
            existing_comment=now,
        )
