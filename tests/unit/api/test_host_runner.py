"""The go-live profile at the API: no orchestrated run, and queue verbs that say who drains.

With HOST_RUNNER=1 the model workers and Dagster stay stopped, and the model
stages run on the host through `make corpus-hosted`. A route that would have
started the orchestrator answers 409 naming that command, and a queue verb for
a model stage still queues its rows and says what drains them.

The routes are imported inside the fixture, never at module scope: see
`tests/unit/api/test_params.py`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


REFUSAL = "the go-live profile runs the model stages through make corpus-hosted"


@pytest.fixture
def api(monkeypatch):
    """The real app, with the queues a fan-out moves replaced by empty ones."""
    from api.main import app
    from api.routes import pipeline

    monkeypatch.setattr(pipeline, "_fan", lambda action, names, trigger=None: ([], 0))
    return TestClient(app, base_url="http://localhost:8000")


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/pipeline/run", None),
        ("post", "/pipeline/start", None),
        ("put", "/pipeline/automation", {"on_arrival": True}),
    ],
)
def test_the_go_live_profile_refuses_what_would_start_the_orchestrator(
    api, monkeypatch, method, path, body
) -> None:
    """409, with the text the Makefile gives, naming the host runner."""
    monkeypatch.setenv("HOST_RUNNER", "1")

    answered = api.request(method, path, json=body)

    assert answered.status_code == 409, answered.text
    assert answered.json()["code"] == "host_runner"
    assert REFUSAL in answered.json()["detail"]


def test_the_development_profile_starts_a_wave_as_before(api, monkeypatch) -> None:
    """Unset, nothing changes."""
    monkeypatch.delenv("HOST_RUNNER", raising=False)

    answered = api.post("/pipeline/start")

    assert answered.status_code == 202


def test_stop_and_retry_still_work_on_the_go_live_profile(api, monkeypatch) -> None:
    """They take rows back or return failures; neither starts a run."""
    from api.routes import pipeline

    monkeypatch.setenv("HOST_RUNNER", "1")
    monkeypatch.setattr(pipeline.orchestrator, "live", lambda: [])

    assert api.post("/pipeline/retry").status_code == 202
    assert api.post("/pipeline/stop").status_code == 202
