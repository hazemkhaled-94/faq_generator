"""What every trace store adapter does, run against each one there is.

`PhoenixStore` is today's, over stand-ins for Phoenix's REST API and its
client. The fake is the in-memory port, and `none` is the deployment that
keeps traces elsewhere, so it only has to accept what it is sent and refuse
what it cannot do. An Azure Monitor adapter would be `none` plus OTLP.
"""

from __future__ import annotations

import pytest
from fakes import FakePhoenixHttp, FakePhoenixSdk, FakeTraceStore

from telemetry import evaluations
from telemetry.evaluations import NoTraceStore, PhoenixStore, TraceStoreUnavailable


class PhoenixRig:
    """Phoenix, with the stand-ins visible."""

    def __init__(self) -> None:
        """Builds the adapter over both."""
        self.http, self.sdk = FakePhoenixHttp(), FakePhoenixSdk()
        self.store = PhoenixStore(
            "http://phoenix.invalid", sdk=self.sdk, session=self.http
        )

    @property
    def annotated(self) -> list:
        """What reached the client."""
        return self.sdk.annotated

    @property
    def prompt_names(self) -> list[str]:
        """The prompts sent."""
        return [call["name"] for call in self.sdk.prompt_calls]

    @property
    def retention(self):
        """What the policy was set to."""
        return self.http.retention


class FakeRig:
    """The fake, with its state visible."""

    def __init__(self) -> None:
        """Builds it."""
        self.store = FakeTraceStore()

    @property
    def annotated(self) -> list:
        """What was filed."""
        return self.store.annotated

    @property
    def prompt_names(self) -> list[str]:
        """The prompts sent."""
        return list(self.store.prompts)

    @property
    def retention(self):
        """What it was set to."""
        return self.store.retention


@pytest.fixture(params=[PhoenixRig, FakeRig], ids=["phoenix", "fake"])
def rig(request):
    """Each adapter that holds things, in turn."""
    return request.param()


def test_an_annotation_is_filed_once_for_each_span(rig) -> None:
    """A label, a score and an explanation, in whatever language the gate wrote."""
    rig.store.annotate(
        [{"span_id": "a", "name": "gate", "result": {"label": "Zu lang"}}]
    )
    rig.store.annotate(
        [{"span_id": "b", "name": "gate", "result": {"label": "Πολύ μακρύ"}}]
    )

    assert [one["span_id"] for one in rig.annotated] == ["a", "b"]


def test_a_prompt_is_published_under_its_name_with_its_provider(rig) -> None:
    """The version carries the call and what Phoenix has no field for."""
    call = {
        "model": "gpt-4.1",
        "messages": [{"role": "system", "content": "Antworte kurz."}],
    }

    rig.store.publish_prompt(
        "extraction-atomic", "d", call, "PROMPT_VERSION 8", "OPENAI"
    )

    assert rig.prompt_names == ["extraction-atomic"]


def test_projects_are_listed_with_whether_work_happened_in_each(rig) -> None:
    """A project of nothing but model calls is spent; one with a stage span is not."""
    found = {one.name: one for one in rig.store.projects()}

    assert found["1-extraction-a"].spent is True
    assert found["2-parsing-b"].spent is False


def test_deleting_a_project_says_whether_it_went(rig) -> None:
    """The second delete finds nothing."""
    first = rig.store.delete_project("p1")
    second = rig.store.delete_project("p1")

    assert (first, second) == (True, False)
    assert [one.id for one in rig.store.projects()] == ["p2"]


def test_datasets_are_listed_and_deleted(rig) -> None:
    """With the id the delete takes."""
    assert {one["id"] for one in rig.store.datasets()} == {"d1", "d2"}

    assert rig.store.delete_dataset("d1") is True
    assert rig.store.delete_dataset("d1") is False
    assert [one["id"] for one in rig.store.datasets()] == ["d2"]


def test_retention_is_set_in_days(rig) -> None:
    """What `make up` asks of it."""
    rig.store.set_retention(30)

    assert rig.retention == 30


def test_a_golden_set_is_uploaded_and_an_experiment_reads_it_back(rig) -> None:
    """The cases go in as inputs and expectations, the task sees only the inputs."""
    seen = []
    rig.store.create_dataset(
        "golden",
        [{"text": "Überweisung"}, {"text": "Virement"}],
        [{"claims": 1}, {"claims": 2}],
        "d",
    )

    url = rig.store.run_experiment("golden", seen.append, {}, "run-1", "d", {})

    assert seen == [{"text": "Überweisung"}, {"text": "Virement"}]
    assert "run-1" in url


def test_phoenix_refuses_a_retention_it_would_not_take() -> None:
    """GraphQL answers 200 with the error in the body: that is a refusal."""
    rig = PhoenixRig()
    rig.http.refuse_retention = True

    with pytest.raises(RuntimeError, match="not allowed"):
        rig.store.set_retention(30)


def test_none_accepts_what_it_is_sent_and_refuses_what_it_cannot_do() -> None:
    """Annotations and prompts are in the database anyway; an experiment has nowhere to run."""
    none = NoTraceStore()

    none.annotate([{"span_id": "a"}])
    none.publish_prompt("n", "d", {}, "v", "OPENAI")
    none.set_retention(30)

    assert none.projects() == [] and none.datasets() == []
    assert none.delete_project("p1") is False
    with pytest.raises(TraceStoreUnavailable):
        none.create_dataset("g", [], [], "d")
    with pytest.raises(TraceStoreUnavailable):
        none.run_experiment("g", print, {}, "n", "d", {})


def test_trace_store_names_the_adapter(monkeypatch) -> None:
    """`phoenix` is the default; an unknown name is refused."""
    monkeypatch.delenv("TRACE_STORE", raising=False)
    assert isinstance(evaluations.trace_store(), PhoenixStore)

    monkeypatch.setenv("TRACE_STORE", "none")
    assert isinstance(evaluations.trace_store(), NoTraceStore)

    monkeypatch.setenv("TRACE_STORE", "elsewhere")
    with pytest.raises(ValueError, match="TRACE_STORE"):
        evaluations.trace_store()


def test_with_none_a_verdict_is_not_posted_and_no_address_is_warned_about(
    monkeypatch, caplog
) -> None:
    """The verdict is in Postgres; a collector that wants no annotations is not an unset address."""
    monkeypatch.setenv("TRACE_STORE", "none")
    monkeypatch.delenv("PHOENIX_BASE_URL", raising=False)

    held = evaluations.Evaluations()

    assert not held.enabled
    assert "unset" not in caplog.text
