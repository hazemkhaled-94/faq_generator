"""The model split: which model each of the seven roles calls, and the go-live refusal.

A deployment names a model for the writer, the verifier, the phrasing judge,
the passage reader, the digest reader, the topic namer and the assessment
judge, and a role it leaves unnamed follows another. With HOST_RUNNER=1 every
role must be a hosted model, because the host runner is the path that reaches
a hosted provider and no Ollama runs on it.
"""

from __future__ import annotations

import logging

import pytest
from unit.llm.test_client import settings

from llm.check import before_work
from llm.config import ROLES, check_split, describe, host_runner, split

GO_LIVE = {
    "LLM_MODEL": "azure/gpt-5.4",
    "LLM_REASONING_EFFORT": "none",
    "QUESTIONS_MODEL": "azure/gpt-5.6-sol",
    "EXTRACTION_MODEL": "azure/gpt-5.4",
    "QUESTIONS_PHRASING_MODEL": "azure/gpt-5.4",
    "EXTRACTION_DIGEST_MODEL": "azure/gpt-4o",
    "ASSESSMENT_JUDGE_MODEL": "azure/gpt-4o",
    "QUESTIONS_VERIFIER_MODEL": "azure/gpt-4.1",
    "TOPIC_MODEL": "azure/gpt-4.1",
    "ASSESSMENT_ENABLED": "true",
    "HOST_RUNNER": "1",
}


def test_every_role_is_resolved_with_its_fallback() -> None:
    """An unnamed role follows the one the docs say it does."""
    got = split({"LLM_MODEL": "m/shared", "QUESTIONS_VERIFIER_MODEL": "m/checker"})

    assert list(got) == [role for role, _, _ in ROLES]
    assert got["writer"] == "m/shared"
    assert got["extraction"] == "m/shared"
    assert got["digest"] == "m/shared"
    assert got["topics"] == "m/shared"
    assert got["verifier"] == "m/checker"
    assert got["phrasing"] == "m/checker"
    assert got["judge"] is None


def test_the_split_line_names_the_seven_roles_and_the_effort() -> None:
    """One line, so a drain's log says what it called without a second file."""
    line = describe(GO_LIVE)

    assert "\n" not in line
    for role, _, _ in ROLES:
        assert f"{role}=" in line
    assert "writer=azure/gpt-5.6-sol" in line
    assert "effort=none" in line


def test_an_effort_left_unset_is_said_so() -> None:
    """Not a blank, which reads as a line that lost its value."""
    assert "effort=unset" in describe({"LLM_MODEL": "m/x"})


def test_the_go_live_split_passes() -> None:
    """The split .env.example ships."""
    check_split(GO_LIVE)


@pytest.mark.parametrize("role", [role for role, _, _ in ROLES])
def test_an_ollama_role_is_refused_naming_it(role: str) -> None:
    """Whichever role it is, and the setting that moves it."""
    setting = next(name for r, name, _ in ROLES if r == role)
    source = {**GO_LIVE, setting: "ollama_chat/gemma4:31b"}

    with pytest.raises(ValueError, match=role) as raised:
        check_split(source)

    assert setting in str(raised.value)


def test_a_role_that_follows_an_ollama_shared_model_is_refused() -> None:
    """Falling back to LLM_MODEL is still resolving to it."""
    source = {
        "HOST_RUNNER": "1",
        "LLM_MODEL": "ollama/x",
        "ASSESSMENT_ENABLED": "false",
    }

    with pytest.raises(ValueError, match="writer"):
        check_split(source)


def test_a_judge_left_unset_while_assessment_runs_is_refused() -> None:
    """The judge has no fallback, so unset is a role without a model."""
    source = {**GO_LIVE}
    del source["ASSESSMENT_JUDGE_MODEL"]

    with pytest.raises(ValueError, match="judge"):
        check_split(source)


def test_a_judge_left_unset_while_assessment_is_off_is_fine() -> None:
    """Nothing is judged, so no role is missing."""
    source = {**GO_LIVE, "ASSESSMENT_ENABLED": "false"}
    del source["ASSESSMENT_JUDGE_MODEL"]

    check_split(source)


def test_without_the_host_runner_an_ollama_split_is_the_development_path() -> None:
    """Today's behaviour, unchanged."""
    check_split({**GO_LIVE, "HOST_RUNNER": "0", "TOPIC_MODEL": "ollama/x"})
    check_split({"LLM_MODEL": "ollama/x"})


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", True), ("true", True), ("0", False), ("", False), ("no", False)],
)
def test_the_host_runner_is_on_for_the_spellings_of_yes(value, expected) -> None:
    """The same spellings every other flag reads."""
    assert host_runner({"HOST_RUNNER": value}) is expected
    assert host_runner({}) is False


def test_a_drain_starts_by_saying_the_split(monkeypatch, caplog) -> None:
    """Every model stage's preflight is `before_work`."""
    for name, value in GO_LIVE.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("llm.check.reachable", lambda _: None)

    with caplog.at_level(logging.INFO, logger="llm.check"):
        before_work(settings(model="azure/gpt-5.4"))

    said = [
        r.getMessage() for r in caplog.records if r.getMessage().startswith("split:")
    ]
    assert len(said) == 1
    assert "judge=azure/gpt-4o" in said[0]


def test_a_drain_refuses_to_start_on_an_ollama_role(monkeypatch) -> None:
    """Under HOST_RUNNER, before a model is asked or a row claimed."""
    for name, value in {**GO_LIVE, "TOPIC_MODEL": "ollama/x"}.items():
        monkeypatch.setenv(name, value)
    asked: list[object] = []
    monkeypatch.setattr("llm.check.reachable", asked.append)

    with pytest.raises(ValueError, match="topics"):
        before_work(settings(model="azure/gpt-5.4"))

    assert asked == []


def test_a_drain_refuses_a_stored_override_that_resolves_to_ollama(monkeypatch) -> None:
    """The models a stage resolved, which a stored setting may have moved."""
    for name, value in GO_LIVE.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("llm.check.reachable", lambda _: None)

    with pytest.raises(ValueError, match="ollama_chat/local"):
        before_work(settings(model="ollama_chat/local"))


def test_the_doctor_fails_on_an_ollama_role_under_the_host_runner(
    monkeypatch, caplog
) -> None:
    """And says the split, so a person reads what a drain will call."""
    from unit.llm.test_client import provider, reply

    from api.doctor import main

    for name, value in {**GO_LIVE, "TOPIC_MODEL": "ollama/x"}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("telemetry.configure", lambda _: None)
    monkeypatch.setattr("api.doctor.behind_lines", list)
    provider(monkeypatch, reply('{"ok": true}'))

    with caplog.at_level(logging.INFO):
        assert main() == 1

    assert any("topics" in r.getMessage() for r in caplog.records)
    assert any(r.getMessage().startswith("split:") for r in caplog.records)
