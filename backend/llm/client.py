"""Asking a served model for an answer in a shape.

Importing this loads litellm. Nothing outside a worker should name it.
"""

from __future__ import annotations

import logging
import math
import re
import time
from collections.abc import Callable, Iterator
from typing import Any, TypeVar

import instructor
import litellm
from instructor.core import InstructorRetryException
from pydantic import BaseModel
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    wait_exponential,
)

import telemetry
from llm import tally
from llm.config import Settings

log = logging.getLogger(__name__)

#: How much of the context window a prompt may use before the call is
#: worth a warning. Four fifths.
_NEAR_WINDOW = 0.8

#: Failures worth another attempt here, and the only retries there are: the
#: call asks litellm, the provider's SDK and instructor for none. An
#: authentication failure, an unknown model, a refused prompt or a malformed
#: request is none of these and is raised at once. A rate limit waits as long
#: as its Retry-After asks; see `_waited`. An `InstructorRetryException` is
#: here because a schema the model failed to fill is worth asking again, but
#: instructor also wraps what the provider refused, and `_retryable` takes
#: those back out.
_TRANSIENT = (
    litellm.exceptions.APIConnectionError,
    litellm.exceptions.Timeout,
    litellm.exceptions.InternalServerError,
    litellm.exceptions.BadGatewayError,
    litellm.exceptions.ServiceUnavailableError,
    litellm.exceptions.RateLimitError,
    InstructorRetryException,
)

#: What a provider says when the request itself is the trouble. Asking again
#: sends the same request. A content-policy refusal is a `BadRequestError`.
_REJECTED = (
    litellm.exceptions.BadRequestError,
    litellm.exceptions.AuthenticationError,
    litellm.exceptions.NotFoundError,
    litellm.exceptions.PermissionDeniedError,
)


def _causes(failure: BaseException) -> Iterator[BaseException]:
    """The failure and every exception behind it, nearest first."""
    seen: set[int] = set()
    at: BaseException | None = failure
    while at is not None and id(at) not in seen:
        seen.add(id(at))
        yield at
        at = at.__cause__ or at.__context__


def _refused(failure: BaseException) -> bool:
    """Whether the provider refused the prompt under its content policy."""
    return any(
        isinstance(cause, litellm.exceptions.ContentPolicyViolationError)
        for cause in _causes(failure)
    )


#: What says the whole deployment is out of reach, as against one request
#: refused: the connection, the clock, the provider's own trouble, a quota,
#: and the credentials or the deployment's name, which every row meets alike.
_DEPLOYMENT = (
    litellm.exceptions.APIConnectionError,
    litellm.exceptions.Timeout,
    litellm.exceptions.InternalServerError,
    litellm.exceptions.BadGatewayError,
    litellm.exceptions.ServiceUnavailableError,
    litellm.exceptions.RateLimitError,
    litellm.exceptions.AuthenticationError,
    litellm.exceptions.NotFoundError,
    litellm.exceptions.PermissionDeniedError,
)


def _server_fault(cause: BaseException) -> bool:
    """Whether a provider's 5xx has no litellm type of its own: a bare `APIError`."""
    return (
        isinstance(cause, litellm.exceptions.APIError)
        and isinstance(cause.status_code, int)
        and cause.status_code >= 500
    )


def deployment_down(failure: BaseException) -> bool:
    """Whether a failure says the deployment, not the request, is the trouble.

    The nearest cause that names either decides: a request the provider
    rejects for itself (too long, malformed, filtered) and a shape the model
    could not fill name neither, and the next row is not bound to meet them.
    """
    for cause in _causes(failure):
        if isinstance(cause, _DEPLOYMENT) or _server_fault(cause):
            return True
        if isinstance(cause, litellm.exceptions.BadRequestError):
            return False
    return False


def _retryable(failure: BaseException) -> bool:
    """Whether asking again could end differently.

    A transient type, except an instructor failure with a rejected request
    behind it: instructor wraps whatever its last attempt raised, so a
    refused prompt arrives looking like a schema the model could not fill.
    """
    if not (isinstance(failure, _TRANSIENT) or _server_fault(failure)):
        return False
    return not any(isinstance(cause, _REJECTED) for cause in _causes(failure))


#: The wait between attempts when the failure says nothing of its own.
_BACKOFF = wait_exponential(multiplier=1, min=1, max=10)

#: The longest a Retry-After is waited, in seconds. A provider may ask for
#: an hour, and a worker waiting it holds its row that long every attempt.
_LONGEST_WAIT = 120.0


#: The most one call waits out rate limits in all, in seconds, however many
#: it meets. A 429 is the provider saying when to come back, not the call
#: failing, so it does not use up `LLM_MAX_ATTEMPTS`; what bounds it is this,
#: after which the call fails as any other that ran out of attempts. Ten
#: minutes is five of the longest wait `_LONGEST_WAIT` allows.
_RATE_LIMIT_PATIENCE = 600.0


def _rate_limited(failure: BaseException) -> bool:
    """Whether the provider said to slow down, wherever it is behind the failure."""
    return any(
        isinstance(cause, litellm.exceptions.RateLimitError)
        for cause in _causes(failure)
    )


def _patience(attempts: int) -> Callable[[RetryCallState], bool]:
    """When to stop retrying: `attempts` real failures, or too long rate-limited.

    A rate limit is waited out and not counted, so drains sharing one quota
    that meet it together do not fail rows three rounds in: they wait their
    Retry-After and ask again, up to `_RATE_LIMIT_PATIENCE`.
    """

    def stop(state: RetryCallState) -> bool:
        """Whether the failure just seen was the last this call may have."""
        failure = state.outcome.exception() if state.outcome else None
        if failure is not None and _rate_limited(failure):
            return state.idle_for >= _RATE_LIMIT_PATIENCE
        # Per call: tenacity resets the statistics as each call begins.
        statistics = state.retry_object.statistics
        statistics["failures"] = statistics.get("failures", 0) + 1
        return statistics["failures"] >= attempts

    return stop


def _waited(state: RetryCallState) -> float:
    """How long to wait before the next attempt.

    What a 429's Retry-After asks, in seconds, where it carries one, up to
    `_LONGEST_WAIT`. Read off the 429 wherever it is behind the failure,
    because instructor wraps whatever its call raised. The backoff
    otherwise, an HTTP-date included.
    """
    failed = state.outcome.exception() if state.outcome else None
    for cause in _causes(failed) if failed else ():
        if isinstance(cause, litellm.exceptions.RateLimitError):
            try:
                asked = float(cause.response.headers.get("retry-after", ""))
            except ValueError:
                break
            # A negative or non-finite one would make the sleep itself raise.
            if not math.isfinite(asked) or asked < 0:
                break
            return min(asked, _LONGEST_WAIT)
    return _BACKOFF(state)


#: Reasoning a model wrote into the answer instead of into a field of its
#: own. A well-behaved runtime keeps the two apart - Ollama returns
#: `message.thinking` beside `message.content`, and litellm carries it as
#: `reasoning_content` - but plenty of open weights emit the tags inline,
#: and then the answer is valid JSON with an essay in front of it.
#:
#: Matched non-greedily and per tag name, so two blocks in one answer are
#: two matches rather than everything between the first and the last.
_REASONING = re.compile(
    r"<(think|thinking|reasoning)\b[^>]*>.*?</\1\s*>", re.DOTALL | re.IGNORECASE
)

#: An opening tag that never closed, which is a model cut off mid-thought.
#: Everything after it is reasoning, so there is no answer in this response
#: - stripping it to nothing is what makes the parser say so.
_UNCLOSED = re.compile(
    r"<(think|thinking|reasoning)\b[^>]*>.*\Z", re.DOTALL | re.IGNORECASE
)

Shape = TypeVar("Shape", bound=BaseModel)


def without_reasoning(text: str) -> str:
    """The answer with any inline reasoning taken out of it.

    Returns the text unchanged when there is none, which is the common
    case and every non-reasoning model: this only ever removes, so a
    model that never thinks pays a regex miss and nothing else.
    """
    return _UNCLOSED.sub("", _REASONING.sub("", text)).strip()


def answering(completion: Any, seen: Callable[[Any], None] | None = None) -> Any:
    """Wraps a completion function so inline reasoning never reaches the parser.

    One place, because every call in this pipeline goes through instructor
    and instructor parses `message.content`. A model that puts its thinking
    there hands the parser an essay with JSON somewhere inside it, which
    fails the schema, retries, fails again and arrives as `ModelUnavailable`
    - a model that answered correctly, reported as one that could not be
    reached.

    Left alone otherwise. The field is not read, not counted and not
    recorded: a response carrying no reasoning is not a response missing
    anything, so there is nothing here to fail on when a model never
    produces any.

    An answer the provider's content filter withheld is raised here as the
    refusal it is. It comes back a 200 that litellm raises nothing for, and
    its empty content would otherwise fail the schema on every attempt and
    arrive as `ModelUnavailable`, though the same prompt is filtered again.

    `seen` is handed every response before anything is read off it: each
    was billed, whether or not an answer came of it.
    """

    def called(*args: Any, **kwargs: Any) -> Any:
        """Calls the model and cleans each choice's content in place."""
        response = completion(*args, **kwargs)
        if seen is not None:
            seen(response)
        for choice in getattr(response, "choices", ()) or ():
            if getattr(choice, "finish_reason", None) == "content_filter":
                # A BadRequestError, so `_retryable` stops and `_refused`
                # finds it behind instructor's wrapping.
                raise litellm.exceptions.ContentPolicyViolationError(
                    message="the provider filtered the answer "
                    "(finish_reason=content_filter)",
                    model=str(kwargs.get("model", "")),
                    llm_provider="",
                )
            message = getattr(choice, "message", None)
            content = getattr(message, "content", None)
            if message is None or not content:
                continue
            cleaned = without_reasoning(content)
            if cleaned != content:
                log.debug(
                    "dropped %d character(s) of inline reasoning",
                    len(content) - len(cleaned),
                )
                message.content = cleaned
        return response

    return called


class ModelUnavailable(Exception):
    """Raised when the model could not be reached or would not answer."""


class ModelRefused(ModelUnavailable):
    """Raised when the provider refused the prompt, or its answer, for what it says."""


def _warn_unpriced(completion: Any) -> None:
    """Says once per model that its calls cannot be counted towards a cap."""
    model = str(getattr(completion, "model", None) or "an unknown model")
    if tally.note_unpriced(model):
        log.warning(
            "%s has no price in litellm, so its calls add nothing to the spend "
            "tally, and a SPEND_CAP cannot bound them",
            model,
            extra={"llm.model": model, "llm.unpriced": True},
        )


def spend(completion: Any) -> dict[str, Any]:
    """What one answer consumed, as the fields it is logged under.

    Tokens and money are read off the response rather than counted here: the
    provider is the only thing that knows what it billed for, and a count of
    our own would disagree with the invoice over a cached prefix or a
    reasoning trace.

    A model with no published price - anything self-hosted - is costed at
    zero by litellm, and zero yields no `llm.cost_usd` at all rather than the
    field set to it. Zero is a number a dashboard sums and reports as free;
    absent is a field it has nothing to sum, which is the truth about a model
    somebody is running on their own hardware.

    A model litellm cannot price at all is not that: the call is logged with
    `llm.unpriced`, and the model is warned about once per process.

    Never raises. A call that has already been paid for and answered must not
    be lost because the arithmetic about what it cost went wrong.
    """
    fields: dict[str, Any] = {}
    usage = getattr(completion, "usage", None)
    if usage is not None:
        fields["llm.tokens.input"] = getattr(usage, "prompt_tokens", None)
        fields["llm.tokens.output"] = getattr(usage, "completion_tokens", None)
    try:
        cost = litellm.completion_cost(completion_response=completion)
    except Exception:  # noqa: BLE001 - any failure here is the same answer
        # A response it cannot read a model off, or a model missing from its
        # price list. An unpriced self-hosted model is neither: that comes
        # back as zero.
        cost = 0.0
        fields["llm.unpriced"] = True
        _warn_unpriced(completion)
    if cost:
        fields["llm.cost_usd"] = float(cost)
    return {name: value for name, value in fields.items() if value is not None}


def _summed(responses: list[Any]) -> dict[str, Any]:
    """What every response one answer took consumed, `spend` field by field."""
    total: dict[str, Any] = {}
    for response in responses:
        for name, value in spend(response).items():
            total[name] = (
                value if name == "llm.unpriced" else total.get(name, 0) + value
            )
    tally.add(total.get("llm.cost_usd", 0.0))
    return total


def priced(fields: dict[str, Any]) -> str:
    """What `spend` found, for the end of a log line a person reads.

    The JSON copy carries the fields whether or not this renders them; this
    is the half somebody watching `make logs` sees, and a run against a
    hosted provider is one where what it has cost so far is the number
    being watched.
    """
    written = []
    if "llm.tokens.input" in fields:
        written.append(f"{fields['llm.tokens.input']:,} in")
    if "llm.tokens.output" in fields:
        written.append(f"{fields['llm.tokens.output']:,} out")
    if "llm.cost_usd" in fields:
        written.append(f"${fields['llm.cost_usd']:.4f}")
    return f" ({', '.join(written)})" if written else ""


#: The instructor modes `instructor.from_litellm` builds a client for. Every
#: other mode is another client's, and refused there in words that name
#: neither LLM_STRUCTURED_MODE nor a value that would work.
#: `settings.catalog` offers the same names, spelled out.
LITELLM_MODES = (
    "FUNCTIONS",
    "PARALLEL_TOOLS",
    "TOOLS",
    "TOOLS_STRICT",
    "JSON",
    "JSON_O1",
    "MD_JSON",
    "JSON_SCHEMA",
)


def mode(name: str) -> instructor.Mode:
    """Turns a mode name from the environment into the mode itself."""
    named = name.strip().upper()
    if named not in LITELLM_MODES:
        raise ValueError(
            f"LLM_STRUCTURED_MODE={name!r} is not a mode litellm takes; expected "
            f"one of {', '.join(LITELLM_MODES)}"
        )
    return instructor.Mode[named]


class Client:
    """One served model, asked for answers in a declared shape."""

    def __init__(self, settings: Settings) -> None:
        """Builds the client and the retry policy around one call."""
        # Here rather than in telemetry.configure, which the api runs too:
        # the instrumentor imports litellm, and this module is the one that
        # already has. Idempotent, and two stages build two clients.
        telemetry.instrument_llm()
        # Lets an azure/* model authenticate with Entra ID instead of a key.
        # Read on the azure path only, and only when no key is set.
        litellm.enable_azure_ad_token_refresh = True
        self._settings = settings
        # Every response the answer being asked for has taken, a failed
        # attempt's included: each was billed, and is logged with it.
        self._responses: list[Any] = []
        # Any: instructor replaces create() at run time, so a checker would
        # match these keywords against the unpatched signature.
        self._client: Any = instructor.from_litellm(
            answering(litellm.completion, self._responses.append),
            mode=mode(settings.structured_mode),
        )
        # Only `_retryable`: retrying a bad model name, a refused prompt or a
        # schema costs the backoff on every call and buries the real error.
        self._attempt = retry(
            retry=retry_if_exception(_retryable),
            stop=_patience(settings.max_attempts),
            wait=_waited,
            reraise=True,
        )(self._ask)

    @property
    def model(self) -> str:
        """The model identifier, recorded on whatever the answer becomes."""
        return self._settings.model

    @property
    def temperature(self) -> float:
        """The sampling temperature, recorded alongside the model."""
        return self._settings.temperature

    def answer(
        self,
        *,
        system: str,
        user: str,
        shape: type[Shape],
        prompt_version: str | None = None,
    ) -> Shape:
        """Asks the model one question and parses the answer into `shape`.

        Timed, counted and logged either way. The model is the pipeline's
        bottleneck, so how long a call took is the one number worth having
        per call, and against a hosted provider what it cost is the second.
        Both are in the logs as well as in the traces, which is what makes
        them readable when the collector is down or was never configured.

        `prompt_version` is the caller's own PROMPT_VERSION, and it goes on
        the log line and the span alike. Two prompts are two datasets, and
        without it a run under version 7 and a run under version 8 are the
        same rows and the same spans. Optional, because a prompt that has
        never been versioned should say nothing rather than claim a
        version it does not have.

        Raises:
            ModelRefused: If the provider refused the prompt, or filtered
                the answer, under its content policy. Not retried.
            ModelUnavailable: If it could not be reached, or did not return
                the requested shape after every attempt.
        """
        started = time.monotonic()
        self._responses.clear()
        # Shared by both lines below, so a failed call is counted in the
        # same fields a successful one is.
        about = {
            "llm.model": self._settings.model,
            "llm.shape": shape.__name__,
        }
        if prompt_version:
            about["llm.prompt_version"] = prompt_version
        try:
            # The same two facts on the span the instrumentor opens inside,
            # spelled as they are in `about`, so a call reads the same in
            # Phoenix and in Grafana.
            with telemetry.asking(shape.__name__, prompt_version):
                answered, completion = self._attempt(system, user, shape)
        except Exception as exc:
            # Logged with the traceback before it is rewrapped: what the
            # caller records against the row is one line, and litellm's own
            # cause is the only thing that says which of the layers below
            # failed. Priced as the answered line is: every attempt was billed.
            elapsed = self._since(started)
            billed = _summed(self._responses)
            log.exception(
                "%s did not answer %s in %.1fs%s",
                self._settings.model,
                shape.__name__,
                elapsed / 1000,
                priced(billed),
                extra=about | {"llm.duration_ms": elapsed} | billed,
            )
            refusal = ModelRefused if _refused(exc) else ModelUnavailable
            raise refusal(f"{type(exc).__name__}: {exc}") from exc

        elapsed = self._since(started)
        # The last response alone: each attempt had a window of its own.
        self._warn_if_near_the_window(spend(completion), shape)
        spent = _summed(self._responses)
        log.info(
            "%s answered %s in %.1fs%s",
            self._settings.model,
            shape.__name__,
            elapsed / 1000,
            priced(spent),
            extra=about | {"llm.duration_ms": elapsed} | spent,
        )
        return answered

    def _warn_if_near_the_window(self, spent: dict, shape: type[Shape]) -> None:
        """Says so when a call came close to the context window.

        A runtime given more than its window TRUNCATES, dropping the oldest
        tokens - which is the system prompt. The answer comes back
        well-formed and confidently wrong, written without the rules it was
        supposed to follow, and nothing anywhere reports it: not the
        response, not the gates, not the row.

        **Prompt AND completion, because the window holds both.** This read
        the prompt alone, which was the whole story while nothing thought.
        A reasoning model moved the overflow to the other end.

        Only where a window was asked for, which is a self-hosted model:
        a hosted provider sizes its own and refuses the parameter.
        """
        window = self._settings.window
        prompt = spent.get("llm.tokens.input") or 0
        completion = spent.get("llm.tokens.output") or 0
        used = prompt + completion
        if not window or not used or used < window * _NEAR_WINDOW:
            return
        log.warning(
            "%s: %s used %s of a %s-token window (%s in, %s out). Over it "
            "the oldest tokens are TRUNCATED - the system prompt first - "
            "and the answer comes back anyway, so raise LLM_NUM_CTX before "
            "this reaches it.",
            self._settings.model,
            shape.__name__,
            f"{used:,}",
            f"{window:,}",
            f"{prompt:,}",
            f"{completion:,}",
        )

    @staticmethod
    def _since(started: float) -> int:
        """Milliseconds since a monotonic reading."""
        return round((time.monotonic() - started) * 1000)

    def _ask(self, system: str, user: str, shape: type[Shape]) -> tuple[Shape, Any]:
        """Sends one request, returning the answer and the response it came in.

        `create_with_completion` rather than `create` because the tokens and
        the price are on the response and not on the parsed shape, and a
        second call to ask what the first one cost would be billed for.
        """
        return self._client.chat.completions.create_with_completion(
            model=self._settings.model,
            # None below the policy around this call: litellm turns this
            # keyword into the SDK's max_retries, and 0 also skips its own
            # retry wrapper, each of which retried a timeout in full.
            num_retries=0,
            # instructor's own re-asks, three by default: each is a billed
            # call inside one attempt here, so LLM_MAX_ATTEMPTS was not the
            # budget it says it is.
            max_retries=0,
            # Omitted when unset: a provider with its own address would be
            # sent to the wrong one by a base URL meant for Ollama.
            **(
                {"api_base": self._settings.base_url} if self._settings.base_url else {}
            ),
            # Derived per model, like the thinking below: a self-hosted
            # runtime reserves the whole window as cache and sizes its
            # parallelism from it, and a hosted provider refuses the
            # parameter outright. See `Settings.window`.
            **({"num_ctx": window} if (window := self._settings.window) else {}),
            # Omitted unless LLM_REASONING_EFFORT names one, which leaves a
            # model its own default: a reasoning model thinks and every
            # other model has nothing to turn off. See `Settings.thinking`
            # for why sending `off` by default broke the models that think.
            # Ollama reads this as `think`.
            **(
                {"reasoning_effort": thinking}
                if (thinking := self._settings.thinking)
                else {}
            ),
            temperature=self._settings.temperature,
            timeout=self._settings.timeout_seconds,
            response_model=shape,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
