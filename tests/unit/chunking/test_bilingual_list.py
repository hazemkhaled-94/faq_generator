"""A list in two languages is cut where the language changes."""

from __future__ import annotations

from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
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


def test_a_bilingual_list_is_not_merged_into_one_passage_read_as_one_language() -> None:
    """_one_language reads paragraphs only, so list items of two languages stay together."""
    document = pages(1)
    document.add_heading(text="Kontoführung / Account maintenance", level=1)
    group = document.add_list_group()
    for at, item in enumerate(
        [
            "Die Kontoführung ist kostenlos, wenn monatlich mindestens 1.000 Euro auf dem Konto eingehen.",
            "Kontoauszüge erhalten Sie jeden Monat kostenlos im Online-Banking und in der App.",
            "The account is free of charge when at least 1,000 euros are paid in every month.",
            "You receive your statements every month free of charge in online banking and in the app.",
        ]
    ):
        document.add_list_item(text=item, parent=group, prov=on(1, 60 + 15 * at))

    _, chunks = chunks_of(document, word_chunker(200), "de")

    assert not any(
        "Kontoauszüge" in chunk.text and "statements" in chunk.text for chunk in chunks
    ), [chunk.text for chunk in chunks]
    # The cut falls before the item's marker, not after it.
    assert any(chunk.text.startswith("- The account") for chunk in chunks)
