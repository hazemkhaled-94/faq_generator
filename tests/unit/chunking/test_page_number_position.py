"""A lone integer is a page number only where page numbers sit."""

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
    ("lang", "label", "value"),
    [
        ("de", "Kündigungsfrist in Monaten:", "3"),
        ("de", "Kostenlose Abhebungen pro Monat:", "4"),
        ("en", "Return period (days):", "30"),
    ],
)
def test_a_bare_integer_value_beside_its_label_is_passage_text(
    lang, label, value
) -> None:
    """Printed at the label's height mid-page, not where the page numbers sit."""
    document = pages(3)
    for page in (1, 2, 3):
        document.add_text(
            label=DocItemLabel.PAGE_FOOTER,
            text=str(page),
            prov=on(page, 800),
            content_layer=ContentLayer.FURNITURE,
        )
    document.add_heading(text="Konditionen", level=1, prov=on(2, 50))
    document.add_text(label=DocItemLabel.TEXT, text=label, prov=on(2, 100))
    document.add_text(label=DocItemLabel.TEXT, text=value, prov=on(2, 100, left=300))

    assert value in texts(document, lang).split()


def test_a_page_number_the_foot_missed_is_not_passage_text() -> None:
    """Pages 1 and 3 print theirs as running feet; page 2's reads as body text."""
    document = pages(3)
    for page in (1, 3):
        document.add_text(
            label=DocItemLabel.PAGE_FOOTER,
            text=str(page),
            prov=on(page, 800),
            content_layer=ContentLayer.FURNITURE,
        )
    document.add_heading(text="Konditionen", level=1, prov=on(2, 50))
    document.add_text(
        label=DocItemLabel.TEXT, text="Das Konto ist kostenlos.", prov=on(2, 100)
    )
    document.add_text(label=DocItemLabel.TEXT, text="2", prov=on(2, 800))

    assert "2" not in texts(document, "de").split()


@pytest.mark.parametrize(
    ("lang", "label", "value"),
    [
        ("de", "Kündigungsfrist in Monaten:", "3"),
        ("en", "Return window in days:", "30"),
    ],
)
def test_a_value_stacked_under_its_label_at_a_page_foot_stays(
    lang, label, value
) -> None:
    """No running page numbers, and the value is the page's last line, in its margin."""
    document = pages(2)
    document.add_heading(text="Konditionen", level=1, prov=on(1, 50))
    document.add_text(
        label=DocItemLabel.TEXT, text="Das Konto ist kostenlos.", prov=on(1, 100)
    )
    document.add_text(label=DocItemLabel.TEXT, text=label, prov=on(1, 780))
    document.add_text(label=DocItemLabel.TEXT, text=value, prov=on(1, 800))

    assert value in texts(document, lang).split()


def test_a_value_beside_its_label_equal_to_its_page_number_stays() -> None:
    """On page 3 of a numbered document, `3` printed mid-page is still a value."""
    document = pages(3)
    for page in (1, 2, 3):
        document.add_text(
            label=DocItemLabel.PAGE_FOOTER,
            text=str(page),
            prov=on(page, 800),
            content_layer=ContentLayer.FURNITURE,
        )
    document.add_heading(text="Konditionen", level=1, prov=on(3, 50))
    document.add_text(
        label=DocItemLabel.TEXT, text="Kündigungsfrist in Monaten:", prov=on(3, 100)
    )
    document.add_text(label=DocItemLabel.TEXT, text="3", prov=on(3, 100, left=300))

    assert "3" in texts(document, "de").split()
