"""A question names the models that wrote and checked it.

The host and the containers drain one topic queue under different models,
and a question recorded none of them: its settings_version is the same
digest on both sides. Three nullable columns, written for new questions
only; every row already stored keeps NULL.

Revision: bf8f2e65c149
Parent:   1ff74784a860
Created:  2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bf8f2e65c149"
down_revision: str | None = "1ff74784a860"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODELS = (
    (
        "writer_model",
        (
            "The model that wrote this question. NULL for a question written before "
            "this was recorded."
        ),
    ),
    (
        "verifier_model",
        (
            "The model the verifying gates asked about this question. NULL for a "
            "question written before this was recorded."
        ),
    ),
    (
        "phrasing_model",
        (
            "The model the phrasing gate asked about this question. NULL when that "
            "gate was off, or for a question written before this was recorded."
        ),
    ),
)


def upgrade() -> None:
    """Adds the three columns, NULL on every row."""
    for name, comment in _MODELS:
        op.add_column(
            "questions", sa.Column(name, sa.Text(), nullable=True, comment=comment)
        )


def downgrade() -> None:
    """Drops them."""
    for name, _ in reversed(_MODELS):
        op.drop_column("questions", name)
