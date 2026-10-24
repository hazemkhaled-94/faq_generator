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
    monkeypatch.setattr("api.doctor.behind_lines", list)
    served = provider(monkeypatch, reply('{"ok": true}'))

    assert main() == 0

    judged = {"azure/judge"} if judging == "true" else set()
    asked = {"azure/shared", *roles.values(), *judged}
    assert sorted(call["model"] for call in served.calls) == sorted(asked)


def test_a_stage_that_will_not_load_still_leaves_the_other_models_asked(
    monkeypatch,
) -> None:
    """The evaluation phase on with no judge named fails the doctor, and the rest are asked."""
    monkeypatch.setenv("LLM_MODEL", "azure/shared")
    monkeypatch.setenv("ASSESSMENT_ENABLED", "true")
    monkeypatch.setenv("ASSESSMENT_JUDGE_MODEL", "")
    monkeypatch.setattr("telemetry.configure", lambda _: None)
    monkeypatch.setattr("api.doctor.behind_lines", list)
    served = provider(monkeypatch, reply('{"ok": true}'))

    assert main() == 1
    assert "azure/shared" in {call["model"] for call in served.calls}


def test_a_capped_drain_refuses_a_model_litellm_cannot_price(monkeypatch) -> None:
    """Its calls would add nothing to the tally the cap is read from."""
    monkeypatch.setenv("SPEND_CAP", "5")
    monkeypatch.setattr("llm.check.reachable", lambda _: None)
    monkeypatch.setattr("llm.check.unpriced_models", lambda: frozenset({"azure/mine"}))

    with pytest.raises(Unreachable, match="azure/mine"):
        before_work(settings(model="azure/mine"))


def test_without_a_cap_an_unpriced_model_is_asked_as_before(monkeypatch) -> None:
    """Nothing is counted, so nothing is blind."""
    monkeypatch.delenv("SPEND_CAP", raising=False)
    monkeypatch.setattr("llm.check.reachable", lambda _: None)
    monkeypatch.setattr("llm.check.unpriced_models", lambda: frozenset({"azure/mine"}))

    before_work(settings(model="azure/mine"))


@pytest.mark.parametrize("value", ["0", "-3", "lots"])
def test_a_cap_that_is_not_a_positive_number_is_refused(monkeypatch, value) -> None:
    """A typo must not read as no cap."""
    from llm.config import spend_cap

    monkeypatch.setenv("SPEND_CAP", value)

    with pytest.raises(ValueError, match="SPEND_CAP"):
        spend_cap()


# ── The doctor asks as the stages do: with the stored settings ─────────────


def _stored(monkeypatch, **stored: str) -> None:
    """A settings store holding `stored`, over an environment that holds none of it."""
    import os

    for name in ("LLM_REASONING_EFFORT", "HOST_RUNNER"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_MODEL", "azure/shared")
    monkeypatch.setenv("ASSESSMENT_ENABLED", "false")
    monkeypatch.setenv("ASSESSMENT_JUDGE_MODEL", "azure/judge")
    monkeypatch.setattr(
        "settings.store.snapshot", lambda: ({**os.environ, **stored}, "version")
    )
    monkeypatch.setattr("telemetry.configure", lambda _: None)
    monkeypatch.setattr("api.doctor.behind_lines", list)


def test_the_doctor_asks_with_the_stored_effort_and_judges_what_is_stored_on(
    monkeypatch, caplog
) -> None:
    """A value written through the page is what a worker uses, so what the doctor asks with."""
    import logging

    _stored(monkeypatch, LLM_REASONING_EFFORT="low", ASSESSMENT_ENABLED="true")
    served = provider(monkeypatch, reply('{"ok": true}'))

    with caplog.at_level(logging.INFO):
        assert main() == 0

    assert {call["model"] for call in served.calls} >= {"azure/shared", "azure/judge"}
    assert {call.get("reasoning_effort") for call in served.calls} == {"low"}
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "LLM_REASONING_EFFORT" in said and "ASSESSMENT_ENABLED" in said
    assert "comes from the store" in said


def test_without_a_store_to_read_the_doctor_says_so_and_asks_with_the_environment(
    monkeypatch, caplog
) -> None:
    """A database that is down does not stop the model check."""
    import logging

    _stored(monkeypatch)

    def down():
        raise RuntimeError("no database")

    monkeypatch.setattr("settings.store.snapshot", down)
    served = provider(monkeypatch, reply('{"ok": true}'))

    with caplog.at_level(logging.INFO):
        assert main() == 0

    assert {call["model"] for call in served.calls} == {"azure/shared"}
    assert any(
        "could not read the stored settings" in r.getMessage() for r in caplog.records
    )


def test_the_doctor_fails_on_a_stored_row_the_catalogue_now_refuses(
    monkeypatch, caplog
) -> None:
    """The same refusal a worker's build gives, found before a corpus runs."""
    import logging

    from settings.store import StoredRefused

    _stored(monkeypatch)

    def refused():
        raise StoredRefused("TOPIC_MIN_WEIGHT='-1' (written 2026-09-01 10:30) is below 0")

    monkeypatch.setattr("settings.store.snapshot", refused)
    provider(monkeypatch, reply('{"ok": true}'))

    with caplog.at_level(logging.INFO):
        assert main() == 1

    assert any("TOPIC_MIN_WEIGHT" in r.getMessage() for r in caplog.records)
