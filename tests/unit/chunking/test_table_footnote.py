"""preprocessing-1: a footnote attached to a table must reach a passage."""

from __future__ import annotations

import pytest
from docling_core.types.doc.document import (
    DoclingDocument,
    TableCell,
    TableData,
)
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of


def grid(*rows: tuple[str, ...]) -> TableData:
    """A table of these rows, the first a header row."""
    cells = [
        TableCell(
            text=text,
            start_row_offset_idx=r,
            end_row_offset_idx=r + 1,
            start_col_offset_idx=c,
            end_col_offset_idx=c + 1,
            column_header=r == 0,
        )
        for r, row in enumerate(rows)
        for c, text in enumerate(row)
    ]
    return TableData(num_rows=len(rows), num_cols=len(rows[0]), table_cells=cells)


def footnoted(title: str, rows, note: str) -> DoclingDocument:
    """A heading and a table whose footnote the converter attached to it."""
    document = DoclingDocument(name="t")
    document.add_heading(text=title, level=1)
    table = document.add_table(data=grid(*rows))
    foot = document.add_text(label=DocItemLabel.FOOTNOTE, text=note, parent=table)
    table.footnotes.append(foot.get_ref())
    return document


@pytest.mark.parametrize(
    ("title", "rows", "note", "needle"),
    [
        (
            "Kontoführung",
            (("Kontomodell", "Grundpreis"), ("Basis", "4,90 EUR¹")),
            "¹ Entfällt bei einem monatlichen Geldeingang von mindestens 1.000 EUR.",
            "mindestens 1.000 EUR",
        ),
        (
            "Delivery",
            (("Method", "Price"), ("Standard", "4.95 EUR*")),
            "* Free for orders over 50 EUR.",
            "Free for orders over 50 EUR",
        ),
        (
            "Versand",
            (("Art", "Preis"), ("Standard", "4,95 EUR¹")),
            "¹ Kostenlos ab 50 EUR Bestellwert.",
            "Kostenlos ab 50 EUR",
        ),
        (
            "Account fees",
            (("Account", "Monthly fee"), ("Basic", "4.90 EUR*")),
            "* Waived with a monthly deposit of 1,000 EUR.",
            "Waived with a monthly deposit",
        ),
    ],
)
def test_a_footnote_attached_to_a_table_is_passage_text(
    title, rows, note, needle
) -> None:
    """The mark in the table is meaningless without the note it points to."""
    document = footnoted(title, rows, note)

    _, chunks = chunks_of(document, word_chunker(200), None)

    assert any(needle in chunk.text for chunk in chunks), [c.text for c in chunks]
