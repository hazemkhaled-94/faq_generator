"""frontend-review-6: a document filter must choose questions, not trim what they cite."""

from __future__ import annotations

import pytest
from seed import digest, document, fact, passage, question
from sqlalchemy.orm import Session

from database.qa_generator import QuestionFact
from question_generation.catalog import QuestionCatalog

pytestmark = pytest.mark.integration


def test_a_document_filter_keeps_every_fact_of_a_cross_document_question(
    engine, database
) -> None:
    """A fee schedule A and terms B (or a price list and returns policy): one fact each."""
    with Session(engine) as session:
        session.add_all([document(digest("a")), document(digest("b"))])
        session.flush()
        here = passage(digest("a"), ordinal=1, language="de")
        there = passage(digest("b"), ordinal=1, language="de")
        session.add_all([here, there])
        session.flush()
        fee, term = (
            fact(here.id, statement="Die Gebuehr betraegt 5 EUR."),
            fact(there.id, statement="Widerspruch binnen sechs Wochen."),
        )
        session.add_all([fee, term])
        session.flush()
        asked = question(
            question_text="Gebuehr und Widerspruchsfrist?", status="accepted"
        )
        session.add(asked)
        session.flush()
        session.add_all(
            [QuestionFact(question_id=asked.id, fact_id=f.id) for f in (fee, term)]
        )
        session.commit()

    _, unfiltered = QuestionCatalog().page()
    _, filtered = QuestionCatalog().page(document=digest("a"))

    assert unfiltered[0].facts == 2
    assert filtered[0].facts == 2, (
        f"filtered by A: facts={filtered[0].facts} documents={filtered[0].documents}"
    )
    assert sorted(filtered[0].statements) == sorted(unfiltered[0].statements)
    assert len(filtered[0].documents) == 2
