"""A long document is read for its furniture in time proportional to its length."""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
from docling_core.types.doc.labels import DocItemLabel

from preprocessing.chunking.furniture import furniture_of, tidied

#: Items per page: a heading, the paragraphs, the page number read as text.
PARAGRAPHS = 20


def on(page: int, top: float) -> ProvenanceItem:
    """Provenance on one page, a line high."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=54, t=top, r=500, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def price_list(count: int) -> DoclingDocument:
    """Pages of fee paragraphs, each page's number read as body text."""
    document = DoclingDocument(name="t")
    for page in range(1, count + 1):
        document.add_page(page_no=page, size=Size(width=595, height=842))
        document.add_heading(text=f"Abschnitt {page}", level=1, prov=on(page, 50))
        for line in range(PARAGRAPHS):
            document.add_text(
                label=DocItemLabel.TEXT,
                text=f"Leistung {line} auf Seite {page} kostet 2,50 EUR.",
                prov=on(page, 100 + 30 * line),
            )
        document.add_text(label=DocItemLabel.TEXT, text=str(page), prov=on(page, 820))
    return document


def items_walked(document: DoclingDocument, monkeypatch) -> int:
    """How many items the tidy pass walks over the document's tree."""
    walked = 0
    walk = DoclingDocument.iterate_items

    def counted(self, *args, **kwargs):
        nonlocal walked
        for found in walk(self, *args, **kwargs):
            walked += 1
            yield found

    monkeypatch.setattr(DoclingDocument, "iterate_items", counted)
    tidy, _ = tidied(document, furniture_of(document), "de")
    monkeypatch.undo()
    # The page numbers did go: the walk did its work.
    assert not any(
        item.text == "7" for item in tidy.texts if item.content_layer.value == "body"
    )
    return walked


@pytest.mark.xfail(
    strict=True,
    reason=(
        "_follows_lead_in walks the whole document once per page number read as "
        "body text, so tidying is quadratic in pages: 23 s of an 800-page document's "
        "24 s go there"
    ),
)
def test_tidying_walks_each_item_a_bounded_number_of_times(monkeypatch) -> None:
    """Doubling the pages at most doubles the walk, give or take a page."""
    short = items_walked(price_list(40), monkeypatch)
    long = items_walked(price_list(160), monkeypatch)

    assert long <= 4.5 * short, (short, long)
