"""The host runner: what the go-live profile starts, refuses and runs.

With HOST_RUNNER=1 the model workers and Dagster stay stopped, `make all`,
`make pipeline` and `make auto` refuse, and the model stages run on the host
through `make corpus-hosted`. Read through `make -n` and, for the chain, real
`make` against stand-ins for poetry and the container engine.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
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
    stand_ins = tmp_path / "bin"
    stand_ins.mkdir(exist_ok=True)
    (stand_ins / "poetry").write_text(
        "#!/bin/sh\n"
        'echo "$APP_DB_NAME $HF_HUB_OFFLINE $SPEND_LEDGER $*" >> "$LOG"\n'
        'case "$*" in *"$FAIL"*) [ -n "$FAIL" ] && exit 3;; esac\n'
        'case "$*" in *topic_modelling*--ensure*) echo "x" >> "$SPEND_LEDGER";; esac\n'
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


def _make(project: Path, *arguments: str, **environment: str):
    inherited = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("MAKE") and name != "MFLAGS"
    }
    return subprocess.run(
        ["make", "--no-print-directory", *arguments],
        cwd=project,
        env={
            **inherited,
            "PATH": f"{project / 'bin'}:{inherited['PATH']}",
            "COMPOSE": str(project / "bin/compose"),
            "LOG": str(project / "drains.log"),
            **environment,
        },
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
    ledger = project / "logs/corpus-spend.usd"
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


def _waited(project: Path) -> None:
    for _ in range(200):
        if not (project / "logs/corpus-hosted.pid").exists():
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


def test_corpus_hosted_refuses_a_second_start(tmp_path: Path) -> None:
    """While the first one's pid is alive."""
    project = _project(tmp_path, env="HOST_RUNNER=1\nLLM_MODEL=azure/gpt-5.4\n")
    (project / "logs").mkdir()
    (project / "logs/corpus-hosted.pid").write_text(f"{os.getpid()}\n")

    ran = _make(project, "corpus-hosted")

    assert ran.returncode != 0
    assert "already running" in ran.stderr
    assert not _drained(project)


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


def test_corpus_hosted_refuses_without_the_go_live_profile(tmp_path: Path) -> None:
    """The container workers drain the queues otherwise."""
    project = _project(tmp_path, env="HOST_RUNNER=0\n")

    ran = _make(project, "corpus-hosted")

    assert ran.returncode != 0
    assert "HOST_RUNNER" in ran.stderr
    assert not _drained(project)


def test_the_supervisor_unit_is_documented() -> None:
    """A restart resumes the run: launchd or systemd runs `make corpus RESUME=1`."""
    text = (ROOT / "docs/operations.md").read_text()

    assert "make corpus RESUME=1" in text
    assert "launchd" in text and "systemd" in text
