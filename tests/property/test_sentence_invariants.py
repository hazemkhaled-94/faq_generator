"""Where a passage's sentences are cut, for any figure, reference or abbreviation inside one.

A fact cites sentences, so a sentence cut in two cites half a rule, and two
read as one cite a rule the fact never drew on. These say that what a bank,
a shop or an office writes inside a sentence - an amount, a
rate, `§ 3 Abs. 1`, `Article 5(2)`, an abbreviation of the language's tables
- cuts nothing, and that a sentence ending on an amount is cut from the next.

A bare figure right after an abbreviation and before a lower-case word
(`Ziff. 3 für`) is C-220's, accepted, and is not drawn. An amount inside a
sentence is drawn in English: in German the parse may cut it from its
currency (T2-05), as the default parse does in French, Polish and Greek,
where only references are written. A sentence ending on an amount is drawn
in both configured languages, its amount without thousands marks.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nlp.analysis import _ABBREVIATIONS, _CLOSING_ABBREVIATIONS, sentences

pytestmark = pytest.mark.nlp

#: Two sentences of each domain, by language: the first holds an amount at
#: `{}`, where the domain states one.
_PAIRS = {
    "de": (
        (
            "Die Bank berechnet {} für die Ersatzkarte.",
            "Der Betrag wird vom Konto abgebucht.",
        ),
        (
            "Der Shop erstattet {} für jede Rücksendung.",
            "Die Erstattung erfolgt auf das Zahlungsmittel.",
        ),
        ("Das Amt erhebt {} für den Antrag.", "Die Gebühr ist sofort fällig."),
    ),
    "en": (
        (
            "The bank charges {} for a replacement card.",
            "The amount is debited from the account.",
        ),
        (
            "The shop refunds {} for every return.",
            "The refund goes to the original payment method.",
        ),
        ("The office charges {} for the application.", "The fee is due at once."),
    ),
}

#: The same, the first naming a reference at `{}`, in every language.
_CITING = {
    "de": (
        (
            "Die Bank sperrt die Karte nach {} der Bedingungen.",
            "Der Kunde wird schriftlich informiert.",
        ),
        (
            "Das Amt bearbeitet den Antrag nach {} binnen eines Monats.",
            "Die Behörde informiert schriftlich.",
        ),
    ),
    "en": (
        (
            "The bank blocks the card under {} of the terms.",
            "The customer is told in writing.",
        ),
        (
            "The office decides on the application under {} within a month.",
            "The applicant is told in writing.",
        ),
    ),
    "fr": (
        (
            "La banque bloque la carte selon {} des conditions.",
            "Le client est informé par écrit.",
        ),
        (
            "La mairie traite la demande selon {} sous un mois.",
            "Elle informe le demandeur par écrit.",
        ),
    ),
    "pl": (
        (
            "Bank blokuje kartę zgodnie z {} regulaminu.",
            "Klient jest informowany na piśmie.",
        ),
        (
            "Urząd rozpatruje wniosek zgodnie z {} w ciągu miesiąca.",
            "Wnioskodawca otrzymuje decyzję na piśmie.",
        ),
    ),
    "el": (
        (
            "Η τράπεζα μπλοκάρει την κάρτα σύμφωνα με {} των όρων.",
            "Ο πελάτης ενημερώνεται γραπτώς.",
        ),
        (
            "Η υπηρεσία εξετάζει την αίτηση σύμφωνα με {} εντός ενός μήνα.",
            "Ο αιτών ενημερώνεται γραπτώς.",
        ),
    ),
}

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
def _inside(draw):
    """A language, two sentences and an amount or a reference put in the first.

    An amount in English only: a German one is now and then cut from its
    currency, with or without thousands marks, which is T2-05's.
    """
    language = draw(st.sampled_from(sorted(_CITING)))
    if language == "en" and draw(st.booleans()):
        first, second = draw(st.sampled_from(_PAIRS[language]))
        return language, first.format(draw(_amount(language))), second
    first, second = draw(st.sampled_from(_CITING[language]))
    number = draw(st.integers(1, 99))
    reference = draw(st.sampled_from(_REFERENCES[language])).format(number)
    return language, first.format(reference), second


@given(case=_inside())
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
    language=st.sampled_from(sorted(_PAIRS)),
    pair=st.integers(0, 2),
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
