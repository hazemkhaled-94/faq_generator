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


def test_a_verdict_written_while_it_runs_is_not_written_over(engine, stored) -> None:
    """A `questions-rejudge` beside it adds an entry the rewrite keeps.

    The row is held while the recalibration starts, as `opine` holds it,
    and gets its verdict before it is let go. Read without a lock, the
    recalibration would write back what it read before the verdict.
    """
    import json
    import threading
    import time

    from sqlalchemy import text

    verdict = {
        "gate": "settles",
        "value": 1.0,
        "threshold": 0.5,
        "margin": None,
        "opinion": True,
    }
    written: list[int] = []
    holder = engine.connect()
    holder.begin()
    holder.execute(text("SELECT id FROM questions FOR UPDATE"))
    running = threading.Thread(
        target=lambda: written.append(recalibrate(Question, floor=0.75))
    )
    running.start()
    try:
        with engine.connect() as watching:
            for _ in range(200):
                waiting = watching.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE wait_event_type = 'Lock' "
                        "AND datname = current_database()"
                    )
                ).scalar()
                if waiting:
                    break
                time.sleep(0.05)
        assert waiting, "the recalibration never reached the held row"
        holder.execute(
            text(
                "UPDATE questions SET gate_scores = gate_scores || "
                "CAST(:verdict AS jsonb)"
            ),
            {"verdict": json.dumps([verdict])},
        )
        holder.commit()
    finally:
        holder.close()
        running.join(timeout=10)

    assert written == [1]
    with Session(engine) as session:
        scores = session.scalars(select_one(Question)).one().gate_scores
    assert [one["gate"] for one in scores] == ["near_duplicate", "settles"]
    assert scores[0]["margin"] == pytest.approx(0.2778, abs=1e-3)


def select_one(model):
    """Every row of one table, which the fixture wrote exactly one of."""
    return select(model)
