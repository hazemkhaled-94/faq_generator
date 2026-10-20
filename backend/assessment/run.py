"""Command-line entry point for the assessment phase.

Every flag is the same operation as the route beside it under /assessment.
Run with --help for the list.

The one thing this stage does that no other does is refuse to run at all:
`ASSESSMENT_ENABLED` off means the queue verbs move nothing and a drain
claims nothing, said once and clearly rather than by silently finding an
empty queue.
"""

from __future__ import annotations

import logging
import sys
import time

import telemetry
from assessment import prompts
from assessment.config import OFF, UNNAMED, Settings, judged_kinds
from assessment.factory import build_service, judge_model
from assessment.repository import AssessmentQueue
from llm.check import before_work
from llm.config import Settings as ModelSettings
from settings import decimal
from settings.store import snapshot
from stages.cli import queue_main
from stages.prompts import record

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Runs the assessment command line."""

    def configured() -> tuple[Settings, ModelSettings, str]:
        """Reads the settings as they stand, and what that configuration is.

        Called rather than captured, so every operation below answers to a
        value written since this process started.
        """
        source, version = snapshot()
        return Settings.load(source), ModelSettings.load(source), version

    argv = sys.argv[1:] if argv is None else argv

    # The flag alone, and deliberately not through `configured`: that one
    # also reads the model settings, which are required and have no
    # default. A deployment with this phase off and no LLM_MODEL set is a
    # perfectly ordinary deployment, and it must not be stopped at
    # start-up by a setting for a model nothing is going to call.
    if not Settings.load(snapshot()[0]).enabled:
        telemetry.configure("assessment", tracing=False)
        log.info("%s", OFF)
        # A worker waits in place rather than exiting: under `restart:
        # unless-stopped` an exit is a restart every few seconds, and the
        # Assessment page switches the flag on without restarting anything.
        # ponytail: argv read by hand, as for --status below.
        if "--watch" not in argv:
            return 0
        while not Settings.load(snapshot()[0]).enabled:
            time.sleep(decimal("WORKER_POLL_SECONDS"))
        log.info("ASSESSMENT_ENABLED is on, so the worker starts claiming work")

    def build():
        """Builds the service, naming the model it will ask."""
        settings, model, version = configured()
        asked = judge_model(settings, model)
        log.info(
            "judging %s with %s",
            ", ".join(judged_kinds(settings)),
            asked.model,
        )
        return build_service(settings, model, version)

    def preflight() -> None:
        """Proves the judge answers before an artefact is claimed."""
        settings, model, _ = configured()
        before_work(judge_model(settings, model))

    def record_prompts() -> int:
        """Records what the judge asks, under the model that judges.

        `judge_model` and not the shared one: ASSESSMENT_JUDGE_MODEL is the
        whole point of this phase - an opinion the pipeline did not already
        hold - and a template published against the writer's model is one
        the playground replays against the wrong model.
        """
        settings, model, _ = configured()
        return record(
            prompts.SERVICE, prompts.catalogue(), judge_model(settings, model)
        )

    def queue() -> AssessmentQueue:
        """The queue this stage claims from."""
        settings, _, _ = configured()
        return AssessmentQueue(
            kinds=judged_kinds(settings),
            sample=settings.sample,
        )

    #: Enrolling without queuing: it writes the `new` rows and says how many
    #: artefacts this phase would judge before anybody commits to paying for
    #: them.
    extra = {
        "enrol": (
            (
                "create an assessment for every artefact that has none, "
                "without queuing any of them. What `--start` does first, "
                "on its own"
            ),
            "enrolled",
            lambda within: queue().enrol(),
        ),
    }

    code = queue_main(
        name="assessment",
        module="assessment.run",
        repository=queue,
        build_service=build,
        argv=argv,
        extra=extra,
        preflight=preflight,
        prompts=record_prompts,
    )
    # Logged after queue_main, which configures the logs.
    # ponytail: argv read by hand, so an abbreviated `--stat` skips this line;
    # the upgrade is a status hook on queue_main.
    if "--status" in argv and not Settings.load(snapshot()[0]).judge_model:
        log.warning("%s", UNNAMED)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
