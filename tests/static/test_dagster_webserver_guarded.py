"""Every start of Dagster's webserver goes through `orchestration.serve`.

Dagster's own webserver answers a GraphQL mutation sent as a GET and takes
a write from any page the operator has open, so a web page could launch or stop
a pipeline run with the token the stack's code location holds. `serve.py`
refuses those. `make dagster-dev` ran plain `dagster dev`, which starts the
unguarded webserver on the host, and nothing checked that the next recipe, compose
command or image command did not do the same.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

#: A command that starts Dagster's webserver without `orchestration.serve`:
#: `dagster dev`, the `dagster-webserver` program, or its module. A service
#: or a container NAMED dagster-webserver is not one.
STARTS = re.compile(
    r"\bdagster\s+dev\b|\bdagster_webserver\b|\bdagster-webserver(?=\s+(?:-|\w+\.))"
)


def _files() -> list[Path]:
    found = [ROOT / "Makefile", *ROOT.glob("compose*.yaml")]
    found += [one for one in ROOT.rglob("Dockerfile") if "node_modules" not in str(one)]
    found += [*(ROOT / ".github" / "workflows").glob("*.yml")]
    found += [*(ROOT / "scripts").glob("*.sh"), *(ROOT / "configs").rglob("*.sh")]
    return sorted(found)


def _code(path: Path) -> list[tuple[int, str]]:
    """The lines that are not whole-line comments."""
    return [
        (number, line)
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if not line.lstrip().startswith("#")
    ]


def test_the_pattern_names_what_it_is_meant_to_catch() -> None:
    """A guard that matches nothing guards nothing."""
    for starter in (
        "poetry run dagster dev",
        "exec dagster-webserver -h 0.0.0.0 -p 3000",
        "python -m dagster_webserver.cli",
        "command: dagster-webserver -w workspace.yaml",
    ):
        assert STARTS.search(starter), starter
    for service in (
        "exec -T dagster-webserver dagster run list",
        "build api dagster-webserver",
        "dagster-webserver=dagster-webserver:3000",
        "python -m orchestration.serve -h 127.0.0.1 -p 3000",
    ):
        assert not STARTS.search(service), service


def test_no_recipe_compose_command_or_image_starts_the_unguarded_webserver() -> None:
    """Every start there is goes through `orchestration.serve`, which is not matched."""
    unguarded = [
        f"{path.relative_to(ROOT)}:{number}: {line.strip()}"
        for path in _files()
        for number, line in _code(path)
        if STARTS.search(line)
    ]

    assert unguarded == []


@pytest.mark.parametrize("name", ["compose.yaml"])
def test_the_webserver_service_runs_serve(name: str) -> None:
    """The one start there is: the compose service's command."""
    command = yaml.safe_load((ROOT / name).read_text())["services"][
        "dagster-webserver"
    ]["command"]

    assert "orchestration.serve" in " ".join(command)
