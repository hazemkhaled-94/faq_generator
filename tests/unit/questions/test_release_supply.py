"""The release draw at the default ceiling of 0 unanswerable rows."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from test_question_service import SETTINGS

from database.qa_generator import Difficulty, QuestionType
from question_generation.balance import Row
from question_generation.service import balance


def _rows(spec):
    """spec: (count, answerable, kind, language) tuples -> Rows with fresh ids."""
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


def _drawn(pool, **setting):
    class Catalog:
        drawn: tuple[int, ...] = ()

        def judged(self, within=None):
            return []

        def reject(self, verdicts):
            return 0

        def releasable(self, within=None):
            return pool

        def twins(self, floor):
            return []

        def release(self, ids):
            self.drawn = tuple(ids)
            return uuid4(), len(self.drawn)

    catalog = Catalog()
    balance(catalog, replace(SETTINGS, release_unanswerable=0.0, **setting))
    return catalog.drawn


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_kind_held_only_by_unanswerable_rows_is_dropped_like_an_absent_one(language):
    """bank/shop pool of 200 answerable factoids, 5 unanswerable reasons."""
    pool = _rows(
        [
            (200, True, QuestionType.FACTOID, language),
            (5, False, QuestionType.REASON, language),
        ]
    )
    drawn = _drawn(
        pool,
        release_difficulty={Difficulty.EASY: 1},
        release_types={QuestionType.FACTOID: 1, QuestionType.REASON: 1},
    )
    assert len(drawn) >= 150, f"release shrank to {len(drawn)} of 200 answerable rows"
