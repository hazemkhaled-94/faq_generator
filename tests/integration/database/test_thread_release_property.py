"""Whatever the status changes, a released question never has an ancestor outside the release."""

from __future__ import annotations

import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from seed import question
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_STATUSES = ["accepted", "rejected", "draft"]


@st.composite
def _threads(draw):
    """A forest of 1-6 questions, their statuses, and a sequence of changes.

    A parent always comes before its child.
    """
    size = draw(st.integers(1, 6))
    parents = [
        draw(
            st.one_of(
                st.none(), st.just(at - 1), st.just(at - 1), st.integers(0, at - 1)
            )
        )
        if at
        else None
        for at in range(size)
    ]
    statuses = [
        draw(st.sampled_from(_STATUSES + ["accepted"] * 3)) for _ in range(size)
    ]
    changes = draw(
        st.lists(
            st.tuples(st.integers(0, min(1, size - 1)), st.sampled_from(_STATUSES)),
            max_size=6,
        )
    )
    wants = draw(
        st.lists(st.sampled_from([True, True, False]), min_size=size, max_size=size)
    )
    return size, parents, statuses, changes, wants


def _held(engine):
    with engine.connect() as c:
        rows = c.execute(
            text("SELECT id, status, release_id, follows_id FROM questions")
        ).all()
    return {r[0]: r[1:] for r in rows}


def _broken(engine) -> list[int]:
    state = _held(engine)
    bad = []
    for at, (_, release, parent) in state.items():
        if release is None:
            continue
        while parent is not None:
            status, parent_release, up = state[parent]
            if status != "accepted" or parent_release is None:
                bad.append(at)
                break
            parent = up
    return bad


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(_threads())
def test_after_any_status_change_no_released_question_has_an_ancestor_outside_the_release(
    engine, database, case
) -> None:
    """Rejecting, drafting or re-accepting any turn leaves every thread whole."""
    size, parents, statuses, changes, wants = case
    drawn = uuid.uuid4()
    ids: list[int] = []
    released: list[bool] = []
    try:
        with Session(engine) as session:
            for at in range(size):
                up = parents[at]
                free = statuses[at] == "accepted" and (up is None or released[up])
                released.append(free and wants[at])
                one = question(
                    status=statuses[at],
                    release_id=drawn if released[at] else None,
                    follows_id=None if up is None else ids[up],
                    thread_position=1 if up is None else 2,
                    kind="needs_both",
                )
                session.add(one)
                session.flush()
                ids.append(one.id)
            session.commit()
        assert _broken(engine) == []
        for at, status in changes:
            with engine.begin() as c:
                c.execute(
                    text(
                        "UPDATE questions SET status = :s, release_id = "
                        "CASE WHEN :s = 'accepted' THEN release_id END WHERE id = :i"
                    ),
                    {"s": status, "i": ids[at]},
                )
            assert _broken(engine) == [], (parents, statuses, changes)
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM questions"))
