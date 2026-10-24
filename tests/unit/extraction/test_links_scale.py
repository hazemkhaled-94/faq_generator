"""What the term links cost at ten times this corpus.

A term in a share of a language's passages linked every pair of them, so a
corpus ten times larger had terms in 50 passages and 1,225 links each. The
share is capped at six passages now, and a passage keeps its best partners,
so the links grow with the corpus.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from drivers import passage

from extraction.links import _Edges, _terms, linked

pytestmark = pytest.mark.nlp


def _stub(ident: int, text: str, **kwargs):
    """A passage as the term pass reads it: an id, a text and a vector."""
    return SimpleNamespace(
        id=ident, text=text, embedding=kwargs.pop("embedding", None), **kwargs
    )


def _lemmas(partners) -> dict[int, frozenset[str]]:
    """What each passage is about: here its words, which are no language's."""
    return {p.id: frozenset(p.text.split()) for p in partners}


def _positioned(partners):
    """An `_Edges` that knows where each passage sits in reading order."""
    edges = _Edges()
    edges.position.update({p.id: at for at, p in enumerate(partners)})
    return edges


def test_term_links_grow_linearly_with_the_corpus() -> None:
    """50,000 passages in groups of 40 sharing a term: edges stay under a budget.

    The terms are words of no language: the pass reads a passage's lemmas
    from what the parse of it gave, so the bound holds for any language a
    corpus is in.
    """
    size = 50_000
    partners = [
        _stub(i, f"common group{i // 40} pair{i // 2} own{i}") for i in range(size)
    ]
    edges = _positioned(partners)

    started = time.perf_counter()
    _terms(edges, partners, _lemmas(partners))  # type: ignore[arg-type]

    assert len(edges.found) <= 8 * size, len(edges.found)
    assert time.perf_counter() - started < 20


def test_a_term_in_a_few_passages_links_them_and_one_in_many_does_not() -> None:
    """The share is capped at six passages, whatever the size of the corpus."""
    partners = [
        _stub(i, "rare" if i < 3 else "usual" if i < 43 else f"filler{i}")
        for i in range(10_000)
    ]
    edges = _positioned(partners)

    _terms(edges, partners, _lemmas(partners))  # type: ignore[arg-type]

    named = {link.named for _, link in edges.found.values()}
    assert named == {"rare"}, named
    assert len(edges.found) == 3


@pytest.mark.parametrize(
    ("language", "sheets", "fillers", "term"),
    [
        (
            "en",
            [
                "The backpack is waterproof and weighs 900 g.",
                "The jacket is waterproof up to 10,000 mm.",
                "A waterproof cover is sold separately.",
            ],
            "Orders ship on Monday.",
            "waterproof",
        ),
        (
            "de",
            [
                "Der Rucksack wird mit einer Regenhülle geliefert.",
                "Für die Jacke ist eine Regenhülle erhältlich.",
                "Die Regenhülle schützt das Gepäck vor Nässe.",
            ],
            "Bestellungen werden montags versandt.",
            "regenhülle",
        ),
    ],
)
def test_a_term_in_three_product_sheets_links_them(
    language, sheets, fillers, term
) -> None:
    """With real lemmas, in a shop's words as in a bank's."""
    from dataclasses import replace

    # 420 passages: a share of 0.5% is three, which is what makes a term in three rare.
    texts = [*sheets, *[f"{fillers} {i}" for i in range(420)]]
    passages = [
        replace(
            passage(
                t, language=language, section_path=f"Sheet {i} > Part {i}", id=i + 1
            ),
            doc_sha256=f"doc-{i}",
        )
        for i, t in enumerate(texts)
    ]

    got = linked(passages[:3], passages, {p.id: p.id for p in passages}, 9, 2)

    assert term in {link.named for link in got if link.kind == "term"}
