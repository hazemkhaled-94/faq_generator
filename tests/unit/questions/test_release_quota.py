"""The capped quota a release size asks of each kind, where its mutants survived.

`quota_of` with a supply caps a kind the pool cannot fill within its slack at
what the pool holds and hands its places to the others, none past its share
plus the slack nor past its own supply. These pin the slack boundary, the
supply ceiling on a kind taking freed places, and the places handed out when
no open kind fills its room.
"""

from __future__ import annotations

from question_generation.balance import quota_of

_BANDS = {"easy": 1}


def _types(size: int, supply: dict[str, int]) -> dict[str, int]:
    return quota_of(size, _BANDS, dict.fromkeys(supply, 1), 0.0, None, supply).types


def test_a_kind_short_of_its_share_by_exactly_the_slack_is_not_capped() -> None:
    """Ten asked, nine held: one short is what `close_enough` allows."""
    assert _types(20, {"a": 9, "b": 50}) == {"a": 10, "b": 10}


def test_a_kind_short_by_the_one_place_always_allowed_is_not_capped() -> None:
    """Five asked, four held: the slack is never below one place."""
    assert _types(10, {"a": 4, "b": 50}) == {"a": 5, "b": 5}


def test_a_kind_is_never_asked_for_more_than_the_pool_holds_of_it() -> None:
    """The freed places stop at the other kind's own supply."""
    assert _types(20, {"a": 0, "b": 10}) == {"a": 0, "b": 10}


def test_freed_places_go_to_kinds_with_room_for_them() -> None:
    """Four places freed and three of room each: both open kinds take some."""
    got = _types(100, {"a": 29, "b": 100, "c": 100})

    assert got == {"a": 29, "b": 36, "c": 35}
    assert sum(got.values()) == 100
