"""The stage routes, as the orchestrator calls them.

HTTP and nothing else. The orchestrator holds no database URL and no object
store credentials on purpose: the queue has three faces already - the Start
button, the make targets and these routes - and a fourth that reached past
them into the tables would be a second way of moving a row, disagreeing with
the other three the first time one of them changed.

Every call here is one a person could make with curl. That is the test of
whether this stays an orchestrator rather than becoming a second backend.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

import requests

log = logging.getLogger(__name__)

#: How long one call may take. Generous for a POST, because `rerun` over a
#: large corpus is one UPDATE over every row of a table; none of them does
#: the work, so none of them waits for a model.
_TIMEOUTS = {"GET": 15.0, "POST": 120.0}


@dataclass(frozen=True)
class Queue:
    """How much work one stage has, as /status reports it."""

    working: bool
    rows: dict[str, int]
    #: Per status, a digest of which rows it holds and which run asked for
    #: each. Equal counts with another digest are other rows.
    digests: dict[str, str] = field(default_factory=dict)

    @property
    def outstanding(self) -> int:
        """Rows a worker still has to take, or is holding right now."""
        return self.rows.get("pending", 0) + self.rows.get("in_progress", 0)

    @property
    def failed(self) -> int:
        """Rows this stage could not process."""
        return self.rows.get("failed", 0)

    @property
    def idle(self) -> bool:
        """Whether there is nothing left for a worker to do.

        Not the same as finished: a queue nobody has started is idle too,
        every row sitting `new`. That distinction is the caller's, because
        `new` is what `start` is for.
        """
        return self.outstanding == 0 and not self.working


class Backend:
    """The backend's stage surface."""

    def __init__(self, base_url: str, session=None) -> None:
        """Initialises the client against the backend at `base_url`."""
        self._base_url = base_url.rstrip("/")
        if session is None:
            session = requests.Session()
            session.headers["X-API-Token"] = os.environ.get("API_TOKEN", "")
        self._session = session

    def status(self, stage: str) -> Queue:
        """Reports how much work one stage has waiting."""
        body = self._call("GET", f"/{stage}/status", digests="true")
        return Queue(
            working=body["working"],
            rows=body["rows"],
            digests=body["digests"],
        )

    def act(self, stage: str, action: str, run: str | None = None) -> int:
        """Runs one queue verb over everything a stage owns.

        Args:
            stage: The route prefix.
            action: The verb.
            run: The Dagster run asking, written onto every row the verb
                queues and adopted by the worker that claims one - so the
                facts a run produced carry that run's id and not the id of
                whichever long-lived worker happened to take them.

        Returns:
            How many rows it moved. None of them does the work: the verb
            moves rows between statuses and whichever worker is watching
            picks up what became claimable.
        """
        moved = self._call("POST", f"/{stage}/{action}", run=run)["rows"]
        log.info("%s: %s moved %d row(s)", stage, action, moved)
        return moved

    def discover(self, run: str | None = None) -> int:
        """Asks for a topic fit over the whole corpus.

        Topic modelling's own verb. It has no `new` rows and so no `start`:
        every topic is estimated jointly over one vocabulary, so asking is
        what creates the work.
        """
        fit = self._call("POST", "/topics/discover", run=run)["fit"]
        log.info("topics: fit %s queued", fit)
        return fit

    def plan(self, stage: str) -> dict:
        """What one stage is configured to do, as its own /plan reports it.

        Only the assessment phase has one that the orchestrator reads, and
        it reads it for one thing: whether the phase is switched on. An
        asset that started a phase a deployment turned off would be the
        orchestrator deciding something `.env` had already decided.
        """
        return self._call("GET", f"/{stage}/plan")

    def judged(self) -> dict:
        """What the judge made of the corpus, as /assessment/quality reports it.

        Read so the assessment asset can carry the approval rate and the
        disagreement count as metadata. A number on an asset page and never
        a reason to fail one - see `assessments_agreement`.
        """
        return self._call("GET", "/assessment/quality")

    def drain(self, stage: str, *, timeout: float, poll: float) -> Queue:
        """Waits until a stage has nothing claimable left.

        Polls rather than subscribes, which is what the workers do to the
        queue as well. The interval is the caller's: a stage whose unit
        costs a model call is not worth asking about every second.

        Raises:
            TimeoutError: If the queue has not drained in `timeout`
                seconds. Never a reason to fail the rows - they are still
                queued and a worker is still on them - so what this means
                is that the run gave up watching, not that the work did.

        ponytail: an asset holds a Dagster op for up to
        ORCHESTRATION_DRAIN_TIMEOUT_SECONDS, and a stage that outlasts it
        fails the asset and skips everything downstream. Upgrade: a sensor
        that starts the next asset when a queue drains.
        """
        deadline = time.monotonic() + timeout
        while True:
            try:
                queue = self.status(stage)
            except requests.exceptions.RequestException as exc:
                # The workers drain on whether this is asking or not.
                log.warning("could not read %s's queue, asking again: %s", stage, exc)
                queue = None
            if queue is not None and queue.idle:
                return queue
            if time.monotonic() >= deadline:
                left = (
                    queue.outstanding if queue is not None else "an unknown number of"
                )
                raise TimeoutError(
                    f"{stage} still has {left} row(s) after "
                    f"{timeout:.0f}s. The work is queued and the worker has "
                    f"it; only this run stopped waiting."
                )
            time.sleep(poll)

    def _call(self, method: str, path: str, **params: str | None) -> dict:
        """Sends one request and returns the parsed body.

        Raises:
            requests.exceptions.RequestException: On a network failure or
                an error status, whose body carries the reason.
        """
        response = self._session.request(
            method,
            f"{self._base_url}{path}",
            params={name: value for name, value in params.items() if value is not None},
            timeout=_TIMEOUTS[method],
        )
        response.raise_for_status()
        return response.json()
