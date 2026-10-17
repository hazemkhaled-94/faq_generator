"""The one call a worker makes before it claims anything."""

from __future__ import annotations

import pytest
from unit.llm.test_client import provider, reply, settings

from llm.check import Unreachable, before_work, reachable


def test_the_preflight_asks_once_and_names_the_model(monkeypatch) -> None:
    """One attempt is one call, so a deployment that cannot work is told fast."""
    served = provider(monkeypatch, reply("not json"))

    with pytest.raises(Unreachable, match="azure/gpt-4.1"):
        reachable(settings(model="azure/gpt-4.1", max_attempts=3))

    assert len(served.calls) == 1


def test_a_model_named_twice_is_asked_once(monkeypatch) -> None:
    """A writer and a verifier on one model are one question."""
    served = provider(monkeypatch, reply('{"ok": true}'))
    model = settings(model="azure/gpt-4.1")

    before_work(model, model)

    assert len(served.calls) == 1
