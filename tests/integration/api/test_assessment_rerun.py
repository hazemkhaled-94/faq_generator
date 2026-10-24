"""POST /assessment/rerun keeps stored verdicts when the phase cannot run."""

from __future__ import annotations

import pytest
from seed import digest, document, fact, passage
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from assessment.repository import AssessmentQueue
from database.qa_generator import Assessment

pytestmark = pytest.mark.integration

FACTS = [
    "A credit card costs 12 EUR a year.",
    "Eine Überweisung ins Ausland kostet 0,50 EUR.",
    "Returns are free within 30 days of delivery.",
    "Gutscheine sind 3 Jahre gültig.",
]


@pytest.mark.parametrize("route", ["whole", "kind"])
@pytest.mark.parametrize(
    "enabled,judge", [("false", "azure/judge"), ("false", None), ("true", None)]
)
def test_rerun_keeps_stored_verdicts_when_nothing_can_rejudge(
    client, engine, monkeypatch, enabled, judge, route
) -> None:
    """A rerun the phase cannot work off is refused before it blanks a verdict."""
    monkeypatch.setenv("ASSESSMENT_ENABLED", "true")
    monkeypatch.setenv("ASSESSMENT_JUDGE_MODEL", "azure/judge")
    with Session(engine) as session:
        session.add(document(digest("b")))
        session.flush()
        held = passage(digest("b"))
        session.add(held)
        session.flush()
        for text in FACTS:
            session.add(fact(held.id, statement=text))
        session.commit()
    AssessmentQueue(kinds=("fact",), sample=0, stratify=False).start()
    with Session(engine) as session:
        session.execute(
            update(Assessment).values(
                approved=True,
                assessed_at=func.now(),
                assess_status="assessed",
                judge_model="azure/judge",
            )
        )
        session.commit()
    monkeypatch.setenv("ASSESSMENT_ENABLED", enabled)
    if judge is None:
        monkeypatch.delenv("ASSESSMENT_JUDGE_MODEL", raising=False)
    else:
        monkeypatch.setenv("ASSESSMENT_JUDGE_MODEL", judge)

    answer = client.post(
        "/assessment/rerun?confirm=true"
        if route == "whole"
        else "/assessment/kind/fact/rerun"
    )

    with Session(engine) as session:
        after = session.execute(
            select(Assessment.approved, Assessment.judge_model)
        ).all()
    assert (
        answer.status_code == 409 and answer.json()["code"] == "assessment_cannot_run"
    )
    assert all(r.approved is True for r in after), (
        f"enabled={enabled} judge={judge}: answered {answer.status_code}, "
        f"verdicts after: {[(r.approved, r.judge_model) for r in after]}"
    )
