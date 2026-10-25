"""What a caller is told when something behind the api fails.

The database's host, address and role, the object store's endpoint and a
driver's own sentence are the deployment's. They go to the log with a trace
id, and the caller gets a fixed sentence naming that id.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

SECRET = 'connection to server at "10.9.8.7", port 5432 failed: role "app_role"'


def test_a_failing_database_is_reported_without_its_address(
    monkeypatch, caplog
) -> None:
    """Unreachable, and nothing the driver said."""
    from api import status

    class Down:
        def __call__(self):
            raise RuntimeError(SECRET)

    monkeypatch.setattr(status, "sessions", lambda: Down())
    monkeypatch.setattr(status, "heads", frozenset)
    caplog.set_level(logging.ERROR)

    reported = status.StatusService({}).snapshot()["database"]

    assert reported.ok is False
    assert "10.9.8.7" not in reported.detail
    assert "app_role" not in reported.detail
    assert "nreachable" in reported.detail
    assert "10.9.8.7" in caplog.text


def test_a_failing_counter_is_reported_without_the_driver_text(monkeypatch) -> None:
    """A service's own numbers, read from the same database."""
    from api import status

    def count() -> dict[str, int]:
        raise RuntimeError(SECRET)

    reported = status.StatusService._counter("parsing", status.Counter("x", count))

    assert reported.ok is False
    assert "10.9.8.7" not in reported.detail


def test_a_failing_object_store_is_reported_without_its_endpoint(monkeypatch) -> None:
    """The store's address is the deployment's."""
    from api import status

    def names() -> list[str]:
        raise RuntimeError("endpoint http://seaweedfs-s3:8333 refused")

    monkeypatch.setattr(status, "bucket_names", names)

    reported = status.StatusService._object_store()

    assert reported.ok is False
    assert "seaweedfs" not in reported.detail


@pytest.mark.parametrize(
    "failure",
    [
        "HTTPConnectionPool(host='dagster-webserver', port=3000): Max retries exceeded",
        "Verbindung zu dagster-webserver:3000 abgelehnt",
    ],
)
def test_an_orchestrator_that_does_not_answer_is_reported_without_its_address(
    failure: str, caplog
) -> None:
    """Unreachable, and neither its address nor the transport's sentence.

    What GET /pipeline polls and what a 503 carries; the log keeps both.
    """
    import requests

    from api.orchestrator import Dagster, Unavailable

    class Down:
        def post(self, *_, **__):
            raise requests.exceptions.ConnectionError(failure)

    client = Dagster("http://dagster-webserver:3000", session=Down())  # type: ignore[arg-type]
    caplog.set_level(logging.ERROR)

    detail = client.state().detail or ""
    with pytest.raises(Unavailable) as raised:
        client.launch()

    for said in (detail, str(raised.value)):
        assert "nreachable" in said
        assert "dagster-webserver" not in said
        assert failure not in said
    assert failure in caplog.text


@pytest.fixture
def broken() -> TestClient:
    """An application whose one route fails as a driver fails."""
    from api import errors

    app = FastAPI()
    errors.install(app)

    @app.get("/fails")
    def fails() -> None:
        raise RuntimeError(SECRET)

    return TestClient(app, raise_server_exceptions=False)


def test_an_unhandled_error_is_answered_with_a_fixed_sentence(broken, caplog) -> None:
    """500, a code, the trace id, and nothing of the error."""
    caplog.set_level(logging.ERROR)

    answered = broken.get("/fails")

    assert answered.status_code == 500
    body = answered.json()
    assert body["code"] == "internal_error"
    assert "10.9.8.7" not in answered.text
    assert "app_role" not in answered.text
    trace = body["detail"].rsplit(" ", 1)[-1]
    assert len(trace) == 32
    assert trace in caplog.text
    assert "10.9.8.7" in caplog.text


def test_the_fixed_sentence_is_the_same_for_every_error(broken) -> None:
    """Nothing of one error tells it from another but the trace."""
    first = broken.get("/fails").json()["detail"].rsplit(" ", 1)[0]
    second = broken.get("/fails").json()["detail"].rsplit(" ", 1)[0]

    assert first == second
