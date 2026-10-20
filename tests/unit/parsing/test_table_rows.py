"""preprocessing-5 and -13: label rows of a fee table read wrongly."""

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


@pytest.mark.parametrize(
    "table",
    [
        (
            ("Option", "Price", "Time"),
            ("same day delivery (London", "14.95 GBP", "same day"),
            ("only)", "", ""),
            ("next day", "9.95 GBP", "1 day"),
        ),
        (
            ("Leistung", "Entgelt"),
            ("Bargeldauszahlung am Schalter", "5,00 EUR"),
            ("ohne Karte", ""),
            ("Kontoauszug", "1,50 EUR"),
        ),
        (
            ("Konto", "Entgelt"),
            ("Girokonto Premium (mit", "12,90 EUR"),
            ("Dispo)", ""),
            ("Sparkonto", "0,00 EUR"),
        ),
        (
            ("Item", "Price"),
            ("Gift wrapping (paper and", "3.50 GBP"),
            ("ribbon)", ""),
            ("Express post", "9.95 GBP"),
        ),
    ],
)
def test_the_tail_of_a_wrapped_label_is_not_glued_to_the_next_rows_label(
    table,
) -> None:
    """It joins the label above, or stays alone; 'next day' stays 'next day'."""
    got = read(*table)

    tails = {"only)", "ohne Karte", "Dispo)", "ribbon)"}
    for row in got:
        assert not any(row[0].startswith(t + " ") for t in tails), got
    assert any(
        row[0] in ("next day", "Kontoauszug", "Sparkonto", "Express post")
        for row in got
    ), got
    # the tail is not left as a row of its own with no price either
    assert not any(row[0] in tails for row in got), got


@pytest.mark.parametrize(
    "table",
    [
        (
            ("Item", "Price"),
            ("Fee (EUR", "1.00"),
            ("Total (net)", ""),
            ("Shipping", "2.00"),
        ),
        (
            ("Leistung", "Entgelt"),
            ("Gebühr (in EUR", "1,00"),
            ("Summe (netto)", ""),
            ("Versand", "2,00"),
        ),
        (
            ("Item", "Price", "Time"),
            ("alpha", "1.00", ""),
            ("beta", "", ""),
            ("Gamma", "2.00", "1 day"),
        ),
    ],
)
def test_a_label_row_with_a_bracket_of_its_own_or_a_gap_above_is_not_a_tail(
    table,
) -> None:
    """A tail closes the bracket above and opens none; its row has all its data."""
    assert [row[0] for row in read(*table)] == [row[0] for row in table]
