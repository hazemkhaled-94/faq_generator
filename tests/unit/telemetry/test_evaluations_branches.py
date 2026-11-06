"""A process with no Phoenix client stops trying, and says why once.

No wait mends a missing package, so the first post that finds none turns
annotation off for the process's life and logs it; every later verdict is
dropped without a call, and the run carries on. The verdicts are in the
database either way. An empty explanation is not posted as one.
"""

from __future__ import annotations

import logging

from telemetry.evaluations import Evaluations, TraceStoreUnavailable, Verdict

BASE = "http://phoenix.invalid:6006"


def verdict() -> Verdict:
    """One gate verdict on a recorded span."""
    return Verdict(span_id="0123456789abcdef", name="gate", label="accepted", score=1.0)


def test_no_client_package_turns_annotation_off_for_good(monkeypatch, caplog) -> None:
    """One attempt, one log line, then nothing is asked again."""
    held = Evaluations(BASE, batch=1)
    attempts: list[int] = []

    def missing():
        attempts.append(1)
        raise TraceStoreUnavailable("arize-phoenix-client is not installed")

    monkeypatch.setattr(held, "_connect", missing)

    with caplog.at_level(logging.INFO):
        held.record(verdict())
        held.record(verdict())

    assert attempts == [1]
    assert not held.enabled
    assert held.flush() == 0
    assert caplog.text.count("arize-phoenix-client is not installed") == 1


def test_a_verdict_with_no_explanation_posts_none() -> None:
    """An empty explanation is left out, not posted as an empty string."""
    result = Verdict(
        span_id="0123456789abcdef", name="gate", label="refused", explanation=""
    ).payload()

    assert "explanation" not in result["result"]
