"""How a fact's numbers are read: formats, words and pronouns (llm-nlp-7 ...)."""

import pytest
from drivers import Checker, passage

from nlp.analysis import numbers


def ok(lang, text, fact=None):
    """The fact check's verdict on one statement against one passage."""
    f = Checker(passage(text, language=lang)).atomic(fact or text)
    return f.validated, f.rejection_code, f.validation_error


def must_validate(lang, text, fact=None):
    """Asserts the statement is accepted."""
    v, code, err = ok(lang, text, fact)
    assert v, f"refused {code}: {err} | {fact or text}"


def must_refuse(lang, text, fact):
    """Asserts the statement is refused."""
    v, _, _ = ok(lang, text, fact)
    assert not v, f"validated a changed figure: {fact}"


FORMATS = [
    (
        "en",
        "The daily withdrawal limit is 1,000 EUR.",
        "The daily withdrawal limit is 1000 EUR.",
    ),
    (
        "en",
        "The daily withdrawal limit is 1000 EUR.",
        "The daily withdrawal limit is 1,000 EUR.",
    ),
    ("en", "Shipping costs 5.00 EUR.", "Shipping costs 5 EUR."),
    ("en", "The fee is 2.50%.", "The fee is 2.5%."),
    (
        "de",
        "Das tägliche Abhebelimit beträgt 1.000 Euro.",
        "Das tägliche Abhebelimit beträgt 1000 Euro.",
    ),
    ("de", "Der Versand kostet 4,90 Euro.", "Der Versand kostet 4,9 Euro."),
]


@pytest.mark.parametrize(("lang", "text", "fact"), FORMATS)
def test_the_same_value_in_another_format_validates(lang, text, fact):
    """One value written another way adds nothing."""
    must_validate(lang, text, fact)


@pytest.mark.parametrize(
    ("lang", "text", "fact"),
    [
        (
            "en",
            "The daily withdrawal limit is 1,000 EUR.",
            "The daily withdrawal limit is 1,500 EUR.",
        ),
        ("de", "Der Versand kostet 4,90 Euro.", "Der Versand kostet 4,99 Euro."),
        (
            "de",
            "Das tägliche Abhebelimit beträgt 1.000 Euro.",
            "Das tägliche Abhebelimit beträgt 1.500 Euro.",
        ),
        ("en", "Shipping costs 5.00 EUR.", "Shipping costs 5.50 EUR."),
    ],
)
def test_a_changed_value_is_still_refused(lang, text, fact):
    """A different value is an addition in any format."""
    must_refuse(lang, text, fact)


def test_the_dedup_reads_one_value_in_two_formats_as_one():
    """The dedup compares values, not spellings."""
    assert numbers("limit 1,000 EUR", "en") == numbers("limit 1000 EUR", "en")
    assert numbers("Versand 4,90 Euro", "de") == numbers("Versand 4,9 Euro", "de")
    assert numbers("limit 1,500 EUR", "en") != numbers("limit 1,000 EUR", "en")


WORDS = [
    (
        "en",
        "You can return items within thirty days of delivery.",
        "Items can be returned within 30 days of delivery.",
    ),
    (
        "en",
        "Items can be returned within 30 days of delivery.",
        "You can return items within thirty days of delivery.",
    ),
    (
        "en",
        "The limit is twenty thousand euros per day.",
        "The limit is 20000 euros per day.",
    ),
    (
        "en",
        "The account fee is twenty-five euros per year.",
        "The account fee is 25 euros per year.",
    ),
    (
        "en",
        "The shop sends one hundred twenty-five parcels a day.",
        "The shop sends 125 parcels a day.",
    ),
    (
        "de",
        "Sie können Waren innerhalb von dreißig Tagen zurückgeben.",
        "Waren können innerhalb von 30 Tagen zurückgegeben werden.",
    ),
    ("de", "Die Gebühr beträgt zwanzig Euro.", "Die Gebühr beträgt 20 Euro."),
    ("de", "Die Gebühr beträgt fünfundzwanzig Euro.", "Die Gebühr beträgt 25 Euro."),
    (
        "de",
        "Die Bank prüft zweihundert Konten pro Tag.",
        "Die Bank prüft 200 Konten pro Tag.",
    ),
]


@pytest.mark.parametrize(("lang", "text", "fact"), WORDS)
def test_a_count_in_words_above_twelve_validates(lang, text, fact):
    """A count past twelve written out is the count in digits."""
    must_validate(lang, text, fact)


@pytest.mark.parametrize(
    ("lang", "text", "fact"),
    [
        (
            "en",
            "The account fee is twenty-five euros per year.",
            "The account fee is 35 euros per year.",
        ),
        (
            "de",
            "Die Gebühr beträgt fünfundzwanzig Euro.",
            "Die Gebühr beträgt 52 Euro.",
        ),
    ],
)
def test_a_wrong_count_past_twelve_is_still_refused(lang, text, fact):
    """A different number is an addition however it is written."""
    must_refuse(lang, text, fact)


def test_the_dedup_reads_a_count_in_words_as_its_digits():
    """The dedup compares values, whether digits or words."""
    assert numbers("within thirty days", "en") == numbers("within 30 days", "en")
    assert numbers("dreißig Tage", "de") == numbers("30 Tage", "de")
    assert numbers("twenty thousand euros", "en") == numbers("20000 euros", "en")
    assert numbers("zweitausend Euro", "de") == numbers("2000 Euro", "de")
    assert numbers("das Jahrhundert", "de") == ()
