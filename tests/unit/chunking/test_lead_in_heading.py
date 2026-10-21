"""A lead-in a page join buries in a list item heads the list after it."""

from __future__ import annotations

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
