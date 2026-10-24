"""What a PDF is called is read off the type its pages are set in.

A document's first heading is often a salutation or a section word, and its
cover sets the real title in the largest type of the first page, over as
many lines as it takes. The candidates come best first: the first heading
that is set in the largest type of its page and heads the whole document, the
cover, the running head, the first heading.
"""

from __future__ import annotations

import pymupdf
import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.common.reference import ProvenanceItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

from preprocessing.parsing.pipelines.pdf import _titles

LANGUAGES = {
    "de": {
        "salute": "Sehr geehrte Damen und Herren,",
        "cover": ("Wichtige Präzisierungen zu den", "Kontoführungsentgelten 2026"),
        "section": "Einleitung",
        "body": "Die Bank erhebt für jedes Konto ein monatliches Entgelt.",
    },
    "en": {
        "salute": "Dear Sir or Madam,",
        "cover": ("Important clarifications to the", "account fees for 2026"),
        "section": "Introduction",
        "body": "The bank charges a monthly fee for each account.",
    },
    "es": {
        "salute": "Estimados señores:",
        "cover": ("Aclaraciones importantes sobre las", "comisiones de cuenta de 2026"),
        "section": "Introducción",
        "body": "El banco cobra una comisión mensual por cada cuenta.",
    },
}


def box(left: float, top: float, width: float, size: float) -> ProvenanceItem:
    """Provenance of one line at a place, with a top-left origin."""
    return ProvenanceItem(
        page_no=1,
        bbox=BoundingBox(
            l=left,
            t=top,
            r=left + width,
            b=top + size,
            coord_origin=CoordOrigin.TOPLEFT,
        ),
        charspan=(0, 1),
    )


def letter(language: str, cover: bool = True) -> tuple[bytes, DoclingDocument]:
    """A cover set in 24 points, then a salutation, a section word and a body."""
    words = LANGUAGES[language]
    pdf = pymupdf.open()
    page = pdf.new_page(width=595, height=842)
    document = DoclingDocument(name="letter")
    document.add_page(page_no=1, size=Size(width=595, height=842))
    top = 60.0
    if cover:
        for line in words["cover"]:
            page.insert_text((54, top + 24), line, fontsize=24)
            top += 30
    for text, size, label in (
        (words["salute"], 12, DocItemLabel.SECTION_HEADER),
        (words["section"], 14, DocItemLabel.SECTION_HEADER),
        (words["body"], 11, DocItemLabel.TEXT),
    ):
        top += 40
        page.insert_text((54, top + size), text, fontsize=size)
        width = pymupdf.get_text_length(text, fontsize=size)
        if label == DocItemLabel.TEXT:
            document.add_text(label=label, text=text, prov=box(54, top, width, size))
        else:
            document.add_heading(text=text, level=1, prov=box(54, top, width, size))
    return pdf.tobytes(), document


@pytest.mark.parametrize("language", sorted(LANGUAGES))
def test_the_cover_is_the_title_over_every_line_it_is_set_on(language: str) -> None:
    """A salutation and a section word are not what the document is called."""
    data, document = letter(language)

    assert _titles(document, data)[0] == " ".join(LANGUAGES[language]["cover"])


@pytest.mark.parametrize("language", sorted(LANGUAGES))
def test_the_first_heading_that_heads_the_document_is_the_title(
    language: str,
) -> None:
    """Set in the largest type of its page, no heading above it."""
    words = LANGUAGES[language]
    title = " ".join(words["cover"])
    pdf = pymupdf.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_text((54, 80), title, fontsize=16)
    page.insert_text((54, 140), words["body"], fontsize=11)
    document = DoclingDocument(name="terms")
    document.add_page(page_no=1, size=Size(width=595, height=842))
    document.add_heading(
        text=title,
        level=1,
        prov=box(54, 66, pymupdf.get_text_length(title, fontsize=16), 16),
    )

    assert _titles(document, pdf.tobytes())[0] == title


@pytest.mark.parametrize("language", sorted(LANGUAGES))
def test_a_lone_word_set_a_little_larger_is_no_cover(language: str) -> None:
    """A section word at the top of a page names nothing; the running head does."""
    data, document = letter(language, cover=False)
    for number in (1, 2):
        document.add_text(
            label=DocItemLabel.PAGE_HEADER,
            text="Account fees for 2026",
            prov=ProvenanceItem(
                page_no=number, bbox=box(54, 20, 100, 9).bbox, charspan=(0, 1)
            ),
            content_layer=ContentLayer.FURNITURE,
        )

    assert _titles(document, data) == ("Account fees for 2026",)


@pytest.mark.parametrize("language", sorted(LANGUAGES))
def test_a_lone_word_set_far_larger_is_the_cover(language: str) -> None:
    """A one-word title in type twice the page's own, over a running date."""
    words = LANGUAGES[language]
    pdf = pymupdf.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_text((54, 90), "Mortgages", fontsize=27)
    page.insert_text((54, 140), words["body"], fontsize=11)
    page.insert_text((54, 160), words["body"], fontsize=11)
    document = DoclingDocument(name="page")
    document.add_page(page_no=1, size=Size(width=595, height=842))
    document.add_text(
        label=DocItemLabel.PAGE_FOOTER,
        text="Last checked: 01/07/2026",
        prov=box(54, 800, 100, 9),
        content_layer=ContentLayer.FURNITURE,
    )

    assert _titles(document, pdf.tobytes())[0] == "Mortgages"


def test_a_heading_set_smaller_than_the_page_largest_type_is_no_title() -> None:
    """The cover's type is the largest of its page; a heading beside it is not."""
    data, document = letter("en")
    document.add_heading(text="Account fees 2026", level=1, prov=box(54, 100, 100, 11))

    assert _titles(document, data)[0] == " ".join(LANGUAGES["en"]["cover"])


def test_a_running_head_is_a_title_when_nothing_else_is() -> None:
    """The head every page repeats, where the pages hold no larger type."""
    pdf = pymupdf.open()
    document = DoclingDocument(name="guide")
    for number in (1, 2):
        pdf.new_page(width=595, height=842).insert_text(
            (54, 40), "Card terms", fontsize=9
        )
        document.add_page(page_no=number, size=Size(width=595, height=842))
        document.add_text(
            label=DocItemLabel.PAGE_HEADER,
            text="Card terms",
            prov=ProvenanceItem(
                page_no=number,
                bbox=box(54, 30, 60, 9).bbox,
                charspan=(0, 1),
            ),
            content_layer=ContentLayer.FURNITURE,
        )
    assert _titles(document, pdf.tobytes()) == ("Card terms",)


def test_a_document_with_no_text_has_no_candidates() -> None:
    """A page of a picture is read by nobody."""
    pdf = pymupdf.open()
    pdf.new_page(width=595, height=842)
    document = DoclingDocument(name="blank")

    assert _titles(document, pdf.tobytes()) == ()
