"""A page that holds only the list's items has no block to read its margin off.

The converter starts a list again on every page, and a page of a long list can
hold nothing else. Its indents are then read off the nearest page of the same
parity, which a facing-page layout sets alike; failing that off the page before,
never right of the list's own leftmost item there; and where a page set further
right cannot be told from a page of sub-items alone, the open levels are not
carried onto it.
"""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of

#: (lead paragraph, outer 1, sub 1, outer 2, sub 2, outer 3, closing paragraph)
LISTS = {
    "de": (
        "Die Bank berechnet folgende Entgelte.",
        "Kontoführung",
        "monatlich fünf Euro",
        "Karten",
        "jährlich zwölf Euro",
        "Überweisungen",
        "Alle Preise verstehen sich inklusive Steuern.",
    ),
    "en": (
        "The shop charges the following fees.",
        "Delivery",
        "five euros an order",
        "Returns",
        "free within fourteen days",
        "Gift wrapping",
        "All prices include value added tax.",
    ),
    "fr": (
        "La mairie perçoit les frais suivants.",
        "Passeport",
        "quatre-vingt-six euros",
        "Carte",
        "gratuite la première fois",
        "Copie",
        "Tous les frais sont payables au guichet.",
    ),
    "el": (
        "Η υπηρεσία χρεώνει τα εξής τέλη.",
        "Διαβατήριο",
        "ογδόντα έξι ευρώ",
        "Ταυτότητα",
        "δωρεάν την πρώτη φορά",
        "Αντίγραφο",
        "Όλα τα τέλη πληρώνονται στο γκισέ.",
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


def two_pages(language: str, odd: float, even: float) -> list[str]:
    """Page 1 ends on outer 1 and its sub 1; page 2 holds only the list's items.

    One group a page, the text block of page 2 starting at `even`.
    """
    lead, o1, s1, o2, s2, o3, _ = LISTS[language]
    document = DoclingDocument(name="fees")
    for page in (1, 2):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    document.add_text(label=DocItemLabel.TEXT, text=lead, prov=placed(1, odd, 680))
    one = document.add_list_group()
    document.add_list_item(text=o1, parent=one, prov=placed(1, odd, 700))
    document.add_list_item(text=s1, parent=one, prov=placed(1, odd + 18, 714))
    two = document.add_list_group()
    for left, top, text in ((even, 60, o2), (even + 18, 74, s2), (even, 88, o3)):
        document.add_list_item(text=text, parent=two, prov=placed(2, left, top))
    return lines(document, language)


def lines(document: DoclingDocument, language: str) -> list[str]:
    """The list lines of every chunk."""
    _, chunks = chunks_of(document, word_chunker(300), language)
    return [
        line
        for chunk in chunks
        for line in chunk.text.splitlines()
        if line.lstrip().startswith("-")
    ]


def expected_two(language: str) -> list[str]:
    """The list as printed."""
    _, o1, s1, o2, s2, o3, _ = LISTS[language]
    return [f"- {o1}", f"    - {s1}", f"- {o2}", f"    - {s2}", f"- {o3}"]


@pytest.mark.parametrize("language", sorted(LISTS))
def test_a_page_of_the_lists_items_alone_at_the_same_margin(language: str) -> None:
    """The control: the page before sets the edge."""
    assert two_pages(language, 54, 54) == expected_two(language)


@pytest.mark.parametrize("language", sorted(LISTS))
def test_a_page_of_the_lists_items_alone_set_22_pt_right(language: str) -> None:
    """Mirrored margins: nothing says the shift is no indent, so no level is carried."""
    assert two_pages(language, 51, 73.7) == expected_two(language)


@pytest.mark.parametrize("language", sorted(LISTS))
def test_a_page_of_the_lists_items_alone_set_22_pt_left(language: str) -> None:
    """An item cannot print left of its list's outer level: the page's leftmost is the edge."""
    assert two_pages(language, 51, 28.3) == expected_two(language)


def four_pages(language: str) -> list[str]:
    """Odd pages at 51, even pages at 73.7.

    Page 2 holds only list items and opens on a sub-item; page 4, of the same
    parity, holds a paragraph.
    """
    lead, o1, s1, o2, s2, _, close = LISTS[language]
    document = DoclingDocument(name="fees")
    for page in (1, 2, 3, 4):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    document.add_text(label=DocItemLabel.TEXT, text=lead, prov=placed(1, 51, 680))
    one = document.add_list_group()
    document.add_list_item(text=o1, parent=one, prov=placed(1, 51, 700))
    document.add_list_item(text=s1, parent=one, prov=placed(1, 69, 714))
    two = document.add_list_group()
    document.add_list_item(text=s2, parent=two, prov=placed(2, 91.7, 60))
    document.add_list_item(text=o2, parent=two, prov=placed(2, 73.7, 74))
    document.add_text(label=DocItemLabel.TEXT, text=close, prov=placed(4, 73.7, 100))
    return lines(document, language)


@pytest.mark.parametrize("language", sorted(LISTS))
def test_a_page_of_the_lists_items_alone_reads_its_edge_off_the_page_of_its_parity(
    language: str,
) -> None:
    """Page 4 shares page 2's margin: the sub-item opening page 2 stays a sub-item."""
    _, o1, s1, o2, s2, _, _ = LISTS[language]
    assert four_pages(language) == [f"- {o1}", f"    - {s1}", f"    - {s2}", f"- {o2}"]


def three_pages(language: str) -> list[str]:
    """Odd pages at 54, the even page 2 at 26 holding only list items, page 3 with a paragraph."""
    lead, o1, s1, o2, s2, o3, close = LISTS[language]
    document = DoclingDocument(name="fees")
    for page in (1, 2, 3):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    document.add_text(label=DocItemLabel.TEXT, text=lead, prov=placed(1, 54, 680))
    one = document.add_list_group()
    document.add_list_item(text=o1, parent=one, prov=placed(1, 54, 700))
    document.add_list_item(text=s1, parent=one, prov=placed(1, 72, 714))
    two = document.add_list_group()
    document.add_list_item(text=o2, parent=two, prov=placed(2, 26, 60))
    document.add_list_item(text=s2, parent=two, prov=placed(2, 44, 74))
    three = document.add_list_group()
    document.add_list_item(text=o3, parent=three, prov=placed(3, 54, 60))
    document.add_list_item(text=s1, parent=three, prov=placed(3, 72, 74))
    document.add_text(label=DocItemLabel.TEXT, text=close, prov=placed(3, 54, 100))
    return lines(document, language)


@pytest.mark.parametrize("language", sorted(LISTS))
def test_an_outer_item_on_a_normal_page_after_a_page_of_the_lists_items_alone(
    language: str,
) -> None:
    """Page 3's outer item, read off page 3's own edge, is outer."""
    _, o1, s1, o2, s2, o3, _ = LISTS[language]
    assert three_pages(language) == [
        f"- {o1}",
        f"    - {s1}",
        f"- {o2}",
        f"    - {s2}",
        f"- {o3}",
        f"    - {s1}",
    ]


def boxed(page: int, left: float, top: float, width: float) -> ProvenanceItem:
    """A box `width` points wide and a line high, from the page's top."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=left, t=top, r=left + width, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def with_note(language: str, margin: float, note_at: float | None) -> list[str]:
    """Pages at `margin`; page 2 holds only list items; page 4 may print a margin note."""
    lead, o1, s1, o2, s2, o3, close = LISTS[language]
    document = DoclingDocument(name="fees")
    for page in (1, 2, 3, 4):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    document.add_text(label=DocItemLabel.TEXT, text=lead, prov=placed(1, margin, 680))
    one = document.add_list_group()
    document.add_list_item(text=o1, parent=one, prov=placed(1, margin, 700))
    document.add_list_item(text=s1, parent=one, prov=placed(1, margin + 18, 714))
    two = document.add_list_group()
    for left, top, text in (
        (margin, 60, o2),
        (margin + 18, 74, s2),
        (margin, 88, o3),
    ):
        document.add_list_item(text=text, parent=two, prov=placed(2, left, top))
    document.add_text(label=DocItemLabel.TEXT, text=close, prov=placed(3, margin, 60))
    if note_at is not None:
        document.add_text(
            label=DocItemLabel.TEXT, text="12", prov=boxed(4, note_at, 100, 15)
        )
    document.add_text(label=DocItemLabel.TEXT, text=close, prov=placed(4, margin, 100))
    return lines(document, language)


@pytest.mark.parametrize("language", sorted(LISTS))
def test_a_margin_note_on_the_page_of_the_same_parity_is_no_column_edge(
    language: str,
) -> None:
    """Only blocks that reach across the item's start give the edge, not a note beside the text."""
    _, o1, s1, o2, s2, o3, _ = LISTS[language]
    assert with_note(language, 54, 20) == [
        f"- {o1}",
        f"    - {s1}",
        f"- {o2}",
        f"    - {s2}",
        f"- {o3}",
    ]


def mirrored_note(language: str) -> list[str]:
    """Odd pages at 51, even at 73.7; page 2 opens on a sub-item; page 4 has a note at 30."""
    lead, o1, s1, o2, s2, _, close = LISTS[language]
    document = DoclingDocument(name="fees")
    for page in (1, 2, 3, 4):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    document.add_text(label=DocItemLabel.TEXT, text=lead, prov=placed(1, 51, 680))
    one = document.add_list_group()
    document.add_list_item(text=o1, parent=one, prov=placed(1, 51, 700))
    document.add_list_item(text=s1, parent=one, prov=placed(1, 69, 714))
    two = document.add_list_group()
    document.add_list_item(text=s2, parent=two, prov=placed(2, 91.7, 60))
    document.add_list_item(text=o2, parent=two, prov=placed(2, 73.7, 74))
    document.add_text(label=DocItemLabel.TEXT, text=close, prov=placed(3, 51, 60))
    document.add_text(label=DocItemLabel.TEXT, text=close, prov=placed(4, 73.7, 100))
    document.add_text(label=DocItemLabel.TEXT, text="12", prov=boxed(4, 30, 100, 15))
    return lines(document, language)


@pytest.mark.parametrize("language", sorted(LISTS))
def test_a_note_on_the_parity_page_of_a_mirrored_layout_is_no_column_edge(
    language: str,
) -> None:
    """The page of the same parity sets its text at 73.7: the note at 30 is beside it."""
    _, o1, s1, o2, s2, _, _ = LISTS[language]
    assert mirrored_note(language) == [
        f"- {o1}",
        f"    - {s1}",
        f"    - {s2}",
        f"- {o2}",
    ]


def cover(language: str) -> list[str]:
    """Same margins everywhere; page 1 a cover whose only text is set at 200.

    The list runs from page 2 onto page 3, which holds only its items and opens on a
    sub-item; the page of the same parity that has a block is the cover, at 200.
    """
    lead, o1, s1, o2, s2, o3, close = LISTS[language]
    document = DoclingDocument(name="fees")
    for page in (1, 2, 3, 4, 5):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    document.add_text(label=DocItemLabel.TEXT, text=close, prov=placed(1, 200, 400))
    document.add_text(label=DocItemLabel.TEXT, text=lead, prov=boxed(2, 54, 680, 400))
    one = document.add_list_group()
    document.add_list_item(text=o1, parent=one, prov=placed(2, 54, 700))
    document.add_list_item(text=s1, parent=one, prov=placed(2, 72, 714))
    two = document.add_list_group()
    for left, top, text in ((72, 60, s2), (54, 74, o2), (54, 88, o3)):
        document.add_list_item(text=text, parent=two, prov=placed(3, left, top))
    document.add_text(label=DocItemLabel.TEXT, text=close, prov=boxed(4, 54, 60, 400))
    document.add_text(label=DocItemLabel.TEXT, text=close, prov=boxed(5, 54, 60, 400))
    return lines(document, language)


@pytest.mark.parametrize("language", sorted(LISTS))
def test_an_edge_read_off_a_far_page_is_bounded_by_the_lists_leftmost_item(
    language: str,
) -> None:
    """A page whose text is set in at 200 does not push the page's outer items right."""
    _, o1, s1, o2, s2, o3, _ = LISTS[language]
    assert cover(language) == [
        f"- {o1}",
        f"    - {s1}",
        f"    - {s2}",
        f"- {o2}",
        f"- {o3}",
    ]
