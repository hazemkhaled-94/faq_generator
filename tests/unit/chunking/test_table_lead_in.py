"""preprocessing-11: a lead-in that scopes a long table is carried with it."""

from __future__ import annotations

import pytest
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker
from test_table_footnote import grid

from preprocessing.chunking.passages import chunks_of


def scheduled(head: str, lead: str, header, row) -> DoclingDocument:
    """A heading, a lead-in ending in a colon and a 60-row table."""
    document = DoclingDocument(name="t")
    document.add_heading(text=head, level=1)
    document.add_text(label=DocItemLabel.TEXT, text=lead)
    document.add_table(data=grid(header, *[row(k) for k in range(1, 61)]))
    return document


@pytest.mark.parametrize(
    ("head", "lead", "header", "row"),
    [
        (
            "Kontoführung",
            "Für Kunden unter 25 Jahren gelten abweichend folgende Entgelte:",
            ("Kontomodell", "Grundpreis", "Buchung"),
            lambda k: (f"Modell {k}", f"{k},90 EUR", f"0,{k:02d} EUR"),
        ),
        (
            "Delivery",
            "For deliveries to islands the following surcharges apply:",
            ("Region", "Surcharge", "Days"),
            lambda k: (f"Island {k}", f"{k}.90 EUR", f"{k % 5 + 2} days"),
        ),
        (
            "Versand",
            "Für Lieferungen auf Inseln gelten folgende Zuschläge:",
            ("Insel", "Zuschlag", "Tage"),
            lambda k: (f"Insel {k}", f"{k},90 EUR", f"{k % 5 + 2} Tage"),
        ),
        (
            "Account fees",
            "For customers under 25 the following fees apply instead:",
            ("Account", "Monthly fee", "Booking"),
            lambda k: (f"Model {k}", f"{k}.90 EUR", f"0.{k:02d} EUR"),
        ),
    ],
)
def test_every_piece_of_a_table_carries_the_lead_in_that_scopes_it(
    head, lead, header, row
) -> None:
    """In its text, or in its trail: a price without its scope is a wrong fact."""
    document = scheduled(head, lead, header, row)

    _, chunks = chunks_of(document, word_chunker(120), None)

    pieces = [c for c in chunks if "|" in c.text]
    assert len(pieces) > 1
    for piece in pieces:
        assert lead in piece.text or lead in (piece.meta.headings or []), (
            piece.meta.headings,
            piece.text[:80],
        )
