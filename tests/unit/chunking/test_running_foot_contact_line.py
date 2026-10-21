"""A body line opening with the running foot's name is passage text."""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of


def on(page: int, top: float = 100.0, left: float = 54) -> ProvenanceItem:
    """Provenance on one page, a line high."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=left, t=top, r=500, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def pages(count: int) -> DoclingDocument:
    """An empty document of `count` A4 pages."""
    document = DoclingDocument(name="t")
    for page in range(1, count + 1):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    return document


def texts(document: DoclingDocument, language: str, budget: int = 200) -> str:
    """Every chunk's text, joined."""
    _, chunks = chunks_of(document, word_chunker(budget), language)
    return "\n".join(chunk.text for chunk in chunks)


@pytest.mark.parametrize(
    ("lang", "foot", "line", "needle"),
    [
        (
            "de",
            "Musterbank AG | Seite {page}",
            "Musterbank AG | Kundenservice: 0800 123 456 | Mo-Fr 8-20 Uhr",
            "0800 123 456",
        ),
        (
            "en",
            "Shop Ltd | Page {page}",
            "Shop Ltd | Customer service: 0800 123 456 | returns@shop.example",
            "returns@shop.example",
        ),
    ],
)
def test_a_contact_line_opening_with_the_running_name_stays_body_text(
    lang, foot, line, needle
) -> None:
    """Only a paragraph that is the running item, or it plus page numbers, is furniture."""
    document = pages(3)
    for page in (1, 2, 3):
        document.add_text(
            label=DocItemLabel.PAGE_FOOTER,
            text=foot.format(page=page),
            prov=on(page, 800),
            content_layer=ContentLayer.FURNITURE,
        )
    document.add_heading(text="Kontakt", level=1, prov=on(3, 50))
    document.add_text(label=DocItemLabel.TEXT, text=line, prov=on(3, 100))

    assert needle in texts(document, lang)
