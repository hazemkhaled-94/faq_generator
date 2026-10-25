"""Crossing threads: a root on one passage with its follow-up on another, and the reverse, deleted or replaced at once."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from facts import FactStore
from seed import digest, document, fact, link, passage, question
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

#: Crossing threads per round, and rounds.
PAIRS = 20
ROUNDS = 8


def threads(session, on_a: list, on_b: list) -> None:
    """Writes, per pair, a thread rooted on A with its follow-up on B and the reverse."""
    drawn = uuid.uuid4()
    for n in range(PAIRS):
        for root_on, follow_on in ((on_a[n], on_b[n]), (on_b[n], on_a[n])):
            root = question(status="accepted", release_id=drawn)
            session.add(root)
            session.flush()
            follow = question(
                status="accepted",
                release_id=drawn,
                follows_id=root.id,
                thread_position=2,
                question_text="And then?",
            )
            session.add(follow)
            session.flush()
            session.add_all([link(root.id, root_on.id), link(follow.id, follow_on.id)])


def raced(first, second) -> list[str]:
    """Runs two callables at once behind a gate, and names what killed them."""
    gate = Barrier(2)
    killed: list[str] = []

    def run(call) -> None:
        gate.wait()
        call()

    with ThreadPoolExecutor(max_workers=2) as pool:
        for each in [pool.submit(run, one) for one in (first, second)]:
            try:
                each.result(timeout=60)
            except Exception as exc:  # noqa: BLE001
                killed.append(type(exc).__name__ + ": " + str(exc).splitlines()[0])
    return killed


def test_two_reextractions_of_crossing_threads_do_not_deadlock(
    engine, database
) -> None:
    """The thread trigger also takes a rejected root's follow-ups, so they are locked too."""
    store = FactStore(engine)
    store.language = "en"
    first, second = store.corpus(("cross", ["One.", "Two."]))["cross"]
    killed: list[str] = []
    for _ in range(ROUNDS):
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM questions"))
            connection.execute(text("DELETE FROM facts"))
        with Session(engine) as session:
            on_a = [fact(first, statement=f"Claim A {n}.") for n in range(PAIRS)]
            on_b = [fact(second, statement=f"Claim B {n}.") for n in range(PAIRS)]
            session.add_all(on_a + on_b)
            session.flush()
            threads(session, on_a, on_b)
            session.commit()
        killed += raced(lambda: store.store(first), lambda: store.store(second))
    assert not killed, killed


def test_two_document_deletions_with_crossing_threads_do_not_deadlock(
    engine, database
) -> None:
    """Root on A with its follow-up on B, and the other way round; delete A and B at once."""
    from ingestion.repository import DocumentRepository

    killed: list[str] = []
    for round_ in range(6):
        a, b = digest(f"cross-a-{round_}"), digest(f"cross-b-{round_}")
        with Session(engine) as session:
            session.add_all([document(a), document(b)])
            session.flush()
            pa, pb = passage(a, text="Eins."), passage(b, text="Two.")
            session.add_all([pa, pb])
            session.flush()
            on_a = [fact(pa.id, statement=f"A {n}.") for n in range(PAIRS)]
            on_b = [fact(pb.id, statement=f"B {n}.") for n in range(PAIRS)]
            session.add_all(on_a + on_b)
            session.flush()
            threads(session, on_a, on_b)
            session.commit()
        killed += raced(
            lambda a=a: DocumentRepository().delete(a),
            lambda b=b: DocumentRepository().delete(b),
        )
    assert not killed, killed
