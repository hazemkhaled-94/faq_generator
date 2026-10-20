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


def row(engine, one):
    """The status, verdict and release of one question."""
    with engine.connect() as c:
        return c.execute(
            text(
                "SELECT status, reviewed_verdict, release_id FROM questions WHERE id = :i"
            ),
            {"i": one},
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


def test_a_stale_recheck_does_not_overrule_a_person_who_accepted(accepted, engine):
    """qg-check-8: reject() writes a gate verdict over reviewed_verdict=accepted."""
    catalog = QuestionCatalog()
    catalog.decide(accepted, "accepted")
    assert row(engine, accepted).reviewed_verdict == "accepted"

    changed = catalog.reject(
        [(accepted, "duplicate")]
    )  # the reading predates the person's decision

    assert changed == 0
    assert row(engine, accepted).status == "accepted"


def test_a_stale_recheck_still_rejects_a_source_that_changed_under_a_person(
    accepted, engine
):
    """source_changed may overrule a person: the fact the answer rests on is gone."""
    catalog = QuestionCatalog()
    catalog.decide(accepted, "accepted")

    assert catalog.reject([(accepted, "source_changed")]) == 1
    assert row(engine, accepted).status == "rejected"


TOPICS = [
    (
        "en",
        "Goods may be returned within 30 days.",
        "How long may goods be returned?",
        "30 days",
        "Delivery takes 3 working days.",
    ),
    (
        "de",
        "Waren dürfen innerhalb von 30 Tagen zurückgegeben werden.",
        "Wie lange dürfen Waren zurückgegeben werden?",
        "30 Tage",
        "Die Lieferung dauert 3 Werktage.",
    ),
]


@pytest.mark.parametrize("lang,returns,asked,answer,delivery", TOPICS)
def test_a_fact_deleted_while_a_topic_is_written_keeps_the_other_questions(
    engine, database, locking, lang, returns, asked, answer, delivery
):
    """database-6: one cited fact gone between the read and store() costs one thread."""
    from ingestion.repository import DocumentRepository
    from question_generation.models import CheckedQuestion, criteria_of
    from question_generation.queue import QuestionQueue

    a, b = digest("shop-returns"), digest("shop-delivery")
    with Session(engine) as session:
        session.add_all([document(a), document(b)])
        held = fitted(0)
        session.add(held)
        session.flush()
        pa = passage(a, ordinal=1, language=lang, text=returns)
        pb = passage(b, ordinal=1, language=lang, text=delivery)
        session.add_all([pa, pb])
        session.flush()
        session.add_all([membership(pa.id, held.id), membership(pb.id, held.id)])
        fa, fb = fact(pa.id, statement=returns), fact(pb.id, statement=delivery)
        session.add_all([fa, fb])
        session.commit()
        topic_id, fact_a, fact_b = held.id, fa.id, fb.id
    queue = QuestionQueue()
    queue.start()
    queue.claim()

    def checked(text_, ans, fid):
        return CheckedQuestion(
            question_text=text_,
            target_answer=ans,
            answerable=True,
            criteria=criteria_of(
                passages=1, documents=1, topics=1, answer_chars=len(ans)
            ),
            language=lang,
            status="accepted",
            rejected_reason=None,
            fact_ids=(fid,),
            embedding=[0.1] * 1024,
        )

    DocumentRepository().delete(b)  # the reading predates this
    written = queue.store(
        topic_id,
        [
            [checked(asked, answer, fact_a)],
            [checked("?" + asked, answer, fact_b)],
        ],
    )

    with engine.connect() as c:
        kept = c.execute(text("SELECT question_text FROM questions")).scalars().all()
    assert written == 1
    assert kept == [asked]
    assert locking and all("ORDER BY" in one for one in locking), locking
