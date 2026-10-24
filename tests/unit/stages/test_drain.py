"""What a drain does with rows that fail, and what it tells whoever ran it.

A model that is down fails every row it is given, and used to be given all of
them: the queue emptied into `failed` and the exit code said 0.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import httpx
import litellm
import pytest
from instructor.core import InstructorRetryException
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


def unavailable(cause: BaseException | None = None) -> ModelUnavailable:
    """What the client raises, with what it failed on behind it."""
    wrapped = ModelUnavailable(f"{type(cause).__name__}")
    wrapped.__cause__ = cause or litellm.exceptions.Timeout(
        "timed out", model="azure/x", llm_provider="azure"
    )
    return wrapped


def down_from(first: int, last: int = 1000) -> dict[int, Exception]:
    """The failures of a model that is unreachable for rows `first` to `last`."""
    return {key: unavailable() for key in range(first, last + 1)}


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
    wrapped.__cause__ = unavailable()

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


def _litellm(kind: Callable[..., Exception], message: str) -> Exception:
    """One litellm failure as the provider's SDK raises it."""
    try:
        return kind(message, model="azure/x", llm_provider="azure")
    except TypeError:
        # The ones that carry the HTTP response they were raised for.
        response = httpx.Response(
            403, request=httpx.Request("POST", "https://example.invalid")
        )
        return kind(message, model="azure/x", llm_provider="azure", response=response)


#: A failure of the whole deployment, or one that passes: asking again later,
#: or of another deployment, is what ends it. The messages are the provider's
#: and come in the languages its users write in.
OUTAGES = [
    _litellm(litellm.exceptions.Timeout, "timed out"),
    _litellm(litellm.exceptions.APIConnectionError, "Verbindung abgelehnt"),
    _litellm(litellm.exceptions.RateLimitError, "rate limited"),
    _litellm(litellm.exceptions.InternalServerError, "Interner Serverfehler"),
    _litellm(litellm.exceptions.ServiceUnavailableError, "unavailable"),
    _litellm(litellm.exceptions.AuthenticationError, "bad key"),
    _litellm(litellm.exceptions.NotFoundError, "deployment not found"),
    _litellm(litellm.exceptions.PermissionDeniedError, "Zugriff verweigert"),
]

#: A failure about one row: the provider answered, and will answer the same
#: about it again, and differently about the next.
ROW_FAULTS = [
    _litellm(litellm.exceptions.BadRequestError, "context_length_exceeded"),
    _litellm(litellm.exceptions.ContextWindowExceededError, "Kontext zu lang"),
    _litellm(litellm.exceptions.ContentPolicyViolationError, "filtered"),
    None,  # the shape the model could not fill: instructor's own failure
]


def _row_fault(cause: Exception | None) -> ModelUnavailable:
    """The client's failure for one of `ROW_FAULTS`."""
    if cause is None:
        return unavailable(
            InstructorRetryException("no valid shape", n_attempts=3, total_usage=0)
        )
    return unavailable(cause)


@pytest.mark.parametrize("cause", OUTAGES, ids=lambda one: type(one).__name__)
def test_a_failure_of_the_deployment_is_an_outage(cause: Exception) -> None:
    """Transient, or a fault of the whole deployment: the next row meets it too."""
    assert is_outage(unavailable(cause))


@pytest.mark.parametrize("cause", ROW_FAULTS, ids=lambda one: type(one).__name__)
def test_a_failure_about_one_row_is_not_an_outage(cause: Exception | None) -> None:
    """The provider answered about this row; the next may be fine."""
    assert not is_outage(_row_fault(cause))


@pytest.mark.parametrize("cause", ROW_FAULTS, ids=lambda one: type(one).__name__)
def test_rows_the_provider_rejects_fail_and_the_drain_goes_on(
    cause: Exception | None,
) -> None:
    """Five in a row fail, the sixth is claimed, and the exit is 3 and not 75."""
    failures = {key: _row_fault(cause) for key in range(3, 3 + STOP_AFTER)}
    stage = Stage(Rows(20), failures)

    stage.drain()

    assert stage.stalled is None
    assert sorted(stage.rows.failed) == list(range(3, 3 + STOP_AFTER))
    assert stage.rows.released == []
    assert stage.rows.finished == [1, 2, *range(3 + STOP_AFTER, 21)]
    assert exit_code(stage) == FAILED


def test_a_drain_that_stopped_itself_reports_no_rows_worked() -> None:
    """A watching worker waits its poll interval only on a drain of none.

    The rows it gave back are not worked, and counting the rest as work had a
    stopped worker claim again at once.
    """
    stage = Stage(Rows(40), down_from(11))

    assert stage.drain() == 0
    assert exit_code(stage) == STOPPED
