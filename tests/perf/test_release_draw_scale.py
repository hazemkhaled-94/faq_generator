"""The release draw at ten times the reviewed build's pool.

21,750 accepted questions in the shape of the build's: six kinds, a scarce one
among them, two languages, answerable and not. The draw steps down from the
size the pool can place and draws each size in one pass over the pool, in
strides of a hundredth above 2,000, so its time is the few dozen sizes tried
times the draw of a pool this size: seconds, where stepping by ones took an
hour on a CI runner and every size rebuilding a list per question took hours.

Never on a pull request: `make test-perf`.
"""

from __future__ import annotations

import time

import pytest

from database.qa_generator import Difficulty, QuestionType
from question_generation.balance import Row, largest

pytestmark = pytest.mark.perf

#: Seconds the whole scan may take: C-089's bar, under five minutes. The scan
#: by ones took 57 minutes on a CI runner; the strided one takes 13 s on a
#: laptop.
BUDGET = 300


def test_a_pool_ten_times_the_size_draws_in_bounded_time() -> None:
    """21,750 rows in the build's shape: the whole scan inside its budget."""
    kinds = [
        (QuestionType.FACTOID, 570),
        (QuestionType.CONDITION, 394),
        (QuestionType.REASON, 380),
        (QuestionType.DEFINITION, 176),
        (QuestionType.PROCEDURE, 140),
        (QuestionType.COMPARISON, 18),
    ]
    spec = [
        (count * 10 // 2, answerable, kind, language)
        for kind, count in kinds
        for language in ("de", "en")
        for answerable in (True, False)
    ]
    pool = _rows(spec)
    types: dict[str, int] = {
        kind: (1 if kind == QuestionType.COMPARISON else 4) for kind, _ in kinds
    }

    started = time.perf_counter()
    release = largest(
        pool,
        {Difficulty.EASY: 1},
        types,
        0.10,
        languages={"de": 1, "en": 1},
    )

    assert release.size > 0.9 * release.quota.size
    assert time.perf_counter() - started < BUDGET


def _rows(spec):
    """spec: (count, answerable, kind, language) -> rows with fresh ids."""
    rows, at = [], 1
    for count, answerable, kind, language in spec:
        for _ in range(count):
            rows.append(
                Row(
                    id=at,
                    answerable=answerable,
                    difficulty=Difficulty.EASY,
                    question_type=kind,
                    language=language,
                )
            )
            at += 1
    return rows
