"""A footnote the converter attaches to a picture reaches a passage."""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
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
    ("lang", "note"),
    [
        ("de", "* Angebot gilt nur für Neukunden bis 31.12.2026."),
        ("en", "* Offer valid for orders placed before 31 December 2026."),
    ],
)
def test_a_footnote_attached_to_a_picture_is_passage_text(lang, note) -> None:
    """Only a table's footnotes are written; a picture's are dropped."""
    document = pages(1)
    document.add_heading(text="Zinsen", level=1, prov=on(1, 40))
    document.add_text(label=DocItemLabel.TEXT, text="Body text.", prov=on(1, 60))
    picture = document.add_picture(prov=on(1, 100))
    foot = document.add_text(
        label=DocItemLabel.FOOTNOTE, text=note, parent=picture, prov=on(1, 215)
    )
    picture.footnotes.append(foot.get_ref())

    assert note.lstrip("* ") in texts(document, lang)
