"""Wiring for the assessment service."""

from __future__ import annotations

import logging

from assessment.config import MARKING, UNNAMED, Settings, judge_equals, judged_kinds
from assessment.judge import Judge
from assessment.repository import AssessmentQueue
from assessment.service import AssessmentService
from llm.client import Client
from llm.config import Settings as ModelSettings
from settings import Source

log = logging.getLogger(__name__)


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
    settings: Settings,
    model: ModelSettings,
    version: str | None = None,
    source: Source = None,
) -> AssessmentService:
    """Wires the service and its collaborators."""
    asked = judge_model(settings, model)
    # The shared model too, which `source` may not name where a test builds
    # this from settings alone.
    marked = judge_equals(settings, source) or (
        ["writer"] if asked.model == model.model else []
    )
    # A warning where the judge wrote or checked the questions it judges, the
    # bulk of what it is asked; a line where it only shares a reader's model.
    # The shipped split puts the judge and the digest reader both on
    # azure/gpt-4o, which warned at every build of a deployment as shipped.
    level = logging.WARNING if MARKING & set(marked) else logging.INFO
    if marked:
        log.log(
            level,
            "%s is judging the pipeline's own output, because "
            "ASSESSMENT_JUDGE_MODEL names it: it is the %s model. A model marking "
            "its own work agrees with itself, and this phase exists to hold "
            "an opinion the pipeline does not already hold.",
            asked.model,
            ", ".join(marked),
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
