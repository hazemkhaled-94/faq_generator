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

    The one check the command line and the API share before a verb that
    clears stored verdicts: a rerun that blanks them for a worker that will
    claim nothing loses them for good.
    """
    if not settings.enabled:
        return OFF
    if not settings.judge_model:
        return UNNAMED
    return None


def judge_of(settings: Settings, source: Source = None) -> tuple[str | None, bool]:
    """The model the next run judges with, and whether it is the writer's.

    None where ASSESSMENT_JUDGE_MODEL names nothing, and then nothing is
    judged.
    """
    writer = optional("LLM_MODEL", source)
    judge = settings.judge_model
    return judge, judge is not None and judge == writer


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
