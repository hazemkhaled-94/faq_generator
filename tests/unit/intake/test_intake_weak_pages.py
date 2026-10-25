"""preprocessing-4: a page the converter is unsure of is named in the parse note.

The floor is read off the mean of the pages' lower bounds, so a few garbled
pages among many good ones pass it; the note says which they are.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from intake_drivers import ParseDriver, ScriptedPipeline
from test_intake_parsing import SHA, claimed

from preprocessing.parsing.pipelines.pdf import _page_scores


def scored(*lows: float | None) -> SimpleNamespace:
    """A conversion result whose pages have these lower-bound scores."""
    return SimpleNamespace(
        confidence=SimpleNamespace(
            pages={
                number: SimpleNamespace(low_score=low)
                for number, low in enumerate(lows, 1)
            }
        )
    )


def test_each_page_own_lower_bound_is_read() -> None:
    """Numbered from 1, in page order, a missing or NaN score left out."""
    result = scored(0.9, float("nan"), 0.0, None, 0.7)

    assert _page_scores(result) == ((1, 0.9), (3, 0.0), (5, 0.7))


def test_a_converter_with_no_page_scores_reads_as_none() -> None:
    """Nothing measured is not a page scored zero."""
    assert _page_scores(SimpleNamespace()) == ()


@pytest.mark.parametrize("pages", [(3,), (2, 7)])
def test_a_page_under_the_floor_is_named_though_the_document_passes(pages) -> None:
    """One garbled page among nine good ones: the mean of the lower bounds is 0.82."""
    scores = tuple((n, 0.0 if n in pages else 0.9) for n in range(1, 11))
    driver = ParseDriver(
        queued=(claimed(),), pipeline=ScriptedPipeline(page_scores=scores)
    )

    driver.run()

    assert SHA in driver.completed
    named = ", ".join(map(str, pages))
    assert f"page(s) {named}" in (driver.notes[SHA] or "")
    held = driver.parsed.metadata[driver.parsed.key_for(SHA)]
    assert held["low-confidence-pages"] == ",".join(map(str, pages))


def test_pages_all_above_the_floor_give_no_note() -> None:
    """Nothing to say, nothing recorded."""
    scores = tuple((n, 0.9) for n in range(1, 11))
    driver = ParseDriver(
        queued=(claimed(),), pipeline=ScriptedPipeline(page_scores=scores)
    )

    driver.run()

    assert driver.notes[SHA] is None
    held = driver.parsed.metadata[driver.parsed.key_for(SHA)]
    assert "low-confidence-pages" not in held


def test_both_kinds_of_page_are_in_one_note() -> None:
    """An unread picture page and a garbled one, each named."""
    driver = ParseDriver(
        queued=(claimed(),),
        pipeline=ScriptedPipeline(unread_pages=(2,), page_scores=((5, 0.1), (6, 0.9))),
    )

    driver.run()

    note = driver.notes[SHA] or ""
    assert "page(s) 2" in note
    assert "page(s) 5" in note


def test_the_characters_nobody_sees_are_counted_in_the_note() -> None:
    """A document that lost hidden text says how much."""
    driver = ParseDriver(
        queued=(claimed(),), pipeline=ScriptedPipeline(unseen_characters=235)
    )

    driver.run()

    assert "235 characters of text no reader can see" in (driver.notes[SHA] or "")
    held = driver.parsed.metadata[driver.parsed.key_for(SHA)]
    assert held["hidden-characters"] == "235"


def test_pages_read_across_their_columns_are_named_in_the_note() -> None:
    """Named, not reordered."""
    driver = ParseDriver(
        queued=(claimed(),), pipeline=ScriptedPipeline(interleaved=(3, 4))
    )

    driver.run()

    assert "page(s) 3, 4 are set in columns" in (driver.notes[SHA] or "")
    held = driver.parsed.metadata[driver.parsed.key_for(SHA)]
    assert held["interleaved-pages"] == "3,4"


def _pdf(*pages: str) -> bytes:
    """A PDF whose pages hold the given texts; an empty text is a blank page."""
    import pymupdf

    with pymupdf.open() as document:
        for text in pages:
            page = document.new_page()
            if text:
                page.insert_text((72, 100), text)
        return document.tobytes()


@pytest.mark.parametrize(
    "texts",
    [("Preisliste", "", "Zeilen"), ("Price list", "", "Rows")],
    ids=["german", "english"],
)
def test_a_blank_page_is_not_named_as_one_the_converter_is_unsure_of(texts) -> None:
    """A page that shows nothing has no text to be unsure of; a garbled one has."""
    from preprocessing.parsing.pipelines.pdf import _blank_pages

    blank = _blank_pages(_pdf(*texts))
    result = scored(0.0, 0.0, 0.0)

    assert blank == frozenset({2})
    assert _page_scores(result, blank) == ((1, 0.0), (3, 0.0))


def test_a_page_with_a_picture_and_no_text_is_not_blank() -> None:
    """A picture is something to read, so its score stands."""
    import pymupdf

    from preprocessing.parsing.pipelines.pdf import _blank_pages

    with pymupdf.open() as document:
        page = document.new_page()
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
        page.insert_image(pymupdf.Rect(50, 50, 150, 150), pixmap=pixmap)
        data = document.tobytes()

    assert _blank_pages(data) == frozenset()
