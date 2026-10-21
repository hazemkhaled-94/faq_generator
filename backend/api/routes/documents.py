"""Routes served by the ingestion service."""

from __future__ import annotations

import re
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import APIRouter, Request, Response, UploadFile
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool

from api.dependencies import ingest_service, ingesting, removal_service
from api.errors import ApiError, ErrorBody
from api.params import Limit, Offset, SearchText
from database.qa_generator import Outcome
from ingestion.models import (
    DocumentName,
    IngestResult,
    Removal,
    StoredDocument,
    UploadedFile,
)

#: Declared on the routes that can raise them, so a refusal appears in the
#: OpenAPI document.
_REFUSALS = {code: {"model": ErrorBody} for code in (400, 404, 411, 413, 415)}

#: Ingest outcomes that are refusals. Anything absent answers 200; a
#: duplicate is an answer, not an error.
_ERROR_STATUS: dict[str, int] = {
    Outcome.TOO_LARGE: 413,
    Outcome.UNSUPPORTED_TYPE: 415,
}

#: What a digest looks like. Checked before a path parameter becomes part of
#: an object key.
_DIGEST = re.compile(r"[0-9a-f]{64}")

#: The states `parse_status` may be narrowed to. A Literal rather than a free
#: string, so the OpenAPI document lists them and the frontend's picker cannot
#: drift from what the backend accepts.
ParseStatus = Literal["new", "pending", "in_progress", "parsed", "failed"]

router = APIRouter(tags=["documents"])


@dataclass(frozen=True)
class DocumentPage:
    """One page of documents."""

    total: int
    documents: list[StoredDocument]


@router.get("/documents")
def list_documents(
    q: SearchText = None,
    parse_status: ParseStatus | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> DocumentPage:
    """Lists stored documents and where each has reached in the pipeline."""
    total, rows = ingest_service.documents(q, limit, offset, parse_status)
    return DocumentPage(total=total, documents=rows)


@router.get("/documents/names")
def document_names() -> list[DocumentName]:
    """Lists every document by name, for a picker to offer.

    Separate from `/documents` because the three pages that draw that picker
    need no passage counts, and aggregating them on every poll is the most
    expensive query the frontend makes.
    """
    return ingest_service.document_names()


@router.get(
    "/documents/{sha256}/file",
    responses={code: _REFUSALS[code] for code in (400, 404)},
)
def document_file(sha256: str) -> Response:
    """Serves one stored document, exactly as it was uploaded.

    Raises:
        ApiError: 400 `invalid_digest` if it is not a digest, 404
            `unknown_document` if no document has it.
    """
    data, media_type = _found(sha256, ingest_service.stored_file)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{sha256[:12]}.pdf"'},
    )


@router.delete(
    "/documents/{sha256}", responses={code: _REFUSALS[code] for code in (400, 404)}
)
def delete_document(sha256: str) -> Removal:
    """Deletes a document, its file, its converted form and its derived rows.

    Archived on the way out: the rows into `archived_rows` and the objects
    into the archive bucket, until `make archive-purge` takes them. The
    upload record in ingest_events survives here regardless.

    Raises:
        ApiError: 400 `invalid_digest` if it is not a digest, 404
            `unknown_document` if no document has it.
    """
    return _found(sha256, removal_service.delete)


@router.delete(
    "/documents/{sha256}/derived",
    responses={code: _REFUSALS[code] for code in (400, 404)},
)
def delete_derived(sha256: str) -> Removal:
    """Deletes what the pipeline built from a document, keeping the document.

    The file and the converted form stay and chunking returns to `new`, so
    the next run rebuilds the passages and facts without re-parsing once
    somebody starts it.

    Raises:
        ApiError: 400 `invalid_digest` if it is not a digest, 404
            `unknown_document` if no document has it.
    """
    return _found(sha256, removal_service.delete_derived)


def _found[T](sha256: str, read: Callable[[str], T | None]) -> T:
    """Validates a digest and answers what the given read found under it.

    Raises:
        ApiError: 400 if the digest is not one, 404 if nothing has it.
    """
    if not _DIGEST.fullmatch(sha256):
        raise ApiError(400, "invalid_digest", "not a SHA-256 digest")
    found = read(sha256)
    if found is None:
        raise ApiError(404, "unknown_document", "no document with that digest")
    return found


def add_document(file: UploadFile) -> IngestResult:
    """Accepts one uploaded document, synchronously.

    A plain function, so FastAPI runs it off the event loop: the ingest
    queries the database, hashes and writes the object store. Its declared
    size is checked first, before the form is parsed.

    Everything after this is batch work the workers pick up by watching
    documents.parse_status.

    Raises:
        ApiError: 400 `invalid_value` if the filename holds a NUL byte, which
            no text column can store. 413 `too_large` if the file is over the
            size limit, 415 `unsupported_type` if it is not a readable
            document of an accepted type. Each of those two codes is the
            ingest outcome itself.
    """
    filename = file.filename or "unnamed"
    # A browser percent-encodes one; only a hand-made request sends it raw.
    if "\x00" in filename:
        raise ApiError(400, "invalid_value", "a filename may not hold a NUL byte")
    # Per upload: ingestion has no worker to pick a changed limit up.
    service = ingesting()

    # One byte past the limit at most, which `ingest` refuses as too large.
    read = file.file.read(service.max_file_size_bytes + 1)
    return _respond(service.ingest(UploadedFile(filename=filename, data=read)))


class _DeclaredSize(APIRoute):
    """A route that checks the declared size before the form is parsed."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """Runs `_refuse_by_declared_size` ahead of FastAPI's own handler."""
        handler = super().get_route_handler()

        async def checked(request: Request) -> Response:
            await run_in_threadpool(_refuse_by_declared_size, request)
            return await handler(request)

        return checked


router.add_api_route(
    "/documents",
    add_document,
    methods=["POST"],
    responses={code: _REFUSALS[code] for code in (400, 411, 413, 415)},
    route_class_override=_DeclaredSize,
)


#: The most a multipart body adds around the file: boundaries and the part's
#: headers.
_FRAMING = 64 * 1024


def _refuse_by_declared_size(request: Request) -> None:
    """Refuses an upload by the size it declares, before its body is read.

    Content-Length covers the whole multipart body, so it is an upper bound
    rather than the file's size: past the limit by more than the framing,
    and `ingest` holds the file itself to the limit exactly. The filename is
    in the body, so a refusal here is recorded as "unnamed".

    Raises:
        ApiError: 411 `length_required` if it declares no Content-Length,
            413 `too_large` if it declares more than the limit and the
            framing.
    """
    declared = _declared_size(request)
    if declared is None:
        raise ApiError(411, "length_required", "an upload must declare its length")
    service = ingesting()
    if declared > service.max_file_size_bytes + _FRAMING:
        _respond(service.refuse_oversized("unnamed", declared))


def _declared_size(request: Request) -> int | None:
    """Reads the size the request declares for its body."""
    declared = request.headers.get("content-length")
    return int(declared) if declared is not None and declared.isdigit() else None


def _respond(result: IngestResult) -> IngestResult:
    """Passes an accepted outcome through, or raises the matching error.

    Raises:
        ApiError: If the outcome was a refusal. The outcome doubles as the
            code.
    """
    if result.outcome in _ERROR_STATUS:
        raise ApiError(
            _ERROR_STATUS[result.outcome], result.outcome, result.detail or ""
        )
    return result
