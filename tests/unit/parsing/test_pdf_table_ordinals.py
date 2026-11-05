"""A raised ordinal inside a table cell joins its number, as in a paragraph.

A converter writes a raised "st" or "er" as a word of its own; a fee table's
"valid from 1st July" must read as the page prints it, or every fact drawn
from the grid gains a stray word.
"""

from __future__ import annotations

import pymupdf
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import DoclingDocument, TableCell, TableData
from test_strikethrough import BASELINE, HEIGHT, LEFT, WIDTH, provenance, raised

from preprocessing.parsing.pipelines.pdf import _rejoined


def ordinal_page(before: str, suffix: str, after: str) -> bytes:
    """A one-page PDF printing a number, a raised suffix and the rest."""
    pdf = pymupdf.open()
    page = pdf.new_page(width=WIDTH, height=HEIGHT)
    raised(page, before, suffix, after)
    return pdf.tobytes()


def table_of(text: str) -> DoclingDocument:
    """A converted page whose one table cell covers the printed line."""
    converted = DoclingDocument(name="t")
    converted.add_page(page_no=1, size=Size(width=WIDTH, height=HEIGHT))
    edges = (LEFT - 1, BASELINE - 12, LEFT + 200, BASELINE + 3)
    cell = TableCell(
        text=text,
        bbox=BoundingBox(
            l=edges[0],
            t=edges[1],
            r=edges[2],
            b=edges[3],
            coord_origin=CoordOrigin.TOPLEFT,
        ),
        start_row_offset_idx=0,
        end_row_offset_idx=1,
        start_col_offset_idx=0,
        end_col_offset_idx=1,
    )
    converted.add_table(
        data=TableData(num_rows=1, num_cols=1, table_cells=[cell]),
        prov=provenance(edges),
    )
    return converted


def test_a_raised_ordinal_in_a_table_cell_joins_its_number() -> None:
    """English "1st" and French "1er" in a grid read as the page prints them."""
    for before, suffix, after, written, joined in (
        ("Valid from 1", "st", "July", "Valid from 1 st July", "Valid from 1st July"),
        (
            "Valable du 1",
            "er",
            "juillet",
            "Valable du 1 er juillet",
            "Valable du 1er juillet",
        ),
    ):
        data = ordinal_page(before, suffix, after)

        (cell,) = _rejoined(table_of(written), data).tables[0].data.table_cells

        assert cell.text == joined
