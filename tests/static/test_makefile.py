"""The Makefile, read through `make -n`, which prints a recipe and runs none.

The one command executed here is the worker guard on its own, against a
stand-in for compose.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: Every target that drains a stage's queue on the host, and the container
#: worker that drains the same queue.
DRAINS = {
    "parse": "parse-worker",
    "parse-rerun": "parse-worker",
    "chunk": "chunk-worker",
    "chunk-rerun": "chunk-worker",
    "extract": "extract-worker",
    "extract-rerun": "extract-worker",
    "topics": "topic-worker",
    "topics-discover": "topic-worker",
    "questions": "question-worker",
    "questions-rerun": "question-worker",
    "assess": "assess-worker",
    "assess-rerun": "assess-worker",
}


def printed(*arguments: str, **environment: str) -> list[str]:
    """What `make -n` prints for the arguments, one command per line."""
    inherited = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("MAKE") and name != "MFLAGS"
    }
    return subprocess.run(
        ["make", "-n", "--no-print-directory", *arguments],
        cwd=ROOT,
        env={**inherited, **environment},
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()


@pytest.mark.parametrize(("target", "worker"), DRAINS.items())
def test_a_host_drain_asks_whether_its_worker_runs_first(
    target: str, worker: str
) -> None:
    """The guard naming the stage's own worker comes before the drain."""
    lines = printed(target)
    guards = [at for at, line in enumerate(lines) if f"ps -q {worker} " in line]
    drains = [at for at, line in enumerate(lines) if "python -m" in line]

    assert guards and drains, lines
    assert guards[0] < drains[0], lines


@pytest.mark.parametrize(
    ("compose", "refused"),
    [
        ("echo 4f1c2a9e", True),
        ("true", False),
        ("echo 'cannot connect to the engine' >&2; exit 125", False),
        (None, False),
    ],
    ids=["worker-running", "stack-down", "engine-not-answering", "no-engine"],
)
def test_the_guard_refuses_only_while_the_worker_runs(
    tmp_path: Path, compose: str | None, refused: bool
) -> None:
    """And names the command that stops it, with the env files compose needs."""
    engine = tmp_path / "compose"
    if compose is not None:
        engine.write_text(f"#!/bin/sh\n{compose}\n")
        engine.chmod(0o755)
    (guard,) = [
        line
        for line in printed("extract", COMPOSE=str(engine))
        if f"{engine} --env-file" in line
    ]
    assert "python -m" not in guard and "poetry" not in guard, guard

    ran = subprocess.run(
        ["bash", "-c", guard], cwd=ROOT, capture_output=True, text=True, check=False
    )

    assert (ran.returncode != 0) is refused, ran
    if refused:
        assert (
            f"{engine} --env-file configs/env/deployment.env --env-file .env "
            "stop extract-worker"
        ) in ran.stdout + ran.stderr


@pytest.mark.parametrize(("given", "forced"), [((), False), (("FORCE=1",), True)])
def test_the_bridge_pass_is_forced_only_when_asked(
    given: tuple[str, ...], forced: bool
) -> None:
    """`FORCE=1` reaches it as `--force`."""
    (bridging,) = [
        line for line in printed("extract-bridge", *given) if "--bridge" in line
    ]

    assert ("--force" in bridging) is forced, bridging


def test_the_corpus_reports_the_topics_and_never_fits_them() -> None:
    """`topics-discover` is the refit, asked for on its own."""
    topics = [line for line in printed("corpus") if "topic_modelling.run" in line]

    assert topics, "the corpus says nothing about the topics"
    assert all(line.endswith("topic_modelling.run --status") for line in topics), topics


def test_a_command_line_value_is_named_for_the_store_to_give_way_to() -> None:
    """A stored row for a name given on the command line is not applied."""
    lines = printed("topics-discover", "TOPIC_PASSES=20")

    assert any('QA_COMMAND_LINE="TOPIC_PASSES"' in line for line in lines), lines
