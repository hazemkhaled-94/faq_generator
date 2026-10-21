"""A lead-in labelled a heading, or buried in a list item, heads its sections."""

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


@pytest.mark.parametrize(
    ("lang", "chapter", "lead", "sections"),
    [
        (
            "de",
            "Entgelte für Geschäftskunden",
            "Für Kunden mit einem Jahresumsatz unter 1 Mio. EUR gilt:",
            [
                ("Kontoführung", ["Das Konto kostet 9 EUR im Monat."]),
                ("Karten", ["Die Debitkarte kostet 12 EUR im Jahr."]),
            ],
        ),
        (
            "en",
            "Shipping",
            "For orders to islands and remote areas:",
            [
                ("Standard delivery", ["costs 9.95 EUR"]),
                ("Express delivery", ["costs 19.95 EUR"]),
            ],
        ),
    ],
)
def test_a_lead_in_the_converter_labels_a_heading_scopes_the_sections_it_introduces(
    lang, chapter, lead, sections
) -> None:
    """As a paragraph it heads both sections; as a heading it reaches neither."""
    document = pages(1)
    document.add_heading(text=chapter, level=1, prov=on(1, 40))
    document.add_heading(text=lead, level=2, prov=on(1, 60))
    top = 60
    for heading, items in sections:
        top += 20
        document.add_heading(text=heading, level=2, prov=on(1, top))
        group = document.add_list_group()
        for item in items:
            top += 12
            document.add_list_item(text=item, parent=group, prov=on(1, top))

    _, chunks = chunks_of(document, word_chunker(200), lang)

    for chunk in chunks:
        assert lead in chunk.text or lead in (chunk.meta.headings or []), (
            chunk.meta.headings,
            chunk.text,
        )


def test_a_lead_in_a_page_join_put_inside_a_list_item_heads_every_piece() -> None:
    """The join ends a list item on 'wenn:'; the list after it is carried no lead-in."""
    document = pages(2)
    document.add_heading(text="Karten", level=1, prov=on(1, 40))
    first = document.add_list_group()
    document.add_list_item(
        text="Eine Ersatzkarte kostet 15 EUR.", parent=first, prov=on(1, 700)
    )
    document.add_list_item(
        text="Die einzigen Ausnahmen von der Gebühr", parent=first, prov=on(1, 780)
    )
    document.add_text(label=DocItemLabel.TEXT, text="bestehen, wenn:", prov=on(2, 40))
    second = document.add_list_group()
    for at, case in enumerate(
        f"die {n} Karte im Ausland gestohlen wurde und der Diebstahl angezeigt ist"
        for n in ("erste", "zweite", "dritte", "vierte", "fünfte", "sechste")
    ):
        document.add_list_item(text=case, parent=second, prov=on(2, 60 + 12 * at))

    _, chunks = chunks_of(document, word_chunker(30), "de")

    listed = [c for c in chunks if "Karte im Ausland gestohlen" in c.text]
    assert listed
    for chunk in listed:
        trail = " ".join(chunk.meta.headings or [])
        assert "wenn:" in chunk.text or "wenn:" in trail, (
            chunk.meta.headings,
            chunk.text,
        )
