"""The text repairs after conversion, on the shapes they meet rarely.

Each repair reads the PDF again with pymupdf and edits the converter's text
by position, so a page whose size the two readers disagree on is one whose
positions cannot be trusted: it is left as the converter wrote it, and a
repair that leaves something in says so.
"""

from __future__ import annotations

import logging

import pymupdf
from docling_core.types.doc.base import Size
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from test_margin_numbers import PARAGRAPHS, item_of, page_of
from test_strikethrough import (
    BASELINE,
    HEIGHT,
    LEFT,
    PRINTED,
    WIDTH,
    box,
    printed,
    provenance,
    raised,
    strike,
)

from preprocessing.parsing.pipelines.pdf import _margined, _rejoined, _unstruck


def resized(document: DoclingDocument, grown: float = 20.0) -> DoclingDocument:
    """The same reading, on a page the converter measured larger."""
    document.pages[1].size = Size(width=WIDTH + grown, height=HEIGHT + grown)
    return document


def reading(text: str, edges: tuple[float, ...]) -> DoclingDocument:
    """A converted page holding one paragraph at `edges`."""
    converted = DoclingDocument(name="t")
    converted.add_page(page_no=1, size=Size(width=WIDTH, height=HEIGHT))
    converted.add_text(label=DocItemLabel.TEXT, text=text, prov=provenance(edges))
    return converted


def test_a_page_the_readers_measure_apart_keeps_its_struck_word_and_says_so(
    caplog,
) -> None:
    """No word is cut by a position that may not be its own."""
    pdf, page = printed((LEFT, BASELINE, PRINTED))
    strike(page, "six")
    converted = resized(reading(PRINTED, box(page, PRINTED)))

    with caplog.at_level(logging.WARNING):
        (item,) = _unstruck(converted, pdf.tobytes()).texts

    assert item.text == PRINTED
    assert "struck-through words on page 1 were left in" in caplog.text


def ordinal_page(before: str, suffix: str, after: str) -> bytes:
    """A one-page PDF printing a number, a raised suffix and the rest."""
    pdf = pymupdf.open()
    page = pdf.new_page(width=WIDTH, height=HEIGHT)
    raised(page, before, suffix, after)
    return pdf.tobytes()


def test_a_page_the_readers_measure_apart_keeps_its_ordinal_as_converted() -> None:
    """The raised suffix stays a word of its own rather than joining a guess."""
    data = ordinal_page("Effective from 1", "st", "July 2026")
    converted = resized(
        reading(
            "Effective from 1 st July 2026",
            (LEFT - 1, BASELINE - 12, LEFT + 200, BASELINE + 3),
        )
    )

    assert _rejoined(converted, data).texts[0].text == "Effective from 1 st July 2026"


def test_a_page_the_readers_measure_apart_keeps_its_margin_number_at_the_end() -> None:
    """German, English, French and Greek paragraphs alike: nothing is moved."""
    for language, (text, number) in PARAGRAPHS.items():
        document = item_of(f"{text} {number}", left=40)
        document.pages[1].size = Size(width=595, height=842 + 20)

        _margined(document, page_of(text, number, margin=True))

        assert document.texts[0].text == f"{text} {number}", language


def test_a_paragraph_on_a_page_the_pdf_does_not_have_is_left_alone() -> None:
    """A provenance past the last page moves nothing and raises nothing."""
    text, number = PARAGRAPHS["en"]
    document = item_of(f"{text} {number}", left=40)
    document.add_page(page_no=2, size=Size(width=595, height=842))
    document.texts[0].prov[0].page_no = 2

    _margined(document, page_of(text, number, margin=True))

    assert document.texts[0].text == f"{text} {number}"
