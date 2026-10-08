"""The backend's HTTP surface, and the only address the frontend holds.

Assembles the application. Wiring is in dependencies; endpoints are in
routes/.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from starlette.datastructures import Headers
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from api import errors
from api.routes import ROUTERS
from settings.env import csv

#: The methods a browser may send from another site.
_READS = frozenset({"GET", "HEAD", "OPTIONS"})


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
    title="qa_generator API",
    middleware=[
        Middleware(TrustedHostMiddleware, allowed_hosts=csv("API_ALLOWED_HOSTS")),
        Middleware(SameOriginWrites),
    ],
)

errors.install(app)

for router in ROUTERS:
    app.include_router(router)
