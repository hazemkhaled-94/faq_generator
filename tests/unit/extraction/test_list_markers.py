"""Which lines of a passage open as a list item, whatever mark the document numbers them with."""

from __future__ import annotations

import pytest
from drivers import Checker, passage

pytestmark = pytest.mark.nlp

_MARKS = [
    ("-", "-"),
    ("1.", "2."),
    ("a)", "b)"),
    ("(a)", "(b)"),
    ("(i)", "(ii)"),
    ("–", "–"),
    ("•", "•"),
]

#: The marks whose list the sentence splitter keeps in one sentence, so that a
#: citation can name a line of it.
_CITED = [("-", "-"), ("a)", "b)"), ("(a)", "(b)"), ("(i)", "(ii)"), ("–", "–")]

_LISTS = {
    "de": (
        "Für die Kontoeröffnung gilt Folgendes. Der Kunde muss vorlegen:\n{a} einen gültigen Ausweis\n{b} eine Meldebescheinigung",
        "Der Kunde muss für die Kontoeröffnung eine Meldebescheinigung vorlegen.",
    ),
    "en": (
        "Opening an account works as follows. The customer must present:\n{a} a valid passport\n{b} proof of address",
        "The customer must present proof of address to open an account.",
    ),
}


@pytest.mark.parametrize("language", ["de", "en"])
@pytest.mark.parametrize(("a", "b"), _CITED)
def test_a_fact_citing_a_line_of_the_last_sentence_resolves(language, a, b) -> None:
    """The list is read by its lines whichever mark numbers them."""
    text, statement = _LISTS[language]
    read = passage(text.format(a=a, b=b), language=language)
    last = len(read.sentences) - 1
    assert read.sentences[last].text.count("\n") == 2, [s.text for s in read.sentences]

    fact = Checker(read).atomic(statement, (last, last + 2))

    assert fact.rejection_code != "evidence_absent", fact.validation_error


@pytest.mark.parametrize(
    ("language", "a", "b", "lead"),
    [
        ("fr", "a)", "b)", "Le client doit présenter :"),
        ("el", "α)", "β)", "Ο πελάτης πρέπει να προσκομίσει:"),
        ("pl", "a)", "b)", "Klient musi przedstawić:"),
    ],
)
def test_the_marker_is_script_neutral_so_a_language_not_configured_reads_the_same(
    language, a, b, lead
) -> None:
    """The lines are found by their mark alone; no language's words are read."""
    from extraction.validation import _lines_of

    text = f"{lead}\n{a} un document\n{b} une preuve"
    read = passage(text, language=language)

    listed = next(one for one in read.sentences if one.text.count("\n") >= 2)

    assert len(_lines_of(listed)) >= 2
    assert read.items == 2


@pytest.mark.parametrize(("a", "b"), _MARKS)
def test_each_item_line_counts(a, b) -> None:
    """The cap's room and the index gate count the lines of a lettered, roman or dashed list."""
    read = passage(
        f"The customer must present:\n{a} a valid passport\n{b} proof of address",
        language="en",
    )

    assert read.items == 2


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_wrapped_line_opening_with_a_date_is_no_list(language) -> None:
    """One such line is a date or an ordinal, not a list: two are needed."""
    from extraction.validation import _lines_of

    text = "Das Konto wird bis zum\n1. Januar geführt und danach geschlossen."
    read = passage(text, language=language)

    assert len(_lines_of(read.sentences[0])) == 1
