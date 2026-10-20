"""Which stored bridges a narrowed pass clears, and which pairs it must not repeat.

`clear_bridges(within)` and `bridged_pairs()` are queries, and a mutant in a
query is only caught by running it. The container these normally run in is
not needed for the three columns they read, so the tables are built by hand
in an in-memory SQLite database, `DOMINANT` (a Postgres `DISTINCT ON`) is a
plain table, and the real statements run against them.

A bridge opens on its position-0 passage; a scoped pass reads the heads of
the topics that hold a selected passage, so those are the bridges it can
write back, and any bridge opening elsewhere stays however its partners are
placed.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import (
    BigInteger,
    Column,
    MetaData,
    Table,
    create_engine,
    insert,
    text,
)
from sqlalchemy.orm import sessionmaker

from database.qa_generator import FactKind, Passage
from extraction import repository

_DDL = (
    "CREATE TABLE passages (id INTEGER PRIMARY KEY, doc_sha256 TEXT NOT NULL)",
    "CREATE TABLE facts (id INTEGER PRIMARY KEY, kind TEXT NOT NULL)",
    (
        "CREATE TABLE fact_passages (fact_id INTEGER, passage_id INTEGER,"
        " position INTEGER, PRIMARY KEY (fact_id, passage_id))"
    ),
)


class World:
    """A corpus of passages in documents and topics, and the bridges on it."""

    def __init__(self) -> None:
        self.engine = create_engine("sqlite://")
        dominant = Table(
            "dominant",
            MetaData(),
            Column("passage_id", BigInteger, primary_key=True),
            Column("topic_id", BigInteger),
        )
        self.dominant = dominant
        with self.engine.begin() as connection:
            for statement in _DDL:
                connection.execute(text(statement))
            dominant.create(connection)
        catalog = repository.FactCatalog.__new__(repository.FactCatalog)
        catalog._session = sessionmaker(self.engine)
        catalog._version = None
        self.catalog = catalog

    def passages(self, placed: dict[int, tuple[str, int]]) -> None:
        """Each passage id with the document it sits in and its dominant topic."""
        with self.engine.begin() as connection:
            for ident, (document, topic) in placed.items():
                connection.execute(
                    text("INSERT INTO passages VALUES (:i, :d)"),
                    {"i": ident, "d": document},
                )
                connection.execute(
                    insert(self.dominant).values(passage_id=ident, topic_id=topic)
                )

    def facts(self, rows: dict[int, tuple[str, tuple[int, ...]]]) -> None:
        """Each fact id with its kind and the passages it rests on, in position order."""
        with self.engine.begin() as connection:
            for ident, (kind, rests) in rows.items():
                connection.execute(
                    text("INSERT INTO facts VALUES (:i, :k)"), {"i": ident, "k": kind}
                )
                for position, passage in enumerate(rests):
                    connection.execute(
                        text("INSERT INTO fact_passages VALUES (:f, :p, :n)"),
                        {"f": ident, "p": passage, "n": position},
                    )

    def selected(self, within) -> set[int]:
        """The bridge ids a pass narrowed by `within` replaces."""
        with self.engine.begin() as connection:
            return set(connection.execute(repository._bridges(within)).scalars().all())

    def left(self) -> set[int]:
        """The ids of the facts still stored."""
        with self.engine.begin() as connection:
            return set(connection.execute(text("SELECT id FROM facts")).scalars())


@contextmanager
def built(placed=None, facts=None):
    """A World with `DOMINANT` swapped for its plain table, closed on the way out."""
    with pytest.MonkeyPatch.context() as patch:
        made = World()
        patch.setattr(repository, "DOMINANT", made.dominant)
        try:
            if placed:
                made.passages(placed)
            if facts:
                made.facts(facts)
            yield made
        finally:
            made.engine.dispose()


@pytest.fixture
def world():
    """An empty World."""
    with built() as made:
        yield made


BRIDGE = FactKind.BRIDGE.value
ATOMIC = FactKind.ATOMIC.value


def in_document(name: str):
    """A scope selecting the passages of one document."""
    return Passage.doc_sha256 == name


# ── Examples: a bank's two documents, a shop's two ────────────────────────


def test_a_scoped_clear_keeps_a_bridge_opening_in_another_topic(world) -> None:
    """The bridge rests on a passage of the scope, but opens where the pass does not read."""
    world.passages({1: ("fees", 1), 2: ("fees", 1), 3: ("cards", 2), 4: ("cards", 2)})
    world.facts(
        {
            10: (BRIDGE, (1, 3)),  # opens in topic 1, rests on topic 2
            11: (BRIDGE, (3, 1)),  # opens in topic 2, rests on the scope's passage
            12: (ATOMIC, (1,)),
        }
    )

    assert world.selected(in_document("fees")) == {10}
    assert world.catalog.clear_bridges(in_document("fees")) == 1
    assert world.left() == {11, 12}


def test_a_scoped_clear_takes_the_bridges_of_the_whole_topic_of_the_scope(
    world,
) -> None:
    """The pass reads a topic whole, so a bridge opening on its other passage is replaced too."""
    world.passages({1: ("shop", 1), 2: ("returns", 1), 3: ("returns", 2)})
    world.facts({10: (BRIDGE, (2, 3)), 11: (BRIDGE, (3, 2))})

    assert world.selected(in_document("shop")) == {10}


def test_an_unscoped_clear_takes_every_bridge_and_only_bridges(world) -> None:
    """Atomic and summary facts of the same passages stay."""
    world.passages({1: ("a", 1), 2: ("b", 2)})
    world.facts(
        {
            10: (BRIDGE, (1, 2)),
            11: (BRIDGE, (2, 1)),
            12: (ATOMIC, (1,)),
            13: ("summary", (2,)),
        }
    )

    assert world.catalog.clear_bridges() == 2
    assert world.left() == {12, 13}


def test_a_scope_matching_no_passage_clears_nothing(world) -> None:
    """No selected passage, no topic read, no bridge replaced."""
    world.passages({1: ("a", 1)})
    world.facts({10: (BRIDGE, (1,))})

    assert world.catalog.clear_bridges(in_document("nowhere")) == 0
    assert world.left() == {10}


# ── bridged_pairs ─────────────────────────────────────────────────────────


def test_bridged_pairs_are_the_first_two_passages_of_each_bridge_unordered(
    world,
) -> None:
    """A third passage of a group is not part of the pair a link was offered as."""
    world.passages({1: ("a", 1), 2: ("a", 1), 3: ("b", 2), 4: ("b", 2)})
    world.facts(
        {
            10: (BRIDGE, (1, 2, 3)),
            11: (BRIDGE, (4, 3)),
            12: (ATOMIC, (1, 2)),
            13: ("summary", (3, 4)),
        }
    )

    assert world.catalog.bridged_pairs() == frozenset(
        {frozenset({1, 2}), frozenset({3, 4})}
    )


def test_two_bridges_on_one_pair_make_one_pair(world) -> None:
    """Opened from either side, it is the same pair."""
    world.passages({1: ("a", 1), 2: ("b", 2)})
    world.facts({10: (BRIDGE, (1, 2)), 11: (BRIDGE, (2, 1))})

    assert world.catalog.bridged_pairs() == frozenset({frozenset({1, 2})})


def test_no_bridge_is_no_pair(world) -> None:
    """A plain fact on two passages is not a bridge."""
    world.passages({1: ("a", 1)})
    world.facts({10: (ATOMIC, (1,))})

    assert world.catalog.bridged_pairs() == frozenset()


# ── Properties ────────────────────────────────────────────────────────────

DOCS = ("a", "b", "c")


@st.composite
def corpora(draw):
    """Passages with a document and a topic each, and bridges and plain facts on them."""
    size = draw(st.integers(2, 9))
    placed = {
        ident: (draw(st.sampled_from(DOCS)), draw(st.integers(1, 4)))
        for ident in range(1, size + 1)
    }
    ids = list(placed)
    facts = {}
    for ident in range(100, 100 + draw(st.integers(0, 10))):
        kind = draw(st.sampled_from([BRIDGE, BRIDGE, ATOMIC, "summary"]))
        rests = draw(
            st.lists(st.sampled_from(ids), min_size=1, max_size=3, unique=True)
        )
        facts[ident] = (kind, tuple(rests))
    return placed, facts


def _opening(facts):
    return {i: rests[0] for i, (kind, rests) in facts.items() if kind == BRIDGE}


def _within(chosen):
    return Passage.doc_sha256.in_(sorted(chosen))


@settings(max_examples=150, deadline=None)
@given(corpus=corpora(), chosen=st.sets(st.sampled_from(DOCS), min_size=1))
def test_a_scoped_clear_never_takes_a_bridge_opening_outside_the_topics_it_reads(
    corpus, chosen
) -> None:
    """Bridges opening on a topic holding a selected passage go, and no other."""
    placed, facts = corpus
    read = {topic for doc, topic in placed.values() if doc in chosen}
    with built(placed, facts) as world:
        got = world.selected(_within(chosen))

    expected = {i for i, first in _opening(facts).items() if placed[first][1] in read}
    assert got == expected


@settings(max_examples=150, deadline=None)
@given(corpus=corpora(), chosen=st.sets(st.sampled_from(DOCS), min_size=1))
def test_a_scoped_clear_deletes_what_it_selects_and_nothing_else(
    corpus, chosen
) -> None:
    """The bridges it skips and every plain fact are still there afterwards."""
    placed, facts = corpus
    with built(placed, facts) as world:
        going = world.selected(_within(chosen))
        removed = world.catalog.clear_bridges(_within(chosen))
        left = world.left()

    assert removed == len(going)
    assert left == set(facts) - going
    assert all(facts[i][0] == BRIDGE for i in going)


@settings(max_examples=100, deadline=None)
@given(corpus=corpora(), chosen=st.sets(st.sampled_from(DOCS), min_size=1))
def test_widening_a_scope_never_spares_a_bridge_the_narrower_one_took(
    corpus, chosen
) -> None:
    """The whole corpus takes every bridge, and a scope inside it takes no more."""
    placed, facts = corpus
    with built(placed, facts) as world:
        narrow = world.selected(_within(chosen))
        wide = world.selected(_within(set(DOCS)))
        unscoped = world.selected(None)

    assert narrow <= wide <= unscoped
    assert unscoped == set(_opening(facts))
    assert wide == unscoped


@settings(max_examples=100, deadline=None)
@given(corpus=corpora())
def test_bridged_pairs_are_exactly_the_leading_pairs_of_the_bridges(corpus) -> None:
    """Whichever order the pair was offered in, and never a plain fact's."""
    placed, facts = corpus
    with built(placed, facts) as world:
        got = world.catalog.bridged_pairs()

    assert got == frozenset(
        frozenset(rests[:2]) for kind, rests in facts.values() if kind == BRIDGE
    )
