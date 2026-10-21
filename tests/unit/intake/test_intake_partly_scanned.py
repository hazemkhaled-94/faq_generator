"""preprocessing-6: a scanned page inside a digital PDF is named, not lost silently."""

from __future__ import annotations

import pymupdf
import pytest
from intake_drivers import ParseDriver, ScriptedPipeline
from test_intake_parsing import SHA, claimed

from preprocessing.parsing.pipelines.pdf import image_only_pages

#: PARSING_OCR_CHAR_THRESHOLD as shipped: fewer characters than this on a page
#: that a picture covers is a scan with a stamp on it.
OCR_CHARS = 100

TEXT = {
    "de": "Die Kontoführung kostet 4,90 EUR im Monat. Die Debitkarte kostet 10 EUR im Jahr. ",
    "en": "Standard delivery costs 4.95 EUR. Returns are free of charge within 30 days. ",
}


def _picture() -> pymupdf.Pixmap:
    picture = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 100), 0)
    for x in range(200):
        for y in range(100):
            picture.set_pixel(x, y, ((x * 7) % 256, (y * 5) % 256, 180))
    return picture


def _pdf(language: str, kinds: str) -> bytes:
    """One page per letter: t text, s scan (full-page picture), l text with a logo, b blank."""
    pdf = pymupdf.open()
    for kind in kinds:
        page = pdf.new_page(width=595, height=842)
        if kind in "tl":
            page.insert_textbox(
                pymupdf.Rect(50, 50, 545, 700), TEXT[language] * 12, fontsize=10
            )
        if kind == "s":
            page.insert_image(page.rect, pixmap=_picture(), keep_proportion=False)
        if kind == "l":
            page.insert_image(pymupdf.Rect(480, 760, 545, 800), pixmap=_picture())
    return pdf.tobytes()


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_page_with_a_picture_and_no_text_is_named(language) -> None:
    """The mean hides it: the other pages' text lifts it over the threshold."""
    assert image_only_pages(_pdf(language, "tstst")) == (2, 4)


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_logo_or_a_blank_page_is_not_a_scan(language) -> None:
    """Text beside a small picture, and a page with nothing, lose no text."""
    assert image_only_pages(_pdf(language, "tlb")) == ()


@pytest.mark.parametrize("language", ["de", "en"])
def test_overlapping_pictures_are_not_counted_twice(language) -> None:
    """One picture over a third of the page, placed twice, still covers a third."""
    pdf = pymupdf.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_image(
        pymupdf.Rect(0, 0, 595, 300), pixmap=_picture(), keep_proportion=False
    )
    page.insert_image(
        pymupdf.Rect(0, 0, 595, 300), pixmap=_picture(), keep_proportion=False
    )
    assert image_only_pages(pdf.tobytes()) == ()


def _stamped_scan(stamp: str | None) -> bytes:
    """Three pages; page 2 is a full-page picture, optionally stamped as text."""
    pdf = pymupdf.open(stream=_pdf("de", "tst"), filetype="pdf")
    if stamp:
        pdf[1].insert_text((480, 830), stamp, fontsize=8)
    return pdf.tobytes()


@pytest.mark.parametrize("stamp", ["Seite 2 von 3", "Page 2", "Anlage 2"])
def test_a_scanned_page_carrying_a_stamped_line_is_named(stamp) -> None:
    """A merge tool's page number puts text on the page; its picture is still unread."""
    assert image_only_pages(_stamped_scan(None), OCR_CHARS) == (2,)
    assert image_only_pages(_stamped_scan(stamp), OCR_CHARS) == (2,)


def test_a_page_of_text_with_a_picture_over_half_of_it_is_not_named() -> None:
    """Text above the threshold is a text page whatever else covers it."""
    pdf = pymupdf.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_textbox(pymupdf.Rect(50, 50, 545, 400), TEXT["de"] * 12, fontsize=10)
    page.insert_image(
        pymupdf.Rect(0, 420, 595, 842), pixmap=_picture(), keep_proportion=False
    )
    assert image_only_pages(pdf.tobytes(), OCR_CHARS) == ()


def test_the_service_warns_and_records_the_named_pages(caplog) -> None:
    """A partly scanned document is parsed, and says which pages it lost."""
    driver = ParseDriver(
        queued=(claimed(),), pipeline=ScriptedPipeline(unread_pages=(2, 4))
    )

    with caplog.at_level("WARNING"):
        driver.run()

    assert SHA in driver.completed
    assert "no text layer on page(s) 2, 4" in caplog.text
    assert "page(s) 2, 4" in (driver.notes[SHA] or "")
    assert (
        driver.parsed.metadata[driver.parsed.key_for(SHA)]["image-only-pages"] == "2,4"
    )


def test_a_document_without_such_pages_is_recorded_as_before(caplog) -> None:
    """No warning, no extra metadata."""
    driver = ParseDriver(queued=(claimed(),))

    with caplog.at_level("WARNING"):
        driver.run()

    assert "no text layer" not in caplog.text
    assert driver.notes[SHA] is None
    assert "image-only-pages" not in driver.parsed.metadata[driver.parsed.key_for(SHA)]
