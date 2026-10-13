"""The fact_passages table."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.qa_generator.base import Base

#: A citation is written whole or not at all, and reads forwards.
CITATION_COMPLETE = (
    "(sentence_ids IS NULL AND evidence_start IS NULL AND evidence_end IS NULL) "
    "OR (sentence_ids IS NOT NULL AND evidence_start IS NOT NULL "
    "AND evidence_end IS NOT NULL AND evidence_end >= evidence_start)"
)

if TYPE_CHECKING:
    from database.qa_generator.facts import Fact
    from database.qa_generator.passages import Passage


class FactPassage(Base):
    """Which passages a fact rests on, and where in each.

    One row per passage for every kind: one for an atomic fact, a summary and
    an outline, two or more for a bridge. The only route from a fact to a
    passage, and so to a document and to a topic.
    """

    __tablename__ = "fact_passages"
    __table_args__ = (
        CheckConstraint(CITATION_COMPLETE, name="fact_passages_citation_complete"),
        {
            "comment": "Which passages a fact rests on and where in each, one row "
            "per passage for every kind. The only route from a fact to a passage."
        },
    )

    fact_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("facts.id", ondelete="CASCADE"),
        primary_key=True,
        comment="The fact.",
    )
    passage_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("passages.id", ondelete="CASCADE"),
        primary_key=True,
        # The primary key indexes (fact_id, passage_id), which is no help to
        # the lookup by passage_id alone that re-extraction runs.
        index=True,
        comment="A passage the claim rests on. Deleting the passage deletes this "
        "row, and a trigger deletes the fact if it is a bridge or cites no other "
        "passage.",
    )
    position: Mapped[int] = mapped_column(
        Integer,
        comment="Where this passage sat in what the model was shown, from 0. "
        "0 for the one passage of an atomic fact, a summary or an outline. A "
        "higher one on any of those is a citation an earlier version's "
        "duplicate refusal added to the fact it repeated.",
    )
    sentence_ids: Mapped[list[int] | None] = mapped_column(
        ARRAY(Integer),
        comment="Which of this passage's sentences the claim rests on. NULL when "
        "the claim named no sentence this passage has: a refused fact, or a "
        "bridge drawn before prompt version 2. Neither is offered to question "
        "generation.",
    )
    evidence_start: Mapped[int | None] = mapped_column(
        Integer,
        comment="Offset of the cited span's first character within this passage's "
        "text. NULL alongside sentence_ids.",
    )
    evidence_end: Mapped[int | None] = mapped_column(
        Integer, comment="Offset one past its last character."
    )

    fact: Mapped[Fact] = relationship(back_populates="passage_links")
    passage: Mapped[Passage] = relationship(back_populates="fact_links")


#: Deletes a fact once a passage it rests on is gone. Re-chunking cascades
#: to this table and not to the fact, and a foreign key cascades parent to
#: child and never the reverse, so without this a claim outlives its evidence.
#:
#: A bridge goes on any citation: its spans are the whole of what it rests
#: on, so losing one is losing part of the claim. Any other fact goes on its
#: last: a further citation is one an earlier version's duplicate refusal
#: added, and the fact still rests on its own. Re-entrant by
#: construction - the cascade from facts back into this table fires it again,
#: and the second firing finds no fact to delete.
#:
#: Locks the fact before deciding, so of two deletions at once the second
#: waits for the first and sees its citation gone.
#:
#: Declared here, beside the table it belongs to. The migrations carry
#: their own copy, and tests/integration/database/test_schema.py checks the
#: installed body against this one.
DELETE_ORPHAN_FUNCTION = """
CREATE OR REPLACE FUNCTION delete_fact_without_passage() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM facts WHERE id = OLD.fact_id FOR UPDATE;
    DELETE FROM facts f
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
