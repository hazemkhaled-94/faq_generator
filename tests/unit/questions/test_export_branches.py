"""Two shapes the workbook meets rarely, each one a reader would notice.

A document title or a section heading is a document's own text, and the
columns that hold them are not wrapped: one that starts like a formula is
still written as text. A verdict recorded before the judge's model and
template were stored names neither as "None".
"""

from __future__ import annotations

import io

import pandas as pd
from openpyxl import load_workbook
from test_export import _Judged, _Metric, cited, sheets, stored

from question_generation.export import workbook


def test_a_title_or_heading_that_starts_like_a_formula_is_written_as_text() -> None:
    """German and English titles, a Greek heading: never a live formula."""
    titles = {
        "=HYPERLINK(\"http://x\",\"Preisverzeichnis\")": "-Kontoführung",
        "+Terms of sale": "@Returns",
        "-Τιμολόγιο": "=1+1",
    }
    drawn = workbook(
        [stored()],
        [
            cited(fact_id=index, document=title, section_path=heading)
            for index, (title, heading) in enumerate(titles.items(), start=1)
        ],
    )
    sheet = load_workbook(io.BytesIO(drawn))["Citations"]
    headings = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
    rows = list(sheet.iter_rows(min_row=2))
    written = {
        (row[headings.index("Document")], row[headings.index("Section")])
        for row in rows
    }

    assert {(one.value, two.value) for one, two in written} == set(titles.items())
    assert {cell.data_type for pair in written for cell in pair} == {"s"}


def test_a_verdict_with_no_recorded_judge_names_none_in_the_summary() -> None:
    """Counted as judged; the judge's model and template are left blank."""
    verdict = _Judged(_Metric("groundedness", "supported", True, "Gedeckt."))
    verdict.judge_model = None
    verdict.prompt_version = None

    summary = sheets(workbook([stored()], [cited()], judged={1: verdict}))["Summary"]
    notes = dict(zip(summary["Measure"], summary["Note"], strict=True))
    counted = dict(zip(summary["Measure"], summary["Count"], strict=True))

    assert counted["Judged by a model"] == 1
    assert pd.isna(notes["Judge model"])
    assert pd.isna(notes["Judge template"])

