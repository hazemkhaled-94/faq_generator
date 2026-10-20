"""preprocessing-5: a group row of a fee table is not a wrapped label."""

from __future__ import annotations

import pytest
from docling_core.types.doc.document import DoclingDocument
from test_tables import grid, rows

from preprocessing.parsing.pipelines.pdf import _tabled


def read(*table_rows: tuple[str, ...]) -> list[list[str]]:
    """The rows the mend leaves of one table."""
    document = DoclingDocument(name="t")
    document.add_table(data=grid(*table_rows))
    return rows(_tabled(document))[0]


@pytest.mark.parametrize(
    "table",
    [
        (
            ("Service", "Fee"),
            ("Cards", ""),
            ("debit card", "10.00 EUR"),
            ("credit card", "30.00 EUR"),
            ("Transfers", ""),
            ("online", "0.00 EUR"),
            ("in branch", "2.50 EUR"),
        ),
        (
            ("Leistung", "Entgelt"),
            ("Überweisungen", ""),
            ("beleghaft", "2,00 EUR"),
            ("online", "0,00 EUR"),
            ("Versand", ""),
            ("innerhalb Deutschlands", "4,90 EUR"),
            ("ins Ausland", "14,90 EUR"),
        ),
        (
            ("Item", "Price"),
            ("Shipping", ""),
            ("standard", "4.95 GBP"),
            ("express", "9.95 GBP"),
            ("Returns", ""),
            ("by post", "0.00 GBP"),
            ("in store", "0.00 GBP"),
        ),
    ],
)
def test_a_group_row_over_lower_case_items_is_not_glued_to_the_first(table) -> None:
    """A group heads several items; a wrapped label continues exactly one row."""
    labels = [row[0] for row in read(*table)]

    for group in (
        "Cards",
        "Transfers",
        "Überweisungen",
        "Versand",
        "Shipping",
        "Returns",
    ):
        if (group,) in [(r[0],) for r in table]:
            assert not any(label.startswith(group + " ") for label in labels), labels


@pytest.mark.parametrize(
    ("table", "joined"),
    [
        (
            (
                ("Service", "Fee"),
                ("cash withdrawal at", ""),
                ("foreign ATM", "3.00 EUR"),
                ("balance enquiry", "0.50 EUR"),
            ),
            "cash withdrawal at foreign ATM",
        ),
        (
            (
                ("Leistung", "Entgelt"),
                ("Bargeldauszahlung an", ""),
                ("fremden Automaten", "3,00 EUR"),
                ("am Schalter", "0,50 EUR"),
            ),
            "Bargeldauszahlung an fremden Automaten",
        ),
    ],
)
def test_a_label_ending_on_a_preposition_is_wrapped_over_lower_case_rows(
    table, joined
) -> None:
    """A label cannot end on 'at' or 'an': the line below finishes it."""
    assert joined in [row[0] for row in read(*table)]
