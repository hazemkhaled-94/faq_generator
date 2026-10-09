"""Four column comments describe settings_version as it is digested now.

settings_version digests every catalogued setting as resolved, not only the
stored overrides, and never reads 'environment'. Comment only.

Revision: 6c1d0e4b9a27
Parent:   2871990b2443
Created:  2026-10-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6c1d0e4b9a27"
down_revision: str | None = "2871990b2443"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    (
        "facts",
        "settings_version",
        "The configuration this fact was extracted under, as the digest settings.store computes, or 'environment' when nothing was overridden. The columns above name the model and the prompt; this names the rest of it, including the shares the checks held this fact to. NULL for a fact written before a setting could be changed without a restart.",
        "The configuration this fact was extracted under: a digest of every catalogued setting as resolved, the env files and the make command line overlaid with the stored overrides. The columns above name the model and the prompt; this names the rest of it, including the shares the checks held this fact to. NULL for a fact written before a setting could be changed without a restart.",
    ),
    (
        "topics",
        "settings_version",
        "The configuration this topic was fitted under, as the digest settings.store computes, or 'environment' when nothing was overridden. A fit is not reproducible without the parameters it used, and the seed is only one of them. NULL for a topic fitted before a setting could be changed without a restart.",
        "The configuration this topic was fitted under: a digest of every catalogued setting as resolved, the env files and the make command line overlaid with the stored overrides. A fit is not reproducible without the parameters it used, and the seed is only one of them. NULL for a topic fitted before a setting could be changed without a restart.",
    ),
    (
        "assessments",
        "settings_version",
        "The configuration this judgement was made under, as the digest settings.store computes, or 'environment' when nothing was overridden.",
        "The configuration this judgement was made under: a digest of every catalogued setting as resolved, the env files and the make command line overlaid with the stored overrides.",
    ),
    (
        "questions",
        "prompt_version",
        "Version of the prompt that wrote this question, as question_generation.types.PROMPT_VERSION declares it. The prompt decides what a question IS, so two prompts are two datasets - the same reason facts.prompt_version exists. Not covered by settings_version, which is a digest of the stored overrides and does not move when a prompt is edited. NULL for a question written before the version was recorded.",
        "Version of the prompt that wrote this question, as question_generation.types.PROMPT_VERSION declares it. The prompt decides what a question IS, so two prompts are two datasets - the same reason facts.prompt_version exists. Not covered by settings_version, which digests the settings and does not move when a prompt is edited. NULL for a question written before the version was recorded.",
    ),
)


def upgrade() -> None:
    """Writes the comments as they read now."""
    for table, column, before, now in _COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.Text(),
            existing_nullable=True,
            comment=now,
            existing_comment=before,
        )


def downgrade() -> None:
    """Puts back the comments as they read before."""
    for table, column, before, now in _COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.Text(),
            existing_nullable=True,
            comment=before,
            existing_comment=now,
        )
