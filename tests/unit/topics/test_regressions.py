"""Defects this service has had, one test each.

Every test here failed once. The name says the symptom rather than the
mechanism, so a reader who sees one go red knows what a user would see; the
docstring says what went wrong underneath.
"""

from __future__ import annotations

import pytest
from synth_topics import DEFAULTS
from synth_topics import corpus as synthetic
from topic_drivers import FitterDriver, ServiceDriver, corpus

from topic_modelling.topics import NoVocabulary


def test_a_corpus_tfidf_weighs_flat_is_refused_rather_than_fitted(settings) -> None:
    """A model of NaN is refused instead of being stored as topics.

    A term in every passage has an idf of zero. With TOPIC_NO_ABOVE at 1 the
    filter keeps such terms, and a corpus where every surviving term is one
    weighed to an all-zero matrix: the factorisation divided by its norm,
    every topic came out NaN, and the fit reported success with two
    identically signed topics, no memberships and a NaN figure.
    """
    flat = FitterDriver(
        settings | {"no_below": 1, "no_above": 1.0},
        corpus("lieferung lieferung versand", "lieferung versand versand"),
    )

    with pytest.raises(NoVocabulary, match="TOPIC_NO_ABOVE"):
        flat.fit("de")


@pytest.mark.parametrize(
    ("domain", "small"),
    [("bank", "de"), ("bank", "en"), ("shop", "de"), ("shop", "en")],
)
def test_a_language_of_a_few_passages_still_gets_topics(domain, small) -> None:
    """Five passages beside four hundred of another language got no topics.

    TOPIC_NO_BELOW is a count and TOPIC_NO_ABOVE a share, so under 6 passages
    no term could be in at least 3 and at most half of them: the frequency
    filter left nothing, the language was skipped and its facts were never
    asked about.
    """
    big = "en" if small == "de" else "de"
    driver = ServiceDriver(
        settings=DEFAULTS,
        corpora={
            big: synthetic(domain, big, 400, seed=2),
            small: synthetic(domain, small, 5, seed=3, first_id=1001),
        },
    )

    driver.request_and_run()

    assert driver.failure is None
    assert len(driver.topics_of(small)) > 0


def test_a_language_the_fit_could_not_model_fails_the_request_it_still_stored() -> None:
    """Passages with no lemma cannot be modelled, and that is said, not logged.

    The other language's topics are stored all the same, and the request is
    kept failed with the reason, which is what the stage and the API show.
    """
    driver = ServiceDriver(
        settings=DEFAULTS,
        corpora={
            "en": synthetic("bank", "en", 400, seed=2),
            "de": corpus("", "", first_id=1001),
        },
    )

    driver.request_and_run()

    assert driver.languages_stored == ["en"]
    assert driver.failure is not None
    assert "de" in driver.failure
    assert driver.queue.kept == [1]
