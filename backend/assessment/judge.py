"""Asking one model for one judgement, and what to do when it will not.

Through `llm.client`, which is the same client every other model call in
this pipeline goes through: one retry policy, one timeout, one structured
mode, one place the reasoning tags are stripped and one place the tokens
and the spend are recorded. A judge built on a second client would be a
second set of all of those, disagreeing with the first the day one moved.

`arize-phoenix-evals` is the obvious alternative and is already a
dependency, but only on the host - no image carries it. Reaching for it here would put a second LLM
client, a second rate limiter and a pandas dependency into a worker
container to ask a question the client already in that container can ask.
What is borrowed from that package instead is the part worth borrowing:
the metric names, the labels and the scores. See `templates.py`.

An unanswerable judgement is an ABSTENTION and never a refusal. A model
that could not be reached has not found a problem with the artefact, and
recording that as disapproval would fill the review queue with rows whose
only fault was that Ollama was restarting.
"""

from __future__ import annotations

import logging

from assessment.models import ArtifactToJudge, Judgement
from assessment.templates import PROMPT_VERSION, TEMPLATES, Template
from llm.client import Client, ModelUnavailable

log = logging.getLogger(__name__)


class JudgeUnavailable(Exception):
    """Raised when no metric of an artefact could be judged at all.

    The difference between this and an abstention is how much was lost. One
    metric of three missing leaves a partial verdict worth recording; none
    of them answering is a row that was never judged, and the queue must be
    able to tell those apart - the first is `assessed`, the second `failed`
    and retryable.
    """


class Judge:
    """One model, asked each metric an artefact kind declares."""

    def __init__(self, client: Client) -> None:
        """Initialises the judge with the model it asks."""
        self._client = client

    @property
    def model(self) -> str:
        """The model answering, recorded beside what it answered."""
        return self._client.model

    def asked(self, artifact: ArtifactToJudge) -> tuple[Template, ...]:
        """The templates this artefact is asked: its kind's, less any meant for a root.

        A follow-up is the one artefact a template can be wrong for. It
        leans on the turn before it, which the paper's rubric is not shown,
        so a rubric asked of one would score the thread's context as the
        question's fault. Only a question claimed as a follow-up is spared:
        nothing else carries a `root` at all.
        """
        return tuple(
            one
            for one in TEMPLATES[artifact.kind]
            if not (one.roots_only and artifact.fields.get("root") == "False")
        )

    def due(self, artifact: ArtifactToJudge) -> int:
        """How many metrics this artefact is due, which is not how many calls.

        The rubric is one call returning six, so a root question is due
        eleven metrics from six calls. Counted in calls, a rubric that
        abstained would cost a verdict one metric rather than six.
        """
        return sum(len(one.metrics) for one in self.asked(artifact))

    def judge(self, artifact: ArtifactToJudge) -> tuple[Judgement, ...]:
        """Asks every metric this artefact is due.

        One call per metric, deliberately. Three judgements in one call is
        what `question_generation/phrasing.py` exists to undo. The paper's
        rubric is the one exception, asked as the paper asked it - see
        `templates.Rubric`.

        Returns:
            One judgement per metric that answered, in template order. Short
            of the full set where a call abstained.

        Raises:
            JudgeUnavailable: If no metric answered, which means the model
                is down rather than that the artefact is bad.
        """
        asked = self.asked(artifact)
        answered = [
            judged for template in asked for judged in self._one(template, artifact)
        ]
        if not answered:
            raise JudgeUnavailable(
                f"{self.model} answered none of the {len(asked)} judgement(s) "
                f"about {artifact.kind} {artifact.artifact_id}"
            )
        due = self.due(artifact)
        if len(answered) < due:
            log.warning(
                "%s %d: %d of %d metric(s) answered; the rest abstained",
                artifact.kind,
                artifact.artifact_id,
                len(answered),
                due,
            )
        return tuple(answered)

    def _one(
        self, template: Template, artifact: ArtifactToJudge
    ) -> tuple[Judgement, ...]:
        """One call's metrics, or none where the model could not be reached."""
        try:
            said = self._client.answer(
                system=template.system,
                user=template.rendered(**artifact.fields),
                shape=template.shape(),
                prompt_version=PROMPT_VERSION,
            )
        except ModelUnavailable as exc:
            # Logged and abstained, never raised past the artefact: losing
            # one opinion must not fail a row the other two judged.
            log.warning(
                "no %s judgement for %s %d: %s",
                template.metric,
                artifact.kind,
                artifact.artifact_id,
                exc,
            )
            return ()
        return template.judged(said)
