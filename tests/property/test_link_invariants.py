"""The pairs a bridge pass is held back from, for any set of passages and any hold.

A stored bridge rests on a pair of passages, and a pass that runs again must
not write a second bridge on that pair. Which pairs the documents link, and
which a store holds, is anyone's: these say what holds whatever they are.
"""

from __future__ import annotations

from dataclasses import replace
from itertools import combinations

import pytest
from drivers import passage
from hypothesis import given, settings
from hypothesis import strategies as st

from extraction.links import linked

pytestmark = pytest.mark.nlp

_PARENTS = ("Fees", "Delivery", "Accounts")


def _passages(count: int, parents: list[str], language: str):
    return [
        replace(
            passage(
                f"Item {i} costs {i} EUR.",
                language=language,
                section_path=f"{parents[i - 1]} > Part {i}",
                id=i,
            ),
            doc_sha256="doc-a",
        )
        for i in range(1, count + 1)
    ]


@st.composite
def worlds(draw):
    """Passages under a few parents, the topic each is in, and some held pairs."""
    count = draw(st.integers(2, 6))
    parents = [draw(st.sampled_from(_PARENTS)) for _ in range(count)]
    topics = {i: draw(st.integers(1, 2)) for i in range(1, count + 1)}
    every = [frozenset(pair) for pair in combinations(range(1, count + 1), 2)]
    held = frozenset(draw(st.sets(st.sampled_from(every))))
    return count, parents, topics, held


def _keys(links):
    return [frozenset(p.id for p in link.passages[:2]) for link in links]


@settings(max_examples=120, deadline=None)
@given(
    world=worlds(),
    wanted=st.integers(1, 4),
    language=st.sampled_from(["en", "de"]),
)
def test_linked_never_offers_a_held_pair_and_never_offers_a_pair_twice(
    world, wanted, language
) -> None:
    """Whatever the documents link, the first two passages of a link are a free pair."""
    count, parents, topics, held = world
    passages = _passages(count, parents, language)

    got = linked(passages, passages, topics, wanted, 2, held=held)

    keys = _keys(got)
    assert not set(keys) & held, set(keys) & held
    assert len(set(keys)) == len(keys)


@settings(max_examples=80, deadline=None)
@given(world=worlds(), wanted=st.integers(1, 4))
def test_holding_a_pair_the_pass_would_not_offer_changes_nothing(world, wanted) -> None:
    """A hold costs only the pairs it names."""
    count, parents, topics, held = world
    passages = _passages(count, parents, "en")
    free = linked(passages, passages, topics, wanted, 2)
    offered = set(_keys(free))

    got = linked(passages, passages, topics, wanted, 2, held=held - offered)

    assert got == free
