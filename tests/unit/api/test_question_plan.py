"""The plan the questions page draws, from stored settings that may not load.

The route is imported inside the test, never at module scope: see
tests/unit/api/test_params.py for why.
"""

from __future__ import annotations

import os


def test_a_stored_nan_does_not_take_the_questions_plan_down(monkeypatch) -> None:
    """Stored before a check refused it; the panel that clears it is below."""
    from api.routes import questions

    warned: list[str] = []
    source = {**os.environ, "QUESTIONS_UNANSWERABLE_SHARE": "nan"}
    monkeypatch.setattr(questions, "resolved", lambda: source)
    monkeypatch.setattr(
        questions.log, "warning", lambda message, *args: warned.append(message % args)
    )

    drawn = questions.plan()

    assert drawn.unanswerable_share == float(os.environ["QUESTIONS_UNANSWERABLE_SHARE"])
    assert "QUESTIONS_UNANSWERABLE_SHARE" in " ".join(warned)
