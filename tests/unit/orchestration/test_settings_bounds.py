"""The orchestrator's two timings refuse values no wait can be made of."""

from __future__ import annotations

import pytest

from orchestration.settings import Settings

_TIMINGS = ("ORCHESTRATION_DRAIN_TIMEOUT_SECONDS", "ORCHESTRATION_POLL_SECONDS")


@pytest.fixture(autouse=True)
def environment(monkeypatch) -> None:
    """A working environment, which each test then spoils in one place."""
    monkeypatch.setenv("BACKEND_URL", "http://api:8000")
    monkeypatch.setenv("ORCHESTRATION_DRAIN_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("ORCHESTRATION_POLL_SECONDS", "1")
    monkeypatch.setenv("INGESTION_OPEN", "true")


def test_the_timings_are_read_as_written() -> None:
    """The deployment's own numbers come back as numbers."""
    loaded = Settings.load()

    assert (loaded.drain_timeout, loaded.poll_seconds) == (60.0, 1.0)


@pytest.mark.parametrize("name", _TIMINGS)
def test_a_timing_that_is_not_a_number_stops_the_code_location(
    monkeypatch, name: str
) -> None:
    """A typo fails at load, naming nothing worse than float()."""
    monkeypatch.setenv(name, "sixty")

    with pytest.raises(ValueError):
        Settings.load()


@pytest.mark.parametrize("value", ["nan", "inf", "-1", "0", "1e-300", "0.5"])
@pytest.mark.parametrize("name", _TIMINGS)
def test_a_timing_no_wait_can_be_made_of_stops_the_code_location(
    monkeypatch, name: str, value: str
) -> None:
    """As backend/settings/env.py decimal() refuses nan for the stages.

    nan never times a drain out, a negative poll raises in time.sleep mid-run,
    and a poll of 0, or of 1e-300, asks the api without pause.
    """
    monkeypatch.setenv(name, value)

    with pytest.raises((KeyError, ValueError)):
        Settings.load()
