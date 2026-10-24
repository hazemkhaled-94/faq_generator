"""The things parsing passes around."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Behind TYPE_CHECKING: the repository imports this module, and the API
    # imports the repository.
    from docling_core.types.doc.document import DoclingDocument


@dataclass(frozen=True)
class ClaimedDocument:
    """One document taken off the parsing queue.

    Attributes:
        sha256: The document's digest.
        media_type: Media type detected at ingest.
        page_count: Pages, counted at ingest.
        char_count: Characters in the text layer, counted at ingest.
    """

    sha256: str
    media_type: str
    page_count: int | None
    char_count: int | None


@dataclass(frozen=True)
class SourceDocument:
    """One stored file, as a pipeline receives it.

    Attributes:
        sha256: The document's digest.
        data: The raw file bytes.
        scanned: Whether the document carries too little text to read.
    """

    sha256: str
    data: bytes
    scanned: bool


@dataclass(frozen=True)
class Conversion:
    """What a pipeline produced from one file.

    Attributes:
        document: The converted document.
        confidence: Mean confidence the converter reported, or None.
        confidence_low: Confidence of its worst page, or None.
        unread_pages: 1-based pages that are a picture and carry no text
            layer, which the conversion could not read.
        interleaved: The pages set in columns that the converter read across,
            so a line of one column may run into one of the next.
        unseen_characters: How many characters no reader sees were left out
            of the document: invisible, in the paper's colour or too small.
        page_scores: Each page's own lower-bound confidence, by page number
            from 1, where the converter reports one.
        titles: What the document may be called, best first, as the file
            itself sets its type: a pipeline that reads none leaves it empty
            and the analyser reads the document's own headings.
    """

    document: DoclingDocument
    confidence: float | None
    confidence_low: float | None
    unread_pages: tuple[int, ...] = ()
    interleaved: tuple[int, ...] = ()
    unseen_characters: int = 0
    page_scores: tuple[tuple[int, float], ...] = ()
    titles: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedDocument:
    """One document as the pipeline understood it. Only what a column holds.

    Attributes:
        title: The document's own title, or None.
        language: ISO 639-1 code, or None when too short to tell.
        content_sha256: Digest of the normalised body text.
        page_count: Pages the converted document holds.
        confidence: Mean confidence the converter reported, or None.
        confidence_low: Confidence of its worst page, or None.
    """

    title: str | None
    language: str | None
    content_sha256: str
    page_count: int
    confidence: float | None
    confidence_low: float | None
