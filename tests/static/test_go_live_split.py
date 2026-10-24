"""The go-live split lives in .env.example, and backend.env names none of it.

backend.env is a project default, the same wherever it runs; which model each
role calls is one deployment's choice. A role model left in backend.env is
one the deployment's .env has to know to override, or a run quietly calls the
project's.
"""

from __future__ import annotations

import re
from pathlib import Path

from llm.config import ROLES

ROOT = Path(__file__).resolve().parents[2]
_LIVE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$", re.MULTILINE)


def _live(path: str) -> dict[str, str]:
    """The assignments a file makes, comments excluded."""
    return dict(_LIVE.findall((ROOT / path).read_text()))


def test_backend_env_names_no_role_model() -> None:
    """The three Ollama defaults are gone, so an unnamed role follows LLM_MODEL."""
    live = _live("configs/env/backend.env")

    named = [setting for _, setting, _ in ROLES if setting in live]

    assert not named, f"backend.env sets {named}; they belong in .env"


def test_the_example_names_the_seven_roles_and_the_effort() -> None:
    """The go-live split, whole."""
    live = _live(".env.example")

    for _, setting, _ in ROLES:
        assert live.get(setting, "").startswith("azure/"), setting
    assert live["LLM_REASONING_EFFORT"] == "none"
    assert live["QUESTIONS_MODEL"] == "azure/gpt-5.6-sol"
    assert {live["EXTRACTION_MODEL"], live["QUESTIONS_PHRASING_MODEL"]} == {
        "azure/gpt-5.4"
    }
    assert {live["EXTRACTION_DIGEST_MODEL"], live["ASSESSMENT_JUDGE_MODEL"]} == {
        "azure/gpt-4o"
    }
    assert {live["QUESTIONS_VERIFIER_MODEL"], live["TOPIC_MODEL"]} == {"azure/gpt-4.1"}


def test_the_docs_say_every_role_is_reached_through_one_address() -> None:
    """C-366: a split across Azure resources needs a gateway."""
    text = " ".join((ROOT / "docs/configuration.md").read_text().split())

    assert "every role model is reached through `LLM_BASE_URL`" in text
    assert "gateway" in text
