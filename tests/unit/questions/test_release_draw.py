"""The release draw: a scarce kind does not cap it, a thread stops at a full bucket, and the last draw is judged.

Rows stand for a bank's or a shop's accepted questions (overdraft fees, returns,
delivery times), German and English.
"""

from __future__ import annotations

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
    """Three kinds weighed alike over 30 places, one with 2 rows: the other two take 14 each."""
    quota = quota_of(
        30,
        {"easy": 1},
        {"fees": 1, "returns": 1, "delivery": 1},
        0.0,
        supply={"fees": 2, "returns": 50, "delivery": 50},
    )
    assert quota.types == {"fees": 2, "returns": 14, "delivery": 14}


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
