"""Recomputing a stored confidence when its calibration changes.

`gate_scores` records what each measuring gate read and what it was read
against, so a margin is arithmetic over two numbers already in the row.
Nothing here calls a model, an embedder or a service: a recalibration is a
read and a write over one column.

It is separate from every stage's own re-check for that reason.
`question_generation.reverify` puts a stored question through the gates
that need no model and may REJECT it; this moves no verdict and touches
neither `status` nor `rejected_reason`.

A row written before the direction was recorded carries only `gate`,
`value`, `threshold` and `margin`, so which way its gate runs has to come
from somewhere. `_REFUSES_HIGH` is that somewhere, and it is the only place
in the codebase that has to know: every row written since carries its own
`high_is_safe`.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from confidence import Measurement, confidence, scored
from database.qa_generator import Fact, Question, sessions

log = logging.getLogger(__name__)

#: The gates a HIGH reading refuses, for rows written before the direction
#: was stored beside the reading. Everything else keeps what it measured by
#: reading high.
_REFUSES_HIGH = frozenset({"near_duplicate", "duplicate"})


def _reading(stored: dict, floor: float) -> Measurement:
    """One stored reading, rebuilt so its margin can be taken again.

    The direction comes off the row where the row carries one, and off
    `_REFUSES_HIGH` where it does not. `floor` applies only to a gate a
    high reading refuses: it is where a similarity scale ends, and the
    gates read the other way already end at 1.0.
    """
    refuses_high = stored.get("high_is_safe") is False or (
        "high_is_safe" not in stored and stored["gate"] in _REFUSES_HIGH
    )
    return Measurement(
        gate=stored["gate"],
        value=float(stored["value"]),
        threshold=float(stored["threshold"]),
        high_is_safe=not refuses_high,
        safe_end=floor if refuses_high else None,
        opinion=bool(stored.get("opinion")),
        version=stored.get("version"),
        shadow=bool(stored.get("shadow")),
        detail=stored.get("detail"),
    )


#: Rows read at a time off the cursor, and rows written back in one
#: transaction. Small writes hold their row locks for a moment.
_READ = 1000
_BATCH = 300

#: PostgreSQL's code for a transaction it aborted to end a deadlock.
_DEADLOCK = "40P01"


def _write(model, pending: list[tuple[int, list, list, float | None]]) -> int:
    """Writes one batch back in a transaction of its own; how many rows moved."""
    with sessions().begin() as session:
        return sum(
            session.execute(
                update(model)
                .where(model.id == key, model.gate_scores == read)
                .values(gate_scores=scores, confidence=margin)
            ).rowcount
            for key, read, scores, margin in pending
        )


def _deadlocked(exc: OperationalError) -> bool:
    """Whether Postgres aborted the batch to end a deadlock."""
    return getattr(exc.orig, "sqlstate", None) == _DEADLOCK


def recalibrate(model, floor: float) -> int:
    """Takes every stored row's margins again, and returns how many moved.

    Rows are read without a lock and written back in small batches, each
    guarded by the scores it read: `UPDATE ... WHERE gate_scores = :read`. A
    row a `questions-rejudge` or an `opine` changed meanwhile is skipped,
    never written over, and the next run takes it. A lock held across the
    whole read would stop every writer of a question or a fact for as long
    as the run lasts.

    A batch takes its rows' locks in its own order, so a writer updating
    several of them in another can deadlock with it, and Postgres aborts one
    side. A batch aborted so is written once more, and aborted again it
    fails the run naming its rows; the batches before it stay written.

    Args:
        model: `Question` or `Fact` - the two tables carrying the columns.
        floor: Where the similarity scale ends for the gate that refuses a
            high reading.

    Returns:
        How many rows were written. A row whose readings come back
        unchanged is left alone, so running this twice writes nothing the
        second time.
    """
    written = skipped = 0
    pending: list[tuple[int, list, list, float | None]] = []

    def flush() -> None:
        nonlocal written, skipped
        if not pending:
            return
        try:
            moved = _write(model, pending)
        except OperationalError as exc:
            if not _deadlocked(exc):
                raise
            log.warning(
                "a batch of %d %s row(s) deadlocked with another writer; "
                "writing it once more",
                len(pending),
                model.__tablename__,
            )
            try:
                moved = _write(model, pending)
            except OperationalError as again:
                if not _deadlocked(again):
                    raise
                raise RuntimeError(
                    f"{model.__tablename__} rows {pending[0][0]} to "
                    f"{pending[-1][0]} deadlocked twice with another writer and "
                    "were left as they are; run it again"
                ) from again
        written += moved
        skipped += len(pending) - moved
        pending.clear()

    with sessions()() as reading:
        rows = reading.execute(
            select(model.id, model.gate_scores)
            .where(model.gate_scores.is_not(None))
            .execution_options(yield_per=_READ)
        )
        for key, scores in rows:
            stored = list(scores or ())
            if not stored:
                continue
            readings = [_reading(one, floor) for one in stored]
            recomputed = scored(readings)
            if recomputed == stored:
                continue
            pending.append((key, stored, recomputed, confidence(readings)))
            if len(pending) >= _BATCH:
                flush()
        flush()
    log.info("recalibrated %d %s row(s)", written, model.__tablename__)
    if skipped:
        log.info(
            "%d %s row(s) changed while this ran and were left as they are; "
            "run it again to take them",
            skipped,
            model.__tablename__,
        )
    return written


def main(questions_floor: float, facts_floor: float) -> int:
    """Recalibrates both tables, reporting what each wrote."""
    return recalibrate(Question, questions_floor) + recalibrate(Fact, facts_floor)
