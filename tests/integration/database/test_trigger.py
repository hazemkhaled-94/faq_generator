"""The triggers that reject a question, or delete a fact, once a source is gone.

A foreign key cascades parent to child, never the reverse, so a question
losing its facts needs a trigger. It rejects the question and keeps it, the
last fact included: what a person asked to delete is deleted with its
questions by the repository, never by this trigger.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from contextlib import suppress

import pytest
from seed import digest, document, fact, link, passage, question
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


@pytest.fixture
def written(engine, database):
    """A question drawn from however many facts a test asks for."""

    def write(facts: int = 1):
        with Session(engine) as session:
            session.add(document())
            session.flush()
            held = passage(digest())
            session.add(held)
            session.flush()
            drawn = [fact(held.id, statement=f"Claim {n}.") for n in range(facts)]
            session.add_all(drawn)
            asked = question()
            session.add(asked)
            session.flush()
            session.add_all(link(asked.id, one.id) for one in drawn)
            session.commit()
            return asked.id, [one.id for one in drawn]

    return write


def counts(engine) -> tuple[int, int]:
    """How many questions and links are left."""
    with engine.connect() as connection:
        return (
            connection.execute(text("SELECT count(*) FROM questions")).scalar_one(),
            connection.execute(
                text("SELECT count(*) FROM question_facts")
            ).scalar_one(),
        )


def rejected(engine) -> list[tuple]:
    """Every question's status, reason and release."""
    with engine.connect() as connection:
        return [
            tuple(row)
            for row in connection.execute(
                text("SELECT status, rejected_reason, release_id FROM questions")
            )
        ]


def test_deleting_the_only_fact_rejects_the_question(written, engine) -> None:
    """The question stays, as evidence, and says why it cannot be asked."""
    _, facts = written(1)

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM facts WHERE id = :id"), {"id": facts[0]})

    assert counts(engine) == (1, 0)
    assert rejected(engine) == [("rejected", "source_changed", None)]


def test_deleting_one_of_two_facts_keeps_the_question(written, engine) -> None:
    """A cross-document question still has a source."""
    _, facts = written(2)

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM facts WHERE id = :id"), {"id": facts[0]})

    assert counts(engine) == (1, 1)


def test_deleting_the_last_of_two_facts_rejects_the_question(written, engine) -> None:
    """The trigger fires per row, and the guard decides."""
    _, facts = written(2)

    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM facts WHERE id = ANY(:ids)"), {"ids": facts}
        )

    assert counts(engine) == (1, 0)


def test_deleting_the_passage_rejects_the_question(written, engine) -> None:
    """Through the facts: passage to fact cascades, fact to question triggers."""
    written(2)

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM passages"))

    assert counts(engine) == (1, 0)


def test_deleting_the_document_takes_the_chain_but_not_the_question(
    written, engine
) -> None:
    """One delete at the top takes every fact; the question is the repository's."""
    written(3)

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM documents"))

    assert counts(engine) == (1, 0)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM facts")).scalar() == 0


def test_a_question_with_no_facts_at_all_is_left_alone(written, engine) -> None:
    """The trigger fires on a deleted link, not on a question that had none."""
    _, facts = written(1)
    with Session(engine) as session:
        session.add(question())
        session.commit()

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM facts WHERE id = :id"), {"id": facts[0]})

    assert counts(engine) == (2, 0)


def _at_once(engine, statement: str, first: dict, second: dict) -> None:
    """Runs a statement in two transactions, the second begun before the first ends.

    The second runs in a thread while the first is still open, and the first
    commits while the second is running or waiting on it.
    """
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        with engine.begin() as opened:
            opened.execute(text(statement), first)

            def other() -> None:
                with engine.begin() as connection:
                    connection.execute(text(statement), second)

            running = pool.submit(other)
            with suppress(FuturesTimeout):
                running.result(timeout=1)
        running.result(timeout=10)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def test_two_deletions_at_once_still_reject_a_question_left_with_no_fact(
    written, engine
) -> None:
    """Each takes one of its two facts; neither may see the other's still there."""
    _, facts = written(2)

    _at_once(
        engine, "DELETE FROM facts WHERE id = :id", {"id": facts[0]}, {"id": facts[1]}
    )

    assert counts(engine) == (1, 0)
    assert rejected(engine) == [("rejected", "source_changed", None)]


def test_two_deletions_at_once_still_delete_a_fact_left_with_no_citation(
    engine, database
) -> None:
    """Each takes one of its two citations; neither may see the other's there."""
    with Session(engine) as session:
        session.add(document())
        session.flush()
        cited = [passage(digest(), ordinal=n) for n in (1, 2)]
        session.add_all(cited)
        session.flush()
        session.add(fact(cited[0].id, cited[1].id))
        session.commit()
        first, second = (one.id for one in cited)

    _at_once(
        engine,
        "DELETE FROM fact_passages WHERE passage_id = :id",
        {"id": first},
        {"id": second},
    )

    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM facts")).scalar() == 0
