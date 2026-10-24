"""The go-live profile refuses what would start the orchestrator.

`make all`, `make pipeline` and `make auto` refuse, naming `make
corpus-hosted`, and Dagster sits under a profile the go-live `make up` leaves
off.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from test_hosted_profile import REFUSAL, ROOT, _compose, _project
from test_makefile import printed

@pytest.mark.parametrize("service", ["dagster-webserver", "dagster-daemon"])
def test_dagster_sits_under_the_orchestrated_profile(service: str) -> None:
    """The orchestrated path is the development one."""
    assert _compose()[service]["profiles"] == ["orchestrated"]


def _guard(target: str) -> str:
    """The one line `make -n` prints for a target that names the host runner."""
    joined = "\n".join(printed(target)).replace("\\\n", "")
    (line, *_) = [one for one in joined.splitlines() if "corpus-hosted" in one]
    return line


@pytest.mark.parametrize("target", ["all", "pipeline", "auto"])
@pytest.mark.parametrize(("flag", "refused"), [("1", True), ("0", False), ("", False)])
def test_the_go_live_profile_refuses_the_orchestrated_targets(
    tmp_path: Path, target: str, flag: str, refused: bool
) -> None:
    """Naming the host runner, with the sentence the routes answer."""
    project = _project(tmp_path, env=f"HOST_RUNNER={flag}\n")

    ran = subprocess.run(
        ["bash", "-c", _guard(target)],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )

    assert (ran.returncode != 0) is refused, ran
    if refused:
        assert REFUSAL in ran.stderr


def test_all_refuses_before_it_brings_anything_up() -> None:
    """The guard is the first thing `all` does."""
    lines = printed("all")
    guard = next(at for at, line in enumerate(lines) if "corpus-hosted" in line)
    up = next(at for at, line in enumerate(lines) if line.endswith(" up -d"))

    assert guard < up


def test_the_route_and_the_makefile_give_one_sentence() -> None:
    """A page, a client and a terminal read the same words."""
    assert REFUSAL in (ROOT / "Makefile").read_text()
    assert REFUSAL in (ROOT / "backend/api/routes/pipeline.py").read_text()
