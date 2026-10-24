"""What the api answers before any route reads a request."""

from __future__ import annotations

import os
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

WRITES = ["POST", "PUT", "PATCH", "DELETE"]


def called_as(host: str) -> TestClient:
    """A client on the api that names one host."""
    from api.main import app

    return TestClient(
        app, base_url=f"http://{host}", headers={"x-api-token": os.environ["API_TOKEN"]}
    )


@pytest.fixture
def guarded() -> TestClient:
    """The api's middleware in front of one route that takes every verb."""
    from api.main import app

    behind = FastAPI(middleware=app.user_middleware)

    @behind.api_route("/anything", methods=["GET", "HEAD", "OPTIONS", *WRITES])
    def anything() -> dict[str, bool]:
        """Answers whatever reaches it."""
        return {"reached": True}

    return TestClient(
        behind,
        base_url="http://localhost:8000",
        headers={"x-api-token": os.environ["API_TOKEN"]},
    )


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


def test_the_docs_page_loads_pinned_assets() -> None:
    """An exact version, which a later publish to the CDN cannot change."""
    client = called_as("localhost:8000")
    page = client.get("/docs")

    assert page.status_code == 200
    assert re.search(r"swagger-ui-dist@\d+\.\d+\.\d+/swagger-ui-bundle\.js", page.text)
    assert re.search(r"swagger-ui-dist@\d+\.\d+\.\d+/swagger-ui\.css", page.text)
    assert "@5/" not in page.text
    assert client.get("/redoc").status_code == 404


class Uploads:
    """An ingest service whose limit every upload here is over."""

    max_file_size_bytes = 0

    def __init__(self) -> None:
        """Starts with nothing refused and nothing ingested."""
        self.refused: list[tuple[str, int]] = []
        self.ingested: list[object] = []

    def refuse_oversized(self, filename: str, size_bytes: int):
        """Records the refusal by declared size."""
        from database.qa_generator import Outcome
        from ingestion.models import IngestResult

        self.refused.append((filename, size_bytes))
        return IngestResult(Outcome.TOO_LARGE, None, "over the limit")

    def ingest(self, upload):
        """Records the upload, which no test here should reach."""
        self.ingested.append(upload)
        raise AssertionError("the upload was ingested")


@pytest.fixture
def uploads(monkeypatch) -> Uploads:
    """The upload route, on a service that records what it was asked."""
    from api.routes import documents

    service = Uploads()
    monkeypatch.setattr(documents, "ingesting", lambda: service)
    return service


@pytest.fixture
def parsed(monkeypatch) -> list[bool]:
    """One entry each time a request's form is parsed."""
    from starlette.requests import Request

    form = Request.form
    calls: list[bool] = []

    def counted(self, *args, **kwargs):
        calls.append(True)
        return form(self, *args, **kwargs)

    monkeypatch.setattr(Request, "form", counted)
    return calls


def test_an_upload_declaring_more_than_the_limit_is_refused_unparsed(
    uploads, parsed
) -> None:
    """413 on Content-Length, recorded under the fallback name."""
    from api.routes import documents

    answered = called_as("localhost:8000").post(
        "/documents",
        files={"file": ("big.pdf", b"x" * (documents._FRAMING + 1), "application/pdf")},
    )

    assert answered.status_code == 413
    assert answered.json()["code"] == "too_large"
    assert [name for name, _ in uploads.refused] == ["unnamed"]
    assert parsed == []


def test_an_upload_declaring_no_length_is_refused_unparsed(uploads, parsed) -> None:
    """Sent chunked: 411, and nothing recorded, parsed or ingested."""
    body = (
        b"--b\r\n"
        b'Content-Disposition: form-data; name="file"; filename="big.pdf"\r\n'
        b"Content-Type: application/pdf\r\n\r\n%PDF-\r\n--b--\r\n"
    )

    answered = called_as("localhost:8000").post(
        "/documents",
        content=iter([body]),
        headers={"content-type": "multipart/form-data; boundary=b"},
    )

    assert answered.status_code == 411
    assert answered.json()["code"] == "length_required"
    assert parsed == []
    assert uploads.refused == []
    assert uploads.ingested == []
