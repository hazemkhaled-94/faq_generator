"""When the orchestrator decides the pipeline should start.

The one piece here that acts on its own. Everything else in this package
runs because a person asked or a clock fired; this runs because something
was uploaded, so what it declines to do matters as much as what it does.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator

import pytest

pytest.importorskip("dagster", reason="the pipeline group is not installed")

from dagster import (
    DagsterInstance,
    DagsterRun,
    DagsterRunStatus,
    RunRequest,
    SkipReason,
    build_sensor_context,
)

import orchestration
from orchestration.client import Queue


@pytest.fixture(autouse=True)
def settings(monkeypatch) -> None:
    """The environment the code location reads, so no .env is needed."""
    monkeypatch.setenv("BACKEND_URL", "http://api:8000")
    monkeypatch.setenv("ORCHESTRATION_DRAIN_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("ORCHESTRATION_POLL_SECONDS", "1")
    monkeypatch.setenv("INGESTION_OPEN", "true")


@pytest.fixture
def instance() -> Iterator[DagsterInstance]:
    """An instance holding no run, disposed when the test ends."""
    with DagsterInstance.ephemeral() as held:
        yield held


def answering(monkeypatch, batch: str = "", **rows: int) -> None:
    """Makes /parsing/status report these counts, of the rows `batch` names."""

    class Stub:
        """Stands in for the backend client."""

        def __init__(self, *args, **kwargs) -> None:
            """Accepts whatever the sensor passes."""

        def status(self, stage: str) -> Queue:
            """Reports the queue the test asked for."""
            return Queue(
                working=rows.get("in_progress", 0) > 0,
                rows={name: count for name, count in rows.items() if count},
                digests={
                    name: f"{batch}{name}{count}"
                    for name, count in rows.items()
                    if count
                },
            )

    monkeypatch.setattr(orchestration, "Backend", Stub)


def evaluate(instance: DagsterInstance):
    """Runs one sensor tick against this instance."""
    return orchestration.arrivals(build_sensor_context(instance=instance))


def test_a_document_nobody_asked_for_starts_a_run(monkeypatch, instance) -> None:
    """Which is the whole reason the sensor exists."""
    answering(monkeypatch, new=3)

    assert isinstance(evaluate(instance), RunRequest)


def test_nothing_starts_while_a_corpus_run_is_going(monkeypatch, instance) -> None:
    """An upload mid-run is read by the run already going through parsing."""
    answering(monkeypatch, new=3)
    instance.add_run(
        DagsterRun(job_name="corpus", run_id="going", status=DagsterRunStatus.STARTED)
    )

    answer = evaluate(instance)

    assert isinstance(answer, SkipReason)
    assert "corpus run" in str(answer.skip_message)


def test_a_run_being_stopped_counts_as_going(monkeypatch, instance) -> None:
    """Until Dagster has torn it down, it still holds the queues."""
    answering(monkeypatch, new=3)
    instance.add_run(
        DagsterRun(
            job_name="corpus", run_id="stopping", status=DagsterRunStatus.CANCELING
        )
    )

    answer = evaluate(instance)

    assert isinstance(answer, SkipReason)
    assert "corpus run" in str(answer.skip_message)


def test_an_empty_queue_starts_nothing(monkeypatch, instance) -> None:
    """A tick a minute over an idle stack must not queue a run a minute."""
    answering(monkeypatch, parsed=8)

    answer = evaluate(instance)
    assert isinstance(answer, SkipReason)
    assert "waiting" in str(answer.skip_message)


def test_nothing_starts_while_a_run_is_already_working(monkeypatch, instance) -> None:
    """`new` beside `pending` is an upload that arrived mid-run.

    Starting a second run for it would have two runs driving one queue,
    both watching the same rows and each crediting the other's work.
    """
    answering(monkeypatch, new=2, pending=5)

    answer = evaluate(instance)
    assert isinstance(answer, SkipReason)
    assert "already queued" in str(answer.skip_message)


def test_two_ticks_over_an_unchanged_queue_ask_for_one_run(
    monkeypatch, instance
) -> None:
    """The run key is what Dagster deduplicates on.

    Without it the sensor asks again every minute until a worker picks
    the documents up, which on a stage with no worker is for ever.
    """
    answering(monkeypatch, new=3)

    assert evaluate(instance).run_key == evaluate(instance).run_key


def test_a_later_upload_asks_for_its_own_run(monkeypatch, instance) -> None:
    """An upload during a run gets a run of its own.

    A run that has already started will not pick up what arrived after
    it, so the key has to change when the queue does.
    """
    answering(monkeypatch, new=3)
    first = evaluate(instance).run_key
    answering(monkeypatch, new=4)

    assert evaluate(instance).run_key != first


def test_the_same_number_arriving_twice_asks_twice(monkeypatch, instance) -> None:
    """Dagster keeps a run key for as long as it keeps the run.

    Three documents uploaded, run, drained, three more uploaded was
    `new-3` both times, and the second one launched nothing: the pipeline
    stopped being unattended the second time a batch happened to be the
    size of an earlier one.
    """
    answering(monkeypatch, new=3)
    context = build_sensor_context(instance=instance)
    first = orchestration.arrivals(context).run_key

    # Worked, and drained. The tick that finds nothing is what records
    # that the queue emptied.
    answering(monkeypatch, parsed=3)
    context = build_sensor_context(cursor=context.cursor, instance=context.instance)
    orchestration.arrivals(context)

    answering(monkeypatch, new=3, parsed=3)
    again = orchestration.arrivals(
        build_sensor_context(cursor=context.cursor, instance=context.instance)
    )

    assert isinstance(again, RunRequest)
    assert again.run_key != first


def test_a_batch_swapped_inside_one_tick_asks_again(monkeypatch, instance) -> None:
    """Three documents worked and three others uploaded between two ticks.

    No tick saw the queue empty or a different count, so a key counting
    only the documents came round again and launched nothing.
    """
    answering(monkeypatch, new=3)
    context = build_sensor_context(instance=instance)
    first = orchestration.arrivals(context).run_key

    answering(monkeypatch, batch="later", new=3, parsed=3)
    again = orchestration.arrivals(
        build_sensor_context(cursor=context.cursor, instance=context.instance)
    )

    assert isinstance(again, RunRequest)
    assert again.run_key != first


def test_a_stopped_run_is_not_started_again_by_the_sensor(
    monkeypatch, instance
) -> None:
    """Stop puts pending documents back to new, which reads as an arrival."""
    answering(monkeypatch, new=3)
    instance.add_run(
        DagsterRun(
            job_name="corpus", run_id="stopped", status=DagsterRunStatus.CANCELED
        )
    )

    answer = evaluate(instance)

    assert isinstance(answer, SkipReason)
    assert "stopped" in str(answer.skip_message)


def test_closed_ingestion_starts_nothing(monkeypatch, instance) -> None:
    """A stage stopped on its own page puts its documents back to `new` too."""
    monkeypatch.setenv("INGESTION_OPEN", "false")
    answering(monkeypatch, new=3)

    answer = evaluate(instance)

    assert isinstance(answer, SkipReason)
    assert "INGESTION_OPEN" in str(answer.skip_message)


def test_a_key_whose_run_failed_is_not_asked_for_again(monkeypatch, instance) -> None:
    """Dagster drops a run key it has seen, so the documents would wait."""
    answering(monkeypatch, new=3)
    context = build_sensor_context(instance=instance)
    first = orchestration.arrivals(context).run_key
    instance.add_run(
        DagsterRun(
            job_name="corpus",
            run_id="failed",
            status=DagsterRunStatus.FAILURE,
            tags={"dagster/run_key": first},
        )
    )

    again = orchestration.arrivals(
        build_sensor_context(cursor=context.cursor, instance=instance)
    )

    assert isinstance(again, RunRequest)
    assert again.run_key != first


def test_two_ticks_over_an_unchanged_queue_share_a_key_through_the_cursor(
    monkeypatch, instance
) -> None:
    """The counter moves on a change, not on a tick.

    A sensor that asked for a new run every minute while a stage with no
    worker held the same three documents would queue a run a minute.
    """
    answering(monkeypatch, new=3)
    context = build_sensor_context(instance=instance)
    first = orchestration.arrivals(context).run_key

    again = orchestration.arrivals(
        build_sensor_context(cursor=context.cursor, instance=context.instance)
    )

    assert again.run_key == first


# ── What the orchestrator did not start ────────────────────────────────────


def _watching(monkeypatch, asked: str = "", **per_stage: dict) -> None:
    """Makes every stage's /status report what the test says, as `asked` left it."""

    class Stub:
        """Stands in for the backend client."""

        def __init__(self, *args, **kwargs) -> None:
            """Accepts whatever the sensor passes."""

        def status(self, stage: str) -> Queue:
            """Reports one stage's queue."""
            rows = per_stage.get(stage, {})
            return Queue(
                working=False,
                rows=rows,
                digests={name: f"{asked}{name}{count}" for name, count in rows.items()},
            )

    monkeypatch.setattr(orchestration, "Backend", Stub)


def test_work_nobody_asked_dagster_to_do_is_still_recorded(
    monkeypatch, instance
) -> None:
    """The whole point.

    A stage drained by `make extract`, by the API, by the Start button or
    by a worker taking a queue somebody else filled is work the asset
    graph used to call "never materialised".
    """
    _watching(monkeypatch, parsing={"parsed": 8, "new": 2})

    result = orchestration.progress(build_sensor_context(instance=instance))

    (event,) = result.asset_events
    assert event.asset_key.to_user_string() == "parsed_documents"
    assert "8 document(s) worked" == event.description


def test_a_tick_that_finds_nothing_new_records_nothing(monkeypatch, instance) -> None:
    """The cursor is what keeps one finished run from being reported for ever."""
    _watching(monkeypatch, parsing={"parsed": 8})
    context = build_sensor_context(instance=instance)
    orchestration.progress(context)

    again = orchestration.progress(
        build_sensor_context(cursor=context.cursor, instance=context.instance)
    )

    assert isinstance(again, SkipReason)


def test_only_the_stage_that_moved_is_reported(monkeypatch, instance) -> None:
    """Five stages, one of which produced something since the last tick."""
    _watching(monkeypatch, parsing={"parsed": 8}, extraction={"extracted": 40})
    context = build_sensor_context(instance=instance)
    orchestration.progress(context)

    _watching(monkeypatch, parsing={"parsed": 8}, extraction={"extracted": 51})
    result = orchestration.progress(
        build_sensor_context(cursor=context.cursor, instance=context.instance)
    )

    (event,) = result.asset_events
    assert event.asset_key.to_user_string() == "facts"
    assert event.metadata["since the last tick"].value == 11


def test_work_that_replaced_rows_between_two_ticks_is_recorded(
    monkeypatch, instance
) -> None:
    """A rerun, or a refit, that left the count where it was.

    Counting alone read eight documents parsed again inside one tick, and
    twelve topics refitted as twelve, as nothing having happened.
    """
    _watching(monkeypatch, topics={"modelled": 12})
    context = build_sensor_context(instance=instance)
    orchestration.progress(context)

    _watching(monkeypatch, asked="refit", topics={"modelled": 12})
    result = orchestration.progress(
        build_sensor_context(cursor=context.cursor, instance=context.instance)
    )

    (event,) = result.asset_events
    assert event.asset_key.to_user_string() == "topics"


def test_a_stage_that_cannot_be_reached_costs_only_itself(
    monkeypatch, instance
) -> None:
    """One unreachable route must not lose the other four."""

    class Stub:
        """Answers for one stage and raises for the rest."""

        def __init__(self, *args, **kwargs) -> None:
            """Accepts whatever the sensor passes."""

        def status(self, stage: str) -> Queue:
            """Reports parsing and refuses everything else."""
            if stage != "parsing":
                raise ConnectionError("no route to the api")
            return Queue(working=False, rows={"parsed": 3})

    monkeypatch.setattr(orchestration, "Backend", Stub)

    result = orchestration.progress(build_sensor_context(instance=instance))

    assert [one.asset_key.to_user_string() for one in result.asset_events] == [
        "parsed_documents"
    ]


def test_it_watches_without_being_switched_on(monkeypatch) -> None:
    """Unlike the schedule and `arrivals`, which decide work should happen.

    A watcher nobody switched on is an asset graph that is quietly wrong.
    """
    assert orchestration.progress.default_status.value == "RUNNING"


# ── What the orchestrator did not start and could not do ───────────────────


def test_a_stage_that_failed_everything_is_reported_red(monkeypatch, instance) -> None:
    """The state worth interrupting somebody over, and the one it missed.

    Counting only what was produced reported silence for a stage that
    failed every row: nothing was produced, so nothing was materialised,
    so the asset read exactly as it did before the corpus arrived.
    """
    _watching(monkeypatch, parsing={"failed": 3})

    result = orchestration.progress(build_sensor_context(instance=instance))

    (check,) = result.asset_events
    assert check.asset_key.to_user_string() == "parsed_documents"
    assert check.check_name == "nothing_failed"
    assert not check.passed


def test_clearing_the_failures_turns_it_green_again(monkeypatch, instance) -> None:
    """Filed on a move in either direction, not only upwards.

    A check filed only when failures appear leaves the asset red until
    some Dagster run happens to evaluate it, which on a pipeline nobody
    drives from Dagster is never.
    """
    _watching(monkeypatch, parsing={"failed": 3})
    context = build_sensor_context(instance=instance)
    orchestration.progress(context)

    _watching(monkeypatch, parsing={"parsed": 3})
    result = orchestration.progress(
        build_sensor_context(cursor=context.cursor, instance=context.instance)
    )

    (materialised, check) = result.asset_events
    assert materialised.asset_key.to_user_string() == "parsed_documents"
    assert check.passed


def test_an_unchanged_failure_count_reports_nothing(monkeypatch, instance) -> None:
    """The same three failures every 30 seconds is not three checks a minute."""
    _watching(monkeypatch, parsing={"parsed": 8, "failed": 3})
    context = build_sensor_context(instance=instance)
    orchestration.progress(context)

    again = orchestration.progress(
        build_sensor_context(cursor=context.cursor, instance=context.instance)
    )

    assert isinstance(again, SkipReason)


def test_a_cursor_written_before_failures_were_watched_is_read(
    monkeypatch, instance
) -> None:
    """A deployment upgrading into this must not re-report its whole corpus.

    The cursor used to hold one number per stage and now holds two. Read
    as absent, the first tick after the upgrade would materialise every
    stage again for work it had already recorded.
    """
    _watching(monkeypatch, parsing={"parsed": 8})

    answer = orchestration.progress(
        build_sensor_context(cursor=json.dumps({"parsing": 8}), instance=instance)
    )

    assert isinstance(answer, SkipReason)


def test_a_cursor_written_before_the_worked_rows_were_watched_is_read(
    monkeypatch, instance
) -> None:
    """A pair per stage, with no digest to compare, is not a replacement."""
    _watching(monkeypatch, parsing={"parsed": 8})

    answer = orchestration.progress(
        build_sensor_context(cursor=json.dumps({"parsing": [8, 0]}), instance=instance)
    )

    assert isinstance(answer, SkipReason)


def test_every_stage_is_asked_at_once(monkeypatch, instance) -> None:
    """Six stages at the client's 15s timeout is 90s, and a tick is given 60.

    Asked one after another, a backend answering slowly switches the
    watcher off exactly when the asset graph most needs it.
    """
    held = 0.2

    class Slow:
        """Answers every stage, slowly."""

        def __init__(self, *args, **kwargs) -> None:
            """Accepts whatever the sensor passes."""

        def status(self, stage: str) -> Queue:
            """Answers after a wait, as a loaded backend would."""
            time.sleep(held)
            return Queue(working=False, rows={})

    monkeypatch.setattr(orchestration, "Backend", Slow)
    stages = len(orchestration.stages.ALL_STAGES)

    context = build_sensor_context(instance=instance)

    began = time.monotonic()
    orchestration.progress(context)
    took = time.monotonic() - began

    assert took < held * stages / 2


def test_a_corpus_run_going_records_its_own_work(monkeypatch, instance) -> None:
    """Its assets materialise themselves; a second event would double them."""
    _watching(monkeypatch, parsing={"parsed": 8})
    instance.add_run(
        DagsterRun(job_name="corpus", run_id="going", status=DagsterRunStatus.STARTED)
    )
    context = build_sensor_context(instance=instance)

    answer = orchestration.progress(context)

    assert isinstance(answer, SkipReason)
    assert json.loads(context.cursor)["parsing"][:2] == [8, 0], "absorbed, not owed"
