"""A heading the converter cut into words on one line is read whole.

A justified article heading comes out of the converter as several section
headers at one level, one per run of words, side by side on one line. Siblings
replace each other in the heading trail, so the article's passages were filed
under its last fragment alone and lost the article number.
"""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.reference import ProvenanceItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of

CASES = {
    "de": (
        ["Artikel 9 Haftung", "des", "Kontoinhabers", "bei Missbrauch"],
        "Die Bank haftet nicht für Schäden durch eine vom Kunden verschuldete Weitergabe.",
    ),
    "en": (
        ["Article 9 Liability", "of", "the account holder", "for misuse"],
        "The bank is not liable for losses caused by the customer passing on a code.",
    ),
    "fr": (
        ["Article 9 Responsabilité", "du", "titulaire du compte", "en cas d'abus"],
        "La banque ne répond pas des pertes dues à la transmission d'un code par le client.",
    ),
    "el": (
        [
            "Άρθρο 9 Ευθύνη",
            "του",
            "δικαιούχου του λογαριασμού",
            "σε περίπτωση κατάχρησης",
        ],
        "Η τράπεζα δεν ευθύνεται για ζημίες από τη μετάδοση κωδικού από τον πελάτη.",
    ),
}


def box(left: float, top: float, right: float) -> ProvenanceItem:
    """A line of text, 12 points high, from `left` to `right` at `top`."""
    return ProvenanceItem(
        page_no=1,
        bbox=BoundingBox(
            l=left, t=top, r=right, b=top + 12, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def trails(
    page: list[tuple[str, str, float, float]], body: str | None = None
) -> list[str]:
    """The trail of each passage of a page of items, in reading order.

    Each item is (kind, text, left, top), a `heading` or a `text`; it is set
    5 points a letter wide. The body, when given, closes the page.
    """
    document = DoclingDocument(name="regulations")
    document.add_page(page_no=1, size=Size(width=595, height=842))
    for kind, text, left, top in page:
        prov = box(left, top, left + 5 * len(text))
        if kind == "heading":
            document.add_heading(text=text, level=2, prov=prov)
        else:
            document.add_text(label=DocItemLabel.TEXT, text=text, prov=prov)
    if body:
        document.add_text(label=DocItemLabel.TEXT, text=body, prov=box(54, 300, 500))
    _, chunks = chunks_of(document, word_chunker(80), None)
    return [" > ".join(chunk.meta.headings or []) for chunk in chunks]


def headings(
    items: list[tuple[str, float, float]],
) -> list[tuple[str, str, float, float]]:
    """Headings (text, left, top) as page items."""
    return [("heading", text, left, top) for text, left, top in items]


def one_line(pieces: list[str]) -> list[tuple[str, float, float]]:
    """The pieces side by side on one line, a gap of 12 points between."""
    placed, left = [], 54.0
    for piece in pieces:
        placed.append((piece, left, 100.0))
        left += 5 * len(piece) + 12
    return placed


@pytest.mark.parametrize("language", sorted(CASES))
def test_a_heading_cut_into_words_on_one_line_heads_its_passage_whole(
    language: str,
) -> None:
    """The trail holds the whole heading, article number first."""
    pieces, body = CASES[language]

    assert trails(headings(one_line(pieces)), body) == [" ".join(pieces)]


@pytest.mark.parametrize("language", sorted(CASES))
def test_a_heading_that_wraps_onto_the_next_line_is_read_whole(language: str) -> None:
    """The last fragment starts the line below, under the line it continues."""
    pieces, body = CASES[language]
    placed = one_line(pieces[:3]) + [(pieces[3], 54.0, 113.0)]

    assert trails(headings(placed), body) == [" ".join(pieces)]


@pytest.mark.parametrize("language", sorted(CASES))
@pytest.mark.parametrize("below", [14.0, 21.0, 30.0])
def test_two_headings_one_below_the_other_stay_apart(
    language: str, below: float
) -> None:
    """A heading of one line under another is a sibling, however close."""
    pieces, body = CASES[language]
    stacked = [(pieces[0], 54.0, 100.0), (pieces[3], 54.0, 100.0 + below)]

    assert trails(headings(stacked), body) == [pieces[3]]


@pytest.mark.parametrize("language", sorted(CASES))
def test_the_headings_of_two_columns_stay_with_their_own_text(language: str) -> None:
    """A column's heading is followed by its text, so the next heading is not its rest."""
    pieces, body = CASES[language]
    page = [
        ("heading", pieces[0], 54.0, 100.0),
        ("text", body[:30], 54.0, 130.0),
        ("heading", pieces[3], 54.0 + 5 * len(pieces[0]) + 12, 100.0),
        ("text", body[:30].upper(), 330.0, 130.0),
    ]

    found = trails(page)

    assert pieces[0] in found[0] and pieces[3] not in found[0]
    assert found[-1].endswith(pieces[3])
