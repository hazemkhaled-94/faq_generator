"""Command-line entry point for the question generation service.

Every flag is the same operation as the route beside it under /questions.
Run with --help for the list.
"""

from __future__ import annotations

import logging
import sys

import telemetry
from database.qa_generator import engine
from llm.check import before_work
from llm.client import Client
from llm.config import Settings as ModelSettings
from question_generation import prompts
from question_generation.catalog import QuestionCatalog
from question_generation.config import Settings
from question_generation.factory import build_service, models
from question_generation.queue import QuestionQueue
from question_generation.service import balance, rejudge, rescore, reverify
from question_generation.verifier import Verifier
from settings.runs import named_run, run_id
from settings.store import snapshot
from stages.cli import proved, queue_main
from stages.prompts import record

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Runs the question generation command line."""

    def configured() -> tuple[Settings, ModelSettings, str]:
        """Reads the settings as they stand, and what that configuration is.

        Called rather than captured, so every operation below answers to a
        value written since this process started. One read for both, so the
        settings and the version recorded cannot come from two moments.
        """
        source, version = snapshot("questions")
        return Settings.load(source), ModelSettings.load(source), version

    def balanced(within) -> int:
        """Draws the release over every accepted question, refusing --only.

        With the verifier the workers use, which judges whether two released
        questions want one answer, proved before the first pair is asked.
        """
        if within is not None:
            raise SystemExit("--balance draws the whole release and takes no --only")

        def ready() -> tuple[Settings, ModelSettings]:
            """The settings, and the verifier proved, before a pair is asked."""
            settings, model, _ = configured()
            _, verifier, _ = models(settings, model)
            before_work(verifier)
            return settings, verifier

        settings, verifier = proved(ready)
        # `queue_main` installs tracing only for a drain, so without this the
        # draw's spans and the verifier's calls were never exported, and its
        # log lines read trace 0. After the preflight, as a drain's is, so a
        # verifier that will not answer leaves no Phoenix project behind.
        telemetry.configure("questions", run=run_id(), named=named_run())
        telemetry.trace_engine(engine())
        return balance(QuestionCatalog(), settings, within, Verifier(Client(verifier)))

    def rejudged(within) -> int:
        """Re-judges the accepted unanswerable questions, with the verifier.

        The verifier the workers use, from the same settings, and proved
        before the first question is asked.
        """
        settings, model, _ = configured()
        _, verifier, _ = models(settings, model)
        before_work(verifier)
        return rejudge(QuestionCatalog(), settings, Verifier(Client(verifier)), within)

    #: This stage's own operation. No model is called: it puts the stored
    #: questions through the gates that need none, which is how a fact
    #: re-judged or a citation deleted reaches the questions resting on it.
    extra = {
        "reverify": (
            "check every stored question again, without calling a model",
            "rejected",
            lambda within: reverify(QuestionCatalog(), configured()[0], within),
        ),
        #: No model either: the four criteria columns read again off what a
        #: question cites now, which a re-verify then compares against.
        "rescore": (
            "rewrite every stored question's scopes and band from its citations",
            "rescored",
            lambda within: rescore(QuestionCatalog(), configured()[0], within),
        ),
        #: Which of the accepted questions make up the release. Accepting
        #: one says it is sound; this says what the SET looks like, and the
        #: two are different problems.
        "balance": (
            "draw a balanced release out of every accepted question",
            "released",
            balanced,
        ),
        #: The re-check that calls a model, and so is not part of reverify:
        #: whether the passages settle each accepted unanswerable question.
        "rejudge": (
            (
                "ask the verifier whether the passages settle each accepted "
                "unanswerable question, and reject those they do"
            ),
            "rejected",
            rejudged,
        ),
    }

    def build():
        """Builds the service, naming the models it will call."""
        settings, model, version = configured()
        writer, verifier, _ = models(settings, model)
        log.info(
            "writing with %s, verifying with %s, at %s",
            writer.model,
            verifier.model,
            model.base_url,
        )
        return build_service(settings, model, version)

    def preflight() -> None:
        """Proves the writer, the verifier and the phrasing judge answer.

        All three before a topic is claimed: a run whose verifier will not
        answer is a run of ungated questions, and an unreachable phrasing
        judge abstains once per question rather than failing the start.
        """
        settings, model, _ = configured()
        before_work(*models(settings, model))

    def record_prompts() -> int:
        """Records what this stage sends, each under the model it goes to.

        The settings as well as the shared model, because this stage sends
        to three: the writer's, the phrasing judge's and the verifier's.
        """
        settings, model, _ = configured()
        return record(prompts.SERVICE, prompts.catalogue(settings), model)

    return queue_main(
        name="questions",
        module="question_generation.run",
        repository=QuestionQueue,
        build_service=build,
        argv=sys.argv[1:] if argv is None else argv,
        extra=extra,
        preflight=preflight,
        prompts=record_prompts,
    )


if __name__ == "__main__":
    raise SystemExit(main())
