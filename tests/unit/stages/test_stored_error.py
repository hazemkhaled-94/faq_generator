"""What a row stores when its stage meets an error nobody expected.

The row is served by an open GET, so it must not carry a driver's own text:
that names the database's host and role and the object store's endpoint. The
log holds the whole of it, under a trace id the stored sentence names.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from opentelemetry import trace

from stages.service import StageService

DRIVER_TEXTS = [
    (
        "Could not connect to the endpoint URL: "
        '"http://seaweedfs-s3:8333/documents/qa_generator/ab/cd/abcd.pdf"'
    ),
    (
        'connection to server at "postgres" (10.89.0.5), port 5432 failed: FATAL:  '
        'password authentication failed for user "qa_app"'
    ),
    # A shop's and a bank's own words, in languages the stage does not read.
    "Verbindung zu „postgres-bank“ (10.0.0.7) abgelehnt: Rolle „app_konto“",
    "η σύνδεση στο postgres-shop (10.0.0.9) απέτυχε",
]
LEAKS = (
    "seaweedfs-s3",
    "10.89.0.5",
    "qa_app",
    "postgres-bank",
    "10.0.0.7",
    "app_konto",
    "postgres-shop",
    "10.0.0.9",
)


class Rows:
    """One queued row and what was stored for it."""

    done = "done"

    def __init__(self) -> None:
        """Queues row 1."""
        self.pending = [1]
        self.failed: dict[int, str] = {}

    def claim(self) -> int | None:
        """Takes the row."""
        return self.pending.pop(0) if self.pending else None

    def abandon(self) -> int:
        """Nothing is left claimed."""
        return 0

    def touch(self) -> bool:
        """The row is still held."""
        return True

    def fail(self, key: int, error: str) -> None:
        """Records the stored error."""
        self.failed[key] = error


class Stage(StageService):
    """A stage whose one row meets an unexpected error."""

    name = "stub"
    unit = "row"

    def __init__(self, failure: Exception) -> None:
        """Holds the row queue and the error."""
        self.rows = Rows()
        super().__init__(self.rows)  # type: ignore[arg-type]
        self._failure = failure

    def process_next(self) -> Any | None:
        """Works the row, which fails."""
        key = self.rows.claim()
        if key is None:
            return None
        self._crashed(key, self._failure, trace.get_current_span())
        return key


@pytest.mark.parametrize("said", DRIVER_TEXTS)
def test_a_crashed_row_stores_a_fixed_sentence_and_the_log_holds_the_text(
    said: str, caplog: pytest.LogCaptureFixture
) -> None:
    """The type and a trace id are stored; the driver's own text is only logged."""
    stage = Stage(OSError(said))

    with caplog.at_level(logging.ERROR):
        stage.process_next()

    stored = stage.rows.failed[1]
    assert stored.startswith("OSError"), stored
    assert "trace " in stored
    for leak in LEAKS:
        assert leak not in stored, stored
    assert said in caplog.text, "the log holds what the row does not"
    trace_id = stored.rsplit("trace ", 1)[1].rstrip(")")
    assert trace_id in caplog.text, "the stored sentence names a trace the log has"
