"""The embed pass reads the questions that carry no vector, and only those."""

from __future__ import annotations

import pytest
from seed import question
from sqlalchemy.orm import Session

from database.qa_generator import Question
from extraction.repository import FactCatalog

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("language", "text"),
    [
        ("de", "Wie lange dauert eine Überweisung?"),
        ("en", "How long does a refund take?"),
        ("fr", "Quel est le délai de remboursement ?"),
        ("el", "Πόσο διαρκεί μια μεταφορά χρημάτων;"),
    ],
)
def test_a_question_with_no_vector_is_read_and_written_and_one_with_a_vector_is_not(
    engine, database, language: str, text: str
) -> None:
    """What a restore leaves, and what the embed pass then fills."""
    with Session(engine) as session:
        bare = question(question_text=text, language=language)
        held = question(question_text="Already embedded?", embedding=[0.1] * 1024)
        session.add_all([bare, held])
        session.commit()
        bare_id, held_id = bare.id, held.id
    catalog = FactCatalog()

    assert catalog.unembedded_questions(10) == [(bare_id, text)]

    assert catalog.embed_questions([(bare_id, [0.2] * 1024)]) == 1
    assert catalog.unembedded_questions(10) == []
    with Session(engine) as session:
        assert session.get(Question, held_id).embedding is not None  # type: ignore[union-attr]
