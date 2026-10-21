"""Which runs Stop stops, without a database or a Dagster.

The queue half is the backend's own and is tested against a real database in
`tests/integration/api/test_pipeline_routes.py`. Here the queues move
nothing, so what is left is which runs were asked to stop and what the
answer says about each.
"""

from __future__ import annotations

import pytest

from api.orchestrator import Refused, Run


class Runs:
    """An orchestrator holding some runs, newest first."""

    def __init__(self, *recent: Run, refuses: dict[str, Exception] | None = None):
        """Holds the runs, and the ones that will not stop."""
        self.recent = list(recent)
        self.refuses = refuses or {}
        self.terminated: list[str] = []

    def live(self) -> list[Run]:
        """The unfinished runs, as Dagster lists them."""
        return [one for one in self.recent if one.live]

    def terminate(self, run_id: str) -> bool:
        """Stops one run, or refuses to."""
        self.terminated.append(run_id)
        if run_id in self.refuses:
            raise self.refuses[run_id]
        return True


@pytest.fixture
def stopping(monkeypatch):
    """Stop, on an orchestrator a test fills and queues that hold nothing."""
    from api.routes import pipeline

    monkeypatch.setattr(pipeline, "_fan", lambda action, names: ([], 0))

    def install(orchestrator: Runs):
        monkeypatch.setattr(pipeline, "orchestrator", orchestrator)
        return pipeline.stop()

    return install


def test_every_live_run_is_stopped_newest_first(stopping) -> None:
    """A queued run left behind starts the moment the running one stops."""
    runs = Runs(
        Run(id="R2", status="QUEUED"),
        Run(id="R1", status="STARTED"),
        Run(id="R0", status="SUCCESS"),
    )

    answer = stopping(runs)

    assert runs.terminated == ["R2", "R1"]
    assert answer.run is not None and answer.run.id == "R1"
    assert "R2" in answer.detail and "R1" in answer.detail


def test_a_run_that_cannot_be_stopped_is_named_in_the_detail(stopping) -> None:
    """Said rather than only logged, so the person who pressed Stop knows."""
    runs = Runs(Run(id="run-7", status="STARTED"), refuses={"run-7": Refused("no")})

    answer = stopping(runs)

    assert answer.run is None
    assert "run-7" in answer.detail
    assert "could NOT be stopped" in answer.detail


def test_the_others_are_stopped_when_one_will_not_be(stopping) -> None:
    """One refusal stops nothing else being stopped."""
    runs = Runs(
        Run(id="R2", status="QUEUED"),
        Run(id="R1", status="STARTED"),
        refuses={"R2": Refused("no")},
    )

    answer = stopping(runs)

    assert runs.terminated == ["R2", "R1"]
    assert answer.run is not None and answer.run.id == "R1"
    assert "R2 (no) could NOT be stopped" in answer.detail


def test_a_second_stop_does_not_call_a_stopping_run_unstoppable(stopping) -> None:
    """The first press left R1 CANCELING, and Dagster refuses to stop it twice."""
    runs = Runs(
        Run(id="R1", status="CANCELING"),
        refuses={
            "R1": Refused(
                "Run R1 could not be terminated due to having status CANCELING."
            )
        },
    )

    answer = stopping(runs)

    assert "could NOT be stopped" not in answer.detail, answer.detail
    assert "R1 already stopping" in answer.detail
    assert runs.terminated == []


def test_a_run_dagster_cannot_stop_yet_is_named_and_not_asked(stopping) -> None:
    """Dagster terminates only a queued or a started run."""
    runs = Runs(Run(id="R1", status="STARTING"))

    answer = stopping(runs)

    assert runs.terminated == []
    assert "R1 (STARTING" in answer.detail
    assert "could NOT be stopped" in answer.detail


class Reply:
    """One GraphQL reply."""

    status_code = 200

    def __init__(self, data: dict) -> None:
        """Holds the `data` the webserver answered."""
        self.data = data

    def json(self) -> dict:
        """The body."""
        return {"data": self.data}


class Webserver:
    """Dagster's GraphQL holding some runs, newest first, honouring `limit` as Dagster does."""

    def __init__(self, *runs: dict) -> None:
        """Holds the runs, and records which were terminated."""
        self.runs = list(runs)
        self.terminated: list[str] = []

    def post(self, url: str, json: dict, timeout: float):
        """Terminates one run, or lists as many as were asked for."""
        query, variables = json["query"], json["variables"]
        if "terminateRuns" in query:
            self.terminated.append(variables["runId"])
            results = [{"__typename": "TerminateRunSuccess"}]
            data = {
                "terminateRuns": {
                    "__typename": "TerminateRunsResult",
                    "terminateRunResults": results,
                }
            }
        else:
            limit = variables.get("limit")
            data = {
                "runsOrError": {
                    "__typename": "Runs",
                    "results": self.runs if limit is None else self.runs[:limit],
                },
                "repositoryOrError": {
                    "__typename": "Repository",
                    "sensors": [],
                    "schedules": [],
                },
            }
        return Reply(data)


def test_the_run_at_work_is_stopped_behind_five_queued(monkeypatch) -> None:
    """The nightly schedule, `make pipeline` and the button queue behind the one at work.

    The page's poll reads the five newest runs; Stop has to reach all of them.
    """
    from api.orchestrator import Dagster
    from api.routes import pipeline

    queued = [{"runId": f"queued-{n}", "status": "QUEUED"} for n in range(5, 0, -1)]
    webserver = Webserver(
        *queued, {"runId": "working", "status": "STARTED", "startTime": 1.0}
    )
    monkeypatch.setattr(
        pipeline, "orchestrator", Dagster("http://dagster:3000", session=webserver)
    )
    monkeypatch.setattr(pipeline, "_fan", lambda action, names: ([], 0))

    answer = pipeline.stop()

    assert webserver.terminated == [*(one["runId"] for one in queued), "working"]
    assert answer.run is not None and answer.run.id == "working"
