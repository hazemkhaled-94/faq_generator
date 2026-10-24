"""The release draw at the size of a pool ten times this build's.

The draw scanned sizes down from a bound that let through places no bucket
could take, drew each of them with a list rebuilt for every question taken,
and blamed bands and languages for what the scarce kinds left unfilled.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import replace
from uuid import uuid4

import pytest
from test_question_service import SETTINGS

import question_generation.balance as balance_module
from database.qa_generator import Difficulty, QuestionType
from question_generation.balance import Row, choose, largest, quota_of
from question_generation.service import balance


def _rows(spec, first: int = 1):
    """spec: (count, answerable, kind, language) -> rows with fresh ids."""
    rows, at = [], first
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


def _old_largest(pool, bands, types, unanswerable, languages, tolerance=0.10):
    """The scan as it was: every size from the loose bound down, first fill wins."""
    most = None
    drawable = balance_module._drawable(pool, languages, None)
    top = balance_module._fillable(
        pool, bands, types, unanswerable, languages, tolerance, None
    )
    for size in range(top, 0, -1):
        supply = balance_module._supply(drawable, unanswerable, size)
        release = balance_module.choose(
            pool,
            quota_of(size, bands, types, unanswerable, languages, supply, tolerance),
            None,
        )
        if balance_module.close_enough(release, tolerance):
            return release
        if most is None or release.size > most.size:
            most = release
    assert most is not None
    return most


def _counted(monkeypatch):
    calls = [0]
    real = balance_module.choose

    def counting(*a, **k):
        calls[0] += 1
        return real(*a, **k)

    monkeypatch.setattr(balance_module, "choose", counting)
    return calls


def test_a_cell_of_twenty_thousand_rows_is_drawn_in_seconds() -> None:
    """A question taken out of its cell was a list rebuilt: 5 s for 20,000 of 20,000."""
    pool = _rows([(20_000, True, QuestionType.FACTOID, "en")])
    quota = quota_of(
        20_000,
        {Difficulty.EASY: 1},
        {QuestionType.FACTOID: 1},
        0.0,
        {"en": 1},
    )

    started = time.perf_counter()
    release = choose(pool, quota)

    assert release.size == 20_000
    assert time.perf_counter() - started < 1.5


def _thin_pool(language_a: str, language_b: str, kind_a: str, kind_b: str):
    """Plentiful rows of one kind, a scarce second kind and unanswerable ones."""
    return _rows(
        [
            (700, True, kind_a, language_a),
            (700, True, kind_a, language_b),
            (30, True, kind_b, language_a),
            (30, True, kind_b, language_b),
            (120, False, kind_b, language_a),
            (120, False, kind_b, language_b),
        ]
    )


@pytest.mark.parametrize(
    ("first", "second", "common", "scarce"),
    [
        ("de", "en", QuestionType.FACTOID, QuestionType.REASON),
        ("en", "de", QuestionType.CONDITION, QuestionType.PROCEDURE),
        ("en", "fr", QuestionType.DEFINITION, QuestionType.COMPARISON),
    ],
)
def test_the_scan_starts_at_the_placeable_size_and_draws_the_same_release(
    monkeypatch, first, second, common, scarce
) -> None:
    """Fewer draws than from the loose bound, and the same questions out of them."""
    pool = _thin_pool(first, second, common, scarce)
    bands = {Difficulty.EASY: 1}
    types = {common: 1, scarce: 1}
    languages = {first: 1, second: 1}
    calls = _counted(monkeypatch)
    old = _old_largest(pool, bands, types, 0.10, languages)
    old_calls, calls[0] = calls[0], 0

    new = largest(pool, bands, types, 0.10, languages=languages)

    assert new.ids == old.ids and new.short == old.short
    assert calls[0] < old_calls, (calls[0], old_calls)


def test_the_scan_agrees_with_the_old_scan_on_small_pools() -> None:
    """Pools of every shape: the release is the one the old scan found."""
    kinds = [
        QuestionType.FACTOID,
        QuestionType.REASON,
        QuestionType.CONDITION,
        QuestionType.PROCEDURE,
    ]
    for seed in range(120):
        rng = random.Random(seed)
        pool = _rows(
            [
                (rng.randint(0, 60), rng.random() < 0.8, rng.choice(kinds), language)
                for language in ("de", "en")
                for _ in range(6)
            ]
        )
        if len({row.language for row in pool}) < 2 or not pool:
            continue
        bands = {Difficulty.EASY: 1}
        types = {kind: rng.randint(1, 4) for kind in kinds}
        types = {
            k: v for k, v in types.items() if any(r.question_type == k for r in pool)
        }
        languages = {"de": 1, "en": 1}
        unanswerable = rng.choice([0.0, 0.05, 0.1, 0.25, 0.4])
        old = _old_largest(pool, bands, types, unanswerable, languages)
        new = largest(pool, bands, types, unanswerable, languages=languages)
        assert new.ids == old.ids, (seed, new.size, old.size)


#: One pool of 33 rows with a ceiling of 0.10 that the strict start missed:
#: (id, answerable, band, kind, follows). A quota of eight cannot absorb a
#: proportional tolerance, and `close_enough` forgives the one place the start
#: had not, so size 8 fills here and the scan began below it.
_ONE_PLACE_POOL = [
    (1, False, "medium", "aggregation", None),
    (2, True, "medium", "aggregation", None),
    (3, True, "medium", "aggregation", None),
    (4, True, "medium", "enumeration", None),
    (5, True, "medium", "enumeration", None),
    (6, True, "medium", "aggregation", None),
    (7, True, "medium", "procedure", None),
    (8, True, "easy", "procedure", None),
    (9, True, "easy", "procedure", 8),
    (10, True, "medium", "entity", None),
    (11, True, "medium", "entity", 10),
    (12, True, "medium", "enumeration", None),
    (13, False, "medium", "procedure", None),
    (14, True, "easy", "condition", None),
    (15, True, "hard", "entity", None),
    (16, False, "medium", "procedure", None),
    (17, True, "medium", "aggregation", None),
    (18, True, "medium", "implication", None),
    (19, False, "medium", "aggregation", None),
    (20, False, "medium", "procedure", None),
    (21, False, "medium", "procedure", None),
    (22, False, "medium", "entity", None),
    (23, True, "hard", "application", None),
    (24, True, "medium", "temporal", None),
    (25, False, "medium", "aggregation", None),
    (26, True, "medium", "procedure", None),
    (27, True, "easy", "entity", None),
    (28, True, "medium", "entity", None),
    (29, True, "medium", "entity", 28),
    (30, True, "medium", "procedure", None),
    (31, True, "medium", "enumeration", None),
    (32, False, "medium", "procedure", None),
    (33, True, "medium", "entity", None),
]
_ONE_PLACE_TYPES = {
    "factoid": 4,
    "entity": 1,
    "reason": 1,
    "procedure": 4,
    "consequence": 4,
    "implication": 1,
    "application": 1,
}


@pytest.mark.parametrize("language", ["en", "de", "xx"])
def test_a_pool_where_one_place_is_forgiven_is_drawn_as_the_old_scan_drew_it(
    language: str,
) -> None:
    """The start is an upper bound: it never begins below a size that fills."""
    pool = [
        Row(
            id=at,
            answerable=answerable,
            difficulty=band,
            question_type=kind,
            follows_id=follows,
            language=language,
        )
        for at, answerable, band, kind, follows in _ONE_PLACE_POOL
    ]
    bands = {Difficulty.EASY: 1, Difficulty.MEDIUM: 1, Difficulty.HARD: 1}
    types = {QuestionType(kind): weight for kind, weight in _ONE_PLACE_TYPES.items()}

    old = _old_largest(pool, bands, types, 0.10, {language: 1})
    new = largest(pool, bands, types, 0.10, languages={language: 1})

    assert old.size == 7
    assert new.ids == old.ids, (new.size, old.size)


def _drawn_with_log(pool, caplog, **setting):
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
    with caplog.at_level(logging.INFO):
        balance(catalog, replace(SETTINGS, **setting))
    return catalog.drawn


@pytest.mark.parametrize(
    ("first", "second", "common", "scarce"),
    [
        ("de", "en", QuestionType.FACTOID, QuestionType.REASON),
        ("en", "de", QuestionType.CONDITION, QuestionType.PROCEDURE),
    ],
)
def test_the_report_names_the_scarce_kind_and_not_the_buckets_it_leaves_short(
    caplog, first, second, common, scarce
) -> None:
    """The kind capped at its supply is the cause; bands and languages follow from it."""
    pool = _thin_pool(first, second, common, scarce)

    _drawn_with_log(
        pool,
        caplog,
        release_unanswerable=0.0,
        release_difficulty={Difficulty.EASY: 1},
        release_types={common: 1, scarce: 1},
        release_languages={first: 1, second: 1},
    )

    warned = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING and "too few of" in record.getMessage()
    ]
    assert len(warned) == 1, warned
    assert f"{scarce.value} (" in warned[0], warned[0]
    for name in ("easy", first, second, "answerable", common.value):
        assert f"{name} (" not in warned[0], warned[0]
        assert f"{name} short" not in warned[0], warned[0]


def test_a_twin_pair_judged_once_is_not_asked_again() -> None:
    """The pair a later round meets again is read from what was said."""
    from types import SimpleNamespace

    from question_generation.service import _judged

    asked = []
    verifier = SimpleNamespace(
        same_answer=lambda one, two: asked.append((one, two)) or False
    )

    def question(ident):
        return SimpleNamespace(
            id=ident, question_text=f"Question {ident}?", target_answer="14 days"
        )

    class Catalog:
        def closest_among(self, ids):
            return [(question(1), question(2))]

    pool = _rows([(3, True, QuestionType.FACTOID, "en")])
    release = largest(
        pool, {Difficulty.EASY: 1}, {QuestionType.FACTOID: 1}, 0.0, languages={"en": 1}
    )

    _judged(
        Catalog(),  # type: ignore[arg-type]
        verifier,  # type: ignore[arg-type]
        {},
        release,
        lambda: release,
        pool,
    )

    assert len(asked) == 1
