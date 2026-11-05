"""A body paragraph that repeats a running foot is dropped wherever it sits.

`tidied` takes a paragraph equal to a running head or foot, field for field,
for the converter reading furniture as body text, and moves it to the
furniture layer. It never asks where the paragraph sits: one in the middle of
the page, a contact section printing the hotline the foot also prints, goes
the same way, and its text then reaches no passage. `_page_number` and
`_where_running` both ask for the margin. German, English, French and Greek.
"""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of

#: (language, the foot's lettered field and the body's contact line, a body sentence)
CONTACTS = {
    "de": ("Kundenservice 0800 123 456", "Wir sind montags bis freitags erreichbar."),
    "en": ("Customer service 0800 123 456", "We answer every order query by phone."),
    "fr": (
        "Service usagers 01 23 45 67 89",
        "Le guichet répond aux demandes de passeport.",
    ),
    "el": ("Εξυπηρέτηση πολιτών 210 123 4567", "Η υπηρεσία απαντά σε κάθε αίτηση."),
}


def placed(page: int, top: float) -> ProvenanceItem:
    """A box at the text's left edge, a line high, from the page's top."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=54, t=top, r=500, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def text(language: str) -> str:
    """Every passage's text of three pages, the last a contact page."""
    contact, sentence = CONTACTS[language]
    document = DoclingDocument(name="contact")
    for page in (1, 2, 3):
        document.add_page(page_no=page, size=Size(width=595, height=842))
        document.add_text(
            label=DocItemLabel.PAGE_FOOTER,
            text=f"{contact} | {page}",
            prov=placed(page, 815),
            content_layer=ContentLayer.FURNITURE,
        )
        document.add_text(
            label=DocItemLabel.TEXT, text=sentence, prov=placed(page, 300)
        )
    # The contact page prints the hotline as body text, in the middle of the page.
    document.add_text(label=DocItemLabel.TEXT, text=contact, prov=placed(3, 400))
    _, chunks = chunks_of(document, word_chunker(200), language)
    return "\n".join(chunk.text for chunk in chunks)


@pytest.mark.parametrize("language", sorted(CONTACTS))
def test_a_contact_line_in_the_body_area_reaches_a_passage(language: str) -> None:
    """The body's own line is no running foot: it sits 400 points from the top."""
    contact, _ = CONTACTS[language]
    assert contact in text(language), text(language)
