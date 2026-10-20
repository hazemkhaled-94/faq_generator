"""A question records what it was written to be.

One NOT NULL column, `kind`: single, needs_both, compound or false_premise.
It used to be read off how many passages a question cites; it is now chosen
before the question is written and follows the citations afterwards. Every
row already stored is backfilled from its passage scope, needs_both where it
cites more than one passage and single otherwise, which is what the count
of passages said. The archive is backfilled by the same rule, because a
restore populates a row from its archived payload and the column refuses the
NULL a payload without the key would give.

The backfill reads passage_scope, which holds no compound question: taking
this revision out and putting it back turns every compound question into
needs_both.

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
    """Adds the column, backfills it and the archive, and constrains it."""
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
    op.execute(
        "UPDATE archived_rows SET payload = payload || jsonb_build_object("
        "'kind', CASE WHEN payload->>'passage_scope' = 'multi_passage' "
        "THEN 'needs_both' ELSE 'single' END) "
        "WHERE table_name = 'questions' AND NOT payload ? 'kind'"
    )
    op.create_check_constraint(
        "questions_kind_valid",
        "questions",
        "kind IN ('single', 'needs_both', 'compound', 'false_premise')",
    )


def downgrade() -> None:
    """Drops the constraint and the column, and the key from the archive."""
    op.execute(
        "UPDATE archived_rows SET payload = payload - 'kind' "
        "WHERE table_name = 'questions'"
    )
    op.drop_constraint("questions_kind_valid", "questions", type_="check")
    op.drop_column("questions", "kind")
