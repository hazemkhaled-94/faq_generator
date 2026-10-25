"""The advisories `make audit` accepts, and for how long.

A list that only grows turns the audit into a list nobody reads, so every
entry names the lock it covers, why it is accepted and the date by which
somebody must look again; past that date the audit fails.
"""

from __future__ import annotations

import importlib.util
import json
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


#: Which lock each file pip-audit is handed is, by its name.
_LOCK_FILES = {
    "api.lock": "api",
    "requirements.lock": "frontend",
    "poetry.lock": "poetry",
}


def _poetry(tmp_path: Path) -> Path:
    """A poetry that runs python for real and stands in for pip-audit.

    It records what pip-audit is given and writes, where `--output` says, the
    findings `found.<lock>.json` holds for that lock, or none.
    """
    calls = tmp_path / "calls"
    poetry = tmp_path / "poetry"
    names = " ".join(f"{name}) lock={lock};;" for name, lock in _LOCK_FILES.items())
    poetry.write_text(
        f'#!/bin/sh\ncase "$*" in "run python"*) shift 2; exec {sys.executable} "$@";; esac\n'
        f'echo "$*" >> {calls}\n'
        'out=""; read=""\n'
        'while [ $# -gt 0 ]; do case "$1" in --output) out=$2;; -r) read=$2;; esac; shift; done\n'
        f'case "$(basename "$read")" in {names} esac\n'
        f'cp "{tmp_path}/found.$lock.json" "$out" 2>/dev/null '
        '|| echo \'{"dependencies": [], "fixes": []}\' > "$out"\n'
    )
    poetry.chmod(0o755)
    return calls


def _found(tmp_path: Path, lock: str, *ids: tuple[str, ...]) -> None:
    """What pip-audit reports for one lock: Pillow, one advisory per id group."""
    findings = {
        "dependencies": [
            {
                "name": "pillow",
                "version": "12.3.0",
                "vulns": [
                    {"id": one[0], "fix_versions": ["13.0.0"], "aliases": list(one[1:])}
                    for one in ids
                ],
            }
        ],
        "fixes": [],
    }
    (tmp_path / f"found.{lock}.json").write_text(json.dumps(findings))


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
    """An advisory accepted for its lock, by its id or an alias, is no finding."""
    _found(tmp_path, "api", ("GHSA-api", "CVE-API"))
    _found(tmp_path, "frontend", ("CVE-FRONT",))
    ran = _audit(
        tmp_path,
        _entry("api", "CVE-API", date.today() + timedelta(days=9))
        + _entry("frontend", "CVE-FRONT", date.today() + timedelta(days=9)),
    )
    calls = (tmp_path / "calls").read_text().splitlines()

    assert ran.returncode == 0, ran
    assert len(calls) == 3, "one pip-audit run per lock"
    assert all("--format json" in one for one in calls)


def test_an_advisory_accepted_for_another_lock_is_a_finding(tmp_path: Path) -> None:
    """One lock's acceptance does not hide the same id in another."""
    _found(tmp_path, "api", ("CVE-FRONT",))
    _found(tmp_path, "frontend", ("CVE-FRONT",))
    ran = _audit(
        tmp_path, _entry("frontend", "CVE-FRONT", date.today() + timedelta(days=9))
    )

    assert ran.returncode != 0
    assert "api: pillow 12.3.0 CVE-FRONT" in ran.stdout


def test_an_accepted_id_no_lock_reports_any_more_fails_the_audit(
    tmp_path: Path,
) -> None:
    """A stale acceptance is named, so the list cannot hide what it no longer needs.

    Pillow moved past its advisory: the id appears in no lock it was accepted for.
    """
    _found(tmp_path, "api", ("CVE-KEPT",))
    ran = _audit(
        tmp_path,
        _entry("all", "CVE-KEPT CVE-GONE", date.today() + timedelta(days=9))
        + _entry("api", "CVE-FRONT-ONLY", date.today() + timedelta(days=9)),
    )

    stale = [line for line in ran.stdout.splitlines() if "no longer needed" in line]

    assert ran.returncode != 0
    assert [line.split(": ")[1].split()[0] for line in stale] == [
        "CVE-GONE",
        "CVE-FRONT-ONLY",
    ]


def test_the_audit_fails_before_auditing_when_an_entry_is_due(tmp_path: Path) -> None:
    """An expired acceptance is a finding, and no pip-audit run hides it."""
    ran = _audit(tmp_path, _entry("all", "CVE-OLD", date.today() - timedelta(days=1)))

    assert ran.returncode != 0
    assert "audit-accepted" in ran.stderr
    assert not (tmp_path / "calls").exists()
