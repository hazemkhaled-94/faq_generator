"""What the api answers before any route reads a request."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

WRITES = ["POST", "PUT", "PATCH", "DELETE"]


def called_as(host: str) -> TestClient:
    """A client on the api that names one host."""
    from api.main import app

    return TestClient(app, base_url=f"http://{host}")


@pytest.fixture
def guarded() -> TestClient:
    """The api's middleware in front of one route that takes every verb."""
    from api.main import app

    behind = FastAPI(middleware=app.user_middleware)

    @behind.api_route("/anything", methods=["GET", "HEAD", "OPTIONS", *WRITES])
    def anything() -> dict[str, bool]:
        """Answers whatever reaches it."""
        return {"reached": True}

    return TestClient(behind, base_url="http://localhost:8000")


@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:8000", "api:8000"])
def test_every_host_a_caller_names_is_answered(host: str) -> None:
    """The host's published port, and the compose service name."""
    assert called_as(host).get("/health").status_code == 200


def test_any_other_host_is_refused() -> None:
    """A name nothing in the deployment calls the api by."""
    assert called_as("evil.example").get("/health").status_code == 400


def test_an_answer_is_not_shared_with_another_site() -> None:
    """No CORS header, so a page elsewhere cannot read what it fetched."""
    answered = called_as("localhost:8000").get(
        "/health", headers={"origin": "https://evil.example"}
    )

    assert answered.status_code == 200
    assert "access-control-allow-origin" not in answered.headers


@pytest.mark.parametrize("method", WRITES)
@pytest.mark.parametrize(
    "headers",
    [
        {"sec-fetch-site": "cross-site"},
        {"sec-fetch-site": "same-site"},
        {"origin": "https://evil.example"},
        {"origin": "http://localhost:8501"},
        {"origin": "null"},
    ],
)
def test_a_write_a_browser_sent_from_elsewhere_is_refused(
    guarded, method: str, headers: dict[str, str]
) -> None:
    """Another site, or another port on this one."""
    answered = guarded.request(method, "/anything", headers=headers)

    assert answered.status_code == 403
    assert answered.json()["code"] == "cross_site_write"


@pytest.mark.parametrize("method", WRITES)
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"sec-fetch-site": "same-origin"},
        {"sec-fetch-site": "none"},
        {"sec-fetch-site": "same-origin", "origin": "http://localhost:8000"},
    ],
)
def test_a_write_from_this_origin_or_no_browser_is_answered(
    guarded, method: str, headers: dict[str, str]
) -> None:
    """The frontend's server, the orchestrator, make, and the docs page."""
    assert guarded.request(method, "/anything", headers=headers).status_code == 200


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_a_read_from_another_site_is_answered(guarded, method: str) -> None:
    """Only a write is refused."""
    answered = guarded.request(
        method,
        "/anything",
        headers={"sec-fetch-site": "cross-site", "origin": "https://evil.example"},
    )

    assert answered.status_code == 200
