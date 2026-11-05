"""A footnote the converter attached to a table's rest reaches no passage.

A fee table running onto the next page comes out as two tables, and its
footnotes, printed under its end, are attached to the second. `_tabled` joins
the second into the first and moves it to the furniture layer; the footnotes
stay its children, so the chunker never visits them, and `_footnoted` reads
only the first table's. Bank, shop and public-administration notes in German,
English, French and Greek.
"""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import (
    DoclingDocument,
    ProvenanceItem,
    TableCell,
    TableData,
)
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of
from preprocessing.parsing.pipelines.pdf import _tabled

#: (language, header, rows on page 1, rows on page 2, footnote under the table's end)
TABLES = {
    "de": (
        ("Leistung", "Entgelt"),
        (("Kontoführung", "4,90 EUR"),),
        (("Ersatzkarte", "15,00 EUR"), ("Kontoauszug", "2,00 EUR")),
        "* Für Kunden unter 25 Jahren entfällt das Entgelt.",
    ),
    "en": (
        ("Service", "Charge"),
        (("Standard delivery", "4.90 EUR"),),
        (("Express delivery", "15.00 EUR"), ("Gift wrapping", "2.00 EUR")),
        "* Members pay no delivery charge on orders over 50 EUR.",
    ),
    "fr": (
        ("Démarche", "Frais"),
        (("Carte d'identité", "25 EUR"),),
        (("Passeport", "86 EUR"), ("Copie certifiée", "2 EUR")),
        "* Les demandeurs de moins de 18 ans sont exonérés.",
    ),
    "el": (
        ("Υπηρεσία", "Τέλος"),
        (("Δελτίο ταυτότητας", "25 EUR"),),
        (("Διαβατήριο", "86 EUR"), ("Επικυρωμένο αντίγραφο", "2 EUR")),
        "* Οι αιτούντες κάτω των 18 ετών απαλλάσσονται.",
    ),
}


def prov(page: int, top: float, high: float = 12) -> ProvenanceItem:
    """A box across the text block, from the page's top."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=60, t=top, r=500, b=top + high, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def grid(rows, top: float, header: bool) -> TableData:
    """The rows as cells a line apart, the first a header row if `header`."""
    cells = [
        TableCell(
            text=text,
            start_row_offset_idx=r,
            end_row_offset_idx=r + 1,
            start_col_offset_idx=c,
            end_col_offset_idx=c + 1,
            column_header=header and r == 0,
            bbox=BoundingBox(
                l=60 + 200 * c,
                t=top + 14 * r,
                r=240 + 200 * c,
                b=top + 14 * r + 12,
                coord_origin=CoordOrigin.TOPLEFT,
            ),
        )
        for r, row in enumerate(rows)
        for c, text in enumerate(row)
    ]
    return TableData(num_rows=len(rows), num_cols=len(rows[0]), table_cells=cells)


def passages(language: str, repeated: bool = False) -> str:
    """Every passage's text of a two-page table whose rest carries the footnote.

    With `repeated`, each of the two tables has a caption, the same words.
    """
    header, first, rest, note = TABLES[language]
    document = DoclingDocument(name="fees")
    for page in (1, 2):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    first_table = document.add_table(
        data=grid((header, *first), 700, header=True), prov=prov(1, 700, 26)
    )
    second = document.add_table(data=grid(rest, 60, header=False), prov=prov(2, 60, 26))
    if repeated:
        for table, page in ((first_table, 1), (second, 2)):
            title = document.add_text(
                label=DocItemLabel.CAPTION,
                text=f"{header[0]} / {header[1]}",
                prov=prov(page, 680),
                parent=table,
            )
            table.captions.append(title.get_ref())
    foot = document.add_text(
        label=DocItemLabel.FOOTNOTE, text=note, prov=prov(2, 100), parent=second
    )
    second.footnotes.append(foot.get_ref())
    _tabled(document, None)
    _, chunks = chunks_of(document, word_chunker(300), language)
    return "\n".join(chunk.text for chunk in chunks)


@pytest.mark.parametrize("language", sorted(TABLES))
def test_the_rows_of_the_rest_join_the_table(language: str) -> None:
    """The control: the join itself works, the rest's rows are in the passage."""
    _, _, rest, _ = TABLES[language]
    assert rest[-1][0] in passages(language)


@pytest.mark.parametrize("language", sorted(TABLES))
def test_the_footnote_under_the_tables_end_reaches_a_passage(language: str) -> None:
    """The condition the footnote sets is passage text, as it is on one page."""
    _, _, _, note = TABLES[language]
    assert note in passages(language), passages(language)


@pytest.mark.parametrize("language", sorted(TABLES))
def test_a_caption_the_table_already_has_is_kept_once(language: str) -> None:
    """The rest's `(continued)` caption repeats the table's: one is printed."""
    header, _, _, _ = TABLES[language]
    assert passages(language, repeated=True).count(f"{header[0]} / {header[1]}") == 1


@pytest.mark.parametrize("language", sorted(TABLES))
def test_the_footnote_still_reaches_a_passage_beside_a_repeated_caption(
    language: str,
) -> None:
    """Dropping the repeated caption takes no footnote with it."""
    _, _, _, note = TABLES[language]
    assert note in passages(language, repeated=True)
