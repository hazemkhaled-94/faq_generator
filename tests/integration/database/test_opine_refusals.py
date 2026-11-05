"""What adding a model's verdicts to a question refuses, and what it skips.

A measurement carries a margin the row's confidence was made from, so adding
one as an opinion would leave the two disagreeing: refused, and nothing is
written. A question deleted since the verdicts were taken is not an error and
rejects nothing.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from confidence import Measurement
from question_generation.catalog import QuestionCatalog

pytestmark = pytest.mark.integration


def test_a_measurement_offered_as_an_opinion_is_refused(engine, database) -> None:
    """Refused before any row is read."""
    with pytest.raises(ValueError, match="only an opinion"):
        QuestionCatalog().opine(1, [Measurement("settles", 1.0, 0.5)])


def test_a_question_deleted_since_is_rejected_by_nobody(engine, database) -> None:
    """No row, no write, no rejection, no error."""
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM questions")).scalar_one() == 0
        )

    assert not QuestionCatalog().opine(
        404,
        [Measurement("settles", 1.0, 0.5, opinion=True)],
        rejected="answerable_after_all",
    )
