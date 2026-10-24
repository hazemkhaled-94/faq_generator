"""Two extraction drains over one database keep one copy of a claim.

The dedup probe reads what is committed. Two workers that each probed before
either stored both found no twin and both kept the claim, so a second extract
replica produced duplicates the gate exists to refuse. `store` now takes a
lock per (language, kind) and probes again inside it, which sees what the
other worker committed.
"""

from __future__ import annotations

import threading

import pytest
from facts import FactStore
from test_fact_store import _reading

from database.qa_generator import Rejection
from extraction.repository import PassageQueue

pytestmark = pytest.mark.integration

#: The same claim in two documents, by language: a bank's fee in German, a
#: shop's return period in English.
CLAIMS = {
    "de": "Bestellungen können innerhalb von 14 Tagen zurückgegeben werden.",
    "en": "Orders can be returned within 14 days.",
}


def _after_the_first_probe(queue: PassageQueue, barrier: threading.Barrier) -> None:
    """Holds a worker, once, until the other has probed too.

    Both have then read the corpus before either has stored, which is the
    interleaving two drains reach by chance.
    """
    probe = queue.nearest_fact
    waited = False

    def nearest(*args, **kwargs):
        nonlocal waited
        found = probe(*args, **kwargs)
        if not waited:
            waited = True
            barrier.wait(timeout=30)
        return found

    queue.nearest_fact = nearest  # type: ignore[method-assign]


@pytest.mark.parametrize("language", ["de", "en"])
def test_two_workers_storing_twin_claims_keep_one(engine, database, language) -> None:
    """Exactly one is validated; the other is refused as the first's duplicate."""
    store = FactStore(engine, language=language)
    text = CLAIMS[language]
    written = store.corpus(("x", [text]), ("y", [text]))
    first, other = written["x"][0], written["y"][0]
    store.queued(first, other)
    barrier = threading.Barrier(2)
    queues = [PassageQueue(), PassageQueue()]
    for queue in queues:
        _after_the_first_probe(queue, barrier)
    answer = {"facts": [{"sentences": [0], "statement": text}]}
    services = [_reading(store, answer, queue) for queue in queues]
    errors: list[BaseException] = []

    def drain(service) -> None:
        try:
            service.process_next()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=drain, args=(one,)) for one in services]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    rows = store.rows("id", "validated", "rejection_code", "validation_error")
    assert len(rows) == 2, rows
    kept = [row for row in rows if row[1]]
    refused = [row for row in rows if not row[1]]
    assert len(kept) == 1 and len(refused) == 1, rows
    assert refused[0][2] == Rejection.DUPLICATE
    assert f"fact {kept[0][0]} already says" in refused[0][3], refused[0][3]


def test_twins_of_different_kinds_do_not_wait_on_each_other(engine, database) -> None:
    """One lock per (language, kind): a summary and an atomic fact take two."""
    from sqlalchemy import text

    store = FactStore(engine)
    with engine.connect() as one, engine.connect() as two:
        one.execute(text("SELECT pg_advisory_xact_lock(hashtext('en:atomic'))"))
        got = two.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext('en:summary'))")
        ).scalar()
    assert got is True
    assert store.rows("id") == []
