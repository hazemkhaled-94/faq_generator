"""A run's spend is carried from one drain's process to the next.

SPEND_CAP is held against an in-process tally, and a corpus run is one process
per drain, so a cap met by one drain would start again at zero in the next.
With SPEND_LEDGER set a process starts its tally at what the ledger holds and
adds what it spent to it as it exits.
"""

from __future__ import annotations

import pytest

from llm import tally


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    """A tally that starts at zero and an exit that runs when the test says."""
    exits: list = []
    monkeypatch.setattr(tally, "_spent", {"usd": 0.0})
    monkeypatch.setattr(tally.atexit, "register", lambda f, *a: exits.append((f, a)))
    return exits


def test_no_ledger_changes_nothing(fresh) -> None:
    """The development path."""
    tally.carry(None)

    assert tally.spent_usd() == 0.0
    assert fresh == []


def test_a_process_starts_at_what_earlier_drains_spent(tmp_path, fresh) -> None:
    """Counted as its own, so the cap holds for the run."""
    ledger = tmp_path / "spend.usd"
    ledger.write_text("1.25\n0.5\n")

    tally.carry(str(ledger))

    assert tally.spent_usd() == pytest.approx(1.75)


def test_a_missing_ledger_is_the_first_drain(tmp_path, fresh) -> None:
    """Nothing spent yet."""
    tally.carry(str(tmp_path / "none.usd"))

    assert tally.spent_usd() == 0.0


def test_what_a_process_spent_is_added_when_it_exits(tmp_path, fresh) -> None:
    """Its own spend and not the carried part twice."""
    ledger = tmp_path / "spend.usd"
    ledger.write_text("2.0\n")
    tally.carry(str(ledger))
    tally.add(0.75)

    for write, arguments in fresh:
        write(*arguments)

    assert [float(x) for x in ledger.read_text().split()] == [2.0, 0.75]


def test_a_process_that_spent_nothing_adds_no_line(tmp_path, fresh) -> None:
    """A status query or a parse."""
    ledger = tmp_path / "spend.usd"
    tally.carry(str(ledger))

    for write, arguments in fresh:
        write(*arguments)

    assert not ledger.exists() or ledger.read_text() == ""


def test_a_ledger_that_cannot_be_read_stops_the_drain(tmp_path, fresh) -> None:
    """A cap nobody can count against is not a cap."""
    ledger = tmp_path / "spend.usd"
    ledger.write_text("lots\n")

    with pytest.raises(ValueError, match="SPEND_LEDGER"):
        tally.carry(str(ledger))
