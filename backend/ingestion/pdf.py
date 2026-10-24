"""Reading a PDF's page and character counts."""

from __future__ import annotations

import logging
import time

import pymupdf

from ingestion.models import PdfFacts

log = logging.getLogger(__name__)


class UnreadablePdf(Exception):
    """Raised when a file cannot be opened and read as a PDF."""


def read_pdf(
    data: bytes, *, max_pages: int | None = None, seconds: float | None = None
) -> PdfFacts:
    """Opens a PDF and counts its pages and extractable characters.

    Args:
        data: The raw file bytes.
        max_pages: Refuse a document of more pages than this, before reading
            any of them. None sets no cap.
        seconds: Stop reading text once this long has passed. None sets no
            cap. Checked between pages, so one page that never returns is
            not interrupted.

    Returns:
        The page and character counts.

    Raises:
        UnreadablePdf: If the file is encrypted, corrupt, over a cap or
            otherwise cannot be opened. A cap is refused naming its setting.
    """
    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:
            if document.needs_pass:
                raise UnreadablePdf("the PDF is password protected")
            if max_pages is not None and document.page_count > max_pages:
                raise UnreadablePdf(
                    f"the PDF has {document.page_count} pages, above "
                    f"PARSING_MAX_PAGES={max_pages}"
                )
            deadline = None if seconds is None else time.monotonic() + seconds
            # Summed page by page, so no document's text is held all at once.
            characters = 0
            for page in document:
                characters += len(page.get_text())
                if deadline is not None and time.monotonic() >= deadline:
                    raise UnreadablePdf(
                        f"reading the PDF took longer than "
                        f"PARSING_TIMEOUT_SECONDS={seconds:g}"
                    )
            return PdfFacts(page_count=document.page_count, char_count=characters)
    except UnreadablePdf:
        raise
    except Exception as exc:
        log.warning("unreadable PDF: %s: %s", type(exc).__name__, exc)
        raise UnreadablePdf(f"the PDF could not be read: {exc}") from exc
