"""A question left with no fact is rejected, not deleted.

`delete_question_without_facts` deleted a question whose last fact went, and
with it every follow-up (`follows_id` cascades). A re-chunk or a re-extraction
replaces facts, so it deleted accepted, reviewed and released questions
whatever their status. It now rejects every question that loses a fact as
`source_changed`, clears its release and keeps the row, its id and its
verdict; a thread trigger takes its follow-ups out of the release. A person
deleting a document, or what was derived from it, deletes that document's
questions explicitly, before the cascade runs.

Revision: 4a7c2e91d3b8
Parent:   7a41c9d2e8b0
Created:  2026-10-24
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "4a7c2e91d3b8"
down_revision: str | None = "7a41c9d2e8b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION = """
CREATE OR REPLACE FUNCTION delete_question_without_facts() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM questions WHERE id = OLD.question_id FOR UPDATE;
{body}
    RETURN NULL;
END;
$$;
"""

_REJECTS = """    UPDATE questions
       SET status = 'rejected',
           rejected_reason = 'source_changed',
           release_id = NULL,
           status_changed_at = now()
     WHERE id = OLD.question_id
       AND status <> 'rejected';"""

_DELETES = """    IF EXISTS (
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
    END IF;"""


_COMMENT = (
    "The test questions themselves. Append-only: rejected questions are the "
    "drop-rate evidence in the coverage report. Losing a fact, the last one "
    "included, rejects the question as source_changed and keeps it: a foreign "
    "key cannot cascade that direction, so an AFTER DELETE trigger on "
    "question_facts does it. Only deleting a document, or what was derived "
    "from it, deletes its questions."
)

_OLD_COMMENT = (
    "The test questions themselves. Append-only and never hard-deleted: "
    "rejected questions are the drop-rate evidence in the coverage report. "
    "Deleting every fact a question came from also deletes the question: a "
    "foreign key cannot cascade that direction, so an AFTER DELETE trigger on "
    "question_facts does it."
)


def upgrade() -> None:
    """Rejects the question whatever is left of its facts."""
    op.execute(_FUNCTION.format(body=_REJECTS))
    op.execute(f"COMMENT ON TABLE questions IS '{_COMMENT}'")


def downgrade() -> None:
    """Deletes a question left with no fact again."""
    op.execute(_FUNCTION.format(body=_DELETES))
    op.execute(f"COMMENT ON TABLE questions IS '{_OLD_COMMENT}'")
