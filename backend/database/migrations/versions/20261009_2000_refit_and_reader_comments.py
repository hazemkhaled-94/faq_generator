"""Four comments say what a fit replaces, who records prompts, when workers read.

A fit replaces the topics of each language it fits, four stages record their
prompts, and a worker reads the stored settings before each drain. Comment
only.

Revision: f6f7b1880b23
Parent:   9e2b7c41d058
Created:  2026-10-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6f7b1880b23"
down_revision: str | None = "9e2b7c41d058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    (
        "topics",
        "question_status",
        sa.Text(),
        False,
        "new | pending | in_progress | failed | generated, enforced by a CHECK constraint. Question generation's own queue, over topics rather than over fits: the unit of work is one topic's facts. Meaningless on a fit request, which is why that queue carries topic_index IS NOT NULL. A fit replaces every row here, so a refit returns every topic to `new`; the questions themselves are not a topic's and survive it.",
        "new | pending | in_progress | failed | generated, enforced by a CHECK constraint. Question generation's own queue, over topics rather than over fits: the unit of work is one topic's facts. Meaningless on a fit request, which is why that queue carries topic_index IS NOT NULL. A fit replaces the rows of each language it fits, so a refit returns those topics to `new`; the questions themselves are not a topic's and survive it.",
    ),
    (
        "assessments",
        "topic_id",
        sa.BigInteger(),
        True,
        "The topic this is about, NULL unless artifact_kind is `topic`. A refit replaces every topic, so this cascades on every `make topics-discover`.",
        "The topic this is about, NULL unless artifact_kind is `topic`. Cascades when a fit replaces the topics of that topic's language.",
    ),
    (
        "prompts",
        "service",
        sa.Text(),
        False,
        "Which stage sends it: extraction or questions. The stage writes its own and no other's, because no backend service imports another.",
        "Which stage sends it: extraction, topics, questions or assessment. The stage writes its own and no other's, because no backend service imports another.",
    ),
)

_TABLES = (
    (
        "service_settings",
        "Settings changed through the API, the CLI or a page, one row per setting. An override over what configs/env/backend.env and .env say, never a default: deleting a row returns the setting to the file. Workers read this when they claim a row, so a change reaches them without a restart.",
        "Settings changed through the API, the CLI or a page, one row per setting. An override over what configs/env/backend.env and .env say, never a default: deleting a row returns the setting to the file. Workers read this before each drain, so a change reaches them without a restart.",
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
    for table, before, now in _TABLES:
        op.create_table_comment(table, now, existing_comment=before)


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
    for table, before, now in _TABLES:
        op.create_table_comment(table, before, existing_comment=now)
