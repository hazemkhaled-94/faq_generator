"""Every prompt each stage's catalogue records, read once for every check."""

from __future__ import annotations

from assessment import prompts as assessment
from extraction import prompts as extraction
from question_generation import prompts as questions
from stages.prompts import Composed
from topic_modelling import prompts as topics


def recorded() -> dict[tuple[str, str], Composed]:
    """Every prompt each stage's catalogue records, by service and name.

    Extraction's under a cap, so the paragraph a cap appends is read too.
    """
    return {
        (service, one.name): one
        for service, held in (
            (questions.SERVICE, questions.catalogue()),
            (extraction.SERVICE, extraction.catalogue(4)),
            (topics.SERVICE, topics.catalogue()),
            (assessment.SERVICE, assessment.catalogue()),
        )
        for one in held
    }
