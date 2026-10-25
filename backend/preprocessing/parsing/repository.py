"""Database access for the parsing service."""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy import select
from sqlalchemy.orm import InstrumentedAttribute

from database.qa_generator import Document, Status
from preprocessing.parsing.models import ClaimedDocument, ParsedDocument
from settings.runs import run_id
from stages import Columns, RowQueue
from telemetry.evaluations import current_ids

#: The next document to parse. FOR UPDATE SKIP LOCKED, so a second worker
#: takes the following row rather than blocking on this one.
_NEXT_PENDING = (
    select(Document.sha256)
    .where(Document.parse_status == Status.PENDING)
    .order_by(Document.sha256)
    .with_for_update(skip_locked=True)
    .limit(1)
    .scalar_subquery()
)


class ParseQueue(RowQueue):
    """Reads the parsing queue and records what became of each document."""

    #: This stage's columns on `documents`.
    columns = Columns(
        entity=Document,
        key=Document.sha256,
        status=Document.parse_status,
        error=Document.parse_error,
        claimed_at=Document.parse_claimed_at,
        trigger=Document.parse_trigger,
    )
    #: The narrowings this stage accepts.
    scopes: ClassVar[dict[str, InstrumentedAttribute]] = {"document": Document.sha256}
    done = Status.PARSED
    next_pending = _NEXT_PENDING

    def claim(self) -> ClaimedDocument | None:
        """Takes the next pending document off the queue.

        Returns:
            The claimed document, or None when the queue is empty.
        """
        claimed = self._claim(
            Document.sha256,
            Document.mime_type,
            Document.page_count,
            Document.char_count,
        )
        if claimed is None:
            return None
        return ClaimedDocument(
            sha256=claimed.sha256,
            media_type=claimed.mime_type,
            page_count=claimed.page_count,
            char_count=claimed.char_count,
        )

    def exists(self, sha256: str) -> bool:
        """Whether the document row is still there, or was deleted meanwhile."""
        with self._session() as session:
            return self._exists(session, sha256)

    def holder_of(self, content_sha256: str, besides: str) -> str | None:
        """Names another document holding this exact text, if one does.

        Args:
            content_sha256: Digest of the normalised body text.
            besides: The document being parsed, which is excluded.

        Returns:
            The other document's digest, or None.
        """
        with self._session() as session:
            return session.scalar(
                select(Document.sha256).where(
                    Document.content_sha256 == content_sha256,
                    Document.sha256 != besides,
                )
            )

    def title_held(self, title: str, besides: str) -> bool:
        """Whether another document is already called this.

        Args:
            title: The title a document is about to take.
            besides: The document being parsed, which is excluded.
        """
        with self._session() as session:
            return (
                session.scalar(
                    select(Document.sha256)
                    .where(Document.title == title, Document.sha256 != besides)
                    .limit(1)
                )
                is not None
            )

    def complete(
        self, sha256: str, parsed: ParsedDocument, note: str | None = None
    ) -> None:
        """Records a successful parse, releasing the claim.

        Writes the title, language, content digest and both confidences.
        page_count is ingestion's column and chunk_status is chunking's;
        neither is touched, so re-parsing leaves the old passages standing
        until somebody asks for them to be rebuilt.

        Args:
            sha256: The document's digest.
            parsed: What the analyser read.
            note: What the parse could not read, shown where a failure's reason
                would be, or None.
        """
        trace_id, span_id = current_ids()
        self._finish(
            sha256,
            note=note,
            title=parsed.title,
            language=parsed.language,
            content_sha256=parsed.content_sha256,
            parse_confidence=parsed.confidence,
            parse_confidence_low=parsed.confidence_low,
            parse_run_id=run_id(),
            parse_trace_id=trace_id or None,
            parse_span_id=span_id or None,
        )
