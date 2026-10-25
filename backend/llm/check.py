"""Whether a configured model answers, asked before a corpus finds out.

An unknown model id, an unreachable address, a missing credential and a
structured mode the provider will not accept all fail the same way: at the
first call. This is that first call, made once and on purpose.

    python -m api.doctor       # which is what `make doctor` runs, for
                               # every model a stage calls

A worker asks the same question before it claims anything, through
`reachable`. **A process that cannot call its model does not take work**,
because the alternative is a stage draining its queue into `failed` one
expensive timeout at a time.

Nothing here knows which provider is configured. The check is one ordinary
call through the same client a stage uses, so whatever authenticates a
stage authenticates this.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace

import litellm
from pydantic import BaseModel, Field

from llm.client import Client
from llm.config import (
    Settings,
    _self_hosted,
    check_split,
    describe,
    host_runner,
    ollama_address,
    spend_cap,
)
from llm.tally import unpriced_models

log = logging.getLogger(__name__)

#: Silenced while the check runs. Each of these narrates a refusal at
#: length - the client with its traceback, instructor once per attempt, a
#: credential library with every identity it tried - which is what a
#: worker's log wants and not what somebody reading a one-line verdict
#: does. The refusal is reported here instead, in one line.
QUIET = ("llm.client", "LiteLLM", "instructor", "azure.identity", "azure.core")


@contextmanager
def quiet() -> Iterator[None]:
    """Silences the libraries that narrate a refusal, for one call.

    Applied around the CHECK rather than only around `make doctor`, which
    is where it used to be. A worker asks this same question before every
    poll, and a worker whose Ollama is down produced tracebacks, litellm
    lines and every identity DefaultAzureCredential tried for a fact that
    fits in one sentence and that `stages.cli` was already writing.

    Restored afterwards, so the narration a real call needs survives: this
    is about the health check, not about the pipeline.
    """
    held = {name: logging.getLogger(name).level for name in QUIET}
    was = litellm.suppress_debug_info
    for name in QUIET:
        logging.getLogger(name).setLevel(logging.CRITICAL)
    litellm.suppress_debug_info = True
    try:
        yield
    finally:
        for name, level in held.items():
            logging.getLogger(name).setLevel(level)
        litellm.suppress_debug_info = was


#: Long enough for a cold local model to load, short enough that a wrong
#: address is a failure rather than a wait. LLM_TIMEOUT_SECONDS is the
#: pipeline's patience with a slow passage and is not this.
TIMEOUT_SECONDS = 90.0


class Unreachable(Exception):
    """A configured model did not answer, and a stage must not start."""


class Reachable(BaseModel):
    """The smallest structured answer a provider can be asked for."""

    ok: bool = Field(description="true")


def reachable(settings: Settings) -> None:
    """Asks one model a trivial question, proving the path a stage needs.

    The address resolves, the credential is accepted, the model exists, and
    it can return an object rather than prose. One attempt and a short
    patience: this reports what happened rather than working around it, and
    the usual backoff would hide an address that is simply wrong.

    Args:
        settings: The model to ask, as the caller will call it.

    Raises:
        Unreachable: If it did not answer in shape.
    """
    once = replace(
        settings, timeout_seconds=TIMEOUT_SECONDS, max_attempts=1, num_ctx=None
    )
    try:
        with quiet():
            Client(once).answer(
                system="You answer with a JSON object and nothing else.",
                user="Set ok to true.",
                shape=Reachable,
            )
    except Exception as refusal:
        where = settings.base_url or "the provider's own address"
        raise Unreachable(
            f"{settings.model} at {where} did not answer: "
            f"{type(refusal).__name__}: {refusal}"
        ) from refusal


def before_work(*models: Settings) -> None:
    """Refuses to start when a model a stage is about to call will not answer.

    Passed to `stages.cli.queue_main` as its preflight by extraction,
    question generation and assessment; topic modelling calls it itself.
    Runs before the watch loop rather than inside it, because that loop logs
    an exception and retries - which is right for a drain that failed and
    wrong for a deployment that can never work.

    Args:
        *models: Every model this stage calls, writer and verifier alike.
            Repeats are asked once.

    A drain with SPEND_CAP set also refuses a model litellm cannot price: its
    calls would add nothing to the tally the cap is read from, so the cap
    would hold for the other roles and say nothing about this one. The
    answer to the question above is priced as any other, so this is read off
    it and not guessed from the name.

    The drain's split is logged first, in one line. Under HOST_RUNNER=1 a role
    that is unset or resolves to an Ollama model - in the files, or in what
    this stage resolved from the stored settings - is refused before any
    model is asked.

    Raises:
        Unreachable: If any of them did not answer, or one has no price while
            a spend cap is set.
        ValueError: If HOST_RUNNER=1 and a role does not name a hosted model.
    """
    log.info("%s", describe())
    check_split()
    if host_runner():
        for settings in models:
            if _self_hosted(settings.model) or ollama_address(settings.base_url):
                raise ValueError(
                    f"HOST_RUNNER=1 runs hosted models only, and this stage "
                    f"resolved {settings.model}"
                    + (f" at {settings.base_url}" if settings.base_url else "")
                )
    for settings in {(m.model, m.base_url): m for m in models}.values():
        reachable(settings)
        log.info("%s answered; claiming work", settings.model)
    if spend_cap() is not None and (unpriced := unpriced_models()):
        raise Unreachable(
            f"SPEND_CAP is set and litellm has no price for "
            f"{', '.join(sorted(unpriced))} (asked as "
            f"{', '.join(sorted({m.model for m in models}))}), so its calls "
            "would not count towards the cap; unset SPEND_CAP or use a priced model"
        )
