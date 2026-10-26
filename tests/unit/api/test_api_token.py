"""The shared secret every state-changing call to the api carries."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

WRITES = ["POST", "PUT", "PATCH", "DELETE"]
TOKEN = "t0ken-for-the-tests"


@pytest.fixture(autouse=True)
def _secret(monkeypatch) -> None:
    """The deployment's secret, as .env gives it."""
    monkeypatch.setenv("API_TOKEN", TOKEN)


@pytest.fixture
def guarded() -> TestClient:
    """The api's middleware in front of routes of every verb."""
    from api.main import app

    behind = FastAPI(middleware=app.user_middleware)

    @behind.api_route("/anything", methods=["GET", *WRITES])
    def anything() -> dict[str, bool]:
        return {"reached": True}

    @behind.api_route("/settings/{service}", methods=["GET"])
    def settings(service: str) -> dict[str, str]:
        return {"service": service}

    return TestClient(behind, base_url="http://localhost:8000")


@pytest.mark.parametrize("method", WRITES)
def test_a_write_without_the_secret_is_refused(guarded, method: str) -> None:
    """401, whatever the verb."""
    answered = guarded.request(method, "/anything")

    assert answered.status_code == 401
    assert answered.json()["code"] == "unauthorized"


@pytest.mark.parametrize("method", WRITES)
@pytest.mark.parametrize("wrong", ["", "t0ken", TOKEN + "x", "éè".encode("latin-1")])
def test_a_write_with_another_secret_is_refused(guarded, method, wrong) -> None:
    """Not a prefix, not an extension, not another alphabet."""
    answered = guarded.request(method, "/anything", headers={"x-api-token": wrong})

    assert answered.status_code == 401


@pytest.mark.parametrize("method", WRITES)
def test_a_write_with_the_secret_is_answered(guarded, method: str) -> None:
    """The frontend, the orchestrator and make send it."""
    answered = guarded.request(method, "/anything", headers={"x-api-token": TOKEN})

    assert answered.status_code == 200


def test_a_read_needs_no_secret(guarded) -> None:
    """GET routes are unchanged."""
    assert guarded.get("/anything").status_code == 200


def test_the_settings_are_read_with_the_secret_only(guarded) -> None:
    """They name every model and path the deployment runs."""
    assert guarded.get("/settings/platform").status_code == 401
    answered = guarded.get("/settings/platform", headers={"x-api-token": TOKEN})
    assert answered.status_code == 200


def test_a_deployment_with_no_secret_refuses_every_write(guarded, monkeypatch) -> None:
    """Closed, not open: an unset secret is a misconfiguration."""
    monkeypatch.delenv("API_TOKEN")

    assert guarded.post("/anything").status_code == 401
    assert guarded.post("/anything", headers={"x-api-token": ""}).status_code == 401


@pytest.mark.parametrize("name", ["QA_MODEL", "NLI_MODEL", "EMBEDDING_MODEL"])
def test_a_model_the_workers_load_is_not_written_at_run_time(name: str) -> None:
    """The deployment's, like the models LLM_MODEL names."""
    from settings import catalog

    assert catalog.BY_NAME[name].fixed is True


def test_the_weights_path_is_not_written_at_run_time() -> None:
    """A path the converter loads code and weights from."""
    from settings import catalog

    assert catalog.BY_NAME["DOCLING_ARTIFACTS_PATH"].fixed is True


def _declared(operation: dict, schemes: dict) -> set[tuple[str, str]]:
    """Where and under what name an operation's declared security sends a key."""
    return {
        (schemes[name]["in"], schemes[name]["name"])
        for requirement in operation.get("security", [])
        for name in requirement
    }


def test_the_docs_page_sends_the_secret_where_the_api_asks_for_it() -> None:
    """Swagger's Authorize sends X-API-Token on a write and a settings read, not elsewhere."""
    from api.main import app

    document = app.openapi()
    schemes = document["components"]["securitySchemes"]
    paths = document["paths"]

    assert _declared(paths["/documents"]["post"], schemes) == {
        ("header", "X-API-Token")
    }
    assert _declared(paths["/settings/{service}"]["get"], schemes) == {
        ("header", "X-API-Token")
    }
    assert _declared(paths["/documents"]["get"], schemes) == set()


def test_what_asks_for_the_secret_documents_the_401_it_answers() -> None:
    """A caller, and schemathesis, read the refusal off the document."""
    from api.main import app

    document = app.openapi()
    paths = document["paths"]
    refused = paths["/settings/{service}"]["get"]["responses"]["401"]
    reference = refused["content"]["application/json"]["schema"]["$ref"]

    assert "401" in paths["/documents"]["post"]["responses"]
    assert "401" not in paths["/documents"]["get"]["responses"]
    assert reference.rsplit("/", 1)[-1] in document["components"]["schemas"]
