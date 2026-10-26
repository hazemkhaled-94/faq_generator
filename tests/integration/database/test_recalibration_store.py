"""Taking every stored margin again, against the database it rewrites.

The arithmetic is `tests/unit/test_confidence.py`'s and the rebuilding of
one stored reading is `tests/unit/stages/test_recalibrate.py`'s. What is
only checkable here is the write: that it moves the two columns it is
about and no others, and that a second run writes nothing.
"""

from __future__ import annotations

import pytest
from seed import digest, document, fact, passage, question
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.qa_generator import Fact, Question, QuestionStatus
from stages.recalibrate import recalibrate

pytestmark = pytest.mark.integration

#: A reading as rows were written before the direction was recorded: four
#: keys, and a margin taken as a share of the whole unit interval.
UNCALIBRATED = {
    "gate": "near_duplicate",
    "value": 0.88,
    "threshold": 0.93,
    "margin": 0.0538,
}


@pytest.fixture
def stored(engine, database):
    """One question and one fact, each carrying an uncalibrated reading."""
    sha = digest("a")
    with Session(engine) as session:
        session.add(document(sha))
        session.flush()
        session.add(passage(sha))
        session.flush()
        held = passage(sha, ordinal=2)
        session.add(held)
        session.flush()
        session.add(
            fact(
                held.id,
                gate_scores=[{**UNCALIBRATED, "gate": "duplicate", "threshold": 0.95}],
                confidence=0.0632,
            )
        )
        session.add(
            question(
                status=QuestionStatus.ACCEPTED,
                gate_scores=[dict(UNCALIBRATED)],
                confidence=0.0538,
            )
        )
        session.commit()
    return sha


def test_a_stored_margin_is_taken_again_against_where_the_scale_ends(
    engine, stored
) -> None:
    """The defect this exists for: 0.05 of the room a cosine really has."""
    written = recalibrate(Question, floor=0.75)

    assert written == 1
    with Session(engine) as session:
        row = session.scalars(select_one(Question)).one()
        assert row.confidence == pytest.approx(0.2778, abs=1e-3)
        assert row.gate_scores[0]["margin"] == pytest.approx(0.2778, abs=1e-3)


def test_the_reading_it_rewrites_keeps_what_was_measured(engine, stored) -> None:
    """Only the margin moves.

    A recalibration that touched a value or a threshold would be changing
    what the gate read rather than how close it came, and no verdict could
    be re-derived from the row afterwards.
    """
    recalibrate(Question, floor=0.75)

    with Session(engine) as session:
        reading = session.scalars(select_one(Question)).one().gate_scores[0]
        assert reading["value"] == UNCALIBRATED["value"]
        assert reading["threshold"] == UNCALIBRATED["threshold"]


def test_the_direction_is_recorded_so_the_next_reader_need_not_guess(
    engine, stored
) -> None:
    """A rewritten row carries what a row written before it could not."""
    recalibrate(Question, floor=0.75)

    with Session(engine) as session:
        reading = session.scalars(select_one(Question)).one().gate_scores[0]
        assert reading["high_is_safe"] is False
        assert reading["safe_end"] == 0.75


def test_no_verdict_moves(engine, stored) -> None:
    """The line between this and `questions-reverify`.

    That one may reject; this one may not. A recalibration that could
    change a status would be a second gate nobody asked to run.
    """
    recalibrate(Question, floor=0.75)

    with Session(engine) as session:
        row = session.scalars(select_one(Question)).one()
        assert row.status == QuestionStatus.ACCEPTED
        assert row.rejected_reason is None


def test_running_it_twice_writes_nothing_the_second_time(engine, stored) -> None:
    """Idempotent, so a scheduled run is free and a repeat is not damage."""
    assert recalibrate(Question, floor=0.75) == 1
    assert recalibrate(Question, floor=0.75) == 0


def test_a_fact_is_recalibrated_by_the_same_arithmetic(engine, stored) -> None:
    """Both tables carry the columns, and the defect was worse on facts."""
    written = recalibrate(Fact, floor=0.75)

    assert written == 1
    with Session(engine) as session:
        row = session.scalars(select_one(Fact)).one()
        # 0.07 of the 0.20 the scale offers, not of the 0.95 it does not.
        assert row.confidence == pytest.approx(0.35, abs=1e-2)


def test_a_verdict_written_while_it_runs_is_not_written_over(
    engine, stored, monkeypatch
) -> None:
    """A `questions-rejudge` beside it adds an entry the rewrite must keep.

    The rows are read without a lock, so the write back says what it read:
    a row whose scores changed meanwhile is skipped, not overwritten, and the
    next run takes it.
    """
    import json

    from sqlalchemy import text

    import stages.recalibrate as module

    verdict = {
        "gate": "settles",
        "value": 1.0,
        "threshold": 0.5,
        "margin": None,
        "opinion": True,
    }
    real = module.scored

    def scored_after_a_verdict(readings):
        """Lets a rejudge commit between the read and the write."""
        with engine.begin() as other:
            # A held row fails this test instead of hanging it.
            other.execute(text("SET LOCAL lock_timeout = '2s'"))
            other.execute(
                text(
                    "UPDATE questions SET gate_scores = gate_scores || "
                    "CAST(:verdict AS jsonb) "
                    "WHERE NOT gate_scores @> CAST(:verdict AS jsonb)"
                ),
                {"verdict": json.dumps([verdict])},
            )
        return real(readings)

    monkeypatch.setattr(module, "scored", scored_after_a_verdict)

    assert recalibrate(Question, floor=0.75) == 0
    with Session(engine) as session:
        scores = session.scalars(select_one(Question)).one().gate_scores
    assert [one["gate"] for one in scores] == ["near_duplicate", "settles"]

    monkeypatch.setattr(module, "scored", real)
    assert recalibrate(Question, floor=0.75) == 1
    with Session(engine) as session:
        scores = session.scalars(select_one(Question)).one().gate_scores
    assert [one["gate"] for one in scores] == ["near_duplicate", "settles"]
    assert scores[0]["margin"] == pytest.approx(0.2778, abs=1e-3)


def test_a_fact_gets_a_question_link_while_it_runs(engine, stored, monkeypatch) -> None:
    """Reading takes no row lock, so a writer beside it is not made to wait.

    With every fact held `FOR UPDATE` for the whole run, linking a question to
    a fact (a share lock on the fact) waits until the recalibration is over.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    import stages.recalibrate as module

    real = module.scored
    outcome: list[str] = []

    def scored_while_a_writer_links(readings):
        """Links a question to the fact from a second connection, mid-run."""
        try:
            with engine.begin() as other:
                other.execute(text("SET LOCAL lock_timeout = '1s'"))
                other.execute(
                    text(
                        "INSERT INTO question_facts (question_id, fact_id) "
                        "SELECT q.id, f.id FROM questions q, facts f"
                    )
                )
            outcome.append("linked")
        except OperationalError:
            outcome.append("waited")
        return real(readings)

    monkeypatch.setattr(module, "scored", scored_while_a_writer_links)

    recalibrate(Fact, floor=0.75)

    assert outcome == ["linked"]


def select_one(model):
    """Every row of one table, which the fixture wrote exactly one of."""
    return select(model)


def test_the_rows_are_read_and_written_in_id_order(
    engine, database, monkeypatch
) -> None:
    """As a deletion locks them, so the two lock in one line, and a batch is a range.

    The rows of lower id are updated first, which moves them to the end of the
    heap, where a read with no order finds them last.
    """
    from stages import recalibrate as module

    with Session(engine) as session:
        session.add_all(
            question(
                status=QuestionStatus.ACCEPTED,
                gate_scores=[dict(UNCALIBRATED)],
                confidence=0.0538,
                language=language,
            )
            for language in ("de", "en") * 10
        )
        session.commit()
        ids = sorted(session.scalars(select(Question.id)))
    with engine.begin() as connection:
        connection.execute(
            Question.__table__.update()
            .where(Question.id.in_(ids[:10]))
            .values(confidence=0.0539)
        )
    batches: list[list[int]] = []
    writing = module._write
    monkeypatch.setattr(
        module,
        "_write",
        lambda model, pending: (
            batches.append([one[0] for one in pending]) or writing(model, pending)
        ),
    )

    assert recalibrate(Question, floor=0.75) == len(ids)

    assert [key for batch in batches for key in batch] == ids
