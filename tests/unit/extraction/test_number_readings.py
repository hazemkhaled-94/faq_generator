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
