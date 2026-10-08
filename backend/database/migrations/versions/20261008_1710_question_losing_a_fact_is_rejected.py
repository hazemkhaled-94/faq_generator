"""A question that loses one of its facts is rejected.

`delete_question_without_facts` deleted a question only when its last fact
went, so one that lost one of several kept its answer and its status. It
now rejects such a question as `source_changed`, and still deletes one
left with no fact.

A fact counts as left only while it and a passage it cites still exist.
One statement deleting a document or a passage removes every fact on it
one cascade at a time; counting links alone would reject the question
before deleting it, and its archived copy would lose its status.

Revision: 04419594a51e
Parent:   3fe4226da3b6
Created:  2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "04419594a51e"
down_revision: str | None = "3fe4226da3b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rejects a question left with a fact, deletes one left with none."""
    op.execute(
        """
CREATE OR REPLACE FUNCTION delete_question_without_facts() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
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
    )


def downgrade() -> None:
    """Deletes a question only on its last fact again."""
    op.execute(
        """
CREATE OR REPLACE FUNCTION delete_question_without_facts() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM questions q
     WHERE q.id = OLD.question_id
       AND NOT EXISTS (
           SELECT 1 FROM question_facts qf WHERE qf.question_id = q.id
       );
    RETURN NULL;
END;
$$;
"""
    )
