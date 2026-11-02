"""The numbers a statement states, which the dedup gate compares.

Two statements naming different numbers state different claims however
alike their words are, so the reading has to be exact where it is read at
all: a digit as written, a number word as the value it names.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.nlp


@pytest.mark.parametrize(
    ("word", "digit", "language"),
    [
        ("The device has two ports.", "The device has 2 ports.", "en"),
        ("Das Gerät hat zwei Anschlüsse.", "Das Gerät hat 2 Anschlüsse.", "de"),
        ("The second reminder is sent.", "The 2nd reminder is sent.", "en"),
    ],
)
def test_a_number_word_reads_as_the_value_it_names(word, digit, language) -> None:
    """A number word and its digits are one number."""
    from nlp.analysis import numbers

    assert numbers(word, language) == numbers(digit, language) == ("2",)


def test_a_text_with_no_language_reads_the_default_pipelines_number_words() -> None:
    """A notice too short to detect is parsed in English and read in it too."""
    from nlp.analysis import numbers, numerals

    assert (
        numbers("Two cards per account.", None)
        == numbers("2 cards per account.", None)
        == ("2",)
    )
    assert numerals("two cards", None) == {"2"}


@pytest.mark.parametrize(
    ("first", "second", "language"),
    [
        ("The device weighs 4 kg.", "The device weighs 7 kg.", "en"),
        (
            "Die Linie liegt 5,5 m vom Pfosten.",
            "Die Linie liegt 16,5 m vom Pfosten.",
            "de",
        ),
        ("Das Gerät hat zwei Anschlüsse.", "Das Gerät hat drei Anschlüsse.", "de"),
        ("The fee is 2 EUR and 2 EUR.", "The fee is 2 EUR.", "en"),
        (
            "Die Pause dauert zwanzig Minuten.",
            "Die Pause dauert dreißig Minuten.",
            "de",
        ),
    ],
)
def test_two_different_values_read_differently(first, second, language) -> None:
    """A different value, or the same value a different number of times."""
    from nlp.analysis import numbers

    assert numbers(first, language) != numbers(second, language)
    assert numbers(first, language) and numbers(second, language)


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Die Kunden achten auf die Gebühren.", "de"),
        ("Die Elf des Betriebs trifft sich am Montag.", "de"),
        ("No one may open the vault at night.", "en"),
    ],
)
def test_a_word_spelled_like_a_number_and_used_otherwise_is_none(
    text, language
) -> None:
    """`achten` is a verb, `Elf` a team and `No one` nobody: read as words."""
    from nlp.analysis import numbers

    assert numbers(text, language) == ()


def test_a_figure_glued_to_its_unit_is_still_read() -> None:
    """`45m` and `08:00` carry numbers that no `like_num` token holds."""
    from nlp.analysis import numbers

    assert numbers("Das Kabel misst mindestens 45m.", "de") == ("45",)
    assert numbers("The line opens at 08:00.", "en") == ("00", "08")


def test_a_language_missing_from_the_table_still_reads_its_digits() -> None:
    """No table, no crash: the digits are the same in every language."""
    from nlp.analysis import numbers

    assert numbers("Le colis pèse 4 kg.", "fr") == ("4",)
    assert numbers("Le colis pèse 4 kg.", None) == ("4",)


def test_a_statement_naming_no_number_reads_none() -> None:
    """Two statements with no numbers agree on them."""
    from nlp.analysis import numbers

    assert numbers("The card is blocked when it is reported stolen.", "en") == ()


@pytest.mark.parametrize(
    ("language", "text", "wanted"),
    [
        ("en", "The bank charges thirty one-time fees.", ("1", "30")),
        ("en", "The shop sells twenty two-week passes.", ("2", "20")),
        ("en", "The card has fifty one-off offers.", ("1", "50")),
        ("en", "The loan runs one hundred two-year terms.", ("100", "2")),
        ("en", "The fee is twenty-five euros.", ("25",)),
        ("de", "Die Gebühr beträgt fünfzig fünf Euro.", ("5", "50")),
        ("de", "Das Konto hat zwanzig fünf Karten.", ("20", "5")),
        ("de", "Die Gebühr beträgt fünfundzwanzig Euro.", ("25",)),
    ],
)
def test_a_cardinal_joins_only_the_cardinal_it_continues(language, text, wanted):
    """A hyphenated word is no part of a number; German has no ten-unit order."""
    from nlp.analysis import numbers

    assert tuple(sorted(numbers(text, language))) == tuple(sorted(wanted))


@pytest.mark.parametrize(
    ("text", "language", "value"),
    [
        ("Limit PLN 100 000 per year", "en", [100000.0]),
        ("Limit 100 000 SEK pro Jahr", "de", [100000.0]),
        ("Limite 100 000 JPY", "it", [100000.0]),
        ("Limit 100 000 ALL per year", "en", [100000.0]),
        ("Call 100 000 for help", "en", [100.0, 0.0]),
    ],
)
def test_a_space_grouped_amount_beside_an_iso_currency_is_one_figure(
    text, language, value
) -> None:
    """The ISO code is the currency in any language; without one the groups stay apart."""
    from nlp.analysis import figures

    assert figures(text, language) == value


@pytest.mark.parametrize(
    ("text", "language", "value"),
    [
        ("Das Privatkonto kostet CHF 1'250.50 pro Jahr.", "de", [1250.5]),
        ("The fee is CHF 1’250.50 a year.", "en", [1250.5]),
        ("Le plafond est de 1'000'000 CHF.", "fr", [1000000.0]),
        ("Ο λογαριασμός κοστίζει 1’250 EUR.", "el", [1250.0]),
        ("Ο λογαριασμός κοστίζει 1.250,50 EUR.", "el", [1250.5]),
        ("Das Limit beträgt 12'5000 CHF.", "de", [12.0, 5000.0]),
    ],
)
def test_an_apostrophe_between_a_digit_and_three_digits_groups_thousands(
    text, language, value
) -> None:
    """The Swiss mark, in either apostrophe, joins the groups into one figure."""
    from nlp.analysis import figures

    assert figures(text, language) == value


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("The 90's were quiet and Section 5's rule applies.", "en"),
        ("Die 90's waren ruhig, Artikel 5's Regel gilt.", "de"),
        ("Les années 90's et l'article 5's.", "fr"),
        ("Τα 90's και το 5's.", "el"),
    ],
)
def test_a_possessive_apostrophe_next_to_a_digit_is_no_group_mark(
    text, language
) -> None:
    """Only a digit before and exactly three digits after make a group."""
    from nlp.analysis import figures, numbers

    assert figures(text, language) == [90.0, 5.0]
    assert numbers(text, language) == ("5", "90")


@pytest.mark.parametrize(
    ("language", "grouped", "plain"),
    [
        (
            "de",
            "Das Konto kostet CHF 1'250.50 im Jahr.",
            "Das Konto kostet CHF 1250.50 im Jahr.",
        ),
        (
            "en",
            "The account costs CHF 1’250.50 a year.",
            "The account costs CHF 1250.50 a year.",
        ),
        (
            "fr",
            "Le compte coûte CHF 1'250.50 par an.",
            "Le compte coûte CHF 1250.50 par an.",
        ),
        (
            "el",
            "Ο λογαριασμός κοστίζει CHF 1’250.50 τον χρόνο.",
            "Ο λογαριασμός κοστίζει CHF 1250.50 τον χρόνο.",
        ),
    ],
)
def test_a_grouped_and_an_ungrouped_amount_are_one_number(
    language, grouped, plain
) -> None:
    """The digits read the same whichever way the thousands are marked."""
    from nlp.analysis import numbers, numerals

    assert numbers(grouped, language) == numbers(plain, language)
    assert numerals(grouped, language) == numerals(plain, language)


@pytest.mark.parametrize(
    ("text", "language", "value"),
    [
        ("The account pays 2½ % interest.", "en", ("2.5",)),
        ("Das Sparkonto bringt 2¼ % Zinsen.", "de", ("2.25",)),
        ("Delivery takes ¾ of a day.", "en", ("0.75",)),
        ("Die Lieferung dauert 1⅛ Tage.", "de", ("1.125",)),
        ("Le compte rapporte 2½ % par an.", "fr", ("2.5",)),
        ("Ο λογαριασμός αποδίδει 2½ % ετησίως.", "el", ("2.5",)),
    ],
)
def test_a_vulgar_fraction_reads_as_its_value(text, language, value) -> None:
    """A fraction after digits adds to them, and alone is its own value."""
    from nlp.analysis import numbers, numerals

    assert numbers(text, language) == value
    assert numerals(text, language) == frozenset(value)


@pytest.mark.parametrize(
    ("text", "language", "value"),
    [
        ("The account pays 2½ % interest a year.", "en", [2.5]),
        ("Das Sparkonto bringt 2½ % Zinsen pro Jahr.", "de", [2.5]),
        ("Die Lieferung dauert 1 ½ Tage.", "de", [1.5]),
        ("Delivery takes 1 ½ days.", "en", [1.5]),
        ("Delivery takes ¾ of a day.", "en", [0.75]),
        ("Le compte rapporte 2½ % par an.", "fr", [2.5]),
        ("Ο λογαριασμός αποδίδει 2½ % ετησίως.", "el", [2.5]),
    ],
)
def test_figures_reads_a_vulgar_fraction_as_its_value(text, language, value) -> None:
    """The regex reader folds the fraction too, glued to its whole number or one space apart."""
    from nlp.analysis import figures

    assert figures(text, language) == value


@pytest.mark.parametrize(
    ("language", "spaced", "glued"),
    [
        ("de", "Die Lieferung dauert 1 ½ Tage.", "Die Lieferung dauert 1½ Tage."),
        ("en", "Delivery takes 1 ½ days.", "Delivery takes 1½ days."),
        ("fr", "La livraison prend 1 ½ jours.", "La livraison prend 1½ jours."),
        ("el", "Η παράδοση διαρκεί 1 ½ ημέρες.", "Η παράδοση διαρκεί 1½ ημέρες."),
    ],
)
def test_a_fraction_one_space_from_its_whole_number_reads_like_the_glued_one(
    language, spaced, glued
) -> None:
    """`1 ½` and `1½` are one number, 1.5."""
    from nlp.analysis import numbers, numerals

    assert numbers(spaced, language) == numbers(glued, language) == ("1.5",)
    assert numerals(spaced, language) == numerals(glued, language) == frozenset({"1.5"})
