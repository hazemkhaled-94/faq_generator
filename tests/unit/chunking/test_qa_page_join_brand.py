"""A paragraph opening with a lower-case name is not the rest of the item before."""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of


def on(page: int, top: float) -> ProvenanceItem:
    """Provenance on one page, a line high."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=54, t=top, r=500, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


@pytest.mark.parametrize(
    ("lang", "item", "rest"),
    [
        (
            "de",
            "Kostenloser Versand ab 50 €",
            "iPhone-Zubehör ist vom Umtausch ausgeschlossen.",
        ),
        ("en", "Free returns within 30 days", "eBay orders are shipped separately."),
    ],
)
def test_a_paragraph_opening_with_a_lower_case_name_stays_its_own(
    lang, item, rest
) -> None:
    """The list ends at the page's foot; the next page opens a new rule."""
    document = DoclingDocument(name="t")
    for page in (1, 2):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    document.add_heading(text="Versand", level=1, prov=on(1, 50))
    group = document.add_list_group()
    document.add_list_item(text="Lieferung in 2 Tagen", parent=group, prov=on(1, 760))
    document.add_list_item(text=item, parent=group, prov=on(1, 780))
    document.add_text(label=DocItemLabel.TEXT, text=rest, prov=on(2, 100))

    _, chunks = chunks_of(document, word_chunker(200), lang)

    assert f"- {item}\n" in "\n".join(chunk.text for chunk in chunks) + "\n"


@pytest.mark.parametrize(
    ("lang", "head", "rest"),
    [
        ("de", "Vom Umtausch ist Zubehör für das", "iPhone ausgeschlossen."),
        ("en", "Orders placed on", "eBay are shipped separately."),
        ("fr", "Les frais sont fixés par", "l'Union européenne."),
    ],
)
def test_a_sentence_cut_before_a_name_or_an_elision_is_still_joined(
    lang, head, rest
) -> None:
    """The tags read `für das` as wanting the name; `l'` opens in lower case."""
    document = DoclingDocument(name="t")
    for page in (1, 2):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    document.add_heading(text="Versand", level=1, prov=on(1, 50))
    document.add_text(label=DocItemLabel.TEXT, text=head, prov=on(1, 780))
    document.add_text(label=DocItemLabel.TEXT, text=rest, prov=on(2, 100))

    _, chunks = chunks_of(document, word_chunker(200), lang)

    assert [chunk.text for chunk in chunks] == [f"{head} {rest}"]
