"""How a fact's numbers are read: formats, words and pronouns (llm-nlp-7 ...)."""

import pytest
from drivers import Checker, passage

from nlp.analysis import figures, numbers


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


PRONOUN = [
    (
        "Customers may withdraw at most 500 EUR per day.",
        "No one may withdraw more than 500 EUR per day.",
    ),
    (
        "The shop refunds the purchase price within 30 days.",
        "The one you bought can be returned within 30 days.",
    ),
    (
        "Customers may open a savings account for 12 months.",
        "No one may close a savings account within 12 months.",
    ),
]


@pytest.mark.parametrize(("text", "fact"), PRONOUN)
def test_one_as_a_pronoun_is_no_number(text, fact):
    """`one` of "no one" or "the one you bought" asserts no count."""
    _, code, err = ok("en", text, fact)
    assert "asserts one" not in str(err), f"{code}: {err}"


@pytest.mark.parametrize(
    ("text", "fact"),
    [
        ("Each account comes with 2 cards.", "Each account comes with one card."),
        ("Each account may hold 3 cards.", "Only one card per account is allowed."),
    ],
)
def test_one_as_a_number_is_still_checked(text, fact):
    """A numeral `one` is a count and a wrong one is refused."""
    must_refuse("en", text, fact)


def test_one_card_per_account_is_still_read_as_one():
    """The numeral reading of `one` survives."""
    must_validate("en", "Each account holds 1 card.", "Each account holds one card.")


@pytest.mark.parametrize(
    ("lang", "text", "fact"),
    [
        (
            "de",
            "Ihr Geld ist bis zu 100 000 Euro geschützt.",
            "Ihr Geld ist bis zu 100.000 Euro geschützt.",
        ),
        (
            "en",
            "Deposits are protected up to EUR 100,000.",
            "Deposits are protected up to EUR 100 000.",
        ),
    ],
)
def test_a_space_grouped_amount_is_one_value_in_the_fact_check(lang, text, fact):
    """One amount written two ways adds nothing; `numbers` reads it as one."""
    must_validate(lang, text, fact)
    assert numbers(fact, lang) == numbers(text, lang)


def test_a_reference_and_a_figure_are_not_one_grouped_number():
    """A heading number and a figure after it stay two."""
    assert numbers("Artikel 3 Absatz 12 gilt.", "de") == ("12", "3")


@pytest.mark.parametrize(
    ("lang", "text", "fact"),
    [
        (
            "en",
            "Under Section 3 100 customers were refunded.",
            "Under Section 3, 100 customers were refunded.",
        ),
        (
            "de",
            "Laut Abschnitt 2 300 Euro werden erstattet.",
            "Laut Abschnitt 2 werden 300 Euro erstattet.",
        ),
    ],
)
def test_a_reference_then_a_figure_still_validates(lang, text, fact):
    """A reference label before a space-grouped run keeps its two numbers."""
    must_validate(lang, text, fact)


@pytest.mark.parametrize(
    ("text", "lang", "expected"),
    [
        ("Fees by tier: 100 200 300 GBP.", "en", [100.0, 200.0, 300.0]),
        ("Gebühren je Stufe 10 250 500 Euro.", "de", [10.0, 250.0, 500.0]),
        ("Rufen Sie 030 123 456 an.", "de", [30.0, 123.0, 456.0]),
        ("Deposits up to 1 299,99 EUR.", "en", [1299.99]),
    ],
)
def test_a_row_of_figures_is_not_one_grouped_number(text, lang, expected):
    """A flattened table row or a phone number is not thousands."""
    assert sorted(figures(text, lang)) == sorted(expected)


def test_a_language_without_amount_words_reads_no_grouped_number():
    """`fr` is read by the English model, and still groups nothing."""
    assert numbers("Codes 100 200 300 EUR", "fr") == ("100", "200", "300")


# FIX-R164: a wrong spelled count is excused by any number elsewhere in the passage.
@pytest.mark.parametrize(
    ("lang", "text", "fact"),
    [
        pytest.param(
            "de",
            "Es gibt vier Kontomodelle. Das Basiskonto kostet 5 Euro im Monat.",
            "Das Basiskonto kostet vier Euro im Monat.",
            marks=pytest.mark.xfail(
                strict=True, reason="FIX-R164 deferred: no German spelled count is read"
            ),
        ),
        (
            "en",
            "There are four account models. The basic account costs 5 euros a month.",
            "The basic account costs four euros a month.",
        ),
        (
            "en",
            "See Section 3 for details. Delivery takes 5 working days.",
            "Delivery takes three working days.",
        ),
    ],
)
def test_a_wrong_spelled_count_is_not_excused_by_an_uncited_sentence(lang, text, fact):
    """A count in words is checked against the cited sentence, not the passage."""
    f = Checker(passage(text, language=lang)).atomic(fact, 1)
    v = f.validated
    assert not v, f"validated a changed count: {fact!r}"


# VAR-one-same-price: a bare 'one' that is a count.
@pytest.mark.parametrize(
    ("text", "fact"),
    [
        (
            "Each customer may hold at most two cards.",
            "Each customer may hold at most one.",
        ),
        ("Only two are allowed per household.", "Only one is allowed per household."),
        ("The limit is three per customer.", "The limit is one per customer."),
    ],
)
def test_a_wrong_bare_one_is_still_refused(text, fact):
    """A bare `one` that is a count is still checked."""
    v, _, _ = ok("en", text, fact)
    assert not v, f"validated a changed count: {fact!r}"


# Lead replay ids 11368, 11962 (0defee49): German count words newly read as units.
def test_a_german_count_restating_a_multiplicative_adverb_validates():
    """`zwei Mahnungen` restates `zweimal gemahnt` (shape of fact 11368)."""
    v, code, err = ok(
        "de",
        "Ein Kunde, der zweimal gemahnt wird, zahlt eine Gebühr.",
        "Ein Kunde mit zwei Mahnungen zahlt eine Gebühr.",
    )
    assert v, f"refused {code}: {err}"


def test_a_german_ordinal_stated_earlier_in_the_passage_validates():
    """`ersten fünf` is stated in the uncited sentence before (shape of fact 11962)."""
    f = Checker(
        passage(
            "Die ersten fünf Bestellungen sind versandkostenfrei. Danach darf der Kunde die Versandart ändern.",
            language="de",
        )
    ).atomic(
        "Nach den ersten fünf Bestellungen darf der Kunde die Versandart ändern.", 1
    )
    v, code, err = f.validated, f.rejection_code, f.validation_error
    assert v, f"refused {code}: {err}"


def test_a_german_amount_closing_a_sentence_is_one_number():
    """`EUR 2 500.` ends a sentence: the tokenizer keeps `500.`, so the merge misses it."""
    text = "Die Gebühr beträgt EUR 2 500."
    assert numbers(text, "de") == ("2500",)
    assert figures(text, "de") == [2500.0]


def test_a_german_amount_closing_a_sentence_restated_with_a_mark_validates():
    """`EUR 2 500.` and `EUR 2.500.` are one amount."""
    f = Checker(passage("Die Gebühr beträgt EUR 2 500.", language="de")).atomic(
        "Die Gebühr beträgt EUR 2.500."
    )
    assert f.validated, f"refused {f.rejection_code}: {f.validation_error}"
