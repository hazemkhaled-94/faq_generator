"""Both orphan triggers lock the row they decide about first.

Each decided with NOT EXISTS at READ COMMITTED and locked nothing, so two
deletions at once each saw the other's citation, or the other's fact, still
there: a fact was left with no citation, and a question was left rejected
with no fact. Each now locks the fact or the question before deciding, and
the second deletion waits for the first and sees its result.

Revision: 14432e9fd5c9
Parent:   bf8f2e65c149
Created:  2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "14432e9fd5c9"
down_revision: str | None = "bf8f2e65c149"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FACT = """
CREATE OR REPLACE FUNCTION delete_fact_without_passage() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
{lock}    DELETE FROM facts f
     WHERE f.id = OLD.fact_id
       AND (
           f.kind = 'bridge'
           OR NOT EXISTS (
               SELECT 1 FROM fact_passages fp WHERE fp.fact_id = f.id
           )
       );
    RETURN NULL;
END;
$$;
"""

_QUESTION = """
CREATE OR REPLACE FUNCTION delete_question_without_facts() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
{lock}    IF EXISTS (
        SELECT 1
          FROM question_facts qf
          JOIN facts f ON f.id = qf.fact_id
          JOIN fact_passages fp ON fp.fact_id = f.id
          JOIN passages p ON p.id = fp.passage_id
         WHERE qf.question_id = OLD.question_id
    ) THEN
        UPDATE questions
           SET status = 'rejected',
               rejected_reason = 'source_changed',
               release_id = NULL,
               status_changed_at = now()
         WHERE id = OLD.question_id
           AND status <> 'rejected';
    ELSE
        DELETE FROM questions WHERE id = OLD.question_id;
    END IF;
    RETURN NULL;
END;
$$;
"""


def upgrade() -> None:
    """Locks the fact, and the question, before the check."""
    op.execute(
        _FACT.format(
            lock="    PERFORM 1 FROM facts WHERE id = OLD.fact_id FOR UPDATE;\n"
        )
    )
    op.execute(
        _QUESTION.format(
            lock="    PERFORM 1 FROM questions WHERE id = OLD.question_id FOR UPDATE;\n"
        )
    )


def downgrade() -> None:
    """Decides without a lock again."""
    op.execute(_FACT.format(lock=""))
    op.execute(_QUESTION.format(lock=""))
