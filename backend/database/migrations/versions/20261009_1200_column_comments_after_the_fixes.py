"""Four column comments say what the columns hold after the 2026-10-09 fixes.

A capped atomic prompt is versioned with its cap, the stored digest is over the
system text alone, and nothing reads topics.embedding. Comment only.

Revision: 9e2b7c41d058
Parent:   6c1d0e4b9a27
Created:  2026-10-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "9e2b7c41d058"
down_revision: str | None = "6c1d0e4b9a27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    (
        "prompts",
        "version",
        sa.Text(),
        False,
        "The PROMPT_VERSION its module declared when this text was written. Indexed: resolving a question's prompt_version is the query this table is for.",
        "The PROMPT_VERSION its module declared when this text was written, with the cap appended for a capped atomic extraction prompt, as 9+cap4. Indexed: resolving a question's prompt_version is the query this table is for.",
    ),
    (
        "prompts",
        "digest",
        sa.Text(),
        False,
        "The first sixteen hex characters of the text's SHA-256, spelled as tests/static/test_prompts_pinned.py spells it, so a row and that file's pin can be compared by eye. What a changed prompt under an unchanged version is noticed by at run time.",
        "The first sixteen hex characters of the system text's SHA-256. What a changed prompt under an unchanged version is noticed by at run time.",
    ),
    (
        "facts",
        "prompt_version",
        sa.Text(),
        True,
        "Version of the extraction prompt. The prompt decides what counts as a fact, so two prompts are two datasets.",
        "Version of the extraction prompt, with the cap appended when the atomic prompt carried one, as 9+cap4. The prompt decides what counts as a fact, so two prompts are two datasets.",
    ),
    (
        "topics",
        "embedding",
        Vector(1024),
        True,
        "Where this topic sits, as the membership-weighted mean of its passages' vectors, normalised back to length 1. Derived rather than asked for: it is an average of passages.embedding computed in SQL, so no worker loads a model to write it and it cannot disagree with the passages it is the mean of. What it is for is telling two topics apart - a factorisation splits one subject in two often enough that the coverage report needs to say so. NULL until the passages are embedded.",
        "Where this topic sits, as the mean of its passages' vectors, normalised back to length 1. Derived rather than asked for: it is an average of passages.embedding computed in SQL, so no worker loads a model to write it and it cannot disagree with the passages it is the mean of. Written by every fit; nothing reads it. NULL until the passages are embedded.",
    ),
)


def upgrade() -> None:
    """Writes the comments as they read now."""
    for table, column, kind, nullable, before, now in _COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=kind,
            existing_nullable=nullable,
            comment=now,
            existing_comment=before,
        )


def downgrade() -> None:
    """Puts back the comments as they read before."""
    for table, column, kind, nullable, before, now in _COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=kind,
            existing_nullable=nullable,
            comment=before,
            existing_comment=now,
        )
