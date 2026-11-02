"""The web UI refuses what a page the operator opened can send, and still serves the UI."""

from __future__ import annotations

import warnings
from urllib.parse import quote

import pytest

pytest.importorskip("dagster_webserver", reason="the pipeline group is not installed")
pytestmark = pytest.mark.filterwarnings("ignore")

from starlette.testclient import TestClient

from orchestration.serve import guarded

MUTATION = "mutation { setAutoMaterializePaused(paused: true) }"
UNPAUSE = MUTATION.replace("true", "false")
READ = "{ instance { autoMaterializePaused } }"
OWN = {"Origin": "http://localhost:3000", "Sec-Fetch-Site": "same-origin"}


@pytest.fixture
def client():
    """Dagster's own application over an empty workspace, behind the guard."""
    from dagster._core.instance_for_test import instance_for_test
    from dagster._core.workspace.context import WorkspaceProcessContext
    from dagster._core.workspace.load_target import EmptyWorkspaceTarget
    from dagster_webserver.app import create_app_from_workspace_process_context

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with (
            instance_for_test() as instance,
            WorkspaceProcessContext(instance, EmptyWorkspaceTarget()) as context,
        ):
            served = TestClient(
                guarded(create_app_from_workspace_process_context(context)),
                base_url="http://localhost:3000",
            )
            # Unpaused through the UI's own path, so a mutation shows.
            served.post("/graphql", json={"query": UNPAUSE}, headers=OWN)
            yield served


def paused(client: TestClient) -> bool:
    """Whether auto-materialisation is paused, read as the UI reads it."""
    answer = client.post("/graphql", json={"query": READ}, headers=OWN)
    return answer.json()["data"]["instance"]["autoMaterializePaused"]


def test_a_cross_site_get_cannot_mutate(client: TestClient) -> None:
    """An `<img>` on another page."""
    answer = client.get(
        f"/graphql?query={quote(MUTATION)}", headers={"Sec-Fetch-Site": "cross-site"}
    )

    assert answer.status_code == 403
    assert paused(client) is False


@pytest.mark.parametrize(
    "origin", ["https://attacker.example", "http://localhost:8501"]
)
def test_a_foreign_origin_form_post_cannot_mutate(
    client: TestClient, origin: str
) -> None:
    """A no-cors form from another site or from the Streamlit port."""
    answer = client.post(
        f"/graphql?query={quote(MUTATION)}",
        content=b"x",
        headers={
            "Origin": origin,
            "Sec-Fetch-Site": "cross-site",
            "Content-Type": "text/plain",
        },
    )

    assert answer.status_code == 403
    assert paused(client) is False


def test_graphql_over_get_is_refused_even_without_headers(client: TestClient) -> None:
    """A tool that sends none of the browser's headers gets no query in a URL either."""
    assert client.get(f"/graphql?query={quote(READ)}").status_code == 403


def test_the_ui_posting_from_its_own_page_still_mutates(client: TestClient) -> None:
    """The same-origin request the UI sends."""
    client.post("/graphql", json={"query": MUTATION}, headers=OWN)

    assert paused(client) is True


def test_the_apis_call_by_service_name_still_runs() -> None:
    """No browser headers, and the compose service name as host."""
    from dagster._core.instance_for_test import instance_for_test
    from dagster._core.workspace.context import WorkspaceProcessContext
    from dagster._core.workspace.load_target import EmptyWorkspaceTarget
    from dagster_webserver.app import create_app_from_workspace_process_context

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with (
            instance_for_test() as instance,
            WorkspaceProcessContext(instance, EmptyWorkspaceTarget()) as context,
        ):
            client = TestClient(
                guarded(create_app_from_workspace_process_context(context)),
                base_url="http://dagster-webserver:3000",
            )
            answer = client.post("/graphql", json={"query": READ})

    assert answer.status_code == 200
    assert client.get("/server_info").status_code == 200


def test_a_foreign_host_name_is_refused(client: TestClient) -> None:
    """A rebinding page reaches the port under its own name."""
    answer = client.post(
        "/graphql", json={"query": READ}, headers={"Host": "rebind.example:3000"}
    )

    assert answer.status_code == 400


class _Echo:
    """An application that accepts a websocket and says hello."""

    async def __call__(self, scope, receive, send) -> None:
        """Accepts the handshake, sends once, and closes."""
        await receive()
        await send({"type": "websocket.accept"})
        await send({"type": "websocket.send", "text": "hello"})
        await send({"type": "websocket.close"})


def test_a_websocket_opened_from_another_origin_is_closed() -> None:
    """A browser applies no same-origin policy to a websocket: a page could stream run logs."""
    from starlette.websockets import WebSocketDisconnect

    from orchestration.serve import SameOrigin

    client = TestClient(SameOrigin(_Echo()))
    host = {"Host": "localhost:3000"}

    with pytest.raises(WebSocketDisconnect) as refused:
        with client.websocket_connect(
            "/graphql", headers={**host, "Origin": "https://evil.example"}
        ):
            pass
    assert refused.value.code == 1008

    with client.websocket_connect(
        "/graphql", headers={**host, "Origin": "http://localhost:3000"}
    ) as socket:
        assert socket.receive_text() == "hello"
    with client.websocket_connect("/graphql", headers=host) as socket:
        assert socket.receive_text() == "hello"
