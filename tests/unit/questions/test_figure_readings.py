"""How figures are read: long plain prices (qg-check-4)."""

from __future__ import annotations

import pytest

from question_generation.gates import adds_up, agrees, figures


@pytest.mark.parametrize(
    ("text", "language", "value"),
    [
        ("Der Laptop kostet 1299,99 EUR.", "de", 1299.99),
        ("Das Konto hat 15000,00 EUR.", "de", 15000.0),
        ("The laptop costs 1299.99 EUR.", "en", 1299.99),
        ("The balance is 2500.00 EUR.", "en", 2500.0),
        ("Der Kredit beträgt 12500,50 EUR.", "de", 12500.5),
    ],
)
def test_a_long_price_without_a_thousands_mark_reads_as_one_figure(
    text, language, value
):
    """A price of four digits or more with a fraction is one figure."""
    assert figures(text, language) == [value]


@pytest.mark.parametrize(
    ("language", "key", "recovery", "question"),
    [
        (
            "de",
            "1299,99 EUR",
            "Der Laptop kostet 1.299,99 EUR.",
            "Was kostet der Laptop?",
        ),
        (
            "en",
            "1,299.99 EUR",
            "The laptop costs 1299.99 EUR.",
            "What does the laptop cost?",
        ),
    ],
)
def test_one_price_written_two_ways_agrees(language, key, recovery, question):
    """One price written with and without a thousands mark agrees."""
    assert agrees(recovery, key, language, "value", question=question) is True


def test_a_wrong_shop_total_is_refused_without_a_thousands_mark():
    """A total over such prices is checked."""
    passages = ["The laptop costs 1299.99 EUR.", "The bag costs 49.99 EUR."]
    assert adds_up("1349.98 EUR", passages, "en") is True
    assert adds_up("1360.00 EUR", passages, "en") is False
