"""The run history and the trigger switch, without a database or a Dagster.

The routes are imported inside the fixture, never at module scope: see
`tests/unit/api/test_params.py`.
"""

from __future__ import annotations

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
        return TestClient(app, base_url="http://localhost:8000")

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
