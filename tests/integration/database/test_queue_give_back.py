"""A worker told to stop gives its row back to the queue, unworked.

Not failed: nothing was wrong with the row, and a failed row is one a person
must remember to retry. What it holds goes back to pending and is claimable
at once; a worker that holds nothing has nothing to give back.
"""

from __future__ import annotations

import pytest
from seed import digest, document
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.qa_generator import Status
from preprocessing.parsing.repository import ParseQueue
from settings.runs import triggered_by

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def unasked():
    """No run is asking; the trigger lives in a ContextVar."""
    triggered_by(None)
    yield
    triggered_by(None)


def statuses(engine) -> dict[str, int]:
    with engine.connect() as connection:
        return dict(
            connection.execute(
                text("SELECT parse_status, count(*) FROM documents GROUP BY 1")
            ).all()
        )


def test_a_held_row_goes_back_to_pending_and_is_claimable_again(
    engine, database
) -> None:
    """Pending, with no error, and the next claim takes it."""
    with Session(engine) as session:
        session.add(document(digest("loan-terms"), parse_status=Status.PENDING))
        session.commit()
    queue = ParseQueue()
    assert queue.claim() is not None

    assert queue.release_held() is True

    assert statuses(engine) == {Status.PENDING: 1}
    assert ParseQueue().claim() is not None


def test_a_worker_holding_nothing_gives_nothing_back(engine, database) -> None:
    """A stop between rows touches no row."""
    with Session(engine) as session:
        session.add(document(digest("loan-terms"), parse_status=Status.PARSED))
        session.commit()

    assert ParseQueue().release_held() is False
    assert statuses(engine) == {Status.PARSED: 1}
