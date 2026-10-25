"""An error from Dagster's runs query is an error, not an empty list."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from unit.api.test_orchestrator import FakeSession

from api.orchestrator import Dagster, Refused

ERROR = {"runsOrError": {"__typename": "PythonError", "message": "storage is down"}}


def test_live_raises_what_dagster_said() -> None:
    """Stop and Run both read it, and neither may take silence for idle."""
    client = Dagster("http://dagster:3000", session=FakeSession({"data": ERROR}))

    with pytest.raises(Refused, match="storage is down"):
        client.live()


def test_the_state_the_page_polls_still_never_raises() -> None:
    """It reads the error as an orchestrator that is not usable."""
    client = Dagster("http://dagster:3000", session=FakeSession({"data": ERROR}))

    assert client.state().available is False


class _Begun:
    """A connection that takes the advisory lock and nothing else."""

    def __enter__(self):
        """Itself."""
        return self

    def __exit__(self, *exc) -> None:
        """Commits nothing."""

    def execute(self, *args, **kwargs) -> None:
        """Takes the lock."""


class _Session:
    """A webserver whose answer to the runs query is an error, not a list."""

    def post(self, url: str, json: dict, timeout: float):
        """Answers `runsOrError` with a PythonError, as Dagster does when its storage fails."""

        class Reply:
            status_code = 200

            def json(self) -> dict:
                """The error, in a body that parses."""
                return {
                    "data": {
                        "runsOrError": {
                            "__typename": "PythonError",
                            "message": "psycopg2.OperationalError: no connection",
                        }
                    }
                }

        return Reply()


def test_a_dagster_that_cannot_list_its_runs_refuses_a_run_with_503(
    monkeypatch,
) -> None:
    """An error is not an empty list: a second run would race the first."""
    from api.main import app
    from api.routes import pipeline

    api = TestClient(
        app,
        base_url="http://localhost:8000",
        headers={"x-api-token": os.environ["API_TOKEN"]},
    )

    monkeypatch.delenv("HOST_RUNNER", raising=False)
    monkeypatch.setattr(
        pipeline, "orchestrator", Dagster("http://dagster:3000", session=_Session())
    )
    monkeypatch.setattr(
        pipeline, "engine", lambda: type("E", (), {"begin": lambda self: _Begun()})()
    )

    answered = api.post("/pipeline/run")

    assert answered.status_code == 503, answered.text
    assert answered.json()["code"] == "orchestrator_refused"
    assert "no connection" in answered.json()["detail"]
