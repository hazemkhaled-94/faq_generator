"""A passage prints the list markers the document prints and invents none.

A numbered paragraph the converter puts into the same list group as lettered
items has no marker of its own. The Markdown serializer numbered it by its
place in the group, so the passage read `4. 3 Die Geldstrafe ...` with a number
the document never printed.
"""

from __future__ import annotations

import pytest
from docling_core.types.doc.document import DoclingDocument
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of

CASES = {
    "de": (
        [
            "Verbot der Ausübung jeglicher Tätigkeit;",
            "Widerruf von Titeln;",
            "Sozialarbeit.",
        ],
        [
            "3 Die Gebühr beträgt mindestens 100 Euro.",
            "4 Die Maßnahmen können verbunden werden.",
        ],
    ),
    "en": (
        ["a ban on any activity;", "withdrawal of a title;", "community service."],
        ["3 The fee is at least 100 euro.", "4 The measures may be combined."],
    ),
    "fr": (
        [
            "interdiction d'exercer toute activité;",
            "retrait d'un titre;",
            "travail d'intérêt général.",
        ],
        [
            "3 Les frais s'élèvent à au moins 100 euros.",
            "4 Les mesures peuvent être combinées.",
        ],
    ),
    "el": (
        ["απαγόρευση κάθε δραστηριότητας;", "ανάκληση τίτλου;", "κοινωφελής εργασία."],
        [
            "3 Το τέλος είναι τουλάχιστον 100 ευρώ.",
            "4 Τα μέτρα μπορούν να συνδυαστούν.",
        ],
    ),
}


def cut(document: DoclingDocument, language: str) -> list[str]:
    """The lines of every chunk's text."""
    _, chunks = chunks_of(document, word_chunker(200), language)
    return [line for chunk in chunks for line in chunk.text.splitlines()]


@pytest.mark.parametrize("language", sorted(CASES))
def test_an_item_without_a_marker_prints_none_of_its_position(language: str) -> None:
    """Lettered items keep their letters; the numbered paragraphs print as they are."""
    lettered, numbered = CASES[language]
    document = DoclingDocument(name="regulations")
    document.add_heading("Artikel 6", level=1)
    group = document.add_list_group()
    for marker, text in zip(("f.", "g.", "h."), lettered, strict=True):
        document.add_list_item(text, enumerated=True, marker=marker, parent=group)
    for text in numbered:
        document.add_list_item(text, enumerated=False, marker="", parent=group)

    lines = cut(document, language)

    assert [line for line in lines if line.startswith(("4. 3", "5. 4"))] == []
    assert any(
        line.endswith(numbered[0]) and not line.startswith("4.") for line in lines
    )
    assert any(line.startswith(("- f.", "f.")) for line in lines)


@pytest.mark.parametrize("language", sorted(CASES))
def test_a_list_that_prints_its_numbers_keeps_them(language: str) -> None:
    """Items marked `1.` and `2.` read `1.` and `2.`."""
    first, second = CASES[language][0][:2]
    document = DoclingDocument(name="steps")
    document.add_heading("Steps", level=1)
    group = document.add_list_group()
    document.add_list_item(first, enumerated=True, marker="1.", parent=group)
    document.add_list_item(second, enumerated=True, marker="2.", parent=group)

    lines = cut(document, language)

    assert [line for line in lines if line.startswith(("1.", "2."))] == [
        f"1. {first}",
        f"2. {second}",
    ]
