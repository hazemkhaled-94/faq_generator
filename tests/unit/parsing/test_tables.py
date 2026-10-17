"""Tables the converter broke at a page or inside a multi-line cell, mended.

The converter starts a new table where a table runs onto the next page, and
the continuation has no header; and it reads a cell wrapped over two lines as
two rows. Both are read off the grid's structure, never off its words.
"""

from __future__ import annotations

import pymupdf
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.document import (
    DoclingDocument,
    ProvenanceItem,
    TableCell,
    TableData,
)
from docling_core.types.doc.labels import DocItemLabel

from preprocessing.parsing.pipelines.pdf import _repaired, _tabled


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


def test_a_cell_wrapped_at_a_hyphen_is_one_word() -> None:
    """The line break the hyphen marked is mended once the halves are joined."""
    document = paged(1)
    document.add_table(
        data=grid(
            ("Leistung", "Entgelt"),
            ("Girokonto", "monatlich, inklusive Kontofüh-"),
            ("", "rungsentgelt 4,90 EUR"),
        ),
        prov=on(1),
    )

    assert rows(_tabled(_repaired(document))) == [
        [
            ["Leistung", "Entgelt"],
            ["Girokonto", "monatlich, inklusive Kontoführungsentgelt 4,90 EUR"],
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


def test_a_row_a_spanning_cell_covers_is_never_joined() -> None:
    """A label spanning two rows holds both; joining one would cut it."""
    cells = [
        TableCell(
            text=text,
            start_row_offset_idx=r,
            end_row_offset_idx=r + 1,
            start_col_offset_idx=c,
            end_col_offset_idx=c + 1,
            column_header=r == 0,
        )
        for r, c, text in (
            (0, 0, "Card"),
            (0, 1, "Fee"),
            (1, 1, "a monthly fee"),
            (2, 1, "waived for students"),
        )
    ] + [
        TableCell(
            text="Debit",
            start_row_offset_idx=1,
            end_row_offset_idx=3,
            start_col_offset_idx=0,
            end_col_offset_idx=1,
            row_span=2,
        )
    ]
    document = paged(1)
    document.add_table(
        data=TableData(num_rows=3, num_cols=2, table_cells=cells), prov=on(1)
    )

    table = _tabled(document).tables[0].data

    assert table.num_rows == 3
    assert any(
        cell.text == "Debit" and cell.row_span == 2 for cell in table.table_cells
    )


# ── A continuation whose first row the converter took for a header ─────────

#: The type a fee schedule sets its header and its data in, as pymupdf's
#: built-in Helvetica faces.
HEADER, DATA = "hebo", "helv"


def typeset(*pages: list[tuple[tuple[str, ...], str]]) -> tuple[bytes, list]:
    """Prints each page's rows, each in its font, in two columns.

    Returns:
        The PDF, and each page's cell boxes by row and column, with a
        top-left origin.
    """
    pdf = pymupdf.open()
    boxes = []
    for printed in pages:
        page = pdf.new_page(width=595, height=842)
        placed = []
        for at, (row, font) in enumerate(printed):
            baseline = 120 + 20 * at
            placed.append([])
            for col, text in enumerate(row):
                left = 60 + 250 * col
                page.insert_text((left, baseline), text, fontname=font, fontsize=9)
                right = left + pymupdf.get_text_length(text, fontname=font, fontsize=9)
                placed[-1].append(
                    BoundingBox(
                        l=left,
                        t=baseline - 9,
                        r=right,
                        b=baseline + 3,
                        coord_origin=CoordOrigin.TOPLEFT,
                    )
                )
        boxes.append(placed)
    return pdf.tobytes(), boxes


def boxed(rows: tuple[tuple[str, ...], ...], boxes: list, header: bool) -> TableData:
    """A table of these rows, each cell in its printed box."""
    data = grid(*rows, header=header)
    for cell in data.table_cells:
        cell.bbox = boxes[cell.start_row_offset_idx][cell.start_col_offset_idx]
    return data


SCHEDULE = (
    ("Leistung", "Entgelt"),
    ("Girocard", "5,00 EUR"),
    ("Kreditkarte", "29 EUR"),
)
REST = (("Ersatzkarte", "15,00 EUR"), ("Bargeld am Automaten", "2,00 EUR"))


def schedule(
    rest_font: str, header_font: str = HEADER
) -> tuple[bytes, DoclingDocument]:
    """A fee schedule run onto page 2, its rest's first row flagged a header."""
    data, (first, second) = typeset(
        [(SCHEDULE[0], header_font), *((row, DATA) for row in SCHEDULE[1:])],
        [(REST[0], rest_font), (REST[1], DATA)],
    )
    document = paged(2)
    document.add_table(data=boxed(SCHEDULE, first, header=True), prov=on(1))
    document.add_table(data=boxed(REST, second, header=True), prov=on(2))
    return data, document


def test_a_rest_whose_first_data_row_is_flagged_a_header_joins_its_table() -> None:
    """The row is set as the schedule's data is, not as its header: it is data."""
    data, document = schedule(rest_font=DATA)

    assert rows(_tabled(document, data)) == [[list(row) for row in SCHEDULE + REST]]
    assert not any(
        cell.column_header
        for cell in document.tables[0].data.table_cells
        if cell.start_row_offset_idx > 0
    )


def test_a_rest_with_a_header_in_the_header_font_is_a_table_of_its_own() -> None:
    """A second table of the same width, its header set as the first's is."""
    data, document = schedule(rest_font=HEADER)

    assert len(rows(_tabled(document, data))) == 2


def test_a_rest_after_a_table_whose_header_is_set_as_its_data_stays_apart() -> None:
    """With header and data in one font, the font tells nothing apart."""
    data, document = schedule(rest_font=DATA, header_font=DATA)

    assert len(rows(_tabled(document, data))) == 2
