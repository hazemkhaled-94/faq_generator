"""Defects this service has had, one test each.

Every test here failed once. The name says the symptom rather than the
mechanism, so a reader who sees one go red knows what a user would see; the
docstring says what went wrong underneath.
"""

from __future__ import annotations

import pytest
from topic_drivers import FitterDriver, corpus

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
        corpus("lieferung versand", "lieferung versand"),
    )

    with pytest.raises(NoVocabulary, match="TOPIC_NO_ABOVE"):
        flat.fit("de")
