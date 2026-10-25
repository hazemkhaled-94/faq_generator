"""The advisory ids `make audit` accepts for each lock, from audit-accepted.txt.

Run by the Makefile as `python configs/audit_ignores.py <lock> [file]`, where
the lock is `api`, `frontend` or `poetry`, it prints the ids, one per line. It
stops, with nothing printed, on an entry that is malformed, names no reason, or
is due: an acceptance with no review date would be a permanent one.

Run as `python configs/audit_ignores.py --verdict <file> <dir>`, it reads what
pip-audit found in each lock, `<dir>/found.<lock>.json`, and prints every
advisory no entry accepts for that lock and every accepted id no lock it covers
reports any more, failing on either: a list that kept an id after its package
moved past it would hide that advisory if it came back.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Mapping
from datetime import date
from pathlib import Path

#: The locks the audit reads, and `all` for an advisory that holds in each.
LOCKS = ("api", "frontend", "poetry")
ALL = "all"

FILE = "configs/audit-accepted.txt"


def _entries(text: str, today: date) -> Iterator[tuple[str, str, list[str]]]:
    """Each entry as (where, lock, ids), checked.

    Raises:
        SystemExit: If an entry is not `lock | ids | review-by | reason`, names
            an unknown lock, has no reason, or its review-by date is today or
            past.
    """
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        where = f"{FILE}:{number}"
        parts = [one.strip() for one in line.split("|", 3)]
        if len(parts) != 4 or not all(parts):
            raise SystemExit(
                f"{where}: want `lock | ids | review-by | reason`, with a reason"
            )
        named, advisories, when, _ = parts
        if named not in (*LOCKS, ALL):
            raise SystemExit(f"{where}: lock {named!r} is not one of {LOCKS} or all")
        try:
            due = date.fromisoformat(when)
        except ValueError:
            raise SystemExit(f"{where}: review-by {when!r} is not YYYY-MM-DD") from None
        if due <= today:
            raise SystemExit(
                f"{where}: review-by {when} has come: read the advisories again, "
                "then renew the date or remove the entry"
            )
        yield where, named, advisories.split()


def ignores(text: str, lock: str, today: date) -> list[str]:
    """The ids accepted for one lock.

    Raises:
        SystemExit: As `_entries` does, on any entry that cannot be trusted.
    """
    return [
        one
        for _, named, ids in _entries(text, today)
        if named in (lock, ALL)
        for one in ids
    ]


def verdict(text: str, found: Mapping[str, dict], today: date) -> list[str]:
    """What fails the audit: findings no entry accepts, and stale acceptances.

    Args:
        text: The accepted list.
        found: pip-audit's JSON report for each lock.
        today: The date entries are due against.

    Returns:
        One line per advisory not accepted for its lock, and one per accepted
        id that no lock it covers reports.
    """
    entries = list(_entries(text, today))
    reported: dict[str, set[str]] = {}
    failing = []
    for lock in LOCKS:
        accepted = set(ignores(text, lock, today))
        reported[lock] = set()
        for package in found[lock].get("dependencies", []):
            for advisory in package.get("vulns", []):
                ids = {advisory["id"], *advisory.get("aliases", [])}
                reported[lock] |= ids
                if not ids & accepted:
                    fixed = ", ".join(advisory.get("fix_versions", [])) or "nothing"
                    failing.append(
                        f"{lock}: {package['name']} {package['version']} "
                        f"{' '.join(sorted(ids))}, fixed in {fixed}"
                    )
    for where, named, ids in entries:
        covered = LOCKS if named == ALL else (named,)
        for one in ids:
            if not any(one in reported[lock] for lock in covered):
                failing.append(
                    f"{where}: {one} is reported by no lock it is accepted for "
                    "any more: no longer needed, remove it"
                )
    return failing


if __name__ == "__main__":
    if sys.argv[1] == "--verdict":
        listed, reports = Path(sys.argv[2]), Path(sys.argv[3])
        found = {}
        for lock in LOCKS:
            report = reports / f"found.{lock}.json"
            if not report.exists():
                raise SystemExit(f"pip-audit wrote no report for the {lock} lock")
            found[lock] = json.loads(report.read_text())
        failing = verdict(listed.read_text(), found, date.today())
        print(*failing, sep="\n")
        raise SystemExit(1 if failing else 0)
    listed = Path(sys.argv[2] if len(sys.argv) > 2 else FILE)
    print(*ignores(listed.read_text(), sys.argv[1], date.today()), sep="\n")
