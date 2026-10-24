"""Lists and column breaks read from the right in a right-to-left script.

A right-to-left list is aligned on its right edge, so the left edges of its
items say how long each one is and nothing about its level; an item indented
under another is set in from the right. The next column of a right-to-left
page lies to the left of the one before it.
"""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.reference import ProvenanceItem
from docling_core.types.doc.document import DoclingDocument
from factories import word_chunker

from nlp.text import right_to_left
from preprocessing.chunking.furniture import _broken
from preprocessing.chunking.passages import chunks_of

SAMPLES = {
    "ar": [
        "يجوز للعميل إغلاق الحساب كتابيا في أي وقت",
        "يرسل البنك إشعارا بالإغلاق",
        "تعاد الأرصدة المتبقية إلى العميل خلال عشرة أيام من تاريخ الإغلاق",
        "لا تسترد الرسوم المدفوعة",
    ],
    "he": [
        "הלקוח רשאי לסגור את החשבון בכתב בכל עת",
        "הבנק שולח הודעה על הסגירה",
        "יתרות שנותרו יוחזרו ללקוח תוך עשרה ימים ממועד הסגירה",
        "דמי ניהול ששולמו אינם מוחזרים",
    ],
}
LEFT_TO_RIGHT = [
    "The customer may close the account in writing at any time",
    "The bank sends a notice of the closure",
    "Remaining balances are returned to the customer within ten days of closing",
    "Fees already paid are not refunded",
]


def at(right: float, top: float, width: float) -> ProvenanceItem:
    """A line set against its right edge: its left edge says how long it is."""
    return ProvenanceItem(
        page_no=1,
        bbox=BoundingBox(
            l=right - width,
            t=top,
            r=right,
            b=top + 10,
            coord_origin=CoordOrigin.TOPLEFT,
        ),
        charspan=(0, 1),
    )


def listed(
    texts: list[str], rights: list[float], widths: list[float]
) -> DoclingDocument:
    """One list, each item against its own right edge."""
    document = DoclingDocument(name="t")
    document.add_page(page_no=1, size=Size(width=595, height=842))
    group = document.add_list_group()
    for k, (text, right, width) in enumerate(zip(texts, rights, widths, strict=True)):
        document.add_list_item(
            text=text, parent=group, prov=at(right, 100 + 14 * k, width)
        )
    return document


def indents(document: DoclingDocument) -> list[bool]:
    """Which lines of the cut list are indented."""
    _, chunks = chunks_of(document, word_chunker(400), None)
    return [line.startswith("    ") for line in chunks[0].text.splitlines() if line]


@pytest.mark.parametrize("language", sorted(SAMPLES))
def test_a_right_aligned_list_of_long_and_short_siblings_stays_flat(
    language: str,
) -> None:
    """A short item after a long one starts further right and is no sub-item."""
    document = listed(SAMPLES[language], [540] * 4, [300, 150, 400, 160])

    assert indents(document) == [False] * 4


@pytest.mark.parametrize("language", sorted(SAMPLES))
def test_an_item_set_in_from_the_right_nests(language: str) -> None:
    """The sub-items end 20 points before the outer items' right edge."""
    document = listed(SAMPLES[language], [540, 520, 520, 540], [300, 250, 260, 300])

    assert indents(document) == [False, True, True, False]


def test_a_left_aligned_list_is_read_as_before() -> None:
    """German and English text keeps its left edge as the level."""
    document = listed(LEFT_TO_RIGHT, [454, 474, 474, 454], [400, 400, 400, 400])

    assert indents(document) == [False, True, True, False]


@pytest.mark.parametrize("language", sorted(SAMPLES))
def test_the_next_column_of_a_right_to_left_page_lies_to_its_left(
    language: str,
) -> None:
    """A block wholly left of the one before it starts the next column."""
    first, second = at(540, 700, 240), at(280, 100, 240)

    assert _broken(first, second, right_to_left(SAMPLES[language][0]))
    assert not _broken(second, first, right_to_left(SAMPLES[language][0]))


def test_the_next_column_of_a_left_to_right_page_lies_to_its_right() -> None:
    """Unchanged: a block wholly right of the one before it."""
    first, second = at(280, 700, 240), at(540, 100, 240)

    assert _broken(first, second, right_to_left(LEFT_TO_RIGHT[0]))
    assert not _broken(second, first, right_to_left(LEFT_TO_RIGHT[0]))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (SAMPLES["ar"][0], True),
        (SAMPLES["he"][0], True),
        (LEFT_TO_RIGHT[0], False),
        ("Die Bank erhebt ein Entgelt von 5 EUR", False),
        ("12 345", False),
        ("", False),
    ],
)
def test_the_direction_is_the_majority_of_the_letters_bidi_class(
    text: str, expected: bool
) -> None:
    """Digits and punctuation vote for neither."""
    assert right_to_left(text) is expected
