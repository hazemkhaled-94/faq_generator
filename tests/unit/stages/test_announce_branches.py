"""What a drain says before it starts, and that saying it never stops it.

The estimate is an order of magnitude a person reads before a long run; a
queue that cannot be counted is a warning, not a failed start.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

from database.qa_generator import Status
from stages import cli


class Queue:
    """A queue holding a number of pending rows, or failing to count them."""

    def __init__(self, pending: int | Exception) -> None:
        self.pending = pending

    def counts_by_status(self) -> dict[str, int]:
        """The pending rows, or the failure."""
        if isinstance(self.pending, Exception):
            raise self.pending
        return {Status.PENDING: self.pending}


def stage(estimate=None) -> SimpleNamespace:
    """A stage as the announcement reads it."""
    return SimpleNamespace(name="extraction", unit="passage", estimate=estimate)


def test_a_queue_that_cannot_be_counted_is_a_warning_not_a_failure(
    monkeypatch, caplog
) -> None:
    """Logged with its cause; no queued line is guessed."""
    monkeypatch.delenv("SPEND_CAP", raising=False)
    with caplog.at_level(logging.INFO):
        cli.announce(stage(), Queue(ConnectionError("database restarting")))

    assert "extraction: could not count the queue" in caplog.text
    assert not [one for one in caplog.records if "queued" in one.getMessage()]


def test_the_estimate_is_the_queue_times_the_measured_cost_each(
    monkeypatch, caplog
) -> None:
    """120 passages at USD 0.05 and 3 s each: USD 6 and 6 minutes."""
    monkeypatch.setattr(cli, "spend_cap", lambda: None)
    with caplog.at_level(logging.INFO):
        cli.announce(stage((0.05, 3.0)), Queue(120))

    assert "extraction: 120 passage(s) queued, about USD 6 and 6m" in caplog.text
