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
from nlp.analysis import AMOUNT_WORDS, REFERENCE_LABELS, figures, parse
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
