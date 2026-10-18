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


def test_a_compound_the_document_prints_whole_keeps_its_hyphen() -> None:
    """A shop's terms print "third-party" on one line and break it on another."""
    from nlp.text import printed, rejoined

    whole = printed(["Payments through a third-party provider are refunded."])

    assert rejoined("sent with a third- party courier", whole) == (
        "sent with a third-party courier"
    )
    assert rejoined("inklusive Kontofüh- rungsentgelt", whole) == (
        "inklusive Kontoführungsentgelt"
    )


@given(
    text=st.text(alphabet="aäbKZ- \n", max_size=40),
    seen=st.text(alphabet="aäbKZ- ", max_size=20),
)
def test_mending_twice_is_mending_once(text: str, seen: str) -> None:
    """A join mends a string already mended, and must leave the rest alone."""
    from nlp.text import printed, rejoined

    whole = printed([seen])
    once = rejoined(text, whole)

    assert rejoined(once, whole) == once
