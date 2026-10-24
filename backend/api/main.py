"""The backend's HTTP surface, and the only address the frontend holds.

Assembles the application. Wiring is in dependencies; endpoints are in
routes/.
"""

from __future__ import annotations

import hmac
import os

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

#: The methods a browser may send from another site.
_READS = frozenset({"GET", "HEAD", "OPTIONS"})

#: The Swagger UI the docs page loads, by exact version. FastAPI's own page
#: asks the CDN for `swagger-ui-dist@5`, which is whatever was last published
#: under 5, so a release nobody here has seen would run on the api's origin.
#: A published version never changes.
_SWAGGER_UI = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.33.3"


class SharedSecret:
    """Refuses a write, and any read of the settings, that lacks the secret.

    `API_TOKEN` comes from `.env`, where `make setup` generates it, and the
    frontend, the orchestrator and the make targets send it as `X-API-Token`.
    Read per request, and closed when unset: an api with no secret is a
    misconfiguration, not an open one.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wraps the application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Answers 401 `unauthorized`, or hands the request on."""
        if scope["type"] == "http" and (
            scope["method"] not in _READS or scope["path"].startswith("/settings")
        ):
            secret = os.environ.get("API_TOKEN", "").encode()
            sent = Headers(scope=scope).get("x-api-token", "").encode("latin-1")
            if not secret or not hmac.compare_digest(sent, secret):
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
    """Refuses a write a browser sent from another site or another port.

    A caller that is not a browser sends neither header and passes.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wraps the application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Answers 403 `cross_site_write`, or hands the request on."""
        if scope["type"] == "http" and scope["method"] not in _READS:
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            if headers.get("sec-fetch-site") in ("cross-site", "same-site") or (
                origin is not None
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
