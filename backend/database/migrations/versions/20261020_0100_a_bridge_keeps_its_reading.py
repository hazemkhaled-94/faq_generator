"""A bridge fact keeps the relation it was written with and the question it was tested with.

Prompt 6 names a relation for every bridge and asks the question only both
passages answer, and neither was stored: a rebuild of the question stage
could not tell a contrast from a definition, and a re-judgement could not
re-test the bridge. `facts.bridge` holds {relation, question, answer} on a
bridge and is NULL on every other fact and on every bridge already stored.

Revision: c3a9e1470b5d
Parent:   a41c9e3d7b52
Created:  2026-10-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3a9e1470b5d"
down_revision: str | None = "a41c9e3d7b52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The relations a bridge may name: `llm.spans.RELATIONS`, spelled out so this
#: revision keeps reading the same when that table grows.
RELATIONS_CHECKED = (
    "defines",
    "limits",
    "consequence",
    "applies",
    "parallel",
    "contrast",
)


def upgrade() -> None:
    """Adds facts.bridge, NULL on every row, and the constraint that keeps it a bridge's."""
    op.add_column(
        "facts",
        sa.Column(
            "bridge",
            postgresql.JSONB(none_as_null=True),
            nullable=True,
            comment="A bridge's own reading: the relation the model named and "
            "the question and short answer it was tested with. NULL on every "
            "other fact and on bridges older than prompt 6.",
        ),
    )
    relations = ", ".join(f"'{one}'" for one in RELATIONS_CHECKED)
    op.create_check_constraint(
        "facts_bridge_reading_valid",
        "facts",
        "bridge IS NULL OR coalesce(kind = 'bridge' AND bridge->>'relation' IN "
        f"({relations}) AND jsonb_typeof(bridge->'question') = 'string' AND "
        "jsonb_typeof(bridge->'answer') = 'string', false)",
    )


def downgrade() -> None:
    """Drops the constraint and the column."""
    op.drop_constraint("facts_bridge_reading_valid", "facts", type_="check")
    op.drop_column("facts", "bridge")
