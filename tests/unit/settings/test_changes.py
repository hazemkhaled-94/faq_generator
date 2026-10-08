"""Which settings a change may name."""

from __future__ import annotations

import os

import pytest

from settings import catalog, changes


class Untouched:
    """A store holding no override."""

    def resolved(self) -> dict[str, str]:
        """No stored value."""
        return {}

    def version(self) -> str:
        """The version of an empty store."""
        return "environment"


class Environment(Untouched):
    """A store holding no override, over the test environment."""

    def resolved(self) -> dict[str, str]:
        """The environment, as nothing stored leaves it."""
        return dict(os.environ)


def test_an_assessment_value_its_stage_cannot_read_is_refused() -> None:
    """The phase's own parser is asked, as every other stage's is."""
    with pytest.raises(changes.Refused) as refused:
        changes.apply("assessment", {"ASSESSMENT_SAMPLE": "abc"}, store=Environment())

    assert refused.value.code == "would_not_load"


@pytest.mark.parametrize("name", ["LLM_BASE_URL", "OLLAMA_BASE_URL"])
def test_a_change_naming_where_a_model_is_served_is_refused(name: str) -> None:
    """The address is the deployment's."""
    with pytest.raises(changes.Refused) as refused:
        changes.apply("platform", {name: "http://elsewhere:11434"}, store=Untouched())

    assert refused.value.code == "fixed_setting"


@pytest.mark.parametrize(
    "name",
    [
        "LLM_MODEL",
        "EXTRACTION_MODEL",
        "EXTRACTION_DIGEST_MODEL",
        "TOPIC_MODEL",
        "QUESTIONS_MODEL",
        "QUESTIONS_VERIFIER_MODEL",
        "QUESTIONS_PHRASING_MODEL",
        "ASSESSMENT_JUDGE_MODEL",
    ],
)
def test_a_change_naming_which_model_is_called_is_refused(name: str) -> None:
    """The host reads its models from .env and a container from compose.

    One table serves both, so no value stored there is right for both.
    """
    service = catalog.BY_NAME[name].service
    with pytest.raises(changes.Refused) as refused:
        changes.apply(service, {name: "ollama_chat/other"}, store=Untouched())

    assert refused.value.code == "fixed_setting"


@pytest.mark.parametrize(
    "name",
    [
        "NLP_MODELS",
        "NLP_DEFAULT_LANGUAGE",
        "NLP_CAPITALISED_NOUNS",
        "WORKER_POLL_SECONDS",
    ],
)
def test_a_setting_read_from_the_environment_alone_is_not_written(name: str) -> None:
    """Read where it is used and never through the store, so a row would do nothing."""
    assert catalog.BY_NAME[name].fixed is True


@pytest.mark.parametrize("name", ["EMBEDDING_MODEL", "NLI_MODEL", "QA_MODEL"])
def test_a_local_encoder_may_still_be_changed(name: str) -> None:
    """Run in the worker, the same on the host and in a container."""
    assert changes.owned("platform", [name])[name].fixed is False
