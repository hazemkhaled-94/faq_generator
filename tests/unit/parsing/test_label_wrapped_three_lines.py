"""A table label wrapped over three lines is joined line by line."""

from __future__ import annotations

import pytest
from docling_core.types.doc.document import DoclingDocument, TableCell, TableData

from preprocessing.parsing.pipelines.pdf import _tabled


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


def rows_after(*rows: tuple[str, ...]) -> list[tuple[str, ...]]:
    """The rows `_tabled` leaves of one table."""
    document = DoclingDocument(name="t")
    document.add_table(data=grid(*rows))
    table = _tabled(document).tables[0]
    by: dict[int, dict[int, str]] = {}
    for cell in table.data.table_cells:
        by.setdefault(cell.start_row_offset_idx, {})[cell.start_col_offset_idx] = (
            cell.text
        )
    return [tuple(by[r][c] for c in sorted(by[r])) for r in sorted(by)]


@pytest.mark.parametrize(
    ("table", "label", "next_label"),
    [
        (
            (
                ("Option", "Price", "Time"),
                ("same day delivery (London", "14.95 GBP", "same day"),
                ("and Manchester", "", ""),
                ("only)", "", ""),
                ("next day", "9.95 GBP", "1 day"),
            ),
            "same day delivery (London and Manchester only)",
            "next day",
        ),
        (
            (
                ("Leistung", "Entgelt"),
                ("Bargeldauszahlung am Schalter", "5,00 EUR"),
                ("ohne Karte und", ""),
                ("ohne Ausweis", ""),
                ("Kontoauszug", "1,00 EUR"),
            ),
            "Bargeldauszahlung am Schalter ohne Karte und ohne Ausweis",
            "Kontoauszug",
        ),
    ],
)
def test_a_label_wrapped_over_three_lines_is_read_whole(
    table, label, next_label
) -> None:
    """The second tail sees a row gone above it and is glued below or left alone."""
    read = rows_after(*table)

    assert [row[0] for row in read[1:]] == [label, next_label], read
