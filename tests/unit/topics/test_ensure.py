"""Whether the corpus run must fit the topics before it writes a bridge or a question.

`make corpus` fits when a language holds passages and no topics, or its topics
no longer fit its passages, and fails when a language still has no topic
afterwards. Languages are the corpus's own: nothing here names one.
"""

from __future__ import annotations

import pytest

from topic_modelling.models import LanguageFit, TopicFit
from topic_modelling.run import fit_needed, unfitted


def fit(*languages: LanguageFit) -> TopicFit:
    """A model with these languages fitted."""
    return TopicFit(
        status="modelled",
        error=None,
        requested_at=None,
        topics=sum(one.topics for one in languages),
        languages=list(languages),
    )


def lang(
    code: str, *, topics: int = 3, live: int = 10, corpus: int = 10, held: int = 9
):
    """One language's fit."""
    return LanguageFit(
        language=code,
        topics=topics,
        corpus_passages=corpus,
        corpus_vocabulary=50,
        passages_without_topics=1,
        fitted_at="2026-10-24T00:00:00",
        live_passages=live,
        memberships=held,
    )


@pytest.mark.parametrize("codes", [["de", "en"], ["fr"], ["xx", "de"]])
def test_every_language_holding_topics_that_fit_needs_nothing(codes) -> None:
    """Whatever the languages are called."""
    assert fit_needed(fit(*(lang(c) for c in codes)), codes) is None


@pytest.mark.parametrize("missing", ["en", "de", "xx"])
def test_a_language_with_passages_and_no_fit_needs_one(missing: str) -> None:
    """Named, so the log says which."""
    others = [c for c in ("de", "en", "xx") if c != missing]

    reason = fit_needed(fit(*(lang(c) for c in others)), [*others, missing])

    assert reason is not None and missing in reason


def test_no_fit_at_all_needs_one() -> None:
    """A fresh database."""
    assert fit_needed(fit(), ["de", "en"]) is not None


def test_a_language_whose_topics_no_longer_fit_its_passages_needs_a_fit() -> None:
    """Passages arrived after the fit."""
    stale = lang("de", live=14, corpus=10)

    reason = fit_needed(fit(stale, lang("en")), ["de", "en"])

    assert reason is not None and "de" in reason


def test_a_language_a_fit_gave_no_topics_still_counts_as_unfitted() -> None:
    """Zero topics is not a fit."""
    assert unfitted(fit(lang("de", topics=0), lang("en")), ["de", "en"]) == ["de"]


def test_unfitted_lists_the_languages_with_passages_and_no_topic() -> None:
    """What the run fails on when the fit has finished."""
    assert unfitted(fit(lang("de")), ["de", "en", "xx"]) == ["en", "xx"]
    assert unfitted(fit(lang("de")), ["de"]) == []
