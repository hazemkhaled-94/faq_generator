"""Deletes the Dagster runs one database launched, and no other database's.

`dagster run wipe` takes every run the instance remembers, and the instance
is one for every database on the stack. The corpus job tags each run with
the database it drives; this takes those. A run with no such tag - one from
before the tag, or launched from the UI - is left, and `make dagster-wipe
ALL_DATABASES=1` is what takes everything.

Run inside the webserver container, which holds the instance:

    python -m orchestration.wipe
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from dagster import DagsterInstance, RunsFilter

import telemetry
from telemetry import pipeline

log = logging.getLogger(__name__)


def wipe_runs(instance: Any, database: str) -> int:
    """Deletes every run tagged with the database, and says how many went."""
    runs = instance.get_runs(filters=RunsFilter(tags={"database": database}))
    for run in runs:
        instance.delete_run(run.run_id)
    return len(runs)


def main() -> int:
    """Wipes this database's runs.

    Returns:
        0, or 2 when the process names no database, which it must to know
        whose runs are its own.
    """
    telemetry.configure("orchestration-wipe")
    database = pipeline.database()
    if not database:
        log.error("APP_DB_NAME is unset, so no run can be called this database's")
        return 2
    with DagsterInstance.get() as instance:
        log.info("deleted %d run(s) tagged %s", wipe_runs(instance, database), database)
    return 0


if __name__ == "__main__":
    sys.exit(main())
