"""What a drain does with rows that fail, and what it tells whoever ran it.

A model that is down fails every row it is given, and used to be given all of
them: the queue emptied into `failed` and the exit code said 0.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from opentelemetry import trace

from llm.client import ModelRefused, ModelUnavailable
from stages.cli import FAILED, STOPPED, exit_code
from stages.service import STOP_AFTER, StageService, is_outage


class Rows:
    """A queue of numbered rows held in memory."""

    done = "done"

    def __init__(self, count: int) -> None:
        """Queues rows 1 to `count`."""
        self.pending = list(range(1, count + 1))
        self.finished: list[int] = []
        self.failed: dict[int, str] = {}
        self.released: list[int] = []

    def claim(self) -> int | None:
        """Takes the next row."""
        return self.pending.pop(0) if self.pending else None

    def abandon(self) -> int:
        """Nothing was left claimed."""
        return 0

    def touch(self) -> bool:
        """Says the held row is still held."""
        return True

    def fail(self, key: int, error: str) -> None:
        """Records a failed row."""
        self.failed[key] = error

    def release(self, *keys: int) -> None:
        """Gives rows back to the front of the queue, unworked."""
        for key in keys:
            self.failed.pop(key, None)
            self.released.append(key)
        self.pending = sorted([*self.pending, *keys])


class Stage(StageService):
    """A stage whose rows fail as a script says."""

    name = "stub"
    unit = "row"

    def __init__(self, rows: Rows, failures: Mapping[int, Exception]) -> None:
        """Initialises the stage over its rows and the failure each one meets."""
        super().__init__(rows)  # type: ignore[arg-type]
        self.rows = rows
        self._failures = failures

    def process_next(self) -> Any | None:
        """Works one row."""
        key = self.rows.claim()
        if key is None:
            return None
        current = trace.get_current_span()
        failure = self._failures.get(key)
        if failure is None:
            self.rows.finished.append(key)
            self._done(current)
        else:
            self._fail(key, str(failure), current, is_outage(failure))
        return key


def down_from(first: int, last: int = 1000) -> dict[int, Exception]:
    """The failures of a model that is unreachable for rows `first` to `last`."""
    return {key: ModelUnavailable("Timeout") for key in range(first, last + 1)}


def test_a_drain_that_works_every_row_exits_0() -> None:
    """Nothing failed and nothing stopped."""
    stage = Stage(Rows(8), {})

    assert stage.drain() == 8
    assert exit_code(stage) == 0


def test_a_model_that_fails_from_one_row_on_stops_the_drain() -> None:
    """The rows before it are done, and the rest are left for the next run."""
    stage = Stage(Rows(40), down_from(11))

    stage.drain()

    assert stage.rows.finished == list(range(1, 11))
    assert stage.rows.failed == {}, "none is left failed by the outage"
    held = list(range(11, 11 + STOP_AFTER))
    assert stage.rows.released == held
    assert stage.rows.pending == list(range(11, 41)), "all pending again"
    assert exit_code(stage) == STOPPED == 75


def test_one_failed_row_among_good_ones_exits_3() -> None:
    """The drain goes on past it."""
    stage = Stage(Rows(6), {3: ValueError("nonsense")})

    assert stage.drain() == 6
    assert list(stage.rows.failed) == [3]
    assert exit_code(stage) == FAILED == 3


def test_a_provider_that_refuses_rows_is_not_an_outage() -> None:
    """It answered, about each row: they fail, and the drain does not stop."""
    refused = {key: ModelRefused("filtered") for key in range(1, 13)}
    stage = Stage(Rows(12), refused)

    assert stage.drain() == 12
    assert stage.stalled is None
    assert exit_code(stage) == 3


def test_a_good_row_ends_a_run_of_failures() -> None:
    """Only rows in a row count."""
    failures = down_from(1, STOP_AFTER - 1) | down_from(
        STOP_AFTER + 1, 2 * STOP_AFTER - 1
    )
    stage = Stage(Rows(2 * STOP_AFTER), failures)

    stage.drain()

    assert stage.stalled is None
    assert len(stage.rows.failed) == 2 * STOP_AFTER - 2
    assert exit_code(stage) == 3


def test_an_outage_found_behind_the_error_that_wraps_it_counts() -> None:
    """Readers raise their own failure from the model's."""
    wrapped = ValueError("could not read")
    wrapped.__cause__ = ModelUnavailable("down")

    assert is_outage(wrapped)
    assert not is_outage(ValueError("nonsense"))
    assert not is_outage(ModelRefused("filtered"))


def test_a_second_drain_starts_its_count_again() -> None:
    """A watching worker reuses its service."""
    stage = Stage(Rows(20), down_from(1))
    stage.drain()
    assert exit_code(stage) == STOPPED

    stage.rows.pending = []
    stage.drain()

    assert stage.stalled is None
    assert exit_code(stage) == 0


def test_a_drain_stops_before_the_row_past_its_spend_cap(monkeypatch) -> None:
    """Nothing is claimed once the tally reaches the cap, so nothing is held."""
    from llm import tally

    monkeypatch.setenv("SPEND_CAP", "1.0")
    monkeypatch.setitem(tally._spent, "usd", 0.0)

    class Costly(Stage):
        """Every row costs forty cents."""

        def process_next(self) -> Any | None:
            """Works a row and pays for it."""
            tally._spent["usd"] += 0.4
            return super().process_next()

    stage = Costly(Rows(10), {})
    stage.drain()

    assert stage.rows.finished == [1, 2, 3], "the third took it past 1.0"
    assert stage.rows.released == [] and len(stage.rows.pending) == 7
    assert "SPEND_CAP" in (stage.stalled or "")
    assert exit_code(stage) == STOPPED


def test_without_a_cap_the_drain_runs_to_the_end(monkeypatch) -> None:
    """Unset means no cap."""
    from llm import tally

    monkeypatch.delenv("SPEND_CAP", raising=False)
    monkeypatch.setitem(tally._spent, "usd", 10_000.0)

    stage = Stage(Rows(4), {})

    assert stage.drain() == 4
