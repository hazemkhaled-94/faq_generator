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
    ],
)
def test_two_different_values_read_differently(first, second, language) -> None:
    """A different value, or the same value a different number of times."""
    from nlp.analysis import numbers

    assert numbers(first, language) != numbers(second, language)


def test_a_figure_glued_to_its_unit_is_still_read() -> None:
    """`45m` and `08:00` carry numbers that no `like_num` token holds."""
    from nlp.analysis import numbers

    assert numbers("Die Torlinie misst mindestens 45m.", "de") == ("45",)
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
