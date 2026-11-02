"""Whether the api serves the settings this checkout catalogues."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from settings import catalog, drift


def _served() -> dict[str, set[str]]:
    """What an api built from this checkout serves, by service."""
    served: dict[str, set[str]] = {}
    for one in catalog.SETTINGS:
        served.setdefault(one.service, set()).add(one.name)
    return served


def test_a_served_catalog_missing_a_setting_is_named() -> None:
    """An image built before a setting was added serves the rest without it."""
    served = _served()
    served["questions"].discard("QUESTIONS_MEETS_SHARE")

    assert drift.missing(served) == {"questions": ({"QUESTIONS_MEETS_SHARE"}, set())}


def test_an_identical_catalog_reports_nothing() -> None:
    """The api runs this checkout's build."""
    assert drift.missing(_served()) == {}


def test_an_unset_address_is_a_warning_not_a_failure(monkeypatch) -> None:
    """The doctor goes on to its other checks, as it does when the api is down."""
    monkeypatch.setattr(drift.telemetry, "configure", lambda *_, **__: None)
    monkeypatch.delenv("BACKEND_URL", raising=False)

    assert drift.main([]) == 0


def test_the_settings_are_read_with_the_deployments_secret(monkeypatch) -> None:
    """The api answers a read of its settings only to a caller that carries it."""
    monkeypatch.setenv("API_TOKEN", "s3cret")
    sent: list[dict[str, str]] = []

    class Answer:
        status_code = 200

        def raise_for_status(self) -> None:
            """Accepts."""

        def json(self) -> dict[str, list[dict[str, str]]]:
            """Serves nothing."""
            return {"settings": []}

    def get(url: str, headers: dict[str, str], timeout: float) -> Answer:
        sent.append(headers)
        return Answer()

    monkeypatch.setattr(drift.requests, "get", get)

    drift.served("http://api:8000")

    assert sent and all(one == {"X-API-Token": "s3cret"} for one in sent)


class _Answering(BaseHTTPRequestHandler):
    """A stand-in for the api: one status for every request."""

    status = 200

    def do_GET(self) -> None:
        """Answers every read with the class's status and a detail."""
        body = b'{"detail": "refused"}'
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        """Keeps the test output clean."""


@pytest.fixture
def api(monkeypatch):
    """Serves `_Answering`, and points BACKEND_URL at it."""
    server = HTTPServer(("127.0.0.1", 0), _Answering)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("BACKEND_URL", f"http://127.0.0.1:{server.server_address[1]}")
    monkeypatch.setenv("API_TOKEN", "not-the-apis")
    monkeypatch.setattr(drift.telemetry, "configure", lambda *_, **__: None)
    yield server
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize(("status", "says"), [(401, "API_TOKEN"), (500, "500")])
def test_an_api_that_refuses_the_request_fails_the_check(
    status, says, api, caplog
) -> None:
    """A refusal is not an api that is not up: the doctor must not pass it."""
    _Answering.status = status

    with caplog.at_level("WARNING"):
        code = drift.main([])

    assert code != 0
    assert says in caplog.text
    if status == 401:
        assert "make up" in caplog.text


def test_an_api_that_cannot_be_reached_is_a_warning(monkeypatch, caplog) -> None:
    """First run, before `make up`: the other checks go on."""
    monkeypatch.setenv("BACKEND_URL", "http://api:8000")
    monkeypatch.setattr(drift.telemetry, "configure", lambda *_, **__: None)

    def get(*args: object, **kwargs: object) -> None:
        raise drift.requests.ConnectionError("no route")

    monkeypatch.setattr(drift.requests, "get", get)

    with caplog.at_level("WARNING"):
        code = drift.main([])

    assert code == 0
    assert "did not serve its settings" in caplog.text
