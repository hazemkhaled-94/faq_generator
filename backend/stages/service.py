"""The drain loop every pipeline stage runs.

A stage claims one row, works it, and records what became of it. Every stage
annotates its span with `stage.name` and `stage.outcome`, so one trace query
finds everything that failed whichever stage failed it.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, ClassVar

from opentelemetry.trace import Span

from llm.config import spend_cap
from llm.tally import spent_usd
from stages.queue import StageQueue

log = logging.getLogger(__name__)

#: How often a worker says it is still on the row it holds. Ten of these fit
#: inside `StageQueue.lease`, so a beat may be missed for a slow query or a
#: paused process without the row being swept out from under it.
HEARTBEAT_SECONDS = 30.0


#: How many rows in a row a model may fail before the drain stops claiming.
#: A count of an outage and not a quality threshold: a model that is down
#: fails every row, and one bad row is never four in a row, so any value from
#: three to ten tells the two apart.
STOP_AFTER = 5


def is_outage(failure: BaseException) -> bool:
    """Whether a row failed because the deployment could not be reached.

    The model unavailable, found behind whatever wrapped it, for a cause
    that is transient or a fault of the whole deployment. A refusal is not
    one, nor is a request the provider rejects or a shape the model could
    not fill: it answered, about this row, and the next may be fine.
    """
    # Here, not at the top: the client loads litellm, which the api, whose
    # routes import this package, must not.
    from llm.client import ModelRefused, ModelUnavailable, deployment_down

    seen: BaseException | None = failure
    while seen is not None:
        if isinstance(seen, ModelUnavailable):
            return not isinstance(seen, ModelRefused) and deployment_down(seen)
        seen = seen.__cause__
    return False


def _never() -> bool:
    """Reports that no stop has been asked for."""
    return False


class StageService(ABC):
    """One stage's worker: claim a row, work it, record the outcome."""

    #: The stage's name, recorded on every span and log line.
    name: ClassVar[str]
    #: What this stage counts, singular: document, passage or fit.
    unit: ClassVar[str]

    #: What one row cost on the build this was measured on, in USD and in
    #: seconds, for the estimate a drain prints before it starts. Only an
    #: order of magnitude: it moves with the model split and the corpus. A
    #: stage that calls no model says nothing.
    estimate: ClassVar[tuple[float, float] | None] = None

    _REQUIRED = ("name", "unit")

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Refuses a stage that has not said what it is called."""
        super().__init_subclass__(**kwargs)
        if ABC in cls.__bases__:
            return
        missing = [name for name in StageService._REQUIRED if not hasattr(cls, name)]
        if missing:
            raise TypeError(
                f"{cls.__name__} is a StageService but does not declare "
                f"{', '.join(missing)}."
            )

    def __init__(self, repository: StageQueue) -> None:
        """Initialises the service with its queue."""
        self._repository = repository
        #: What the last drain left: how many rows failed, the keys of the
        #: rows in a row the model could not be reached for, and why the
        #: drain stopped itself, if it did.
        self.failed = 0
        self._outages: list[tuple[Any, bool]] = []
        self.stalled: str | None = None

    @abstractmethod
    def process_next(self) -> Any | None:
        """Claims one row and works it, returning its key or None."""

    @contextmanager
    def _beating(self) -> Iterator[None]:
        """Says this worker is still alive for as long as the body runs.

        One thread for the drain rather than one per row: the queue beats
        whichever row it holds, and holds none between rows.
        """
        stop = threading.Event()

        def beat() -> None:
            """Refreshes the held claim until the drain is done with it."""
            while not stop.wait(HEARTBEAT_SECONDS):
                try:
                    self._repository.touch()
                except Exception:
                    # Logged, not raised: this thread failing must not take
                    # the work down with it, and a missed beat costs nothing
                    # until the lease runs out.
                    log.warning("%s: heartbeat failed", self.name, exc_info=True)

        thread = threading.Thread(
            target=beat, name=f"{self.name}-heartbeat", daemon=True
        )
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=HEARTBEAT_SECONDS)

    def drain(self, stopping: Callable[[], bool] = _never) -> int:
        """Works every queued row, sweeping abandoned claims first."""
        abandoned = self._repository.abandon()
        if abandoned:
            log.warning(
                "%s: failed %d %s(s) left claimed by an earlier run",
                self.name,
                abandoned,
                self.unit,
            )
        processed = 0
        self.failed = 0
        self._outages = []
        self.stalled = None
        cap = spend_cap()
        with self._beating():
            while not stopping() and self.stalled is None:
                # Before the claim, so nothing is held when it stops.
                if cap is not None and spent_usd() >= cap:
                    self._stop(
                        f"SPEND_CAP is USD {cap:.2f} and this process has spent "
                        f"USD {spent_usd():.2f}; nothing more is claimed"
                    )
                    break
                if self.process_next() is None:
                    break
                processed += 1
        # What a stalled drain gave back was not worked.
        processed -= len(self._outages) if self.stalled else 0
        if processed or self.failed:
            log.info(
                "%s: %d %s(s), %d failed, USD %.2f spent",
                self.name,
                processed,
                self.unit,
                self.failed,
                spent_usd(),
            )
        return processed

    def _stop(self, reason: str, *keys: Any) -> None:
        """Stops the drain, giving back the rows it will not finish.

        They go back to the queue, the held one included: they were not
        worked on their own account, and rows left failed, or finished with
        nothing, would be passed over by the next run without anybody having
        said so.
        """
        self._repository.release(*keys)
        self.stalled = reason
        log.error("%s: %s", self.name, reason)

    def give_back(self) -> bool:
        """Returns the row this stage holds to the queue, unworked.

        What a worker does when it is told to stop and cannot wait for the
        row to finish. Whether it held one.
        """
        return self._repository.release_held()

    def _gone(self, key: Any) -> None:
        """Takes a row that no longer exists out of the count of failures.

        A delete that lands while a row is worked leaves nothing to record a
        failure on, and the row is not the model being down.
        """
        self._outages = [(one, was) for one, was in self._outages if one != key]

    def _missed(self, key: Any, outage: bool, failed: bool = True) -> bool:
        """Counts one row's outcome towards a stall, and says whether it came.

        `STOP_AFTER` rows in a row the model could not be reached for stop
        the drain. They go back to the queue, the held one included: they did
        not fail on their own account, and rows left failed would be skipped
        by the next run without anybody having said so. `failed` says whether
        this row was failed, as against kept as it was.
        """
        if not outage:
            self._outages.clear()
            return False
        self._outages.append((key, failed))
        if len(self._outages) < STOP_AFTER:
            return False
        # The held one was never counted; the rest were.
        self.failed -= sum(1 for _, was in self._outages[:-1] if was)
        self._stop(
            f"the model could not be reached for {STOP_AFTER} {self.unit}(s) in a "
            "row; they are back in the queue and nothing more is claimed",
            *(one for one, _ in self._outages),
        )
        return True

    def _fail(self, key: Any, error: str, current: Span, outage: bool = False) -> None:
        """Marks a row failed and annotates the span.

        `outage` says the model could not be reached for it, which is what a
        run of rows failing together is counted on.
        """
        current.set_attribute("stage.name", self.name)
        current.set_attribute("stage.outcome", "failed")
        log.warning("%s: failed %s %s: %s", self.name, self.unit, key, error)
        if self._missed(key, outage):
            return
        self._repository.fail(key, error)
        self.failed += 1

    def _done(self, current: Span) -> None:
        """Annotates the span of a row this stage finished."""
        self._outages.clear()
        current.set_attribute("stage.name", self.name)
        current.set_attribute("stage.outcome", self._repository.done)
