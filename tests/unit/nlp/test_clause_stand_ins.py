"""The polite-address rule and the exceptive clause, on documents built by hand.

The sentence tests in `test_references.py` hold what a parse makes of a
statement. These hold the rule itself, token by token, so that a boundary of
it (the word right after an opening pronoun, an exception that opens at the
very end, a verb that is the root of the sentence) is pinned without waiting
for a parser to produce it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from nlp import analysis


class _Doc:
    """A document as far as the rules read it: tokens, slices and a language."""

    def __init__(self, language: str, words: list[str]) -> None:
        self.lang_ = language
        self.user_data: dict = {}
        self._tokens = [
            SimpleNamespace(
                i=i,
                text=word,
                is_punct=not any(c.isalnum() for c in word),
                doc=self,
            )
            for i, word in enumerate(words)
        ]

    def __getitem__(self, index):
        return self._tokens[index]

    def __len__(self) -> int:
        return len(self._tokens)

    def __iter__(self):
        return iter(self._tokens)


def _polite(language: str, words: list[str], at: int) -> bool:
    doc = _Doc(language, words)
    return analysis._polite(doc[at])


@pytest.mark.parametrize(
    ("words", "at"),
    [
        # Polite forms sit anywhere a capital is no sign of a sentence start.
        (["Wenn", "Sie", "Ihre", "PIN", "vergessen"], 1),
        (["Wenn", "Sie", "Ihre", "PIN", "vergessen"], 2),
        (["Die", "Bank", "schickt", "Ihnen", "die", "Karte"], 3),
        (["Bitte", "senden", "Sie", "die", "Ware", "zurück"], 2),
    ],
)
def test_a_polite_form_inside_a_statement_is_polite_without_any_other(
    words, at
) -> None:
    """Inside a statement only the capital is read, so nothing else has to follow."""
    assert _polite("de", words, at)


@pytest.mark.parametrize(
    "words",
    [
        ["Sie", "Ihnen", "helfen", "wir", "gern"],
        ["Sie", "Ihre", "Karte", "sperren", "können", "Sie"],
        ["Sie", "können", "Ihre", "Karte", "sperren"],
        ["Sie", "erhalten", "Ihre", "Bestellung", "bald"],
    ],
)
def test_an_opening_sie_is_polite_when_a_polite_form_follows_it(words) -> None:
    """Including the word right after it: the later form is looked for from there."""
    assert _polite("de", words, 0)


@pytest.mark.parametrize(
    "words",
    [
        ["Sie", "werden", "innerhalb", "von", "5", "Tagen", "geliefert"],
        ["Sie", "haben", "keinen", "Anspruch", "auf", "Erstattung"],
        ["Sie", "wurde", "gesperrt", "."],
    ],
)
def test_an_opening_sie_with_no_polite_form_after_it_stays_a_reference(words) -> None:
    """Capitalised either way at the start, so nothing says it names the reader."""
    assert not _polite("de", words, 0)


def test_punctuation_before_an_opening_sie_does_not_make_it_inside() -> None:
    """A quotation mark or a bullet opens the statement as much as nothing does."""
    assert not _polite("de", ['"', "Sie", "werden", "geliefert"], 1)
    assert _polite("de", ['"', "Sie", "können", "Ihre", "Karte", "sperren"], 1)


@pytest.mark.parametrize("word", ["sie", "ihre", "SIE", "Ihr", "sie."])
def test_only_the_written_polite_forms_count(word) -> None:
    """Lower case is the third person, and a word outside the table is no form."""
    words = ["Wenn", word, "Ihre", "Karte", "verlieren"]
    assert _polite("de", words, 1) is (word == "Ihr")


def test_a_language_with_no_polite_forms_has_none() -> None:
    """The table is keyed by ISO 639-1 code; a code it lacks is no polite form, not an error."""
    assert not _polite("fr", ["Wenn", "Sie", "Ihre", "Karte"], 1)
    assert not _polite("en", ["If", "Sie", "Ihre", "card"], 1)


# ── The clause an exceptive run opens ─────────────────────────────────────


def _verb_doc(language="de"):
    """`Karte wird gesperrt , außer sie ist ersetzt .` with a hand-made parse.

    0 Karte, 1 wird (root verb), 2 gesperrt, 3 `,`, 4 außer, 5 sie, 6 ist
    (verb, hangs from the root), 7 ersetzt, 8 `.`
    """
    doc = _Doc(
        language,
        ["Karte", "wird", "gesperrt", ",", "außer", "sie", "ist", "ersetzt", "."],
    )
    pos = ["NOUN", "AUX", "VERB", "PUNCT", "ADP", "PRON", "AUX", "VERB", "PUNCT"]
    heads = [1, 1, 1, 1, 6, 6, 1, 6, 1]
    for token, p, h in zip(doc, pos, heads, strict=True):
        token.pos_ = p
        token.head = doc[h]
    return doc


def _exceptive(monkeypatch, starts, doc):
    calls = []

    def fake(seen):
        calls.append(seen)
        return set(), set(starts)

    monkeypatch.setattr(analysis, "_exceptive_tokens", fake)
    return calls


def test_the_verb_of_the_clause_an_exception_opens_is_found(monkeypatch) -> None:
    """From the word the run is followed by, up the parse to the verb of that clause."""
    doc = _verb_doc()
    _exceptive(monkeypatch, {5}, doc)

    assert analysis._exception_verbs(doc) == frozenset({6})


def test_a_run_opening_in_the_root_clause_marks_no_clause_beneath_it(
    monkeypatch,
) -> None:
    """The root verb heads the sentence, not a clause under another."""
    doc = _verb_doc()
    _exceptive(monkeypatch, {1}, doc)

    assert analysis._exception_verbs(doc) == frozenset()


def test_a_run_ending_the_document_marks_nothing_and_raises_nothing(
    monkeypatch,
) -> None:
    """`except` as the last word is followed by the end of the text, which is no token."""
    doc = _verb_doc()
    _exceptive(monkeypatch, {len(doc)}, doc)

    assert analysis._exception_verbs(doc) == frozenset()


def test_the_verbs_are_read_once_per_document(monkeypatch) -> None:
    """`_clause` asks for every token, so the answer is kept on the document."""
    doc = _verb_doc()
    calls = _exceptive(monkeypatch, {5}, doc)

    first = analysis._exception_verbs(doc)
    second = analysis._exception_verbs(doc)

    assert first == second == frozenset({6})
    assert len(calls) == 1
    assert doc.user_data["exception_verbs"] == first
