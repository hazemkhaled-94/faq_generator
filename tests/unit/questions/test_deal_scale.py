"""The deal's relative floor at the size of a topic ten times this build's.

The floor is read off a topic's own vectors: the cosine the closest `share`
of its cross-passage fact pairs reach. Taken from a dense n x n product, a
topic of 50,000 facts asked for 20 GB. Past a budget of pairs the quantile is
estimated from a seeded sample of them, and below it the answer is exactly
what it was.
"""

from __future__ import annotations

import time
import tracemalloc
from types import SimpleNamespace

import numpy as np
import pytest

from question_generation import selection
from question_generation.models import SourceFact, SourcePassage
from question_generation.selection import Deal, _relative_floor


def _stub(count: int, width: int = 8, seed: int = 5, per_passage: int = 3):
    """Facts with a vector and a passage each, in clusters so cosines spread."""
    rng = np.random.default_rng(seed)
    centres = rng.normal(size=(max(count // 40, 2), width))
    members = centres[rng.integers(len(centres), size=count)] + 0.6 * rng.normal(
        size=(count, width)
    )
    members /= np.linalg.norm(members, axis=1, keepdims=True)
    return [
        SimpleNamespace(
            id=i, passage_id=i // per_passage, embedding=tuple(members[i].tolist())
        )
        for i in range(count)
    ]


def _exact(facts, share: float) -> float:
    """The floor as it was computed before the budget: the dense product."""
    vectors = np.array([fact.embedding for fact in facts], dtype=float)
    ids = np.array([fact.passage_id for fact in facts])
    pairs = np.triu(ids[:, None] != ids[None, :], k=1)
    cosines = np.clip((vectors @ vectors.T)[pairs], 0.0, 1.0)
    return float(np.quantile(cosines, 1 - share))


def test_a_topic_under_the_budget_has_exactly_the_floor_it_had() -> None:
    """The branch every topic of this build takes. The floor reads vectors, no language."""
    facts = _stub(300)

    assert _relative_floor(facts, 0.05) == _exact(facts, 0.05)  # type: ignore[arg-type]


def test_a_topic_over_the_budget_is_estimated_within_a_hundredth(monkeypatch) -> None:
    """5,000 facts, a budget a fortieth of their pairs, the same answer to 0.01."""
    monkeypatch.setattr(selection, "_PAIR_BUDGET", 300_000)
    facts = _stub(5_000)

    sampled = _relative_floor(facts, 0.05)  # type: ignore[arg-type]

    assert abs(sampled - _exact(facts, 0.05)) < 0.01  # type: ignore[arg-type]


def test_the_sample_is_seeded_by_the_facts(monkeypatch) -> None:
    """The same topic gives the same floor twice, so a deal is repeatable."""
    monkeypatch.setattr(selection, "_PAIR_BUDGET", 50_000)
    facts = _stub(2_000)

    assert _relative_floor(facts, 0.05) == _relative_floor(facts, 0.05)  # type: ignore[arg-type]


def test_a_sample_never_pairs_a_passage_with_itself(monkeypatch) -> None:
    """Every fact in one passage: no cross-passage pair, so no floor."""
    monkeypatch.setattr(selection, "_PAIR_BUDGET", 10)
    facts = [
        SimpleNamespace(id=i, passage_id=1, embedding=(1.0, 0.0)) for i in range(100)
    ]

    assert _relative_floor(facts, 0.05) == 0.0  # type: ignore[arg-type]


def test_a_deal_over_fifty_thousand_facts_stays_under_a_memory_bound() -> None:
    """The dense product of these was 20 GB; the deal is built in under 300 MB."""
    rng = np.random.default_rng(1)
    vectors = rng.normal(size=(50_000, 8))
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    passages = [
        SourcePassage(
            id=i,
            text=f"Passage {i}.",
            doc_sha256=f"d{i // 100}",
            language="de" if i % 2 else "en",
            ordinal=i,
        )
        for i in range(10_000)
    ]
    facts = [
        SourceFact(
            id=i,
            statement=f"Fact {i}.",
            passages=(passages[i % 10_000],),
            embedding=tuple(vectors[i].tolist()),
        )
        for i in range(50_000)
    ]

    tracemalloc.start()
    started = time.perf_counter()
    try:
        Deal(facts, wanted=100, size=2, rounds=1, floor=0.0, share=0.05)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak < 300 * 1024 * 1024, peak
    assert time.perf_counter() - started < 120


def _at(i: int, passage: int, *vector: float) -> SimpleNamespace:
    """One fact of one passage, with the vector given."""
    return SimpleNamespace(id=i, passage_id=passage, embedding=vector)


#: Three facts of three passages, each pair at cosine -0.5: 120 degrees apart.
_OPPOSED = [
    _at(0, 0, 1.0, 0.0),
    _at(1, 1, -0.5, 3**0.5 / 2),
    _at(2, 2, -0.5, -(3**0.5) / 2),
]


def test_a_share_of_zero_sets_no_floor() -> None:
    """QUESTIONS_MEETS_SHARE 0 is the switch that turns the relative floor off."""
    facts = _stub(30)

    assert _relative_floor(facts, 0.0) == 0.0  # type: ignore[arg-type]


def test_a_topic_of_one_passage_has_no_floor_under_the_budget() -> None:
    """No pair of facts from two passages, so nothing to read a floor off."""
    facts = [_at(i, 1, 1.0, 0.0) for i in range(5)]

    assert _relative_floor(facts, 0.05) == 0.0  # type: ignore[arg-type]


@pytest.mark.parametrize("budget", [100, 0], ids=["exact", "sampled"])
def test_a_floor_is_never_below_zero(monkeypatch, budget: int) -> None:
    """Opposed vectors mean what unrelated ones do to a sampler: a cosine of 0."""
    monkeypatch.setattr(selection, "_PAIR_BUDGET", budget)

    assert _relative_floor(_OPPOSED, 0.5) == 0.0  # type: ignore[arg-type]


def test_a_topic_with_a_fact_carrying_no_vector_has_no_floor() -> None:
    """A floor of cosines does not belong to a topic `meets` reads by words."""
    facts = [*_stub(20), _at(99, 99)]

    assert _relative_floor(facts, 0.05) == 0.0  # type: ignore[arg-type]


def test_two_facts_of_two_passages_set_the_floor_at_their_cosine() -> None:
    """The smallest topic with a pair keeps it: its one pair clears its own floor."""
    facts = [_at(0, 0, 1.0, 0.0), _at(1, 1, 0.6, 0.8)]

    assert _relative_floor(facts, 0.05) == pytest.approx(0.6)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("budget", "sampled"), [(15, False), (14, True)], ids=["at", "past"]
)
def test_the_floor_is_sampled_only_past_the_pair_budget(
    monkeypatch, budget: int, sampled: bool
) -> None:
    """Six facts hold fifteen pairs: exact at a budget of 15, sampled at 14.

    The budget is what keeps a large topic's floor inside memory, and a topic
    within it is read exactly.
    """
    calls = []
    monkeypatch.setattr(selection, "_PAIR_BUDGET", budget)
    monkeypatch.setattr(
        selection, "_sampled_floor", lambda *args: calls.append(args) or 0.0
    )
    facts = _stub(6, per_passage=1)

    floor = _relative_floor(facts, 0.05)  # type: ignore[arg-type]

    assert bool(calls) is sampled
    if not sampled:
        assert floor == _exact(facts, 0.05)


def test_a_sampled_floor_reads_every_pair_it_drew(monkeypatch) -> None:
    """Chunked or not, each drawn pair's cosine is read, none left unset.

    Two facts at cosine 0.6, so every pair drawn is that pair, and the lowest
    percentile of a sample read whole is 0.6 too.
    """
    monkeypatch.setattr(selection, "_PAIR_BUDGET", 0)
    monkeypatch.setattr(selection, "_SAMPLED_PAIRS", 5)
    monkeypatch.setattr(selection, "_CHUNK", 2)
    # A cosine left unread shows as NaN rather than as whatever memory held.
    unset = np.empty
    monkeypatch.setattr(
        selection.np,
        "empty",
        lambda size, dtype=float, **kw: (
            np.full(size, np.nan, dtype=dtype)
            if np.issubdtype(np.dtype(dtype), np.floating)
            else unset(size, dtype=dtype, **kw)
        ),
    )
    facts = [_at(0, 0, 1.0, 0.0), _at(1, 1, 0.6, 0.8)]

    assert _relative_floor(facts, 0.99) == pytest.approx(0.6)  # type: ignore[arg-type]
