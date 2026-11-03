"""What every orchestrator adapter does, run against each one there is.

The adapters are `Dagster` over a stand-in webserver that keeps state, an
in-memory fake, and `none`, the deployment that has no orchestrator. The
queries themselves are validated against Dagster's own GraphQL schema,
in-process, so a renamed field fails here and not on the first real request.
"""

from __future__ import annotations

import pytest
from fakes import FakeDagsterSession, FakeOrchestrator

from api import orchestrator as module
from api.orchestrator import Dagster, NoOrchestrator, Unavailable

ADAPTERS = {
    "dagster": lambda: Dagster("http://dagster:3000", session=FakeDagsterSession()),
    "fake": FakeOrchestrator,
}


@pytest.fixture(params=ADAPTERS)
def orchestrator(request):
    """Each adapter that has one, in turn."""
    return ADAPTERS[request.param]()


def test_an_idle_orchestrator_is_available_and_runs_nothing(orchestrator) -> None:
    """Never raises, and says there is nothing running."""
    state = orchestrator.state()

    assert state.available is True
    assert state.running is None
    assert orchestrator.live() == []


def test_a_launched_run_is_live_and_is_what_state_reports(orchestrator) -> None:
    """Launch, then read it back three ways."""
    run = orchestrator.launch()

    assert run.live
    assert [r.id for r in orchestrator.live()] == [run.id]
    assert orchestrator.state().running.id == run.id


def test_runs_come_newest_first_and_honour_the_limit(orchestrator) -> None:
    """The history a page lists."""
    first, second = orchestrator.launch(), orchestrator.launch()

    assert [r.id for r in orchestrator.runs(limit=5)] == [second.id, first.id]
    assert [r.id for r in orchestrator.runs(limit=1)] == [second.id]


def test_terminating_a_live_run_is_true_and_a_second_stop_is_false(
    orchestrator,
) -> None:
    """A second press of Stop is not a failure."""
    run = orchestrator.launch()

    assert orchestrator.terminate(run.id) is True
    assert orchestrator.terminate(run.id) is False
    assert orchestrator.live() == []


def test_a_trigger_given_is_switched_and_one_left_out_is_left_alone(
    orchestrator,
) -> None:
    """None means leave it."""
    on = orchestrator.automate(on_arrival=True, nightly=None)
    both = orchestrator.automate(on_arrival=None, nightly=True)
    off = orchestrator.automate(on_arrival=False, nightly=None)

    assert (on.on_arrival, on.nightly) == (True, False)
    assert (both.on_arrival, both.nightly) == (True, True)
    assert (off.on_arrival, off.nightly) == (False, True)


def test_none_is_unavailable_and_says_why() -> None:
    """A deployment without an orchestrator still answers `state`."""
    none = NoOrchestrator()

    assert none.state().available is False
    assert "ORCHESTRATOR=none" in (none.state().detail or "")
    for verb in (none.live, none.launch, lambda: none.runs(limit=1)):
        with pytest.raises(Unavailable):
            verb()
    with pytest.raises(Unavailable):
        none.terminate("run-0")
    with pytest.raises(Unavailable):
        none.automate(on_arrival=True, nightly=None)


def test_orchestrator_names_the_adapter(monkeypatch) -> None:
    """`dagster` is the default; an unknown name is refused."""
    monkeypatch.delenv("ORCHESTRATOR", raising=False)
    assert isinstance(module.build(), Dagster)

    monkeypatch.setenv("ORCHESTRATOR", "none")
    assert isinstance(module.build(), NoOrchestrator)

    monkeypatch.setenv("ORCHESTRATOR", "kubernetes")
    with pytest.raises(ValueError, match="ORCHESTRATOR"):
        module.build()


# ── The documents against Dagster's schema ─────────────────────────────────


@pytest.fixture(scope="module")
def schema():
    """Dagster's GraphQL schema, built in this process: no server."""
    from dagster_graphql.schema import create_schema

    return create_schema().graphql_schema


def documents() -> dict[str, str]:
    """Every document the adapter can send."""
    held = {
        name: text
        for name, text in vars(module).items()
        if name in ("_STATE", "_RUNS", "_TRIGGERS", "_LAUNCH", "_RUN", "_TERMINATE")
    }
    for group in ("_START", "_STOP"):
        held.update({f"{group}[{k}]": v for k, v in getattr(module, group).items()})
    return held


def errors(schema, document: str) -> list[str]:
    """What the schema says is wrong with a document."""
    from graphql import parse, validate

    return [str(e) for e in validate(schema, parse(document))]


def test_every_document_is_accepted_by_dagsters_schema(schema) -> None:
    """The 1.13 queries, against 1.13's own types."""
    held = documents()
    assert len(held) == 10, sorted(held)

    wrong = {name: errors(schema, text) for name, text in held.items()}

    assert {name: bad for name, bad in wrong.items() if bad} == {}


def test_a_renamed_field_fails_the_validation(schema) -> None:
    """The check has teeth: one field misspelt in one query is caught."""
    broken = module._RUNS.replace("startTime", "startedAt")

    assert errors(schema, broken)
    assert errors(schema, module._TERMINATE.replace("terminatePolicy", "policy"))
