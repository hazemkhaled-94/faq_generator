"""The command line every pipeline stage shares.

One drain on the host, in the foreground, against the same database the
workers use. The flags mirror the stage's HTTP surface one for one.

A watching worker builds its service again when the settings change. The
check sits between drains, where nothing is claimed.
"""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Callable
from typing import Any

import telemetry
from database.qa_generator import Status, engine
from database.qa_generator.status import OUTSTANDING
from llm.config import spend_cap
from llm.tally import carry
from settings import decimal, optional
from settings.runs import named_run, run_id
from stages.queue import StageQueue, Unnarrowable
from stages.service import SpendCapReached, StageService
from stages.worker import DEFAULT_GRACE_SECONDS, GRACE_SECONDS, Shutdown, watch

log = logging.getLogger(__name__)

#: The queue actions every stage answers, and the route each mirrors.
_ACTIONS = {
    "status": "report the queue depth",
    "start": "queue the rows never asked for",
    "stop": "take back what has not begun",
    "retry": "return failed rows to the queue",
    "reclaim": "return a row a dead worker still holds, without waiting "
    "out its lease. Narrow it with --only unless the stage is stopped",
    "rerun": "queue every row again, finished ones included",
}

#: The host's own action, which no route mirrors: what `make corpus` does with
#: a stage whose container worker is running, rather than drain beside it.
_WAIT = (
    "wait for the stage's container worker to empty the queue, logging the "
    "counts as they move; 3 if rows failed meanwhile"
)

#: One operation only a single stage has, as (help, verb, run). `run` takes
#: whatever `--only` narrowed to and returns how many rows it changed.
Extra = tuple[str, str, Callable[[Any], int]]

#: How long a watching worker waits before asking the model again, and the
#: ceiling it doubles towards. Unchanged by the quietening below: how often
#: a worker TRIES decides how fast it recovers, and a model that comes back
#: should be noticed within the minute.
_RETRY_SECONDS = 5.0
_RETRY_CEILING = 60.0

#: How often a worker that still cannot reach its model says so again.
#:
#: How often it SHOUTS is a different question from how often it tries, and
#: they used to be the same one. A worker polling every 60s wrote a line
#: every 60s, and around it the client wrote a traceback, instructor wrote
#: its attempts and a credential library listed every identity it had.
#:
#: So the first refusal is reported in full and the repeats are counted.
#: Ten minutes is long enough that an overnight outage is a handful of
#: lines and short enough that `make logs` on a broken deployment still
#: says what is wrong without scrolling.
_RETRY_REPORT_SECONDS = 600.0

#: How often a wait for a container worker says it is still waiting when the
#: counts have not moved: a worker that never claims - held by a stale image,
#: a refused stored row or a model it cannot reach - is otherwise one line,
#: and then silence for as long as the hosted run waits.
_WAIT_REPORT_SECONDS = 300.0

#: How long a watching worker whose service would not build on new settings
#: waits before building it again, and the ceiling that doubles towards.
#: Every attempt is a preflight model call and a build, and a value that
#: parses but cannot build stands until somebody changes it. Short at first
#: all the same: the build that fails most is a worker's first, racing the
#: object store or the model hub as the stack starts, and that one wants
#: trying again at the next poll rather than in minutes.
_REBUILD_SECONDS = 5.0
_REBUILD_CEILING = 3600.0


def parser(module: str, actions: dict[str, str]) -> argparse.ArgumentParser:
    """Builds a stage's argument parser.

    The actions are mutually exclusive: two of them in one command silently
    ran only the first.
    """
    built = argparse.ArgumentParser(prog=f"python -m {module}")
    group = built.add_mutually_exclusive_group()
    for flag, description in actions.items():
        group.add_argument(f"--{flag}", action="store_true", help=description)
    built.add_argument(
        "--only",
        metavar="SCOPE=VALUE",
        help="narrow the action to one item, as document=<sha256> or "
        "passage=<id>. Which scopes a stage takes is its own; --only on a "
        "stage that takes none is ignored.",
    )
    built.add_argument("--watch", action="store_true", help="drain and keep draining")
    built.add_argument(
        "--force",
        action="store_true",
        help="rerun a stage whose output released, accepted or reviewed "
        "questions rest on, which --rerun otherwise refuses. Extraction's "
        "--bridge reads it too.",
    )
    return built


def reloading(
    name: str,
    build_service: Callable[[], StageService],
    preflight: Callable[[], None] | None = None,
    prompts: Callable[[], int] | None = None,
    held: dict[str, Any] | None = None,
) -> Callable[[Callable[[], bool]], int]:
    """Wraps a drain so it rebuilds the service when the settings change.

    One small query per poll - the version is a digest of every catalogued
    setting as resolved - and a rebuild only when something moved.

    ponytail: checked between drains, not per row, so a change made during a
    long run waits for that run to finish. The ceiling is that a rebuild
    reloads 2.2 GB of embedding weights in one stage; the upgrade is to
    check inside `StageService.drain`'s loop and rebuild only the
    collaborators whose settings differ.

    A rebuild waits for `preflight` before it claims anything, and records
    `prompts` again. The first build does neither: `queue_main` has already.

    A build that fails drops the service it would have replaced, so nothing
    is worked on settings nobody asks for any more, and is not tried again
    on those settings for `_REBUILD_SECONDS`, doubling to `_REBUILD_CEILING`
    while those settings stand. Settings that move start again from
    `_REBUILD_SECONDS`.

    ponytail: the wait ignores a stop request. Nothing is claimed while it
    waits, so the supervisor's kill loses nothing; the upgrade is giving
    `_ready` the `stopping` callable and an interruptible sleep.
    """
    from settings.store import current

    # The caller's, when it wants to reach the service that holds a row.
    held = {} if held is None else held

    def drain(stopping: Callable[[], bool]) -> int:
        """Drains the queue, on a service built from the current settings."""
        version = current()
        if held.get("version") != version:
            if held.get("failed") == version and time.monotonic() < held["retry_at"]:
                return 0
            if held:
                log.info(
                    "%s: settings are now %s; building the service again",
                    name,
                    version,
                )
                if preflight is not None:
                    _ready(name, preflight, True)
                if prompts is not None:
                    prompts()
            try:
                service = build_service()
            except Exception:
                wait = (
                    held["backoff"]
                    if held.get("failed") == version
                    else _REBUILD_SECONDS
                )
                held.pop("service", None)
                held.pop("version", None)
                held.update(
                    failed=version,
                    retry_at=time.monotonic() + wait,
                    backoff=min(2 * wait, _REBUILD_CEILING),
                )
                log.exception(
                    "%s: the service would not build on settings %s; claiming "
                    "nothing, and building it again in %s",
                    name,
                    version,
                    _for(wait),
                )
                return 0
            held.clear()
            held.update(service=service, version=version)
        return held["service"].drain(stopping)

    return drain


def narrowing(queue: StageQueue, only: str | None):
    """Reads `--only` into the condition it selects, or nothing.

    Raises:
        SystemExit: If it is not `scope=value`, names a scope this stage does
            not take, or carries a value that column cannot hold. The last
            two are the queue's own wording, which the route answers with too.
    """
    if only is None:
        return None
    scope, _, value = only.partition("=")
    if not value:
        accepted = ", ".join(queue.scopes) or "nothing"
        raise SystemExit(f"--only takes SCOPE=VALUE, where SCOPE is one of {accepted}")
    try:
        return queue.narrowed(scope, value)
    except Unnarrowable as exc:
        raise SystemExit(str(exc)) from None


def trace(name: str) -> None:
    """Starts exporting this process's spans, once it is going to call a model.

    Named with the run only when somebody named the run: an unnamed one
    appends to the stage's own project and is told apart by the `run.id`
    attribute. See telemetry/pipeline.py. For a drain, and for a pass of a
    stage's own that calls a model - which calls this after its own preflight,
    in the same order a drain does: logged, proved, traced, worked.
    """
    telemetry.configure(name, run=run_id(), named=named_run())
    telemetry.trace_engine(engine())


def queue_main(
    *,
    name: str,
    module: str,
    repository: Callable[[], StageQueue],
    build_service: Callable[[], StageService],
    argv: list[str],
    extra: dict[str, Extra] | None = None,
    preflight: Callable[[], None] | None = None,
    prompts: Callable[[], int] | None = None,
    report: Callable[[], str] | None = None,
) -> int:
    """Runs one stage's command line.

    The repository and the service are built only when a flag needs them, so
    `--status` costs a query and not a converter. `extra` adds the operations
    only this stage has, in the same mutually exclusive group as the rest.

    `preflight` is what a stage proves before it claims anything - for the
    three that call a model, that the model answers. It raises, and the
    process stops with nothing taken.

    `report` is a line only this stage can add to `--status`.

    `prompts` records what this stage sends, so the version on each row it
    writes can be resolved to the text that produced it. Beside preflight
    because both are things done once before the first claim; unlike
    preflight it cannot fail a start, since a prompt nobody can read back
    is worse than a run that did not happen only if the run happened.
    """
    extra = extra or {}
    actions = {
        **_ACTIONS,
        "wait": _WAIT,
        **{flag: help for flag, (help, _, _) in extra.items()},
    }
    args = parser(module, actions).parse_args(argv)

    # Before anything is asked of a model: this process's spend counts from
    # what the run's earlier drains spent.
    carry(optional("SPEND_LEDGER"))

    # Logs now, tracing once this process knows it is going to work.
    #
    # The exporter is what creates a Phoenix project, and the first span a
    # stage produces is the preflight's - the call it makes to prove the
    # model answers. A deployment whose credential has expired therefore
    # left a project per attempt holding one failed call, which under
    # `restart: unless-stopped` is a project per restart. That is the same
    # failure the comment in `_ready` describes from the other side, and
    # this is the half of it the retry loop could not fix.
    #
    # A provider can be installed once per process, so this cannot be done
    # by configuring twice; `tracing=False` leaves it uninstalled.
    telemetry.configure(name, run=run_id(), named=named_run(), tracing=False)

    def act(run):
        """Runs one queue operation, narrowed to whatever --only names."""
        queue = repository()
        return run(queue, narrowing(queue, args.only))

    if args.status:
        log.info("%s queue: %s", name, act(lambda q, w: q.counts_by_status(w)))
        if report is not None:
            log.info("%s: %s", name, report())
        return 0

    if args.wait:
        return wait_for_worker(name, repository(), decimal("WORKER_POLL_SECONDS"))

    # Every verb that queues rows stamps them with this process's run, so
    # the drain that picks them up - a different process, or a container
    # started weeks ago - writes what it produces under the id of whatever
    # asked. RUN_ID names it where somebody named it; see settings.runs.
    asking = run_id()

    for chosen, verb, run in (
        (args.start, "queued", lambda q, w: q.start(w, trigger=asking)),
        (args.stop, "taken off the queue", lambda q, w: q.stop(w)),
        (args.retry, "returned to the queue", lambda q, w: q.retry(w, trigger=asking)),
        (args.reclaim, "reclaimed", lambda q, w: q.reclaim(w, trigger=asking)),
    ):
        if chosen:
            log.info("%s: %d row(s) %s", name, act(run), verb)
            return 0

    for flag, (_, verb, run) in extra.items():
        if getattr(args, flag):
            try:
                done = act(lambda q, w, do=run: do(w))
            except SpendCapReached as stop:
                # What the pass wrote is kept; it stopped itself, as a drain does.
                log.error("%s: --%s stopped itself: %s", name, flag, stop)
                return STOPPED
            log.info("%s: %d row(s) %s", name, done, verb)
            return 0

    # ponytail: a drain takes the whole queue, so `--only` narrows the verb
    # before it and never the drain. Upgrade: pass the narrowing into
    # `process_next`, which every stage's claim would have to take.
    if args.only is not None:
        if not args.rerun:
            raise SystemExit(
                "--only narrows a verb or --rerun; on its own the drain takes "
                "the whole queue"
            )
        queue = repository()
        within = narrowing(queue, args.only)
        outside = queue.counts_by_status().get(
            Status.PENDING, 0
        ) - queue.counts_by_status(within).get(Status.PENDING, 0)
        if outside:
            raise SystemExit(
                f"--only {args.only}: {outside} row(s) outside it are queued, and "
                f"the drain after the rerun would take them too. Take them back "
                f"first: python -m {module} --stop"
            )

    # A rerun over questions somebody accepted, reviewed or released is
    # refused, before the model is asked for anything, until it is forced.
    if args.rerun and not args.force:
        queue = repository()
        resting = getattr(queue, "resting", None)
        at_risk = resting(narrowing(queue, args.only)) if resting else None
        if at_risk:
            raise SystemExit(f"{name}: {at_risk.refusal('FORCE=1 (--force)')}")

    # Here rather than inside the loop below, which logs an exception and
    # polls again: that is right for a drain that failed and wrong for a
    # deployment that can never work. A worker with no usable credential
    # would otherwise claim a row every poll and fail it, and the queue
    # would empty into `failed` while the container reported itself up.
    # Before the rerun's reset, which can clear stored work.
    if preflight is not None and not _ready(name, preflight, args.watch):
        return 1

    if args.rerun:
        log.info(
            "%s: %d row(s) queued again",
            name,
            act(lambda q, w: q.reset(w, trigger=asking)),
        )

    # Past here the process is going to claim rows, so its spans are worth
    # a project.
    trace(name)

    # After preflight, so a deployment that cannot work does not leave a
    # record of prompts it never sent. Never raises; see stages.prompts.
    if prompts is not None:
        prompts()

    if not args.watch:
        # Built once: one drain cannot outlive a change to the settings.
        service = build_service()
        announce(service, repository())
        return drain_once(service)

    serving: dict[str, Any] = {}
    watch(
        reloading(name, build_service, preflight, prompts, serving),
        decimal("WORKER_POLL_SECONDS"),
        give_back(serving),
        GRACE_SECONDS.get(name, DEFAULT_GRACE_SECONDS),
    )
    return 0


#: What a drain exits with when it stopped itself: EX_TEMPFAIL, the code for
#: try again later. Its claimed row is back in the queue.
STOPPED = 75

#: What a drain exits with when a row failed.
FAILED = 3


def announce(service: StageService, queue: StageQueue) -> None:
    """Says what a drain is about to take, and what that may cost.

    The estimate is the stage's own, measured on one build and so only an
    order of magnitude; with SPEND_CAP set, the line says where the drain
    stops.
    """
    try:
        queued = queue.counts_by_status().get(Status.PENDING, 0)
    except Exception:
        log.warning("%s: could not count the queue", service.name, exc_info=True)
        return
    if not queued:
        return
    cost = ""
    if service.estimate is not None:
        usd, seconds = service.estimate
        cost = (
            f", about USD {queued * usd:.0f} and {_for(queued * seconds)} at the "
            f"measured USD {usd:.4f} and {seconds:.1f}s each"
        )
    cap = spend_cap()
    log.info(
        "%s: %d %s(s) queued%s%s",
        service.name,
        queued,
        service.unit,
        cost,
        "" if cap is None else f"; stops at USD {cap:.2f}",
    )


def drain_once(service: StageService) -> int:
    """Drains once, as a worker does under a stop, and says how it ended.

    The same `Shutdown` a watching worker has: SIGTERM or SIGINT lets the row
    in hand finish and claims no more, a second signal or the stage's grace
    running out gives the row back and leaves, so a supervised one-off drain
    (the host runner's) never dies holding a row for the next start to fail.
    A stop asked for ends it 75, as the drain's own stops do.
    """
    shutdown = Shutdown(
        GRACE_SECONDS.get(service.name, DEFAULT_GRACE_SECONDS), service.give_back
    ).install()
    try:
        service.drain(shutdown.requested)
    finally:
        shutdown.done()
    return STOPPED if shutdown.requested() else exit_code(service)


def wait_for_worker(
    name: str,
    queue: StageQueue,
    interval: float,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Waits for the stage's container worker to empty the queue, and says how it ended.

    What the corpus chain does where that worker runs - parsing and chunking
    on the go-live profile - since a host drain beside it is what the
    Makefile's guard refuses. Polls the counts every `interval` seconds and
    logs them when they move, and every `_WAIT_REPORT_SECONDS` when they do
    not, naming a worker that has claimed nothing in that time, until nothing
    is pending or in progress. Exits as a drain would: 3 when rows failed
    while it waited, so the chain stops there, and 75 when a stop is asked
    for, which it obeys at once because it holds nothing.
    """
    shutdown = Shutdown().install()
    try:
        counts = queue.counts_by_status()
        failed = counts.get(Status.FAILED, 0)
        said, said_at = None, clock()
        while any(left := tuple(counts.get(one, 0) for one in OUTSTANDING)):
            idle = clock() - said_at
            if left != said or idle >= _WAIT_REPORT_SECONDS:
                still = left == said and not left[1]
                log.info(
                    "%s: waiting for its worker: %d pending, %d in progress%s",
                    name,
                    *left,
                    f"; it has claimed nothing for {_for(idle)}: read its log for a "
                    "stale image, a refused setting or a model it cannot reach"
                    if still
                    else "",
                )
                said, said_at = left, clock()
            shutdown.wait(interval)
            if shutdown.requested():
                return STOPPED
            counts = queue.counts_by_status()
    finally:
        shutdown.done()
    if (newly := counts.get(Status.FAILED, 0) - failed) > 0:
        log.error(
            "%s: its worker failed %d row(s) while it was waited for", name, newly
        )
        return FAILED
    log.info("%s: its worker has emptied the queue", name)
    return 0


def give_back(serving: dict[str, Any]) -> Callable[[], object]:
    """What a worker cut short calls to return the row its service holds."""

    def called() -> object:
        """Returns the held row, if there is a service and it holds one."""
        service = serving.get("service")
        return service.give_back() if service is not None else False

    return called


def exit_code(service: StageService) -> int:
    """What a drain that has finished tells whoever ran it.

    0 when every row was worked, 3 when a row failed, and 75 when the drain
    stopped itself - the model could not be reached, or it answered nothing
    for too many passages, or the spend cap was reached - with what it held
    back in the queue. 75 outranks 3: it is the one that wants the run
    started again.
    """
    if service.stalled:
        return STOPPED
    return FAILED if service.failed else 0


def _ready(name: str, preflight: Callable[[], None], watching: bool) -> bool:
    """Whether the model answered, waiting for it where this is a worker.

    A one-off drain gives up, because a person is holding the exit code.
    A **watching worker waits in place** instead, and that is the whole
    point of this function: exiting costs a process, and under
    `restart: unless-stopped` a process is a restart and a new `run_id`.

    Waiting also recovers by itself. A model that is down at boot and up
    ten minutes later is the ordinary case for one served off a laptop,
    and it needs nobody to run `make up` again.
    """
    delay = _RETRY_SECONDS
    attempts = 0
    began = time.monotonic()
    said = 0.0
    while True:
        try:
            preflight()
            if attempts:
                # The recovery is worth a line of its own. Without it the
                # log goes quiet and a reader cannot tell a worker that
                # started working from one that stopped complaining.
                log.info(
                    "%s reached its model after %d attempt(s) over %s, and is "
                    "claiming work",
                    name,
                    attempts + 1,
                    _for(time.monotonic() - began),
                )
            return True
        except Exception as refusal:  # noqa: BLE001 - any of them means wait
            # One line rather than a traceback: this is a deployment that is
            # wrong, not a bug, and the person reading `podman logs` needs
            # the reason and not the call stack.
            if not watching:
                log.error("%s will not start: %s", name, refusal)
                return False
            # A setting refused, not a model that is down.
            why = (
                "refuses to claim work"
                if isinstance(refusal, (KeyError, ValueError))
                else "cannot reach its model"
            )
            waited = time.monotonic() - began
            if not attempts:
                log.error(
                    "%s %s and will keep trying every %.0fs, reporting again "
                    "every %.0f minutes until it can: %s",
                    name,
                    why,
                    _RETRY_CEILING,
                    _RETRY_REPORT_SECONDS / 60,
                    refusal,
                )
                said = waited
            elif waited - said >= _RETRY_REPORT_SECONDS:
                # Counted rather than repeated. The reason is in the first
                # line; what a reader needs now is whether it is still
                # happening and for how long.
                log.warning(
                    "%s still %s: %d attempt(s) over %s",
                    name,
                    why,
                    attempts + 1,
                    _for(waited),
                )
                said = waited
            attempts += 1
            time.sleep(delay)
            delay = min(delay * 2, _RETRY_CEILING)


def _for(seconds: float) -> str:
    """How long something has been going on, for a person to read."""
    if seconds < 90:
        return f"{seconds:.0f}s"
    if seconds < 5400:
        return f"{seconds / 60:.0f}m"
    return f"{seconds / 3600:.1f}h"
