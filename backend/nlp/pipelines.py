"""Loading the spaCy pipeline for a language."""

from __future__ import annotations

import logging
from functools import lru_cache

import spacy
from spacy.language import Language

from settings import csv, required

log = logging.getLogger(__name__)


def _models() -> dict[str, str]:
    """Reads NLP_MODELS, a comma-separated list of `language:model`."""
    models = {}
    for pair in csv("NLP_MODELS"):
        language, _, model = pair.partition(":")
        if not model:
            raise ValueError(f"NLP_MODELS entry {pair!r} is not language:model")
        models[language.strip().lower()] = model.strip()
    return models


@lru_cache(maxsize=1)
def _configured() -> tuple[dict[str, str], str]:
    """Returns the configured models and the fallback language."""
    models = _models()
    default = required("NLP_DEFAULT_LANGUAGE").lower()
    if default not in models:
        raise ValueError(
            f"NLP_DEFAULT_LANGUAGE={default!r} is not one of the languages "
            f"NLP_MODELS names ({', '.join(sorted(models))})"
        )
    return models, default


@lru_cache(maxsize=8)
def _loaded(model: str) -> Language:
    """Loads one pipeline, once per process."""
    try:
        loaded = spacy.load(model)
        _warn_if_small(model, loaded)
        return loaded
    except OSError as exc:
        raise RuntimeError(
            f"the spaCy model {model!r} is not installed. It is named in "
            f"NLP_MODELS and must be present in the image; nothing downloads "
            f"it at run time."
        ) from exc


def _warn_if_small(model: str, loaded: Language) -> None:
    """Warns, naming the language, of a pipeline that is small or has no vectors.

    A small pipeline segments, tags and parses differently from the medium
    and large ones, and with no word vectors it cannot tell what is alike, so
    what a fact is changes with the pipeline picked.
    """
    vectors = loaded.meta.get("vectors", {}).get("vectors", 0)
    reasons = [
        *(["is a small (_sm) pipeline"] if model.endswith("_sm") else []),
        *([] if vectors else ["has no word vectors"]),
    ]
    if reasons:
        named = sorted(
            language for language, one in _configured()[0].items() if one == model
        )
        log.warning(
            "language %s is read with %s, which %s: sentences, tags and facts "
            "differ from the medium and large pipelines. Name an _md or _lg "
            "pipeline for it in NLP_MODELS (see the nlp README).",
            ", ".join(named) or "?",
            model,
            " and ".join(reasons),
        )


def languages() -> tuple[str, ...]:
    """Every language this deployment has a pipeline for."""
    models, _ = _configured()
    return tuple(sorted(models))


def pipeline(language: str | None) -> Language:
    """Returns the pipeline for a language, falling back to the default."""
    return _loaded(name(language))


def name(language: str | None) -> str:
    """Returns the model identifier used for a language."""
    models, default = _configured()
    return models.get((language or "").strip().lower(), models[default])


def version(language: str | None) -> str:
    """Returns the version of the pipeline used for a language.

    Recorded on every fact beside its name: the pipeline decides the
    verdicts, so two versions of one are two datasets.
    """
    return pipeline(language).meta["version"]
