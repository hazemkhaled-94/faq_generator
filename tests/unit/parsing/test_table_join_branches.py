"""Which pieces of a broken table join, on the shapes the converter gives rarely.

A headerless table two pages after one of its width is not its rest: a page
between them prints something else, and joining them would price one
schedule's rows under another's header. A running head or a page number
between the two halves is page furniture, no text between them, and does
not part them.
"""

from __future__ import annotations

from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.labels import DocItemLabel
from test_tables import FEES, grid, on, paged, rows

from preprocessing.parsing.pipelines.pdf import _tabled


def test_a_headerless_table_two_pages_on_is_a_table_of_its_own() -> None:
    """Page 1's fees and page 3's rows stay two tables."""
    document = paged(3)
    document.add_table(data=grid(*FEES), prov=on(1))
    document.add_table(data=grid(("Kontoauszug", "1 EUR"), header=False), prov=on(3))

    assert rows(_tabled(document)) == [
        [["Service", "Fee"], ["Card", "5 EUR"], ["Transfer", "2 EUR"]],
        [["Kontoauszug", "1 EUR"]],
    ]


def test_page_furniture_between_the_halves_of_a_table_does_not_part_them() -> None:
    """A page number at the foot of page 1 is not text between the halves."""
    document = paged(2)
    document.add_table(data=grid(*FEES), prov=on(1))
    document.add_text(
        label=DocItemLabel.PAGE_FOOTER,
        text="Seite 1 von 2",
        prov=on(1),
        content_layer=ContentLayer.FURNITURE,
    )
    document.add_table(data=grid(("Cash", "3 EUR"), header=False), prov=on(2))

    assert rows(_tabled(document)) == [
        [
            ["Service", "Fee"],
            ["Card", "5 EUR"],
            ["Transfer", "2 EUR"],
            ["Cash", "3 EUR"],
        ]
    ]
