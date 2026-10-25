"""A document of single pages with two numbers per page is not a spread.

It prints its page number in the foot and a sheet or Bates number in the
head; a bare value in a margin stays text.
"""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.common.reference import ProvenanceItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of

BODY = {
    "de": "Rückgabefrist (Tage):",
    "en": "Return period (days):",
}
HEAD = {"de": "Blatt", "en": "Sheet"}


def at(page: int, top: float, left: float) -> ProvenanceItem:
    """A box of the page at this position."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=left, t=top, r=left + 20, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def dual(language: str, value: str, pages: int = 20, on: int = 15) -> DoclingDocument:
    """Pages with a head sheet number and a foot page number, and a margin value."""
    document = DoclingDocument(name="dual")
    for page in range(1, pages + 1):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    for page in range(1, pages + 1):
        document.add_text(
            label=DocItemLabel.PAGE_HEADER,
            text=f"{HEAD[language]} {page + 100}",
            prov=at(page, 30, 450),
            content_layer=ContentLayer.FURNITURE,
        )
        document.add_text(
            label=DocItemLabel.PAGE_FOOTER,
            text=str(page),
            prov=at(page, 810, 290),
            content_layer=ContentLayer.FURNITURE,
        )
    document.add_text(
        label=DocItemLabel.TEXT, text=BODY[language], prov=at(on, 770, 54)
    )
    document.add_text(label=DocItemLabel.TEXT, text=value, prov=at(on, 790, 54))
    return document


@pytest.mark.parametrize("language", sorted(BODY))
@pytest.mark.parametrize("value", ["25", "14", "3"])
def test_a_margin_value_of_a_dual_numbered_document_stays(language, value) -> None:
    """A value such as 25 under a label is text, not a page number."""
    _, chunks = chunks_of(dual(language, value), word_chunker(200), language)
    text = "\n".join(chunk.text for chunk in chunks)
    assert value in text.split()
