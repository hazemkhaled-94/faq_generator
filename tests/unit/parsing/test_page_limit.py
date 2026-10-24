"""A document longer than the parse worker can hold is refused before conversion.

Docling holds every page it converts, and the worker's memory limit is what
ends a conversion that does not fit: the container is killed and the claim
sits until a sweep. Measured offline, converting the 139-page Laws of the
Game took 2.4 GB of resident memory, and a document twice as long 4.9 GB, the
parse worker's limit being 4 GB. `PARSING_MAX_PAGES` is the longest document
the worker takes, and the refusal names it.
"""

from __future__ import annotations

import hashlib

import pymupdf
import pytest

from preprocessing.parsing.config import Settings
from preprocessing.parsing.models import SourceDocument
from preprocessing.parsing.pipelines import ConversionFailed, PdfPipeline

#: One line of body text per language the corpus is configured for.
LINES = {"de": "Die Karte kostet 25 Euro im Jahr.", "en": "Orders can be returned."}


def _pdf(pages: int, line: str) -> bytes:
    """A PDF of this many pages, the first of them carrying a line of text."""
    document = pymupdf.open()
    for number in range(pages):
        page = document.new_page()
        if number == 0:
            page.insert_text((72, 72), line)
    return document.tobytes()


def _pipeline(max_pages: int) -> PdfPipeline:
    return PdfPipeline(
        table_mode="fast",
        heading_hierarchy=False,
        document_timeout_seconds=60,
        artifacts_path=None,
        max_pages=max_pages,
    )


def _source(data: bytes) -> SourceDocument:
    return SourceDocument(
        sha256=hashlib.sha256(data).hexdigest(), data=data, scanned=False
    )


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_thousand_page_pdf_is_refused_before_conversion(
    monkeypatch, language
) -> None:
    """The refusal names the count, the limit and the setting; nothing is converted."""
    pipeline = _pipeline(200)
    monkeypatch.setattr(
        pipeline, "_converter", lambda: pytest.fail("converted a refused document")
    )

    with pytest.raises(ConversionFailed) as refused:
        pipeline.convert(_source(_pdf(1_000, LINES[language])))

    message = str(refused.value)
    assert "PARSING_MAX_PAGES" in message
    assert "1000" in message.replace(",", "") and "200" in message


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_pdf_within_the_limit_is_converted(monkeypatch, language) -> None:
    """A ten-page document reaches the converter, as one at the limit does."""

    def reached():
        raise RuntimeError("reached the converter")

    for pages in (10, 200):
        pipeline = _pipeline(200)
        monkeypatch.setattr(pipeline, "_converter", reached)

        with pytest.raises(ConversionFailed, match="reached the converter") as raised:
            pipeline.convert(_source(_pdf(pages, LINES[language])))

        assert "PARSING_MAX_PAGES" not in str(raised.value)


def test_a_limit_of_zero_takes_every_document(monkeypatch) -> None:
    """Off, as the pipeline was built before the setting."""

    def reached():
        raise RuntimeError("reached the converter")

    pipeline = _pipeline(0)
    monkeypatch.setattr(pipeline, "_converter", reached)

    with pytest.raises(ConversionFailed, match="reached the converter"):
        pipeline.convert(_source(_pdf(300, LINES["en"])))


def test_the_shipped_limit_takes_the_longest_document_of_the_corpus() -> None:
    """139 pages are the Laws of the Game, 2.4 GB converted; the shipped limit is above them."""
    assert Settings.load().max_pages >= 139


def test_the_shipped_limit_sits_under_the_worker_s_memory() -> None:
    """Measured: 139 pages 2.4 GB, 278 pages 4.9 GB, against the worker's 4 GB."""
    assert Settings.load().max_pages < 250


def test_the_limit_is_read_from_the_environment(monkeypatch) -> None:
    """One name, in the file the worker reads."""
    monkeypatch.setenv("PARSING_MAX_PAGES", "7")

    assert Settings.load().max_pages == 7
