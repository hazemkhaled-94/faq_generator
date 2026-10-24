"""`make upgrade` takes a deployment to this checkout's code in the order that works.

Check the engine has the room, build, prune what the build orphaned, stop the
workers, migrate, start. A build that runs out of room half way leaves a stack
that will not start, so the check comes first and a failed build stops the rest.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from test_hosted_profile import _project


def _engine(project: Path, free: str, fail_on: str = "") -> None:
    """Stand-ins for the container engine and compose, recording every call."""
    (project / "bin/container").write_text(
        "#!/bin/sh\n"
        'echo "container $*" >> "$LOG"\n'
        'case "$*" in "machine ssh"*) echo "  ' + free + 'G";; esac\n'
    )
    (project / "bin/compose").write_text(
        "#!/bin/sh\n"
        'echo "compose $*" >> "$LOG"\n'
        'case "$*" in *' + (fail_on or "NEVER") + "*) exit 1;; esac\n"
    )
    for one in ("container", "compose"):
        (project / "bin" / one).chmod(0o755)
    # What `make up` would otherwise generate with openssl.
    (project / "certs").mkdir(exist_ok=True)
    for name in ("elasticsearch.crt", "ca.key", "elasticsearch.key"):
        (project / "certs" / name).write_text("x")


def _upgrade(project: Path, **environment: str):
    return subprocess.run(
        [
            "make",
            "--no-print-directory",
            "upgrade",
            *[f"{k}={v}" for k, v in environment.items()],
        ],
        cwd=project,
        env={
            **os.environ,
            "PATH": f"{project / 'bin'}:{os.environ['PATH']}",
            "COMPOSE": str(project / "bin/compose"),
            "CONTAINER": str(project / "bin/container"),
            "LOG": str(project / "calls.log"),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _calls(project: Path) -> list[str]:
    log = project / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def _at(calls: list[str], needle: str) -> int:
    return next(i for i, line in enumerate(calls) if needle in line)


def test_an_engine_short_of_room_refuses_before_building(tmp_path: Path) -> None:
    """Naming what it has and what the budget is."""
    project = _project(tmp_path)
    _engine(project, "5")

    ran = _upgrade(project)

    assert ran.returncode != 0
    assert "5 GB" in ran.stderr and "20 GB" in ran.stderr
    assert not [line for line in _calls(project) if line.startswith("compose")]


def test_the_budget_is_stated_and_can_be_changed(tmp_path: Path) -> None:
    """UPGRADE_FREE_GB, for a machine that knows better."""
    project = _project(tmp_path)
    _engine(project, "5")
    (project / "bin/poetry").write_text('#!/bin/sh\necho "poetry $*" >> "$LOG"\n')

    ran = _upgrade(project, UPGRADE_FREE_GB="4")

    assert ran.returncode == 0, ran.stderr


def test_the_steps_run_in_order(tmp_path: Path) -> None:
    """Check, build, prune, stop the workers, migrate, start."""
    project = _project(tmp_path)
    _engine(project, "80")
    (project / "bin/poetry").write_text('#!/bin/sh\necho "poetry $*" >> "$LOG"\n')

    ran = _upgrade(project)

    assert ran.returncode == 0, ran.stderr
    calls = _calls(project)
    order = [
        _at(calls, "machine ssh"),
        _at(
            calls, "compose --env-file configs/env/deployment.env --env-file .env build"
        ),
        _at(calls, "image prune"),
        _at(calls, " stop "),
        _at(calls, "alembic upgrade head"),
        _at(calls, " up -d"),
    ]
    assert order == sorted(order), calls
    stopped = calls[_at(calls, " stop ")]
    for worker in ("parse", "chunk", "extract", "topic", "question", "assess"):
        assert f"{worker}-worker" in stopped


def test_a_failed_build_stops_everything_after_it(tmp_path: Path) -> None:
    """No prune, no stop, no migration, no start on an image that did not build."""
    project = _project(tmp_path)
    _engine(project, "80", fail_on="build")

    ran = _upgrade(project)

    assert ran.returncode != 0
    calls = _calls(project)
    for later in ("image prune", " stop ", "alembic", " up -d"):
        assert not [line for line in calls if later in line], (later, calls)


def test_the_operations_guide_calls_it(tmp_path: Path) -> None:
    """The upgrade section says to run it, not six commands."""
    text = (Path(__file__).resolve().parents[2] / "docs/operations.md").read_text()

    assert "make upgrade" in text


@pytest.mark.parametrize("target", ["upgrade"])
def test_the_target_is_phony(target: str) -> None:
    """A file of its name would otherwise make make skip it."""
    makefile = (Path(__file__).resolve().parents[2] / "Makefile").read_text()

    assert f" {target} " in makefile.split(".PHONY:", 1)[1].split("\n\n", 1)[0] + " "
