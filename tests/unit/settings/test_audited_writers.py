"""The two writers outside a stage's build read their settings through the audit too.

`make confidence-recalibrate` rewrites stored confidences from the duplicate
floors, and the assessment enrolment reads which kinds to enrol and how many:
a stored row the catalogue now refuses stops both, naming the row, as it stops
every stage and the upload.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from settings import store


def _table(name: str, value: str, service: str):
    """The settings table holding one row, read the old way and the audited."""

    class Table:
        def rows(self):
            return [
                SimpleNamespace(
                    name=name,
                    value=value,
                    updated_at=datetime(2026, 9, 1, 10, 30),
                    service=service,
                )
            ]

        def resolved(self):
            return store._source({name: value})

    return Table


def test_a_refused_duplicate_floor_stops_the_recalibration(monkeypatch) -> None:
    """3 and nothing rewritten, where the refused floor was applied."""
    from stages import recalibrate_run

    monkeypatch.setattr(
        store, "Settings", _table("QUESTIONS_DUPLICATE_FLOOR", "2", "questions")
    )
    monkeypatch.delenv("QA_COMMAND_LINE", raising=False)
    rewrote: list[dict] = []
    monkeypatch.setattr(
        recalibrate_run, "main", lambda **floors: rewrote.append(floors) or 0
    )

    assert recalibrate_run.run() == 3
    assert rewrote == []


def test_a_refused_assessment_sample_stops_the_enrolment(monkeypatch) -> None:
    """The kinds and the sample an enrolment reads come through the audit."""
    from assessment.repository import AssessmentQueue

    monkeypatch.setattr(
        store, "Settings", _table("ASSESSMENT_SAMPLE", "-1", "assessment")
    )
    monkeypatch.delenv("QA_COMMAND_LINE", raising=False)
    monkeypatch.setenv("ASSESSMENT_ENABLED", "true")

    with pytest.raises(store.StoredRefused, match="ASSESSMENT_SAMPLE"):
        AssessmentQueue()._asked()


def test_the_api_answers_a_refused_stored_row_with_503_naming_it() -> None:
    """Any route that builds on the audited settings, the enrolment's included."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.errors import install

    app = FastAPI()
    install(app)

    @app.post("/enrol")
    def enrol() -> None:
        raise store.StoredRefused("ASSESSMENT_SAMPLE='-1' is refused now")

    answered = TestClient(app).post("/enrol")

    assert answered.status_code == 503
    assert answered.json()["code"] == "stored_setting_refused"
    assert "ASSESSMENT_SAMPLE" in answered.json()["detail"]
