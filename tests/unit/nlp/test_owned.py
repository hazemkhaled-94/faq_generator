"""What only one passage gives a text: the words and numbers no other passage carries."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.nlp


def test_owned_names_what_only_each_passage_gives() -> None:
    """A word or figure one passage alone carries is that passage's; shared words are nobody's."""
    from nlp.analysis import numerals, owned

    shop = [
        "Standard requests are answered within 48 hours.",
        "Urgent requests are answered within 4 hours.",
    ]
    got = owned("an urgent request, within 4 hours against 48 hours", shop, "en")
    assert got[0] >= numerals("48", "en")
    assert "standard" not in got[0]
    assert got[1] >= {"urgent"} | numerals("4", "en")
    assert not {"request", "hour"} & (got[0] | got[1])

    german = [
        "Standardanfragen werden innerhalb von 48 Stunden beantwortet.",
        "Dringende Anfragen werden innerhalb von 4 Stunden beantwortet.",
    ]
    got = owned("eine dringende Anfrage, in 4 statt 48 Stunden", german, "de")
    assert numerals("48", "de") <= got[0]
    assert "dringend" in got[1]
    assert numerals("4", "de") <= got[1]


def test_a_word_every_passage_carries_is_owned_by_none() -> None:
    """Both passages carrying a word and a figure, neither owns them."""
    from nlp.analysis import owned

    shop = [
        "Standard orders can be returned within 30 days.",
        "Express orders can be returned within 30 days.",
    ]
    assert owned("within 30 days", shop, "en") == (frozenset(), frozenset())
    german = [
        "Standardbestellungen können innerhalb von 30 Tagen zurückgegeben werden.",
        "Expressbestellungen können innerhalb von 30 Tagen zurückgegeben werden.",
    ]
    assert owned("innerhalb von 30 Tagen", german, "de") == (frozenset(), frozenset())
