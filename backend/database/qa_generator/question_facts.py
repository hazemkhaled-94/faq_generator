"""The question_facts table."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.qa_generator.base import Base

if TYPE_CHECKING:
    from database.qa_generator.facts import Fact
    from database.qa_generator.questions import Question


class QuestionFact(Base):
    """Which facts a question was generated from.

    One row for an ordinary question, two or more for a cross-document one.
    The passages a question needs retrieved are reached from here through
    fact_passages rather than stored.
    """

    __tablename__ = "question_facts"
    __table_args__ = (
        {
            "comment": "Which facts a question was generated from. One row for an "
            "ordinary question, two or more for a cross-document question. The "
            "passages a question needs retrieved are derived from here through "
            "fact_passages rather than stored separately."
        },
    )

    question_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
        comment="The question.",
    )
    fact_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("facts.id", ondelete="CASCADE"),
        primary_key=True,
        # The primary key indexes (question_id, fact_id), which is no help
        # to the lookup by fact_id alone that the cascade runs.
        index=True,
        comment="A fact the question tests. Deleting the fact removes this row; "
        "see the note on the questions table about questions left with no facts.",
    )

    question: Mapped[Question] = relationship(back_populates="fact_links")
    fact: Mapped[Fact] = relationship(back_populates="question_links")


#: Rejects a question that loses a fact as `source_changed`, clearing its
#: release, unless it is rejected already; it never deletes one, whatever is
#: left of its facts. What a person deletes (a document, or what was derived
#: from it) deletes its questions first, through `ingestion.repository`. A
#: foreign key cascades parent to child, never the reverse. Does nothing to
#: a question that is itself being deleted. Locks the question before deciding, so of
#: two deletions at once the second waits for the first and sees its fact
#: gone.
#:
#: Declared here, beside the table it belongs to. The migrations carry
#: their own copy, and tests/integration/database/test_schema.py checks the
#: installed body against this one.
DELETE_ORPHAN_FUNCTION = """
CREATE OR REPLACE FUNCTION delete_question_without_facts() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM questions WHERE id = OLD.question_id FOR UPDATE;
    UPDATE questions
       SET status = 'rejected',
           rejected_reason = 'source_changed',
           release_id = NULL,
           status_changed_at = now()
     WHERE id = OLD.question_id
       AND status <> 'rejected';
    RETURN NULL;
END;
$$;
"""
