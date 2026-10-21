"""What the mend leaves of a ligature and of a joiner a script spells with."""

from __future__ import annotations

import pytest

from preprocessing.parsing.pipelines.pdf import _mend


@pytest.mark.parametrize(
    ("drawn", "spelled"),
    [
        ("Kontoeröﬀnung", "Kontoeröffnung"),
        ("ﬁnanzierung", "finanzierung"),
        ("Oﬄine-Zahlung", "Offline-Zahlung"),
        ("certiﬁed reﬂex", "certified reflex"),
        ("\ufb13", "\u0574\u0576"),
    ],
)
def test_a_ligature_is_spelled_as_its_letters(drawn, spelled) -> None:
    """A quote, a search or a lemma of the word holds the letters, not the glyph."""
    assert _mend(drawn) == spelled


@pytest.mark.parametrize("kept", ["5 m²", "½ Jahr", "Ｎｒ. 5"])
def test_a_superscript_a_fraction_and_a_full_width_letter_are_kept(kept) -> None:
    """Only the ligatures are spelled out, not every compatibility character."""
    assert _mend(kept) == kept


@pytest.mark.parametrize(
    "word",
    [
        "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645",
        "\u0915\u094d\u200d\u0937",
        "\u1781\u17d2\u200d\u1798",
        "\u1019\u200d\u103c",
        "\u0f40\u200d\u0fb2",
        "\U0001f468\u200d\U0001f469\u200d\U0001f467",
        "\u2764\ufe0f\u200d\U0001f525",
        "\U0001f9d1\U0001f3fd\u200d\U0001f4bb",
    ],
    ids=[
        "persian-zwnj",
        "devanagari-zwj",
        "khmer-zwj",
        "myanmar-zwj",
        "tibetan-zwj",
        "emoji-family",
        "emoji-selector",
        "emoji-skin-tone",
    ],
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


@pytest.mark.parametrize(
    ("drawn", "spelled"),
    [
        ("Konto ‌ Nr", "Konto  Nr"),
        ("5‌%", "5%"),
        ("Preis:‍ 5 EUR", "Preis: 5 EUR"),
        ("e‌‍ x", "e x"),
        ("می‌ 5", "می 5"),
    ],
)
def test_a_joiner_beside_anything_but_a_joining_letter_is_dropped(
    drawn, spelled
) -> None:
    """Beside a space, a digit, a sign or another joiner a joiner spells nothing."""
    assert _mend(drawn) == spelled
