"""Configuration for the assessment stage.

The two settings that matter are in `.env` rather than in
`configs/env/backend.env`, against this project's usual split. `.env` holds
credentials, ports and addresses; tuning goes in git. These are neither:
turning the phase on commits a deployment to a model call per artefact, and
naming the judge decides whose opinion is being recorded. Both are
deployment decisions that differ between a laptop and a server, which is
what `.env` is.
"""

from __future__ import annotations

from dataclasses import dataclass

from llm.config import split
from settings import Source, boolean, csv, integer, optional

#: What is said when the phase is switched off. A message rather than an
#: empty queue: a deployment that has not turned this on and cannot tell
#: the difference between "off" and "nothing to judge" will read the second
#: as a bug in the first.
OFF = (
    "ASSESSMENT_ENABLED is off, so nothing is judged. The pipeline is "
    "unaffected - this phase only ever records an opinion beside the "
    "checker's. Set ASSESSMENT_ENABLED=true in .env to run it."
)

#: What is said when ASSESSMENT_JUDGE_MODEL names no model.
UNNAMED = (
    "ASSESSMENT_JUDGE_MODEL names no model, so nothing is judged, and "
    "LLM_MODEL is not asked in its place. Set ASSESSMENT_JUDGE_MODEL, or "
    "ASSESSMENT_JUDGE_CONTAINER_MODEL for the containers, to a model that is "
    "not LLM_MODEL."
)


@dataclass(frozen=True)
class Settings:
    """Whether to judge, what to judge, and who judges it."""

    #: Whether the phase runs at all. Off, the queue answers `/status` with
    #: an empty queue, `start` enrols nothing and the Dagster asset reports
    #: that it is off rather than that it did nothing.
    enabled: bool
    #: The model asked. Absent, nothing is judged: LLM_MODEL in its place
    #: would be the writer marking its own work.
    judge_model: str | None
    #: Which artefacts are judged. Narrowing it is how a deployment pays for
    #: the questions and not for the facts.
    kinds: tuple[str, ...]
    #: How many artefacts of each kind one `start` enrols, newest first.
    #: 0 is every one of them.
    sample: int
    #: Whether a sample is drawn evenly across language, and across type for
    #: a question, in an order fixed by a hash of the id within each, instead
    #: of newest first. Drawn again over the same corpus, it is the same rows.
    stratify: bool = False

    @classmethod
    def load(cls, source: Source = None) -> Settings:
        """Reads settings from the environment, or from an override."""
        return cls(
            enabled=boolean("ASSESSMENT_ENABLED", source),
            judge_model=optional("ASSESSMENT_JUDGE_MODEL", source),
            kinds=csv("ASSESSMENT_KINDS", source),
            sample=integer("ASSESSMENT_SAMPLE", source),
            stratify=boolean("ASSESSMENT_STRATIFY", source),
        )


def cannot_run(settings: Settings) -> str | None:
    """Why no worker would judge anything now, or None where one would.

    The API's rerun checks it before it clears stored verdicts: a rerun that
    blanks them for a worker that will claim nothing loses them for good. The
    command line does not call it: the queue's preflight in run.py proves the
    judge answers before it claims an artefact.
    """
    if not settings.enabled:
        return OFF
    if not settings.judge_model:
        return UNNAMED
    return None


def judge_equals(settings: Settings, source: Source = None) -> list[str]:
    """The roles whose output is judged that the judge model also is.

    The writer, the verifier, the phrasing judge, the passage reader, the
    digest reader and the topic namer each produce what this phase judges, and
    a judge that is any of them marks its own work. Named, so the log and the
    plan say which.
    """
    judge = settings.judge_model
    if judge is None:
        return []
    return [
        role
        for role, model in split(source).items()
        if role != "judge" and model == judge
    ]


#: The roles that wrote and checked the questions a judge is asked about, the
#: bulk of what it judges: a judge that is one of them marks its own work.
MARKING = frozenset({"writer", "verifier"})


def judge_of(settings: Settings, source: Source = None) -> tuple[str | None, bool]:
    """The model the next run judges with, and whether it marks its own work.

    Its own work where the judge is the writer's or the verifier's model; a
    judge that only shares another role's - the shipped split's digest
    reader - is said, not warned about, as the build says it. None where
    ASSESSMENT_JUDGE_MODEL names nothing, and then nothing is judged.
    """
    return settings.judge_model, bool(MARKING & set(judge_equals(settings, source)))


def judged_kinds(settings: Settings) -> tuple[str, ...]:
    """The kinds this deployment judges, refusing a name that is not one.

    Raises:
        ValueError: If ASSESSMENT_KINDS names something that is not an
            artefact kind, naming both it and the three that are.
    """
    from assessment.templates import TEMPLATES

    unknown = [one for one in settings.kinds if one not in TEMPLATES]
    if unknown:
        raise ValueError(
            f"ASSESSMENT_KINDS names {', '.join(unknown)}, which "
            f"{'are' if len(unknown) > 1 else 'is'} not judged here. The "
            f"kinds are {', '.join(TEMPLATES)}."
        )
    return settings.kinds
