"""What a numbered reference reads as, for any number and any sentence around it.

A passage that names `Artikel 5`, `§ 3 Abs. 1` or `Section 4.2(b)` links to the
part its document numbers so; `label_word` and `numbered` are what read the
label and the number. These say the reading is the same however long the
sentence holding it, and that a list after a plural label names every number
in it. In French, Polish and Greek, which no `NLP_MODELS` row names, a
reference is read right or not at all, never as another number.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from extraction.validation import label_word, numbered
from nlp.analysis import parse

pytestmark = pytest.mark.nlp

#: The label words a corpus of each language learns from its headings, as
#: written in a sentence, and sentences of a bank, a shop and an office that
#: name one. `{}` is the reference; the first frame is the reference alone.
_CITING = {
    "de": (
        ("Artikel", "Abschnitt", "§", "Ziffer"),
        (
            "{}",
            "Gemäß {} gilt die Gebühr.",
            "Die Bank kann die Karte nach {} der Bedingungen sperren, wenn der Kunde nicht zahlt.",
            "Rücksendungen sind nach {} innerhalb von 14 Tagen kostenlos.",
            "Das Amt bearbeitet den Antrag gemäß {} binnen eines Monats.",
        ),
    ),
    "en": (
        ("Article", "Section", "Clause"),
        (
            "{}",
            "Under {} the fee applies.",
            "The bank may block the card under {} of these terms if the customer does not pay.",
            "Returns are free within 14 days as set out in {}.",
            "The office decides on the application under {} within one month.",
        ),
    ),
    "fr": (
        ("Article",),
        (
            "{}",
            "Les frais sont dus selon {}.",
            "La banque peut bloquer la carte conformément à {} des conditions.",
            "Le retour est gratuit selon {} pendant 14 jours.",
        ),
    ),
    "pl": (
        ("Artykuł", "Paragraf"),
        (
            "{}",
            "Zgodnie z {} opłata obowiązuje.",
            "Bank może zablokować kartę na podstawie {} regulaminu.",
            "Urząd rozpatruje wniosek zgodnie z {} w ciągu miesiąca.",
        ),
    ),
    "el": (
        ("Άρθρο",),
        (
            "{}",
            "Σύμφωνα με το {} ισχύει η χρέωση.",
            "Η τράπεζα μπορεί να μπλοκάρει την κάρτα βάσει του {} των όρων.",
        ),
    ),
}

#: What may follow the number inside the reference: a sub-clause in brackets,
#: or a paragraph the language's abbreviation names.
_AFTER = {
    "de": ("", "(2)", " Abs. 2", " Satz 1"),
    "en": ("", "(2)", "(b)", " para. 2"),
    "fr": ("", " alinéa 2"),
    "pl": ("", " ust. 2", " pkt 3"),
    "el": ("", " παρ. 2"),
}

_NUMBER = st.lists(st.integers(1, 99), min_size=1, max_size=3).map(
    lambda parts: ".".join(map(str, parts))
)


def _read(text: str, language: str, label: str) -> list[tuple[str, list[str]]]:
    """Every label word the text holds, with the numbers it names."""
    tokens = list(parse(text, language))
    words = (label.casefold(),)
    return [
        (found, numbered(tokens, at))
        for at in range(len(tokens) - 1)
        if (found := label_word(tokens, at, words, language))
    ]


@st.composite
def _citing(draw, languages: list[str]):
    """A language, a label word, a number, what follows it and a sentence holding it."""
    language = draw(st.sampled_from(languages))
    labels, frames = _CITING[language]
    label = draw(st.sampled_from(labels))
    number = draw(_NUMBER)
    after = draw(st.sampled_from(_AFTER[language]))
    return (
        language,
        label,
        number,
        f"{label} {number}{after}",
        draw(st.sampled_from(frames)),
    )


@given(case=_citing(["de", "en"]))
def test_a_numbered_reference_reads_the_same_in_a_longer_sentence(case) -> None:
    """`Artikel 5(2)` alone and inside a bank's rule name the one article 5."""
    language, label, number, reference, frame = case

    assert _read(frame.format(reference), language, label) == [
        (label.casefold(), [number])
    ], frame.format(reference)


@given(case=_citing(["fr", "pl", "el"]))
def test_a_reference_in_a_language_with_no_pipeline_is_read_right_or_not_at_all(
    case,
) -> None:
    """`l'Article 5` may go unread in French; it is never read as article 2."""
    language, label, number, reference, frame = case

    assert _read(frame.format(reference), language, label) in (
        [],
        [(label.casefold(), [number])],
    ), frame.format(reference)


#: A plural label, how a language joins the last of a list, and a sentence.
_PLURAL = {
    "de": ("Abschnitte", "abschnitt", "und", "Die Gebühren regeln die {}."),
    "en": ("Sections", "section", "and", "The fees are set out in {}."),
}


@given(
    language=st.sampled_from(sorted(_PLURAL)),
    sections=st.lists(st.integers(1, 99), min_size=2, max_size=4, unique=True),
)
def test_a_plural_label_names_every_number_of_its_list(language, sections) -> None:
    """`Sections 7, 9 and 11` names all three, and no count of anything."""
    label, word, conjunction, frame = _PLURAL[language]
    *head, last = map(str, sections)
    reference = f"{label} {', '.join(head)} {conjunction} {last}"
    tokens = list(parse(frame.format(reference), language))
    at = next(i for i, token in enumerate(tokens) if token.text == label)

    assert label_word(tokens, at, (word,), language) == word
    assert numbered(tokens, at) == [*head, last], frame.format(reference)
