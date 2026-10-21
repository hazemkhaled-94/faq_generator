"""The release draw: a scarce kind does not cap it, a thread stops at a full bucket, and the last draw is judged.

Rows stand for a bank's or a shop's accepted questions (overdraft fees, returns,
delivery times), German and English.
"""

from __future__ import annotations

import math
from collections import Counter

import pytest

from question_generation.balance import Row, choose, largest, quota_of
from question_generation.models import Posed
from question_generation.service import _judged

KINDS = (
    "factoid",
    "definition",
    "enumeration",
    "condition",
    "reason",
    "procedure",
    "consequence",
    "application",
    "comparison",
    "aggregation",
)


def _roots(spec, language, start=1):
    rows, at = [], start
    for kind, count in spec:
        for _ in range(count):
            rows.append(
                Row(
                    id=at,
                    answerable=True,
                    difficulty="easy",
                    question_type=kind,
                    language=language,
                )
            )
            at += 1
    return rows


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_kind_the_pool_holds_one_of_does_not_cap_the_whole_release(language):
    """R122 / BL-B14: 40 accepted rows of each of ten kinds and one `implication`.

    A shop pool of 401 rows; every kind weighed alike. The one implication row
    can fill its own share at most, and the rest of the release should not be
    cut to the size that one row's share allows.
    """
    pool = _roots([(kind, 40) for kind in KINDS] + [("implication", 1)], language)
    types = dict.fromkeys([*KINDS, "implication"], 1)
    release = largest(pool, {"easy": 1}, types, 0.0, languages={language: 1})
    assert release.size >= 200, (
        f"{release.size} of {len(pool)} released; short {release.short}"
    )


def test_the_places_an_exhausted_kind_cannot_take_go_to_the_others():
    """Three kinds weighed alike over 30 places, one with 2 rows.

    The other two take their ten and the slack close_enough allows, 11 each.
    """
    quota = quota_of(
        30,
        {"easy": 1},
        {"fees": 1, "returns": 1, "delivery": 1},
        0.0,
        supply={"fees": 2, "returns": 50, "delivery": 50},
    )
    assert quota.types == {"fees": 2, "returns": 11, "delivery": 11}


def _within_tolerance(release, pool, weights):
    """No kind holds more of the release than its share and the tolerance allow."""
    drawn = Counter(row.question_type for row in pool if row.id in set(release.ids))
    total = sum(weights.values())
    for kind, count in drawn.items():
        share = math.ceil(release.quota.size * weights[kind] / total)
        assert count <= share + int(max(1, 0.1 * share)), (
            f"{kind} {count} of {release.size}; quota {release.quota.types}"
        )


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_kind_that_floods_the_pool_is_held_within_the_tolerance(language):
    """Five kinds with 30 rows each and a `condition` with 30 roots and 150 follow-ups.

    The scarce kinds are capped at what they hold, their places go to
    condition, but only up to its share and the tolerance: not the pool's own
    split. The release is larger than the base's and condition stays near 1/6.
    """
    kinds = ("factoid", "definition", "procedure", "reason", "application")
    roots = _roots([(kind, 30) for kind in kinds] + [("condition", 30)], language)
    follows = [
        Row(
            1000 + root.id,
            True,
            "easy",
            "condition",
            follows_id=root.id,
            language=language,
        )
        for root in roots
        if root.question_type != "condition"
    ]
    pool = roots + follows
    weights = dict.fromkeys([*kinds, "condition"], 1)
    release = largest(pool, {"easy": 1}, weights, 0.0, languages={language: 1})
    _within_tolerance(release, pool, weights)
    assert 180 < release.size < len(pool)


def test_a_pool_with_two_scarce_kinds_and_one_flood_does_not_release_the_flood():
    """a: 2, b: 2, c: 500 rows, weighed alike: balance allows only a handful."""
    pool = _roots([("a", 2), ("b", 2), ("c", 500)], "de")
    weights = {"a": 1, "b": 1, "c": 1}
    release = largest(pool, {"easy": 1}, weights, 0.0, languages={"de": 1})
    _within_tolerance(release, pool, weights)
    assert release.size < 20


def test_the_release_grows_where_balance_allows_it():
    """40 rows of each of ten kinds and one implication: grows past the base's size."""
    pool = _roots([(kind, 40) for kind in KINDS] + [("implication", 1)], "en")
    weights = dict.fromkeys([*KINDS, "implication"], 1)
    release = largest(pool, {"easy": 1}, weights, 0.0, languages={"en": 1})
    _within_tolerance(release, pool, weights)
    assert release.size > 100


@pytest.mark.parametrize("language", ["de", "en"])
def test_twinned_rows_of_a_scarce_kind_count_as_one_supply(language):
    """Three rewordings of one question are one place: the kind is capped at one."""
    pool = _roots([(kind, 40) for kind in KINDS] + [("implication", 3)], language)
    ids = [row.id for row in pool if row.question_type == "implication"]
    twins = {one: set(ids) - {one} for one in ids}
    weights = dict.fromkeys([*KINDS, "implication"], 1)
    release = largest(
        pool, {"easy": 1}, weights, 0.0, languages={language: 1}, twins=twins
    )
    _within_tolerance(release, pool, weights)
    assert release.size >= 200, f"{release.size}; short {release.short}"


def test_rows_in_a_language_the_release_gives_no_weight_are_no_supply():
    """The scarce kind has 3 de rows and 3 en: only the de ones can be drawn."""
    pool = _roots([(kind, 40) for kind in KINDS] + [("implication", 3)], "de")
    pool += [Row(900 + n, True, "easy", "implication", language="en") for n in range(3)]
    weights = dict.fromkeys([*KINDS, "implication"], 1)
    release = largest(pool, {"easy": 1}, weights, 0.0, languages={"de": 1})
    _within_tolerance(release, pool, weights)
    assert release.size >= 200, f"{release.size}; short {release.short}"


@pytest.mark.parametrize("language", ["de", "en"])
def test_follow_ups_do_not_draw_a_kind_past_its_quota(language):
    """R3 P1/P4: three roots in ten bring a `condition` follow-up ("And if the account is joint?").

    A release of 60 over six kinds weighed alike gives condition ten places.
    Threads are drawn whole and each turn was counted after the fact, so
    condition ended far past its ten and the other kinds ended short; a thread
    now ends at the first turn whose kind is full.
    """
    kinds = ("factoid", "definition", "procedure", "reason", "application")
    roots = _roots([(kind, 100) for kind in kinds] + [("condition", 100)], language)
    follows = [
        Row(
            id=1000 + root.id,
            answerable=True,
            difficulty="easy",
            question_type="condition",
            follows_id=root.id,
            language=language,
        )
        for root in roots
        if root.question_type != "condition" and (root.id - 1) % 100 < 30
    ]
    pool = roots + follows
    types = dict.fromkeys([*kinds, "condition"], 1)
    quota = quota_of(60, {"easy": 1}, types, 0.0, {language: 1})
    release = choose(pool, quota)
    drawn = Counter(row.question_type for row in pool if row.id in set(release.ids))
    assert drawn["condition"] <= quota.types["condition"], (
        f"condition {drawn['condition']} against a quota of {quota.types['condition']}; "
        f"short {release.short}"
    )
    assert release.size == 60 and not release.short


class _Everything:
    """A twin judge that reads every pair it is shown as wanting one answer."""

    def __init__(self):
        self.asked: set[tuple[int, int]] = set()

    def same_answer(self, first, second):
        self.asked.add(
            tuple(sorted((int(first[0].split("#")[1]), int(second[0].split("#")[1]))))
        )
        return True


class _Adjacent:
    """Pairs each released question with the next one by id, as nearest."""

    def __init__(self, text):
        self.text = text

    def closest_among(self, ids):
        held = sorted(ids)
        return [
            (
                Posed(a, f"{self.text} #{a}", "5 EUR"),
                Posed(b, f"{self.text} #{b}", "5 EUR"),
            )
            for a, b in zip(held[::2], held[1::2], strict=False)
        ]


@pytest.mark.parametrize(
    "language, text",
    [
        ("de", "Wie hoch ist die Gebühr für eine Ersatzkarte?"),
        ("en", "How much does a replacement card cost?"),
    ],
)
def test_the_release_handed_back_holds_no_pair_the_judge_was_never_asked(
    language, text
):
    """R3 P3: after the last twin round the release is drawn again and not judged.

    Twelve rewordings of one bank question; the judge reads every pair it sees as
    one answer, so each round finds twins and the redraw after round 3 holds a
    pair nobody asked about.
    """
    pool = _roots([("factoid", 12)], language)
    twins: dict[int, set[int]] = {}

    def draw():
        return choose(
            pool, quota_of(4, {"easy": 1}, {"factoid": 1}, 0.0, {language: 1}), twins
        )

    judge = _Everything()
    catalog = _Adjacent(text)
    release = _judged(catalog, judge, twins, draw(), draw)
    unasked = [
        (a.id, b.id)
        for a, b in catalog.closest_among(release.ids)
        if (a.id, b.id) not in judge.asked
    ]
    assert not unasked, f"released {release.ids}; never judged: {unasked}"
