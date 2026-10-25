"""The passes that call a model outside a drain are traced.

`queue_main` leaves tracing off until a drain is going to claim rows, so a
pass of its own - the bridge pass, the unanswerable re-judge - ran with no
exporter: Phoenix held nothing of it, and its log lines read trace 0. They
configure it themselves, after the preflight that proves the model answers,
in the order a drain does: logged, proved, traced, then worked.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from drivers import DIGEST_SHARE, Catalogue, Model, group

from extraction.extractors.bridge import BridgeExtractor
from extraction.service import bridge
from extraction.validation import FactChecker


@pytest.fixture
def order(monkeypatch) -> list:
    """What `telemetry` is asked to do, in order, wherever it is asked."""
    events: list = []
    import stages.cli as shared

    monkeypatch.setattr(
        shared.telemetry,
        "configure",
        lambda name, **kwargs: events.append(
            ("traced" if kwargs.get("tracing", True) else "logged", name)
        ),
    )
    monkeypatch.setattr(shared.telemetry, "trace_engine", lambda _engine: None)
    monkeypatch.setattr(shared, "engine", lambda: None)
    return events


class _Loaded:
    """Settings that load to the attributes a pass reads."""

    def __init__(self, **attributes) -> None:
        """Holds them."""
        self._attributes = attributes

    def load(self, _source=None):
        """The settings, read from nothing."""
        return SimpleNamespace(
            **{"overridden": lambda model: model, **self._attributes}
        )


def test_the_bridge_pass_logs_proves_traces_then_bridges(monkeypatch, order) -> None:
    """The preflight is before the exporter, so a model that will not answer leaves no project."""
    from extraction import run as module

    monkeypatch.setattr(module, "snapshot", lambda: ({}, "v1"))
    monkeypatch.setattr(module, "ModelSettings", _Loaded())
    monkeypatch.setattr(
        module,
        "Settings",
        _Loaded(model=None, digest_share=0.5, bridges_per_topic=1, bridge_passages=2),
    )
    monkeypatch.setattr(module, "before_work", lambda *_: order.append(("proved",)))
    monkeypatch.setattr(module, "FactCatalog", lambda **_: object())
    monkeypatch.setattr(module, "build_bridge", lambda *_: object())
    monkeypatch.setattr(module, "FactChecker", lambda _share: object())
    monkeypatch.setattr(module, "bridge", lambda *_args: order.append(("worked",)) or 0)

    assert module.main(["--bridge"]) == 0

    assert order == [
        ("logged", "extraction"),
        ("proved",),
        ("traced", "extraction"),
        ("worked",),
    ]


def test_the_rejudge_logs_proves_traces_then_judges(monkeypatch, order) -> None:
    """The same order for the other pass that asks a model outside a drain."""
    from question_generation import run as module

    monkeypatch.setattr(module, "snapshot", lambda: ({}, "v1"))
    monkeypatch.setattr(module, "Settings", _Loaded())
    monkeypatch.setattr(module, "ModelSettings", _Loaded())
    monkeypatch.setattr(module, "models", lambda *_: (None, "verifier", None))
    monkeypatch.setattr(module, "before_work", lambda *_: order.append(("proved",)))
    monkeypatch.setattr(module, "QuestionCatalog", lambda: object())
    monkeypatch.setattr(module, "Verifier", lambda client: client)
    monkeypatch.setattr(module, "Client", lambda model: model)
    monkeypatch.setattr(
        module, "rejudge", lambda *_args: order.append(("worked",)) or 0
    )

    assert module.main(["--rejudge"]) == 0

    assert order == [
        ("logged", "questions"),
        ("proved",),
        ("traced", "questions"),
        ("worked",),
    ]


ANSWER = {
    "relation": "contrast",
    "facts": [{"excerpt": 0, "fact": 0}, {"excerpt": 1, "fact": 0}],
    "statement": "Urgent requests are answered sooner than standard requests.",
    "question": "Which is answered sooner, a standard or an urgent request?",
    "answer": "an urgent request",
}


def _pair(language: str, at: int, texts: tuple[str, str], parent: str):
    """Two sections of one heading, in one language."""
    first, second = group(*texts, language=language)
    return [
        replace(
            first,
            id=first.id + at,
            language=language,
            section_path=f"{parent} > A",
        ),
        replace(
            second,
            id=second.id + at,
            language=language,
            section_path=f"{parent} > B",
        ),
    ]


def test_every_offered_link_is_one_span_and_the_parent_of_its_model_call(
    monkeypatch,
) -> None:
    """One German and one English link: two spans, each over its own call."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from extraction import service as module

    exported = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exported))
    tracer = provider.get_tracer("test")
    monkeypatch.setattr(module, "span", tracer)

    class Traced(Model):
        """A model whose every call opens the span litellm would."""

        def answer(self, **kwargs):
            """Answers inside a span of its own."""
            with tracer.start_as_current_span("completion"):
                return super().answer(**kwargs)

    german = _pair(
        "de",
        0,
        (
            "Standardanfragen werden innerhalb von 48 Stunden beantwortet.",
            "Dringende Anfragen werden innerhalb von 4 Stunden beantwortet.",
        ),
        "Support",
    )
    english = _pair(
        "en",
        100,
        (
            "Parcels leave the warehouse within 2 days.",
            "Pallets leave the depot within 9 days.",
        ),
        "Delivery",
    )
    catalog = Catalogue(support=german, delivery=english)
    catalog.stating()

    model = Traced(ANSWER)
    bridge(
        catalog,  # type: ignore[arg-type]
        BridgeExtractor(model),  # type: ignore[arg-type]
        FactChecker(DIGEST_SHARE),
        5,
        2,
    )

    spans = exported.get_finished_spans()
    links = [one for one in spans if one.name == "bridge_link"]
    calls = [one for one in spans if one.name == "completion"]
    assert model.calls == 2
    assert len(links) == len(calls) == 2
    assert {one.parent.span_id for one in calls if one.parent} == {
        one.context.span_id for one in links
    }
    assert {one.attributes["link.language"] for one in links} == {"de", "en"}
