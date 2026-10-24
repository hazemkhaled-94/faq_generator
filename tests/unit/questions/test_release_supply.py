"""The release draw at the default ceiling of 0 unanswerable rows."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from test_question_service import SETTINGS

import question_generation.balance as balance_module
from database.qa_generator import Difficulty, QuestionType
from question_generation.balance import Row, largest
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


@pytest.mark.parametrize("first, second", [("en", "de"), ("de", "en")])
def test_a_language_mostly_unanswerable_is_weighed_by_its_drawable_rows(first, second):
    """qg-check-2: the default language weights follow answerable rows, as bands do."""
    pool = _rows(
        [
            (100, True, QuestionType.FACTOID, first),
            (100, True, QuestionType.FACTOID, second),
            (5, True, QuestionType.FACTOID, "fr"),
            (25, False, QuestionType.FACTOID, "fr"),
        ]
    )
    drawn = _drawn(
        pool,
        release_difficulty={Difficulty.EASY: 1},
        release_types={QuestionType.FACTOID: 1},
        release_languages={},
    )
    assert len(drawn) >= 150, f"release shrank to {len(drawn)} of 205 answerable rows"


def _tight_fillable(pool, bands, types, unanswerable, languages, tolerance, twins=None):
    """The fix hint's bound: unanswerable rows count only up to the ceiling."""
    from collections import Counter

    from question_generation.balance import _drawable, _supply, quota_of

    held = Counter(
        n
        for r in pool
        if r.answerable
        for n in (r.difficulty, r.question_type, r.language)
    )
    spare = Counter(
        n
        for r in pool
        if not r.answerable
        for n in (r.difficulty, r.question_type, r.language)
    )
    unanswered = sum(not r.answerable for r in pool)
    for size in range(len(pool), 0, -1):
        supply = _supply(_drawable(pool, languages, twins), unanswerable, size)
        quota = quota_of(size, bands, types, unanswerable, languages, supply)
        wanted = {**quota.difficulty, **quota.types, **quota.languages}
        missing = {
            n: c - held[n] - min(spare[n], quota.unanswerable)
            for n, c in wanted.items()
        }
        missing["answerable"] = (
            size - min(quota.unanswerable, unanswered) - (len(pool) - unanswered)
        )
        wanted["answerable"] = size - quota.unanswerable
        if all(s <= max(1, tolerance * wanted[n]) for n, s in missing.items()):
            return size
    return 0


def _count_draws(monkeypatch):
    calls = [0]
    real = balance_module.choose

    def counted(*a, **k):
        calls[0] += 1
        return real(*a, **k)

    monkeypatch.setattr(balance_module, "choose", counted)
    return calls


SCAN = {
    "bands": {Difficulty.EASY: 1},
    "types": {QuestionType.FACTOID: 1, QuestionType.REASON: 1},
    "languages": {"de": 1, "en": 1},
}


def _scan_pool():
    return _rows(
        [
            (300, True, QuestionType.FACTOID, "de"),
            (300, True, QuestionType.FACTOID, "en"),
            (20, True, QuestionType.REASON, "de"),
            (20, True, QuestionType.REASON, "en"),
            (250, False, QuestionType.REASON, "de"),
            (250, False, QuestionType.REASON, "en"),
        ]
    )


def test_the_scan_does_not_start_above_what_the_ceiling_lets_a_draw_take(monkeypatch):
    """lead-1: unanswerable rows the ceiling never draws made 1,100+ draws of 1."""
    calls = _count_draws(monkeypatch)
    largest(_scan_pool(), unanswerable=0.0, **SCAN)
    assert calls[0] <= 50, f"{calls[0]} draws for a release of a few dozen rows"


def test_the_tight_bound_keeps_the_ids(monkeypatch):
    """lead-1 equivalence: the hinted bound hands back the same release (passes on BASE too)."""
    pool = _scan_pool()
    base = largest(pool, unanswerable=0.0, **SCAN)
    monkeypatch.setattr(
        balance_module,
        "_placeable",
        lambda pool, bands, types, unanswerable, languages, tolerance, counts: (
            _tight_fillable(pool, bands, types, unanswerable, languages, tolerance)
        ),
    )
    tight = largest(pool, unanswerable=0.0, **SCAN)
    assert tight.ids == base.ids and tight.short == base.short
