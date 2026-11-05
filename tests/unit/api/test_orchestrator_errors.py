"""An error from Dagster's runs query is an error, not an empty list."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from unit.api.test_orchestrator import FakeSession

from api.orchestrator import Dagster, Refused

ERROR = {"runsOrError": {"__typename": "PythonError", "message": "storage is down"}}


def test_live_raises_the_type_dagster_answered(caplog) -> None:
    """Stop and Run both read it, and neither may take silence for idle."""
    client = Dagster("http://dagster:3000", session=FakeSession({"data": ERROR}))

    with pytest.raises(Refused, match="PythonError"):
        client.live()
    assert "storage is down" in caplog.text, "Dagster's own words are in the log"


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
    detail = answered.json()["detail"]
    assert "PythonError" in detail and "trace" in detail
    assert "no connection" not in detail


def test_an_open_read_of_the_runs_does_not_echo_the_storage_error(
    monkeypatch, caplog
) -> None:
    """Dagster's text names its database's host and role: the log has it, the read not."""
    from api.main import app
    from api.routes import pipeline

    storage_down = (
        "sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) connection to "
        'server at "postgres" (10.89.0.7), port 5432 failed: FATAL:  password '
        'authentication failed for user "dagster_owner"\n'
    )
    answer = {"runsOrError": {"__typename": "PythonError", "message": storage_down}}
    monkeypatch.setattr(
        pipeline,
        "orchestrator",
        Dagster("http://dagster:3000", session=FakeSession({"data": answer})),
    )

    # No X-API-Token: a read, which the token does not guard.
    answered = TestClient(app, base_url="http://localhost:8000").get("/pipeline/runs")

    assert answered.status_code == 503, answered.text
    detail = answered.json()["detail"]
    assert "PythonError" in detail and "trace" in detail
    assert "10.89.0.7" not in detail and "dagster_owner" not in detail, detail
    trace = detail.rsplit("trace ", 1)[1]
    assert f"trace {trace}" in caplog.text and "10.89.0.7" in caplog.text


@pytest.mark.parametrize(
    "message", ["Zugriff verweigert: Benutzer »dagster«", "Σφάλμα αποθήκευσης"]
)
def test_the_polled_state_does_not_carry_the_storage_error(
    message: str, caplog
) -> None:
    """`GET /pipeline` shows the detail to anyone: the type and an id, not the text."""
    answer = {"runsOrError": {"__typename": "PythonError", "message": message}}
    client = Dagster("http://dagster:3000", session=FakeSession({"data": answer}))

    detail = client.state().detail or ""

    assert "PythonError" in detail and "trace" in detail
    assert message not in detail
    assert message in caplog.text
