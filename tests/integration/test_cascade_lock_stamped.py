"""A thread crossing two documents through a question a rerun already left with no fact deadlocks no delete or re-extraction.

Thread 1: Qs (lost its fact on A, stamped A, rejected) <- R_b (on B) follows it.
Thread 2: R_a (on A) <- F_b (on B) follows it.
Ids in creation order: Qs < R_b < R_a < F_b.
Deleting A locks R_a and F_b (reached through A's fact), then deletes Qs by its stamp, which lock_reached never took.
Re-extracting (or deleting) B locks Qs, R_b, R_a, F_b in id order.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from facts import FactStore
from seed import digest, document, fact, link, passage, question
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

ROUNDS = 12


def build(engine, tag: str):
    """Two documents and the crossing threads, with the first question already stamped by a re-extraction of A."""
    a, b = digest(f"x3-lock-a-{tag}"), digest(f"x3-lock-b-{tag}")
    with Session(engine) as session:
        session.add_all([document(a), document(b)])
        session.flush()
        pa, pb = (
            passage(a, text="Die Gebühr beträgt 5 EUR."),
            passage(b, text="The fee is 5 EUR."),
        )
        session.add_all([pa, pb])
        session.flush()
        old, fa = fact(pa.id, statement="Alt."), fact(pa.id, statement="Neu.")
        fb, fb2 = fact(pb.id, statement="B one."), fact(pb.id, statement="B two.")
        session.add_all([old, fa, fb, fb2])
        session.flush()
        qs = question(status="accepted")
        session.add(qs)
        session.flush()
        session.add(link(qs.id, old.id))
        session.commit()
        ids = {
            "pa": pa.id,
            "pb": pb.id,
            "old": old.id,
            "fa": fa.id,
            "fb": fb.id,
            "fb2": fb2.id,
            "qs": qs.id,
        }
    with (
        engine.begin() as c
    ):  # a re-extraction of A's passage took `old`: Qs is rejected and stamped A
        c.execute(
            text("DELETE FROM fact_passages WHERE fact_id = :f"), {"f": ids["old"]}
        )
    with Session(engine) as session:
        rb = question(
            status="accepted",
            follows_id=ids["qs"],
            thread_position=2,
            question_text="And B?",
        )
        session.add(rb)
        session.flush()
        ra = question(status="accepted")
        session.add(ra)
        session.flush()
        fbq = question(
            status="accepted",
            follows_id=ra.id,
            thread_position=2,
            question_text="And then?",
        )
        session.add(fbq)
        session.flush()
        session.add_all(
            [link(rb.id, ids["fb"]), link(ra.id, ids["fa"]), link(fbq.id, ids["fb2"])]
        )
        session.commit()
    with engine.connect() as c:
        stamped = c.execute(
            text("SELECT source_digests FROM questions WHERE id = :q"), {"q": ids["qs"]}
        ).scalar_one()
    assert stamped == [a], stamped
    return a, b, ids


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
                killed.append(
                    type(exc).__name__ + ": " + str(exc).splitlines()[0][:160]
                )
    return killed


@pytest.mark.parametrize("other", ["reextract_b", "delete_b", "delete_derived_b"])
def test_delete_a_beside_a_rerun_or_delete_of_b(engine, database, other) -> None:
    """Deleting A takes the stamped question in the same line as B's lock."""
    from ingestion.repository import DocumentRepository

    store = FactStore(engine)
    killed: list[str] = []
    for n in range(ROUNDS):
        with engine.begin() as c:
            c.execute(
                text(
                    "TRUNCATE documents, passages, facts, questions, question_facts, fact_passages, archived_rows RESTART IDENTITY CASCADE"
                )
            )
        a, b, ids = build(engine, f"{other}-{n}")
        second = {
            "reextract_b": lambda ids=ids: store.store(ids["pb"]),
            "delete_b": lambda b=b: DocumentRepository().delete(b),
            "delete_derived_b": lambda b=b: DocumentRepository().delete_derived(b),
        }[other]
        killed += raced(lambda a=a: DocumentRepository().delete(a), second)
    assert not killed, killed
