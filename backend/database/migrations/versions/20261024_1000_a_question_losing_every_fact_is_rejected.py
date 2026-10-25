"""A question left with no fact is rejected, not deleted.

`delete_question_without_facts` deleted a question whose last fact went, and
with it every follow-up (`follows_id` cascades). A re-chunk or a re-extraction
replaces facts, so it deleted accepted, reviewed and released questions
whatever their status. It now rejects every question that loses a fact as
`source_changed`, clears its release and keeps the row, its id and its
verdict; a thread trigger takes its follow-ups out of the release. A person
deleting a document, or what was derived from it, deletes that document's
questions explicitly, before the cascade runs. A question left with no fact
keeps no link to its document, so `questions.source_digests` records the
documents a deleted passage or fact belonged to (BEFORE DELETE triggers on
`passages`, `facts` and `fact_passages`, while the document is still known) and the
explicit delete finds the question by it.

Revision: 4a7c2e91d3b8
Parent:   7a41c9d2e8b0
Created:  2026-10-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

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


_STAMP_PASSAGE = """
CREATE OR REPLACE FUNCTION stamp_questions_with_passage_document() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE questions q
       SET source_digests = coalesce(q.source_digests, '{}') || OLD.doc_sha256
     WHERE q.id IN (
               SELECT qf.question_id
                 FROM question_facts qf
                 JOIN fact_passages fp ON fp.fact_id = qf.fact_id
                WHERE fp.passage_id = OLD.id)
       AND NOT coalesce(q.source_digests, '{}') @> ARRAY[OLD.doc_sha256];
    RETURN OLD;
END;
$$;
"""

_STAMP_FACT = """
CREATE OR REPLACE FUNCTION stamp_questions_with_fact_documents() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    digest char(64);
BEGIN
    FOR digest IN
        SELECT DISTINCT p.doc_sha256
          FROM fact_passages fp
          JOIN passages p ON p.id = fp.passage_id
         WHERE fp.fact_id = OLD.id
    LOOP
        UPDATE questions q
           SET source_digests = coalesce(q.source_digests, '{}') || digest
         WHERE q.id IN (SELECT qf.question_id FROM question_facts qf WHERE qf.fact_id = OLD.id)
           AND NOT coalesce(q.source_digests, '{}') @> ARRAY[digest];
    END LOOP;
    RETURN OLD;
END;
$$;
"""

_STAMP_CITATION = """
CREATE OR REPLACE FUNCTION stamp_questions_with_citation_document() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    digest char(64);
BEGIN
    SELECT p.doc_sha256 INTO digest FROM passages p WHERE p.id = OLD.passage_id;
    IF digest IS NOT NULL THEN
        UPDATE questions q
           SET source_digests = coalesce(q.source_digests, '{}') || digest
         WHERE q.id IN (SELECT qf.question_id FROM question_facts qf WHERE qf.fact_id = OLD.fact_id)
           AND NOT coalesce(q.source_digests, '{}') @> ARRAY[digest];
    END IF;
    RETURN OLD;
END;
$$;
"""

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
    """Rejects the question whatever is left of its facts, and stamps its documents."""
    op.add_column(
        "questions",
        sa.Column(
            "source_digests",
            ARRAY(sa.CHAR(64)),
            nullable=True,
            comment="The digests of the documents a source of this question was "
            "taken from, set by a trigger when a passage or a fact it rested on is "
            "deleted. NULL while it keeps every source. A question left with no "
            "fact keeps no link to its document through question_facts; this is "
            "what deleting the document finds it by.",
        ),
    )
    op.execute(_STAMP_PASSAGE)
    op.execute(_STAMP_FACT)
    op.execute(
        "CREATE TRIGGER passages_stamp_questions BEFORE DELETE ON passages "
        "FOR EACH ROW EXECUTE FUNCTION stamp_questions_with_passage_document()"
    )
    op.execute(
        "CREATE TRIGGER facts_stamp_questions BEFORE DELETE ON facts "
        "FOR EACH ROW EXECUTE FUNCTION stamp_questions_with_fact_documents()"
    )
    op.execute(_STAMP_CITATION)
    op.execute(
        "CREATE TRIGGER fact_passages_stamp_questions BEFORE DELETE ON fact_passages "
        "FOR EACH ROW EXECUTE FUNCTION stamp_questions_with_citation_document()"
    )
    op.execute(_FUNCTION.format(body=_REJECTS))
    op.execute(f"COMMENT ON TABLE questions IS '{_COMMENT}'")


def downgrade() -> None:
    """Deletes a question left with no fact again, and drops the stamp."""
    op.execute("DROP TRIGGER fact_passages_stamp_questions ON fact_passages")
    op.execute("DROP FUNCTION stamp_questions_with_citation_document()")
    op.execute("DROP TRIGGER facts_stamp_questions ON facts")
    op.execute("DROP TRIGGER passages_stamp_questions ON passages")
    op.execute("DROP FUNCTION stamp_questions_with_fact_documents()")
    op.execute("DROP FUNCTION stamp_questions_with_passage_document()")
    op.drop_column("questions", "source_digests")
    op.execute(_FUNCTION.format(body=_DELETES))
    op.execute(f"COMMENT ON TABLE questions IS '{_OLD_COMMENT}'")
