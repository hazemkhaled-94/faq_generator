"""Defects the QA pass of the finalize session found in question generation, kept red.

Each test states what the documented behaviour asks and fails on the code
under test; `strict` makes a fix announce itself by turning the test green.
"""

from __future__ import annotations

import pytest

from nlp.analysis import figures
from question_generation.gates import adds_up, explains

pytestmark = pytest.mark.nlp


# ── QA-qg-1: a space-grouped amount asserts nothing an explanation is held to ──

#: A passage, the key it answers, and an explanation stating another amount.
_PROTECTED = {
    "en": (
        (
            "Deposits are protected up to EUR 100 000 per customer. Savings and "
            "current accounts count together."
        ),
        "up to EUR 100 000",
        (
            "Deposit protection covers each customer's balances at the bank. Savings "
            "and current accounts are added together and protected up to EUR 200 000 "
            "per customer, so larger balances are not covered in full."
        ),
    ),
    "de": (
        (
            "Guthaben sind bis zu 100 000 Euro je Kunde geschützt. Spar- und "
            "Girokonten zählen zusammen."
        ),
        "bis zu 100 000 Euro",
        (
            "Die Einlagensicherung schützt die Guthaben eines Kunden bei der Bank. "
            "Spar- und Girokonten werden zusammengerechnet und sind bis zu 200 000 "
            "Euro je Kunde geschützt, darüber hinaus nicht."
        ),
    ),
}


@pytest.mark.xfail(
    strict=True,
    reason=(
        "QA-questions-1, its fix withdrawn after three reviews (see docs/bugs.md): "
        "an explanation stating a space-grouped amount the passages do not "
        "(EUR 200 000 against EUR 100 000) still passes explains(), as in v0.4.2"
    ),
)
@pytest.mark.parametrize("language", ["en", "de"])
def test_qa_qg_1_an_explanation_with_a_wrong_space_grouped_amount_is_unusable(
    language,
) -> None:
    """`EUR 200,000` is refused; `EUR 200 000`, the same wrong amount, must be too."""
    passage, key, explanation = _PROTECTED[language]

    assert not explains(explanation, key, (passage,), language)


def test_qa_qg_1_the_same_wrong_amount_with_a_thousands_mark_is_refused() -> None:
    """The control: the gate does hold an explanation's figures to the passages."""
    passage, key, explanation = _PROTECTED["en"]

    assert not explains(
        explanation.replace("EUR 200 000", "EUR 200,000"), key, (passage,), "en"
    )


# ── QA-qg-4: a currency word carrying a suffix ─────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "Guthaben sind bis 100 000 Euro/Kunde geschützt.",
        "Guthaben sind bis 100 000 Euro* geschützt.",
        "Der Dispositionskredit beträgt 5 000,- EUR.",
    ],
)
def test_qa_qg_4_a_space_grouped_amount_beside_a_marked_currency_is_one_figure(
    text,
) -> None:
    """`100 000 Euro` is one figure (NEW-release-1); so is `100 000 Euro/Kunde`."""
    assert len(figures(text, "de")) == 1, figures(text, "de")


def test_qa_qg_4_a_right_total_over_marked_amounts_is_not_refused() -> None:
    """The same passages with `je Kunde` add up; with `/Kunde` they must too."""
    assert (
        adds_up(
            "300.000 Euro",
            [
                "Ihr Geld ist bis zu 100 000 Euro/Kunde geschützt.",
                "Für das Gemeinschaftskonto gelten bis zu 200 000 Euro/Kunde.",
            ],
            "de",
        )
        is not False
    )


# ── C-052: the cases that defeated the earlier fixes, and a shop price list ──


@pytest.mark.parametrize(
    ("text", "language", "expected"),
    [
        ("Der Kredit beträgt 5.000,-EUR.", "de", [5000.0]),
        ("Der Kredit beträgt 5 000,-EUR.", "de", [5000.0]),
        ("Es gibt 3 500-Euro-Scheine.", "de", [3.0, 500.0]),
        ("Deposits are protected up to EUR 100 000 per customer.", "en", [100000.0]),
        ("Das Konto kostet 12 500 € im Jahr.", "de", [12500.0]),
        ("The cart totals 12 500 USD before tax.", "en", [12500.0]),
        ("Call 030 123 456 for the shop.", "en", [30.0, 123.0, 456.0]),
    ],
)
def test_c052_one_amount_reader_folds_marks_and_keeps_counts_apart(
    text, language, expected
) -> None:
    """An amount beside a currency is one figure whatever mark follows; a count of notes or a phone number is not."""
    assert figures(text, language) == expected
