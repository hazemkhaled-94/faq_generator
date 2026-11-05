"""Two gates over text that holds no word they can count.

A passage of figures alone (a fee grid, a table of limits) is no credits
page, whatever language it is filed under, and is read without a division by
its zero words. A follow-up whose key is only "yes" says nothing its thread
did not, so it cannot be the turn that moves the thread on.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.nlp

GRID = "| 4,90 | 12,00 |\n| 1.000 | 250 |"


@pytest.mark.parametrize("language", ["de", "en", "fr", "el"])
def test_a_passage_of_figures_alone_names_no_parties(language) -> None:
    """No alphabetic word, so no share of names to read."""
    from question_generation.gates import names_parties

    assert names_parties(GRID, language) is False


@pytest.mark.parametrize(
    ("language", "key", "thread"),
    [
        ("de", "Ja.", [("Kostet die Karte etwas?", "4 Euro im Monat")]),
        ("en", "Yes.", [("Does the card cost anything?", "4 euros a month")]),
    ],
)
def test_a_key_with_no_content_word_adds_nothing(language, key, thread) -> None:
    """Nothing in it, so nothing new in it."""
    from question_generation.gates import adds_to

    assert adds_to(key, thread, language) is False
