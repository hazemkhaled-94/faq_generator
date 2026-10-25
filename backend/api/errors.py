"""The shape every refusal from this API takes.

Each deliberate refusal answers with a stable `code` beside its message, so a
caller can branch on the code rather than on English. The codes are the
ingest outcomes and validation failures named elsewhere in the project.

Two things are left alone: FastAPI's own 422 for a malformed query keeps its
standard shape, and a stage's own failures are recorded against the row and
read back through its status rather than answered here.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ErrorBody:
    """What a refused request is answered with."""

    code: str
    detail: str


class ApiError(Exception):
    """A refusal answered as an :class:`ErrorBody` at a chosen status.

    Raised instead of `HTTPException` so the body carries a code.
    """

    def __init__(self, status: int, code: str, detail: str) -> None:
        """Initialises the refusal."""
        super().__init__(detail)
        self.status = status
        self.body = ErrorBody(code=code, detail=detail)


async def refused(request: Request, exc: ApiError) -> JSONResponse:
    """Renders one refusal, and records it.

    One line here rather than one at each `raise`: every deliberate
    refusal passes through, so the code a caller branched on is also
    the code a dashboard can count. At warning, not error - a 404 for
    an unknown id is the API working.
    """
    log.warning(
        "%s %s refused: %s",
        request.method,
        request.url.path,
        exc.body.code,
        extra={
            "http.request.method": request.method,
            "url.path": request.url.path,
            "http.response.status_code": exc.status,
            "error.code": exc.body.code,
        },
    )
    return JSONResponse(status_code=exc.status, content=asdict(exc.body))


class _Escaped(JSONResponse):
    """JSON escaped to ASCII, so any text it echoes can be sent."""

    def render(self, content: Any) -> bytes:
        """The body, with every character past ASCII written as an escape."""
        return json.dumps(content, allow_nan=False, separators=(",", ":")).encode()


async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI's own 422, in its own shape, rendered ASCII-escaped.

    It echoes the input it refused, and one holding a lone surrogate, which
    a JSON escape carries, is text UTF-8 cannot encode: rendered as FastAPI
    renders it, the refusal answered 500.
    """
    return _Escaped(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


async def stored_refused(request: Request, exc: Exception) -> JSONResponse:
    """A stored setting the catalogue now refuses, which a route built on.

    The 503 the upload answers, for every route that reads its settings
    through the audit the stages build through - the enrolment's among them.
    """
    return await refused(request, ApiError(503, "stored_setting_refused", str(exc)))


def install(app: FastAPI) -> None:
    """Teaches an application to answer :class:`ApiError` with its body."""
    from settings.store import StoredRefused

    app.exception_handler(ApiError)(refused)
    app.exception_handler(RequestValidationError)(invalid)
    app.exception_handler(StoredRefused)(stored_refused)
