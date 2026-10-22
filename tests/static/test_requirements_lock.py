"""Every requirement a service declares is pinned in the lock it installs.

The same comparison backend/api/Dockerfile makes, run without a build: only
the lock is installed, so a dependency added to requirements.txt alone
produces a green image that fails on its first import.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: The directories holding a requirements.txt and the lock built from it.
SERVICES = (ROOT / "backend/api", ROOT / "frontend")

_DECLARED = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
_PINNED = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==")


def _folded(name: str) -> str:
    """Folds a distribution name to PEP 503 form."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _names(path: Path, pattern: re.Pattern[str]) -> set[str]:
    """Reads the distribution names a file lists, folded."""
    return {
        _folded(found.group(1))
        for line in path.read_text().splitlines()
        if (found := pattern.match(line.split("#")[0].strip()))
    }


@pytest.mark.parametrize("service", SERVICES, ids=lambda path: path.name)
def test_the_lock_pins_every_declared_requirement(service: Path) -> None:
    """The lock names everything requirements.txt does."""
    declared = _names(service / "requirements.txt", _DECLARED)
    assert declared, f"{service.name}/requirements.txt declares nothing"

    missing = declared - _names(service / "requirements.lock", _PINNED)
    assert not missing, (
        f"{service.name}/requirements.lock does not pin {', '.join(sorted(missing))}. "
        f"Run `make lock`."
    )


def test_the_orchestrator_image_pins_the_dagster_the_host_is_locked_to() -> None:
    """Both run against the one `dagster` database, and a version migrates it."""
    import tomllib

    locked = {
        _folded(one["name"]): one["version"]
        for one in tomllib.loads((ROOT / "poetry.lock").read_text())["package"]
    }
    declared = [
        line.split("#")[0].strip()
        for line in (ROOT / "orchestration/requirements.txt").read_text().splitlines()
    ]
    dagster = [line for line in declared if line.startswith(("dagster", "sqlalchemy"))]
    unpinned = [
        line
        for line in dagster
        if line.partition("==")[2] != locked.get(_folded(line.partition("==")[0]))
    ]

    assert any(line.startswith("sqlalchemy") for line in dagster), (
        "orchestration/requirements.txt leaves the SQLAlchemy dagster-postgres "
        "connects through to the resolver"
    )
    assert dagster, "orchestration/requirements.txt declares no dagster"
    assert not unpinned, unpinned


def test_dagsters_database_url_names_psycopg2() -> None:
    """SQLAlchemy 2.1 reads a bare `postgresql://` as psycopg 3, which Dagster's storage loses.

    dagster-postgres builds its URL from `postgres_db` and installs psycopg2;
    under psycopg 3 the webserver failed at start with "the connection is
    closed", and before psycopg 3 was installed with "No module named psycopg".
    """
    import yaml

    storage = yaml.safe_load((ROOT / "configs/dagster/dagster.yaml").read_text())[
        "storage"
    ]

    assert storage["postgres"]["postgres_db"]["scheme"] == "postgresql+psycopg2"


def _locked_versions() -> dict[str, set[str]]:
    """Every version poetry.lock holds per package, folded; a marker can split one."""
    import tomllib

    held: dict[str, set[str]] = {}
    for one in tomllib.loads((ROOT / "poetry.lock").read_text())["package"]:
        held.setdefault(_folded(one["name"]), set()).add(one["version"])
    return held


@pytest.mark.parametrize("service", SERVICES, ids=lambda path: path.name)
def test_an_image_lock_pins_what_the_host_lock_pins_for_every_shared_package(
    service: Path,
) -> None:
    """The suite runs poetry.lock's versions, so the image must run the same ones."""
    held = _locked_versions()
    differ = []
    for line in (service / "requirements.lock").read_text().splitlines():
        name, _, version = line.partition("==")
        if (
            _PINNED.match(line)
            and _folded(name) in held
            and version not in held[_folded(name)]
        ):
            differ.append(
                f"{name}: image {version}, host {sorted(held[_folded(name)])}"
            )
    assert not differ, (
        f"{service.name}/requirements.lock differs from poetry.lock: {differ}"
    )
