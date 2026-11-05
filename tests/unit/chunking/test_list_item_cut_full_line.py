"""The rest of a cut list item is told from a first sub-item by a full line and a readable edge.

A parent item with no end mark whose only sub-item opens the next page has the
geometry of a cut item and its rest, but its last line is a label that stops
short of the column. And a page that holds only sub-items has no edge to read
their indents off, so two siblings across it are not a cut item.
"""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of

#: (lead paragraph, outer 1, sub 1, outer 2, sub 2, closing paragraph, sub 3)
LISTS = {
    "de": (
        "Die Bank berechnet folgende Entgelte.",
        "Kontoführung",
        "monatlich fünf Euro",
        "Karten",
        "jährlich zwölf Euro",
        "Alle Preise verstehen sich inklusive Steuern.",
        "je Auftrag zwei Euro",
    ),
    "en": (
        "The shop charges the following fees.",
        "Delivery",
        "five euros an order",
        "Returns",
        "free within fourteen days",
        "All prices include value added tax.",
        "two euros a parcel",
    ),
    "fr": (
        "La mairie perçoit les frais suivants.",
        "Passeport",
        "quatre-vingt-six euros",
        "Carte",
        "gratuite la première fois",
        "Tous les frais sont payables au guichet.",
        "deux euros la page",
    ),
    "el": (
        "Η υπηρεσία χρεώνει τα εξής τέλη.",
        "Διαβατήριο",
        "ογδόντα έξι ευρώ",
        "Ταυτότητα",
        "δωρεάν την πρώτη φορά",
        "Όλα τα τέλη πληρώνονται στο γκισέ.",
        "δύο ευρώ η σελίδα",
    ),
}
LANGS = sorted(LISTS)


def placed(page: int, left: float, top: float, width: float = 200) -> ProvenanceItem:
    """A box `width` points wide and a line high, from the page's top."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=left, t=top, r=left + width, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def pages(count: int) -> DoclingDocument:
    """An empty document of `count` pages."""
    document = DoclingDocument(name="fees")
    for page in range(1, count + 1):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    return document


def lines(document: DoclingDocument, language: str) -> list[str]:
    """The list lines of every chunk."""
    _, chunks = chunks_of(document, word_chunker(300), language)
    return [
        line
        for chunk in chunks
        for line in chunk.text.splitlines()
        if line.lstrip().startswith("-")
    ]


def parent_cut(language: str, after: str, label_width: float) -> list[str]:
    """Page 1 ends on an outer item with no end mark; page 2 opens on its one sub-item.

    The sub-item is set in at 72 and followed by an outer item (`after` "outer") or a
    paragraph; the parent's box is `label_width` points wide, the lead's 400.
    """
    lead, o1, s1, o2, _, close, _ = LISTS[language]
    d = pages(2)
    d.add_text(label=DocItemLabel.TEXT, text=lead, prov=placed(1, 54, 680, width=400))
    one = d.add_list_group()
    d.add_list_item(text=o1, parent=one, prov=placed(1, 54, 700, width=label_width))
    two = d.add_list_group()
    d.add_list_item(text=s1, parent=two, prov=placed(2, 72, 60))
    if after == "outer":
        d.add_list_item(text=o2, parent=two, prov=placed(2, 54, 74))
    d.add_text(label=DocItemLabel.TEXT, text=close, prov=placed(2, 54, 100, width=400))
    return lines(d, language)


@pytest.mark.parametrize("language", LANGS)
def test_a_parents_only_sub_item_opening_the_next_page_then_an_outer_item(
    language: str,
) -> None:
    """The parent is a label that stops short of the column: its sub-item is no rest.

    No level opens across a page break, so the sub-item prints flat, as it does
    without the join.
    """
    _, o1, s1, o2, _, _, _ = LISTS[language]
    assert parent_cut(language, "outer", 120) == [f"- {o1}", f"- {s1}", f"- {o2}"]


@pytest.mark.parametrize("language", LANGS)
def test_a_parents_only_sub_item_opening_the_next_page_then_a_paragraph(
    language: str,
) -> None:
    """The same with a paragraph after the sub-item."""
    _, o1, s1, _, _, _, _ = LISTS[language]
    assert parent_cut(language, "para", 120) == [f"- {o1}", f"- {s1}"]


@pytest.mark.parametrize("language", LANGS)
def test_a_parent_whose_line_runs_to_the_column_edge_is_cut(language: str) -> None:
    """The control: a full line with no end mark, its rest set in, is one item."""
    _, o1, s1, o2, _, _, _ = LISTS[language]
    assert parent_cut(language, "outer", 400) == [f"- {o1} {s1}", f"- {o2}"]


def sub_pages(language: str) -> list[str]:
    """Three pages.

    Page 2 holds only sub-items at 72, the last with no end mark; page 3 opens on
    the next sub-item (lower case), then an outer item and a paragraph.
    """
    lead, o1, s1, o2, s2, close, _ = LISTS[language]
    d = pages(3)
    d.add_text(label=DocItemLabel.TEXT, text=lead, prov=placed(1, 54, 680, width=400))
    one = d.add_list_group()
    d.add_list_item(text=o1, parent=one, prov=placed(1, 54, 700))
    d.add_list_item(text=s1, parent=one, prov=placed(1, 72, 714))
    two = d.add_list_group()
    d.add_list_item(text=s2, parent=two, prov=placed(2, 72, 60))
    d.add_list_item(text=s1, parent=two, prov=placed(2, 72, 74))
    three = d.add_list_group()
    d.add_list_item(text=s2, parent=three, prov=placed(3, 72, 60))
    d.add_list_item(text=o2, parent=three, prov=placed(3, 54, 74))
    d.add_text(label=DocItemLabel.TEXT, text=close, prov=placed(3, 54, 100, width=400))
    return lines(d, language)


@pytest.mark.parametrize("language", LANGS)
def test_sibling_sub_items_across_a_page_after_a_page_of_sub_items_alone(
    language: str,
) -> None:
    """Page 2 has no edge to read the indents off: the sibling is not the rest."""
    _, o1, s1, o2, s2, _, _ = LISTS[language]
    assert sub_pages(language) == [
        f"- {o1}",
        f"    - {s1}",
        f"    - {s2}",
        f"    - {s1}",
        f"    - {s2}",
        f"- {o2}",
    ]


@pytest.mark.parametrize("language", LANGS)
def test_a_sub_item_on_a_page_of_sub_items_alone_is_no_first_half(
    language: str,
) -> None:
    """Page 2 holds only sub-items at 69; page 3 opens on one more sub-item, then an outer item."""
    lead, o1, s1, o2, s2, close, s3 = LISTS[language]
    d = pages(3)
    d.add_text(label=DocItemLabel.TEXT, text=lead, prov=placed(1, 51, 680))
    one = d.add_list_group()
    d.add_list_item(text=o1, parent=one, prov=placed(1, 51, 700))
    d.add_list_item(text=s1, parent=one, prov=placed(1, 69, 714))
    two = d.add_list_group()
    d.add_list_item(text=s2, parent=two, prov=placed(2, 69, 60))
    d.add_list_item(text=s3, parent=two, prov=placed(2, 69, 74))
    three = d.add_list_group()
    d.add_list_item(text=s1, parent=three, prov=placed(3, 69, 60))
    d.add_list_item(text=o2, parent=three, prov=placed(3, 51, 74))
    d.add_text(label=DocItemLabel.TEXT, text=close, prov=placed(3, 51, 100))
    got = lines(d, language)
    assert not any(s3 in one and s1 in one for one in got), got


@pytest.mark.parametrize("language", LANGS)
def test_a_cut_sub_item_whose_rest_opens_a_page_of_sub_items_is_not_joined(
    language: str,
) -> None:
    """Without an edge to read the rest's indent off, nothing says it hangs."""
    lead, o1, s1, o2, s2, _, _ = LISTS[language]
    d = pages(2)
    d.add_text(label=DocItemLabel.TEXT, text=lead, prov=placed(1, 54, 680, width=400))
    one = d.add_list_group()
    d.add_list_item(text=o1, parent=one, prov=placed(1, 54, 700, width=400))
    d.add_list_item(text=s1, parent=one, prov=placed(1, 72, 714, width=400))
    two = d.add_list_group()
    d.add_list_item(text=s2, parent=two, prov=placed(2, 90, 60))
    d.add_list_item(text=o2, parent=two, prov=placed(2, 72, 74))
    assert f"    - {s1} {s2}" not in lines(d, language)
