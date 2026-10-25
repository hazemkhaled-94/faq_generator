"""A panel polls its queue only while the queue moves.

Every open tab used to redraw every panel every three seconds, whether or
not a worker was on anything. A fragment's timer is fixed where it is
declared, so these read the `run_every` it was declared with.
"""

from __future__ import annotations

import pytest
import streamlit as st
from pages import STATUS, Answers, answers, pipeline

pytestmark = pytest.mark.frontend

VIEW = "facts"

#: A queue at rest, and one with a row on a worker.
RESTING = {**STATUS, "rows": {"new": 2, "failed": 1}}
WORKED = {**STATUS, "rows": {"pending": 1, "in_progress": 1}}


@pytest.fixture
def timers(monkeypatch) -> list[float | None]:
    """The `run_every` of every fragment the page declares, in order."""
    declared: list[float | None] = []
    real = st.fragment

    def recording(*args, run_every=None, **kwargs):
        """Records the timer, and declares the fragment as before."""
        declared.append(run_every)
        return real(*args, run_every=run_every, **kwargs)

    monkeypatch.setattr(st, "fragment", recording)
    return declared


def _open(open_view, status: dict):
    """The Facts page over a queue in this state."""
    client = Answers(**answers(stage_status=lambda *a, **k: status))
    return open_view("facts", client)


def test_a_queue_at_rest_has_no_timer(open_view, timers) -> None:
    """Nothing pending or in progress: nothing to wait for."""
    opened = _open(open_view, RESTING)

    assert opened.raised == []
    assert timers and timers[-1] is None


def test_a_queue_on_a_worker_polls(open_view, timers) -> None:
    """The spinner is for this."""
    opened = _open(open_view, WORKED)

    assert opened.raised == []
    assert timers and timers[-1] is not None and timers[-1] > 0


def test_the_pipeline_panel_stops_when_nothing_runs(open_view, timers) -> None:
    """Documents: the whole-pipeline panel, idle and then working."""
    idle = Answers(
        state=pipeline(working=False), run=(True, "x"), act=lambda a: (True, a)
    )
    open_view("documents", pipeline_api=idle)
    assert None in timers
    timers.clear()

    busy = Answers(
        state=pipeline(working=True), run=(True, "x"), act=lambda a: (True, a)
    )
    open_view("documents", pipeline_api=busy)
    assert timers and all(one is not None for one in timers[-1:])
