"""The comment of `questions.status` says what deletes a question.

It said rejected questions are never deleted. A question that loses its last
citation is rejected as `source_changed` and kept, and deleting a document,
or what was derived from it, deletes its questions explicitly, rejected ones
included. Comment only.

Revision: c5a82e17d3f9
Parent:   9e3b61d4a2c7
Created:  2026-11-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5a82e17d3f9"
down_revision: str | None = "9e3b61d4a2c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BEFORE = "draft | accepted | rejected, enforced by a CHECK constraint. Rejected questions are never deleted: they are the drop-rate evidence in the coverage report."
_NOW = "draft | accepted | rejected, enforced by a CHECK constraint. A rejected question is kept as the drop-rate evidence in the coverage report, and so is one that lost its last citation (source_changed). Deleting a document, or what was derived from it, deletes its questions, rejected ones included."


def upgrade() -> None:
    """Writes the comment as it reads now."""
    op.alter_column(
        "questions",
        "status",
        existing_type=sa.Text(),
        existing_nullable=False,
        existing_server_default="draft",
        comment=_NOW,
        existing_comment=_BEFORE,
    )


def downgrade() -> None:
    """Puts back the comment as it read before."""
    op.alter_column(
        "questions",
        "status",
        existing_type=sa.Text(),
        existing_nullable=False,
        existing_server_default="draft",
        comment=_BEFORE,
        existing_comment=_NOW,
    )
