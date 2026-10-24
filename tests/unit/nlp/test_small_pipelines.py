"""A small pipeline, or one with no word vectors, is named when it is loaded.

A `_sm` model segments sentences, tags and parses differently from the `_md`
and `_lg` ones, and with no word vectors it cannot judge what is alike, so
what a fact is changes with the model picked. The warning names the language.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from nlp import pipelines


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch):
    """NLP_MODELS set by the test, with the caches emptied around it."""

    def given(models: str, meta: dict) -> None:
        monkeypatch.setenv("NLP_MODELS", models)
        monkeypatch.setenv("NLP_DEFAULT_LANGUAGE", models.split(":")[0])
        pipelines._configured.cache_clear()
        pipelines._loaded.cache_clear()
        monkeypatch.setattr(
            pipelines.spacy, "load", lambda model: SimpleNamespace(meta=meta)
        )

    yield given
    pipelines._configured.cache_clear()
    pipelines._loaded.cache_clear()


@pytest.mark.parametrize(
    ("models", "language"),
    [
        ("fr:fr_core_news_sm", "fr"),
        ("de:de_core_news_sm", "de"),
        ("en:en_core_web_sm", "en"),
    ],
)
def test_a_small_pipeline_is_warned_of_naming_its_language(
    configured, caplog, models: str, language: str
) -> None:
    """The model, its language, and what to pick instead."""
    configured(models, {"vectors": {"vectors": 0}})

    with caplog.at_level(logging.WARNING, logger="nlp.pipelines"):
        pipelines.pipeline(language)

    assert f"language {language}" in caplog.text
    assert models.split(":")[1] in caplog.text


def test_a_pipeline_with_no_vectors_is_warned_of_whatever_its_name(
    configured, caplog
) -> None:
    """The name is a hint; the missing vectors are the fact."""
    configured("de:de_dep_news_trf", {"vectors": {"vectors": 0}})

    with caplog.at_level(logging.WARNING, logger="nlp.pipelines"):
        pipelines.pipeline("de")

    assert "language de" in caplog.text


def test_a_medium_pipeline_with_vectors_is_not_warned_of(configured, caplog) -> None:
    """Nothing to say of the pipelines the deployment ships."""
    configured("de:de_core_news_md", {"vectors": {"vectors": 20000}})

    with caplog.at_level(logging.WARNING, logger="nlp.pipelines"):
        pipelines.pipeline("de")

    assert not caplog.text
