"""A list item a page break cuts mid-sentence stays two halves.

Docling 2.141 starts a new list group on every page, and the rest of an item
the page cut comes out as that list's first item, with no marker of its own.
The sentence join of `tidied` takes only a paragraph as the second half, so
the item ends mid-sentence and its rest is an item of its own, printed under
a dash. Over four football PDFs, 7 such cuts, 0 joined. Bank, shop and
public-administration items in German, English, French and Greek.
"""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of

#: (language, lead-in, the item's first half, its rest, the next item)
ITEMS = {
    "de": (
        "Die Bank erstattet:",
        "die Kosten der Prüfung, die von der Bank",
        "übernommen werden, wenn der Antrag bewilligt wird,",
        "die Porto- und Versandkosten.",
    ),
    "en": (
        "The shop refunds:",
        "the cost of returning goods that the shop",
        "delivered damaged or incomplete,",
        "the original delivery charge.",
    ),
    "fr": (
        "Le service rembourse :",
        "les frais de dossier que le demandeur a",
        "payés avant le rejet de sa demande,",
        "les frais d'envoi du courrier.",
    ),
    "el": (
        "Η υπηρεσία επιστρέφει:",
        "τα τέλη φακέλου που ο αιτών έχει",
        "καταβάλει πριν από την απόρριψη,",
        "τα έξοδα αποστολής.",
    ),
}


def placed(page: int, top: float, left: float = 54) -> ProvenanceItem:
    """A box a line high from the page's top, its left edge at `left`."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=left, t=top, r=400, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def passage(language: str, rest_at: float = 72, marker: str = "") -> str:
    """The passage text of a list cut at a page break, as the converter hands it over.

    The first half and the next item start at the marker's edge, 54 points;
    the rest, the text of the cut item running on, at `rest_at`.
    """
    lead, first, rest, after = ITEMS[language]
    document = DoclingDocument(name="terms")
    for page in (1, 2):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    document.add_text(label=DocItemLabel.TEXT, text=lead, prov=placed(1, 680))
    page_one = document.add_list_group()
    document.add_list_item(
        text=first, marker="a)", parent=page_one, prov=placed(1, 700)
    )
    page_two = document.add_list_group()
    document.add_list_item(
        text=rest, marker=marker, parent=page_two, prov=placed(2, 60, rest_at)
    )
    document.add_list_item(text=after, marker="b)", parent=page_two, prov=placed(2, 74))
    document.add_text(label=DocItemLabel.TEXT, text=lead, prov=placed(2, 120, 54))
    _, chunks = chunks_of(document, word_chunker(200), language)
    return chunks[0].text


def bullets(language: str, second_at: float) -> list[str]:
    """Marker-less bullets, no end marks, a page apart, the last two at `second_at`."""
    _, first, rest, after = ITEMS[language]
    document = DoclingDocument(name="terms")
    for page in (1, 2):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    page_one = document.add_list_group()
    document.add_list_item(text=first, parent=page_one, prov=placed(1, 700))
    page_two = document.add_list_group()
    document.add_list_item(text=rest, parent=page_two, prov=placed(2, 60, second_at))
    document.add_list_item(text=after, parent=page_two, prov=placed(2, 74, second_at))
    _, chunks = chunks_of(document, word_chunker(200), language)
    return chunks[0].text.splitlines()


@pytest.mark.parametrize("language", sorted(ITEMS))
def test_the_rest_of_an_item_cut_at_a_page_joins_it(language: str) -> None:
    """The item reads as the one sentence it is printed as."""
    _, first, rest, _ = ITEMS[language]
    assert f"{first} {rest}" in passage(language), passage(language)


@pytest.mark.parametrize("language", sorted(ITEMS))
def test_the_rest_of_an_item_is_no_item_of_its_own(language: str) -> None:
    """No line of the passage opens on the rest under a dash."""
    _, _, rest, _ = ITEMS[language]
    assert f"- {rest}" not in passage(language).splitlines(), passage(language)


@pytest.mark.parametrize("language", sorted(ITEMS))
def test_a_rest_at_its_next_items_indent_is_an_item_of_its_own(
    language: str,
) -> None:
    """Without the hanging indent nothing tells a rest from a separate bullet."""
    _, first, rest, _ = ITEMS[language]
    assert f"{first} {rest}" not in passage(language, rest_at=54)


@pytest.mark.parametrize("language", sorted(ITEMS))
def test_bullets_without_markers_at_one_indent_across_a_page_stay_apart(
    language: str,
) -> None:
    """A converter that leaves every bullet without a marker splits no sentence."""
    _, _, rest, after = ITEMS[language]
    lines = bullets(language, second_at=54)
    assert f"- {rest}" in lines and f"- {after}" in lines, lines


@pytest.mark.parametrize("language", sorted(ITEMS))
def test_a_sub_item_at_the_indent_of_the_item_after_it_stays_apart(
    language: str,
) -> None:
    """Both bullets of page 2 are set in alike: the first is not a rest."""
    _, first, rest, _ = ITEMS[language]
    assert f"{first} {rest}" not in " ".join(bullets(language, second_at=72))


@pytest.mark.parametrize("language", sorted(ITEMS))
def test_a_joined_rest_takes_no_part_in_the_depth_of_its_list(language: str) -> None:
    """The rest goes to the furniture layer: the list's levels are read without it."""
    lead, first, rest, after = ITEMS[language]
    document = DoclingDocument(name="terms")
    for page in (1, 2):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    page_one = document.add_list_group()
    document.add_list_item(text=lead, parent=page_one, prov=placed(1, 690, 54))
    document.add_list_item(
        text=first, marker="a)", parent=page_one, prov=placed(1, 710, 72)
    )
    page_two = document.add_list_group()
    document.add_list_item(text=rest, parent=page_two, prov=placed(2, 60, 90))
    document.add_list_item(
        text=after, marker="b)", parent=page_two, prov=placed(2, 74, 72)
    )
    document.add_text(label=DocItemLabel.TEXT, text=lead, prov=placed(1, 680, 54))
    document.add_text(label=DocItemLabel.TEXT, text=lead, prov=placed(2, 120, 54))
    _, chunks = chunks_of(document, word_chunker(200), language)
    assert chunks[0].text.splitlines()[:3] == [
        f"- {lead}",
        f"    - a) {first} {rest}",
        f"    - b) {after}",
    ], chunks[0].text
