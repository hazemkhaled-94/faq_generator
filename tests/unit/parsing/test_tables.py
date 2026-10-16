"""Tables the converter broke at a page or inside a multi-line cell, mended.

The converter starts a new table where a table runs onto the next page, and
the continuation has no header; and it reads a cell wrapped over two lines as
two rows. Both are read off the grid's structure, never off its words.
"""

from __future__ import annotations

from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.document import (
    DoclingDocument,
    ProvenanceItem,
    TableCell,
    TableData,
)
from docling_core.types.doc.labels import DocItemLabel

from preprocessing.parsing.pipelines.pdf import _tabled


def on(page: int) -> ProvenanceItem:
    """Provenance on one page."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(l=54, t=100, r=500, b=300, coord_origin=CoordOrigin.TOPLEFT),
        charspan=(0, 1),
    )


def grid(*rows: tuple[str, ...], header: bool = True) -> TableData:
    """A table of these rows, the first a header row when `header`."""
    cells = [
        TableCell(
            text=text,
            start_row_offset_idx=r,
            end_row_offset_idx=r + 1,
            start_col_offset_idx=c,
            end_col_offset_idx=c + 1,
            column_header=header and r == 0,
        )
        for r, row in enumerate(rows)
        for c, text in enumerate(row)
    ]
    return TableData(num_rows=len(rows), num_cols=len(rows[0]), table_cells=cells)


def paged(count: int) -> DoclingDocument:
    """An empty document of `count` pages."""
    document = DoclingDocument(name="fees")
    for page in range(1, count + 1):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    return document


def rows(document: DoclingDocument) -> list[list[list[str]]]:
    """Each body table's rows, as text."""
    return [
        [[cell.text for cell in row] for row in table.data.grid]
        for table in document.tables
        if table.content_layer == ContentLayer.BODY
    ]


FEES = (("Service", "Fee"), ("Card", "5 EUR"), ("Transfer", "2 EUR"))


def test_a_table_running_onto_the_next_page_is_one_table() -> None:
    """The second half has no header: it is the first half's rest."""
    document = paged(2)
    document.add_table(data=grid(*FEES), prov=on(1))
    document.add_table(data=grid(("Cash", "3 EUR"), header=False), prov=on(2))

    assert rows(_tabled(document)) == [
        [
            ["Service", "Fee"],
            ["Card", "5 EUR"],
            ["Transfer", "2 EUR"],
            ["Cash", "3 EUR"],
        ]
    ]


def test_a_table_with_its_own_header_is_a_table_of_its_own() -> None:
    """A header says a new table starts, whatever its width."""
    document = paged(2)
    document.add_table(data=grid(*FEES), prov=on(1))
    document.add_table(data=grid(("Limit", "Amount"), ("Daily", "500 EUR")), prov=on(2))

    assert len(rows(_tabled(document))) == 2


def test_tables_of_two_widths_or_with_text_between_are_two_tables() -> None:
    """Same width and nothing in between is what a continuation is."""
    wider = paged(2)
    wider.add_table(data=grid(*FEES), prov=on(1))
    wider.add_table(data=grid(("Cash", "3 EUR", "daily"), header=False), prov=on(2))
    apart = paged(2)
    apart.add_table(data=grid(*FEES), prov=on(1))
    apart.add_text(label=DocItemLabel.TEXT, text="Limits apply.", prov=on(2))
    apart.add_table(data=grid(("Cash", "3 EUR"), header=False), prov=on(2))

    assert len(rows(_tabled(wider))) == 2
    assert len(rows(_tabled(apart))) == 2


def test_a_cell_wrapped_onto_a_row_of_its_own_rejoins_the_row_above() -> None:
    """No label of its own, and it carries on in lower case: the rest of a cell."""
    document = paged(1)
    document.add_table(
        data=grid(
            ("Offence", "Restart"),
            ("Encroachment", "a free kick taken"),
            ("", "from where it happened"),
        ),
        prov=on(1),
    )

    assert rows(_tabled(document)) == [
        [
            ["Offence", "Restart"],
            ["Encroachment", "a free kick taken from where it happened"],
        ]
    ]


def test_a_row_whose_label_did_not_span_keeps_its_own_values() -> None:
    """`Credit` under `Debit` is a second row, not the rest of the first."""
    document = paged(1)
    document.add_table(
        data=grid(
            ("Card", "Kind", "Fee"), ("Cards", "Debit", "5"), ("", "Credit", "10")
        ),
        prov=on(1),
    )

    assert rows(_tabled(document))[0][2] == ["", "Credit", "10"]


def test_a_wrapped_label_whose_head_stands_on_its_own_row_rejoins_it() -> None:
    """A label alone on a row, its rest opening the next in lower case."""
    document = paged(1)
    document.add_table(
        data=grid(
            ("Offence", "Restart"),
            ("Encroachment only", ""),
            ("by the defending team", "the kick is retaken"),
        ),
        prov=on(1),
    )

    assert rows(_tabled(document)) == [
        [
            ["Offence", "Restart"],
            ["Encroachment only by the defending team", "the kick is retaken"],
        ]
    ]


def test_a_cell_ending_on_a_colon_goes_on_in_the_row_below() -> None:
    """A colon in a cell opens what follows; it ends nothing."""
    document = paged(1)
    document.add_table(
        data=grid(("Case", "Outcome"), ("Missed", "Impact:"), ("", "goal kick")),
        prov=on(1),
    )

    assert rows(_tabled(document))[0][1] == ["Missed", "Impact: goal kick"]


def test_a_picture_between_the_halves_of_a_table_does_not_part_them() -> None:
    """A page's decoration can sit between a table and its rest."""
    document = paged(2)
    document.add_table(data=grid(*FEES), prov=on(1))
    document.add_picture(prov=on(2))
    document.add_table(data=grid(("Cash", "3 EUR"), header=False), prov=on(2))

    assert len(rows(_tabled(document))) == 1
