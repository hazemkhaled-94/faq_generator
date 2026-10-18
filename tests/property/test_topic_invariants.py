"""Invariants of a fitted topic model, over corpora nobody wrote down.

The example-based tests say what this corpus comes out as. These say what
must hold of any corpus at all, which is what the next document will be.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from topic_modelling.models import FittedTopic, PassageVocabulary
from topic_modelling.topics import NoVocabulary, TopicFitter, carry_labels

#: A lemma, as chunking stores one: alphabetic, folded, longer than a letter.
LEMMA = st.text(alphabet="abcdefgh", min_size=2, max_size=4)

#: A passage's vocabulary.
LEMMAS = st.lists(LEMMA, max_size=8)

#: A topic's signature.
TERMS = st.lists(LEMMA, min_size=1, max_size=6, unique=True)

#: How many topics the carry properties fit, before and after.
_TOPICS = 5

#: Each passage's dominant topic in one fit.
DOMINANT = st.dictionaries(
    st.integers(min_value=1, max_value=12),
    st.integers(min_value=0, max_value=_TOPICS - 1),
    max_size=12,
)


def decided(count: int) -> list[FittedTopic]:
    """That many topics a person named, `L0` on topic 0 and so on."""
    return [
        FittedTopic(index, ["x"], label=f"L{index}", labelled_by="person")
        for index in range(count)
    ]


#: The settings the properties fit under, small enough to stay quick.
TUNING = {
    "num_topics": 2,
    "passes": 1,
    "random_state": 42,
    "top_terms": 4,
    "min_weight": 0.05,
    "no_below": 1,
    "no_above": 1.0,
}


def corpus_of(lemmas: list[list[str]]) -> list[PassageVocabulary]:
    """Numbers a list of vocabularies as passages."""
    return [
        PassageVocabulary(id=index, lemmas=list(one))
        for index, one in enumerate(lemmas, start=1)
    ]


def fit(lemmas: list[list[str]]):
    """Fits a corpus, or None when there was nothing to fit."""
    passages = corpus_of(lemmas)
    try:
        return TopicFitter(**TUNING).fit(lambda: list(passages), "de")
    except NoVocabulary:
        return None


# ── The fit ───────────────────────────────────────────────────────────────


@given(lemmas=st.lists(LEMMAS, min_size=1, max_size=6))
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_every_stored_weight_is_a_probability(lemmas) -> None:
    """The CHECK on passage_topics.weight holds for any corpus."""
    fitting = fit(lemmas)
    if fitting is None:
        return

    for weight in fitting.weights:
        assert 0 < weight.weight <= 1, weight


@given(lemmas=st.lists(LEMMAS, min_size=1, max_size=6))
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_every_passage_is_either_placed_or_counted_as_unplaced(lemmas) -> None:
    """The two are exhaustive, so the coverage figure cannot drift."""
    fitting = fit(lemmas)
    if fitting is None:
        return

    placed = {weight.passage_id for weight in fitting.weights}
    assert len(placed) + fitting.without_topics == fitting.passages, (
        f"{len(placed)} placed + {fitting.without_topics} unplaced "
        f"!= {fitting.passages} fitted"
    )


@given(lemmas=st.lists(LEMMAS, min_size=1, max_size=6))
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_a_membership_always_names_a_topic_the_fit_produced(lemmas) -> None:
    """A weight pointing at no topic is a membership nothing can resolve."""
    fitting = fit(lemmas)
    if fitting is None:
        return

    indices = {topic.topic_index for topic in fitting.topics}
    assert all(weight.topic_index in indices for weight in fitting.weights)


@given(lemmas=st.lists(LEMMAS, min_size=1, max_size=6))
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_a_membership_always_names_a_passage_the_fit_read(lemmas) -> None:
    """A weight on an id nothing holds would fail the foreign key."""
    fitting = fit(lemmas)
    if fitting is None:
        return

    given_ids = {one.id for one in corpus_of(lemmas)}
    assert all(weight.passage_id in given_ids for weight in fitting.weights)


@given(lemmas=st.lists(LEMMAS, min_size=1, max_size=6))
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_the_space_is_rectangular(lemmas) -> None:
    """PyLDAvis is handed matrices, and a ragged one is a broken figure."""
    fitting = fit(lemmas)
    if fitting is None:
        return

    space = fitting.space
    assert len(space.vocabulary) == fitting.vocabulary
    assert len(space.term_frequency) == fitting.vocabulary
    assert len(space.doc_lengths) == len(space.doc_topic)
    for row in space.topic_term:
        assert len(row) == fitting.vocabulary
    for row in space.doc_topic:
        assert len(row) == len(fitting.topics)


@given(lemmas=st.lists(LEMMAS, min_size=1, max_size=6))
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_every_row_of_the_space_is_a_distribution(lemmas) -> None:
    """Each sums to 1, which is what makes the areas in the figure mean anything."""
    fitting = fit(lemmas)
    if fitting is None:
        return

    for row in (*fitting.space.topic_term, *fitting.space.doc_topic):
        assert abs(sum(row) - 1) < 1e-5, sum(row)
        assert all(value >= 0 for value in row), row


@given(lemmas=st.lists(LEMMAS, min_size=1, max_size=6))
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_a_seeded_fit_is_reproducible(lemmas) -> None:
    """The same corpus and settings must give the same topics every time."""
    first, second = fit(lemmas), fit(lemmas)

    assert (first is None) == (second is None)
    if first is None or second is None:
        return
    assert [one.top_terms for one in first.topics] == [
        one.top_terms for one in second.topics
    ]
    assert first.weights == second.weights


# ── Carrying a label ──────────────────────────────────────────────────────


@given(
    fitted=st.lists(TERMS, max_size=5),
    decisions=st.integers(min_value=0, max_value=5),
    before=DOMINANT,
    after=DOMINANT,
)
@settings(deadline=None)
def test_carrying_labels_keeps_every_topic_as_it_was(
    fitted, decisions, before, after
) -> None:
    """Only the decision may move; the index and the terms are the fit's."""
    topics = [FittedTopic(index, terms) for index, terms in enumerate(fitted)]

    carried, _ = carry_labels(topics, decided(decisions), before=before, after=after)

    assert len(carried) == len(topics)
    for was, now in zip(topics, carried, strict=True):
        assert now.topic_index == was.topic_index
        assert now.top_terms == was.top_terms


@given(
    fitted=st.integers(min_value=0, max_value=5),
    decisions=st.integers(min_value=0, max_value=5),
    before=DOMINANT,
    after=DOMINANT,
)
@settings(deadline=None)
def test_every_decision_is_carried_once_or_counted_lost(
    fitted, decisions, before, after
) -> None:
    """None is carried twice, and none goes without being counted."""
    topics = [FittedTopic(index, ["x"]) for index in range(fitted)]

    carried, dropped = carry_labels(
        topics, decided(decisions), before=before, after=after
    )

    labels = [one.label for one in carried if one.label]
    assert len(labels) == len(set(labels)), labels
    assert len(labels) + dropped == decisions, (labels, dropped)


@given(before=DOMINANT, after=DOMINANT)
@settings(deadline=None)
def test_a_carried_decision_lands_where_most_of_its_passages_went(
    before, after
) -> None:
    """Most both ways, and only there.

    Of all the old topic's passages, and of the new one's that both fits hold.
    """
    topics = [FittedTopic(index, ["x"]) for index in range(_TOPICS)]

    carried, _ = carry_labels(topics, decided(_TOPICS), before=before, after=after)

    common = before.keys() & after.keys()
    for old in range(_TOPICS):
        for new in range(_TOPICS):
            mine = {one for one in before if before[one] == old}
            theirs = {one for one in common if after[one] == new}
            most = 2 * len(mine & theirs) > max(len(mine), len(theirs))
            assert (carried[new].label == f"L{old}") == most, (old, new)


@given(fitted=st.lists(TERMS, max_size=5), before=DOMINANT, after=DOMINANT)
@settings(deadline=None)
def test_a_first_fit_carries_no_label(fitted, before, after) -> None:
    """There is nothing to carry from, and that is not an error."""
    topics = [FittedTopic(index, terms) for index, terms in enumerate(fitted)]

    carried, dropped = carry_labels(topics, [], before=before, after=after)

    assert all(one.label is None for one in carried)
    assert dropped == 0


# ── The settings the fitter refuses ───────────────────────────────────────


@given(num_topics=st.integers(min_value=-5, max_value=1))
@settings(deadline=None)
def test_too_few_topics_is_never_a_partition(num_topics) -> None:
    """Below two there is nothing to tell apart."""
    with pytest.raises(ValueError, match="TOPIC_NUM_TOPICS"):
        TopicFitter(**(TUNING | {"num_topics": num_topics}))


@given(min_weight=st.floats(min_value=-5, max_value=0))
@settings(deadline=None)
def test_a_floor_at_or_below_zero_is_refused(min_weight) -> None:
    """The column's CHECK requires a weight above zero."""
    with pytest.raises(ValueError, match="TOPIC_MIN_WEIGHT"):
        TopicFitter(**(TUNING | {"min_weight": min_weight}))


@given(
    no_above=st.one_of(
        st.floats(min_value=-5, max_value=0),
        st.floats(min_value=1.0001, max_value=5),
    )
)
@settings(deadline=None)
def test_a_share_outside_zero_to_one_is_refused(no_above) -> None:
    """It is a share of the corpus, so it cannot exceed all of it."""
    with pytest.raises(ValueError, match="TOPIC_NO_ABOVE"):
        TopicFitter(**(TUNING | {"no_above": no_above}))
