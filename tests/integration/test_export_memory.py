"""What an export holds at once, and how many questions it can name.

The workbook was built whole: every row a frame, then the file. An export of
the user's ten-times corpus passes the api's 512 MB, and the judge's
verdicts were asked for with one bound parameter per question id, which
libpq refuses past 65,535 of them.
"""

from __future__ import annotations

import io
import tracemalloc

import pytest
from openpyxl import load_workbook
from seed import digest, document, fact, passage
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from assessment.repository import AssessmentCatalog
from database.qa_generator import Document, Fact
from question_generation.catalog import QuestionCatalog
from question_generation.export import write

pytestmark = pytest.mark.integration


def _seed(engine, count: int) -> list[int]:
    """`count` more questions of two languages, each resting on one fact.

    The document, passage and fact are written by the first call and shared
    by every call after it.
    """
    with Session(engine) as session:
        if session.get(Document, digest("shop")) is None:
            session.add(document(digest("shop"), title="Gebührenordnung"))
            session.flush()
            held = passage(digest("shop"), text="Die Kontoführung kostet 4,90 EUR.")
            session.add(held)
            session.flush()
            session.add(fact(held.id, statement="Die Kontoführung kostet 4,90 EUR."))
            session.commit()
        fact_id = session.scalars(select(Fact.id)).one()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO questions (question_text, answerable, language) "
                "SELECT CASE WHEN g % 2 = 0 THEN 'Was kostet Konto ' ELSE "
                "'What does account ' END || g, true, "
                "CASE WHEN g % 2 = 0 THEN 'de' ELSE 'en' END "
                "FROM generate_series(1, :n) AS g"
            ),
            {"n": count},
        )
        connection.execute(
            text(
                "INSERT INTO question_facts (question_id, fact_id) "
                "SELECT id, :fact FROM questions WHERE id NOT IN "
                "(SELECT question_id FROM question_facts)"
            ),
            {"fact": fact_id},
        )
        return list(
            connection.execute(text("SELECT id FROM questions ORDER BY id")).scalars()
        )


def _peak(path) -> int:
    """The most Python memory one export of everything held asks for."""
    catalog = QuestionCatalog()
    assessments = AssessmentCatalog()
    tracemalloc.start()
    try:
        with catalog.snapshot() as read, open(path, "wb") as handle:
            write(
                handle,
                catalog.stream(read=read),
                catalog.citations(read=read),
                catalog.quality(read=read),
                lambda ids: assessments.verdicts_for("question", ids),
            )
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_an_export_holds_a_batch_and_not_the_corpus(engine, database, tmp_path) -> None:
    """Ten times the questions, about the same peak."""
    _seed(engine, 1_000)
    small = _peak(tmp_path / "small.xlsx")
    _seed(engine, 9_000)
    large = _peak(tmp_path / "large.xlsx")

    assert large < 2.5 * small, f"{small:,} bytes for 1,000, {large:,} for 10,000"


def test_seventy_thousand_ids_are_looked_up_in_one_statement(engine, database) -> None:
    """The judge's verdicts for every question of a very large export."""
    ids = _seed(engine, 70_000)

    assert AssessmentCatalog().verdicts_for("question", ids) == {}


def test_an_export_of_seventy_thousand_questions_completes(
    engine, database, tmp_path
) -> None:
    """Rows, citations and the Summary that counts them."""
    _seed(engine, 70_000)
    out = tmp_path / "all.xlsx"
    catalog = QuestionCatalog()
    assessments = AssessmentCatalog()

    with catalog.snapshot() as read, open(out, "wb") as handle:
        write(
            handle,
            catalog.stream(read=read),
            catalog.citations(read=read),
            catalog.quality(read=read),
            lambda ids: assessments.verdicts_for("question", ids),
        )

    book = load_workbook(io.BytesIO(out.read_bytes()), read_only=True)
    # A read-only sheet trims a row after its last value, so a row with no
    # count has one cell.
    summary = {
        row[0]: row[1] if len(row) > 1 else None
        for row in list(book["Summary"].iter_rows(values_only=True))[1:]
    }
    assert summary["Questions in this workbook"] == 70_000
    assert summary["Citation rows"] == 70_000
