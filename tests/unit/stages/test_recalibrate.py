"""Rebuilding a stored reading.

The half of a recalibration that is not a database write.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Self

import pytest

from confidence import scored
from stages.recalibrate import _reading


def test_a_legacy_reading_gets_its_direction_from_the_gate_name() -> None:
    """Rows written before the direction was stored carry only four keys."""
    rebuilt = _reading(
        {"gate": "near_duplicate", "value": 0.88, "threshold": 0.93, "margin": 0.0538},
        floor=0.75,
    )

    assert rebuilt.high_is_safe is False
    assert rebuilt.safe_end == 0.75
    assert rebuilt.margin == pytest.approx(0.05 / 0.18, abs=1e-4)


def test_a_legacy_reading_of_a_gate_read_the_other_way_keeps_its_end() -> None:
    """The floor is a similarity scale's, and `recall` is not one.

    Applying it to every gate would move a reading no calibration was
    wrong about, which is the way a recalibration does damage.
    """
    rebuilt = _reading(
        {"gate": "recall", "value": 0.8, "threshold": 0.6, "margin": 0.5}, floor=0.75
    )

    assert rebuilt.high_is_safe is True
    assert rebuilt.safe_end is None
    assert rebuilt.margin == pytest.approx(0.5, abs=1e-4)


def test_a_recorded_direction_is_believed_over_the_name() -> None:
    """A row written since carries its own direction, so the map is not read."""
    rebuilt = _reading(
        {
            "gate": "invented_later",
            "value": 0.8,
            "threshold": 0.93,
            "margin": 0.0,
            "high_is_safe": False,
            "safe_end": 0.75,
        },
        floor=0.75,
    )

    assert rebuilt.high_is_safe is False
    assert rebuilt.safe_end == 0.75


def test_an_unknown_legacy_gate_is_read_as_the_common_direction() -> None:
    """High is safe for every gate here but the two similarity ones."""
    rebuilt = _reading(
        {"gate": "something_new", "value": 0.8, "threshold": 0.6, "margin": 0.5},
        floor=0.75,
    )

    assert rebuilt.high_is_safe is True


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("What does the express fee cost?", "When is a refund paid out?"),
        ("Was kostet die Expressgebühr?", "Wann wird eine Erstattung ausgezahlt?"),
        ("速達料金はいくらですか。", "返金はいつ支払われますか。"),
    ],
)
def test_a_compound_reading_keeps_its_halves_through_a_recalibration(
    first, second
) -> None:
    """The halves cannot be recomputed from the row, so the rebuild carries them."""
    halves = [
        {"passage_id": 1, "question": first, "answer": "10 EUR"},
        {"passage_id": 2, "question": second, "answer": "14 days"},
    ]
    stored = {
        "gate": "halves",
        "value": 2.0,
        "threshold": 2.0,
        "margin": None,
        "high_is_safe": True,
        "safe_end": 1.0,
        "shadow": True,
        "detail": halves,
    }

    rebuilt = _reading(stored, floor=0.75)

    assert rebuilt.detail == halves
    assert scored([rebuilt]) == [stored]


def test_the_command_reads_both_floors_from_the_settings(monkeypatch) -> None:
    """The entry point's whole job: two settings, one call, a reported total.

    Stubbed at `main`, because what the command contributes is reading the
    right two settings and reporting what came back - the write itself is
    `tests/integration/database/test_recalibration_store.py`'s. A stored
    override wins over the environment, as it does for the workers.
    """
    from settings import store
    from stages import recalibrate_run

    monkeypatch.setenv("QUESTIONS_DUPLICATE_FLOOR", "0.75")
    monkeypatch.setenv("EXTRACTION_DUPLICATE_FLOOR", "0.70")
    monkeypatch.setattr(store, "sessions", lambda: None)
    monkeypatch.setattr(
        store.Settings,
        "overrides",
        lambda self: {"QUESTIONS_DUPLICATE_FLOOR": "0.81"},
    )
    asked: dict[str, float] = {}

    def recorded(questions_floor: float, facts_floor: float) -> int:
        """Stands in for the recalibration, keeping what it was asked."""
        asked.update(questions=questions_floor, facts=facts_floor)
        return 7

    monkeypatch.setattr(recalibrate_run, "main", recorded)

    assert recalibrate_run.run() == 0
    assert asked == {"questions": 0.81, "facts": 0.70}


def test_a_stored_opinion_is_rebuilt_as_one() -> None:
    """And so is written back unchanged, still feeding no confidence."""
    from confidence import confidence, scored

    stored = {
        "gate": "settles",
        "value": 1.0,
        "threshold": 0.5,
        "margin": None,
        "high_is_safe": True,
        "safe_end": 1.0,
        "opinion": True,
    }

    rebuilt = _reading(stored, floor=0.75)

    assert rebuilt.opinion is True
    assert scored([rebuilt]) == [stored]
    assert confidence([rebuilt]) is None


def test_a_shadow_reading_stays_a_shadow() -> None:
    """A reading taken before it gates anything must not start gating.

    Rebuilt without its mark, a coverage reading of 0.2 against 0.5 gets a
    margin of 0.0 and takes the question's confidence down with it.
    """
    from confidence import confidence, scored

    stored = [
        {
            "gate": "recall",
            "value": 0.9,
            "threshold": 0.6,
            "margin": 0.75,
            "high_is_safe": True,
            "safe_end": 1.0,
        },
        {
            "gate": "coverage",
            "value": 0.2,
            "threshold": 0.5,
            "margin": None,
            "high_is_safe": True,
            "safe_end": 1.0,
            "shadow": True,
        },
    ]

    rebuilt = [_reading(one, floor=0.75) for one in stored]

    assert scored(rebuilt) == stored
    assert confidence(rebuilt) == pytest.approx(0.75)


def test_an_opinion_keeps_its_prompt_version() -> None:
    """Without it, the next re-judge pays to ask the same question again."""
    from confidence import scored

    stored = {
        "gate": "settles",
        "value": 1.0,
        "threshold": 0.5,
        "margin": None,
        "high_is_safe": True,
        "safe_end": 1.0,
        "opinion": True,
        "version": "7",
    }

    assert scored([_reading(stored, floor=0.75)]) == [stored]


class _Deadlocking:
    """The session factory `recalibrate` asks for, its writes deadlocking `times` times.

    Reads two rows carrying a reading written before the direction was
    stored, which the recalibration rewrites; a write is one batch.
    """

    def __init__(self, times: int) -> None:
        """Deadlocks the first `times` batches it is asked to write."""
        self.left = times
        self.written = 0
        self.batches = 0

    def __call__(self) -> Self:
        """Itself, as `sessions()` returns the factory."""
        return self

    def __enter__(self) -> Self:
        """A session, or a batch's transaction."""
        return self

    def __exit__(self, *_) -> bool:
        """Lets an error through."""
        return False

    def begin(self) -> Self:
        """One batch's transaction."""
        self.batches += 1
        return self

    def execute(self, statement):
        """The read, or one row's guarded update."""
        import psycopg
        from sqlalchemy.exc import OperationalError

        if statement.is_select:
            reading = {"gate": "near_duplicate", "value": 0.88, "threshold": 0.93}
            return [(1, [reading]), (2, [reading])]
        if self.left:
            self.left -= 1
            raise OperationalError(
                "UPDATE", {}, psycopg.errors.DeadlockDetected("deadlock detected")
            )
        self.written += 1
        return SimpleNamespace(rowcount=1)


def test_a_deadlocked_batch_is_written_once_more(monkeypatch) -> None:
    """Another writer took the same rows in another order; Postgres chose this side."""
    from database.qa_generator import Question
    from stages import recalibrate as module

    factory = _Deadlocking(times=1)
    monkeypatch.setattr(module, "sessions", factory)

    assert module.recalibrate(Question, floor=0.75) == 2
    assert factory.batches == 2


def test_a_batch_deadlocked_twice_fails_naming_its_rows(monkeypatch) -> None:
    """Not a traceback of the driver alone: which rows, and that a rerun takes them."""
    from database.qa_generator import Question
    from stages import recalibrate as module

    monkeypatch.setattr(module, "sessions", _Deadlocking(times=2))

    with pytest.raises(RuntimeError, match=r"questions rows 1 to 2 deadlocked twice"):
        module.recalibrate(Question, floor=0.75)
