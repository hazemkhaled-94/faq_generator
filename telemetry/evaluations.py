"""Posting a verdict to Phoenix, against the span that reached it.

A gate verdict was in two places and neither could be compared. Postgres
answers how many of each gate fired - `question_generation.runs` is that
query - and it cannot say what a gate COST, because the calls, the tokens
and the latency are in the spans. An attribute on the span joins the two
for filtering, and that is where this started.

This is the other half. Phoenix files an ANNOTATION separately from the
span it is about, which is what puts a verdict in its Evaluations view: a
label, a score and an explanation per span, sortable, chartable and
comparable across two projects without anybody writing a query. An
attribute cannot do that, because Phoenix does not know an arbitrary
attribute is a judgement.

`annotator_kind` is **CODE** and not LLM, and that distinction is the one
this repository cares about most. Every question gate is posted as CODE,
the phrasing judgements included; the assessment judge's verdicts are a
model's opinion and are posted as LLM, so the two can be told apart in the
one place they are shown together.

Best-effort throughout. Phoenix being unreachable must not fail a run that
is otherwise producing questions: everything here is caught and logged,
and the verdict is in Postgres either way. That is the same bargain
`traces.py` makes with an unreachable collector.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from opentelemetry import trace

if TYPE_CHECKING:
    from telemetry.projects import Project

log = logging.getLogger(__name__)

#: Where Phoenix's HTTP API is, as THIS process reaches it. One name for
#: both, the way OTEL_EXPORTER_OTLP_ENDPOINT is one name for both: .env
#: holds the host's address and compose overwrites it per container with
#: OTEL_CONTAINER_ENDPOINT's opposite number. Two names read in order was
#: the bug - the Makefile sources .env for a host command, so the container
#: address was set there too and preferred, and `make questions` posted its
#: verdicts to a hostname the host cannot resolve.
ENDPOINT = "PHOENIX_BASE_URL"

#: Phoenix's API key. compose passes PHOENIX_ADMIN_SECRET under the first
#: name; a host command has only the second, because that is what .env
#: calls it. Phoenix compares the bearer token against that value directly,
#: so they are the same credential - and without the fallback a host run
#: posted no annotations at all against an authenticated Phoenix.
API_KEY = ("PHOENIX_API_KEY", "PHOENIX_ADMIN_SECRET")

#: How many annotations are held before they are posted. One HTTP call per
#: question would cost more than the gate it is recording.
BATCH = 100

#: How long after a post fails before one is tried again. Verdicts recorded
#: meanwhile are dropped, as the batch that failed is: they are annotations,
#: and every one of them is in the database.
_RETRY_SECONDS = 300.0


@dataclass(frozen=True)
class Verdict:
    """One judgement about one span.

    Attributes:
        span_id: The span this is about, as Phoenix names it - the
            16-character hex OTel writes.
        name: What the judgement is called. One name per question in the
            Evaluations view, so `gate` rather than the gate's own code.
        label: The answer, as a word. The gate that fired, or `accepted`.
        score: The answer as a number, where there is one. 1 for accepted
            and 0 for refused, so a project's mean IS the acceptance rate.
        explanation: Why. The reason the checker already composed.
        by_model: Whether a model decided this rather than a rule.
        metadata: Anything else worth filtering on.
    """

    span_id: str
    name: str
    label: str
    score: float | None = None
    explanation: str = ""
    by_model: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        """This verdict as the annotation Phoenix takes."""
        result: dict[str, Any] = {"label": self.label}
        if self.score is not None:
            result["score"] = self.score
        if self.explanation:
            result["explanation"] = self.explanation
        annotation: dict[str, Any] = {
            "name": self.name,
            "annotator_kind": "LLM" if self.by_model else "CODE",
            "span_id": self.span_id,
            "result": result,
        }
        if self.metadata:
            annotation["metadata"] = dict(self.metadata)
        return annotation


def current_ids() -> tuple[str, str]:
    """The trace and the span being recorded into, as Phoenix names them.

    Both empty when nothing is recording. Empty rather than None because
    the caller that wants both is writing them onto a row, and a column
    holding "" for a run that exported no spans says the same thing a
    NULL would without a second branch to produce it.

    Phoenix resolves either from the hex alone -`getSpanByOtelId` is what
    its `/redirects/spans/` route is built on - so a row carrying these
    two is a row that links to its own trace without knowing anything
    about Phoenix's internal ids.
    """
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return "", ""
    return format(context.trace_id, "032x"), format(context.span_id, "016x")


class Evaluations:
    """Holds verdicts and posts them to Phoenix in batches.

    Nothing is built until the first verdict arrives, so a worker whose
    stage records none - every stage but question generation, today -
    never constructs a client or reads a setting.
    """

    def __init__(self, base_url: str | None = None, batch: int = BATCH) -> None:
        """Names where Phoenix is. Nothing is connected until asked."""
        self._base_url = base_url or os.getenv(ENDPOINT)
        self._off = os.getenv("TRACE_STORE", "phoenix").strip() == "none"
        self._batch = max(batch, 1)
        self._held: list[dict[str, Any]] = []
        self._client: Any = None
        #: No client package, which no wait mends.
        self._broken = False
        #: When a post may be tried again after one failed, on the
        #: monotonic clock, and whether this outage has been warned about.
        self._retry_at = 0.0
        self._warned = False
        if not self._base_url and not self._off:
            # The one failure with no other symptom: an unreachable Phoenix
            # warns from flush, and no address at all warned from nowhere.
            log.warning(
                "%s is unset, so gate verdicts stay in the database and this "
                "run records no annotations in Phoenix",
                ENDPOINT,
            )

    @property
    def enabled(self) -> bool:
        """Whether there is anywhere to post to, and it is worth trying now."""
        return (
            bool(self._base_url)
            and not self._off
            and not self._broken
            and time.monotonic() >= self._retry_at
        )

    def record(self, *verdicts: Verdict) -> None:
        """Holds some verdicts, posting once enough have piled up."""
        if not self.enabled:
            return
        self._held.extend(one.payload() for one in verdicts if one.span_id)
        if len(self._held) >= self._batch:
            self.flush()

    def flush(self) -> int:
        """Posts what is held, and reports how many went.

        Returns 0 and logs where Phoenix could not be reached. A run that
        is producing questions must not fail because the thing watching it
        is down.
        """
        if not self._held or not self.enabled:
            return 0
        held, self._held = self._held, []
        try:
            self._connect().annotate(held)
        except TraceStoreUnavailable:
            self._broken = True
            log.info(
                "arize-phoenix-client is not installed, so gate verdicts stay "
                "in the database and on the span and are not posted as "
                "annotations"
            )
            return 0
        except Exception as exc:  # noqa: BLE001 - any failure is the same answer
            # Not tried again for a while, rather than never: a watch worker
            # outlives a Phoenix restart by days. Warned once per outage,
            # not once per batch, which is the log nobody reads.
            self._retry_at = time.monotonic() + _RETRY_SECONDS
            if not self._warned:
                self._warned = True
                log.warning(
                    "could not record %d verdict(s) in Phoenix, and will try "
                    "again in %.0f min: %s: %s. The verdicts are in the database.",
                    len(held),
                    _RETRY_SECONDS / 60,
                    type(exc).__name__,
                    exc,
                )
            return 0
        self._warned = False
        log.debug("recorded %d verdict(s) in Phoenix", len(held))
        return len(held)

    def _connect(self) -> TraceStore:
        """The trace store, built once."""
        if self._client is None:
            self._client = trace_store(self._base_url)
        return self._client


class TraceStoreUnavailable(Exception):
    """The store cannot do this: its client is not installed, or there is none."""


class TraceStore(Protocol):
    """What the pipeline asks of the place its traces and evaluations are read.

    Spans are not here: they travel by OTLP, which every collector speaks, and
    `traces.py` follows `OTEL_EXPORTER_OTLP_PROTOCOL`. This is the rest of what
    Phoenix is used for: the annotations beside a span, the prompts a stage
    published, the projects a run filed under, the golden datasets and their
    experiments, and the retention of what it holds. `TRACE_STORE` names the
    adapter: `phoenix`, or `none` for a deployment that keeps traces somewhere
    that needs none of it (Azure Monitor).

    A method the store cannot serve raises `TraceStoreUnavailable`.
    """

    def annotate(self, annotations: list[dict[str, Any]]) -> None:
        """Files one annotation per span, a label, a score and an explanation each."""
        ...

    def publish_prompt(
        self,
        name: str,
        description: str,
        call: dict[str, Any],
        version_description: str,
        provider: str,
    ) -> None:
        """Sends one prompt version: an OpenAI-shaped call, as a template."""
        ...

    def projects(self) -> list[Project]:
        """Every project, and whether work happened in each."""
        ...

    def delete_project(self, project_id: str) -> bool:
        """Deletes one project, and says whether it went."""
        ...

    def datasets(self) -> list[dict[str, Any]]:
        """Every dataset, as at least an `id` and a `name`."""
        ...

    def delete_dataset(self, dataset_id: str) -> bool:
        """Deletes one dataset and its experiments, and says whether it went."""
        ...

    def set_retention(self, days: int) -> None:
        """Sets how long traces are kept.

        Raises:
            RuntimeError: If the store refuses.
        """
        ...

    def create_dataset(
        self,
        name: str,
        inputs: list[dict[str, Any]],
        outputs: list[dict[str, Any]],
        description: str,
    ) -> str:
        """Uploads a golden set, as a new version if it is there, and returns its id."""
        ...

    def run_experiment(
        self,
        dataset: str,
        task: Callable[..., Any],
        evaluators: dict[str, Callable[..., Any]],
        name: str,
        description: str,
        metadata: dict[str, Any],
    ) -> str:
        """Runs a task over a dataset, scored by the evaluators, and returns where to read it."""
        ...


class PhoenixStore:
    """The `TraceStore` over Phoenix: its client for annotations, prompts and experiments, its REST API for the rest.

    `sdk` and `session` are for a test, which hands over a stand-in for each;
    otherwise the client is built on first use, from PHOENIX_BASE_URL and the
    credential `API_KEY` names, and the session is `telemetry.projects`'s.
    """

    def __init__(
        self, base_url: str | None = None, *, sdk: Any = None, session: Any = None
    ) -> None:
        """Names where Phoenix is. Nothing is connected until asked."""
        self._base_url = base_url or os.getenv(ENDPOINT)
        self._sdk_client = sdk
        self._session = session

    def _sdk(self) -> Any:
        """The Phoenix client, built once.

        An absent address is NOT refused here - Phoenix's own default is
        localhost, which is right for a host command.

        Raises:
            TraceStoreUnavailable: Where arize-phoenix-client is not installed.
        """
        if self._sdk_client is None:
            try:
                from phoenix.client import Client
            except ImportError as missing:
                raise TraceStoreUnavailable(
                    "arize-phoenix-client is not installed"
                ) from missing
            key = next((os.getenv(name) for name in API_KEY if os.getenv(name)), None)
            self._sdk_client = Client(
                base_url=self._base_url,
                headers={"Authorization": f"Bearer {key}"} if key else None,
            )
        return self._sdk_client

    def _rest(self) -> Any:
        """The HTTP session on Phoenix's REST API."""
        if self._session is None:
            from telemetry import projects

            self._session = projects._client()
        return self._session

    def annotate(self, annotations: list[dict[str, Any]]) -> None:
        """See `TraceStore.annotate`."""
        self._sdk().spans.log_span_annotations(span_annotations=annotations)

    def publish_prompt(
        self,
        name: str,
        description: str,
        call: dict[str, Any],
        version_description: str,
        provider: str,
    ) -> None:
        """See `TraceStore.publish_prompt`.

        MUSTACHE, so the `{{name}}` in a user template reads as the variable
        it is. Safe for the system half: perturb's `{{asks}}` and follow's
        `{{type}}` are filled in before sending and are variables here too,
        and the single braces in bridge's worked example are not a
        substitution.
        """
        sdk = self._sdk()
        from phoenix.client.types import PromptVersion

        sdk.prompts.create(
            name=name,
            prompt_description=description,
            version=PromptVersion.from_openai(
                call,  # type: ignore[arg-type] - a plain dict of the same keys
                description=version_description,
                template_format="MUSTACHE",
                model_provider=provider,  # type: ignore[arg-type]
            ),
        )

    def projects(self) -> list[Project]:
        """See `TraceStore.projects`."""
        from telemetry import projects

        return projects.held(self._rest())

    def delete_project(self, project_id: str) -> bool:
        """See `TraceStore.delete_project`."""
        answered = self._rest().delete(f"/v1/projects/{project_id}")
        if not answered.ok:
            log.warning("could not delete %s: %s", project_id, answered.status_code)
        return bool(answered.ok)

    def datasets(self) -> list[dict[str, Any]]:
        """See `TraceStore.datasets`."""
        from telemetry import projects

        return list(projects.listed(self._rest(), "/v1/datasets"))

    def delete_dataset(self, dataset_id: str) -> bool:
        """See `TraceStore.delete_dataset`."""
        answered = self._rest().delete(f"/v1/datasets/{dataset_id}")
        if not answered.ok:
            log.warning(
                "could not delete dataset %s: %s", dataset_id, answered.status_code
            )
        return bool(answered.ok)

    def set_retention(self, days: int) -> None:
        """See `TraceStore.set_retention`."""
        from telemetry import projects

        projects.set_retention(self._rest(), days)

    def create_dataset(
        self,
        name: str,
        inputs: list[dict[str, Any]],
        outputs: list[dict[str, Any]],
        description: str,
    ) -> str:
        """See `TraceStore.create_dataset`."""
        return (
            self._sdk()
            .datasets.create_dataset(
                name=name,
                inputs=inputs,
                outputs=outputs,
                dataset_description=description,
            )
            .id
        )

    def run_experiment(
        self,
        dataset: str,
        task: Callable[..., Any],
        evaluators: dict[str, Callable[..., Any]],
        name: str,
        description: str,
        metadata: dict[str, Any],
    ) -> str:
        """See `TraceStore.run_experiment`."""
        sdk = self._sdk()
        held = sdk.datasets.get_dataset(dataset=dataset)
        experiment = sdk.experiments.run_experiment(
            dataset=held,
            task=task,
            evaluators=evaluators,
            experiment_name=name,
            experiment_description=description,
            experiment_metadata=metadata,
        )
        return sdk.experiments.get_experiment_url(
            dataset_id=held.id, experiment_id=_id_of(experiment)
        )


def _id_of(experiment: Any) -> str:
    """The experiment's id, however the client hands it back."""
    if isinstance(experiment, dict):
        return experiment.get("id") or experiment["experiment_id"]
    return getattr(experiment, "id", None) or experiment.experiment_id


class NoTraceStore:
    """A deployment that keeps traces elsewhere: nothing is sent, and nothing is held."""

    _WHY = "TRACE_STORE=none, so there is no trace store to ask"

    def annotate(self, annotations: list[dict[str, Any]]) -> None:
        """Drops them: they are in the database."""

    def publish_prompt(
        self, name, description, call, version_description, provider
    ) -> None:
        """Drops it: it is in the table."""

    def projects(self) -> list[Project]:
        """None."""
        return []

    def delete_project(self, project_id: str) -> bool:
        """Nothing to delete."""
        return False

    def datasets(self) -> list[dict[str, Any]]:
        """None."""
        return []

    def delete_dataset(self, dataset_id: str) -> bool:
        """Nothing to delete."""
        return False

    def set_retention(self, days: int) -> None:
        """Retention is the other store's own setting."""

    def create_dataset(self, name, inputs, outputs, description) -> str:
        """Raises: there is nowhere to upload to."""
        raise TraceStoreUnavailable(self._WHY)

    def run_experiment(
        self, dataset, task, evaluators, name, description, metadata
    ) -> str:
        """Raises: there is nowhere to run it."""
        raise TraceStoreUnavailable(self._WHY)


def trace_store(base_url: str | None = None) -> TraceStore:
    """The adapter TRACE_STORE names, `phoenix` unless told otherwise.

    Raises:
        ValueError: If it names none that exists.
    """
    adapter = os.getenv("TRACE_STORE", "phoenix").strip() or "phoenix"
    if adapter == "phoenix":
        return PhoenixStore(base_url)
    if adapter == "none":
        return NoTraceStore()
    raise ValueError(f"TRACE_STORE={adapter!r} names no adapter: phoenix or none")
