"""Which settings a change may name."""

from __future__ import annotations

import os
from contextlib import suppress
from typing import get_args

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


@pytest.mark.parametrize("value", ["0", "1"])
def test_a_membership_floor_the_fit_would_refuse_is_refused_when_set(
    value: str,
) -> None:
    """The fit keeps a membership only above a floor between 0 and 1."""
    with pytest.raises(changes.Refused) as refused:
        changes.within_bounds(catalog.writable("TOPIC_MIN_WEIGHT"), value)

    assert refused.value.code == "out_of_range"
    assert "TOPIC_MIN_WEIGHT" in refused.value.detail


def test_a_threshold_that_is_not_a_number_is_refused() -> None:
    """A nan passes every bound, since each comparison with it is false."""
    with pytest.raises(changes.Refused) as refused:
        changes.apply("parsing", {"PARSING_MIN_CONFIDENCE": "nan"}, store=Environment())

    assert refused.value.code == "would_not_load"
    assert "PARSING_MIN_CONFIDENCE" in refused.value.detail


def test_a_flag_spelled_wrong_is_refused() -> None:
    """Read, it is off; written, it is a typo that switched something off."""
    with pytest.raises(changes.Refused) as refused:
        changes.within_bounds(catalog.writable("CHUNKING_MERGE_PEERS"), "ture")

    assert refused.value.code == "not_a_choice"
    assert "CHUNKING_MERGE_PEERS" in refused.value.detail


@pytest.mark.parametrize("value", ["TRUE", " off ", "1", "no"])
def test_a_flag_spelled_either_way_is_accepted(value: str) -> None:
    """Case and surrounding whitespace do not matter, as when it is read."""
    changes.within_bounds(catalog.writable("CHUNKING_MERGE_PEERS"), value)


def test_a_choice_is_read_as_the_store_will_write_it() -> None:
    """The value is stored stripped, so it is checked stripped.

    Checked as sent, the route refused what the command line, which strips
    first, wrote.
    """
    changes.within_bounds(catalog.writable("PARSING_TABLE_MODE"), "fast ")


def test_one_topic_is_refused() -> None:
    """The fitter refuses fewer than two, so the topic worker could not build."""
    with pytest.raises(changes.Refused) as refused:
        changes.within_bounds(catalog.writable("TOPIC_NUM_TOPICS"), "1")

    assert refused.value.code == "out_of_range"


@pytest.mark.parametrize(
    ("value", "said"), [("-1", "below 0"), ("4294967296", "above 4294967295")]
)
def test_a_seed_outside_the_fitters_range_is_refused(value: str, said: str) -> None:
    """The factorisation takes a seed from 0 to 2**32 - 1, named in full."""
    with pytest.raises(changes.Refused) as refused:
        changes.within_bounds(catalog.writable("TOPIC_RANDOM_STATE"), value)

    assert refused.value.code == "out_of_range"
    assert said in refused.value.detail


def test_a_bound_is_accepted_where_the_setting_allows_it() -> None:
    """Only a setting marked exclusive refuses its bounds themselves."""
    changes.within_bounds(catalog.writable("TOPIC_NO_ABOVE"), "1")


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


class Recording(Environment):
    """A store over the test environment that keeps what it is asked to write."""

    def __init__(self) -> None:
        """Holds nothing yet."""
        self.written: dict[str, str] = {}

    def change(self, writes, clears, expected=None) -> list[str]:
        """Keeps the writes; clears nothing."""
        self.written.update(writes)
        return []


@pytest.mark.parametrize(
    ("service", "name", "value"),
    [
        ("topics", "TOPIC_LANGUAGE_NAMES", "de:Ger\x00man,en:English"),
        ("parsing", "DOCLING_ARTIFACTS_PATH", "/models/doc\x00ling"),
        ("topics", "TOPIC_LANGUAGE_NAMES", "de:Ger\ud800man,en:English"),
        ("parsing", "DOCLING_ARTIFACTS_PATH", "/models/doc\udc80ling"),
    ],
)
def test_a_value_text_cannot_hold_is_refused_before_it_is_stored(
    service: str, name: str, value: str
) -> None:
    """A NUL PostgreSQL cannot store, or a lone surrogate psycopg cannot encode.

    A JSON escape carries either, and the write would fail as a 500.
    """
    store = Recording()

    with pytest.raises(changes.Refused) as refused:
        changes.apply(service, {name: value}, store=store)

    assert refused.value.code == "out_of_range"
    assert name in refused.value.detail
    assert store.written == {}


@pytest.mark.parametrize("value", ["1", "5", "6"])
def test_an_embedding_window_no_passage_fits_in_is_refused(value: str) -> None:
    """The chunker cuts to the window less the tokens the embedder adds.

    Five of those for multilingual-e5-large, so 5 leaves no budget and every
    document fails chunking, and 6 cuts "Eine Überweisung ins Ausland kostet
    5,00 EUR." into sub-word passages, each a paid extraction call later.
    """
    store = Recording()

    with pytest.raises(changes.Refused) as refused:
        changes.apply("platform", {"EMBEDDING_MAX_TOKENS": value}, store=store)

    assert refused.value.code == "out_of_range"
    assert store.written == {}


def test_a_structured_mode_instructor_does_not_have_is_refused() -> None:
    """Otherwise every model worker fails its rebuild on every poll."""
    with pytest.raises(changes.Refused) as refused:
        changes.apply(
            "platform", {"LLM_STRUCTURED_MODE": "JSONSCHEMA"}, store=Recording()
        )

    assert refused.value.code == "not_a_choice"


def test_a_mode_litellm_cannot_take_is_refused() -> None:
    """An instructor mode is not enough: litellm's client takes eight."""
    with pytest.raises(changes.Refused) as refused:
        changes.apply(
            "platform", {"LLM_STRUCTURED_MODE": "ANTHROPIC_TOOLS"}, store=Recording()
        )

    assert refused.value.code == "not_a_choice"


def test_an_empty_reasoning_effort_is_stored_as_the_absence_it_means(
    monkeypatch,
) -> None:
    """Empty names no choice, so it is not checked against the choices."""
    monkeypatch.setenv("LLM_REASONING_EFFORT", "off")
    store = Recording()

    moved = changes.apply("platform", {"LLM_REASONING_EFFORT": ""}, store=store)

    assert moved.changed == ["LLM_REASONING_EFFORT"]
    assert store.written == {"LLM_REASONING_EFFORT": ""}


def test_a_change_with_a_cheaper_rebuild_names_it_instead_of_a_rerun() -> None:
    """A new release size is a redraw, not a run of the whole stage."""
    moved = changes.apply(
        "questions", {"QUESTIONS_RELEASE_SIZE": "50"}, store=Recording()
    )

    assert "make questions-balance" in moved.detail, moved.detail
    assert "rerun" not in moved.detail, moved.detail


def test_every_service_a_page_configures_is_parsed_before_a_write() -> None:
    """A service missing here takes any value, and its worker then fails on it."""
    assert set(changes.PARSERS) == set(get_args(catalog.Service))


class _Watched(dict):
    """A source that records which names were read from it."""

    def __init__(self, values: dict[str, str]) -> None:
        """Holds the values; nothing read yet."""
        super().__init__(values)
        self.read: set[str] = set()

    def get(self, name, default=None):
        """Records the name, then reads it."""
        self.read.add(name)
        return super().get(name, default)


def test_every_writable_setting_is_read_from_the_source_its_parser_is_given() -> None:
    """A stored row reaches a stage only through that source.

    A setting read off the environment instead is one the page can change
    and nothing applies.
    """
    source = _Watched({**os.environ, "LLM_MODEL": "ollama_chat/test"})
    for load in changes.PARSERS.values():
        with suppress(KeyError, ValueError):
            load(source)

    unread = [
        one.name
        for one in catalog.SETTINGS
        if not one.fixed and one.name not in source.read
    ]
    assert not unread, unread
