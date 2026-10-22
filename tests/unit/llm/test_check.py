"""The one call a worker makes before it claims anything."""

from __future__ import annotations

import pytest
from unit.llm.test_client import provider, reply, settings

from api.doctor import main
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


@pytest.mark.parametrize("judging", ["true", "false"])
def test_the_doctor_asks_every_model_a_stage_calls(monkeypatch, judging) -> None:
    """Each stage's own model is asked, not LLM_MODEL alone.

    backend.env names a digest, a topic and a phrasing model of its own, so a
    deployment that moved LLM_MODEL alone passed `make doctor` and failed at
    its first digest, topic name and phrasing judgement. The judge is asked
    while the evaluation phase is on, as its worker asks it.
    """
    roles = {
        "EXTRACTION_MODEL": "azure/reader",
        "EXTRACTION_DIGEST_MODEL": "azure/digest",
        "TOPIC_MODEL": "azure/namer",
        "QUESTIONS_MODEL": "azure/writer",
        "QUESTIONS_VERIFIER_MODEL": "azure/verifier",
        "QUESTIONS_PHRASING_MODEL": "azure/phrasing",
    }
    judge = {"ASSESSMENT_ENABLED": judging, "ASSESSMENT_JUDGE_MODEL": "azure/judge"}
    for name, value in {"LLM_MODEL": "azure/shared", **roles, **judge}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("telemetry.configure", lambda _: None)
    served = provider(monkeypatch, reply('{"ok": true}'))

    assert main() == 0

    judged = {"azure/judge"} if judging == "true" else set()
    asked = {"azure/shared", *roles.values(), *judged}
    assert sorted(call["model"] for call in served.calls) == sorted(asked)
