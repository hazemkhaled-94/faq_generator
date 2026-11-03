"""The run history and the trigger switch, without a database or a Dagster.

The routes are imported inside the fixture, never at module scope: see
`tests/unit/api/test_params.py`.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from api.orchestrator import Refused


class Asked:
    """An orchestrator that records the limits it was asked for, and may say no."""

    def __init__(self, refusal: Exception | None = None) -> None:
        """Holds the refusal every call raises, if any."""
        self.limits: list[int] = []
        self.refusal = refusal

    def runs(self, *, limit: int = 20) -> list:
        """No runs, or the refusal."""
        self.limits.append(limit)
        if self.refusal:
            raise self.refusal
        return []

    def automate(self, **switches) -> None:
        """The refusal."""
        raise self.refusal or AssertionError("not scripted")


@pytest.fixture
def api(monkeypatch):
    """The real app, with the routes' orchestrator replaced by a stand-in."""
    from api.main import app
    from api.routes import pipeline

    def install(orchestrator: Asked) -> TestClient:
        monkeypatch.setattr(pipeline, "orchestrator", orchestrator)
        return TestClient(
            app,
            base_url="http://localhost:8000",
            headers={"x-api-token": os.environ["API_TOKEN"]},
        )

    return install


@pytest.mark.parametrize("limit", ["-1", "0", "3000000000"])
def test_a_runs_limit_out_of_range_is_refused_before_dagster(api, limit) -> None:
    """As every other listing holds its limit to 1..PAGE_MAX."""
    held = Asked()

    answered = api(held).get(f"/pipeline/runs?limit={limit}")

    assert answered.status_code == 422, (answered.status_code, held.limits)
    assert held.limits == []


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("put", "/pipeline/automation", {"on_arrival": True}),
        ("get", "/pipeline/runs", None),
    ],
)
def test_a_dagster_that_answered_no_is_not_called_absent(
    api, method, path, body
) -> None:
    """Refused means Dagster answered, as `POST /pipeline/run` already says."""
    client = api(Asked(Refused("UnauthorizedError: Konto gesperrt")))

    answered = client.request(method, path, json=body)

    assert answered.status_code == 503
    assert answered.json()["code"] == "orchestrator_refused", answered.json()
    assert "Konto gesperrt" in answered.json()["detail"]


class Queue:
    """A stage queue that reports two rows waiting and no database behind it."""

    def queue_state(self, within=None, *, digests: bool = False):
        """The counts."""
        from types import SimpleNamespace

        return SimpleNamespace(working=True, rows={"pending": 2}, digests={})


def stalled_server(seconds: float):
    """A webserver that accepts a request and answers it only after `seconds`."""
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Stall(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            """Sits on the request."""
            time.sleep(seconds)
            try:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")
            except OSError:
                pass

        def log_message(self, format, *args) -> None:
            """Silent."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Stall)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_a_dagster_that_stalls_leaves_the_queues_answering_within_four_seconds(
    api, monkeypatch
) -> None:
    """The page waits ten seconds for this route, so a slow Dagster must not take them."""
    import time

    from api.orchestrator import Dagster
    from api.routes import pipeline

    server = stalled_server(5)
    monkeypatch.setattr(pipeline, "STAGES", (("parsing", Queue()),))
    client = api(Dagster(f"http://127.0.0.1:{server.server_port}"))

    started = time.monotonic()
    answered = client.get("/pipeline")
    waited = time.monotonic() - started
    server.shutdown()
    server.server_close()

    assert answered.status_code == 200, answered.text
    assert waited < 4, f"answered after {waited:.1f}s"
    body = answered.json()
    assert body["stages"][0]["rows"] == {"pending": 2}
    assert body["orchestration"]["available"] is False
