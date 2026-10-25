"""Command-line entry point for the topic modelling service.

Every flag is the same operation as the route beside it under /topics.
`--discover` only queues a fit; pass it with no other flag to queue and drain
in one go. Run with --help for the list.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import telemetry
from blob_store.s3 import ArchiveBucket, ExportBucket, ModelsBucket
from database.qa_generator import Status, engine
from llm.check import before_work
from llm.config import Settings as ModelSettings
from llm.tally import carry
from settings import decimal, optional
from settings.runs import named_run, run_id
from settings.store import snapshot
from stages import watch
from stages.cli import (
    FAILED,
    REFUSED,
    _ready,
    drain_once,
    give_back,
    parser,
    reloading,
)
from stages.prompts import record
from topic_modelling import prompts
from topic_modelling.config import Settings
from topic_modelling.factory import build_service
from topic_modelling.models import TopicFit
from topic_modelling.repository import QuestionsRunning, TopicCatalog, TopicQueue
from topic_modelling.space import load

log = logging.getLogger(__name__)

#: This stage's actions. No --start or --rerun: a refit and a first fit are
#: the same request.
_ACTIONS = {
    "status": "report the fit queue and the topics held",
    "discover": "queue a fit over the whole corpus",
    "visualise": "write each language's pyLDAvis page to a file",
    "render": "redraw each language's page from its stored model",
    "stop": "withdraw a queued fit",
    "retry": "return a failed fit to the queue",
    "delete": "delete every topic and membership",
    "name": "name the topics a fit left unnamed, off the stored fit and with no refit",
}

#: Where --visualise writes, one file per modelled language.
_DRAWN = Path("topics")


def unfitted(fit: TopicFit, languages: list[str]) -> list[str]:
    """The languages with passages that hold no topic."""
    fitted = {one.language for one in fit.languages if one.topics}
    return [language for language in languages if language not in fitted]


def fit_needed(fit: TopicFit, languages: list[str]) -> str | None:
    """Why the corpus needs a fit before a bridge or a question, or None.

    A language that holds passages and no topic, or whose topics no longer
    fit its passages. The languages are the corpus's own.
    """
    if missing := unfitted(fit, languages):
        return f"no topics yet for {', '.join(missing)}"
    if stale := [one.language for one in fit.languages if one.stale]:
        return f"the topics of {', '.join(stale)} no longer fit its passages"
    return None


def main(argv: list[str] | None = None) -> int:
    """Runs the topic modelling command line.

    Args:
        argv: The arguments, defaulting to the process's own.

    Returns:
        The exit status.
    """
    built = parser("topic_modelling.run", _ACTIONS)
    built.add_argument(
        "--ensure",
        action="store_true",
        help="with --discover, fit only when a language holds passages and no "
        "topic or its topics are stale, else drain a fit already queued, and "
        "fail if a language still has no topic afterwards. What make corpus "
        "asks for.",
    )
    built.add_argument(
        "--language",
        metavar="CODE",
        help="with --render, redraw only this language. One model is kept "
        "per language and the next fit replaces it, so this chooses which "
        "LANGUAGE to redraw and not which fit to redraw from.",
    )
    args = built.parse_args(sys.argv[1:] if argv is None else argv)
    if args.ensure and not args.discover:
        raise SystemExit("--ensure goes with --discover")
    carry(optional("SPEND_LEDGER"))

    def build():
        """Builds the service from the settings as they stand.

        Called rather than captured: a watching worker rebuilds when a
        setting changes. One read for the settings and the version.
        """
        source, version = snapshot("topics")
        return build_service(Settings.load(source), version)

    # With the run, as `stages/cli.queue_main` does for the other four
    # stages, and with no exporter until the model check has passed.
    telemetry.configure(
        "topic_modelling", run=run_id(), named=named_run(), tracing=False
    )

    if args.status:
        queue = TopicQueue()
        log.info("topics and the fit queue: %s", queue.counts())
        log.info("%d passage(s) are in no topic", queue.unplaced())
        return 0

    if args.visualise:
        return _visualise()

    if args.render:
        return _render(args.language)

    if args.delete:
        try:
            removed = TopicCatalog().delete_all()
        except QuestionsRunning as exc:
            log.error("%s", exc)
            return 1
        # The figures go with the topics, as they do on the route. `delete_all`
        # reports the languages whose figure is now orphaned and this read that
        # list and dropped it, so the command left the pyLDAvis pages in the
        # export bucket describing topics that no longer existed.
        bucket, archive = ExportBucket(), ArchiveBucket()
        models = ModelsBucket()
        figures = sum(
            archive.take(bucket.name, bucket.topic_visualisation_key(language))
            for language in removed.languages
        )
        # The model goes with the figure. A factorisation of topics that no
        # longer exist describes nothing, and leaving it is the same orphan
        # the figures were before this read `removed.languages`.
        kept = sum(
            archive.take(models.name, models.topic_model_key(language))
            for language in removed.languages
        )
        log.info(
            "archived %d topic(s), %d membership(s), %d figure(s) and %d "
            "model(s); %d label(s) lost",
            removed.topics,
            removed.memberships,
            figures,
            kept,
            removed.labels,
        )
        return 0

    if args.stop:
        log.info("withdrew %d queued fit(s)", TopicQueue().stop())
        return 0

    if args.retry:
        log.info(
            "returned %d fit(s) to the queue",
            TopicQueue().retry(trigger=run_id()),
        )
        return 0

    asking = args.discover
    if args.ensure:
        queue = TopicQueue()
        reason = fit_needed(TopicCatalog().fit_state(), queue.languages())
        # A fit a resume returned to the queue (make corpus RESUME=1 runs
        # topics-retry first) is drained rather than left pending for good.
        waiting = queue.counts_by_status().get(Status.PENDING, 0)
        if reason is None and not waiting:
            log.info("every language holds topics that fit its passages")
            return 0
        if reason is None:
            log.info("draining the %d fit(s) already queued", waiting)
            asking = False
        else:
            log.info("fitting the topics: %s", reason)

    naming: list[ModelSettings | None] = []

    def preflight() -> None:
        """Reads the settings, and asks the naming model where one is configured.

        As `stages/cli.queue_main` does for the other four, and through the
        same wait, so a worker whose stored settings are refused waits in
        place. The model only where one is configured: this stage names
        topics with one where it has one, and falls back to their terms where
        it does not, so an absent model is a choice and an unanswering one is
        a fit that would fail on every label.
        """
        model = Settings.load(snapshot("topics")[0]).model
        if model is not None:
            before_work(model)
        naming[:] = [model]

    # Before anything is built or a fit asked for: a refused start leaves the
    # queue as it was, and says so with REFUSED.
    if not _ready("topic_modelling", preflight, args.watch):
        return REFUSED
    if (model := naming[0]) is not None:
        # Here rather than at the top, for the same reason `before_work` is:
        # a deployment with no model never sends this prompt, and a row
        # saying it did would be a record of a call nothing made.
        record(prompts.SERVICE, prompts.catalogue(), model)

    # A worker builds its service in the watch loop, which waits on settings
    # it cannot build on rather than exiting; a one-off drain and a fit asked
    # for build it here.
    service = build() if args.discover or not args.watch else None
    if service is not None and asking:
        try:
            log.info("queued topic fit %d", service.request(run_id()))
        except QuestionsRunning as exc:
            log.error("%s", exc)
            return 1

    telemetry.configure("topic_modelling", run=run_id(), named=named_run())
    telemetry.trace_engine(engine())

    if args.name and service is not None:
        service.name_unnamed()
        return 0

    if service is not None and not args.watch:
        code = drain_once(service)
        if args.ensure:
            languages = TopicQueue().languages()
            if missing := unfitted(TopicCatalog().fit_state(), languages):
                log.error("no topic for %s after the fit", ", ".join(missing))
                return code or FAILED
        return code

    serving: dict[str, Any] = {}
    watch(
        reloading("topic_modelling", build, held=serving),
        decimal("WORKER_POLL_SECONDS"),
        give_back(serving),
    )
    return 0


def _render(only: str | None = None) -> int:
    """Redraws each language's figure from its stored model.

    The fit draws one as it goes, and this is how a figure comes back
    without one: `export` holds a view and `models` holds what the view is
    of, so a lost or corrupted page costs a render rather than a re-fit of
    the corpus.

    **The figure it writes replaces the one already there.** The key is one
    per language, and the render is deterministic - the same stored model
    through the same `prepare` gives the same page - so rewriting it is
    idempotent rather than lossy.

    **Which model is not a choice, and cannot be.** One model is kept per
    language because the database holds one fit's topics per language:
    `replace` drops a fitted language's rows and writes the new fit's. A figure drawn from an older model
    would number its topics off rows that are gone, which is the orphan a
    fit already avoids by taking the old figure away before drawing the
    new one. `only` therefore picks a LANGUAGE.

    Args:
        only: Redraw this language alone, or every modelled one.

    Returns:
        1 if nothing was drawn, else 0.
    """
    # pyLDAvis, imported here for the reason the service defers it: it is
    # needed by this one action and by nothing else the command line does.
    try:
        from topic_modelling.visualisation import render
    except ImportError:
        log.exception("pyLDAvis is missing, so nothing can be drawn")
        return 1

    models, export = ModelsBucket(), ExportBucket()
    languages = [one.language for one in TopicCatalog().fit_state().languages]
    if only is not None:
        languages = [one for one in languages if one == only]
        if not languages:
            log.error("no topics are stored for %s", only)
            return 1
    if not languages:
        log.error("no topics are stored, so there is nothing to draw")
        return 1

    drawn = 0
    for language in languages:
        held = models.find(models.topic_model_key(language))
        if held is None:
            log.warning(
                "no %s model is stored, so its figure cannot be redrawn. Only "
                "a fit since this bucket existed leaves one, so run --discover",
                language,
            )
            continue
        key = export.topic_visualisation_key(language)
        # Away before the new one goes in, exactly as the fit does it: a
        # language whose render raises should have no figure rather than
        # the one belonging to whatever was there before.
        export.remove(key)
        try:
            page = render(load(held), language)
            export.put(key, page, content_type=export.TOPIC_VISUALISATION_TYPE)
        except Exception:
            log.exception("could not redraw the %s figure", language)
            continue
        drawn += 1
        log.info("redrew the %s figure from its model (%d bytes)", language, len(page))
    return 0 if drawn else 1


def _visualise() -> int:
    """Writes every stored visualisation to `_DRAWN`, one file per language.

    Returns:
        1 if no topics are stored or no language had a figure, else 0.
    """
    export = ExportBucket()
    languages = [one.language for one in TopicCatalog().fit_state().languages]
    if not languages:
        log.error("no topics are stored, so there is nothing to draw")
        return 1

    _DRAWN.mkdir(parents=True, exist_ok=True)
    missing = 0
    for language in languages:
        drawn = export.find(export.topic_visualisation_key(language))
        if drawn is None:
            log.warning(
                "no %s visualisation; it is drawn by a fit, so run --discover",
                language,
            )
            missing += 1
            continue
        written = _DRAWN / f"{language}.html"
        written.write_bytes(drawn)
        log.info("wrote %s (%d bytes)", written, len(drawn))
    return 1 if missing == len(languages) else 0


if __name__ == "__main__":
    raise SystemExit(main())
