"""The advisories `make audit` accepts, and for how long.

A list that only grows turns the audit into a list nobody reads, so every
entry names the lock it covers, why it is accepted and the date by which
somebody must look again; past that date the audit fails.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "configs/audit_ignores.py"
ACCEPTED = ROOT / "configs/audit-accepted.txt"


def _script():
    """The script `make audit` runs, loaded by path."""
    spec = importlib.util.spec_from_file_location("audit_ignores", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _entry(lock: str, ids: str, when: date, reason: str = "fixed upstream only") -> str:
    return f"{lock} | {ids} | {when.isoformat()} | {reason}\n"


TODAY = date(2026, 10, 25)
LATER = TODAY + timedelta(days=30)


def test_an_entry_names_the_ids_of_its_lock_and_of_all(tmp_path: Path) -> None:
    """One lock's advisory does not hide another's."""
    listed = tmp_path / "accepted.txt"
    listed.write_text(
        "# a comment\n\n"
        + _entry("api", "CVE-1 GHSA-2", LATER)
        + _entry("frontend", "CVE-3", LATER)
        + _entry("all", "CVE-4", LATER)
    )

    read = _script().ignores(listed.read_text(), "api", TODAY)

    assert read == ["CVE-1", "GHSA-2", "CVE-4"]


@pytest.mark.parametrize(
    "line",
    [
        "api | CVE-1 | 2026-10-24 | expired yesterday\n",
        "api | CVE-1 | 2026-10-25 | expires today\n",
        "api | CVE-1 | 2027-01-01 |\n",
        "api | CVE-1 | next spring | not a date\n",
        "somewhere | CVE-1 | 2027-01-01 | no such lock\n",
        "CVE-1 2027-01-01 no separators\n",
    ],
    ids=["expired", "today", "no-reason", "no-date", "no-lock", "malformed"],
)
def test_an_entry_that_cannot_be_trusted_fails_the_audit(line: str) -> None:
    """Expired, undated, unexplained, or not about a lock the audit reads."""
    with pytest.raises(SystemExit, match="audit-accepted"):
        _script().ignores(line, "api", TODAY)


def test_every_accepted_advisory_is_explained_and_not_yet_due() -> None:
    """The shipped list, today."""
    for lock in ("api", "frontend", "poetry"):
        assert _script().ignores(ACCEPTED.read_text(), lock, date.today()) is not None


def _poetry(tmp_path: Path) -> Path:
    """A poetry that runs python for real and records what pip-audit is given."""
    calls = tmp_path / "calls"
    poetry = tmp_path / "poetry"
    poetry.write_text(
        f'#!/bin/sh\ncase "$*" in "run python"*) shift 2; exec {sys.executable} "$@";; esac\n'
        f'echo "$*" >> {calls}\n'
    )
    poetry.chmod(0o755)
    return calls


def _audit(tmp_path: Path, listed: str) -> subprocess.CompletedProcess:
    accepted = tmp_path / "accepted.txt"
    accepted.write_text(listed)
    _poetry(tmp_path)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    env = {k: v for k, v in env.items() if not k.startswith("MAKE")}
    return subprocess.run(
        ["make", "--no-print-directory", "audit", f"AUDIT_ACCEPTED={accepted}"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_audit_passes_each_lock_its_accepted_ids(tmp_path: Path) -> None:
    """pip-audit is told to ignore them, lock by lock."""
    ran = _audit(
        tmp_path,
        _entry("api", "CVE-API", date.today() + timedelta(days=9))
        + _entry("frontend", "CVE-FRONT", date.today() + timedelta(days=9)),
    )
    calls = (tmp_path / "calls").read_text().splitlines()

    assert ran.returncode == 0, ran
    (api,) = [one for one in calls if "api.lock" in one]
    (front,) = [one for one in calls if "frontend/requirements.lock" in one]
    assert "--ignore-vuln CVE-API" in api and "CVE-FRONT" not in api
    assert "--ignore-vuln CVE-FRONT" in front and "CVE-API" not in front


def test_the_audit_fails_before_auditing_when_an_entry_is_due(tmp_path: Path) -> None:
    """An expired acceptance is a finding, and no pip-audit run hides it."""
    ran = _audit(tmp_path, _entry("all", "CVE-OLD", date.today() - timedelta(days=1)))

    assert ran.returncode != 0
    assert "audit-accepted" in ran.stderr
    assert not (tmp_path / "calls").exists()
