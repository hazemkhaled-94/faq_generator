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
