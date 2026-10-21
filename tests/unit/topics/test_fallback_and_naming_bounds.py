"""The edges of the one-topic fallback and of the shared-ending strip.

Each test pins one boundary a targeted mutation run found no test held: the
fallback's size gate on the tf-idf branch and at 2 x TOPIC_PASSAGES_PER_TOPIC,
what counts as a distinct passage, and the strip's three-name floor, its
majority, the name the affix is all of, and the four-letter term match.
"""

from __future__ import annotations

from itertools import product

import pytest
from synth_topics import DEFAULTS
from topic_drivers import FitterDriver, LabellerDriver, corpus

from topic_modelling.labels import _unshared
from topic_modelling.models import FittedTopic, PassageVocabulary
from topic_modelling.topics import NoVocabulary


def _counts(first: str, second: str, distinct: int) -> list[PassageVocabulary]:
    """`distinct` passages of the same two words, each in its own counts."""
    pairs = list(product(range(1, 21), repeat=2))[:distinct]
    return [
        PassageVocabulary(index + 1, [first] * a + [second] * b)
        for index, (a, b) in enumerate(pairs)
    ]


# ── The one-topic fallback ────────────────────────────────────────────────


@pytest.mark.parametrize("distinct", [40, 60, 79])
def test_too_few_distinct_passages_for_two_topics_are_one_topic(distinct) -> None:
    """Under 2 x TOPIC_PASSAGES_PER_TOPIC passages the filter emptying is one topic."""
    fitting = FitterDriver(dict(DEFAULTS), _counts("konto", "karte", distinct)).fit()

    assert len(fitting.fitting.topics) == 1
    assert fitting.unplaced == 0


@pytest.mark.parametrize("distinct", [80, 100])
def test_enough_distinct_passages_for_two_topics_name_the_filter(distinct) -> None:
    """From 2 x TOPIC_PASSAGES_PER_TOPIC distinct passages an empty filter is refused.

    The same two words in other counts are distinct passages, not copies.
    """
    with pytest.raises(NoVocabulary, match="TOPIC_NO_BELOW"):
        FitterDriver(dict(DEFAULTS), _counts("fee", "card", distinct)).fit("en")


@pytest.mark.parametrize("distinct", [2, 39])
def test_with_sizing_off_fewer_distinct_passages_than_topics_are_one_topic(
    distinct,
) -> None:
    """TOPIC_PASSAGES_PER_TOPIC=0 fits TOPIC_NUM_TOPICS, so that many are too few."""
    off = dict(DEFAULTS) | {"passages_per_topic": 0}

    fitting = FitterDriver(off, _counts("konto", "karte", distinct)).fit()

    assert len(fitting.fitting.topics) == 1
    assert fitting.unplaced == 0


def test_with_sizing_off_as_many_distinct_passages_as_topics_name_the_filter() -> None:
    """From TOPIC_NUM_TOPICS distinct passages an empty filter is refused."""
    off = dict(DEFAULTS) | {"passages_per_topic": 0}

    with pytest.raises(NoVocabulary, match="TOPIC_NO_BELOW"):
        FitterDriver(off, _counts("fee", "card", 40)).fit("en")


def test_a_large_corpus_tfidf_weighs_flat_is_refused_naming_the_share() -> None:
    """Every kept term in every passage of a corpus big enough for topics is refused."""
    flat = dict(DEFAULTS) | {"no_above": 1.0}

    with pytest.raises(NoVocabulary, match="TOPIC_NO_ABOVE"):
        FitterDriver(flat, _counts("lieferung", "versand", 100)).fit()


def test_many_copies_tfidf_weighs_flat_are_one_topic() -> None:
    """Copies count once: 80 stored passages of two texts are too few to split."""
    flat = dict(DEFAULTS) | {"no_above": 1.0}
    texts = ["refund return return"] * 79 + ["refund refund return"]

    fitting = FitterDriver(flat, corpus(*texts)).fit("en")

    assert len(fitting.fitting.topics) == 1
    assert len(fitting.placed_ids) == 80


# ── The shared-ending strip ───────────────────────────────────────────────


def _named(*names: str, terms: list[list[str]] | None = None) -> dict[int, str]:
    """What the labeller stores when the model answers `names`, one per topic."""
    driver = LabellerDriver(*names)
    held = terms or [[f"term{index}"] for index in range(len(names))]
    return driver.labeller.label_all(
        [(FittedTopic(index, held[index]), []) for index in range(len(names))], "en"
    )


def test_two_names_sharing_an_ending_keep_it() -> None:
    """A pair is not the whole set: the strip needs three names or more."""
    assert _named("Card fees in banking", "Transfers in banking") == {
        0: "Card fees in banking",
        1: "Transfers in banking",
    }


def test_an_ending_only_half_its_carriers_hold_as_a_term_is_still_the_domain() -> None:
    """The subject of most of the topics carrying it keeps it; half is not most."""
    names = {
        0: "Fees in banking",
        1: "Cards in banking",
        2: "Loans in banking",
        3: "Savings in banking",
    }
    terms = {0: ["banking", "fee"], 1: ["banking", "card"], 2: ["loan"], 3: ["saving"]}

    assert _unshared(names, terms, "en") == {
        0: "Fees",
        1: "Cards",
        2: "Loans",
        3: "Savings",
    }


def test_a_name_the_ending_is_all_of_keeps_it() -> None:
    """Stripping the whole name would store an empty one."""
    named = _named(
        "Fees in banking", "Cards in banking", "Loans in banking", "In banking"
    )

    assert named == {0: "Fees", 1: "Cards", 2: "Loans", 3: "In banking"}


def test_a_four_letter_term_reaches_the_word_it_starts() -> None:
    """`card` is four letters, enough to stand for `cards`, so the ending is a subject."""
    names = ["Limits on cards", "Fees on cards", "Insurance on cards", "Transfers"]
    terms = [["card", "limit"], ["card", "fee"], ["card", "insurance"], ["transfer"]]

    assert _named(*names, terms=terms) == dict(enumerate(names))


def test_a_name_not_carrying_the_ending_is_left_whole() -> None:
    """Only the names that end on the domain lose it."""
    named = _named(
        "Card fees in banking",
        "Transfers in banking",
        "Savings in banking",
        "Opening hours of branches",
    )

    assert named[3] == "Opening hours of branches"
