"""A Phoenix that refuses prompts never fails the stage that sends them.

One bad prompt does not stop the rest; a Phoenix that refuses all of them is
reported once in full and then counted; a process with no trace client says
so and publishes nothing. Each returns how many went, never raises.
"""

from __future__ import annotations

import logging

import pytest

from llm.config import Settings as ModelSettings
from stages.prompts import Composed
from stages.publish import publish
from telemetry.evaluations import TraceStoreUnavailable


def settings() -> ModelSettings:
    """A hosted model's settings."""
    return ModelSettings(
        model="azure/gpt-4.1",
        base_url=None,
        ollama_base_url=None,
        temperature=0.2,
        timeout_seconds=900.0,
        max_attempts=3,
        num_ctx=None,
        reasoning_effort=None,
        structured_mode="json_schema",
    )


PROMPTS = [
    Composed("factoid", "3", "ROLE\nA writer for a bank's help pages.", "{{facts}}"),
    Composed("procedural", "3", "ROLE\nA writer for a shop's help pages.", ""),
    Composed("definition", "3", "ROLE\nA writer for a public office.", "{{facts}}"),
]


class Store:
    """A trace store that refuses the prompts named, and keeps the rest."""

    def __init__(self, refuses: set[str], error: Exception) -> None:
        self.refuses, self.error = refuses, error
        self.published: list[str] = []

    def publish_prompt(self, name, description, call, note, provider) -> None:
        """Refuses the prompts named, keeps the rest."""
        if any(name.endswith(one) for one in self.refuses):
            raise self.error
        self.published.append(name)


@pytest.fixture
def store(monkeypatch):
    """Installs a trace store refusing the prompts named."""
    monkeypatch.setenv("PHOENIX_BASE_URL", "http://phoenix.invalid:6006")

    def install(refuses: set[str], error: Exception | None = None):
        held = Store(refuses, error or ConnectionError("refused"))
        monkeypatch.setattr("stages.publish.trace_store", lambda base_url=None: held)
        return held

    return install


def test_one_refused_prompt_does_not_stop_the_rest(store, caplog) -> None:
    """Two go, the refusal is named and counted."""
    held = store({"procedural"})

    with caplog.at_level(logging.WARNING):
        assert publish("questions", PROMPTS, settings()) == 2

    assert sorted(held.published) == ["questions-definition", "questions-factoid"]
    assert "'procedural'" in caplog.text
    assert "1 of questions's 3 prompt(s) did not reach Phoenix" in caplog.text


def test_a_phoenix_refusing_everything_is_named_once_then_counted(
    store, caplog
) -> None:
    """One full sentence, not one per prompt, and nothing raised."""
    store({"factoid", "procedural", "definition"}, ConnectionError("Phoenix is down"))

    with caplog.at_level(logging.WARNING):
        assert publish("questions", PROMPTS, settings()) == 0

    assert caplog.text.count("Phoenix is down") == 1
    assert "3 of questions's 3 prompt(s) did not reach Phoenix" in caplog.text


def test_no_trace_client_publishes_nothing_and_says_how_to_send_them(
    store, caplog
) -> None:
    """The prompts stay in the table; the stage carries on."""
    held = store({"factoid", "procedural", "definition"}, TraceStoreUnavailable())

    with caplog.at_level(logging.INFO):
        assert publish("questions", PROMPTS, settings()) == 0

    assert held.published == []
    assert "make prompts-publish" in caplog.text


def test_nothing_to_publish_never_opens_the_trace_store(monkeypatch) -> None:
    """An empty batch is no call to Phoenix at all."""
    monkeypatch.setenv("PHOENIX_BASE_URL", "http://phoenix.invalid:6006")

    def opened(base_url=None):
        raise AssertionError("the trace store was opened for nothing")

    monkeypatch.setattr("stages.publish.trace_store", opened)

    assert publish("questions", [], settings()) == 0
