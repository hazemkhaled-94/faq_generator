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
        [
            "Artikel 9 Disziplinarische",
            "Tragweite",
            "von",
            "Schiedsrichterentscheidungen",
        ],
        "Auf dem Spielfeld getroffene Entscheidungen sind endgültig.",
    ),
    "en": (
        ["Article 9 Disciplinary", "scope", "of", "referee decisions"],
        "Decisions taken by the referee on the field of play are final.",
    ),
    "fr": (
        ["Article 9 Portée", "disciplinaire", "des", "décisions arbitrales"],
        "Les décisions prises par l'arbitre sur le terrain sont définitives.",
    ),
    "el": (
        ["Άρθρο 9 Πειθαρχική", "εμβέλεια", "των", "αποφάσεων διαιτησίας"],
        "Οι αποφάσεις του διαιτητή στον αγωνιστικό χώρο είναι οριστικές.",
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


def trails(headings: list[tuple[str, float, float]], body: str) -> list[str]:
    """The trail of each passage of a page of the headings, then the body.

    Each heading is (text, left, top); it is set 5 points a letter wide.
    """
    document = DoclingDocument(name="regulations")
    document.add_page(page_no=1, size=Size(width=595, height=842))
    for text, left, top in headings:
        document.add_heading(
            text=text, level=2, prov=box(left, top, left + 5 * len(text))
        )
    document.add_text(label=DocItemLabel.TEXT, text=body, prov=box(54, 300, 500))
    _, chunks = chunks_of(document, word_chunker(80), None)
    return [" > ".join(chunk.meta.headings or []) for chunk in chunks]


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

    assert trails(one_line(pieces), body) == [" ".join(pieces)]


@pytest.mark.parametrize("language", sorted(CASES))
def test_two_headings_on_separate_lines_stay_apart(language: str) -> None:
    """Siblings one below the other are two headings."""
    pieces, body = CASES[language]
    stacked = [(pieces[0], 54.0, 100.0), (pieces[3], 54.0, 124.0)]

    assert trails(stacked, body) == [pieces[3]]


@pytest.mark.parametrize("language", sorted(CASES))
def test_headings_of_two_columns_on_one_line_stay_apart(language: str) -> None:
    """Two columns' headings share a line and are a column apart."""
    pieces, body = CASES[language]
    columns = [(pieces[0], 54.0, 100.0), (pieces[3], 400.0, 100.0)]

    assert trails(columns, body) == [pieces[3]]


@pytest.mark.parametrize("language", sorted(CASES))
def test_a_heading_that_wraps_onto_the_next_line_is_read_whole(language: str) -> None:
    """The last fragment starts the line below, left of where the first started."""
    pieces, body = CASES[language]
    placed = one_line(pieces[:3]) + [(pieces[3], 54.0, 113.0)]

    assert trails(placed, body) == [" ".join(pieces)]
