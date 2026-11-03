"""What every authenticator adapter does, run against each one there is.

`TokenAuthenticator` is today's: one shared secret. The fake stands for the
shape an Entra ID adapter has, a bearer token a validator accepts, and shows
the port asks nothing of the headers but what the adapter reads from them.
An adapter is chosen by `API_AUTH`.
"""

from __future__ import annotations

import pytest

from api import main
from api.main import TokenAuthenticator

SECRET = "s3cret-for-the-tests"


class BearerAuthenticator:
    """Accepts `Authorization: Bearer <a token it issued>` on a write or a settings read."""

    ISSUED = "issued-by-the-directory"

    def allows(self, headers, method, path) -> bool:
        """Whether the bearer token is one it knows, where one is asked for."""
        if method in ("GET", "HEAD", "OPTIONS") and not path.startswith("/settings"):
            return True
        return headers.get("authorization") == f"Bearer {self.ISSUED}"


ADAPTERS = {
    "token": (TokenAuthenticator, {"x-api-token": SECRET}),
    "bearer": (
        BearerAuthenticator,
        {"authorization": f"Bearer {BearerAuthenticator.ISSUED}"},
    ),
}


@pytest.fixture(params=ADAPTERS)
def adapter(request, monkeypatch):
    """Each adapter in turn, with the credential it accepts."""
    monkeypatch.setenv("API_TOKEN", SECRET)
    build, credential = ADAPTERS[request.param]
    return build(), credential


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_a_write_needs_the_credential(adapter, method) -> None:
    """Refused without, and with a credential that is not the one."""
    allowing, credential = adapter

    assert not allowing.allows({}, method, "/documents")
    assert not allowing.allows(
        {"x-api-token": "no", "authorization": "Bearer no"}, method, "/documents"
    )
    assert allowing.allows(credential, method, "/documents")


def test_a_read_of_the_documents_is_open_and_a_read_of_the_settings_is_not(
    adapter,
) -> None:
    """The one read that names every model and path the deployment runs."""
    allowing, credential = adapter

    assert allowing.allows({}, "GET", "/questions")
    assert not allowing.allows({}, "GET", "/settings/platform")
    assert allowing.allows(credential, "GET", "/settings/platform")


def test_the_middleware_asks_the_adapter_api_auth_names(monkeypatch) -> None:
    """`token` is the default; an unknown name is refused."""
    monkeypatch.delenv("API_AUTH", raising=False)
    assert isinstance(main.authenticator(), TokenAuthenticator)
    # compose hands an unset name over empty
    monkeypatch.setenv("API_AUTH", "")
    assert isinstance(main.authenticator(), TokenAuthenticator)

    monkeypatch.setenv("API_AUTH", "entra")
    with pytest.raises(ValueError, match="API_AUTH"):
        main.authenticator()


def test_a_fake_authenticator_decides_what_the_middleware_lets_through(
    monkeypatch,
) -> None:
    """The middleware holds no rule of its own."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main, "authenticator", BearerAuthenticator)
    behind = FastAPI(middleware=main.app.user_middleware)

    @behind.post("/anything")
    def anything() -> dict[str, bool]:
        return {"reached": True}

    client = TestClient(behind, base_url="http://localhost:8000")

    assert client.post("/anything").status_code == 401
    assert (
        client.post(
            "/anything", headers={"authorization": "Bearer issued-by-the-directory"}
        ).status_code
        == 200
    )
