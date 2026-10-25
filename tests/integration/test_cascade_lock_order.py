"""Two passages read again at once reach the same facts in opposite order.

The orphan triggers lock each fact as the DELETE reaches its citation, in the
order the rows are stored. Two transactions that hold the same facts through
two passages, stored in opposite orders, each hold one and wait for the
other's: Postgres kills one with `deadlock_detected`. `store` locks every
fact and question its deletion will reach in id order first, so the
triggers' own locks find them already held.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from facts import FactStore
from seed import fact
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.qa_generator import FactPassage

pytestmark = pytest.mark.integration

#: Facts both passages cite, and how many times the race is run. Enough
#: citations that each transaction is still deleting when the other starts.
FACTS = 150
ROUNDS = 20


@pytest.fixture
def store(engine, database):
    """A fact driver on the migrated database."""
    return FactStore(engine)


def shared(store, engine, passages: tuple[int, int]) -> None:
    """Facts each passage cites, the second's citations stored in reverse."""
    first, second = passages
    with Session(engine) as session:
        drawn = [fact(first, statement=f"Claim {n}.") for n in range(FACTS)]
        session.add_all(drawn)
        session.flush()
        ids = [one.id for one in drawn]
        for fact_id in reversed(ids):
            session.add(
                FactPassage(
                    fact_id=fact_id,
                    passage_id=second,
                    position=1,
                    sentence_ids=[0],
                    evidence_start=0,
                    evidence_end=0,
                )
            )
        session.commit()


@pytest.mark.parametrize("language", ["de", "en"])
def test_two_passages_replaced_at_once_do_not_deadlock(
    store, engine, language: str
) -> None:
    """Each round both passages lose every citation; no transaction is killed."""
    store.language = language
    seed = f"race-{language}"
    first, second = store.corpus((seed, ["One.", "Two."]))[seed]

    for _ in range(ROUNDS):
        shared(store, engine, (first, second))

        gate = Barrier(2)

        def replace(passage_id: int, gate: Barrier) -> int:
            gate.wait()
            return store.store(passage_id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(replace, one, gate) for one in (first, second)]
            for each in results:
                each.result(timeout=60)

        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM facts")).scalar_one() == 0
            )
