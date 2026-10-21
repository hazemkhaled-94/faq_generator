"""A heading holding ' > ' reads back as one heading from section_path."""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import (
    DoclingDocument,
    ProvenanceItem,
    TableCell,
    TableData,
)
from factories import passage, word_chunker

from extraction.extractors.table import _nearest
from extraction.links import _segments
from preprocessing.chunking.passages import PassageBuilder, chunks_of


def on(page: int, top: float = 100.0, left: float = 54) -> ProvenanceItem:
    """Provenance on one page, a line high."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=left, t=top, r=500, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def pages(count: int) -> DoclingDocument:
    """An empty document of `count` A4 pages."""
    document = DoclingDocument(name="t")
    for page in range(1, count + 1):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    return document


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


@pytest.mark.parametrize(
    ("top", "heading"),
    [("Auslandszahlungen", "Zahlungen > 50.000 EUR"), ("Shipping", "Orders > 50 EUR")],
)
def test_a_heading_holding_the_trail_separator_reads_back_as_one_heading(
    top, heading
) -> None:
    """Readers split section_path on ' > ': a heading holding one becomes two."""
    document = pages(1)
    document.add_heading(text=top, level=1, prov=on(1, 40))
    document.add_heading(text=heading, level=2, prov=on(1, 60))
    document.add_table(
        data=grid(("Art", "Entgelt"), ("SEPA", "0,00 EUR"), ("SWIFT", "25,00 EUR")),
        prov=on(1, 80),
    )
    tidy, chunks = chunks_of(document, word_chunker(200), "de")
    stored = passage(
        sentences=[],
        section_path=PassageBuilder._passage(tidy, 1, chunks[0]).section_path,
    )

    assert _segments(stored) == [top, heading]
    assert _nearest(stored) == heading
