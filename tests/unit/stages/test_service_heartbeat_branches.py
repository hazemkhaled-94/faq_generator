"""A failing heartbeat is logged, and the work it beats for goes on.

The beat runs on a thread of its own. A database blip while it refreshes the
claim costs nothing until the lease runs out, so it must neither stop the
drain nor vanish from the log. And a worker cut short gives its held row
back through the stage, or reports it held nothing.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from stages import service as module
from stages.cli import give_back
from stages.service import StageService


class Rows:
    """Rows in memory whose claim refresh always fails."""

    def __init__(self, count: int) -> None:
        self.pending = list(range(1, count + 1))
        self.finished: list[int] = []
        self.beats = 0
        self.held: int | None = None

    def claim(self) -> int | None:
        """Takes the next row and holds it."""
        self.held = self.pending.pop(0) if self.pending else None
        return self.held

    def abandon(self) -> int:
        """Nothing was left claimed."""
        return 0

    def touch(self) -> bool:
        """Counts the beat and fails it."""
        self.beats += 1
        raise ConnectionError("server closed the connection unexpectedly")

    def release_held(self) -> bool:
        """Puts the held row back at the front."""
        held, self.held = self.held, None
        if held is None:
            return False
        self.pending.insert(0, held)
        return True


class Stage(StageService):
    """A stage whose rows take a little while each."""

    name = "stub"
    unit = "row"

    def __init__(self, rows: Rows) -> None:
        super().__init__(rows)  # type: ignore[arg-type]
        self.rows = rows

    def process_next(self) -> Any | None:
        """Works one row."""
        key = self.rows.claim()
        if key is None:
            return None
        time.sleep(0.05)
        self.rows.finished.append(key)
        return key


def test_a_failing_heartbeat_is_logged_and_the_drain_finishes(
    monkeypatch, caplog
) -> None:
    """Every row is worked; the failed beat is in the log."""
    monkeypatch.setattr(module, "HEARTBEAT_SECONDS", 0.01)
    rows = Rows(4)

    with caplog.at_level(logging.WARNING):
        assert Stage(rows).drain() == 4

    assert rows.finished == [1, 2, 3, 4]
    assert rows.beats > 0
    assert "stub: heartbeat failed" in caplog.text


def test_a_worker_cut_short_gives_its_held_row_back() -> None:
    """The row goes back to the front of the queue, unworked."""
    rows = Rows(2)
    stage = Stage(rows)
    rows.claim()

    assert give_back({"service": stage})() is True
    assert rows.pending == [1, 2]


def test_a_worker_with_no_service_yet_has_nothing_to_give_back() -> None:
    """Cut short before the stage was built, which is not an error."""
    assert give_back({})() is False
