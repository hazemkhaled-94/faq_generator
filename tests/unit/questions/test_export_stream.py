"""The workbook written as it is read, and what that changes about its cells.

One pass over rows that are drawn a batch at a time: text that starts like a
formula is marked text, the page columns are numbers, a sheet that would
pass Excel's row limit goes on in a numbered one, and nothing is asked for
or held beyond a batch.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from openpyxl import load_workbook
from test_export import _Judged, _Metric, cited, stored

from question_generation import export
from question_generation.export import workbook, write


def _rows(drawn: bytes, sheet: str) -> list[dict]:
    """One sheet's rows by heading."""
    book = load_workbook(io.BytesIO(drawn))
    head, *rows = book[sheet].iter_rows(values_only=True)
    return [dict(zip(head, row, strict=True)) for row in rows]


@pytest.mark.parametrize(
    "text",
    [
        "- Rückgabe innerhalb von 14 Tagen\n- Erstattung binnen 7 Tagen",
        "- Returns within 14 days\n- Refund within 7 days",
        "+41 44 245 00 00",
        "@support",
        "=SUM(A1:A2)",
    ],
)
def test_a_cell_starting_like_a_formula_or_a_sign_is_marked_as_text(text) -> None:
    """Edited, or saved as CSV and opened again, it would otherwise be live."""
    book = load_workbook(io.BytesIO(workbook([stored(target_answer=text)])))
    sheet = book["Questions"]
    head = [one.value for one in sheet[1]]
    cell = sheet.cell(row=2, column=head.index("Answer") + 1)

    assert cell.value == text
    assert cell.data_type == "s"
    assert cell.quotePrefix is True


@pytest.mark.parametrize("text", ["Rückgabe nach 14 Tagen", "Returns after 14 days"])
def test_ordinary_text_is_not_marked(text) -> None:
    """Only a cell that could be read as something else."""
    book = load_workbook(io.BytesIO(workbook([stored(target_answer=text)])))
    sheet = book["Questions"]
    head = [one.value for one in sheet[1]]

    assert sheet.cell(row=2, column=head.index("Answer") + 1).quotePrefix is False


@pytest.mark.parametrize(
    ("first", "last", "expected"),
    [(3, 5, (3, 5)), (2, 2, (2, 2)), (None, None, (None, None))],
)
def test_the_pages_are_two_integer_columns(first, last, expected) -> None:
    """One type to a column, so it sorts and filters as numbers."""
    (row,) = _rows(
        workbook(
            [stored()],
            [cited(first_page=first, last_page=last, document="Gebührenordnung")],
        ),
        "Citations",
    )

    assert (row["First page"], row["Last page"]) == expected
    assert "Page" not in row


def test_a_sheet_that_would_pass_the_row_limit_goes_on_in_a_numbered_one(
    monkeypatch,
) -> None:
    """With the header repeated, and every row once."""
    monkeypatch.setattr(export, "_SHEET_ROWS", 3)
    citations = [cited(fact_id=one) for one in range(1, 8)]

    book = load_workbook(io.BytesIO(workbook([stored()], citations)))

    assert [name for name in book.sheetnames if name.startswith("Citations")] == [
        "Citations",
        "Citations 2",
        "Citations 3",
    ]
    heads = {tuple(c.value for c in book[name][1]) for name in book.sheetnames[-2:]}
    assert len(heads) == 1
    column = [one.value for one in book["Citations"][1]].index("Fact ID")
    held = [
        row[column]
        for name in ("Citations", "Citations 2", "Citations 3")
        for row in book[name].iter_rows(min_row=2, values_only=True)
    ]
    assert held == list(range(1, 8))
    summary = {
        row[0]: row[1] for row in list(book["Summary"].iter_rows(values_only=True))[1:]
    }
    assert summary["Citation rows"] == 7


def test_the_real_row_limit_is_excels() -> None:
    """1,048,576 rows, less the heading."""
    assert export._SHEET_ROWS == 1_048_576 - 1


def test_questions_are_asked_about_in_batches_and_drawn_lazily() -> None:
    """The judge is asked for a batch at a time, and rows are taken as needed."""
    drawn: list[int] = []
    asked: list[int] = []

    def rows():
        for one in range(1, 1251):
            drawn.append(one)
            yield stored(one)

    def verdicts(ids: list[int]) -> dict:
        """Records the batch, and what had been drawn when it was asked."""
        asked.append(len(ids))
        assert len(drawn) == ids[-1], "rows were drawn past the batch asked for"
        return {}

    buffer = io.BytesIO()
    write(buffer, rows(), (), None, verdicts)

    assert asked == [500, 500, 250]
    assert len(_rows(buffer.getvalue(), "Questions")) == 1250


def test_a_judged_question_reads_the_same_from_a_mapping_and_from_a_lookup() -> None:
    """Either way the verdict, its reasons and the Assessment rows are written."""
    refused = _Metric("answerable", "no", False, "the passages do not say")
    mapping = {1: _Judged(refused)}

    by_mapping = workbook([stored(1), stored(2)], judged=mapping)
    by_lookup = workbook(
        [stored(1), stored(2)],
        judged=lambda ids: {i: mapping[i] for i in ids if i in mapping},
    )

    for drawn in (by_mapping, by_lookup):
        questions = _rows(drawn, "Questions")
        assert [one["Judge"] for one in questions] == ["refused", "not judged"]
        assert len(_rows(drawn, "Assessment")) == 1


def test_the_export_path_builds_no_frame() -> None:
    """A frame of every row is what held the whole corpus in the api."""
    source = Path(export.__file__).read_text()

    assert "pandas" not in source
    assert "DataFrame" not in source


def test_the_ids_of_a_lookup_are_one_array_not_one_parameter_each() -> None:
    """Libpq takes 65,535 parameters in a statement; an export has more ids."""
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    from assessment.repository import _among
    from database.qa_generator import Assessment

    compiled = str(
        select(Assessment.id)
        .where(_among(Assessment.id, list(range(70_000))))
        .compile(dialect=postgresql.dialect())
    )

    assert "ANY (" in compiled
    assert " IN " not in compiled


def test_seventy_thousand_ids_bind_one_parameter() -> None:
    """One array, not one placeholder each."""
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    from assessment.repository import _among
    from database.qa_generator import Assessment

    compiled = (
        select(Assessment.id)
        .where(_among(Assessment.id, list(range(70_000))))
        .compile(dialect=postgresql.dialect())
    )

    assert len(compiled.params) == 1


def test_the_kind_heading_says_what_kind_means() -> None:
    """A tester reads single on every question with no answer and asks why.

    The note on the heading says: the span of the answer's passages, which a
    question with no answer has none of, so Answerable is filtered first.
    """
    book = load_workbook(io.BytesIO(workbook([stored()])))
    sheet = book["Questions"]
    (kind,) = [cell for cell in sheet[1] if cell.value == "Kind"]

    assert kind.comment is not None
    note = kind.comment.text
    assert "span of the answer's passages" in note
    assert "single" in note and "Answerable" in note
    assert all(cell.comment is None for cell in sheet[1] if cell.value != "Kind")


def _peak(count: int) -> int:
    """The most Python memory writing `count` questions from a generator asks for."""
    import tracemalloc

    def rows():
        for one in range(1, count + 1):
            yield stored(one, question_text=f"Which fee applies to account {one}?")

    tracemalloc.start()
    try:
        write(io.BytesIO(), rows(), (), None, lambda ids: {})
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_twenty_thousand_questions_are_held_a_batch_at_a_time() -> None:
    """Ten times the questions, about the same peak, and well under the api's 512 MB."""
    small = _peak(2_000)
    large = _peak(20_000)

    assert large < 2.5 * small, f"{small:,} bytes for 2,000, {large:,} for 20,000"
    assert large < 100 * 1024 * 1024


@pytest.mark.parametrize(
    ("language", "key", "explanation"),
    [
        ("de", "- Visum\n- Mastercard", "+49 30 1234 Erreichbarkeit der Bank"),
        ("en", "- Visa\n- Mastercard", "+44 20 7946 0000 for the helpdesk"),
        ("fr", "- Carte bleue\n- Virement", "@conseiller de la banque"),
        ("el", "- Κάρτα\n- Έμβασμα", "=SUM(A1) δεν είναι τύπος"),
    ],
)
def test_text_opening_with_a_formula_sign_round_trips_as_text(
    language, key, explanation
) -> None:
    """Any language: the sign decides, never a word."""
    book = load_workbook(
        io.BytesIO(
            workbook(
                [
                    stored(
                        target_answer=key,
                        answer_explanation=explanation,
                        language=language,
                    )
                ]
            )
        )
    )
    sheet = book["Questions"]
    head = [one.value for one in sheet[1]]
    for heading, text in (("Answer", key), ("Answer in full", explanation)):
        cell = sheet.cell(row=2, column=head.index(heading) + 1)
        assert cell.value == text
        assert cell.data_type == "s"
        assert cell.quotePrefix is True


@pytest.mark.parametrize(
    ("language", "turn"),
    [
        ("de", "Wie lange gilt die Frist? "),
        ("en", "How long does the deadline apply? "),
        ("fr", "Quel est le délai pour un virement ? "),
        ("el", "Ποια είναι η προθεσμία; "),
    ],
)
def test_every_long_cell_is_cut_and_marked(language, turn) -> None:
    """The columns filled from a lookup, not only the ones read off the row."""
    from types import SimpleNamespace as N

    long = turn * 1500
    metric = N(
        metric="faithfulness",
        label="no",
        explanation=turn * 2000,
        approved=False,
        score=0.0,
    )
    judged = {
        2: N(
            approved=False,
            refused=("faithfulness",),
            metrics=[metric],
            judge_model="a-model",
            prompt_version="1",
            disagrees=True,
        )
    }
    book = load_workbook(
        io.BytesIO(
            workbook(
                [stored(2, follows_id=1, thread_position=2, language=language)],
                judged=judged,
                earlier={2: [(long, long)]},
            )
        )
    )
    sheet = book["Questions"]
    head = [one.value for one in sheet[1]]
    for heading in ("Earlier turns", "Why the judge said so"):
        value = sheet.cell(row=2, column=head.index(heading) + 1).value
        assert str(value).endswith("[truncated]"), heading
        assert len(value) <= export._CELL_LIMIT + len("… [truncated]")
    why = [row[5] for row in book["Assessment"].iter_rows(min_row=2, values_only=True)]
    assert why and str(why[0]).endswith("[truncated]")
