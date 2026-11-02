"""The parsing flow: claim, dispatch, convert, store, analyse, record."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from functools import partial
from importlib.metadata import version
from typing import ClassVar, Protocol

from opentelemetry.trace import Span

from preprocessing.parsing.analysis import (
    AlreadyHeld,
    DocumentAnalyser,
    EmptyDocument,
    UnconfiguredLanguage,
    Unconvincing,
)
from preprocessing.parsing.models import (
    ClaimedDocument,
    ParsedDocument,
    SourceDocument,
)
from preprocessing.parsing.pipelines import (
    ConversionFailed,
    PipelineRegistry,
    UnsupportedFormat,
)
from preprocessing.parsing.repository import ParseQueue
from stages import Gone, StageService
from telemetry import tracer, working

log = logging.getLogger(__name__)
span = tracer(__name__)

#: The Docling release this process converts with.
_DOCLING = version("docling")


class SourceStore(Protocol):
    """What this service needs from the store holding source documents."""

    def key_for(self, sha256: str, media_type: str) -> str:
        """Returns the key a document of this type is stored under."""
        ...

    def get(self, key: str) -> bytes:
        """Reads an object."""
        ...


class ParsedStore(Protocol):
    """What this service needs from the store holding converted documents."""

    def key_for(self, sha256: str) -> str:
        """Returns the key a converted document is stored under."""
        ...

    def find(self, key: str) -> bytes | None:
        """Reads an object, or None if it is not there."""
        ...

    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str,
        metadata: dict[str, str],
    ) -> None:
        """Stores an object under `key`."""
        ...

    def remove(self, key: str) -> bool:
        """Deletes an object, reporting whether one was there."""
        ...


class ParsingService(StageService):
    """Converts stored documents into structured ones, one at a time.

    The order is fixed: dispatch on the media type recorded at ingest,
    convert, store the converted document, and only then read out of it.
    A re-parse stores only once the checks pass, so a refusal leaves the
    earlier converted document in place.

    Work arrives through documents.parse_status.
    """

    name: ClassVar[str] = "parsing"
    unit: ClassVar[str] = "document"

    def __init__(
        self,
        *,
        repository: ParseQueue,
        documents: SourceStore,
        parsed: ParsedStore,
        pipelines: PipelineRegistry,
        analyser: DocumentAnalyser,
        ocr_char_threshold: int,
        min_confidence: float,
    ) -> None:
        """Initialises the service with its collaborators.

        Args:
            repository: The parsing queue.
            documents: Where the uploaded files are.
            parsed: Where the converted documents go.
            pipelines: One pipeline per media type.
            analyser: Reads the converted document.
            ocr_char_threshold: Characters per page below which a document
                counts as scanned.
            min_confidence: Lowest confidence a conversion may carry.
        """
        super().__init__(repository)
        self._repository: ParseQueue = repository
        self._documents = documents
        self._parsed = parsed
        self._pipelines = pipelines
        self._analyser = analyser
        self._ocr_char_threshold = ocr_char_threshold
        self._min_confidence = min_confidence

    def process_next(self) -> str | None:
        """Parses one queued document.

        A failure is recorded against the document rather than raised.

        Returns:
            The digest of the document worked, or None when the queue is
            empty.
        """
        document = self._repository.claim()
        if document is None:
            return None

        with working(
            span,
            "parse",
            {
                "stage": self.name,
                "document.sha256": document.sha256,
                "document.media_type": document.media_type,
            },
        ) as current:
            try:
                self._parse(document, current)
            except Gone as exc:
                current.set_attribute("stage.name", self.name)
                current.set_attribute("stage.outcome", "deleted")
                log.info("%s: %s", self.name, exc)
            except (
                UnsupportedFormat,
                ConversionFailed,
                EmptyDocument,
                UnconfiguredLanguage,
                Unconvincing,
                AlreadyHeld,
            ) as exc:
                self._fail(document.sha256, str(exc), current)
            except Exception as exc:
                self._fail(document.sha256, f"{type(exc).__name__}: {exc}", current)
                log.exception("failed %s", document.sha256)
        return document.sha256

    def _parse(self, document: ClaimedDocument, current: Span) -> None:
        """Runs one claimed document through its pipeline.

        Args:
            document: The document taken off the queue.
            current: The span to annotate.

        Raises:
            UnsupportedFormat: If no pipeline handles the media type.
            ConversionFailed: If the pipeline could not convert the file.
            EmptyDocument: If the conversion yielded no body text.
            UnconfiguredLanguage: If the text is in a language not configured.
            Unconvincing: If the conversion's confidence is below the floor.
            AlreadyHeld: If another document holds the same text.
        """
        pipeline = self._pipelines.for_media_type(document.media_type)
        scanned = self._is_scanned(document)
        current.set_attribute("parse.pipeline", type(pipeline).__name__)
        current.set_attribute("parse.scanned", scanned)

        data = self._documents.get(
            self._documents.key_for(document.sha256, document.media_type)
        )
        converted = pipeline.convert(
            SourceDocument(sha256=document.sha256, data=data, scanned=scanned)
        )

        note = None
        if converted.unread_pages:
            pages = ", ".join(map(str, converted.unread_pages))
            note = (
                f"no text layer on page(s) {pages}, which hold only a picture "
                "and are not read without OCR, so their text is missing"
            )
            current.set_attribute("parse.image_only_pages", pages)
            log.warning("parsed %s: %s", document.sha256, note)

        weak = [
            number
            for number, score in converted.page_scores
            if score < self._min_confidence
        ]
        if weak:
            pages = ", ".join(map(str, weak))
            warning = (
                f"the converter is unsure of page(s) {pages}: each one's own "
                f"lower bound is under the {self._min_confidence:.2f} floor, "
                "which only the mean of the pages' lower bounds is held to"
            )
            note = f"{note}; {warning}" if note else warning
            current.set_attribute("parse.low_confidence_pages", pages)
            log.warning("parsed %s: %s", document.sha256, warning)

        if converted.interleaved:
            pages = ", ".join(map(str, converted.interleaved))
            mixed = (
                f"page(s) {pages} are set in columns the converter read across, "
                "so a line of one column may run into one of the next"
            )
            note = f"{note}; {mixed}" if note else mixed
            current.set_attribute("parse.interleaved_pages", pages)
            log.warning("parsed %s: %s", document.sha256, mixed)

        if converted.unseen_characters:
            hidden = (
                f"{converted.unseen_characters} characters of text no reader can "
                "see (invisible, in the colour of the paper or under 2 points) "
                "were left out"
            )
            note = f"{note}; {hidden}" if note else hidden
            current.set_attribute(
                "parse.hidden_characters", converted.unseen_characters
            )
            log.warning("parsed %s: %s", document.sha256, hidden)

        key = self._parsed.key_for(document.sha256)
        store = partial(
            self._parsed.put,
            key,
            json.dumps(
                converted.document.export_to_dict(), ensure_ascii=False
            ).encode(),
            content_type="application/json",
            metadata={
                "sha256": document.sha256,
                "docling-version": _DOCLING,
                **(
                    {"image-only-pages": ",".join(map(str, converted.unread_pages))}
                    if converted.unread_pages
                    else {}
                ),
                **({"low-confidence-pages": ",".join(map(str, weak))} if weak else {}),
                **(
                    {"interleaved-pages": ",".join(map(str, converted.interleaved))}
                    if converted.interleaved
                    else {}
                ),
                **(
                    {"hidden-characters": str(converted.unseen_characters)}
                    if converted.unseen_characters
                    else {}
                ),
            },
        )
        # ponytail: downloads the earlier object only to learn it exists; a
        # head request on the bucket is the upgrade.
        earlier = self._parsed.find(key) is not None
        if not earlier:
            self._stay(document.sha256)
            store()

        parsed = self._analyser.analyse(converted)
        self._trustworthy(parsed)
        self._unheld(document.sha256, parsed)
        parsed = self._distinct(document.sha256, parsed, converted.titles)
        if earlier:
            self._stay(document.sha256)
            store()
        try:
            self._repository.complete(document.sha256, parsed, note)
        except Gone:
            # Deleted since the check: what was just written belongs to no row.
            self._parsed.remove(key)
            raise

        self._done(current)
        current.set_attribute("parse.pages", parsed.page_count)
        if parsed.confidence is not None:
            current.set_attribute("parse.confidence", parsed.confidence)
        log.info(
            "parsed %s: %d pages, language=%s, confidence=%s, title=%r",
            document.sha256,
            parsed.page_count,
            parsed.language,
            "n/a" if parsed.confidence is None else f"{parsed.confidence:.3f}",
            parsed.title,
        )

    def _stay(self, sha256: str) -> None:
        """Refuses to write for a document whose row has been deleted.

        Raises:
            Gone: If the row is not there. A converted document written now
                would be an object no row names.
        """
        if not self._repository.exists(sha256):
            raise Gone(f"{sha256} was deleted while this worker held it")

    def _trustworthy(self, parsed: ParsedDocument) -> None:
        """Refuses a conversion whose lower-bound confidence is under the floor.

        Args:
            parsed: What the analyser read.

        Raises:
            Unconvincing: If the lower bound is under PARSING_MIN_CONFIDENCE.
        """
        measured = parsed.confidence_low
        if measured is not None and measured < self._min_confidence:
            raise Unconvincing(
                f"the converter puts this document's confidence at "
                f"{measured:.2f}, under the {self._min_confidence:.2f} floor. "
                "Everything drawn from it would be built on text nothing "
                "vouches for. Lower PARSING_MIN_CONFIDENCE to accept it."
            )

    def _distinct(
        self, sha256: str, parsed: ParsedDocument, titles: tuple[str, ...]
    ) -> ParsedDocument:
        """Tells a document from one already called the same.

        The title another document holds gets the next candidate the file
        offers added to it, as `Title - Next`; with none that is free the
        title stays, for it still names the document.
        """
        title = parsed.title
        if title is None or not self._repository.title_held(title, sha256):
            return parsed
        for other in titles:
            if other != title and not self._repository.title_held(
                f"{title} - {other}", sha256
            ):
                return replace(parsed, title=f"{title} - {other}")
        return parsed

    def _unheld(self, sha256: str, parsed: ParsedDocument) -> None:
        """Refuses a document whose text the corpus already holds.

        Args:
            sha256: The document being parsed.
            parsed: What the analyser read.

        Raises:
            AlreadyHeld: If another document has the same content digest.
        """
        held = self._repository.holder_of(parsed.content_sha256, besides=sha256)
        if held:
            raise AlreadyHeld(
                f"document {held[:12]} already holds this exact text. Parsing "
                "it again would count every fact and every topic membership "
                "twice. Delete whichever copy you do not want."
            )

    def _is_scanned(self, document: ClaimedDocument) -> bool:
        """Decides whether a document carries a text layer worth reading.

        Read from the counts ingestion already took.

        Args:
            document: The document taken off the queue.

        Returns:
            True when there is less than PARSING_OCR_CHAR_THRESHOLD of text
            per page, or nothing was counted.
        """
        if document.char_count is None or not document.page_count:
            return True
        return document.char_count / document.page_count < self._ocr_char_threshold
