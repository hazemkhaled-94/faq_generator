"""Mending a word a converter broke at a line, wherever the break is found.

Parsing mends each string it reads, and the table and page joins mend the
string they make, so a second pass over what is already whole has to
change nothing.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st


@pytest.mark.parametrize(
    ("broken", "whole"),
    [
        (
            "monatlich, inklusive Kontofüh- rungsentgelt",
            "monatlich, inklusive Kontoführungsentgelt",
        ),
        ("Zoll- und Steuerrecht", "Zoll- und Steuerrecht"),
        ("pre- and post-trade", "pre- and post-trade"),
    ],
)
def test_a_broken_word_is_joined_and_a_shared_suffix_kept(broken, whole) -> None:
    """The joining words of every configured language complete a hyphen."""
    from nlp.text import rejoined

    assert rejoined(broken) == whole


@given(text=st.text(alphabet="aäbKZ- \n", max_size=40))
def test_mending_twice_is_mending_once(text: str) -> None:
    """A join mends a string already mended, and must leave the rest alone."""
    from nlp.text import rejoined

    once = rejoined(text)

    assert rejoined(once) == once
