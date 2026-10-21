"""A sentence cut at a page break is joined whatever case its rest opens in."""

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
    ("lang", "before", "after"),
    [
        ("de", "Die Gebühr für die", "Ersatzkarte beträgt 15 EUR."),
        ("en", "Refunds for orders paid by", "PayPal are made within 14 days."),
    ],
)
def test_a_sentence_cut_at_a_page_break_before_a_capital_is_read_whole(
    lang, before, after
) -> None:
    """A German noun or an English name opens the rest of the sentence in capitals."""
    document = pages(2)
    document.add_heading(text="Karten", level=1, prov=on(1, 50))
    document.add_text(label=DocItemLabel.TEXT, text=before, prov=on(1, 780))
    document.add_text(label=DocItemLabel.TEXT, text=after, prov=on(2, 60))

    assert f"{before} {after}" in texts(document, lang)


def test_a_list_item_ending_on_an_adjective_does_not_swallow_the_next_page() -> None:
    """`gratis` can end an item with no full stop; a noun opening page 2 is a new sentence."""
    document = pages(2)
    document.add_heading(text="Zahlungsarten", level=1, prov=on(1, 50))
    group = document.add_list_group()
    document.add_list_item(
        text="Kreditkarte für Neukunden gratis", parent=group, prov=on(1, 780)
    )
    document.add_text(
        label=DocItemLabel.TEXT,
        text="Zahlungen per PayPal sind möglich.",
        prov=on(2, 60),
    )

    assert "gratis Zahlungen" not in texts(document, "de")
