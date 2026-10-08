"""What the api answers before any route reads a request."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def called_as(host: str) -> TestClient:
    """A client on the api that names one host."""
    from api.main import app

    return TestClient(app, base_url=f"http://{host}")


@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:8000", "api:8000"])
def test_every_host_a_caller_names_is_answered(host: str) -> None:
    """The host's published port, and the compose service name."""
    assert called_as(host).get("/health").status_code == 200


def test_any_other_host_is_refused() -> None:
    """A name nothing in the deployment calls the api by."""
    assert called_as("evil.example").get("/health").status_code == 400
