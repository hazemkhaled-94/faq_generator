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
    ("dotted", "colon", "language"),
    [
        ("Die Frist endet bis 24.00 Uhr.", "Die Frist endet um 24:00 Uhr.", "de"),
        (
            "Das Konto ist bis 18.00 Uhr geöffnet.",
            "Das Konto ist bis 18:00 geöffnet.",
            "de",
        ),
        ("The cut-off is 23.59 CET.", "The cut-off is 23:59 CET.", "en"),
        ("Orders close at 8.30 sharp.", "Orders close at 08:30 sharp.", "en"),
        (
            "Il negozio chiude entro le 18.00.",
            "Il negozio chiude entro le 18:00.",
            "it",
        ),
    ],
)
def test_a_time_written_with_a_dot_carries_the_hour_and_minute_of_its_colon_form(
    dotted, colon, language
) -> None:
    """`24.00` and `24:00` are one time, in any language."""
    from nlp.analysis import numerals

    assert numerals(colon, language) <= numerals(dotted, language)


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("The fee is 8.75 EUR.", "en"),
        ("Die Gebühr beträgt 8.75 EUR.", "de"),
        ("The rate is 24.75 percent.", "en"),
    ],
)
def test_a_decimal_whose_second_part_is_no_minute_gains_no_time(text, language) -> None:
    """Minutes stop at 59: `8.75` is a value, not eight hours and 75 minutes."""
    from nlp.analysis import numerals

    assert not {"75"} & numerals(text, language)
