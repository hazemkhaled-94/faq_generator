"""A page set in columns that the converter read across is named in the note.

A two-column page whose lines sit at the same heights comes out of the
converter with a line of each column joined into one block, so a sentence of
the left column runs into one of the right. Nothing is reordered; the pages
are named so a reader knows where the text may be mixed.
"""

from __future__ import annotations

import pymupdf
import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.reference import ProvenanceItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

from preprocessing.parsing.pipelines.pdf import _interleaved_pages

COLUMNS = {
    "de": (
        [
            "Die Bank erhebt für jedes Konto ein Entgelt.",
            "Das Entgelt wird zum Monatsende abgebucht.",
            "Bei Schliessung wird es anteilig erstattet.",
            "Eine Änderung wird zwei Monate vorher mitgeteilt.",
            "Der Kunde kann der Änderung widersprechen.",
            "Das Konto kann jederzeit gekündigt werden.",
        ],
        [
            "The card is issued within five working days.",
            "A replacement card costs fifteen euro.",
            "Lost cards must be blocked at once.",
            "Cash withdrawals abroad carry a fee.",
            "The fee is shown before each withdrawal.",
            "Limits can be changed in the app.",
        ],
    ),
    "en": (
        [
            "The bank charges a monthly fee for each account.",
            "The fee is taken at the end of the month.",
            "On closing it is refunded in proportion.",
            "A change is announced two months before.",
            "The customer may object to a change.",
            "The account may be closed at any time.",
        ],
        [
            "Die Karte wird innerhalb von fünf Werktagen ausgestellt.",
            "Eine Ersatzkarte kostet fünfzehn Euro.",
            "Verlorene Karten sind sofort zu sperren.",
            "Abhebungen im Ausland kosten eine Gebühr.",
            "Die Gebühr wird vor jeder Abhebung gezeigt.",
            "Limits lassen sich in der App ändern.",
        ],
    ),
}


def page(columns: bool, joined: bool, language: str) -> tuple[bytes, DoclingDocument]:
    """A page of two columns (or one), the converter's reading joined or kept apart."""
    left, right = COLUMNS[language]
    pdf = pymupdf.open()
    sheet = pdf.new_page(width=595, height=842)
    document = DoclingDocument(name="t")
    document.add_page(page_no=1, size=Size(width=595, height=842))

    def box(l: float, r: float, t: float) -> ProvenanceItem:
        return ProvenanceItem(
            page_no=1,
            bbox=BoundingBox(l=l, t=t, r=r, b=t + 12, coord_origin=CoordOrigin.TOPLEFT),
            charspan=(0, 1),
        )

    for row, text in enumerate(left):
        top = 100 + 30 * row
        if columns:
            sheet.insert_text((54, top + 10), text, fontsize=10)
            sheet.insert_text((330, top + 10), right[row], fontsize=10)
            if joined:
                document.add_text(
                    label=DocItemLabel.TEXT,
                    text=f"{text} {right[row]}",
                    prov=box(54, 540, top),
                )
            else:
                document.add_text(
                    label=DocItemLabel.TEXT, text=text, prov=box(54, 280, top)
                )
                document.add_text(
                    label=DocItemLabel.TEXT, text=right[row], prov=box(330, 540, top)
                )
        else:
            sheet.insert_text((54, top + 10), text, fontsize=10)
            document.add_text(
                label=DocItemLabel.TEXT, text=text, prov=box(54, 540, top)
            )
    return pdf.tobytes(), document


@pytest.mark.parametrize("language", sorted(COLUMNS))
def test_a_two_column_page_the_converter_read_across_is_named(language: str) -> None:
    """Each block runs from the left column into the right."""
    data, document = page(columns=True, joined=True, language=language)

    assert _interleaved_pages(document, data) == (1,)


@pytest.mark.parametrize("language", sorted(COLUMNS))
def test_a_two_column_page_read_column_by_column_is_not_named(language: str) -> None:
    """The converter kept the columns apart: nothing to warn of."""
    data, document = page(columns=True, joined=False, language=language)

    assert _interleaved_pages(document, data) == ()


@pytest.mark.parametrize("language", sorted(COLUMNS))
def test_a_single_column_page_is_not_named(language: str) -> None:
    """One column has no gutter."""
    data, document = page(columns=False, joined=False, language=language)

    assert _interleaved_pages(document, data) == ()
