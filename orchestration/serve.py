"""Serves Dagster's web UI behind the checks the api makes of a browser.

`dagster-webserver` reads a GraphQL query from the URL of a GET and from a POST
whose body is not JSON, and looks at no `Origin`, `Sec-Fetch-Site` or `Host`. A
page the operator has open could then launch the corpus job or stop a run with
an `<img>` or a form, one hop past the api's own same-origin check. This wraps
Dagster's application in a host check and a same-origin check and hands it to
the same command line, so the options are the ones the plain command takes:

    python -m orchestration.serve -h 0.0.0.0 -p 3000 -w workspace.yaml
"""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocketClose

#: The names the UI is reached by: from the host, and from the api, which calls
#: it by its compose service name.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "dagster-webserver"]

_READS = ("GET", "HEAD", "OPTIONS")


class SameOrigin:
    """Refuses GraphQL over GET and a write a browser sent from another origin.

    The UI queries and mutates with POST from its own page, so a request that
    the browser marks `cross-site` or `same-site` (another port is the same
    site), or that carries an `Origin` other than the host it was sent to, is
    not the UI's. A caller that is not a browser sends neither header.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wraps the application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Answers 403, closes a foreign websocket handshake, or hands the request on."""
        if scope["type"] == "websocket":
            # A browser applies no same-origin policy to a websocket: its Origin
            # is the only thing that says which page opened it.
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            if origin is not None and urlsplit(origin).netloc != headers.get("host"):
                await WebSocketClose(1008)(scope, receive, send)
                return
        if scope["type"] == "http":
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            if scope["method"] in _READS:
                refused = scope["path"].rstrip("/") == "/graphql" and (
                    scope["method"] == "GET"
                )
            else:
                refused = headers.get("sec-fetch-site") in (
                    "cross-site",
                    "same-site",
                ) or (
                    origin is not None
                    and origin != f"{scope['scheme']}://{headers.get('host')}"
                )
            if refused:
                answer = PlainTextResponse(
                    "a browser sent this from another origin", status_code=403
                )
                await answer(scope, receive, send)
                return
        await self.app(scope, receive, send)


def guarded(app: ASGIApp) -> ASGIApp:
    """Dagster's application, behind the host check and the same-origin check."""
    return TrustedHostMiddleware(SameOrigin(app), allowed_hosts=ALLOWED_HOSTS)


def main() -> None:
    """Runs `dagster-webserver` with its application guarded."""
    from dagster_webserver import cli

    name = "create_app_from_workspace_process_context"
    build = getattr(cli, name)
    setattr(cli, name, lambda *args, **kwargs: guarded(build(*args, **kwargs)))
    cli.main()


if __name__ == "__main__":
    main()
