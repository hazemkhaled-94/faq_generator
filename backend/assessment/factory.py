"""Wiring for the assessment service."""

from __future__ import annotations

import logging

from assessment.config import Settings, judged_kinds
from assessment.judge import Judge
from assessment.repository import AssessmentQueue
from assessment.service import AssessmentService
from llm.client import Client
from llm.config import Settings as ModelSettings

log = logging.getLogger(__name__)

#: What is said when ASSESSMENT_JUDGE_MODEL names no model.
UNNAMED = (
    "ASSESSMENT_JUDGE_MODEL names no model, so nothing is judged, and "
    "LLM_MODEL is not asked in its place. Set ASSESSMENT_JUDGE_MODEL, or "
    "ASSESSMENT_JUDGE_CONTAINER_MODEL for the containers, to a model that is "
    "not LLM_MODEL."
)


def judge_model(settings: Settings, shared: ModelSettings) -> ModelSettings:
    """The model that judges, which is not the one that wrote.

    `ASSESSMENT_JUDGE_MODEL` names it, and naming nothing is refused rather
    than read as the shared model, because a judge that is also the writer
    is a model marking its own work. The same argument
    `question_generation.factory` makes about the verifier, and it bites
    harder here: the whole value of this phase is that it is an opinion the
    pipeline did not already hold.

    Raises:
        ValueError: If ASSESSMENT_JUDGE_MODEL names no model.
    """
    if not settings.judge_model:
        raise ValueError(UNNAMED)
    return shared.overridden(settings.judge_model)


def build_service(
    settings: Settings, model: ModelSettings, version: str | None = None
) -> AssessmentService:
    """Wires the service and its collaborators."""
    asked = judge_model(settings, model)
    if asked.model == model.model:
        log.warning(
            "%s is judging the pipeline's own output, because "
            "ASSESSMENT_JUDGE_MODEL names it. A model marking "
            "its own work agrees with itself, and this phase exists to hold "
            "an opinion the pipeline does not already hold.",
            asked.model,
        )
    return AssessmentService(
        repository=AssessmentQueue(
            kinds=judged_kinds(settings),
            sample=settings.sample,
            stratify=settings.stratify,
            version=version,
        ),
        judge=Judge(Client(asked)),
    )
