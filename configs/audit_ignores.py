"""The advisory ids `make audit` may ignore for one lock, from audit-accepted.txt.

Run by the Makefile as `python configs/audit_ignores.py <lock> [file]`, where
the lock is `api`, `frontend` or `poetry`. Prints the ids, one per line. It stops, with
nothing printed, on an entry that is malformed, names no reason, or is due: an
acceptance with no review date would be a permanent one.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

#: The locks the audit reads, and `all` for an advisory that holds in each.
LOCKS = ("api", "frontend", "poetry")
ALL = "all"

FILE = "configs/audit-accepted.txt"


def ignores(text: str, lock: str, today: date) -> list[str]:
    """The ids accepted for one lock.

    Raises:
        SystemExit: If an entry is not `lock | ids | review-by | reason`, names
            an unknown lock, has no reason, or its review-by date is today or
            past.
    """
    ids: list[str] = []
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
        if named in (lock, ALL):
            ids.extend(advisories.split())
    return ids


if __name__ == "__main__":
    listed = Path(sys.argv[2] if len(sys.argv) > 2 else FILE)
    print(*ignores(listed.read_text(), sys.argv[1], date.today()), sep="\n")
