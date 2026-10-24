"""A fact carries the language it was read in.

The dedup probe narrows its search to the candidate's language. It read the
language through the passage and document a fact cites, which made the
planner join the citations first and sort every fact in exact order: the
HNSW index on `facts.embedding` was never used, 311 ms a probe over 7,000
facts and a query a corpus ten times larger could not afford. `facts.language`
is that same value, the language of the passage at position 0 of
`fact_passages` and where that has none the document's, written when the fact
is stored. Existing facts are backfilled from the same citation, and the
table is analysed after it so the first probe plans with the new column's
statistics.

Revision: 860d56b11032
Parent:   20e31b1656f7
Created:  2026-10-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "860d56b11032"
down_revision: str | None = "20e31b1656f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Adds facts.language and fills it from each fact's first citation."""
    op.add_column(
        "facts",
        sa.Column(
            "language",
            sa.Text(),
            nullable=True,
            comment="The language the fact was read in: that of the passage at "
            "position 0 of fact_passages, and where that passage is too short "
            "to tell, its document's. Written when the fact is stored, so the "
            "dedup probe filters on it beside the vector index rather than "
            "through the citations. NULL on a fact whose passage and document "
            "name none.",
        ),
    )
    op.execute(
        """
        UPDATE facts SET language = coalesce(p.language, d.language)
        FROM fact_passages fp
        JOIN passages p ON p.id = fp.passage_id
        JOIN documents d ON d.sha256 = p.doc_sha256
        WHERE fp.fact_id = facts.id AND fp.position = 0
        """
    )
    # The planner has no statistics on the new column until autovacuum visits
    # the table, and the probe planned without them kept a sequential scan:
    # 142 ms a probe against 31 ms once analysed, on the reviewed build.
    op.execute("ANALYZE facts")


def downgrade() -> None:
    """Drops the column."""
    op.drop_column("facts", "language")
