"""Ending a worker's loop.

A worker killed mid-item leaves its row claimed until the lease expires.
"""

from __future__ import annotations

import os
import signal
from typing import Any

import pytest

from stages.service import StageService
from stages.worker import Shutdown, watch


@pytest.fixture(autouse=True)
def _handlers():
    """Puts back the SIGTERM and SIGINT handlers a Shutdown installs."""
    held = {one: signal.getsignal(one) for one in (signal.SIGTERM, signal.SIGINT)}
    yield
    for one, handler in held.items():
        signal.signal(one, handler)


def test_a_signal_is_recorded_rather_than_raised() -> None:
    """The flag goes up; the process stays."""
    left: list[int] = []
    flag = Shutdown(leave=left.append)
    assert not flag.requested()

    flag._request(signal.SIGTERM, None)
    # The grace clock the request started would end the test run when it ran
    # out: it is stopped as a worker that finished in time stops it.
    flag.done()
    assert flag.requested()
    assert left == []


def test_sigterm_ends_the_loop_after_the_current_drain() -> None:
    """The drain in progress finishes and no further drain begins."""
    drains: list[bool] = []

    def drain(stopping) -> int:
        """Records what the loop was told, and asks to stop on the second."""
        drains.append(stopping())
        if len(drains) == 2:
            os.kill(os.getpid(), signal.SIGTERM)
        return 1  # work found, so the loop does not sleep

    watch(drain, 0.01)
    assert drains == [False, False], drains


def test_a_failed_drain_waits_the_interval_and_tries_again(monkeypatch) -> None:
    """A drain that raises is logged and retried, never the end of the worker.

    And an empty queue waits the same interval before it is asked again.
    """
    waits: list[float] = []
    monkeypatch.setattr(Shutdown, "wait", lambda self, seconds: waits.append(seconds))
    calls: list[int] = []

    def drain(stopping) -> int:
        """Raises, then finds nothing, then asks to stop."""
        calls.append(len(calls))
        if len(calls) == 1:
            raise RuntimeError("the database went away")
        if len(calls) == 3:
            os.kill(os.getpid(), signal.SIGTERM)
        return 0

    watch(drain, 7.0)

    assert len(calls) == 3
    assert waits == [7.0, 7.0, 7.0]


class _Repository:
    """A queue that counts how often it was asked for work."""

    done = "extracted"

    def __init__(self) -> None:
        """Initialises the counter."""
        self.claims = 0

    def abandon(self) -> int:
        """Reports that nothing was left claimed."""
        return 0

    def touch(self) -> bool:
        """Holds nothing to refresh."""
        return False


class _Service(StageService):
    """A stage whose work is to count that it was asked."""

    name = "check"
    unit = "row"

    def process_next(self) -> Any | None:
        """Claims one row and does nothing with it."""
        self._repository.claims += 1
        return None


def test_a_stopping_worker_claims_nothing() -> None:
    """A drain that starts already stopping asks the queue for no row."""
    service = _Service(_Repository())

    assert service.drain(stopping=lambda: True) == 0
    assert service._repository.claims == 0, "a stopping worker claimed another row"


def test_a_draining_worker_claims_once_before_an_empty_queue_ends_it() -> None:
    """An ordinary drain asks for a row, and stops when there is none."""
    running = _Service(_Repository())

    assert running.drain() == 0
    assert running._repository.claims == 1, "a draining worker never claimed"


# ── A worker told to stop before its row is done ───────────────────────────


class _Leaving:
    """A shutdown whose exit and give-back are recorded rather than done."""

    def __init__(self, grace: float = 60.0) -> None:
        """Initialises it, with a held row to give back."""
        self.events: list[object] = []
        self.shutdown = Shutdown(
            grace,
            give_back=lambda: self.events.append("given back"),
            leave=lambda code: self.events.append(("left", code)),
        )

    def wait(self) -> None:
        """Waits for the thread that gives the row back to finish."""
        import time

        for _ in range(200):
            if ("left", 75) in self.events:
                return
            time.sleep(0.01)


def test_one_signal_lets_the_row_finish_and_gives_nothing_back() -> None:
    """The first signal stops the claiming and leaves the row alone."""
    leaving = _Leaving()

    leaving.shutdown._request(signal.SIGTERM, None)

    assert leaving.shutdown.requested()
    assert leaving.events == []
    leaving.shutdown.done()


def test_a_second_signal_gives_the_held_row_back_and_leaves() -> None:
    """Nobody is waiting any longer: the row goes back to pending."""
    leaving = _Leaving()

    leaving.shutdown._request(signal.SIGTERM, None)
    leaving.shutdown._request(signal.SIGTERM, None)
    leaving.wait()

    assert leaving.events == ["given back", ("left", 75)]
    leaving.shutdown.done()


def test_the_grace_running_out_gives_the_row_back_and_leaves() -> None:
    """The supervisor stops waiting at its deadline; the worker is before it."""
    leaving = _Leaving(grace=0.05)

    leaving.shutdown._request(signal.SIGTERM, None)
    leaving.wait()

    assert leaving.events == ["given back", ("left", 75)]


def test_a_worker_that_finishes_in_time_never_gives_anything_back() -> None:
    """The clock stops with the loop."""
    leaving = _Leaving(grace=0.05)

    leaving.shutdown._request(signal.SIGTERM, None)
    leaving.shutdown.done()
    import time

    time.sleep(0.2)

    assert leaving.events == []


def test_a_row_that_cannot_be_given_back_is_left_to_its_lease() -> None:
    """The worker still leaves, and says so."""
    events: list[object] = []

    def refuse() -> None:
        """Fails as a release does when another worker has the row."""
        raise RuntimeError("claimed by another worker")

    shutdown = Shutdown(60.0, refuse, lambda code: events.append(code))
    shutdown._request(signal.SIGTERM, None)
    shutdown._request(signal.SIGTERM, None)
    import time

    for _ in range(200):
        if events:
            break
        time.sleep(0.01)

    assert events == [75]
    shutdown.done()


def test_the_service_gives_back_the_row_its_queue_holds() -> None:
    """Through the queue's own release, the one a stalled drain uses."""

    class Holding(_Repository):
        """A queue holding one row."""

        def release_held(self) -> bool:
            """Gives the row back."""
            self.released = True
            return True

    queue = Holding()
    service = _Service(queue)

    assert service.give_back() is True
    assert queue.released is True


def test_a_worker_stage_gets_a_grace_its_container_outlasts() -> None:
    """compose.yaml's stop_grace_period is above the grace plus the release margin."""
    import re
    from pathlib import Path

    import yaml

    from stages.worker import DEFAULT_GRACE_SECONDS, GRACE_SECONDS, RELEASE_MARGIN

    stages = {
        "parse-worker": "parsing",
        "chunk-worker": "chunking",
        "extract-worker": "extraction",
        "topic-worker": "topic_modelling",
        "question-worker": "questions",
        "assess-worker": "assessment",
    }
    compose = yaml.safe_load(
        (Path(__file__).resolve().parents[3] / "compose.yaml").read_text()
    )
    workers = {
        name
        for name, service in compose["services"].items()
        if "--watch" in service.get("command", [])
    }
    assert workers == set(stages), "a worker with no stage to size it from"
    for name, stage in stages.items():
        given = compose["services"][name]["stop_grace_period"]
        seconds = sum(
            int(number) * {"s": 1, "m": 60, "h": 3600}[unit]
            for number, unit in re.findall(r"(\d+)([smh])", given)
        )
        need = GRACE_SECONDS.get(stage, DEFAULT_GRACE_SECONDS) + RELEASE_MARGIN
        assert seconds >= need, f"{name}: {given} is under {need:.0f}s"


def test_the_hosted_stop_outlasts_every_stage_grace() -> None:
    """The stop kills only what a drain's grace and give-back left."""
    import re
    from pathlib import Path

    from stages.worker import DEFAULT_GRACE_SECONDS, GRACE_SECONDS, RELEASE_MARGIN

    makefile = (Path(__file__).resolve().parents[3] / "Makefile").read_text()
    (given,) = re.findall(r"^HOSTED_GRACE = (\d+)$", makefile, re.MULTILINE)

    assert (
        int(given)
        >= max(DEFAULT_GRACE_SECONDS, *GRACE_SECONDS.values()) + RELEASE_MARGIN
    )
