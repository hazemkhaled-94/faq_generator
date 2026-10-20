"""Formal address, for any statement.

German `Sie` is spelled like the third person plural, so the reading of it as
the reader rests on what else the statement holds. These say, over statements
nobody wrote down, which way that goes: only a polite form after an opening
`Sie` makes it polite, and anything inside a statement that is spelled as one
is.
"""

from __future__ import annotations

from types import SimpleNamespace

from hypothesis import given
from hypothesis import strategies as st

from nlp import analysis

_FORMS = sorted(analysis._POLITE["de"])
_OTHER = ["Karte", "können", "die", "Bank", "sperren", "wurde", "Konto", "sie", "ihre"]
_WORDS = st.sampled_from([*_FORMS, *_OTHER, ",", "."])


class _Doc:
    """A document as far as the rule reads it: tokens, slices and a language."""

    def __init__(self, language: str, words: list[str]) -> None:
        self.lang_ = language
        self.tokens = [
            SimpleNamespace(
                i=i, text=word, is_punct=not any(c.isalnum() for c in word), doc=self
            )
            for i, word in enumerate(words)
        ]

    def __getitem__(self, index):
        return self.tokens[index]


def _doc(language: str, words: list[str]) -> _Doc:
    return _Doc(language, words)


@given(
    before=st.lists(_WORDS, max_size=4),
    form=st.sampled_from(_FORMS),
    after=st.lists(_WORDS, max_size=5),
)
def test_a_form_inside_a_statement_is_polite_whatever_follows(
    before, form, after
) -> None:
    """Capitalised mid-statement can only be formal address."""
    words = ["Wenn", *before, form, *after]
    doc = _doc("de", words)

    assert analysis._polite(doc[len(before) + 1])


@given(words=st.lists(_WORDS, max_size=8))
def test_an_opening_sie_is_polite_only_with_a_polite_form_after_it(words) -> None:
    """Otherwise it stays a reference: `Sie werden geliefert` is the third person."""
    later = [w for w in words if w in _FORMS]
    doc = _doc("de", ["Sie", *words])

    assert analysis._polite(doc[0]) is bool(later)


@given(
    words=st.lists(_WORDS, min_size=1, max_size=8),
    language=st.sampled_from(["en", "fr", "it", ""]),
)
def test_no_other_language_has_a_polite_form(words, language) -> None:
    """The table is keyed by ISO 639-1 code, and a code it lacks is never polite."""
    doc = _doc(language, ["Wenn", *words])

    assert not any(analysis._polite(token) for token in doc.tokens)


@given(words=st.lists(_WORDS, min_size=1, max_size=8))
def test_a_word_outside_the_table_is_never_polite(words) -> None:
    """Lower case and every other word are the third person or no pronoun at all."""
    doc = _doc("de", ["Wenn", *words])

    for token in doc.tokens:
        if token.text not in _FORMS:
            assert not analysis._polite(token)
