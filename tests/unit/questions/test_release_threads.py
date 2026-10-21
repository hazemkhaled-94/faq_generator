"""How a thread joins the release beside its twins, where the draw's mutants survived.

`choose` draws a root and the turns under it; a turn twinning a question
already in, or an earlier turn of its own thread, ends the thread there, and
the twins of every turn taken leave the waiting roots.
"""

from __future__ import annotations

import pytest

from question_generation.balance import Row, choose, quota_of

_BANDS = {"easy": 1}
_TYPES = {"factoid": 1}


def _row(id: int, follows: int | None = None) -> Row:
    return Row(
        id=id,
        answerable=True,
        difficulty="easy",
        question_type="factoid",
        follows_id=follows,
    )


def _drawn(pool: list[Row], twins: dict[int, set[int]]) -> set[int]:
    return set(choose(pool, quota_of(len(pool), _BANDS, _TYPES, 0.0), twins).ids)


@pytest.mark.parametrize(("root", "other"), [(1, 2), (2, 1), (5, 9), (9, 5)])
def test_a_turn_and_a_root_it_twins_are_never_both_released(root, other) -> None:
    """Whichever is drawn first, the other is out."""
    turn = 20
    pool = [_row(root), _row(turn, root), _row(other)]
    twins = {turn: {other}, other: {turn}}

    drawn = _drawn(pool, twins)

    assert not {turn, other} <= drawn, drawn


def test_a_turn_twinning_an_earlier_turn_of_its_thread_ends_it() -> None:
    """Its own earlier turns count, not only its root."""
    pool = [_row(1), _row(2, 1), _row(3, 2)]
    twins = {2: {3}, 3: {2}}

    assert _drawn(pool, twins) == {1, 2}
