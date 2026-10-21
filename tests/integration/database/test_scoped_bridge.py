"""A narrowed bridge pass must not delete a bridge it cannot write back."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from facts import FactStore, checked

from database.qa_generator import FactKind, Passage
from extraction.service import bridge

pytestmark = pytest.mark.integration

#: Three passages: the first and second are siblings under one heading, the
#: second names the section the third opens. The full pass offers (1, 2) and
#: (2, 3); a pass narrowed to the second's topic reads the second and third
#: as heads and must leave (1, 2), headed outside, where it is.
CASES = {
    ("bank", "en"): (
        [
            "A dormant account is charged a yearly fee of 10 EUR.",
            "A replacement card costs 5 EUR, as Section 9 explains.",
            "A transfer abroad costs 1 EUR.",
        ],
        ["Fees > Yearly fees", "Fees > Card fees", "Section 9 > Transfers"],
    ),
    ("bank", "de"): (
        [
            "Für ein ruhendes Konto wird eine Jahresgebühr von 10 EUR erhoben.",
            "Eine Ersatzkarte kostet 5 EUR, wie Abschnitt 9 erläutert.",
            "Eine Auslandsüberweisung kostet 1 EUR.",
        ],
        [
            "Gebühren > Jahresgebühren",
            "Gebühren > Kartengebühren",
            "Abschnitt 9 > Überweisungen",
        ],
    ),
    ("shop", "en"): (
        [
            "Standard delivery costs 4 EUR within the country.",
            "Express delivery costs 9 EUR, as Section 4 explains.",
            "Returns are free within 30 days.",
        ],
        ["Delivery > Standard", "Delivery > Express", "Section 4 > Returns"],
    ),
    ("shop", "de"): (
        [
            "Der Standardversand kostet 4 EUR im Inland.",
            "Der Expressversand kostet 9 EUR, wie Abschnitt 4 erläutert.",
            "Rücksendungen sind innerhalb von 30 Tagen kostenlos.",
        ],
        ["Versand > Standard", "Versand > Express", "Abschnitt 4 > Rücksendungen"],
    ),
}


class Extractor:
    """Proposes one candidate for every link it is offered."""

    provenance = None

    def extract(self, offered, link, facts):
        """Returns a candidate standing for the offered passages."""
        return [SimpleNamespace(ids=[p.id for p in offered])]


class Checker:
    """Accepts a candidate as a bridge resting on the offered passages."""

    def check_bridge(self, offered, candidate, provenance):
        """Returns the bridge fact, opening on the first offered passage.

        With the reading every bridge prompt 6 or later writes, refused ones too.
        """
        ids = [p.id for p in offered]
        return checked(
            ids[0],
            "Bridge.",
            kind=FactKind.BRIDGE,
            passage_ids=ids,
            bridge={"relation": "parallel", "question": "Q?", "answer": "A"},
        )


@pytest.mark.parametrize(("domain", "language"), list(CASES))
def test_a_scoped_pass_keeps_a_bridge_opening_outside_its_scope(
    engine, database, domain, language
) -> None:
    """Narrowing to the second passage keeps the bridge the first opens."""
    texts, paths = CASES[(domain, language)]
    store = FactStore(engine, language=language)
    first, second, third = store.corpus((domain, texts))[domain]
    for pid, path, text in zip((first, second, third), paths, texts, strict=True):
        store._execute(
            "UPDATE passages SET section_path = :p WHERE id = :i", p=path, i=pid
        )
        store.store(pid, checked(pid, text))
        store.topic(f"t{pid}", pid)

    bridge(store.catalog, Extractor(), Checker(), 12, 2)
    full = set(_pairs(store))
    assert (first, second) in full
    assert (second, third) in full

    bridge(store.catalog, Extractor(), Checker(), 12, 2, Passage.id == second)
    scoped = _pairs(store)
    assert (first, second) in scoped, f"lost by the narrowed pass: {scoped}"
    assert sorted(scoped) == sorted(set(scoped)), "no bridge is written twice"


#: First and second are siblings; the first also names the third's section,
#: so its own best link is that reference and the second heads the sibling
#: pair, which shows the earlier passage, the first, at position 0.
HEADED = {
    ("bank", "en"): (
        [
            "A dormant account is charged a yearly fee of 10 EUR, as Section 9 explains.",
            "A replacement card costs 5 EUR.",
            "A transfer abroad costs 1 EUR.",
        ],
        ["Fees > Yearly fees", "Fees > Card fees", "Section 9 > Transfers"],
    ),
    ("shop", "de"): (
        [
            "Der Standardversand kostet 4 EUR im Inland, wie Abschnitt 4 erläutert.",
            "Der Expressversand kostet 9 EUR.",
            "Rücksendungen sind innerhalb von 30 Tagen kostenlos.",
        ],
        ["Versand > Standard", "Versand > Express", "Abschnitt 4 > Rücksendungen"],
    ),
}


@pytest.fixture(params=list(HEADED))
def headed(request, engine, database):
    """Three passages in three topics, and the full pass already run."""
    domain, language = request.param
    texts, paths = HEADED[request.param]
    store = FactStore(engine, language=language)
    ids = store.corpus((domain, texts))[domain]
    topics = []
    for pid, path, text in zip(ids, paths, texts, strict=True):
        store._execute(
            "UPDATE passages SET section_path = :p WHERE id = :i", p=path, i=pid
        )
        store.store(pid, checked(pid, text))
        topics.append(store.topic(f"t{pid}", pid))
    bridge(store.catalog, Extractor(), Checker(), 12, 2)
    first, second, third = ids
    full = set(_pairs(store))
    assert (first, second) in full
    assert (first, third) in full
    return store, ids, topics


def test_a_scoped_pass_keeps_a_sibling_bridge_headed_outside_it(headed) -> None:
    """Narrowing to the first passage keeps the bridge the second headed."""
    store, (first, second, _), _ = headed
    bridge(store.catalog, Extractor(), Checker(), 12, 2, Passage.id == first)
    scoped = _pairs(store)
    assert (first, second) in scoped, f"lost by the narrowed pass: {scoped}"
    assert sorted(scoped) == sorted(set(scoped)), "no bridge is written twice"


def test_the_topic_of_a_bridges_head_holds_a_bridge(headed) -> None:
    """A MISSING=1 pass leaves the second's topic: it heads the sibling bridge."""
    store, _, (first, second, _) = headed
    assert store.catalog.bridged_topics() == {first, second}


def _pairs(store) -> list[tuple[int, ...]]:
    """The passages each bridge rests on, in the order it shows them."""
    rows = store._execute(
        "SELECT fact_id, passage_id FROM fact_passages fp "
        "JOIN facts f ON f.id = fp.fact_id WHERE f.kind = :k "
        "ORDER BY fact_id, position",
        k=FactKind.BRIDGE,
    )
    by: dict[int, list[int]] = {}
    for fact, passage in rows:
        by.setdefault(fact, []).append(passage)
    return [tuple(sorted(v)) for v in by.values()]


PAIRS = {
    ("bank", "en"): (
        [
            "A dormant account is charged a yearly fee of 10 EUR.",
            "A replacement card costs 5 EUR.",
        ],
        ["Fees > Yearly fees", "Fees > Card fees"],
    ),
    ("bank", "de"): (
        [
            "Für ein ruhendes Konto wird eine Jahresgebühr von 10 EUR erhoben.",
            "Eine Ersatzkarte kostet 5 EUR.",
        ],
        ["Gebühren > Jahresgebühren", "Gebühren > Kartengebühren"],
    ),
    ("shop", "en"): (
        [
            "Standard delivery costs 4 EUR within the country.",
            "Express delivery costs 9 EUR.",
        ],
        ["Delivery > Standard", "Delivery > Express"],
    ),
    ("shop", "de"): (
        [
            "Der Standardversand kostet 4 EUR im Inland.",
            "Der Expressversand kostet 9 EUR.",
        ],
        ["Versand > Standard", "Versand > Express"],
    ),
}


@pytest.fixture(params=list(PAIRS))
def two(request, engine, database):
    """Two sibling passages in two topics, and the full pass already run."""
    domain, language = request.param
    texts, paths = PAIRS[request.param]
    store = FactStore(engine, language=language)
    first, second = store.corpus((domain, texts))[domain]
    for pid, path, text in zip((first, second), paths, texts, strict=True):
        store._execute(
            "UPDATE passages SET section_path = :p WHERE id = :i", p=path, i=pid
        )
        store.store(pid, checked(pid, text))
        store.topic(f"t{pid}", pid)
    bridge(store.catalog, Extractor(), Checker(), 12, 2)
    assert _pairs(store) == [(first, second)]
    return store, first, second


@pytest.mark.parametrize("scope", ["first", "second"])
def test_a_scoped_pass_does_not_offer_a_pair_that_holds_a_bridge(two, scope) -> None:
    """A sibling bridge opens on the earlier passage, whichever heads it."""
    store, first, second = two
    kept = first if scope == "first" else second
    bridge(store.catalog, Extractor(), Checker(), 12, 2, Passage.id == kept)
    assert len(_pairs(store)) == 1


def test_a_second_missing_pass_does_not_bridge_a_pair_again(two) -> None:
    """`make corpus` twice: the second head of a bridged pair offers it again."""
    store, _, _ = two
    bridge(store.catalog, Extractor(), Checker(), 12, 2, missing=True)
    assert len(_pairs(store)) == 1
