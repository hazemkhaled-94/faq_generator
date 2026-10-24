"""Command-line entry point for reading and changing settings.

Every flag is the same operation as the route beside it under /settings:

  python -m settings.run --service topics                GET  /settings/topics
  python -m settings.run --service topics --set K=V      PATCH
  python -m settings.run --service topics --unset K      PATCH, with a null

One command for all eight services, `platform` included. The Makefile wraps
it per service.

Nothing here runs a stage. A setting written reaches a worker at that
worker once its queue is empty - not per row, so a drain under way works the
rest of its queue under the old values - and what a change staled is printed.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable

import telemetry
from database.qa_generator import engine
from settings import catalog, changes
from settings.store import Settings

log = logging.getLogger(__name__)


def parser() -> argparse.ArgumentParser:
    """Builds the argument parser."""
    built = argparse.ArgumentParser(prog="python -m settings.run")
    built.add_argument(
        "--service",
        required=True,
        choices=sorted({one.service for one in catalog.SETTINGS}),
        help="which service to read or change. One per command.",
    )
    built.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        dest="written",
        help="change one setting. Repeatable; a command is written together "
        "and one refusal refuses all of it.",
    )
    built.add_argument(
        "--unset",
        action="append",
        default=[],
        metavar="NAME",
        dest="cleared",
        help="return one setting to whatever configs/env/backend.env or .env "
        "says. Repeatable.",
    )
    return built


def proposed(written: list[str], cleared: list[str]) -> dict[str, str | None]:
    """Reads the changes a command asked for.

    Raises:
        SystemExit: If a `--set` carries no `=`, or a name is given twice.
    """
    values: dict[str, str | None] = {}
    for entry in written:
        name, sign, value = entry.partition("=")
        if not sign:
            raise SystemExit(f"--set takes NAME=VALUE; {entry!r} has no '='")
        values[name.strip()] = value.strip()
    for name in cleared:
        if name.strip() in values:
            raise SystemExit(
                f"{name.strip()} is both set and unset in one command, and "
                f"only one of those can be what was meant"
            )
        values[name.strip()] = None
    return values


def report(service: str, store: Settings) -> list[str]:
    """Reads what one service is configured to do, one line per setting.

    The value it reads now beside what the files say. Returned rather than
    logged, so what a person sees is what a test reads.
    """
    resolved = store.resolved()
    overrides = store.overrides()
    lines = [f"{service} settings, at version {store.version()}:"]
    for setting in catalog.of(service):
        value = resolved.get(setting.name) or ""
        default = os.environ.get(setting.name) or ""
        where = (
            "deployment"
            if setting.fixed
            else ("stored" if setting.name in overrides else "file")
        )
        said = f", file says {default or '(unset)'}" if where == "stored" else ""
        lines.append(f"  {setting.name:<32} {value or '(unset)':<28} {where}{said}")
    return lines


#: The stages whose output records the configuration it was made under, with
#: what one row of it is called and the command that makes it again.
_RECORDED = {
    "extraction": ("fact", "make extract-rerun"),
    "topics": ("topic", "make topics-discover"),
    "questions": ("question", "make questions-rerun"),
}


def stored_behind(service: str, version: str) -> int:
    """How many rows a service produced under a configuration other than `version`.

    Rows written before the version was recorded are not counted: nothing
    says what they were made under.
    """
    from sqlalchemy import func, select

    from database.qa_generator import Fact, Question, Topic
    from database.qa_generator.engine import sessions

    table = {"extraction": Fact, "topics": Topic, "questions": Question}[service]
    with sessions()() as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(table)
                .where(
                    table.settings_version.is_not(None),
                    table.settings_version != version,
                )
            )
            or 0
        )


def behind(
    service: str,
    version: str,
    count: Callable[[str, str], int] = stored_behind,
) -> list[str]:
    """Says how much of what a service stored predates the configuration now.

    A change to a setting reaches no stored row: nothing requeues them, and
    a drain under way keeps its settings until its queue is empty. So after a
    change, this is where a person sees what is still made under the old one,
    and which command brings it in line: the cheaper ones the catalogue names
    for the settings of this service that stale its output, and the stage's
    rerun for those that name none.

    The version is a digest of every setting, so it cannot say which setting
    moved; the count is of rows made under any other configuration.
    """
    if service not in _RECORDED:
        return []
    noun, rerun = _RECORDED[service]
    rows = count(service, version)
    if not rows:
        return []
    staling = [one for one in catalog.of(service) if service in one.invalidates]
    commands = sorted({one.rebuild for one in staling if one.rebuild})
    if any(not one.rebuild for one in staling):
        commands.append(rerun)
    said = (
        f"{rows} stored {noun}(s) were made under another configuration than "
        f"{version}. Whichever of this service's settings moved since, what "
        f"brings them in line is {' and '.join(commands)}."
    )
    return [said]


def change(service: str, values: dict[str, str | None], store: Settings) -> list[str]:
    """Writes what a command asked for, refusing what the stage would not read.

    Through `settings.changes`, which the route uses too. No version is
    given: a terminal decides against what it just read.

    Raises:
        SystemExit: If a setting is not this service's, is one the deployment
            owns, or would stop a service that is working now.
    """
    try:
        moved = changes.apply(service, values, store=store)
    except changes.Refused as refusal:
        raise SystemExit(refusal.detail) from None

    # The detail already names what is stale and how to rebuild it.
    return [f"{service}: {moved.detail}"]


def main(argv: list[str] | None = None) -> int:
    """Runs the settings command line.

    Args:
        argv: The arguments to parse, or None to read them from sys.argv.

    Returns:
        The process exit code.
    """
    args = parser().parse_args(sys.argv[1:] if argv is None else argv)

    telemetry.configure("settings")
    telemetry.trace_engine(engine())

    store = Settings()
    values = proposed(args.written, args.cleared)
    said = (
        change(args.service, values, store)
        if values
        else report(args.service, store) + behind(args.service, store.version())
    )
    for line in said:
        log.info("%s", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
