"""A sheet that prints two page numbers is read as a spread.

Where each PDF page is a two-page spread, the printed numbers run two for each
page, so the offset from a page's number to its printed ones changes with the
page: the offsets are read per printed page, not once for the document.
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
    "de": "Das Konto wird mit Ablauf der Frist geschlossen.",
    "en": "The account is closed when the notice period ends.",
}


def at(page: int, top: float, left: float) -> ProvenanceItem:
    """A short line on a page, with a top-left origin."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=left, t=top, r=left + 20, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def spread(language: str, sheets: int = 6, per_sheet: int = 2) -> DoclingDocument:
    """Sheets whose feet the converter read, then one whose numbers it read as text.

    Sheet `p` prints `per_sheet * p` and the next numbers; the last sheet's
    numbers are body paragraphs in the foot margin, as on a full-page photo.
    """
    document = DoclingDocument(name="spread")
    for page in range(1, sheets + 1):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    for page in range(1, sheets):
        for part in range(per_sheet):
            document.add_text(
                label=DocItemLabel.PAGE_FOOTER,
                text=str(per_sheet * page + part),
                prov=at(page, 800, 100 + 300 * part),
                content_layer=ContentLayer.FURNITURE,
            )
    document.add_text(label=DocItemLabel.TEXT, text=BODY[language], prov=at(1, 100, 54))
    for part in range(per_sheet):
        document.add_text(
            label=DocItemLabel.TEXT,
            text=str(per_sheet * sheets + part),
            prov=at(sheets, 800, 100 + 300 * part),
        )
    return document


def cut(document: DoclingDocument, language: str) -> str:
    """Every chunk's text, joined."""
    _, chunks = chunks_of(document, word_chunker(200), language)
    return "\n".join(chunk.text for chunk in chunks)


@pytest.mark.parametrize("language", sorted(BODY))
def test_both_numbers_of_a_spread_are_dropped(language: str) -> None:
    """12 and 13 on sheet 6: the offsets of the sheets before do not hold."""
    text = cut(spread(language), language)

    assert text == BODY[language]


@pytest.mark.parametrize("language", sorted(BODY))
def test_a_document_of_single_pages_is_read_as_before(language: str) -> None:
    """One number a page: the offset is constant."""
    text = cut(spread(language, per_sheet=1), language)

    assert text == BODY[language]


def test_a_number_that_belongs_to_no_page_stays() -> None:
    """A figure in the foot margin that no sheet prints is text."""
    document = spread("en")
    document.add_text(label=DocItemLabel.TEXT, text="87", prov=at(3, 810, 54))

    assert "87" in cut(document, "en")
