"""The release draw: a scarce kind does not cap it, a thread stops at a full bucket, and the last draw is judged.

Rows stand for a bank's or a shop's accepted questions (overdraft fees, returns,
delivery times), German and English.
"""

from __future__ import annotations

import pytest

from question_generation.balance import Row, largest, quota_of

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
