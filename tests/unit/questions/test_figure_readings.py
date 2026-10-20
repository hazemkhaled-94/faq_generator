"""How figures are read: long plain prices (qg-check-4)."""

from __future__ import annotations

import pytest

from question_generation.gates import adds_up, agrees, figures, restates, unnamed


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


@pytest.mark.parametrize(
    ("language", "question", "echo", "number"),
    [
        (
            "en",
            "Which account is free for students?",
            "The one for students is free.",
            "Each account for students costs 2 EUR.",
        ),
    ],
)
def test_one_as_a_pronoun_does_not_exempt_an_echo_answer(
    language, question, echo, number
):
    """An answer whose only number-like word is a pronoun is still an echo."""
    assert restates(question, echo, language) is True
    assert restates(question, number, language) is False


STEPS = [
    (
        "en",
        (
            "Step 1: The customer enters the personal PIN on the checkout terminal.\n"
            "Step 2: The customer confirms the displayed amount."
        ),
        "enter the PIN and confirm",
        "How does a customer pay by card?",
    ),
    (
        "de",
        (
            "Schritt 1: Der Kunde gibt am Kassenterminal des Geschäfts seine persönliche PIN ein.\n"
            "Schritt 2: Der Kunde bestätigt den angezeigten Betrag."
        ),
        "PIN eingeben und bestätigen",
        "Wie bezahlt ein Kunde mit Karte?",
    ),
    (
        "en",
        (
            "To pay by card at the checkout terminal, the customer must (1) enter the personal PIN "
            "and (2) confirm the displayed amount."
        ),
        "enter the PIN and confirm",
        "How does a customer pay by card?",
    ),
    (
        "de",
        (
            "Zum Bezahlen am Kassenterminal muss der Kunde (1) die persönliche PIN eingeben "
            "und (2) den angezeigten Betrag bestätigen."
        ),
        "PIN eingeben und bestätigen",
        "Wie bezahlt ein Kunde mit Karte?",
    ),
    (
        "en",
        "1. The customer opens the banking app on the phone; 2. The customer approves the transfer.",
        "open the app and approve",
        "How is a transfer approved?",
    ),
    (
        "de",
        "1. Der Kunde öffnet die Banking-App auf dem Handy; 2. Der Kunde gibt die Überweisung frei.",
        "App öffnen und freigeben",
        "Wie wird eine Überweisung freigegeben?",
    ),
]


@pytest.mark.parametrize(("language", "recovery", "key", "question"), STEPS)
def test_step_numbers_are_not_figures_the_key_lacks(language, recovery, key, question):
    """A numbered step is an item, and its number no figure."""
    stated = [
        n
        for n in unnamed(recovery, key, language, question)
        if n.replace(".", "", 1).isdigit()
    ]
    assert stated == [], f"step numbers read as figures: {stated}"


@pytest.mark.parametrize(
    ("language", "recovery", "key", "question"),
    [
        (
            "en",
            "Step 1: The customer pays a fee of 30 EUR at the checkout.",
            "pay the fee",
            "What does a customer do?",
        ),
        (
            "de",
            "Schritt 1: Der Kunde zahlt an der Kasse eine Gebühr von 30 EUR.",
            "Gebühr zahlen",
            "Was tut der Kunde?",
        ),
    ],
)
def test_a_figure_beside_a_step_number_is_still_named(
    language, recovery, key, question
):
    """Only the step number goes; a stated figure stays."""
    stated = [
        n
        for n in unnamed(recovery, key, language, question)
        if n.replace(".", "", 1).isdigit()
    ]
    assert stated == ["30.0"] or stated == ["30"], stated


@pytest.mark.parametrize(
    ("language", "recovery", "key", "question", "figure"),
    [
        (
            "de",
            "Der Kontoauszug erscheint zum Stichtag: 15. März im Postfach.",
            "Kontoauszug",
            "Wann erscheint der Kontoauszug?",
            "15",
        ),
        (
            "en",
            "The invoice is issued on the cut-off date: 15. March at the latest.",
            "invoice",
            "When is the invoice issued?",
            "15",
        ),
        (
            "en",
            "The bank charges a fee: 30. Payment is due at month end.",
            "pay the fee",
            "What does the bank charge?",
            "30",
        ),
        (
            "de",
            "Die Bank erhebt eine Gebühr; 30. Die Zahlung ist monatlich fällig.",
            "Gebühr",
            "Was erhebt die Bank?",
            "30",
        ),
        (
            "en",
            "The shop adds a step 10 EUR for each parcel.",
            "step",
            "What does the shop add?",
            "10",
        ),
        (
            "en",
            "Step 2 weeks later the card is sent to the customer.",
            "card sent",
            "When is the card sent?",
            "2",
        ),
        (
            "de",
            "Schritt 5 Euro pro Monat kostet die Karte im Konto.",
            "Karte",
            "Was kostet die Karte?",
            "5",
        ),
    ],
)
def test_a_figure_that_is_no_item_number_is_still_named(
    language, recovery, key, question, figure
):
    """A figure after a colon or a step word is kept unless it numbers an item."""
    stated = [
        n
        for n in unnamed(recovery, key, language, question)
        if n.replace(".", "", 1).isdigit()
    ]
    assert [n.split(".")[0] for n in stated] == [figure], stated
