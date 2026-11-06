"""Where a passage's sentences are cut, for any figure, reference or abbreviation inside one.

A fact cites sentences, so a sentence cut in two cites half a rule, and two
read as one cite a rule the fact never drew on. These say that what a bank,
a shop or an office writes inside a sentence - an amount, a
rate, `§ 3 Abs. 1`, `Article 5(2)`, an abbreviation of the language's tables
- cuts nothing, and that a sentence ending on an amount is cut from the next.

A bare figure right after an abbreviation and before a lower-case word
(`Ziff. 3 für`) is C-220's, accepted, and is not drawn. An amount is written
with its decimal mark and no thousands marks: one grouped by them may be cut
from its currency in German, which is T2-05's. French, Polish and Greek have
no abbreviation table and are read by the default parse, which may cut an
amount with a decimal comma so too, so only references are written there.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nlp.analysis import _ABBREVIATIONS, _CLOSING_ABBREVIATIONS, sentences

pytestmark = pytest.mark.nlp

#: Two sentences of each domain, by language: the first holds `{}`.
_PAIRS = {
    "de": (
        (
            "Die Bank berechnet {} für die Ersatzkarte.",
            "Der Betrag wird vom Konto abgebucht.",
        ),
        (
            "Das Amt bearbeitet den Antrag {} binnen eines Monats.",
            "Die Behörde informiert schriftlich.",
        ),
        (
            "Im Shop gilt {} für jede Rücksendung.",
            "Die Erstattung erfolgt auf das Zahlungsmittel.",
        ),
    ),
    "en": (
        (
            "The bank charges {} for a replacement card.",
            "The amount is debited from the account.",
        ),
        (
            "The office decides on the application {} within a month.",
            "The applicant is told in writing.",
        ),
        (
            "The shop applies {} to every return.",
            "The refund goes to the original payment method.",
        ),
    ),
    "fr": (
        (
            "La banque facture {} pour la carte de remplacement.",
            "Le montant est débité du compte.",
        ),
        (
            "La mairie traite la demande selon {} sous un mois.",
            "Elle informe le demandeur par écrit.",
        ),
    ),
    "pl": (
        ("Bank pobiera {} za kartę zastępczą.", "Kwota jest pobierana z konta."),
        (
            "Urząd rozpatruje wniosek zgodnie z {} w ciągu miesiąca.",
            "Wnioskodawca otrzymuje decyzję na piśmie.",
        ),
    ),
    "el": (
        (
            "Η τράπεζα χρεώνει {} για την κάρτα αντικατάστασης.",
            "Το ποσό χρεώνεται στον λογαριασμό.",
        ),
        (
            "Η υπηρεσία εξετάζει την αίτηση σύμφωνα με {} εντός ενός μήνα.",
            "Ο αιτών ενημερώνεται γραπτώς.",
        ),
    ),
}

#: The languages whose amounts the default parse may cut from their currency: T2-05.
_CUT = frozenset({"fr", "pl", "el"})

#: The decimal mark each language writes an amount with.
_DECIMAL = {"de": ",", "en": "."}


#: A reference by label and number, as each language writes one: `{}` is
#: the number.
_REFERENCES = {
    "de": ("§ {} Abs. 2", "Art. {} Abs. 1", "Nr. {}", "Abschnitt {}"),
    "en": ("Article {}(2)", "Section {}", "clause {}(b)", "No. {}"),
    "fr": ("l'article {}", "l'article {} alinéa 2"),
    "pl": ("artykuł {}", "§ {}"),
    "el": ("το άρθρο {}",),
}


@st.composite
def _amount(draw, language: str) -> str:
    """An amount with the language's decimal mark, or a rate."""
    decimal = _DECIMAL[language]
    whole = draw(st.integers(1, 99_999))
    cents = draw(st.integers(0, 99))
    return draw(
        st.sampled_from(
            [f"{whole}{decimal}{cents:02d} EUR", f"{whole % 100}{decimal}5 %"]
        )
    )


@st.composite
def _inside(draw, languages: list[str]):
    """A language, the two sentences and a figure or reference to put in the first."""
    language = draw(st.sampled_from(languages))
    first, second = draw(st.sampled_from(_PAIRS[language]))
    number = draw(st.integers(1, 99))
    reference = st.sampled_from(_REFERENCES[language]).map(
        lambda one: one.format(number)
    )
    held = draw(
        reference if language in _CUT else st.one_of(_amount(language), reference)
    )
    return language, first.format(held), second


@given(case=_inside(sorted(_PAIRS)))
def test_a_figure_or_reference_inside_a_sentence_never_cuts_it(case) -> None:
    """`1234,56 EUR`, `§ 3 Abs. 2` or `Article 5(2)` mid-sentence leave two sentences two."""
    language, first, second = case

    cut = [one.text for one in sentences(f"{first} {second}", language)]

    assert cut == [first, second], cut


#: What follows an abbreviation inside a sentence: an amount, or a lower-case
#: phrase; a capitalised noun only after one that never closes a sentence.
_AFTER = {
    "de": ("14,50 EUR", "die Gebühr", "der Kunde"),
    "en": ("14.50 EUR", "the fee", "the customer"),
}
_NOUN = {"de": "Kreditkarten", "en": "Visa cards"}

#: Abbreviations written capitalised in running text, as the table folds them.
_CAPITALISED = frozenset(
    [
        "abs.",
        "ziff.",
        "abschn.",
        "art.",
        "nr.",
        "mo.",
        "di.",
        "mi.",
        "do.",
        "fr.",
        "sa.",
        "so.",
        "no.",
        "sect.",
        "mon.",
        "tue.",
        "wed.",
        "thu.",
        "fri.",
        "sat.",
        "sun.",
    ]
)


@st.composite
def _abbreviated(draw):
    """A language, the two sentences, and an abbreviation of its tables put in the first."""
    language = draw(st.sampled_from(sorted(_AFTER)))
    closing = _CLOSING_ABBREVIATIONS[language]
    # A single letter is half of `z. B.` and `u. a.`, written with its pair.
    listed = sorted(one for one in _ABBREVIATIONS[language] | closing if len(one) > 2)
    word = draw(st.sampled_from(listed))
    after = list(_AFTER[language]) + ([] if word in closing else [_NOUN[language]])
    written = word.capitalize() if word in _CAPITALISED else word
    first, second = draw(st.sampled_from(_PAIRS[language]))
    return language, first.format(f"{written} {draw(st.sampled_from(after))}"), second


@given(case=_abbreviated())
def test_an_abbreviation_of_the_languages_tables_inside_a_sentence_never_cuts_it(
    case,
) -> None:
    """`zzgl. 14,50 EUR`, `inkl. die Gebühr`, `approx. the fee` end no sentence."""
    language, first, second = case

    cut = [one.text for one in sentences(f"{first} {second}", language)]

    assert cut == [first, second], cut


@given(
    language=st.sampled_from(sorted(set(_PAIRS) - _CUT)),
    pair=st.integers(0, 1),
    amount=st.data(),
)
def test_a_sentence_ending_on_an_amount_is_cut_from_the_next(
    language, pair, amount
) -> None:
    """`Die Gebühr beträgt 1234,56 EUR. Der Betrag ...` is two sentences."""
    first, second = _PAIRS[language][pair]
    ended = first.split("{}")[0] + amount.draw(_amount(language)) + "."

    cut = [one.text for one in sentences(f"{ended} {second}", language)]

    assert cut == [ended, second], cut
