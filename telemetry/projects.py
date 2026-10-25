"""What Phoenix is holding, and taking back the projects holding no work.

A project is created by the first span filed under it and never by
anything else, so one appears whenever a process exports and disappears
never. That was survivable while a project meant a run somebody asked
for. It stopped being survivable when `run_id` minted a uuid per PROCESS:
a `--watch` worker is a process per restart, and a credential that has
expired restarts it every minute.

Two things came out of that, and this is the second:

- `telemetry/pipeline.py` no longer gives an unnamed run a project of its
  own, and `stages/cli.py` no longer installs the exporter until the
  preflight has passed. Together those stop the count growing.
- This takes back what the old arrangement left behind.

**What counts as holding no work.** Not "empty". A project holds work
when something other than a model call happened in it: an `assess`, an
`extract`, a `parse`. A project whose every span is a `completion` is a
process that proved the model answers and then died, and the call it
proved it with is in the logs.

A third thing is kept here for the same reason, that Phoenix holds what was
sent: every prompt is a passage of a customer's document. `--retention` sets
the default trace retention policy, which every project without a policy of
its own is under and which ships as "never delete", to
`PHOENIX_TRACE_RETENTION_DAYS`. `make up` runs it.

Runs on the host, like `evaluation/` and `review/`: no image carries a
reason to delete a project.
"""

from __future__ import annotations

import argparse
import base64
import logging
import os
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

import requests

from telemetry import pipeline

log = logging.getLogger(__name__)

#: How many projects one page of the listing asks for.
PAGE = 500

#: How many spans are read per project to decide whether it holds work.
#: One would do for the common case - a leftover holds exactly one - and
#: this is enough that a project whose first spans happen to be model
#: calls is still read correctly.
SAMPLE = 50

#: The span a model call produces, whoever made it. A project holding
#: nothing else is a preflight that never became a run.
CALL = "completion"

#: How many days a trace is kept where the deployment says nothing.
RETENTION_DAYS = 30

#: Phoenix's default retention policy, which a project with no policy of its
#: own is under. A GraphQL global id: the type's name and the policy's number.
DEFAULT_POLICY = base64.b64encode(b"ProjectTraceRetentionPolicy:0").decode()

_RETAIN = """
mutation ($input: PatchProjectTraceRetentionPolicyInput!) {
  patchProjectTraceRetentionPolicy(input: $input) { __typename }
}
"""

#: Never deleted, whatever it holds. Phoenix files a span carrying no
#: project name here, so it is where anything misconfigured ends up - and
#: a tool that swept it would take the evidence with it.
KEEP = frozenset({"default"})


@dataclass(frozen=True)
class Project:
    """One Phoenix project, and whether anything happened in it."""

    id: str
    name: str
    spans: int
    #: Whether any span is something other than a model call.
    work: bool
    #: Whether every span was read, rather than the first `SAMPLE` of them.
    whole: bool

    @property
    def spent(self) -> bool:
        """Whether this project is a leftover rather than a run.

        Nothing but model calls, AND few enough of them that every span was
        actually read. A project that filled the sample is one this has
        only seen the start of, and the first fifty spans of a run can be
        model calls too.

        So a project this cannot see the end of is kept. The cost is a
        leftover nobody sweeps; the cost the other way is somebody's data.
        """
        # ponytail: spans are exported when they end, so a run still going,
        # or one killed before its parent span ended, holds only completions
        # and reads as spent. Upgrade: keep a project whose newest span is
        # recent.
        return not self.work and self.whole


#: How long one Phoenix call may take. A prune walks every project and
#: deletes some of them, and the server is doing real work for each.
_TIMEOUT = 60.0


class _Phoenix(requests.Session):
    """A session that answers relative paths and times every call out.

    `requests` has neither a base URL nor a default timeout, and both are
    what the call sites here rely on. The same shape `orchestration/client`
    and `frontend/lib/backend/base` build by hand; a Session subclass
    because this one is used as a context manager and passed around as a
    client rather than wrapped in a class of its own.
    """

    def __init__(self, base: str) -> None:
        """Points the session at one Phoenix."""
        super().__init__()
        self._base = base.rstrip("/")

    def request(self, method, url, *args, **kwargs):
        """Sends one call, resolving the path and defaulting the timeout."""
        kwargs.setdefault("timeout", _TIMEOUT)
        return super().request(method, f"{self._base}{url}", *args, **kwargs)


def _client() -> _Phoenix:
    """An HTTP client pointed at Phoenix, with the bearer it wants.

    requests rather than httpx, which is what every other first-party
    caller in this repository speaks. httpx arrives transitively through
    the model stack and was never declared here.
    """
    base = os.environ.get("PHOENIX_BASE_URL")
    if not base:
        raise SystemExit(
            "PHOENIX_BASE_URL is unset, so there is nothing to ask. It is in "
            ".env; see .env.example."
        )
    key = os.environ.get("PHOENIX_API_KEY") or os.environ.get("PHOENIX_ADMIN_SECRET")
    client = _Phoenix(base)
    if key:
        client.headers["Authorization"] = f"Bearer {key}"
    return client


def listed(client, path: str = "/v1/projects") -> Iterator[dict]:
    """Everything Phoenix holds at one path, following the cursor to the end.

    **Paginated, and the first version of this was not.** Phoenix answers
    with a page and a `next_cursor`, and a tool that reads one page reports
    a number that is really "the page size" and prunes a slice of the
    backlog.
    """
    cursor = None
    while True:
        params = {"limit": PAGE}
        if cursor:
            params["cursor"] = cursor
        answered = client.get(path, params=params)
        answered.raise_for_status()
        page = answered.json()
        yield from page.get("data", [])
        cursor = page.get("next_cursor")
        if not cursor:
            return


def held(client) -> list[Project]:
    """Every project Phoenix holds, and whether work happened in each.

    One request per project on top of the listing, which is why this is a
    command somebody runs rather than something a page polls.
    """
    found = []
    for one in listed(client):
        answered = client.get(
            f"/v1/projects/{one['id']}/spans", params={"limit": SAMPLE}
        )
        if not answered.ok:
            log.warning(
                "could not read the spans of %s: %s, so it is kept",
                one["name"],
                answered.status_code,
            )
            found.append(
                Project(
                    id=one["id"], name=one["name"], spans=0, work=False, whole=False
                )
            )
            continue
        spans = answered.json().get("data", []) or []
        found.append(
            Project(
                id=one["id"],
                name=one["name"],
                spans=len(spans),
                work=any(span.get("name") != CALL for span in spans),
                whole=len(spans) < SAMPLE,
            )
        )
    return found


def spent(projects: list[Project]) -> list[Project]:
    """The projects worth taking back, `default` never among them."""
    return [one for one in projects if one.spent and one.name not in KEEP]


def report(projects: list[Project]) -> list[str]:
    """What Phoenix is holding, as lines to print."""
    taking = spent(projects)
    return [
        f"{len(projects)} project(s) in Phoenix",
        (
            f"{len(taking)} of them hold no work - every span is a {CALL}, "
            f"which is a preflight that never became a run"
        ),
        (
            f"{len(projects) - len(taking)} hold something, or are too big "
            f"to read in one page and are left alone"
        ),
        "",
        *(f"  no work: {one.name} ({one.spans} span(s))" for one in taking[:25]),
        *([f"  ... and {len(taking) - 25} more"] if len(taking) > 25 else []),
    ]


def own(projects: list[Project], every_database: bool = False) -> list[Project]:
    """The projects this database filed, or all of them where asked.

    A project from before names carried the database belongs to none, so it
    is left alone unless every database is meant.
    """
    return (
        projects
        if every_database
        else [one for one in projects if pipeline.owned(one.name)]
    )


def prune(
    client,
    projects: list[Project],
    everything: bool = False,
    every_database: bool = False,
) -> int:
    """Deletes projects, and says how many went.

    Args:
        client: The Phoenix client.
        projects: Everything Phoenix holds.
        every_database: Take other databases' projects too, and any filed before
            names carried one. Without it only this database's go.
        everything: Take all of them bar KEEP, rather than only the spent ones. What
            `make wipe` passes: a corpus that is gone has no traces worth
            keeping, and the spent-only rule would leave every project that
            recorded a real run - which after a wipe is all of them.

    Returns:
        How many were deleted.
    """
    projects = own(projects, every_database)
    taking = (
        [one for one in projects if one.name not in KEEP]
        if everything
        else spent(projects)
    )
    if not taking:
        return 0
    log.warning(
        "deleting %d project(s) holding %d span(s) between them%s",
        len(taking),
        sum(one.spans for one in taking),
        "" if everything else ", all of them model calls no run followed",
    )
    deleted = 0
    for one in taking:
        answered = client.delete(f"/v1/projects/{one.id}")
        if answered.ok:
            deleted += 1
        else:
            log.warning("could not delete %s: %s", one.name, answered.status_code)
    return deleted


def retention_days(environment: Mapping[str, str] | None = None) -> int:
    """How many days traces are kept, from PHOENIX_TRACE_RETENTION_DAYS.

    Raises:
        SystemExit: If it is set and is not a whole number of days above
            zero. Zero is Phoenix's own "never delete", the policy this
            replaces, so it is refused rather than read as a choice.
    """
    value = (
        (os.environ if environment is None else environment)
        .get("PHOENIX_TRACE_RETENTION_DAYS", "")
        .strip()
    )
    if not value:
        return RETENTION_DAYS
    if not value.isdecimal() or int(value) < 1:
        raise SystemExit(
            f"PHOENIX_TRACE_RETENTION_DAYS={value!r} is not a whole number of "
            "days above zero; it is in configs/env/deployment.env."
        )
    return int(value)


def set_retention(client, days: int) -> None:
    """Sets the default trace retention policy to `days`.

    Phoenix deletes spans older than that when its policy runs, which it does
    on its own schedule, so what a trace held is gone by a day after the limit
    and not at it.

    Raises:
        RuntimeError: If Phoenix answers with an error. GraphQL answers 200
            with the error in the body.
    """
    answered = client.post(
        "/graphql",
        json={
            "query": _RETAIN,
            "variables": {
                "input": {
                    "id": DEFAULT_POLICY,
                    "rule": {"maxDays": {"maxDays": days}},
                }
            },
        },
    )
    answered.raise_for_status()
    if errors := answered.json().get("errors"):
        raise RuntimeError(
            "Phoenix refused the retention policy: "
            + "; ".join(str(one.get("message", one)) for one in errors)
        )


def purge_datasets(client, every_database: bool = False) -> int:
    """Deletes this database's datasets, or every one, and says how many went.

    A dataset carries its database after its name, as a project does, so
    the golden set one database uploaded and the experiments scored on it
    are not taken by another's wipe. `every_database` takes them all, and
    any uploaded before names carried one.

    A different resource from a project and not reached by deleting one:
    `/v1/projects` holds the traces a run wrote, `/v1/datasets` holds the
    golden cases `make eval-upload` puts there and the experiments scored
    against them, which Phoenix keeps under the dataset.

    Its own flag rather than part of `--purge`, because `make wipe
    KEEP=golden` spares these and takes the projects anyway. The cases are
    re-uploadable from `evaluation/`, which is what makes either choice
    reasonable.

    Returns:
        How many datasets were deleted.
    """
    taking = [
        one
        for one in listed(client, "/v1/datasets")
        if every_database or pipeline.owned(one.get("name", ""))
    ]
    if not taking:
        return 0
    log.warning("deleting %d dataset(s) and their experiments", len(taking))
    deleted = 0
    for one in taking:
        answered = client.delete(f"/v1/datasets/{one['id']}")
        if answered.ok:
            deleted += 1
        else:
            log.warning(
                "could not delete dataset %s: %s",
                one.get("name", one["id"]),
                answered.status_code,
            )
    return deleted


def parser() -> argparse.ArgumentParser:
    """Builds the argument parser."""
    built = argparse.ArgumentParser(
        prog="python -m telemetry.projects",
        description="What Phoenix is holding, and taking back the projects "
        "holding no work.",
    )
    built.add_argument(
        "--all-databases",
        action="store_true",
        dest="all_databases",
        help="with --prune, --purge or --purge-datasets, take every database's "
        "and any from before names carried one, not only this database's",
    )
    group = built.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--list",
        action="store_true",
        help="report what Phoenix holds, and change nothing",
    )
    group.add_argument(
        "--prune",
        action="store_true",
        help="delete the projects in which nothing but a model call ever "
        "happened. Irreversible, and it says what it is taking first.",
    )
    group.add_argument(
        "--purge",
        action="store_true",
        help="delete EVERY project, whatever it holds. What `make wipe` "
        "runs: traces of a corpus that no longer exists. Irreversible.",
    )
    group.add_argument(
        "--purge-datasets",
        action="store_true",
        dest="purge_datasets",
        help="delete every DATASET and the experiments under it - the "
        "golden cases `make eval-upload` puts there. A different resource "
        "from a project, so `--purge` does not reach them. Irreversible, "
        "and re-uploadable from evaluation/.",
    )
    group.add_argument(
        "--retention",
        action="store_true",
        help="set the default trace retention policy to "
        "PHOENIX_TRACE_RETENTION_DAYS (30 where unset), so a prompt - a "
        "passage of a customer's document - is not kept for ever. What "
        "`make up` runs.",
    )
    return built


def main(argv: list[str] | None = None) -> int:
    """Runs the command line.

    Returns:
        The process exit code.
    """
    import telemetry

    args = parser().parse_args(sys.argv[1:] if argv is None else argv)
    telemetry.configure("telemetry-projects")

    with _client() as client:
        if args.retention:
            days = retention_days()
            set_retention(client, days)
            log.info("Phoenix keeps traces for %d day(s)", days)
            return 0
        # Only when a project is being read or taken: `held` costs one
        # request per project, and the dataset flag touches none of them.
        projects = [] if args.purge_datasets else held(client)
        for line in report(projects) if not args.purge_datasets else ():
            log.info("%s", line)
        if args.prune or args.purge:
            log.info(
                "deleted %d project(s)",
                prune(client, projects, args.purge, args.all_databases),
            )
        if args.purge_datasets:
            log.info(
                "deleted %d dataset(s)",
                purge_datasets(client, args.all_databases),
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
