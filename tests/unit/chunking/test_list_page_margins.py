"""List depth across a page break on a page whose text block is shifted.

A printed brochure sets facing pages with mirrored margins: the text block of
an even page starts further left or right than an odd page's. `nested` reads
the indent on the new page off the previous page's column edge, so the shift
is read as an indent. Bank, shop and public-administration lists, in German,
English, French and Greek: the geometry is the same in each.
"""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of

#: (language, lead-in item, sub-item on page 1, sub-item on page 2, outer item, paragraph)
LISTS = {
    "de": (
        "Die Bank sperrt die Karte, wenn:",
        "der Karteninhaber die Sperre verlangt,",
        "der Verdacht einer missbräuchlichen Nutzung besteht.",
        "Die Sperre wird dem Karteninhaber mitgeteilt.",
        "Die Bank haftet nicht für Schäden durch die Sperre.",
    ),
    "en": (
        "A refund is paid:",
        "to the card the order was paid with,",
        "within fourteen days of the return.",
        "Gift cards cannot be returned.",
        "The shop answers every complaint in writing.",
    ),
    "fr": (
        "La demande est refusée si :",
        "le formulaire est incomplet,",
        "le justificatif de domicile manque.",
        "Le demandeur est informé par courrier.",
        "Le service répond dans un délai de trente jours.",
    ),
    "el": (
        "Η αίτηση απορρίπτεται όταν:",
        "το έντυπο είναι ελλιπές,",
        "λείπει η βεβαίωση διεύθυνσης.",
        "Ο αιτών ενημερώνεται εγγράφως.",
        "Η υπηρεσία απαντά εντός τριάντα ημερών.",
    ),
}


def placed(page: int, left: float, top: float) -> ProvenanceItem:
    """A box 200 points wide and a line high, from the page's top."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=left, t=top, r=left + 200, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def lines(language: str, odd: float, even: float) -> list[str]:
    """The list's lines when page 1's text starts at `odd` and page 2's at `even`."""
    lead, first, second, outer, after = LISTS[language]
    document = DoclingDocument(name="terms")
    for page in (1, 2):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    group = document.add_list_group()
    for page, left, top, text in (
        (1, odd, 700, lead),
        (1, odd + 18, 714, first),
        (2, even + 18, 60, second),
        (2, even, 74, outer),
    ):
        document.add_list_item(text=text, parent=group, prov=placed(page, left, top))
    document.add_text(label=DocItemLabel.TEXT, text=after, prov=placed(2, even, 100))
    _, chunks = chunks_of(document, word_chunker(200), language)
    return chunks[0].text.splitlines()[:4]


def expected(language: str) -> list[str]:
    """The list as printed: two sub-items under the lead-in, then an outer item."""
    lead, first, second, outer, _ = LISTS[language]
    return [f"- {lead}", f"    - {first}", f"    - {second}", f"- {outer}"]


@pytest.mark.parametrize("language", sorted(LISTS))
def test_same_margins_on_both_pages_keep_the_depth(language: str) -> None:
    """The control: the shipped behaviour when both pages share one margin."""
    assert lines(language, 54, 54) == expected(language)


@pytest.mark.parametrize("language", sorted(LISTS))
def test_an_even_page_set_further_right_keeps_the_outer_item_outer(
    language: str,
) -> None:
    """Page 2's text block starts 28 points right of page 1's (mirrored margins)."""
    assert lines(language, 54, 82) == expected(language)


@pytest.mark.parametrize("language", sorted(LISTS))
def test_an_even_page_set_further_left_keeps_the_sub_item_nested(
    language: str,
) -> None:
    """Page 2's text block starts 28 points left of page 1's (mirrored margins)."""
    assert lines(language, 82, 54) == expected(language)
