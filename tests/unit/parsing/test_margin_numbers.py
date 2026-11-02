"""A paragraph number printed in the margin is read before its paragraph.

Regulations and terms number each paragraph in a column beside it. The
converter reads that number after the paragraph's text, so the list item ends
on its own number and the sentence splitter opens the next paragraph on it.
Each test draws a page with pymupdf and builds the item the converter hands
over for it: the text, then the number, in one box that spans both.
"""

from __future__ import annotations

import pymupdf
import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.reference import ProvenanceItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

from preprocessing.parsing.pipelines.pdf import _margined

PARAGRAPHS = {
    "de": ("Die Bank erhebt für jedes Konto ein monatliches Entgelt.", "8.01"),
    "en": ("The bank charges a monthly fee for each account.", "8.01"),
    "fr": ("La banque perçoit des frais mensuels pour chaque compte.", "8.01"),
    "el": ("Η τράπεζα χρεώνει μηνιαίο τέλος για κάθε λογαριασμό.", "8.01"),
}
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"


def page_of(text: str, number: str, *, margin: bool) -> bytes:
    """One line: the number in the margin before the text, or after it."""
    pdf = pymupdf.open()
    page = pdf.new_page(width=595, height=842)
    options = {"fontsize": 11, "fontname": "uni", "fontfile": FONT}
    if margin:
        page.insert_text((40, 100), number, **options)
        page.insert_text((80, 100), text, **options)
    else:
        page.insert_text((80, 100), f"{text} {number}", **options)
    return pdf.tobytes()


def item_of(text: str, left: float) -> DoclingDocument:
    """What the converter hands over: the text, then the number, in one box."""
    document = DoclingDocument(name="regulations")
    document.add_page(page_no=1, size=Size(width=595, height=842))
    document.add_text(
        label=DocItemLabel.TEXT,
        text=text,
        orig=text,
        prov=ProvenanceItem(
            page_no=1,
            bbox=BoundingBox(
                l=left, t=88, r=560, b=102, coord_origin=CoordOrigin.TOPLEFT
            ),
            charspan=(0, len(text)),
        ),
    )
    return document


@pytest.mark.parametrize("language", sorted(PARAGRAPHS))
def test_a_number_in_the_margin_moves_to_the_front_of_its_paragraph(
    language: str,
) -> None:
    """The number printed left of the text is the paragraph's own."""
    text, number = PARAGRAPHS[language]
    document = item_of(f"{text} {number}", 40)

    _margined(document, page_of(text, number, margin=True))

    assert document.texts[0].text == f"{number} {text}"
    assert document.texts[0].orig == f"{number} {text}"


@pytest.mark.parametrize("language", sorted(PARAGRAPHS))
def test_a_number_that_ends_the_printed_line_stays_where_it_is(language: str) -> None:
    """A reference at the end of a sentence is part of it."""
    text, number = PARAGRAPHS[language]
    document = item_of(f"{text} {number}", 80)

    _margined(document, page_of(text, number, margin=False))

    assert document.texts[0].text == f"{text} {number}"
