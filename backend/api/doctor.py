"""`make doctor`'s model check: every model a stage run from here calls, asked once.

It sits in the api package because it imports every stage's settings and
model factory to resolve the models they call, and the api is the one layer
the import contract lets reach every stage. Every import is inside a function,
so the api process loads none of it.

    python -m api.doctor       # which is what `make doctor` runs
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm.config import Settings

log = logging.getLogger(__name__)


def every_model() -> list[Settings]:
    """Every model a stage run from this environment calls, as it resolves it.

    LLM_MODEL and each stage's own: backend.env names some of those, so
    LLM_MODEL alone is not what a run calls. The judge only while the
    evaluation phase is on, as its worker asks it.
    """
    # Inside the function, as every import here: the api process imports
    # none of the stages' working halves, and tests/static/test_api_stays_light.py
    # reads only the imports a module makes when it loads.
    from assessment.config import Settings as Assessment
    from assessment.factory import judge_model
    from extraction.config import Settings as Extraction
    from extraction.factory import models as extraction_models
    from llm.config import Settings as Shared
    from question_generation.config import Settings as Questions
    from question_generation.factory import models as question_models
    from topic_modelling.config import Settings as Topics

    shared = Shared.load()
    asked = [shared, *extraction_models(Extraction.load(), shared)]
    if naming := Topics.load().model:
        asked.append(naming)
    asked += question_models(Questions.load(), shared)
    if (judging := Assessment.load()).enabled:
        asked.append(judge_model(judging, shared))
    return list({(m.model, m.base_url): m for m in asked}.values())


def main() -> int:
    """Asks every configured model one question, and says what happened.

    Returns:
        The process exit code: 0 if every model answered in shape.
    """
    import telemetry
    from llm.check import Unreachable, reachable

    telemetry.configure("doctor")

    failed = 0
    for settings in every_model():
        log.info("model    %s", settings.model)
        log.info("address  %s", settings.base_url or "(the provider's own)")
        log.info("mode     %s", settings.structured_mode)
        try:
            reachable(settings)
        except Unreachable as refusal:
            log.error("%s", refusal)
            failed = 1
            continue
        log.info("the model answered in shape")
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
