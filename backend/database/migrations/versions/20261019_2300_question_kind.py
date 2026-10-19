"""A question records what it was written to be.

One NOT NULL column, `kind`: single, needs_both, compound or false_premise.
It used to be read off how many passages a question cites; it is now chosen
before the question is written and follows the citations afterwards. Every
row already stored is backfilled from its passage scope, needs_both where it
cites more than one passage and single otherwise, which is what the count
of passages said.

Revision: a41c9e3d7b52
Parent:   8f759a3a3848
Created:  2026-10-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a41c9e3d7b52"
down_revision: str | None = "8f759a3a3848"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMENT = (
    "single | needs_both | compound | false_premise, enforced by a CHECK "
    "constraint. What the question was written to be, which decides the "
    "instruction its writer got and the checks it passed. It follows the "
    "citations: a question dealt as needs_both that rests on one passage is "
    "stored single. Rows from before this column read needs_both where "
    "passage_scope is multi_passage and single otherwise."
)


def upgrade() -> None:
    """Adds the column, backfills it from the passage scope, and constrains it."""
    op.add_column(
        "questions",
        sa.Column(
            "kind",
            sa.Text(),
            nullable=False,
            server_default="single",
            comment=_COMMENT,
        ),
    )
    op.execute(
        "UPDATE questions SET kind = 'needs_both' WHERE passage_scope = 'multi_passage'"
    )
    op.create_check_constraint(
        "questions_kind_valid",
        "questions",
        "kind IN ('single', 'needs_both', 'compound', 'false_premise')",
    )


def downgrade() -> None:
    """Drops the constraint and the column."""
    op.drop_constraint("questions_kind_valid", "questions", type_="check")
    op.drop_column("questions", "kind")
