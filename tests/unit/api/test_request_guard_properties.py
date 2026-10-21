"""The api's two request guards, over every input rather than five.

A write a browser sent from any origin but the api's own is refused, and a
document route never hands a string that is not a digest to the store it
would become an object key in.
"""

from __future__ import annotations

import string
from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_OWN = "http://localhost:8000"
_WRITES = ("POST", "PUT", "PATCH", "DELETE")
_SHARED = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])


@pytest.fixture
def guarded() -> TestClient:
    """The api's middleware in front of one route that takes every verb."""
    from api.main import app

    behind = FastAPI(middleware=app.user_middleware)

    @behind.api_route("/anything", methods=["GET", *_WRITES])
    def anything() -> dict[str, bool]:
        return {"reached": True}

    return TestClient(behind, base_url=_OWN)


_HEADER_TEXT = st.text(
    alphabet=st.characters(min_codepoint=0x21, max_codepoint=0x7E), max_size=40
)


@_SHARED
@given(
    method=st.sampled_from(_WRITES),
    origin=st.one_of(
        _HEADER_TEXT,
        st.builds(
            "{}://{}".format,
            st.sampled_from(["http", "https", "HTTP", "ws"]),
            st.sampled_from(
                [
                    "localhost:8000",
                    "localhost",
                    "127.0.0.1:8000",
                    "localhost:8501",
                    "localhost:8000.evil.example",
                    "api:8000",
                ]
            ),
        ),
    ).filter(lambda origin: origin != _OWN),
)
def test_a_write_from_any_other_origin_is_refused(guarded, method, origin) -> None:
    """Not a prefix, a case, a scheme or a port away from the api's own."""
    answered = guarded.request(method, "/anything", headers={"origin": origin})

    assert answered.status_code == 403, origin
    assert answered.json()["code"] == "cross_site_write"


@_SHARED
@given(method=st.sampled_from(_WRITES), site=_HEADER_TEXT)
def test_a_write_naming_its_own_origin_is_refused_only_when_cross_or_same_site(
    guarded, method, site
) -> None:
    """Sec-Fetch-Site refuses exactly cross-site and same-site.

    The two values a browser sends for another site and another port.
    """
    answered = guarded.request(
        method, "/anything", headers={"origin": _OWN, "sec-fetch-site": site}
    )

    refused = site in ("cross-site", "same-site")
    assert (answered.status_code == 403) is refused, site


class _Untouched:
    """A service that fails the test if a route reaches it."""

    def __getattr__(self, name):
        def reached(*_args, **_kwargs):
            raise AssertionError(f"the route reached {name} with a non-digest")

        return reached


@pytest.fixture
def documents(monkeypatch) -> TestClient:
    """The api, with document services that must never be reached."""
    from api.main import app
    from api.routes import documents as routes

    monkeypatch.setattr(routes, "ingest_service", _Untouched())
    monkeypatch.setattr(routes, "removal_service", _Untouched())
    return TestClient(app, base_url=_OWN)


_NOT_A_DIGEST = st.text(
    alphabet=string.hexdigits + "gGxXzZ.-_ é%٠²", min_size=1, max_size=70
).filter(
    # A dot segment is resolved away by the client before any route sees it.
    lambda text: (
        text not in (".", "..")
        and not (len(text) == 64 and set(text) <= set("0123456789abcdef"))
    )
)


@_SHARED
@given(sha=_NOT_A_DIGEST)
@pytest.mark.parametrize(
    ("method", "suffix"),
    [("GET", "/file"), ("DELETE", ""), ("DELETE", "/derived")],
)
def test_a_document_route_refuses_anything_but_a_digest(
    documents, method, suffix, sha
) -> None:
    """400 invalid_digest, before any store or table is asked."""
    answered = documents.request(method, f"/documents/{quote(sha, safe='')}{suffix}")

    assert answered.status_code == 400, sha
    assert answered.json()["code"] == "invalid_digest"


def test_a_refused_path_cannot_start_a_line_of_its_own(documents, caplog) -> None:
    """One request, one log line, whatever its path decodes to.

    api.errors.refused logs the decoded path; a %0A in it reaches no log as
    a line break, here or under uvicorn.
    """
    forged = "x\n2026-10-21T00:00:00 INFO    ingestion.service stored forged.pdf"

    with caplog.at_level("WARNING", logger="api.errors"):
        documents.delete(f"/documents/{quote(forged, safe='')}")

    refusals = [r.getMessage() for r in caplog.records if r.name == "api.errors"]
    assert refusals, "nothing was refused"
    assert all("\n" not in message for message in refusals), refusals
