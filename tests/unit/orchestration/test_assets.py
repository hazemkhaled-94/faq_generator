"""What the asset and check bodies report, against a stand-in backend."""

from __future__ import annotations

from typing import ClassVar

import pytest

pytest.importorskip("dagster", reason="the pipeline group is not installed")

from dagster import build_asset_context

from orchestration import stages
from orchestration.client import Queue

#: The assets read `context.run_id`, which Dagster 1.13 deprecates.
pytestmark = pytest.mark.filterwarnings(
    "ignore:AssetExecutionContext.run_id is deprecated:DeprecationWarning"
)

#: The queue every drain and status read returns.
ROWS = {"parsed": 5, "failed": 2, "new": 1}


class Stub:
    """Stands in for the backend client, recording each verb it is sent."""

    plan_enabled = True
    acted: ClassVar[list[tuple[str, str]]] = []

    def __init__(self, *args, **kwargs) -> None:
        """Accepts whatever the asset passes."""

    def act(self, stage: str, action: str, run: str | None = None) -> int:
        """Records the verb."""
        self.acted.append((stage, action))
        return 3

    def discover(self, run: str | None = None) -> int:
        """Asks for fit 9."""
        return 9

    def drain(self, stage: str, *, timeout: float, poll: float) -> Queue:
        """The drained queue."""
        return Queue(stage=stage, working=False, rows=ROWS)

    def status(self, stage: str) -> Queue:
        """The same queue."""
        return self.drain(stage, timeout=0, poll=0)

    def plan(self, stage: str) -> dict:
        """Whether the phase is on."""
        return {"enabled": self.plan_enabled}

    def judged(self) -> dict:
        """Nothing judged."""
        return {}


@pytest.fixture(autouse=True)
def backend(monkeypatch) -> type[Stub]:
    """The environment the assets read, and the stand-in they call."""
    monkeypatch.setenv("BACKEND_URL", "http://api:8000")
    monkeypatch.setenv("ORCHESTRATION_DRAIN_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("ORCHESTRATION_POLL_SECONDS", "1")
    monkeypatch.setenv("INGESTION_OPEN", "true")
    monkeypatch.setattr(Stub, "acted", [])
    monkeypatch.setattr(stages, "Backend", Stub)
    return Stub


def test_a_row_stage_starts_and_reports_what_was_done(backend) -> None:
    """Done is everything but new and failed."""
    out = stages.parsed_documents(build_asset_context())

    assert backend.acted == [("parsing", "start")]
    assert out.value == 5
    assert out.metadata["failed"].value == 2


def test_assessment_switched_off_materialises_nothing(backend, monkeypatch) -> None:
    """Off is not a failure, and nothing is started."""
    monkeypatch.setattr(backend, "plan_enabled", False)

    out = stages.assessments(build_asset_context())

    assert out.value == 0
    assert backend.acted == []


def test_assessment_switched_on_reports_what_was_judged(backend) -> None:
    """The count is what the queue says was produced."""
    out = stages.assessments(build_asset_context())

    assert backend.acted == [("assessment", "start")]
    assert out.value == stages.produced(ROWS)


@pytest.mark.parametrize(
    ("check", "stage"),
    [
        (stages.parsed_documents_check, "parsing"),
        (stages.topics_check, "topics"),
        (stages.questions_check, "questions"),
        (stages.assessments_check, "assessment"),
    ],
)
def test_a_failed_row_fails_the_stage_check(check, stage: str) -> None:
    """Reported with the count and the route that retries it, never raised."""
    result = check()

    assert result.passed is False
    assert result.metadata["failed"].value == 2
    assert result.metadata["retry with"].value == f"POST /{stage}/retry"


def test_the_agreement_check_passes_with_nothing_judged() -> None:
    """No division by zero, and a rate that says why it is missing."""
    result = stages.assessments_agreement()

    assert result.passed is True
    assert result.metadata["approval rate"].value == "nothing judged"
