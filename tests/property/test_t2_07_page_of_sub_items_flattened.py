"""T2-07 (v55/parsing at def56b93 only): a page holding only a list's sub-items, at two levels, is flattened by one.

Green on v55/t2 (18622f09). Drop into tests/property/ of an export of
v55/parsing (git archive) and run with onetest.sh; the committed property is
test_a_list_going_on_over_a_page_keeps_each_items_depth in
tests/property/test_chunk_boundary_invariants.py on v55/t2.
"""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of

#: (page, depth, text): a bank's card-blocking list, its sub-items going on
#: at the top of page 2, both pages at the same 54 pt margin.
BLOCKING = {
    "de": [
        (1, 0, "Die Bank sperrt die Karte, wenn:"),
        (1, 1, "der Karteninhaber es verlangt, oder"),
        (2, 1, "ein Verdacht auf Missbrauch besteht, nämlich:"),
        (2, 2, "eine Zahlung im Ausland ohne Freigabe."),
    ],
    "en": [
        (1, 0, "The bank blocks the card when:"),
        (1, 1, "the holder asks for it, or"),
        (2, 1, "misuse is suspected, namely:"),
        (2, 2, "a payment abroad without approval."),
    ],
}


@pytest.mark.parametrize("language", sorted(BLOCKING))
def test_sub_items_alone_on_the_next_page_keep_their_depth(language) -> None:
    """Both pages share one margin: the page of sub-items alone reads off the edge before."""
    document = DoclingDocument(name="terms")
    for page in (1, 2):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    group = document.add_list_group()
    rows = {1: 0, 2: 0}
    for page, depth, text in BLOCKING[language]:
        left = 54 + 18 * depth
        top = (700 if page == 1 else 60) + 14 * rows[page]
        rows[page] += 1
        document.add_list_item(
            text=text,
            parent=group,
            prov=ProvenanceItem(
                page_no=page,
                bbox=BoundingBox(
                    l=left,
                    t=top,
                    r=left + 200,
                    b=top + 10,
                    coord_origin=CoordOrigin.TOPLEFT,
                ),
                charspan=(0, 1),
            ),
        )
    _, chunks = chunks_of(document, word_chunker(200), language)
    lines = [line for chunk in chunks for line in chunk.text.splitlines()]
    assert [(len(line) - len(line.lstrip())) // 4 for line in lines] == [0, 1, 1, 2], (
        lines
    )
