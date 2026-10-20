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
        """Returns the bridge fact, opening on the first offered passage."""
        ids = [p.id for p in offered]
        return checked(ids[0], "Bridge.", kind=FactKind.BRIDGE, passage_ids=ids)


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
