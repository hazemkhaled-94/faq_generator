"""Writes decided on a reading taken earlier."""

from __future__ import annotations

import pytest
from seed import digest, document, fact, fitted, membership, passage, question
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.qa_generator import QuestionFact
from question_generation.catalog import QuestionCatalog

pytestmark = pytest.mark.integration


@pytest.fixture
def accepted(engine, database):
    """One accepted question (a shop's returns window), its id."""
    with Session(engine) as session:
        sha = digest("a")
        session.add(document(sha))
        held = fitted(0)
        session.add(held)
        session.flush()
        at = passage(
            sha, ordinal=1, text="Orders can be returned within 14 days.", language="en"
        )
        session.add(at)
        session.flush()
        session.add(membership(at.id, held.id))
        drawn = fact(at.id, statement="Orders can be returned within 14 days.")
        session.add(drawn)
        session.flush()
        asked = question(
            question_text="Within how many days can an order be returned?",
            target_answer="14 days",
            answerable=True,
            difficulty="easy",
            question_type="factoid",
            status="accepted",
        )
        session.add(asked)
        session.flush()
        session.add(QuestionFact(question_id=asked.id, fact_id=drawn.id))
        session.commit()
        return asked.id


def row(engine, id):
    with engine.connect() as c:
        return c.execute(
            text(
                "SELECT status, reviewed_verdict, release_id FROM questions WHERE id = :i"
            ),
            {"i": id},
        ).one()


def test_releasing_a_question_rejected_since_the_draw_does_not_crash(accepted, engine):
    """qg-check-7: a reviewer rejects a drawn id while the twin rounds run."""
    catalog = QuestionCatalog()
    ids = [one.id for one in catalog.releasable()]
    assert ids == [accepted]
    catalog.decide(accepted, "rejected")

    _, written = catalog.release(
        ids
    )  # BASE: CHECK questions_released_is_accepted raises

    assert written == 0
    assert row(engine, accepted).release_id is None


THREADS = [
    ("en", ["Which orders ship free?", "And how fast?", "And returns?"]),
    (
        "de",
        [
            "Welche Bestellungen versenden Sie kostenlos?",
            "Und wie schnell?",
            "Und Rückgaben?",
        ],
    ),
]


@pytest.mark.parametrize("language,turns", THREADS)
def test_a_follow_up_whose_root_was_rejected_since_the_draw_is_not_released(
    engine, database, language, turns
) -> None:
    """A thread cut in the middle by the race releases nothing below the cut."""
    with Session(engine) as session:
        sha = digest("thread")
        session.add(document(sha))
        held = fitted(0, language=language)
        session.add(held)
        session.flush()
        at = passage(sha, ordinal=1, text=turns[0], language=language)
        session.add(at)
        session.flush()
        session.add(membership(at.id, held.id))
        drawn = fact(at.id, statement=turns[0])
        session.add(drawn)
        session.flush()
        made = []
        for position, said in enumerate(turns, 1):
            made.append(
                question(
                    question_text=said,
                    language=language,
                    status="accepted",
                    difficulty="easy",
                    question_type="factoid",
                    follows_id=made[-1].id if made else None,
                    thread_position=position,
                    kind="needs_both" if position == 1 else "single",
                )
            )
            session.add(made[-1])
            session.flush()
            session.add(QuestionFact(question_id=made[-1].id, fact_id=drawn.id))
        session.commit()
        first, second, third = (one.id for one in made)
    catalog = QuestionCatalog()
    ids = [one.id for one in catalog.releasable()]
    assert ids == [first, second, third]
    catalog.decide(second, "rejected")  # the middle turn, after the draw

    _, written = catalog.release(ids)

    assert written == 1
    assert row(engine, first).release_id is not None
    assert row(engine, third).release_id is None
