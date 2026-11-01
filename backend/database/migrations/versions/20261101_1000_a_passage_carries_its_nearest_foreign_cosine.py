"""A passage carries the cosine of its nearest twin in another document.

The furniture filter asked, for every candidate passage of every topic, whether
another document of the same language holds a passage at least as close as the
threshold. Without a stored score that is one nearest-neighbour probe per
candidate: linear in the corpus, repeated for every topic and every run.
`passages.nearest_foreign_cosine` is that score, the exact maximum cosine to
any embedded passage of another document in the same language, written when a
passage is embedded and raised when a later document's passages exceed it. The
filter reads the column against the threshold.

The backfill computes the column for the passages already embedded, in batches
of passage ids committed one at a time, outside the revision's transaction.
Each batch compares its passages with every other embedded passage of their
language, so on a large corpus time it on a copy first.

Revision: 9e3b61d4a2c7
Parent:   4a7c2e91d3b8
Created:  2026-11-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9e3b61d4a2c7"
down_revision: str | None = "4a7c2e91d3b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Passages whose score one statement computes.
_BATCH = 500


def upgrade() -> None:
    """Adds passages.nearest_foreign_cosine and fills it for embedded passages."""
    op.add_column(
        "passages",
        sa.Column(
            "nearest_foreign_cosine",
            sa.Float(),
            nullable=True,
            comment="The exact cosine between this passage and the closest "
            "embedded passage of another document in the same language. "
            "Written when the passage is embedded, and raised when a later "
            "document's passage is closer, so the furniture filter reads a "
            "column instead of probing for a twin per candidate. NULL while "
            "the passage has no embedding or no other document holds its "
            "language.",
        ),
    )
    connection = op.get_bind()
    bounds = connection.execute(
        sa.text("SELECT min(id), max(id) FROM passages WHERE embedding IS NOT NULL")
    ).one()
    if bounds[0] is None:
        return
    # Committed batch by batch, so a long backfill holds no lock for its run.
    with op.get_context().autocommit_block():
        for low in range(bounds[0], bounds[1] + 1, _BATCH):
            op.execute(
                sa.text(
                    """
                    UPDATE passages p SET nearest_foreign_cosine = (
                        SELECT max(1 - (q.embedding <=> p.embedding))
                        FROM passages q
                        WHERE q.doc_sha256 <> p.doc_sha256
                          AND q.language = p.language
                          AND q.embedding IS NOT NULL
                    )
                    WHERE p.embedding IS NOT NULL AND p.id >= :low AND p.id < :high
                    """
                ).bindparams(low=low, high=low + _BATCH)
            )


def downgrade() -> None:
    """Drops the column."""
    op.drop_column("passages", "nearest_foreign_cosine")
