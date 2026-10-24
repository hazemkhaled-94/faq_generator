"""The watch loop every stage worker runs.

ponytail: a poll, not LISTEN/NOTIFY. At this interval an idle worker costs one
cheap query every few seconds; NOTIFY on the status column is the upgrade if
that ever matters.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
from collections.abc import Callable
from types import FrameType

log = logging.getLogger(__name__)

#: How long a worker whose stage is called this finishes the row it holds
#: after a SIGTERM, before it gives the row back and leaves. Sized from one
#: row's worst case where that fits inside what a supervisor will wait: a
#: parse or a chunking is minutes, so it is allowed to end. A row that calls a
#: model - a topic's questions are dozens of calls - cannot be waited for, and
#: gets the default, after which the row goes back to pending instead of
#: being killed in progress and failed by the next start.
GRACE_SECONDS = {"parsing": 90.0, "chunking": 90.0}
DEFAULT_GRACE_SECONDS = 270.0

#: What `stop_grace_period` in compose.yaml must be above the grace: the time
#: to give the row back and exit. A static test holds the two together.
RELEASE_MARGIN = 30.0

#: What a worker exits with when it left a row unfinished and gave it back.
LEFT_EARLY = 75


class Shutdown:
    """Records that the process has been asked to stop, and wakes the loop."""

    def __init__(
        self,
        grace: float = DEFAULT_GRACE_SECONDS,
        give_back: Callable[[], object] | None = None,
        leave: Callable[[int], object] = os._exit,
    ) -> None:
        """Initialises an unrequested shutdown.

        Args:
            grace: How long the held row may go on after the first signal.
            give_back: Returns the held row to the queue, unworked.
            leave: Ends the process; replaced in a test.
        """
        # An Event rather than a bool, so a worker asleep between polls wakes
        # at once instead of serving out the rest of its interval.
        self._event = threading.Event()
        self._grace = grace
        self._give_back = give_back
        self._leave = leave
        self._timer: threading.Timer | None = None

    def install(self) -> Shutdown:
        """Catches the signals a supervisor stops a container with."""
        for received in (signal.SIGTERM, signal.SIGINT):
            signal.signal(received, self._request)
        return self

    def _request(self, number: int, frame: FrameType | None) -> None:
        """Records the request; a second one, or the grace running out, ends it.

        The first signal stops the worker claiming and lets the row finish. A
        second signal says nobody is waiting any longer, and `grace` seconds
        after the first is when the supervisor stops waiting: either way the
        held row goes back to the queue and the worker leaves, rather than
        being killed holding a row nothing will retry.
        """
        del frame
        if self._event.is_set():
            log.warning("%s received again", signal.Signals(number).name)
            self._leaving("asked twice")
            return
        log.info(
            "%s received: finishing the current item, then stopping; the item "
            "goes back to the queue if that takes over %.0fs",
            signal.Signals(number).name,
            self._grace,
        )
        self._event.set()
        self._timer = threading.Timer(self._grace, self._leaving, ["out of time"])
        self._timer.daemon = True
        self._timer.start()

    def _leaving(self, why: str) -> None:
        """Gives the held row back and ends the process, on a thread of its own.

        Not on the one a signal interrupted: that thread may be holding the
        lock the queue's release needs, and would wait on itself.
        """
        threading.Thread(target=self._leave_now, args=(why,), daemon=True).start()

    def _leave_now(self, why: str) -> None:
        """Returns the held row to the queue, then ends the process."""
        log.warning("leaving before the item is finished (%s)", why)
        try:
            if self._give_back is not None:
                self._give_back()
        except Exception:
            log.exception("could not give the held item back; the lease will")
        logging.shutdown()
        self._leave(LEFT_EARLY)

    def done(self) -> None:
        """Stops the clock on a worker that finished in time."""
        if self._timer is not None:
            self._timer.cancel()

    def requested(self) -> bool:
        """Whether a stop has been asked for."""
        return self._event.is_set()

    def wait(self, seconds: float) -> None:
        """Sleeps, unless and until a stop is requested."""
        self._event.wait(seconds)


def watch(
    drain: Callable[[Callable[[], bool]], int],
    interval: float,
    give_back: Callable[[], object] | None = None,
    grace: float = DEFAULT_GRACE_SECONDS,
) -> None:
    """Drains the queue until the process is asked to stop.

    `give_back` returns the row the worker holds to the queue, which is what
    it does when a second signal, or `grace` seconds, cut a row short.
    """
    shutdown = Shutdown(grace, give_back).install()
    log.info("watching the queue, polling every %.0fs", interval)

    while not shutdown.requested():
        try:
            if drain(shutdown.requested) == 0:
                shutdown.wait(interval)
        except Exception:
            # Logged rather than raised: exiting here would stop the pipeline
            # until somebody noticed, and the lease recovers the held row.
            log.exception("drain failed; retrying after %.0fs", interval)
            shutdown.wait(interval)

    shutdown.done()
    log.info("stopped with nothing claimed")
