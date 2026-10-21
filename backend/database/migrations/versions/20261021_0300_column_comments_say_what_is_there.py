"""Four column comments say what the columns hold.

`questions.categories` is NULL wherever no category was rendered, a compound
question included, which is told none; `topics.top_terms` is no longer what a
label is matched on across a refit, the passages a topic holds are; and
`topics.embedding` is read, to place each passage the fit left in no topic;
and `facts.bridge` also holds the id of the passage that headed the link.
Comments only.

Revision: 20e31b1656f7
Parent:   626a5b07ae34
Created:  2026-10-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "20e31b1656f7"
down_revision: str | None = "626a5b07ae34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    (
        "questions",
        "categories",
        postgresql.JSONB(astext_type=sa.Text()),
        True,
        "The categories QUESTIONS_CATEGORIZATIONS dealt this question, each as its writer was told it, one JSON object per categorization. NULL where none was rendered: an unanswerable question, a follow-up, a run with no categorizations, and every question written before this column.",
        "The categories QUESTIONS_CATEGORIZATIONS dealt this question, each as its writer was told it, one JSON object per categorization. NULL where none was rendered.",
    ),
    (
        "topics",
        "top_terms",
        postgresql.ARRAY(sa.Text()),
        False,
        "Highest-weighted terms, descending. The topic's readable identity and the only signature a label is matched on across a refit.",
        "Highest-weighted terms, descending. The topic's readable identity. A label is carried across a refit by the passages a topic holds, not by these terms.",
    ),
    (
        "facts",
        "bridge",
        postgresql.JSONB(astext_type=sa.Text()),
        True,
        "A bridge's own reading: the relation the model named and the question and short answer it was tested with. NULL on every other fact and on bridges older than prompt 6.",
        "A bridge's own reading: the relation the model named, the question and short answer it was tested with, and the id of the passage that headed the link (head). NULL on every other fact and on bridges older than prompt 6, which read as headed by the passage they show first.",
    ),
    (
        "topics",
        "embedding",
        Vector(1024),
        True,
        "Where this topic sits, as the mean of its passages' vectors, normalised back to length 1. Derived rather than asked for: it is an average of passages.embedding computed in SQL, so no worker loads a model to write it and it cannot disagree with the passages it is the mean of. Written by every fit; nothing reads it. NULL until the passages are embedded.",
        "Where this topic sits, as the mean of its passages' vectors, normalised back to length 1. Derived rather than asked for: it is an average of passages.embedding computed in SQL, so no worker loads a model to write it and it cannot disagree with the passages it is the mean of. Written by every fit, and read to place each passage the fit left in no topic in the nearest one. NULL until the passages are embedded.",
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
