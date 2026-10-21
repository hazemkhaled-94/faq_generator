"""The space-grouped amount merge and the ordinal reading, where their mutants survived.

`_grouped` merges a space-grouped run into one token only where `_amount`
says it is an amount, and gives it its own text as its lemma; `ordinal`
reads `3rd`, `Dritte` and a German `3.` inside a sentence as ordinals.
"""

from __future__ import annotations

import pytest

from nlp.analysis import figures, is_number, ordinal, parse
from question_generation.gates import agrees

pytestmark = pytest.mark.nlp


def test_a_run_opening_the_text_beside_no_currency_is_two_figures() -> None:
    """Alone in its text a run is an amount; at its start beside a count noun it is not."""
    assert figures("100 000 Kunden sind betroffen.", "de") == [100.0, 0.0]


def test_a_merged_amount_is_its_own_lemma() -> None:
    """The merge keeps the amount's text as its lemma, for every lemma reader."""
    merged = [one for one in parse("Bis zu 100 000 Euro sind geschützt.", "de") if " " in one.text]

    assert [one.lemma_ for one in merged] == ["100 000"]


def test_a_run_of_more_than_two_groups_is_not_merged_in_part() -> None:
    """`1 000 000` stays three figures, as the ponytail note says, not 1000 and 0."""
    assert len(figures("Deposits up to EUR 1 000 000 are covered.", "en")) == 3


def test_an_english_ordinal_closing_a_sentence_is_still_an_ordinal() -> None:
    """A letter suffix is no full stop: `the 3rd.` is the third, never the count 3."""
    assert not agrees("The fee is due on the 3rd.", "3", "en")


def test_a_german_figure_closing_a_sentence_is_the_count() -> None:
    """At a sentence's end the full stop closes the sentence: `3.` is 3."""
    assert ordinal(parse("Es sind 3.", "de")[2]) is None


def test_a_capitalised_ordinal_word_is_read() -> None:
    """`Dritte` opening a sentence is the ordinal `dritte`."""
    assert ordinal(parse("Dritte Mahnungen kosten 5 Euro.", "de")[0]) == "3"


def test_an_ordinal_word_tagged_as_an_adjective_states_a_number() -> None:
    """`third` is tagged ADJ, and is a number all the same."""
    token = parse("The third reminder costs 5 EUR.", "en")[1]

    assert token.pos_ == "ADJ"
    assert is_number(token)
