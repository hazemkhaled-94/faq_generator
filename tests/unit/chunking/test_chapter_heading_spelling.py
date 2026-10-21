"""Text above a mid-page chapter keeps its chapter, whatever the heading's spelling."""

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


@pytest.mark.parametrize(
    ("head_a", "head_b", "heading_b"),
    [
        ("A Privatkunden", "B Geschäftskunden", "B. Geschäftskunden"),
        ("Privatkunden", "Geschäftskunden", "B Geschäftskunden"),
        ("Kapitel A: Personal", "Kapitel B: Business", "B Business"),
    ],
)
def test_text_above_a_mid_page_chapter_keeps_its_chapter_when_spelled_otherwise(
    head_a, head_b, heading_b
) -> None:
    """The chapter's heading and its running head differ in a mark or a prefix."""
    document = pages(4)
    for page, chapter in {1: head_a, 2: head_a, 3: head_b, 4: head_b}.items():
        document.add_text(
            label=DocItemLabel.PAGE_HEADER,
            text=chapter,
            prov=on(page, 20),
            content_layer=ContentLayer.FURNITURE,
        )
    document.add_heading(text=head_a, level=1, prov=on(1, 60))
    document.add_heading(text="1.3 Sparkonten", level=2, prov=on(2, 60))
    document.add_text(label=DocItemLabel.TEXT, text="Filler on 2.", prov=on(2, 80))
    line = "Sparkonten werden mit 1,5 % p.a. verzinst."
    document.add_text(label=DocItemLabel.TEXT, text=line, prov=on(3, 60))
    document.add_heading(text=heading_b, level=1, prov=on(3, 400))
    document.add_text(
        label=DocItemLabel.TEXT,
        text="Das Geschäftskonto kostet 12,90 EUR.",
        prov=on(3, 430),
    )

    _, chunks = chunks_of(document, word_chunker(200), "de")

    held = [c for c in chunks if line in c.text]
    assert held
    for chunk in held:
        assert "1.3 Sparkonten" in (chunk.meta.headings or []), chunk.meta.headings
