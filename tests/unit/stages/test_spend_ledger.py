"""A run's spend is carried from one drain's process to the next.

SPEND_CAP is held against an in-process tally, and a corpus run is one process
per drain, so a cap met by one drain would start again at zero in the next.
With SPEND_LEDGER set a process starts its tally at what the ledger holds and
writes the run's total back after every call it pays for, so a drain killed
before it exits leaves what it spent counted.
"""

from __future__ import annotations

import pytest

from llm import tally


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    """A tally that starts at zero and names no ledger."""
    monkeypatch.setattr(tally, "_spent", {"usd": 0.0})
    monkeypatch.setattr(tally, "_ledger", {"path": None})


def test_no_ledger_changes_nothing(tmp_path, monkeypatch) -> None:
    """The development path."""
    monkeypatch.chdir(tmp_path)
    tally.carry(None)
    tally.add(0.5)

    assert tally.spent_usd() == 0.5
    assert list(tmp_path.iterdir()) == []


def test_a_process_starts_at_what_earlier_drains_spent(tmp_path) -> None:
    """Counted as its own, so the cap holds for the run."""
    ledger = tmp_path / "spend.usd"
    ledger.write_text("1.25\n0.5\n")

    tally.carry(str(ledger))

    assert tally.spent_usd() == pytest.approx(1.75)


def test_a_missing_ledger_is_the_first_drain(tmp_path) -> None:
    """Nothing spent yet."""
    tally.carry(str(tmp_path / "none.usd"))

    assert tally.spent_usd() == 0.0


def test_the_run_total_is_written_after_every_priced_call(tmp_path) -> None:
    """Not at exit: a drain killed by SIGKILL or the OOM killer never gets there."""
    ledger = tmp_path / "spend.usd"
    ledger.write_text("2.0\n")
    tally.carry(str(ledger))

    tally.add(0.75)
    after_one = ledger.read_text()
    tally.add(0.25)

    assert [float(x) for x in after_one.split()] == [2.75]
    assert [float(x) for x in ledger.read_text().split()] == [3.0]


def test_the_ledger_is_replaced_whole(tmp_path) -> None:
    """A new file renamed over it, so a kill mid-write leaves the last total."""
    ledger = tmp_path / "spend.usd"
    tally.carry(str(ledger))

    tally.add(1.5)

    assert [one.name for one in tmp_path.iterdir()] == ["spend.usd"]
    assert sum(float(x) for x in ledger.read_text().split()) == pytest.approx(1.5)


def test_a_process_that_spent_nothing_writes_nothing(tmp_path) -> None:
    """A status query, a parse, or a call nobody could price."""
    ledger = tmp_path / "spend.usd"
    tally.carry(str(ledger))

    tally.add(0.0)

    assert not ledger.exists()


def test_a_ledger_that_cannot_be_read_stops_the_drain(tmp_path) -> None:
    """A cap nobody can count against is not a cap."""
    ledger = tmp_path / "spend.usd"
    ledger.write_text("lots\n")

    with pytest.raises(ValueError, match="SPEND_LEDGER"):
        tally.carry(str(ledger))
