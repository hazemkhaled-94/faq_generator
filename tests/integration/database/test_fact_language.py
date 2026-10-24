"""A fact's language, written when it is stored, and the dedup probe on it.

The probe narrows the nearest-neighbour search to the candidate's language.
Read through the passage and document a fact cites, that narrowing was a
subquery the planner joined first, so the HNSW index was never used: a
nested loop over every citation and an exact sort, a probe a corpus ten times
the size could not afford. A column on the fact itself is a filter the index
scan applies as it goes.
"""

from __future__ import annotations

import re

import pytest
from facts import FactStore, checked
from sqlalchemy import event, text

from database.qa_generator import FactKind
from database.qa_generator import engine as app_engine

pytestmark = pytest.mark.integration


@pytest.fixture
def store(engine, database) -> FactStore:
    """A driver on the empty, migrated database."""
    return FactStore(engine)


def _axis(at: int) -> list[float]:
    """A unit vector along one axis of the column's width."""
    return [1.0 if i == at else 0.0 for i in range(1024)]


def test_a_fact_is_stored_in_its_passage_s_language(store) -> None:
    """The passage's own, the document's where it is too short to tell, any code."""
    written = store.corpus(
        ("bank", ["Die Karte kostet 25 Euro im Jahr.", "Kurz."]),
        ("shop", ["Orders can be returned within 14 days."]),
        ("other", ["Les retours sont acceptes sous 14 jours."]),
    )
    german, short = written["bank"]
    (english,) = written["shop"]
    (french,) = written["other"]
    store.language_of(german, "de")
    store.language_of(short, None)
    store.language_of(french, "fr")

    for passage in (german, short, english, french):
        store.store(passage, checked(passage, f"A claim about {passage}."))

    assert store.rows("language", where="statement LIKE :a", a=f"%{german}.") == [
        ("de",)
    ]
    assert store.rows("language", where="statement LIKE :a", a=f"%{short}.") == [
        ("en",)
    ]
    assert store.rows("language", where="statement LIKE :a", a=f"%{english}.") == [
        ("en",)
    ]
    assert store.rows("language", where="statement LIKE :a", a=f"%{french}.") == [
        ("fr",)
    ]


def test_a_bridge_is_stored_in_its_head_passage_s_language(store) -> None:
    """The first passage it rests on, as the probe has always read it."""
    written = store.corpus(("a", ["Eins.", "Zwei."]))
    first, other = written["a"]
    store.language_of(first, "de")

    store.bridges(
        checked(first, "Eine Brücke.", kind=FactKind.BRIDGE, passage_ids=[first, other])
    )

    assert store.rows("language") == [("de",)]


def _probe_plan(store, **narrowed) -> str:
    """The plan Postgres chooses for one dedup probe, as the code sends it."""
    sent: list[tuple[str, object]] = []

    def watch(connection, cursor, statement, parameters, *rest) -> None:
        if "cosine" in statement or "<=>" in statement:
            sent.append((statement, parameters))

    sending = app_engine()
    event.listen(sending, "before_cursor_execute", watch)
    try:
        store.queue.nearest_fact(_axis(0), **narrowed)
    finally:
        event.remove(sending, "before_cursor_execute", watch)
    statement, parameters = sent[-1]
    with store.engine.connect() as connection:
        connection.execute(text("SET enable_seqscan = off"))
        rows = connection.exec_driver_sql("EXPLAIN " + statement, parameters)
        plan = "\n".join(row[0] for row in rows)
    # The probe's vector is 1024 numbers, which say nothing about the plan.
    return re.sub(r"'\[[^']*\]'::vector", "'[...]'::vector", plan)


def test_the_probe_in_a_language_reads_the_vector_index(store) -> None:
    """EXPLAIN names the HNSW index and no join over the citations."""
    written = store.corpus(("a", ["One claim.", "Another claim."]))
    first, other = written["a"]
    store.store(first, checked(first, "A claim.", embedding=_axis(0)))
    store.store(other, checked(other, "Another.", embedding=_axis(1)))

    plan = _probe_plan(store, language="en")

    assert "ix_facts_embedding_hnsw" in plan, plan
    assert "fact_passages" not in plan, plan
    assert "documents" not in plan, plan


def test_the_probe_still_finds_the_twin_in_its_own_language_only(store) -> None:
    """The same vector in two languages: each probe returns its own."""
    written = store.corpus(
        ("a", ["Die Karte kostet 25 Euro.", "The card costs 25 EUR."])
    )
    german, english = written["a"]
    store.language_of(german, "de")
    store.store(
        german, checked(german, "Die Karte kostet 25 Euro.", embedding=_axis(0))
    )
    store.store(english, checked(english, "The card costs 25 EUR.", embedding=_axis(0)))

    in_german = store.queue.nearest_fact(_axis(0), language="de")
    in_english = store.queue.nearest_fact(_axis(0), language="en")
    in_french = store.queue.nearest_fact(_axis(0), language="fr")
    anywhere = store.queue.nearest_fact(_axis(0))

    assert in_german is not None and in_german.statement.startswith("Die Karte")
    assert in_english is not None and in_english.statement.startswith("The card")
    assert in_french is None
    assert anywhere is not None


@pytest.mark.parametrize(
    "text, before, after, now",
    [
        # Stored under the fallback, re-read as German by a newly configured model.
        ("Die Karte kostet 25 Euro im Jahr.", "en", "de", "de"),
        ("Orders can be returned within 14 days.", "de", "en", "en"),
        # A language no configuration names behaves like any other.
        ("Zahlungen werden binnen 3 Tagen gebucht.", "de", "xx", "xx"),
        # Too short to tell: the document's, as the store reads it.
        ("Orders can be returned within 14 days.", "de", None, "en"),
    ],
)
def test_a_re_read_that_moves_a_passage_s_language_moves_its_facts(
    store, text, before, after, now
) -> None:
    """`make chunk-revocabulary` rewrites passages.language in place.

    The probe filters on the fact's own copy, so the copy moves with it: the
    fact is found in the new language and no longer in the old one.
    """
    from preprocessing.chunking.repository import PassageCatalog

    written = store.corpus(("moved", [text]), ("kept", ["Another passage here."]))
    (moved,) = written["moved"]
    (kept,) = written["kept"]
    store.language_of(moved, before)
    store.language_of(kept, "fr")
    store.store(moved, checked(moved, text, embedding=_axis(0)))
    store.store(kept, checked(kept, "A kept claim.", embedding=_axis(1)))

    assert PassageCatalog().revocabulary([(moved, after, [])]) == 1

    assert store.queue.nearest_fact(_axis(0), language=now) is not None
    assert store.queue.nearest_fact(_axis(0), language=before) is None
    assert store.rows("language", where="statement = :s", s=text) == [(now,)]
    assert store.rows("language", where="statement = :s", s="A kept claim.") == [
        ("fr",)
    ]
