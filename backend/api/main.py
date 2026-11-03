"""The backend's HTTP surface, and the only address the frontend holds.

Assembles the application. Wiring is in dependencies; endpoints are in
routes/.
"""

from __future__ import annotations

import hmac
import logging
import os
from collections.abc import Mapping
from typing import Any, Protocol

from fastapi import FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from starlette.datastructures import Headers
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from api import errors
from api.routes import ROUTERS
from settings.env import csv

log = logging.getLogger(__name__)

#: The methods whose `Origin` is not judged: they change nothing.
_READS = frozenset({"GET", "HEAD", "OPTIONS"})

#: The Swagger UI the docs page loads, by exact version. FastAPI's own page
#: asks the CDN for `swagger-ui-dist@5`, which is whatever was last published
#: under 5, so a release nobody here has seen would run on the api's origin.
#: A published version never changes.
_SWAGGER_UI = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.33.3"


def _guarded(method: str, path: str) -> bool:
    """Whether `SharedSecret` asks a request for the secret.

    `path` is the one routing reads: the request's, less any root path.
    """
    return method.upper() not in _READS or path.startswith("/settings")


def _routed(scope: Scope) -> str:
    """The path routing matches, as Starlette reads it: less the root path."""
    path, root = scope["path"], scope.get("root_path", "")
    if root and path.startswith(root) and path[len(root) : len(root) + 1] in ("", "/"):
        return path[len(root) :]
    return path


class Authenticator(Protocol):
    """Decides whether a request may go on.

    One port for what guards the api: today a shared secret, behind an ingress
    that signs users in a token's validation (Entra ID). `headers` are the
    request's, lower-cased; `path` is the one routing reads.
    """

    def allows(self, headers: Mapping[str, str], method: str, path: str) -> bool:
        """Whether the request carries what its method and path need."""
        ...


class TokenAuthenticator:
    """One shared secret, `API_TOKEN`, as `X-API-Token` on writes and settings reads.

    Read per request, and closed when unset: an api with no secret is a
    misconfiguration, not an open one. So is the placeholder `.env.example`
    ships, a value starting `change_me_`, which is printed in the repository.
    """

    #: What `make setup` replaces and `.env.example` ships.
    PLACEHOLDER = "change_me_"

    def __init__(self) -> None:
        """Starts unwarned."""
        self._warned = False

    def _secret(self) -> bytes:
        """The secret, or nothing when there is none worth having."""
        secret = os.environ.get("API_TOKEN", "")
        if secret.startswith(self.PLACEHOLDER):
            if not self._warned:
                self._warned = True
                log.warning(
                    "API_TOKEN is still the placeholder %s...; every write is "
                    "refused until `make setup` or an edit of .env replaces it",
                    self.PLACEHOLDER,
                )
            return b""
        return secret.encode()

    def allows(self, headers: Mapping[str, str], method: str, path: str) -> bool:
        """Whether the secret came, where one is asked for."""
        if not _guarded(method, path):
            return True
        secret = self._secret()
        sent = headers.get("x-api-token", "").encode("latin-1")
        return bool(secret) and hmac.compare_digest(sent, secret)


def authenticator() -> Authenticator:
    """The adapter API_AUTH names, `token` unless told otherwise.

    Raises:
        ValueError: If it names none that exists.
    """
    # Empty is unset: compose hands an unset name over as "".
    adapter = os.environ.get("API_AUTH", "").strip() or "token"
    if adapter == "token":
        return _TOKEN
    raise ValueError(
        f"API_AUTH={adapter!r} names no adapter; the one there is is token"
    )


#: One instance, so the placeholder is reported once per process.
_TOKEN = TokenAuthenticator()


class SharedSecret:
    """Refuses a write, and any read of the settings, the authenticator does not allow.

    The frontend, the orchestrator and the make targets send the token as
    `X-API-Token`; see `TokenAuthenticator`, which is today's adapter.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wraps the application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Answers 401 `unauthorized`, or hands the request on."""
        if scope["type"] == "http" and not authenticator().allows(
            Headers(scope=scope), scope["method"], _routed(scope)
        ):
            refusal = errors.ApiError(
                401,
                "unauthorized",
                "send the deployment's API_TOKEN as X-API-Token",
            )
            answer = await errors.refused(Request(scope), refusal)
            await answer(scope, receive, send)
            return
        await self.app(scope, receive, send)


class SameOriginWrites:
    """Refuses a request a browser sent from another site or another port.

    Any method: a read is what an `<img>` or a `fetch` on a page the operator
    opened can send, and the export and the quality report cost the api its
    memory. A write is also judged by its `Origin`. The one page left open is
    `/docs`, which the System health page links to and a browser sends from
    that page's port. A caller that is not a browser sends neither header and
    passes.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wraps the application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Answers 403 `cross_site_write`, or hands the request on."""
        if scope["type"] == "http" and scope["path"] != "/docs":
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            if headers.get("sec-fetch-site") in ("cross-site", "same-site") or (
                scope["method"] not in _READS
                and origin is not None
                and origin != f"{scope['scheme']}://{headers.get('host')}"
            ):
                refusal = errors.ApiError(
                    403, "cross_site_write", "a browser sent this from another origin"
                )
                answer = await errors.refused(Request(scope), refusal)
                await answer(scope, receive, send)
                return
        await self.app(scope, receive, send)


app = FastAPI(
    title="FAQ Generator API",
    # /docs is served below, from pinned assets, and ReDoc not at all.
    docs_url=None,
    redoc_url=None,
    middleware=[
        Middleware(TrustedHostMiddleware, allowed_hosts=csv("API_ALLOWED_HOSTS")),
        Middleware(SameOriginWrites),
        Middleware(SharedSecret),
    ],
)

errors.install(app)


def _openapi() -> dict[str, Any]:
    """The schema, declaring X-API-Token on what `SharedSecret` guards.

    So /docs offers Authorize and sends the secret on a write and a settings
    read, and each of those names the 401 it answers without it; the
    middleware is what checks it.
    """
    if app.openapi_schema is None:
        document = FastAPI.openapi(app)
        document.setdefault("components", {})["securitySchemes"] = {
            "APIToken": {"type": "apiKey", "in": "header", "name": "X-API-Token"}
        }
        refused = {
            "description": "unauthorized: no X-API-Token, or not the deployment's",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorBody"}
                }
            },
        }
        for path, verbs in document["paths"].items():
            for method, operation in verbs.items():
                if _guarded(method, path):
                    operation["security"] = [{"APIToken": []}]
                    operation.setdefault("responses", {})["401"] = refused
    return app.openapi_schema or {}


app.openapi = _openapi


@app.get("/docs", include_in_schema=False)
def docs() -> HTMLResponse:
    """Swagger UI on the api's schema."""
    return get_swagger_ui_html(
        openapi_url=app.openapi_url or "",
        title=f"{app.title} - Swagger UI",
        swagger_js_url=f"{_SWAGGER_UI}/swagger-ui-bundle.js",
        swagger_css_url=f"{_SWAGGER_UI}/swagger-ui.css",
    )


for router in ROUTERS:
    app.include_router(router)
