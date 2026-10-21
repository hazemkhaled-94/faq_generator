"""What the mend leaves of a ligature and of a joiner a script spells with."""

from __future__ import annotations

import pytest

from preprocessing.parsing.pipelines.pdf import _mend


@pytest.mark.xfail(
    strict=True,
    reason=(
        "_mend composes to NFC, which keeps a presentation-form ligature "
        "(U+FB00-FB06) that docling-parse's glyph list emits for an 'ff' or 'fi' "
        "glyph, so 'Kontoeröﬀnung' is stored and searched unlike 'Kontoeröffnung'"
    ),
)
@pytest.mark.parametrize(
    ("drawn", "spelled"),
    [
        ("Kontoeröﬀnung", "Kontoeröffnung"),
        ("ﬁnanzierung", "finanzierung"),
        ("Oﬄine-Zahlung", "Offline-Zahlung"),
        ("certiﬁed reﬂex", "certified reflex"),
    ],
)
def test_a_ligature_is_spelled_as_its_letters(drawn, spelled) -> None:
    """A quote, a search or a lemma of the word holds the letters, not the glyph."""
    assert _mend(drawn) == spelled


@pytest.mark.xfail(
    strict=True,
    reason=(
        "_mend drops every format character, ZWNJ and ZWJ too, which Persian and "
        "the Indic scripts spell words with, so 'می\u200cخواهم' is stored as the "
        "misspelling 'میخواهم'"
    ),
)
@pytest.mark.parametrize(
    "word",
    ["\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645", "\u0915\u094d\u200d\u0937"],
    ids=["persian-zwnj", "devanagari-zwj"],
)
def test_a_joiner_a_word_is_spelled_with_stays(word) -> None:
    """A zero-width non-joiner or joiner is part of the word's spelling."""
    assert _mend(word) == word


@pytest.mark.parametrize(
    ("drawn", "spelled"),
    [
        ("Nr.\u00a05", "Nr. 5"),
        ("5\u202f%", "5 %"),
        ("\u200fשלום\u200e", "שלום"),
        ("\u2067+49 30 1234\u2069", "+49 30 1234"),
    ],
)
def test_spaces_and_bidi_marks_are_folded(drawn, spelled) -> None:
    """The control: what the mend promises for spaces and bidi marks."""
    assert _mend(drawn) == spelled
