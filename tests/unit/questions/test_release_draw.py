"""The release draw: a scarce kind does not cap it, a thread stops at a full bucket, and the last draw is judged.

Rows stand for a bank's or a shop's accepted questions (overdraft fees, returns,
delivery times), German and English.
"""

from __future__ import annotations

import math
from collections import Counter

import pytest

from question_generation import service
from question_generation.balance import Row, _rank, choose, largest, quota_of
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
def test_the_release_handed_back_holds_no_pair_the_last_round_found(language, text):
    """R3 P3: the round after the last redraw reads that draw and drops what it finds.

    Twelve rewordings of one bank question; the judge reads every pair it sees as
    one answer, so each round finds twins. The pairs the last round found are
    not both in the release handed back, and it does not draw again.
    """
    pool = _roots([("factoid", 12)], language)
    twins: dict[int, set[int]] = {}
    draws = []

    def draw():
        draws.append(1)
        return choose(
            pool, quota_of(4, {"easy": 1}, {"factoid": 1}, 0.0, {language: 1}), twins
        )

    judge = _Everything()
    catalog = _Adjacent(text)
    release = _judged(catalog, judge, twins, draw(), draw, pool=pool)
    held = set(release.ids)
    kept = [pair for pair in judge.asked if set(pair) <= held]
    assert not kept, f"released {release.ids}; judged one answer and kept: {kept}"
    assert release.ids and len(draws) == service._TWIN_ROUNDS + 1


def test_a_twin_dropped_by_the_last_round_takes_its_follow_ups_with_it():
    """The later-ranked member of a pair goes with its thread."""
    pool = _roots([("factoid", 2)], "de")
    pool.append(Row(50, True, "easy", "factoid", follows_id=2, language="de"))
    pool.append(Row(51, True, "easy", "factoid", follows_id=50, language="de"))

    class _Pair:
        """Fresh pairs for the first three rounds, then the pair 1 and 2."""

        rounds = 0

        def closest_among(self, ids):
            self.rounds += 1
            a, b = (
                (1, 2)
                if self.rounds > service._TWIN_ROUNDS
                else (100 + self.rounds, 200 + self.rounds)
            )
            return [(Posed(a, f"q #{a}", "5"), Posed(b, f"q #{b}", "5"))]

    twins: dict[int, set[int]] = {}
    release = choose(pool, quota_of(5, {"easy": 1}, {"factoid": 1}, 0.0, {"de": 1}))
    assert release.ids == [1, 2, 50, 51]
    kept = _judged(_Pair(), _Everything(), twins, release, lambda: release, pool=pool)
    later = max((1, 2), key=lambda one: _rank(next(r for r in pool if r.id == one)))
    assert later not in kept.ids
    assert len(kept.ids) in (1, 3)
    assert (50 in kept.ids) == (later == 1)


def test_a_turn_and_the_question_it_follows_read_as_one_answer_lose_the_turn():
    """Of a root and its own follow-up read as one answer, the follow-up goes.

    Dropping the root would take its turn with it, so both would go where
    one is spare ("Was kostet ein Dispo?" asked again as a follow-up).
    """
    root = next(
        n
        for n in range(1, 100)
        if _rank(Row(n, True, "easy", "factoid"))
        > _rank(Row(n + 100, True, "easy", "factoid"))
    )
    pool = [
        Row(root, True, "easy", "factoid", language="de"),
        Row(root + 100, True, "easy", "factoid", follows_id=root, language="de"),
        Row(500, True, "easy", "factoid", language="de"),
    ]
    release = choose(pool, quota_of(3, {"easy": 1}, {"factoid": 1}, 0.0, {"de": 1}))
    assert len(release.ids) == 3

    class _Pair:
        """Fresh pairs for the first rounds, then the root and its own turn."""

        rounds = 0

        def closest_among(self, ids):
            self.rounds += 1
            a, b = (
                (root, root + 100)
                if self.rounds > service._TWIN_ROUNDS
                else (900 + self.rounds, 950 + self.rounds)
            )
            return [
                (
                    Posed(a, f"Was kostet ein Dispo? #{a}", "1"),
                    Posed(b, f"Was kostet ein Dispo? #{b}", "1"),
                )
            ]

    kept = _judged(_Pair(), _Everything(), {}, release, lambda: release, pool=pool)
    assert sorted(kept.ids) == sorted([root, 500])
