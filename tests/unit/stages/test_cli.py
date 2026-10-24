"""The command line every pipeline stage shares."""

from __future__ import annotations

import pytest

from extraction.repository import PassageQueue
from preprocessing.parsing.repository import ParseQueue
from stages.cli import narrowing, parser

ACTIONS = {"status": "report", "start": "queue", "stop": "take back"}


def test_no_narrowing_asked_for_is_the_whole_queue() -> None:
    """`--only` is optional."""
    assert narrowing(ParseQueue(), None) is None


def test_a_scope_and_value_becomes_a_condition() -> None:
    """The same condition the route builds."""
    assert narrowing(ParseQueue(), "document=abc") is not None


@pytest.mark.parametrize("only", ["document", "", "justtext"])
def test_a_narrowing_without_a_value_is_refused(only: str) -> None:
    """The message names the form and the scopes this stage takes."""
    with pytest.raises(SystemExit, match="SCOPE=VALUE"):
        narrowing(ParseQueue(), only)


def test_a_scope_this_stage_does_not_take_is_refused() -> None:
    """Parsing queues over documents and knows nothing of a passage."""
    with pytest.raises(SystemExit, match="narrows to document"):
        narrowing(ParseQueue(), "passage=1")


def test_a_value_the_column_cannot_hold_is_refused() -> None:
    """Refused here rather than at the database."""
    with pytest.raises(SystemExit, match="not a valid passage"):
        narrowing(PassageQueue(), "passage=not-a-number")


def test_two_actions_in_one_command_are_refused() -> None:
    """They used to run only the first, silently."""
    with pytest.raises(SystemExit):
        parser("stage.run", ACTIONS).parse_args(["--start", "--stop"])


def test_each_action_is_a_flag_of_its_own() -> None:
    """The flags mirror the stage's HTTP surface one for one."""
    parsed = parser("stage.run", ACTIONS).parse_args(["--status"])

    assert parsed.status is True
    assert parsed.start is False
    assert parsed.only is None
    assert parsed.watch is False


def test_the_shared_flags_are_always_there() -> None:
    """`--only` and `--watch` are not a stage's to declare."""
    parsed = parser("stage.run", ACTIONS).parse_args(
        ["--only", "document=abc", "--watch"]
    )

    assert parsed.only == "document=abc"
    assert parsed.watch is True


# ── Tracing starts when the work does ──────────────────────────────────────


class _Empty:
    """A queue with nothing pending, for a drain that counts it before it starts."""

    def counts_by_status(self, within=None) -> dict:
        """Counts nothing."""
        return {}


def _queue_main(monkeypatch, *, refuse: Exception | None):
    """Runs one stage's command line, recording how telemetry was set up."""
    from stages import cli

    configured: list[dict] = []
    monkeypatch.setattr(
        cli.telemetry,
        "configure",
        lambda name, **kwargs: configured.append({"name": name, **kwargs}),
    )
    monkeypatch.setattr(cli.telemetry, "trace_engine", lambda engine: None)
    monkeypatch.setattr(cli, "engine", lambda: None)
    monkeypatch.setattr(cli, "run_id", lambda: "8f2c1e")
    monkeypatch.setattr(cli, "named_run", lambda: None)

    class _Service:
        """A service whose drain does nothing."""

        name = "stub"
        unit = "row"
        estimate = None
        failed = 0
        stalled = None

        def drain(self, stopping=None):
            """Drains nothing."""
            return 0

    def preflight() -> None:
        """Proves the model answers, or does not."""
        if refuse is not None:
            raise refuse

    cli.queue_main(
        name="extraction",
        module="extraction.run",
        repository=_Empty,
        build_service=_Service,
        argv=[],
        preflight=preflight,
    )
    return configured


def test_a_refused_preflight_installs_no_exporter(monkeypatch) -> None:
    """So a deployment that cannot work leaves no Phoenix project behind.

    The exporter is what creates a project, and a stage's first span is the
    preflight's own model call. A credential that has expired therefore
    left one project per attempt holding one failed call - and under
    `restart: unless-stopped`, one per restart.
    """
    configured = _queue_main(monkeypatch, refuse=RuntimeError("no credential"))

    assert [one["tracing"] for one in configured] == [False], (
        "tracing must stay uninstalled when the model will not answer"
    )


def test_a_rerun_whose_preflight_fails_resets_nothing(monkeypatch) -> None:
    """For assessment a reset deletes every metric and blanks every verdict.

    With an unreachable or unnamed judge, a rerun that reset first left
    nothing judged and nothing stored.
    """
    from stages import cli

    monkeypatch.setattr(cli.telemetry, "configure", lambda *_, **__: None)
    reset: list = []

    class _Queue:
        """A queue that records each reset."""

        def reset(self, within=None, *, trigger=None) -> int:
            """Records one reset."""
            reset.append(within)
            return 1

    def preflight() -> None:
        """Refuses, as `judge_model` does with no judge named."""
        raise ValueError("ASSESSMENT_JUDGE_MODEL names no model")

    exit_code = cli.queue_main(
        name="assessment",
        module="assessment.run",
        repository=_Queue,
        build_service=object,
        argv=["--rerun"],
        preflight=preflight,
    )

    assert exit_code == 1
    assert reset == [], "a refused preflight must leave every stored row as it was"


def test_a_drain_that_starts_installs_the_exporter(monkeypatch) -> None:
    """A process past the preflight is one that claims rows.

    Its spans are worth a project, so it installs the exporter then.
    """
    configured = _queue_main(monkeypatch, refuse=None)

    assert [one.get("tracing", True) for one in configured] == [False, True]
    assert configured[-1]["run"] == "8f2c1e"
    assert configured[-1]["named"] is None


# ── What a worker says while its model is down ─────────────────────────────


def _waiting(
    monkeypatch,
    *,
    failures: int,
    refusal: Exception | None = None,
    slept: list[float] | None = None,
):
    """Runs `_ready` as a watching worker whose model is down for a while."""
    from stages import cli

    clock = {"now": 0.0}

    def sleep(seconds: float) -> None:
        """Moves the clock on, and records the wait in `slept`."""
        clock["now"] += seconds
        if slept is not None:
            slept.append(seconds)

    monkeypatch.setattr(cli.time, "sleep", sleep)
    monkeypatch.setattr(cli.time, "monotonic", lambda: clock["now"])

    said: list[tuple[str, str]] = []
    for level in ("error", "warning", "info"):
        monkeypatch.setattr(
            cli.log,
            level,
            lambda msg, *a, _l=level: said.append((_l, msg % a if a else msg)),
        )

    tries = {"n": 0}

    def preflight() -> None:
        """Refuses `failures` times, then answers."""
        tries["n"] += 1
        if tries["n"] <= failures:
            raise refusal or RuntimeError("Connection refused")

    assert cli._ready("extraction", preflight, True) is True
    return said


def test_a_refused_setting_is_not_called_an_unreachable_model(monkeypatch) -> None:
    """An unnamed judge is a refusal, and the log reads as one."""
    said = _waiting(
        monkeypatch,
        failures=40,
        refusal=ValueError("ASSESSMENT_JUDGE_MODEL names no model"),
    )

    assert not [line for _, line in said if "cannot reach" in line]
    assert said[0][1].startswith("extraction refuses to claim work")
    assert "keep trying" in said[0][1]
    assert "ASSESSMENT_JUDGE_MODEL names no model" in said[0][1]
    assert "still refuses to claim work" in said[1][1]


def test_a_model_that_is_down_is_reported_once_and_then_counted(monkeypatch) -> None:
    """Not once per attempt.

    A worker polling every 60s wrote a line every 60s, and the client,
    instructor and a credential library wrote around it. How often it TRIES
    is unchanged; how often it says so is not.
    """
    said = _waiting(monkeypatch, failures=40)

    errors = [one for one in said if one[0] == "error"]
    warnings = [one for one in said if one[0] == "warning"]

    assert len(errors) == 1, "the reason is given once, in full"
    assert "Connection refused" in errors[0][1]
    assert len(warnings) < 10, "the repeats are counted, not narrated"


def test_the_first_line_says_it_will_keep_trying(monkeypatch) -> None:
    """So nobody restarts a worker that is already recovering by itself."""
    said = _waiting(monkeypatch, failures=3)

    assert "keep trying" in said[0][1]


def test_coming_back_is_worth_a_line(monkeypatch) -> None:
    """A recovery gets a line of its own.

    Otherwise the log goes quiet and a reader cannot tell a worker that
    started working from one that stopped complaining.
    """
    said = _waiting(monkeypatch, failures=3)

    assert said[-1][0] == "info"
    assert "reached its model" in said[-1][1]


def test_a_model_that_answers_at_once_says_nothing(monkeypatch) -> None:
    """The common case stays silent."""
    assert _waiting(monkeypatch, failures=0) == []


def test_a_model_that_will_not_answer_stops_a_drain(monkeypatch) -> None:
    """A one-off drain gives up, because a person holds the exit code.

    `stages.worker.watch` logs an exception and polls again, which is right
    for a drain that failed and wrong for a deployment that can never work:
    a worker with no usable credential would claim a topic every poll and
    fail it, emptying the queue into `failed` while reporting itself up.
    """
    from stages import cli

    slept: list[float] = []
    monkeypatch.setattr(cli.time, "sleep", slept.append)

    def refusing() -> None:
        """Refuses, as a model with no usable credential does."""
        raise RuntimeError("no credential")

    assert cli._ready("questions", refusing, False) is False
    assert slept == [], "a drain does not wait for a model"


def test_a_watching_worker_waits_for_its_model_rather_than_exiting(
    monkeypatch,
) -> None:
    """The process stays, and the model coming back is enough.

    Exiting costs a process, and under `restart: unless-stopped` a process
    is a restart and a fresh `run_id`.
    """
    slept: list[float] = []

    _waiting(monkeypatch, failures=3, slept=slept)

    assert slept == [5.0, 10.0, 20.0], "it backs off between attempts"


def test_the_wait_between_attempts_has_a_ceiling(monkeypatch) -> None:
    """A minute, so a model down overnight is not a log line every second."""
    slept: list[float] = []

    _waiting(monkeypatch, failures=8, slept=slept)

    assert max(slept) == 60.0, slept


# ── A worker rebuilt after a settings change ───────────────────────────────


def test_a_rebuilt_worker_claims_nothing_until_its_new_models_answer(
    monkeypatch,
) -> None:
    """A watching worker whose new settings name a model that does not answer.

    An unreachable phrasing judge abstains once per question, and the
    checker accepts on the gates that did not run.
    """
    from settings import store
    from stages import cli

    settings = {"version": "before"}
    monkeypatch.setattr(store, "current", lambda: settings["version"])
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(cli.telemetry, "configure", lambda *_, **__: None)
    monkeypatch.setattr(cli.telemetry, "trace_engine", lambda engine: None)
    monkeypatch.setattr(cli, "engine", lambda: None)
    watched: list = []
    monkeypatch.setattr(cli, "watch", lambda drain, seconds, *_: watched.append(drain))

    happened: list[str] = []
    refusals = {"left": 0}

    def preflight() -> None:
        """Refuses while the test says to, then answers."""
        if refusals["left"]:
            refusals["left"] -= 1
            happened.append("refused")
            raise RuntimeError("phrasing judge unreachable")
        happened.append("answered")

    class _Service:
        """A service that records each drain."""

        name = "stub"
        unit = "row"
        estimate = None
        failed = 0
        stalled = None

        def drain(self, stopping=None) -> int:
            """Records one drain."""
            happened.append("drained")
            return 0

    cli.queue_main(
        name="questions",
        module="question_generation.run",
        repository=PassageQueue,
        build_service=_Service,
        argv=["--watch"],
        preflight=preflight,
    )
    (drain,) = watched
    drain(lambda: False)
    settings["version"] = "after"
    refusals["left"] = 2
    drain(lambda: False)

    assert happened == [
        "answered",
        "drained",
        "refused",
        "refused",
        "answered",
        "drained",
    ]


# ── A narrowing that a drain would not keep to ─────────────────────────────


class _Narrowed:
    """A queue with rows pending inside and outside one topic."""

    def __init__(self) -> None:
        """Records each reset."""
        self.reset_within: list = []

    def narrowed(self, scope: str, value: str):
        """The condition one topic selects."""
        return f"{scope}={value}"

    def counts_by_status(self, within=None) -> dict[str, int]:
        """One pending row inside the topic, three in the whole queue."""
        return {"pending": 1 if within else 3}

    def reset(self, within=None, *, trigger=None) -> int:
        """Records one reset."""
        self.reset_within.append(within)
        return 1


def _narrowed_main(monkeypatch, argv: list[str]) -> _Narrowed:
    """Runs the questions command line over that queue; nothing may drain."""
    from stages import cli

    monkeypatch.setattr(cli.telemetry, "configure", lambda *_, **__: None)
    queue = _Narrowed()

    def built():
        """Nothing here may drain."""
        raise AssertionError("drained")

    with pytest.raises(SystemExit, match="--only"):
        cli.queue_main(
            name="questions",
            module="question_generation.run",
            repository=lambda: queue,
            build_service=built,
            argv=argv,
        )
    return queue


def test_a_narrowing_with_nothing_to_narrow_is_refused(monkeypatch) -> None:
    """A drain takes the whole queue, whatever `--only` says."""
    _narrowed_main(monkeypatch, ["--only", "topic=7"])


def test_a_narrowed_rerun_refuses_while_other_rows_are_queued(monkeypatch) -> None:
    """Its drain would take them too, under this run's name."""
    queue = _narrowed_main(monkeypatch, ["--rerun", "--only", "topic=7"])

    assert queue.reset_within == [], "refused before the reset"


def test_a_rebuilt_worker_records_its_prompts_again(monkeypatch) -> None:
    """A setting that moved can move the text a stage sends."""
    from settings import store
    from stages import cli

    settings = {"version": "before"}
    monkeypatch.setattr(store, "current", lambda: settings["version"])
    monkeypatch.setattr(cli.telemetry, "configure", lambda *_, **__: None)
    monkeypatch.setattr(cli.telemetry, "trace_engine", lambda engine: None)
    monkeypatch.setattr(cli, "engine", lambda: None)
    watched: list = []
    monkeypatch.setattr(cli, "watch", lambda drain, seconds, *_: watched.append(drain))
    recorded: list[str] = []

    class _Service:
        """A service that drains nothing."""

        name = "stub"
        unit = "row"
        estimate = None
        failed = 0
        stalled = None

        def drain(self, stopping=None) -> int:
            """Drains nothing."""
            return 0

    cli.queue_main(
        name="extraction",
        module="extraction.run",
        repository=PassageQueue,
        build_service=_Service,
        argv=["--watch"],
        prompts=lambda: recorded.append(settings["version"]) or 0,
    )
    (drain,) = watched
    drain(lambda: False)
    drain(lambda: False)
    settings["version"] = "after"
    drain(lambda: False)

    assert recorded == ["before", "after"]


# ── A rebuild that fails ───────────────────────────────────────────────────


class _Rebuilt:
    """A watching worker's drain whose settings move and whose builds fail."""

    def __init__(self, monkeypatch) -> None:
        """Settings at v1, a clock at 0, and a build that succeeds once."""
        from settings import store
        from stages import cli

        self.version = "v1"
        self.now = 0.0
        self.builds = 0
        self.preflights = 0
        self.failing = False
        self.drained: list[int] = []
        monkeypatch.setattr(store, "current", lambda: self.version)
        monkeypatch.setattr(cli.time, "monotonic", lambda: self.now)
        monkeypatch.setattr(cli.log, "exception", lambda *_, **__: None)
        self.drain = cli.reloading("extraction", self._build, self._preflight)

    def _preflight(self) -> None:
        """Answers, and counts."""
        self.preflights += 1

    def _build(self):
        """Builds a service that records its drains, or fails to build one."""
        self.builds += 1
        if self.failing:
            raise OSError("no such model")
        built = self.builds

        class _Service:
            def drain(_, stopping) -> int:
                self.drained.append(built)
                return 1

        return _Service()

    def __call__(self) -> int:
        """One poll."""
        return self.drain(lambda: False)


def test_a_build_that_fails_is_not_retried_every_poll(monkeypatch) -> None:
    """Every retry is a preflight model call and a build: thousands a day."""
    worker = _Rebuilt(monkeypatch)
    worker()
    worker.version, worker.failing = "v2", True

    polls = [worker() for _ in range(3)]

    assert polls == [0, 0, 0]
    assert (worker.builds, worker.preflights) == (2, 1)


def test_a_build_that_failed_is_tried_again_after_the_back_off(monkeypatch) -> None:
    """A model hub that was down for a minute is not a value that stands."""
    worker = _Rebuilt(monkeypatch)
    worker()
    worker.version, worker.failing = "v2", True
    worker()

    worker.now += 301
    worker.failing = False

    assert worker() == 1
    assert (worker.builds, worker.preflights) == (3, 2)


def test_the_back_off_doubles_while_the_build_keeps_failing(monkeypatch) -> None:
    """Up to an hour, so a value nobody corrects costs a build an hour."""
    worker = _Rebuilt(monkeypatch)
    worker()
    worker.version, worker.failing = "v2", True
    worker()
    worker.now += 5
    worker()

    worker.now += 5
    worker()

    assert worker.builds == 3
    worker.now += 5
    worker()
    assert worker.builds == 4


def test_a_change_after_a_failed_build_is_built_at_once(monkeypatch) -> None:
    """The back-off is on the value that failed, not on the next one."""
    worker = _Rebuilt(monkeypatch)
    worker()
    worker.version, worker.failing = "v2", True
    worker()

    worker.version, worker.failing = "v3", False

    assert worker() == 1
    assert worker.builds == 3


def test_a_failed_build_does_not_keep_working_on_the_old_settings(
    monkeypatch,
) -> None:
    """Nobody asked for them any more, even if the new ones will not build."""
    worker = _Rebuilt(monkeypatch)
    worker()
    worker.version, worker.failing = "v2", True

    worker()
    worker()
    worker.version = "v1"
    worker.failing = False
    worker()

    assert worker.drained == [1, 3]


def test_a_first_build_that_fails_once_is_serving_within_a_poll(monkeypatch) -> None:
    """A worker racing the object store or the model hub as the stack starts.

    Nothing about the settings is wrong, so the retry it was owed before
    the back-off existed, one poll later, is still the one it gets.
    """
    worker = _Rebuilt(monkeypatch)
    worker.failing = True
    worker()

    worker.now += 5
    worker.failing = False

    assert worker() == 1


def test_a_new_value_that_fails_backs_off_from_the_start(monkeypatch) -> None:
    """The back-off is the failing value's, not the worker's."""
    worker = _Rebuilt(monkeypatch)
    worker()
    worker.version, worker.failing = "v2", True
    for _ in range(5):
        worker()
        worker.now += 3600

    worker.version = "v3"
    worker()
    worker.now += 5
    worker.failing = False

    assert worker() == 1
