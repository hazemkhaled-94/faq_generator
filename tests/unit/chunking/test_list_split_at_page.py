"""A list the converter splits at a page break loses its depth there.

Docling 2.141 starts a new list group on every page: over three long PDFs of
the football build, 0 of 509 list groups hold items of two pages, and 14 of 45
lists split at a page break had a level open at the break. `nested` reads
each group alone, so sub-items continuing at the top of the next page are the
first group's level 0 and read as siblings of the outer items. Bank, shop and
public-administration lists in German, English, French and Greek, laid out as
the converter hands them over: one group a page, same margins on both pages.
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


def lines(language: str, groups: int) -> list[str]:
    """The list's lines, its items in one group or in one group a page."""
    lead, first, second, outer, after = LISTS[language]
    document = DoclingDocument(name="terms")
    for page in (1, 2):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    page_one = document.add_list_group()
    page_two = page_one if groups == 1 else document.add_list_group()
    for group, page, left, top, text in (
        (page_one, 1, 54, 700, lead),
        (page_one, 1, 72, 714, first),
        (page_two, 2, 72, 60, second),
        (page_two, 2, 54, 74, outer),
    ):
        document.add_list_item(text=text, parent=group, prov=placed(page, left, top))
    document.add_text(label=DocItemLabel.TEXT, text=after, prov=placed(2, 54, 100))
    _, chunks = chunks_of(document, word_chunker(200), language)
    return chunks[0].text.splitlines()[:4]


def expected(language: str) -> list[str]:
    """The list as printed: two sub-items under the lead-in, then an outer item."""
    lead, first, second, outer, _ = LISTS[language]
    return [f"- {lead}", f"    - {first}", f"    - {second}", f"- {outer}"]


@pytest.mark.parametrize("language", sorted(LISTS))
def test_one_group_over_the_page_keeps_the_depth(language: str) -> None:
    """The control: the shape the shipped tests pin, which the converter never makes."""
    assert lines(language, groups=1) == expected(language)


@pytest.mark.parametrize("language", sorted(LISTS))
def test_one_group_a_page_keeps_the_depth(language: str) -> None:
    """The shape the converter makes: the sub-item on page 2 is still a sub-item."""
    assert lines(language, groups=2) == expected(language)


def _two_lists(language: str, between: bool, page_two: int) -> list[str]:
    """Two lists, the second opening on `page_two`, a paragraph between them or not."""
    lead, first, second, _, after = LISTS[language]
    document = DoclingDocument(name="terms")
    for page in (1, 2):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    page_one = document.add_list_group()
    document.add_list_item(text=lead, parent=page_one, prov=placed(1, 54, 700))
    document.add_list_item(text=first, parent=page_one, prov=placed(1, 72, 714))
    if between:
        document.add_text(label=DocItemLabel.TEXT, text=after, prov=placed(1, 54, 740))
    other = document.add_list_group()
    top = 60 if page_two == 2 else 760
    document.add_list_item(text=second, parent=other, prov=placed(page_two, 72, top))
    document.add_list_item(
        text=after, parent=other, prov=placed(page_two, 54, top + 14)
    )
    _, chunks = chunks_of(document, word_chunker(200), language)
    return [line for chunk in chunks for line in chunk.text.splitlines()]


@pytest.mark.parametrize("language", sorted(LISTS))
def test_a_paragraph_between_two_lists_keeps_them_apart(language: str) -> None:
    """The second list opens at its own level: nothing of the first goes on in it."""
    _, _, second, _, _ = LISTS[language]
    assert f"- {second}" in _two_lists(language, between=True, page_two=2)


@pytest.mark.parametrize("language", sorted(LISTS))
def test_two_lists_on_one_page_are_not_one_list(language: str) -> None:
    """Only a page break joins two lists; on one page a second group is a second list."""
    _, _, second, _, _ = LISTS[language]
    assert f"- {second}" in _two_lists(language, between=False, page_two=1)
