"""The host runner: what the go-live profile starts, refuses and runs.

With HOST_RUNNER=1 the model workers and Dagster stay stopped, `make all`,
`make pipeline` and `make auto` refuse, and the model stages run on the host
through `make corpus-hosted`. Read through `make -n` and, for the chain, real
`make` against stand-ins for poetry and the container engine.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from test_makefile import printed

ROOT = Path(__file__).resolve().parents[2]
REFUSAL = "the go-live profile runs the model stages through make corpus-hosted"
MODEL_WORKERS = ("extract-worker", "topic-worker", "question-worker", "assess-worker")


def _compose() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]


# ── compose ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("worker", MODEL_WORKERS)
def test_a_model_worker_sits_under_the_local_models_profile(worker: str) -> None:
    """So the go-live `make up` leaves it stopped."""
    assert _compose()[worker]["profiles"] == ["local-models"]


@pytest.mark.parametrize(
    "service", ["parse-worker", "chunk-worker", "api", "streamlit"]
)
def test_what_the_go_live_profile_runs_has_no_profile(service: str) -> None:
    """Parsing and chunking call no model."""
    assert "profiles" not in _compose()[service]


def test_what_the_go_live_profile_refuses_beside_is_its_two_profiles() -> None:
    """OFF_PROFILE is every service under local-models or orchestrated."""
    (named,) = re.findall(
        r"^OFF_PROFILE = (.*)$", (ROOT / "Makefile").read_text(), re.MULTILINE
    )
    profiled = {
        name
        for name, service in _compose().items()
        if {"local-models", "orchestrated"} & set(service.get("profiles", []))
    }

    assert set(named.split()) == profiled


def test_the_example_turns_the_host_runner_on_and_backend_env_does_not_set_it() -> None:
    """backend.env's default leaves today's development behaviour."""
    live = dict(
        re.findall(
            r"^([A-Z][A-Z0-9_]*)=(.*)$",
            (ROOT / ".env.example").read_text(),
            re.MULTILINE,
        )
    )
    backend = (ROOT / "configs/env/backend.env").read_text()

    assert live["HOST_RUNNER"] == "1"
    assert not re.search(r"^HOST_RUNNER=", backend, re.MULTILINE)


# ── make ───────────────────────────────────────────────────────────────────


def _project(
    tmp_path: Path, *, env: str = "", given: str = "", running: tuple[str, ...] = ()
) -> Path:
    """A directory the Makefile can run in, with env files and stand-ins on PATH.

    `running` names the containers the compose stand-in reports as up.
    """
    for name, text in {
        "configs/env/backend.env": "",
        "configs/env/deployment.env": "APP_DB_NAME=qa_scratch\nBACKEND_PORT=8000\n",
        ".env": env,
    }.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    (tmp_path / "Makefile").symlink_to(ROOT / "Makefile")
    (tmp_path / "scripts").symlink_to(ROOT / "scripts")
    stand_ins = tmp_path / "bin"
    stand_ins.mkdir(exist_ok=True)
    (stand_ins / "poetry").write_text(
        "#!/bin/sh\n"
        'echo "$APP_DB_NAME $HF_HUB_OFFLINE $SPEND_LEDGER $*" >> "$LOG"\n'
        'case "$*" in *"$FAIL"*) [ -n "$FAIL" ] && exit "${CODE:-3}";; esac\n'
        'case "$*" in *topic_modelling*--ensure*) echo "x" >> "$SPEND_LEDGER";; esac\n'
        # A long extraction drain, stopped as drain_once stops one: 75 on SIGTERM.
        # Its sleep ignores the TERM the group gets, so the wait is always the
        # one interrupted and the handler always runs; a sleep that died first
        # let sh return from the wait and exit before it ran, now and then.
        'case "$*" in *"extraction.run") [ -n "$SLOW" ] && {\n'
        '  (trap "" TERM; exec sleep "$SLOW") & held=$!\n'
        "  trap 'kill -KILL $held; echo stopped >> \"$LOG.stopped\"; exit 75' TERM\n"
        '  echo started >> "$LOG.slow"\n'
        "  wait $held; };; esac\n"
        "exit 0\n"
    )
    (stand_ins / "compose").write_text(
        "#!/bin/sh\n"
        + "".join(
            f'case "$*" in *"ps -q {one}"*) echo 0123abcd;; esac\n' for one in running
        )
    )
    for one in stand_ins.iterdir():
        one.chmod(0o755)
    return tmp_path


def _environment(project: Path, **environment: str) -> dict[str, str]:
    inherited = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("MAKE") and name != "MFLAGS"
    }
    return {
        **inherited,
        "PATH": f"{project / 'bin'}:{inherited['PATH']}",
        "COMPOSE": str(project / "bin/compose"),
        "LOG": str(project / "drains.log"),
        **environment,
    }


def _make(project: Path, *arguments: str, **environment: str):
    return subprocess.run(
        ["make", "--no-print-directory", *arguments],
        cwd=project,
        env=_environment(project, **environment),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_up_starts_everything_in_development_and_the_go_live_set_otherwise() -> None:
    """HOST_RUNNER decides which profiles `up` enables."""
    (line,) = [one for one in printed("up") if one.endswith(" up -d")]

    assert "COMPOSE_PROFILES" in line


def test_every_other_compose_command_sees_every_profile() -> None:
    """So down, ps, logs and stop reach a container whichever profile started it."""
    assert "export COMPOSE_PROFILES ?= *" in (ROOT / "Makefile").read_text()


# ── the chain ──────────────────────────────────────────────────────────────

STAGES = [
    "preprocessing.parsing.run --start",
    "preprocessing.parsing.run",
    "preprocessing.chunking.run --start",
    "preprocessing.chunking.run",
    "extraction.run --start",
    "extraction.run",
    "extraction.run --digests",
    "extraction.run --bridge",
    "question_generation.run --start",
    "question_generation.run",
    "assessment.run --start",
    "assessment.run",
]


def _drained(project: Path) -> list[str]:
    log = project / "drains.log"
    return log.read_text().splitlines() if log.exists() else []


def test_the_corpus_runs_the_stages_in_order() -> None:
    """The order a document moves through them, and the digests after extraction."""
    lines = printed("corpus")
    at = {stage: next(i for i, l in enumerate(lines) if stage in l) for stage in STAGES}

    assert [at[stage] for stage in STAGES] == sorted(at.values())


def test_the_corpus_says_its_database_and_pins_what_every_drain_reads(
    tmp_path: Path,
) -> None:
    """The name printed is the name every drain gets, and none reaches the Hub."""
    project = _project(tmp_path)

    ran = _make(project, "corpus")

    assert ran.returncode == 0, ran.stderr
    assert "database qa_scratch" in ran.stdout + ran.stderr
    drains = _drained(project)
    assert drains, ran.stderr
    assert all(line.startswith("qa_scratch 1 ") for line in drains), drains[:3]


@pytest.mark.parametrize("target", ["corpus", "corpus-hosted"])
def test_a_database_exported_in_the_shell_is_the_one_announced_and_used(
    tmp_path: Path, target: str
) -> None:
    """As every host command's OVERRIDE takes it: never deployment.env's instead."""
    project = _project(tmp_path, env="HOST_RUNNER=1\nLLM_MODEL=azure/gpt-5.4\n")

    ran = _make(project, target, APP_DB_NAME="qa_shell")

    assert ran.returncode == 0, ran.stderr
    if target == "corpus-hosted":
        _waited(project)
        said = (project / "logs/corpus-hosted.log").read_text()
    else:
        said = ran.stdout + ran.stderr
    assert "corpus: database qa_shell" in said, said
    drains = _drained(project)
    assert drains and {line.split()[0] for line in drains} == {"qa_shell"}, drains


@pytest.mark.parametrize("target", ["corpus", "corpus-hosted"])
def test_a_database_given_on_the_command_line_is_the_one_announced_and_used(
    tmp_path: Path, target: str
) -> None:
    """It beats the files, as every host command's OVERRIDE makes it."""
    project = _project(tmp_path, env="HOST_RUNNER=1\nLLM_MODEL=azure/gpt-5.4\n")

    ran = _make(project, target, "APP_DB_NAME=qa_other")

    assert ran.returncode == 0, ran.stderr
    if target == "corpus-hosted":
        _waited(project)
        said = (project / "logs/corpus-hosted.log").read_text()
    else:
        said = ran.stdout + ran.stderr
    assert "corpus: database qa_other" in said, said
    drains = _drained(project)
    assert drains and {line.split()[0] for line in drains} == {"qa_other"}, drains


def test_the_corpus_hands_every_drain_one_spend_ledger(tmp_path: Path) -> None:
    """The tally is per process, so the run's spend is carried between them."""
    project = _project(tmp_path)

    _make(project, "corpus")

    ledgers = {line.split()[2] for line in _drained(project)}
    assert len(ledgers) == 1 and ledgers != {""}, ledgers


def test_a_fresh_corpus_starts_a_fresh_ledger_and_a_resume_keeps_it(
    tmp_path: Path,
) -> None:
    """A second run on another day is not held to the first one's spend."""
    project = _project(tmp_path)
    ledger = project / LEDGER
    ledger.parent.mkdir()
    ledger.write_text("4.5\n")

    _make(project, "corpus", "RESUME=1")
    kept = ledger.read_text()
    _make(project, "corpus")

    assert kept.startswith("4.5\n")
    assert not ledger.read_text().startswith("4.5\n")


@pytest.mark.parametrize(
    "failing", ["extraction.run --start", "extraction.run --digests"]
)
def test_a_drain_that_exits_non_zero_stops_the_chain(
    tmp_path: Path, failing: str
) -> None:
    """3 for a failed row, 75 for a stopped drain: neither lets the next stage run."""
    project = _project(tmp_path)

    ran = _make(project, "corpus", FAIL=failing)

    assert ran.returncode != 0
    drained = "\n".join(_drained(project))
    assert failing in drained
    assert "question_generation" not in drained, drained


def test_a_stage_whose_worker_runs_is_waited_for_and_not_drained_beside_it(
    tmp_path: Path,
) -> None:
    """The go-live `make up` starts the parse and chunk workers: the chain waits for each."""
    project = _project(tmp_path, running=("parse-worker", "chunk-worker"))

    ran = _make(project, "corpus")

    assert ran.returncode == 0, ran.stderr
    drained = [line.split(" python -m ")[-1] for line in _drained(project)]
    assert "preprocessing.parsing.run --wait" in drained, drained
    assert "preprocessing.chunking.run --wait" in drained, drained
    assert "preprocessing.parsing.run" not in drained, "no host drain beside the worker"
    assert "preprocessing.chunking.run" not in drained
    assert "extraction.run" in drained, "a stage whose worker is down is drained here"
    assert "assessment.run" in drained, drained


def test_rows_the_worker_failed_while_the_chain_waited_stop_it(tmp_path: Path) -> None:
    """The wait exits as a drain would: 3 when rows failed, and the next stage waits."""
    project = _project(tmp_path, running=("parse-worker",))

    ran = _make(project, "corpus", FAIL="preprocessing.parsing.run --wait")

    assert ran.returncode != 0
    assert "chunking" not in "\n".join(_drained(project))


def test_a_resume_returns_failed_rows_to_the_queue_first(tmp_path: Path) -> None:
    """A killed drain leaves rows failed, and the lease sweep gave them up."""
    project = _project(tmp_path)

    _make(project, "corpus", "RESUME=1")

    drained = _drained(project)
    retries = [i for i, l in enumerate(drained) if " --retry" in l]
    first = next(i for i, l in enumerate(drained) if " --start" in l)
    assert len(retries) == 6 and max(retries) < first, drained


# ── corpus-hosted ──────────────────────────────────────────────────────────


def _waited(project: Path, runs: int = 1) -> None:
    """Until the runner has said `runs` times that its run ended."""
    log = project / "logs/corpus-hosted.log"
    for _ in range(300):
        if log.exists() and log.read_text().count("the run ended") >= runs:
            return
        time.sleep(0.1)
    raise AssertionError("the hosted run never finished")


def test_corpus_hosted_runs_the_corpus_detached_with_a_pid_file_and_a_log(
    tmp_path: Path,
) -> None:
    """Back at once; the log holds the chain."""
    project = _project(tmp_path, env="HOST_RUNNER=1\nLLM_MODEL=azure/gpt-5.4\n")

    ran = _make(project, "corpus-hosted")

    assert ran.returncode == 0, ran.stderr
    _waited(project)
    assert (
        "corpus: database qa_scratch"
        in (project / "logs/corpus-hosted.log").read_text()
    )
    assert _drained(project)


def _started(pid: int) -> str:
    """A process's start time, as the runner records its run's leader."""
    return subprocess.run(
        ["ps", "-o", "lstart=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_corpus_hosted_refuses_a_second_start(tmp_path: Path) -> None:
    """While the process group the first one recorded, its leader as started, lives."""
    project = _project(tmp_path, env="HOST_RUNNER=1\nLLM_MODEL=azure/gpt-5.4\n")
    (project / "logs").mkdir()
    running = subprocess.Popen(["sleep", "60"], start_new_session=True)
    (project / "logs/corpus-hosted.pid").write_text(
        f"{running.pid} qa_scratch\n{_started(running.pid)}\n"
    )

    try:
        ran = _make(project, "corpus-hosted")
    finally:
        running.kill()
        running.wait()

    assert ran.returncode != 0
    assert "already running" in ran.stderr
    assert not _drained(project)


GO_LIVE = "HOST_RUNNER=1\nLLM_MODEL=azure/gpt-5.4\n"

#: The spend ledger of the database the stand-in files name: one a database.
LEDGER = "logs/corpus-spend-qa_scratch.usd"


def _until(done: Callable[[], bool], seconds: float = 20) -> None:
    end = time.time() + seconds
    while not done():
        if time.time() > end:
            raise AssertionError("it never happened")
        time.sleep(0.1)


def _extracting(project: Path) -> bool:
    """The slow extraction drain runs, with its stop handler in place."""
    return (project / "drains.log.slow").exists()


def _alive(group: int) -> bool:
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return False
    return True


def test_killing_the_make_at_the_head_of_the_run_leaves_a_start_refused(
    tmp_path: Path,
) -> None:
    """The pid file holds the run's process group: its drain outlives a kill -9 of make."""
    project = _project(tmp_path, env=GO_LIVE)
    assert _make(project, "corpus-hosted", SLOW="6").returncode == 0
    _until(lambda: _extracting(project))
    group, database = (project / "logs/corpus-hosted.pid").read_text().split()[:2]

    os.kill(int(group), signal.SIGKILL)
    second = _make(project, "corpus-hosted")

    assert database == "qa_scratch"
    assert second.returncode != 0
    assert "already running" in second.stderr
    _until(lambda: not _alive(int(group)))


def test_the_stop_signals_the_whole_run_and_its_drain_stops_as_asked(
    tmp_path: Path,
) -> None:
    """TERM to the group reaches the drain, which exits 75; nothing after it runs."""
    project = _project(tmp_path, env=GO_LIVE)
    ledger = project / LEDGER
    assert _make(project, "corpus-hosted", SLOW="60").returncode == 0
    _until(lambda: _extracting(project))
    group = int((project / "logs/corpus-hosted.pid").read_text().split()[0])
    ledger.write_text("3.5\n")

    stopped = _make(project, "corpus-hosted-stop", "HOSTED_GRACE=20")

    assert stopped.returncode == 0, stopped.stderr
    assert (project / "drains.log.stopped").exists(), "the drain was told to stop"
    assert not _alive(group)
    assert "question_generation" not in "\n".join(_drained(project))
    assert ledger.read_text() == "3.5\n", "the stop keeps the spend"


@pytest.mark.parametrize("code", ["75", "3"])
def test_a_stopped_run_keeps_its_record_and_its_spend_and_the_next_start_resumes(
    tmp_path: Path, code: str
) -> None:
    """75 at the cap or 3 for failed rows: the restart counts the spend so far."""
    project = _project(tmp_path, env=GO_LIVE)
    pidfile = project / "logs/corpus-hosted.pid"
    ledger = project / LEDGER

    first = _make(
        project,
        "corpus-hosted",
        "SPEND_CAP=50",
        FAIL="extraction.run --digests",
        CODE=code,
    )
    assert first.returncode == 0, first.stderr
    _waited(project)
    assert pidfile.read_text().split()[1] == "qa_scratch", "the run's identity is kept"
    ledger.write_text("45.0\n")  # what the stopped run had spent

    again = _make(project, "corpus-hosted", "SPEND_CAP=50")
    assert again.returncode == 0, again.stderr
    _waited(project, runs=2)

    assert any(" --retry" in line for line in _drained(project)), "a resume"
    assert ledger.read_text().startswith("45.0\n"), "the 45.0 still counts"
    assert not pidfile.exists(), "a run that finished leaves no record"


def test_a_fresh_corpus_on_another_database_keeps_a_stopped_run_s_spend(
    tmp_path: Path,
) -> None:
    """Each database has its ledger: qa_b's run never empties qa_scratch's."""
    project = _project(tmp_path, env=GO_LIVE)
    ledger = project / LEDGER
    _make(project, "corpus-hosted", FAIL="extraction.run --digests", CODE="75")
    _waited(project)
    ledger.write_text("45.0\n")

    other = _make(project, "corpus", "APP_DB_NAME=qa_b")
    again = _make(project, "corpus-hosted")
    _waited(project, runs=2)

    assert other.returncode == 0, other.stderr
    assert again.returncode == 0, again.stderr
    assert (project / "logs/corpus-spend-qa_b.usd").exists()
    assert ledger.read_text().startswith("45.0\n"), "the resume still counts 45.0"


def test_a_fresh_corpus_beside_a_stopped_hosted_run_of_its_database_is_refused(
    tmp_path: Path,
) -> None:
    """It would start the stopped run's spend again; resume it or RESET=1."""
    project = _project(tmp_path, env=GO_LIVE)
    ledger = project / LEDGER
    _make(project, "corpus-hosted", FAIL="extraction.run --digests", CODE="75")
    _waited(project)
    ledger.write_text("45.0\n")
    (project / "drains.log").unlink()

    fresh = _make(project, "corpus")

    assert fresh.returncode != 0
    assert "RESET=1" in fresh.stderr and "make corpus-hosted" in fresh.stderr
    assert ledger.read_text() == "45.0\n"
    assert not _drained(project)


def test_make_corpus_beside_a_live_hosted_run_of_its_database_is_refused(
    tmp_path: Path,
) -> None:
    """A second chain on its queues would overwrite its spend."""
    project = _project(tmp_path, env=GO_LIVE)
    assert _make(project, "corpus-hosted", SLOW="60").returncode == 0
    _until(lambda: _extracting(project))
    ledger = project / LEDGER
    ledger.write_text("3.5\n")

    try:
        beside = _make(project, "corpus", "RESUME=1")
    finally:
        _make(project, "corpus-hosted-stop", "HOSTED_GRACE=20")

    assert beside.returncode != 0
    assert "is going" in beside.stderr, beside.stderr
    assert ledger.read_text() == "3.5\n"


def test_reset_starts_a_fresh_run_after_a_stop(tmp_path: Path) -> None:
    """The one way to start the count again besides a run that finished."""
    project = _project(tmp_path, env=GO_LIVE)
    ledger = project / LEDGER
    _make(project, "corpus-hosted", FAIL="extraction.run --digests", CODE="75")
    _waited(project)
    ledger.write_text("45.0\n")
    (project / "drains.log").unlink()

    again = _make(project, "corpus-hosted", "RESET=1")
    assert again.returncode == 0, again.stderr
    _waited(project, runs=2)

    assert not any(" --retry" in line for line in _drained(project))
    assert not ledger.read_text().startswith("45.0")


def test_a_stopped_run_is_not_resumed_on_another_database(tmp_path: Path) -> None:
    """Its ledger and its failed rows are another database's."""
    project = _project(tmp_path, env=GO_LIVE)
    _make(project, "corpus-hosted", FAIL="extraction.run --digests", CODE="75")
    _waited(project)
    (project / "drains.log").unlink()

    other = _make(project, "corpus-hosted", "APP_DB_NAME=qa_other")

    assert other.returncode != 0
    assert "qa_scratch" in other.stderr and "RESET=1" in other.stderr
    assert not _drained(project), "refused before the preflight"


# ── the runner a supervisor runs ───────────────────────────────────────────


def _run(project: Path, *arguments: str, **environment: str):
    """scripts/corpus-hosted.sh in the foreground, as a supervisor's unit runs it."""
    return subprocess.run(
        ["scripts/corpus-hosted.sh", *arguments],
        cwd=project,
        env=_environment(project, **environment),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


@pytest.mark.parametrize(
    ("failing", "code", "exit"),
    [
        ("", "", 0),
        ("extraction.run --digests", "75", 75),
        ("question_generation.run --balance", "75", 75),
        ("extraction.run --start", "3", 3),
        ("assessment.run", "3", 3),
        ("extraction.run --digests", "1", 1),
    ],
    ids=["finished", "stopped", "stopped-late", "failed-rows", "failed-late", "crash"],
)
def test_the_runner_exits_with_the_stage_code_and_not_make_s(
    tmp_path: Path, failing: str, code: str, exit: int
) -> None:
    """0 finished, 75 stopped, 3 failed rows: a supervisor restarts only a crash."""
    project = _project(tmp_path, env=GO_LIVE)

    ran = _run(project, FAIL=failing, CODE=code)

    assert ran.returncode == exit, (ran.stdout, ran.stderr)


@pytest.mark.parametrize(("code", "exit"), [("75", 0), ("3", 0), ("1", 1)])
def test_for_launchd_a_stop_the_operator_clears_exits_0(
    tmp_path: Path, code: str, exit: int
) -> None:
    """The daemon restarts on any code but 0, and a stop at SPEND_CAP is not to be restarted."""
    project = _project(tmp_path, env=GO_LIVE)

    ran = _run(project, "--zero-on-stop", FAIL="extraction.run --digests", CODE=code)

    assert ran.returncode == exit, (ran.stdout, ran.stderr)
    assert (project / "logs/corpus-hosted.pid").exists(), "the run is still resumable"


def test_a_runner_told_to_stop_stops_its_run_and_exits_75(tmp_path: Path) -> None:
    """A supervisor's TERM reaches the drain once, through the run's group."""
    project = _project(tmp_path, env=GO_LIVE)
    runner = subprocess.Popen(
        ["scripts/corpus-hosted.sh"],
        cwd=project,
        env=_environment(project, SLOW="60"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _until(lambda: _extracting(project))
        runner.terminate()
        code = runner.wait(timeout=60)
    finally:
        runner.kill()

    assert code == 75
    assert (project / "drains.log.stopped").read_text() == "stopped\n"
    assert "question_generation" not in "\n".join(_drained(project))


def test_a_stop_with_no_run_going_says_so(tmp_path: Path) -> None:
    """And signals nothing."""
    project = _project(tmp_path, env=GO_LIVE)

    stopped = _make(project, "corpus-hosted-stop")

    assert stopped.returncode == 0
    assert "no hosted run" in stopped.stdout


def test_corpus_hosted_resumes_after_a_run_that_was_killed(tmp_path: Path) -> None:
    """A pid file nobody holds is a run that died, and the drains resume by lease."""
    project = _project(tmp_path, env="HOST_RUNNER=1\nLLM_MODEL=azure/gpt-5.4\n")
    (project / "logs").mkdir()
    (project / "logs/corpus-hosted.pid").write_text("999999\n")

    ran = _make(project, "corpus-hosted")

    assert ran.returncode == 0, ran.stderr
    _waited(project)
    assert any(" --retry" in line for line in _drained(project))


def test_corpus_hosted_runs_on_the_go_live_profile_whose_up_starts_two_workers(
    tmp_path: Path,
) -> None:
    """parse-worker and chunk-worker run there; the hosted run reaches the model stages."""
    project = _project(
        tmp_path,
        env="HOST_RUNNER=1\nLLM_MODEL=azure/gpt-5.4\n",
        running=("parse-worker", "chunk-worker"),
    )

    ran = _make(project, "corpus-hosted", "SPEND_CAP=1")

    assert ran.returncode == 0, ran.stderr
    _waited(project)
    log = (project / "logs/corpus-hosted.log").read_text()
    assert "is running and drains this queue" not in log, log
    assert any("assessment.run" in line for line in _drained(project)), log


@pytest.mark.parametrize(
    "worker", ["extract-worker", "question-worker", "assess-worker", "dagster-daemon"]
)
def test_a_model_worker_left_up_refuses_the_hosted_run_before_any_drain(
    tmp_path: Path, worker: str
) -> None:
    """One left from development calls Ollama: it is refused, never waited for."""
    project = _project(
        tmp_path,
        env="HOST_RUNNER=1\nLLM_MODEL=azure/gpt-5.4\n",
        running=("parse-worker", "chunk-worker", worker),
    )

    ran = _make(project, "corpus-hosted")

    assert ran.returncode != 0
    assert worker in ran.stderr and f"stop {worker}" in ran.stderr, ran.stderr
    assert not _drained(project), "refused before the preflight and any drain"


@pytest.mark.parametrize(
    "worker", ["extract-worker", "question-worker", "assess-worker"]
)
def test_the_chain_refuses_beside_a_model_worker_and_never_waits_for_it(
    tmp_path: Path, worker: str
) -> None:
    """Only the parse and chunk workers are waited for."""
    project = _project(tmp_path, running=(worker,))

    ran = _make(project, "corpus")

    assert ran.returncode != 0
    assert f"{worker} is running and drains this queue" in ran.stderr
    assert not any("--wait" in line for line in _drained(project))


@pytest.mark.parametrize(
    ("running", "said"),
    [
        (("extract-worker",), "extract-worker up on the go-live profile"),
        ((), "the model workers and Dagster are stopped"),
    ],
)
def test_the_doctor_says_the_model_workers_are_stopped_only_after_it_looked(
    tmp_path: Path, running: tuple[str, ...], said: str
) -> None:
    """On the go-live profile a model worker up is a failure, named with its stop."""
    project = _project(
        tmp_path, env="HOST_RUNNER=1\nLLM_MODEL=azure/gpt-5.4\n", running=running
    )

    ran = _make(project, "doctor", CONTAINER="true")

    assert said in ran.stdout, ran.stdout
    if running:
        assert ran.returncode != 0
        assert "stop extract-worker" in ran.stdout


def test_corpus_hosted_refuses_without_the_go_live_profile(tmp_path: Path) -> None:
    """The container workers drain the queues otherwise."""
    project = _project(tmp_path, env="HOST_RUNNER=0\n")

    ran = _make(project, "corpus-hosted")

    assert ran.returncode != 0
    assert "HOST_RUNNER" in ran.stderr
    assert not _drained(project)


def test_the_runner_parses_in_the_bash_a_mac_ships() -> None:
    """/bin/bash on macOS is 3.2, and a supervisor runs the script with it."""
    script = ROOT / "scripts/corpus-hosted.sh"
    parsed = subprocess.run(
        ["/bin/bash", "-n", str(script)], capture_output=True, text=True, check=False
    )

    assert parsed.returncode == 0, parsed.stderr
    assert os.access(script, os.X_OK)
    assert script.read_text().startswith("#!/bin/bash\n")


def _unit(fence: str) -> str:
    """The block of docs/operations.md's "After a stop" fenced as `fence`."""
    text = (ROOT / "docs/operations.md").read_text()
    section = text[text.index("### After a stop") :]
    (block,) = re.findall(
        rf"```{fence}\n(.*?)```", section[: section.index("\n## ")], re.DOTALL
    )
    return block


def test_the_systemd_unit_restarts_only_a_crash() -> None:
    """Not a stop at SPEND_CAP (75) nor failed rows or a refusal (3), and starts at boot."""
    import configparser

    unit = configparser.ConfigParser(strict=False, interpolation=None)
    unit.optionxform = str  # type: ignore[assignment]
    unit.read_string(_unit("ini"))
    service = unit["Service"]

    assert service["ExecStart"].split()[0].endswith("/scripts/corpus-hosted.sh")
    assert "RESUME=1" not in service["ExecStart"], "the runner resumes by itself"
    assert service["Restart"] == "on-failure"
    assert set(service["RestartPreventExitStatus"].split()) == {"3", "75"}
    assert service["User"]
    assert service["Environment"].startswith("PATH=")
    assert service["KillMode"] == "mixed", "the stop reaches the drain once"
    assert int(service["TimeoutStopSec"]) > 300
    assert unit["Install"]["WantedBy"] == "multi-user.target"


def test_the_launchd_daemon_restarts_only_a_crash() -> None:
    """A LaunchDaemon, run as a user with a PATH, its stops turned into 0."""
    import plistlib

    block = _unit("xml")
    job = plistlib.loads(block[block.index("<?xml") :].encode())

    assert "/Library/LaunchDaemons/" in block
    assert job["UserName"]
    assert job["EnvironmentVariables"]["PATH"]
    assert job["ProgramArguments"][0].endswith("/scripts/corpus-hosted.sh")
    assert job["ProgramArguments"][1] == "--zero-on-stop"
    assert job["KeepAlive"] == {"SuccessfulExit": False}
    assert job["RunAtLoad"] is True
    assert job["ExitTimeOut"] > 300


def test_docling_weights_host_fills_the_host_cache_and_not_the_volume() -> None:
    """What make doctor and the hosted preflight read on the go-live host."""
    hosted = printed("docling-weights", "HOST=1")
    volume = printed("docling-weights")

    assert any(
        "poetry run python -m preprocessing.parsing.weights" in line for line in hosted
    ), hosted
    assert not any("compose" in line and " run " in line for line in hosted), hosted
    assert any("run --rm --no-deps chunk-worker" in line for line in volume), volume


@pytest.mark.parametrize(
    "record",
    ["{pid} qa_scratch\n", "{pid} qa_scratch\nThu Jan  1 00:00:00 1970\n"],
    ids=["no-start-time", "another-start-time"],
)
def test_a_group_number_reused_by_another_process_is_not_the_run(
    tmp_path: Path, record: str
) -> None:
    """The stop signals nothing of it, and a start resumes rather than refuses."""
    project = _project(tmp_path, env=GO_LIVE)
    (project / "logs").mkdir()
    unrelated = subprocess.Popen(["sleep", "60"], start_new_session=True)
    (project / "logs/corpus-hosted.pid").write_text(record.format(pid=unrelated.pid))

    try:
        stopped = _make(project, "corpus-hosted-stop", "HOSTED_GRACE=3")
        alive_after_stop = unrelated.poll() is None
        started = _make(project, "corpus-hosted")
        _waited(project)
    finally:
        unrelated.kill()
        unrelated.wait()

    assert "no hosted run" in stopped.stdout, stopped.stdout
    assert alive_after_stop, "the stop signalled an unrelated group"
    assert started.returncode == 0, started.stderr
    assert any(" --retry" in line for line in _drained(project)), "a resume"


# ── What the supervised runner proves, as make corpus-hosted does ──────────


def test_a_supervisor_started_without_a_database_records_the_one_corpus_resolves(
    tmp_path: Path,
) -> None:
    """Never a record naming no database, which a start on another would resume."""
    project = _project(tmp_path, env=GO_LIVE)

    ran = _run(project, FAIL="extraction.run --digests", CODE="75")

    assert ran.returncode == 75, (ran.stdout, ran.stderr)
    record = (project / "logs/corpus-hosted.pid").read_text().splitlines()[0]
    assert record.split()[1:] == ["qa_scratch"]
    assert {line.split()[0] for line in _drained(project)} == {"qa_scratch"}


def test_the_supervised_runner_refuses_without_the_go_live_profile(
    tmp_path: Path,
) -> None:
    """The check make corpus-hosted makes, before any drain: 3, which no unit restarts."""
    project = _project(tmp_path, env="HOST_RUNNER=0\n")

    ran = _run(project)

    assert ran.returncode == 3
    assert "HOST_RUNNER" in ran.stderr
    assert not _drained(project)


def test_the_supervised_runner_runs_the_preflight_before_the_first_drain(
    tmp_path: Path,
) -> None:
    """The split, the password and the cache, as make corpus-hosted asks."""
    project = _project(tmp_path, env=GO_LIVE)

    assert _run(project).returncode == 0

    drained = _drained(project)
    assert "from api.doctor import preflight" in drained[0], drained[:2]
    assert sum("preflight" in line for line in drained) == 1


def test_corpus_hosted_asks_the_preflight_once(tmp_path: Path) -> None:
    """Checked before it detaches, and not again by the run it detached."""
    project = _project(tmp_path, env=GO_LIVE)

    assert _make(project, "corpus-hosted").returncode == 0
    _waited(project)

    assert sum("preflight" in line for line in _drained(project)) == 1
