"""A running head naming the chapter that opens mid-page leaves the text above it in its chapter."""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of


def on(page: int, top: float = 100.0) -> ProvenanceItem:
    """Provenance on one page, a line high."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=54, t=top, r=500, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


@pytest.mark.parametrize(
    ("chap_a", "chap_b", "sec", "line", "opening"),
    [
        (
            "A Privatkunden",
            "B Geschäftskunden",
            "1.3 Sparkonten",
            "Sparkonten werden mit 1,5 % p.a. verzinst.",
            "Das Geschäftskonto kostet 12,90 EUR im Monat.",
        ),
        (
            "A Versand",
            "B Rückgabe",
            "1.3 Express",
            "Expressversand kostet 9,90 EUR pro Bestellung.",
            "Retouren sind innerhalb von 30 Tagen kostenlos.",
        ),
        (
            "A Delivery",
            "B Returns",
            "1.3 Express",
            "Express delivery costs 9.90 EUR per order.",
            "Returns are free within 30 days of receipt.",
        ),
        (
            "A Personal",
            "B Business",
            "1.3 Savings",
            "Savings earn 1.5% a year.",
            "A business account costs 12.90 EUR a month.",
        ),
    ],
)
def test_text_above_a_chapter_opening_mid_page_keeps_its_old_chapter(
    chap_a, chap_b, sec, line, opening
) -> None:
    """A running head naming the page's last chapter must not refile the top."""
    document = DoclingDocument(name="t")
    for page in range(1, 5):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    heads = {1: chap_a, 2: chap_a, 3: chap_b, 4: chap_b}
    for page, chapter in heads.items():
        document.add_text(
            label=DocItemLabel.PAGE_HEADER,
            text=chapter,
            prov=on(page, 20),
            content_layer=ContentLayer.FURNITURE,
        )
    document.add_heading(text=chap_a, level=1, prov=on(1, 60))
    document.add_heading(text=sec, level=2, prov=on(2, 60))
    document.add_text(label=DocItemLabel.TEXT, text="Filler on 2.", prov=on(2, 80))
    document.add_text(label=DocItemLabel.TEXT, text=line, prov=on(3, 60))
    document.add_heading(text=chap_b, level=1, prov=on(3, 400))
    document.add_text(label=DocItemLabel.TEXT, text=opening, prov=on(3, 430))
    document.add_text(label=DocItemLabel.TEXT, text="More B.", prov=on(4, 80))

    _, chunks = chunks_of(document, word_chunker(200), "en")

    held = [c for c in chunks if line in c.text]
    assert held, [c.text for c in chunks]
    for chunk in held:
        assert chap_b not in (chunk.meta.headings or []), chunk.meta.headings
        assert chap_a in (chunk.meta.headings or []), chunk.meta.headings
