"""A paragraph set where the running items sit is a running item.

The converter reads a running head or foot as body text now and then, and when
it is printed in another language than the document's it matches none of the
running strings the other pages carry. Where it sits is what says it is one:
the left edge and the top of the running items of three or more other pages.
"""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.common.reference import ProvenanceItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of

FEET = {
    "de": ("Jahresbericht 2026 | Konten", "Annual Report 2026 | Accounts"),
    "en": ("Annual Report 2026 | Accounts", "Jahresbericht 2026 | Konten"),
}
BODY = {
    "de": "Das Konto wird mit Ablauf der Frist geschlossen.",
    "en": "The account is closed when the notice period ends.",
}


def at(page: int, top: float, left: float = 54.0) -> ProvenanceItem:
    """A line of one height and width on a page."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=left, t=top, r=left + 300, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def document(language: str, foot: str, top: float = 800.0) -> DoclingDocument:
    """Six pages with the running foot on five; one paragraph at `top` on page 6."""
    own, _ = FEET[language]
    result = DoclingDocument(name="t")
    for page in range(1, 7):
        result.add_page(page_no=page, size=Size(width=595, height=842))
    for page in range(1, 6):
        result.add_text(
            label=DocItemLabel.PAGE_FOOTER,
            text=own,
            prov=at(page, 800),
            content_layer=ContentLayer.FURNITURE,
        )
    result.add_text(label=DocItemLabel.TEXT, text=BODY[language], prov=at(6, 100))
    result.add_text(label=DocItemLabel.TEXT, text=foot, prov=at(6, top))
    return result


def cut(result: DoclingDocument, language: str) -> str:
    """Every chunk's text, joined."""
    _, chunks = chunks_of(result, word_chunker(200), language)
    return "\n".join(chunk.text for chunk in chunks)


@pytest.mark.parametrize("language", sorted(FEET))
def test_a_foot_in_the_other_language_where_the_feet_sit_is_dropped(
    language: str,
) -> None:
    """Its words match no foot of the document; its place does."""
    other = FEET[language][1]

    assert cut(document(language, other), language) == BODY[language]


@pytest.mark.parametrize("language", sorted(FEET))
def test_a_paragraph_at_another_height_is_kept(language: str) -> None:
    """The same words mid-page are text."""
    other = FEET[language][1]

    assert other in cut(document(language, other, top=400), language)


def test_a_paragraph_in_the_margin_where_no_running_item_sits_is_kept() -> None:
    """Left edge and top both within a point of a running item, or it stays."""
    result = document("en", "Kundenservice Tel. 030 1234567", top=800)
    result.texts[-1].prov[0].bbox.l = 200

    assert "Kundenservice" in cut(result, "en")
