"""A figure-only value whose digits equal a page number is body text, not a heading."""

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
    ("heading", "label", "value", "lang"),
    [
        ("Entgelte", "Kontoführung im Monat", "5 €", "de"),
        ("Entgelte", "Sollzins für Überziehungen", "2,5 %", "de"),
        ("Versandkosten", "Standardversand", "4 €", "de"),
        ("Fees", "Standard delivery", "£5", "en"),
        ("Fees", "Restocking fee", "2.5%", "en"),
        ("Gebühren", "Ersatzkarte", "3 EUR", "de"),
        ("Fees", "Gift card", "$4", "en"),
    ],
)
def test_a_price_equal_to_a_page_number_is_not_a_heading(
    heading, label, value, lang
) -> None:
    """The value stays body text; no chunk is headed by it."""
    document = DoclingDocument(name="t")
    for page in range(1, 31):
        document.add_page(page_no=page, size=Size(width=595, height=842))
        document.add_text(
            label=DocItemLabel.PAGE_FOOTER,
            text=str(page),
            prov=on(page, 800),
            content_layer=ContentLayer.FURNITURE,
        )
    document.add_heading(text=heading, level=1, prov=on(3, 50))
    document.add_text(label=DocItemLabel.TEXT, text=label, prov=on(3, 100))
    document.add_text(label=DocItemLabel.TEXT, text=value, prov=on(3, 160))
    document.add_text(
        label=DocItemLabel.TEXT, text="Gift wrapping 4.95", prov=on(3, 220)
    )

    _, chunks = chunks_of(document, word_chunker(200), lang)

    assert not any(value in (c.meta.headings or []) for c in chunks), [
        c.meta.headings for c in chunks
    ]
    assert any(value in c.text for c in chunks)
