"""What the number readings hold for any amount and any ordinal, not just the examples.

A run of digit groups joined by a space is one amount only beside a word of
the language's `AMOUNT_WORDS` or a currency sign, and never after a
`REFERENCE_LABELS` word; a language with no row reads the groups apart beside
a word, and as one beside a sign. An ordinal, written as a word or as a
figure, is the ordinal it is and never the count of the same digits.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from database.qa_generator import AnswerForm
from nlp.analysis import AMOUNT_WORDS, REFERENCE_LABELS, figures, numbers, parse
from question_generation.gates import agrees

pytestmark = pytest.mark.nlp

#: Words that stand beside a number and mark no amount.
_PLAIN = ("Kunden", "customers", "Stück", "items", "Tage", "days", "Mio.", "Konto")

#: Currency signs, which no row lists, and a sign that is none.
_SIGNS = ("€", "£", "¥", "₹")
_NO_SIGN = "%"


@st.composite
def spaced(draw):
    """A space-grouped run, the words either side of it and the language."""
    language = draw(st.sampled_from(["de", "en", "fr"]))
    head = draw(st.integers(1, 999))
    group = draw(st.integers(0, 999))
    fraction = draw(st.sampled_from(["", ",50", ".00"]))
    run = f"{head} {group:03d}{fraction}"
    words = sorted(AMOUNT_WORDS.get(language, frozenset())) or ["eur"]
    labels = sorted(REFERENCE_LABELS.get(language, frozenset())) or ["section"]
    before = draw(st.sampled_from(["", *_PLAIN, *words, *_SIGNS, *labels]))
    after = draw(st.sampled_from(["", *_PLAIN, *words, *_SIGNS, _NO_SIGN]))
    return language, run, before, after


@given(spaced())
def test_a_space_grouped_run_is_one_amount_only_beside_a_currency_word(case) -> None:
    """Beside a currency word and after no label it is one figure; anywhere else two."""
    language, run, before, after = case
    text = " ".join(one for one in ("Es sind", before, run, after, "fällig.") if one)
    amounts = AMOUNT_WORDS.get(language, frozenset())
    merged = before.casefold() not in REFERENCE_LABELS.get(
        language, frozenset()
    ) and bool({before.casefold(), after.casefold()} & {*amounts, *_SIGNS})

    read = figures(text, language)
    tokens = [one.text for one in parse(text, language)]

    if merged:
        assert len(read) == 1, (text, read)
        assert run in tokens, (text, tokens)
    else:
        assert len(read) == 2, (text, read)
        assert run not in tokens, (text, tokens)


#: Ordinals the readings name, by language: the word and the figure for each
#: value, inside a sentence, and a count of the same value beside the same noun.
_ORDINALS = {
    "en": (
        [
            "first",
            "second",
            "third",
            "fourth",
            "fifth",
            "sixth",
            "seventh",
            "eighth",
            "ninth",
            "tenth",
            "eleventh",
            "twelfth",
        ],
        [
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
        ],
    ),
    "de": (
        [
            "ersten",
            "zweiten",
            "dritten",
            "vierten",
            "fünften",
            "sechsten",
            "siebten",
            "achten",
            "neunten",
            "zehnten",
            "elften",
            "zwölften",
        ],
        [
            "zwei",
            "drei",
            "vier",
            "fünf",
            "sechs",
            "sieben",
            "acht",
            "neun",
            "zehn",
            "elf",
            "zwölf",
        ],
    ),
}

_SUFFIX = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(language: str, value: int, spelled: bool) -> str:
    words, _ = _ORDINALS[language]
    if language == "en":
        written = words[value - 1] if spelled else f"{value}{_SUFFIX.get(value, 'th')}"
        return f"from the {written} reminder on"
    written = words[value - 1] if spelled else f"{value}."
    return f"ab der {written} Mahnung"


def _cardinal(language: str, value: int, spelled: bool) -> str:
    _, words = _ORDINALS[language]
    written = words[value - 2] if spelled else str(value)
    return f"{written} reminders" if language == "en" else f"{written} Mahnungen"


@given(
    language=st.sampled_from(["en", "de"]),
    value=st.integers(2, 12),
    ordinal_spelled=st.booleans(),
    cardinal_spelled=st.booleans(),
)
def test_an_ordinal_never_agrees_with_the_count_of_its_digits(
    language, value, ordinal_spelled, cardinal_spelled
) -> None:
    """`the third reminder` is no `3 reminders`, whichever way each is written."""
    ordinal = _ordinal(language, value, ordinal_spelled)
    cardinal = _cardinal(language, value, cardinal_spelled)

    assert not agrees(ordinal, cardinal, language, AnswerForm.VALUE), (
        ordinal,
        cardinal,
    )
    assert not agrees(cardinal, ordinal, language, AnswerForm.VALUE), (
        cardinal,
        ordinal,
    )


@given(
    language=st.sampled_from(["en", "de"]),
    value=st.integers(1, 12),
    spelled=st.booleans(),
)
def test_an_ordinal_agrees_with_itself_written_the_other_way(
    language, value, spelled
) -> None:
    """The guard above is no refusal of every ordinal: `third` is `3rd`."""
    assert agrees(
        _ordinal(language, value, spelled),
        _ordinal(language, value, not spelled),
        language,
        AnswerForm.VALUE,
    )


# ── A figure, with or without its language's marks ───────────────────────

#: A sentence of each domain that states an amount, by language: a bank's
#: fee, a shop's order value, an office's charge. `{}` is the figure, and
#: the word after it a currency word every row of `AMOUNT_WORDS` lists or an
#: ISO code, so no space-grouped run is in play.
_STATING = {
    "de": (
        "Die Gebühr für die Ersatzkarte beträgt {} EUR.",
        "Ab einem Bestellwert von {} Euro ist der Versand kostenlos.",
        "Für den Antrag erhebt das Amt {} EUR.",
    ),
    "en": (
        "The fee for a replacement card is {} EUR.",
        "Orders over {} euros ship free of charge.",
        "The office charges {} EUR for the application.",
    ),
    "fr": (
        "Les frais pour une carte de remplacement sont de {} EUR.",
        "La livraison est gratuite dès {} EUR de commande.",
        "La mairie facture {} EUR pour la demande.",
    ),
    "pl": (
        "Opłata za kartę zastępczą wynosi {} EUR.",
        "Dostawa jest bezpłatna od {} EUR.",
        "Urząd pobiera {} EUR za wniosek.",
    ),
    "el": (
        "Η χρέωση για κάρτα αντικατάστασης είναι {} EUR.",
        "Η αποστολή είναι δωρεάν για παραγγελίες άνω των {} EUR.",
        "Η υπηρεσία χρεώνει {} EUR για την αίτηση.",
    ),
}

#: The thousands and decimal marks each configured language writes.
_MARKS = {"de": (".", ","), "en": (",", ".")}


def _spelled(cents: int, thousands: str, decimal: str) -> str:
    """An amount in cents, its whole part grouped by `thousands` (none if empty)."""
    whole, part = divmod(cents, 100)
    grouped = f"{whole:,}".replace(",", thousands)
    return f"{grouped}{decimal}{part:02d}"


@given(
    language=st.sampled_from(sorted(_MARKS)),
    cents=st.integers(100_000, 10**11),
    domain=st.integers(0, 2),
)
def test_an_amount_reads_the_same_with_or_without_its_languages_thousands_marks(
    language, cents, domain
) -> None:
    """`1.234.567,89 EUR` is `1234567,89 EUR` in German, as `1,234,567.89` is in English."""
    thousands, decimal = _MARKS[language]
    frame = _STATING[language][domain]

    grouped = figures(frame.format(_spelled(cents, thousands, decimal)), language)
    plain = figures(frame.format(_spelled(cents, "", decimal)), language)

    assert grouped == plain == [cents / 100], (grouped, plain)


@given(
    language=st.sampled_from(["fr", "pl", "el"]),
    cents=st.integers(100_000, 10**11),
    marks=st.sampled_from([(".", ","), (",", "."), ("", ","), ("", ".")]),
    domain=st.integers(0, 2),
)
def test_an_amount_in_a_language_with_no_mark_reads_its_value_whichever_marks_it_takes(
    language, cents, marks, domain
) -> None:
    """With no `DECIMAL_MARK` row, the last of two marks or two digits after one is the decimal.

    French, Polish and Greek write `1 234,56` or `1.234,56`; a model writing
    about them may write `1,234.56`. Each is the one amount, never two
    figures and never a thousandfold one.
    """
    text = _STATING[language][domain].format(_spelled(cents, *marks))

    assert figures(text, language) == [cents / 100], text


@given(
    language=st.sampled_from(sorted(_MARKS)),
    cents=st.integers(100_000, 10**11),
    domain=st.integers(0, 2),
    signed=st.booleans(),
)
def test_the_numbers_a_statement_states_do_not_change_with_its_thousands_marks(
    language, cents, domain, signed
) -> None:
    """The duplicate gate reads `1.500,00 EUR` and `1500,00 €` as one number.

    In German and English, the code or the sign. In a language no
    `NLP_MODELS` row names, the default parse now and then tags a word `NUM`
    (`od`, `είναι`) and the word is read as a number.
    """
    thousands, decimal = _MARKS[language]
    frame = _STATING[language][domain]
    frame = frame.replace("EUR", "€") if signed else frame

    grouped = numbers(frame.format(_spelled(cents, thousands, decimal)), language)
    plain = numbers(frame.format(_spelled(cents, "", decimal)), language)

    assert grouped == plain, (grouped, plain)


#: The ordinals past twelve as each configured language writes them, built
#: here rather than read off the readings' own table. English only where it
#: is one word: a hyphenated `twenty-first` is C-270's, accepted.
_EN_PAST_TWELVE = {
    **dict(
        zip(
            range(13, 20),
            [
                "thirteenth",
                "fourteenth",
                "fifteenth",
                "sixteenth",
                "seventeenth",
                "eighteenth",
                "nineteenth",
            ],
            strict=True,
        )
    ),
    **dict(
        zip(
            range(20, 100, 10),
            [
                "twentieth",
                "thirtieth",
                "fortieth",
                "fiftieth",
                "sixtieth",
                "seventieth",
                "eightieth",
                "ninetieth",
            ],
            strict=True,
        )
    ),
}
_DE_UNITS = ["ein", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun"]
_DE_TEENS = [
    "dreizehn",
    "vierzehn",
    "fünfzehn",
    "sechzehn",
    "siebzehn",
    "achtzehn",
    "neunzehn",
]
_DE_TENS = [
    "zwanzig",
    "dreißig",
    "vierzig",
    "fünfzig",
    "sechzig",
    "siebzig",
    "achtzig",
    "neunzig",
]


def _de_past_twelve(value: int) -> str:
    """A German ordinal from 13 to 99 in the dative after `der`: `dreizehnten`, `einundzwanzigsten`."""
    if value < 20:
        return _DE_TEENS[value - 13] + "ten"
    tens, unit = divmod(value, 10)
    cardinal = _DE_TENS[tens - 2]
    if unit:
        cardinal = f"{_DE_UNITS[unit - 1]}und{cardinal}"
    return cardinal + "sten"


_PAST_TWELVE = st.one_of(
    st.tuples(st.just("en"), st.sampled_from(sorted(_EN_PAST_TWELVE))),
    st.tuples(st.just("de"), st.integers(13, 99)),
)


def _past_twelve(language: str, value: int, spelled: bool) -> str:
    """`value` as an ordinal in a sentence, as a word or as a figure."""
    if language == "en":
        written = _EN_PAST_TWELVE[value] if spelled else f"{value}th"
        return f"from the {written} reminder on"
    written = _de_past_twelve(value) if spelled else f"{value}."
    return f"ab der {written} Mahnung"


#: An ordinal figure and the count of its digits, as French and Greek write
#: them before a noun of one form: languages no `ORDINAL_SUFFIX` row reads,
#: whose suffix stays on the figure as written.
_UNREAD_ORDINALS = {
    "fr": ("dès le {}e versement", "dès le {} versement"),
    "el": ("από την {}η δόση", "από την {} δόση"),
}


@given(
    case=st.one_of(
        _PAST_TWELVE,
        st.tuples(st.sampled_from(sorted(_UNREAD_ORDINALS)), st.integers(13, 99)),
    )
)
def test_an_ordinal_figure_past_twelve_never_agrees_with_the_count_of_its_digits(
    case,
) -> None:
    """`the 14th reminder` is no `14 reminders`, `der 21. Mahnung` no `21 Mahnungen`.

    In French and Greek the suffix is read as part of what the figure says.
    """
    language, value = case
    if language in _UNREAD_ORDINALS:
        ordinal, count = (one.format(value) for one in _UNREAD_ORDINALS[language])
    else:
        ordinal = _past_twelve(language, value, spelled=False)
        count = f"{value} reminders" if language == "en" else f"{value} Mahnungen"

    assert not agrees(ordinal, count, language, AnswerForm.VALUE), (ordinal, count)
    assert not agrees(count, ordinal, language, AnswerForm.VALUE), (count, ordinal)
