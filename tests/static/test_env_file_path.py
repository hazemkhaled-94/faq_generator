"""The secrets file may live outside the checkout.

`.env` beside the Makefile is the default, and ENV_FILE names another: host
commands source it and compose is handed it, so a go-live host can keep its
secrets where no sync client copies them and no `git clean` reaches.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from test_hosted_profile import ROOT, _project
from test_makefile import printed


def test_compose_is_handed_the_env_file_names() -> None:
    """The guard's own message shows the command a person would run."""
    lines = printed("extract", ENV_FILE="/srv/qa/secrets.env")

    assert any(
        "--env-file configs/env/deployment.env --env-file /srv/qa/secrets.env" in line
        for line in lines
    ), lines


def test_without_it_compose_reads_dot_env_as_before() -> None:
    """Nothing changes for a checkout that keeps its .env."""
    env = {k: v for k, v in os.environ.items() if k != "ENV_FILE"}
    ran = subprocess.run(
        ["make", "-n", "--no-print-directory", "extract"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "--env-file configs/env/deployment.env --env-file .env " in ran.stdout


def test_a_host_command_sources_the_file_outside_the_checkout(tmp_path: Path) -> None:
    """With no .env in the checkout at all."""
    project = _project(tmp_path)
    (project / ".env").unlink()
    elsewhere = tmp_path / "secrets dir"
    elsewhere.mkdir()
    (elsewhere / "prod.env").write_text("APP_DB_PASSWORD=moved\n")
    (project / "bin/poetry").write_text(
        '#!/bin/sh\necho "$APP_DB_PASSWORD" >> "$LOG"\n'
    )

    ran = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "topics-status",
            f"ENV_FILE={elsewhere}/prod.env",
        ],
        cwd=project,
        env={
            **os.environ,
            "PATH": f"{project / 'bin'}:{os.environ['PATH']}",
            "COMPOSE": str(project / "bin/compose"),
            "LOG": str(project / "drains.log"),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert ran.returncode == 0, ran.stderr
    assert (project / "drains.log").read_text().strip() == "moved"


def test_a_relative_file_is_read_from_the_checkout(tmp_path: Path) -> None:
    """`ENV_FILE=local.env` is not looked up on PATH, which `. local.env` would."""
    project = _project(tmp_path)
    (project / "local.env").write_text("APP_DB_PASSWORD=relative\n")
    (project / "bin/poetry").write_text(
        '#!/bin/sh\necho "$APP_DB_PASSWORD" >> "$LOG"\n'
    )

    ran = subprocess.run(
        ["make", "--no-print-directory", "topics-status", "ENV_FILE=local.env"],
        cwd=project,
        env={
            **os.environ,
            "PATH": f"{project / 'bin'}:{os.environ['PATH']}",
            "COMPOSE": str(project / "bin/compose"),
            "LOG": str(project / "drains.log"),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert ran.returncode == 0, ran.stderr
    assert (project / "drains.log").read_text().strip() == "relative"


def test_the_runbook_says_where_the_secrets_go_and_that_the_keys_are_rotated() -> None:
    """Moving the checkout is the user's, so the page is what carries it."""
    text = " ".join((ROOT / "docs/operations.md").read_text().split())

    assert "ENV_FILE=/etc/qa/secrets.env" in text
    assert "Rotate every key after the move" in text
    assert "no sync client watches" in text
