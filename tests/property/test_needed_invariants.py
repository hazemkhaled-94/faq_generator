"""Which passages a question needs, read off the quotes."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from question_generation.checker import needed, tied
from question_generation.verifier import Part

_SENTENCES = [
    "An account with no payment for 24 months is dormant.",
    "A dormant account is charged 30 EUR a year.",
    "Orders over 50 EUR are shipped free of charge.",
    "Gift cards cannot be exchanged for cash.",
    "Ein Konto ohne Zahlung gilt als ruhend.",
    "Bestellungen über 50 EUR werden versandkostenfrei geliefert.",
]


@st.composite
def _cases(draw):
    texts = draw(
        st.lists(st.sampled_from(_SENTENCES), min_size=2, max_size=4, unique=True)
    )
    parts = draw(
        st.lists(
            st.lists(st.sampled_from(texts + ["held nowhere at all"]), max_size=3),
            max_size=4,
        )
    )
    return texts, tuple(Part(f"p{at}", tuple(one)) for at, one in enumerate(parts))


def _holds(parts, texts):
    return [
        {n for n, part in enumerate(parts) if any(q == text for q in part.quotes)}
        for text in texts
    ]


@given(_cases())
def test_needed_keeps_every_passage_alone_holding_a_part(case) -> None:
    """A passage holding a part no other passage holds is never dropped."""
    texts, parts = case
    got = needed(parts, texts)
    holds = _holds(parts, texts)
    if got is None:
        assert not any(holds)
        return
    for at, mine in enumerate(holds):
        others = set().union(*(h for i, h in enumerate(holds) if i != at))
        if mine - others:
            assert at in got
    assert got == tuple(sorted(set(got)))
    assert all(0 <= at < len(texts) for at in got)


@given(_cases())
def test_with_no_passage_of_its_own_one_holding_the_most_is_kept(case) -> None:
    """Without a unique part, the first of the fullest; alone where it holds them all."""
    texts, parts = case
    holds = _holds(parts, texts)
    got = needed(parts, texts)
    own = [
        at
        for at, mine in enumerate(holds)
        if mine - set().union(*(h for i, h in enumerate(holds) if i != at))
    ]
    if got is None or own:
        return
    best = max(len(h) for h in holds)
    first = min(at for at, h in enumerate(holds) if len(h) == best)
    assert first in got
    if holds[first] == set().union(*holds):
        assert got == (first,)


@given(_cases())
def test_the_passages_needed_hold_every_part_some_passage_holds(case) -> None:
    """No part a passage states is lost by the narrowing."""
    texts, parts = case
    holds = _holds(parts, texts)
    got = needed(parts, texts)
    if got is None:
        return
    assert set().union(*holds) <= set().union(*(holds[at] for at in got))


@given(_cases())
def test_tied_means_every_passage_holds_the_same_parts(case) -> None:
    """Tied implies no passage has a part of its own and some quote is held."""
    texts, parts = case
    holds = _holds(parts, texts)
    assert tied(parts, texts) == (any(holds) and all(h == holds[0] for h in holds))
