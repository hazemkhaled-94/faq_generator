"""compose.yaml's profiles: the go-live set, and what each optional service is under.

With no profile named, compose starts eleven services: the database, the object
store, the api, the parse and chunk workers, the page and Phoenix. Everything
else sits under a profile a deployment turns on, and `make wipe` and `make
doctor` skip the steps of a service that is not running.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml
from test_hosted_profile import _project
from test_makefile import printed

ROOT = Path(__file__).resolve().parents[2]

GO_LIVE_SET = {
    "postgres",
    "seaweedfs-master",
    "seaweedfs-volume",
    "seaweedfs-volume2",
    "seaweedfs-filer",
    "seaweedfs-s3",
    "api",
    "parse-worker",
    "chunk-worker",
    "streamlit",
    "phoenix",
}

PROFILES = {
    "argilla": "review",
    "redis": "review",
    "elasticsearch": "review",
    "filebeat": "logs",
    "grafana": "logs",
    "adminer": "tools",
    "extract-worker": "local-models",
    "topic-worker": "local-models",
    "question-worker": "local-models",
    "assess-worker": "local-models",
    "dagster-webserver": "orchestrated",
    "dagster-daemon": "orchestrated",
}


def _services() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]


def test_with_no_profile_compose_lists_the_eleven_go_live_services() -> None:
    """No more and no fewer."""
    bare = {name for name, one in _services().items() if not one.get("profiles")}

    assert bare == GO_LIVE_SET


@pytest.mark.parametrize(("service", "profile"), sorted(PROFILES.items()))
def test_each_optional_service_names_its_one_profile(
    service: str, profile: str
) -> None:
    """Argilla and its stores, the logs, the browser, the model workers, Dagster."""
    assert _services()[service]["profiles"] == [profile]


def test_every_service_is_in_the_go_live_set_or_has_a_profile_here() -> None:
    """A service added without either is a decision nobody took."""
    assert set(_services()) == GO_LIVE_SET | set(PROFILES)


def _run(project: Path, line: str, compose_prints: str):
    (project / "bin/compose").write_text(f"#!/bin/sh\n{compose_prints}\n")
    (project / "bin/compose").chmod(0o755)
    return subprocess.run(
        ["bash", "-c", line],
        cwd=project,
        env={
            **os.environ,
            "PATH": f"{project / 'bin'}:{os.environ['PATH']}",
            "COMPOSE": str(project / "bin/compose"),
            "LOG": str(project / "calls.log"),
        },
        capture_output=True,
        text=True,
        check=False,
    )


def _wipe_line(project: Path, holding: str, also: str, *arguments: str) -> str:
    """The wipe's line holding all three, printed with the stand-in as compose."""
    joined = "\n".join(
        printed("wipe", *arguments, COMPOSE=str(project / "bin/compose"))
    ).replace("\\\n", "")
    (line,) = [
        one
        for one in joined.splitlines()
        if holding in one and "ps -q" in one and also in one
    ]
    return line


@pytest.mark.parametrize(
    ("service", "step"),
    [
        ("argilla", "review-delete"),
        ("elasticsearch", "logs-wipe"),
        ("dagster-webserver", "dagster-wipe"),
    ],
)
def test_wipe_skips_a_service_that_is_not_running_and_says_so(
    tmp_path: Path, service: str, step: str
) -> None:
    """Its profile is off, so there is nothing of its to delete and the wipe goes on."""
    project = _project(tmp_path)
    line = _wipe_line(project, f"ps -q {service}", f"make {step}")

    ran = _run(project, line, "")

    assert ran.returncode == 0, ran
    assert f"{service} is not running" in ran.stdout
    assert f"{step} is skipped by the wipe" in ran.stdout
    assert not (project / "drains.log").exists()


@pytest.mark.parametrize(
    ("service", "step"),
    [("argilla", "review-delete"), ("dagster-webserver", "dagster-wipe")],
)
def test_wipe_runs_the_step_of_a_service_that_is_up(
    tmp_path: Path, service: str, step: str
) -> None:
    """The same line, with a container answering."""
    project = _project(tmp_path)
    (project / "configs/env/review.env").write_text("")
    (project / "bin/poetry").write_text('#!/bin/sh\necho "poetry $*" >> "$LOG"\n')
    line = _wipe_line(project, f"ps -q {service}", f"make {step}")

    ran = _run(project, line, 'echo "4f1c2a9e"')

    assert ran.returncode == 0, ran
    assert "is not running" not in ran.stdout


def test_a_wipe_of_every_database_still_empties_the_log_files_without_elasticsearch(
    tmp_path: Path,
) -> None:
    """The stream is the review profile's; the files are everyone's."""
    project = _project(tmp_path)
    (project / "logs").mkdir()
    (project / "logs/api.log").write_text("before\n")
    line = _wipe_line(project, "ps -q elasticsearch", "truncate", "ALL_DATABASES=1")

    ran = _run(project, line, "")

    assert ran.returncode == 0, ran
    assert (project / "logs/api.log").read_text() == ""


def test_a_wipe_of_one_database_leaves_the_shared_log_files_without_elasticsearch(
    tmp_path: Path,
) -> None:
    """Every database writes to the same files, so one database's wipe keeps them."""
    project = _project(tmp_path)
    (project / "logs").mkdir()
    (project / "logs/api.log").write_text("before\n")
    line = _wipe_line(project, "ps -q elasticsearch", "truncate")

    ran = _run(project, line, "")

    assert ran.returncode == 0, ran
    assert (project / "logs/api.log").read_text() == "before\n"


def test_doctor_does_not_check_the_containers_model_where_the_workers_are_stopped() -> (
    None
):
    """HOST_RUNNER is the go-live profile, which has none to call it."""
    recipe = (
        (ROOT / "Makefile").read_text().split("\ndoctor:\n", 1)[1].split("\n\n", 1)[0]
    )

    guard = recipe.index("HOST_RUNNER")
    assert guard < recipe.index("OLLAMA_CONTAINER_URL")


def test_the_operations_guide_lists_the_profiles() -> None:
    """Where an operator finds what each one starts."""
    text = (ROOT / "docs/operations.md").read_text()

    for profile in ("review", "logs", "tools", "local-models", "orchestrated"):
        assert f"`{profile}`" in text, profile
