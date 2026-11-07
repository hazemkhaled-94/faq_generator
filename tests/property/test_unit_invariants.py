"""What the round trip reads of a figure's unit and of a range, for any value.

`agrees` is what keeps `4 hours` from passing for `48 hours`. These say,
over values nobody wrote down, that the same figure beside another unit is
another answer, and that a range is the two ends it states: both written
apart are the range, and one alone, or a range sharing one end, is not.
In German and English, and in French, Polish and Greek, which no
`NLP_MODELS` row names and where the gate must refuse rather than misfire.

Units are words of one form each, none inside another: a lower-case German
unit symbol is N-145's and a unit spelled inside another N-147's, both
accepted.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from question_generation.gates import agrees

pytestmark = pytest.mark.nlp

#: What a bank, a shop and an office count, by language, and a sentence of
#: the verifier's that states a figure and its unit.
_UNITS = {
    "de": (
        ("Euro", "Prozent", "Tage", "Wochen", "Monate", "Stück", "Kunden", "Karten"),
        "Laut den Bedingungen sind es {} {}.",
    ),
    "en": (
        ("euros", "percent", "days", "weeks", "months", "items", "customers", "cards"),
        "Under the terms it is {} {}.",
    ),
    "fr": (
        ("euros", "jours", "semaines", "mois", "clients", "comptes", "cartes"),
        "Selon les conditions, il s'agit de {} {}.",
    ),
    "pl": (
        ("złotych", "dni", "tygodni", "miesięcy", "klientów", "kart"),
        "Według regulaminu jest to {} {}.",
    ),
    "el": (
        ("ευρώ", "ημέρες", "εβδομάδες", "μήνες", "πελάτες", "κάρτες"),
        "Σύμφωνα με τους όρους είναι {} {}.",
    ),
}

_LANGUAGES = sorted(_UNITS)


@st.composite
def _figure(draw, language: str) -> str:
    """A whole number, or an amount with the decimal comma, or point in English."""
    whole = draw(st.integers(1, 100_000))
    if not draw(st.booleans()):
        return str(whole)
    mark = "." if language == "en" else ","
    return f"{whole}{mark}{draw(st.integers(1, 99)):02d}"


@st.composite
def _two_units(draw, languages=_LANGUAGES):
    """A language, one figure in it and two different units it counts in."""
    language = draw(st.sampled_from(languages))
    units, frame = _UNITS[language]
    first, second = draw(st.permutations(units))[:2]
    return language, draw(_figure(language)), first, second, frame


@given(case=_two_units(), sentence=st.booleans())
def test_one_figure_beside_two_different_units_never_agrees(case, sentence) -> None:
    """`14 Tage` is no `14 Wochen`, whether the verifier answers bare or in a sentence."""
    language, figure, unit, other, frame = case
    recovered = frame.format(figure, other) if sentence else f"{figure} {other}"

    assert not agrees(recovered, f"{figure} {unit}", language), (recovered, unit)


@given(case=_two_units(["de", "en"]), sentence=st.booleans())
def test_one_figure_agrees_with_itself_beside_the_same_unit(case, sentence) -> None:
    """The guard above is no refusal of every figure: `14 Tage` is `14 Tage`.

    In German and English: elsewhere the gate may refuse, which is safe.
    """
    language, figure, unit, _, frame = case
    recovered = frame.format(figure, unit) if sentence else f"{figure} {unit}"

    assert agrees(recovered, f"{figure} {unit}", language), (recovered, unit)


#: The ways each language writes a range's two ends apart, and a unit counted
#: in one form for both. `{a}` and `{b}` are the ends.
_APART = {
    "de": (
        (
            "zwischen {a} und {b} {u}",
            "von {a} bis {b} {u}",
            "mindestens {a} {u}, höchstens {b} {u}",
        ),
        ("Euro", "Tage", "Stück"),
    ),
    "en": (
        (
            "between {a} and {b} {u}",
            "from {a} to {b} {u}",
            "at least {a} {u} and at most {b} {u}",
        ),
        ("euros", "days", "items"),
    ),
    "fr": (("entre {a} et {b} {u}", "de {a} à {b} {u}"), ("euros", "jours")),
    "pl": (("od {a} do {b} {u}",), ("dni", "złotych")),
    "el": (("από {a} έως {b} {u}",), ("ημέρες", "ευρώ")),
}


@st.composite
def _range(draw, languages=_LANGUAGES):
    """A language, a range's two ends, a unit and a way to write the ends apart."""
    language = draw(st.sampled_from(languages))
    forms, units = _APART[language]
    low = draw(st.integers(1, 5_000))
    high = low + draw(st.integers(1, 5_000))
    return (
        language,
        low,
        high,
        draw(st.sampled_from(units)),
        draw(st.sampled_from(forms)),
    )


@given(case=_range())
def test_a_range_agrees_with_its_two_ends_written_apart(case) -> None:
    """`100–110 euros` is `between 100 and 110 euros` and `at least 100 euros and at most 110 euros`."""
    language, low, high, unit, form = case
    key = f"{low}–{high} {unit}"

    assert agrees(form.format(a=low, b=high, u=unit), key, language)


@given(case=_range(), upper=st.booleans())
def test_one_end_of_a_range_never_agrees_with_the_range(case, upper) -> None:
    """`110 m` is not what `100–110 m` says, and neither is `100 m`."""
    language, low, high, unit, _ = case
    end = high if upper else low

    assert not agrees(f"{end} {unit}", f"{low}–{high} {unit}", language)


@given(case=_range(), upper=st.booleans(), shift=st.integers(1, 50))
def test_a_range_sharing_one_end_with_the_key_never_agrees(case, upper, shift) -> None:
    """`100–120 Euro` is not `100–110 Euro`, written whole or apart."""
    language, low, high, unit, form = case
    other = (low, high + shift) if upper else (max(0, low - shift), high)

    assert not agrees(f"{other[0]}–{other[1]} {unit}", f"{low}–{high} {unit}", language)
    assert not agrees(
        form.format(a=other[0], b=other[1], u=unit), f"{low}–{high} {unit}", language
    )
