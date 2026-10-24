"""Fitting a topic model, and what the fit reports."""

from __future__ import annotations

from math import isnan

import pytest
import synth_topics as st
from topic_drivers import FitterDriver, corpus

from topic_modelling.models import PassageVocabulary
from topic_modelling.topics import NoVocabulary, memberships


def test_every_weight_is_storable(fitter) -> None:
    """A membership weight stays inside (0, 1], as the column's CHECK needs.

    And no topic's term weight is NaN, which compares false against the floor.
    """
    fitting = fitter.fit("de")

    assert fitting.fitting.weights, "two clear subjects produced no membership"
    for weight in fitting.fitting.weights:
        assert 0 < weight.weight <= 1, (
            f"weight {weight.weight!r} breaches the CHECK on passage_topics"
        )
    for row in fitting.space.topic_term:
        assert not any(isnan(value) for value in row), row


def test_the_fit_reports_what_it_was_over(fitter, passages) -> None:
    """The vocabulary size, the passage count and the language."""
    fitting = fitter.fit("de").fitting

    assert fitting.vocabulary > 0
    assert fitting.passages == len(passages)
    assert fitting.language == "de", "a fit belongs to the language it was over"


def test_the_fit_produces_the_number_of_topics_it_was_asked_for(fitter) -> None:
    """TOPIC_NUM_TOPICS is a ceiling, fitted as written with no passages per topic."""
    assert fitter.fit("de").topic_count == 2


@pytest.mark.parametrize(
    ("per_topic", "passages", "count"),
    [(0, 15, 7), (10, 15, 2), (10, 45, 4), (10, 1000, 7)],
)
def test_the_topic_count_follows_the_corpus_under_its_ceiling(
    settings, per_topic: int, passages: int, count: int
) -> None:
    """One topic per TOPIC_PASSAGES_PER_TOPIC passages, from two to the ceiling."""
    from topic_modelling.topics import TopicFitter

    fitter = TopicFitter(
        **settings | {"num_topics": 7, "passages_per_topic": per_topic}
    )

    assert fitter._count(passages) == count


def test_every_topic_carries_a_signature_no_longer_than_asked_for(
    settings, passages
) -> None:
    """TOPIC_TOP_TERMS caps it; a small vocabulary may not reach it."""
    fitting = FitterDriver(settings | {"top_terms": 3}, passages).fit("de")

    for index in range(fitting.topic_count):
        terms = fitting.terms_of(index)
        assert 0 < len(terms) <= 3, terms
        assert len(set(terms)) == len(terms), f"{terms} repeats a term"


def test_the_same_seed_gives_the_same_model(settings, passages) -> None:
    """A reference dataset's topic weighting must not move between runs."""
    first = FitterDriver(settings, passages).fit("de")
    second = FitterDriver(settings, passages).fit("de")

    assert [first.terms_of(i) for i in range(2)] == [
        second.terms_of(i) for i in range(2)
    ]
    assert first.fitting.weights == second.fitting.weights


def test_the_corpus_is_walked_more_than_once(fitter) -> None:
    """Once to build the vocabulary, once per pass, once to score."""
    fitter.fit("de")

    assert fitter.walks > 2, fitter.walks


def test_a_corpus_that_cannot_be_rewalked_is_refused(fitter) -> None:
    """A spent generator would fit a model over nothing and report success."""
    with pytest.raises(NoVocabulary, match="second walk"):
        fitter.fit_once_walkable("de")


def test_an_empty_corpus_is_refused_by_name(settings) -> None:
    """The message has to say which language had nothing."""
    with pytest.raises(NoVocabulary, match="no de passages"):
        FitterDriver(settings).fit("de")


def test_passages_with_no_lemma_fail_the_run(settings) -> None:
    """An empty vocabulary is a failure, not an empty fit."""
    with pytest.raises(NoVocabulary, match="frequency filter"):
        FitterDriver(settings, corpus("", "", "")).fit("de")


def test_the_refusal_says_what_the_filter_was_and_what_it_left(
    settings, passages
) -> None:
    """A reader has to be able to tell which setting to move."""
    with pytest.raises(NoVocabulary) as raised:
        FitterDriver(settings | {"no_below": 99}, corpus("", "", "", "")).fit("de")

    said = str(raised.value)
    assert "99" in said, said
    assert "4 passage" in said, said


# ── What falls out of a topic ─────────────────────────────────────────────


def test_a_passage_holding_none_of_the_vocabulary_is_counted(fitter) -> None:
    """It is counted once and appears in no membership."""
    counted = fitter.with_passage(99, "zzz", "qqq").fit("de")

    assert counted.unplaced == 1, counted.unplaced
    assert 99 not in counted.placed_ids


def test_a_passage_placed_nowhere_is_named_for_the_store_to_place(fitter) -> None:
    """Counting it is not enough to put it anywhere."""
    counted = fitter.with_passage(99, "zzz", "qqq").fit("de")

    assert counted.fitting.unplaced == (99,), counted.fitting.unplaced


def test_a_passage_with_no_lemmas_at_all_is_counted(fitter) -> None:
    """A passage chunking stored no lemmas for is the same case.

    Skipped rather than normalised, which would divide by its zero sum.
    """
    empty = fitter.holding(PassageVocabulary(id=98)).fit("de")

    assert empty.unplaced == 1, empty.unplaced
    assert all(abs(sum(row) - 1) < 1e-6 for row in empty.space.doc_topic)


@pytest.mark.parametrize(
    ("share", "kept"),
    [(0.5, [0]), (0.4, [0, 1]), (0.15, [0, 1, 2]), (0.05, [0, 1, 2, 3])],
)
def test_a_membership_is_kept_by_its_share_of_the_strongest(share, kept) -> None:
    """Weights 0.6, 0.25, 0.1 and 0.05: what a passage keeps follows its own top."""
    found = [(0, 0.6), (1, 0.25), (2, 0.1), (3, 0.05)]

    assert [index for index, _ in memberships(found, share)] == kept


def test_the_strongest_membership_is_kept_however_weak() -> None:
    """On a passage that splits over many topics every weight is small."""
    found = [(0, 0.03), (1, 0.02), (2, 0.01)]

    assert memberships(found, 0.5) == [(0, 0.03), (1, 0.02)]


def test_a_tie_for_the_strongest_is_kept_whole() -> None:
    """A tie goes to neither topic."""
    found = [(0, 0.3), (1, 0.3), (2, 0.1)]

    assert memberships(found, 0.9) == [(0, 0.3), (1, 0.3)]


def test_a_passage_scored_zero_everywhere_has_no_membership() -> None:
    """The column's CHECK needs a weight above zero."""
    assert memberships([(0, 0.0), (1, 0.0)], 0.5) == []


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_fitted_passage_keeps_only_what_is_near_its_strongest(
    settings, passages, english, language
) -> None:
    """Over a German and an English corpus, every kept weight is within the share."""
    fitting = FitterDriver(settings, passages if language == "de" else english).fit(
        language
    )

    top: dict[int, float] = {}
    for weight in fitting.fitting.weights:
        top[weight.passage_id] = max(top.get(weight.passage_id, 0), weight.weight)
    assert top, "nothing was placed"
    for weight in fitting.fitting.weights:
        assert weight.weight >= settings["relative_weight"] * top[weight.passage_id]


def test_a_passage_the_model_gives_a_vocabulary_is_never_left_unplaced(
    settings, passages
) -> None:
    """Its strongest membership is always kept, so only a passage with no lemma is not."""
    mixed = PassageVocabulary(
        id=99, lemmas=["lieferung", "versand", "wartung", "reparatur"]
    )

    fitted = FitterDriver(settings | {"relative_weight": 0.99}, [*passages, mixed]).fit(
        "de"
    )

    assert 99 in fitted.placed_ids
    assert fitted.unplaced == 0


def test_the_no_topic_warning_is_logged_once_for_the_kept_draw(
    settings, passages, caplog
) -> None:
    """Not once per draw: seven of the eight are thrown away."""
    caplog.set_level("INFO", logger="topic_modelling.topics")

    FitterDriver(settings, passages).holding(PassageVocabulary(id=98)).fit("de")

    warned = [r for r in caplog.records if "came out with no topic" in r.getMessage()]
    assert len(warned) == 1, [r.getMessage() for r in warned]


@pytest.mark.parametrize("language", ["de", "en"])
def test_the_fit_logs_how_many_members_sit_nearest_their_own_topic(
    settings, passages, english, caplog, language
) -> None:
    """The proxy that tracks the labels, per language, beside the draw kept."""
    caplog.set_level("INFO", logger="topic_modelling.topics")

    FitterDriver(settings, passages if language == "de" else english).fit(language)

    said = [
        r.getMessage()
        for r in caplog.records
        if "nearest their own topic's centroid" in r.getMessage()
    ]
    assert len(said) == 1, said
    assert said[0].startswith(f"{language}: "), said[0]
    share = float(said[0].rsplit("nearest", 1)[0].split()[-1])
    assert 0.0 <= share <= 1.0


def test_a_term_in_every_passage_is_dropped_from_the_vocabulary(
    settings, passages
) -> None:
    """The boilerplate filter, which no word list could know about."""
    everywhere = [
        PassageVocabulary(id=one.id, lemmas=[*one.lemmas, "seitenfuss"])
        for one in passages
    ]

    fitting = FitterDriver(settings, everywhere).fit("de")

    assert "seitenfuss" not in fitting.space.vocabulary, fitting.space.vocabulary


def test_a_term_in_too_few_passages_is_dropped_from_the_vocabulary(fitter) -> None:
    """The typo and one-off product name filter."""
    fitting = fitter.with_passage(97, "lieferung", "einmaligerbegriff").fit("de")

    assert "einmaligerbegriff" not in fitting.space.vocabulary


def test_two_clear_subjects_come_out_as_two_topics(fitter, passages) -> None:
    """The passages about one subject do not land on the topic of the other."""
    fitting = fitter.fit("de")

    shipping = {fitting.dominant_topic(1), fitting.dominant_topic(2)}
    maintenance = {fitting.dominant_topic(3), fitting.dominant_topic(4)}

    assert len(shipping) == 1, f"the two shipping passages split: {shipping}"
    assert len(maintenance) == 1, f"the two maintenance passages split: {maintenance}"
    assert shipping != maintenance, "both subjects landed on one topic"


def test_a_topic_signature_is_drawn_from_the_terms_of_its_own_subject(fitter) -> None:
    """A signature mixing both subjects is a model that has not separated."""
    fitting = fitter.fit("de")
    shipping = fitting.terms_of(fitting.dominant_topic(1) or 0)

    assert "lieferung" in shipping, shipping
    assert "wartung" not in shipping, shipping


# ── Settings the fitter refuses ───────────────────────────────────────────


@pytest.mark.parametrize(
    "bad",
    [
        {"num_topics": 1},
        {"num_topics": 0},
        {"num_topics": -1},
        {"top_terms": 0},
        {"top_terms": -1},
        {"relative_weight": 0},
        {"relative_weight": -0.1},
        # A share of the strongest of 1 keeps only a tie for it, and above 1 nothing.
        {"relative_weight": 1},
        {"relative_weight": 1.5},
        {"no_above": 0},
        {"no_above": -0.5},
        {"no_above": 1.01},
    ],
)
def test_a_fitter_that_cannot_do_its_job_is_refused(settings, bad) -> None:
    """The settings are checked when the fitter is built, not at the fit."""
    with pytest.raises(ValueError):
        FitterDriver(settings | bad)


@pytest.mark.parametrize(
    "allowed",
    [{"relative_weight": 0.999}, {"no_above": 1}, {"num_topics": 2}, {"top_terms": 1}],
)
def test_the_edge_of_each_range_is_allowed(settings, allowed) -> None:
    """The bounds are inclusive where the message says they are."""
    FitterDriver(settings | allowed)


def test_a_settings_refusal_names_the_environment_variable(settings) -> None:
    """A reader has to know which line of the env file to change."""
    with pytest.raises(ValueError, match="TOPIC_NUM_TOPICS"):
        FitterDriver(settings | {"num_topics": 1})


def test_the_fit_keeps_the_most_cohesive_of_its_seeded_draws(
    settings, passages, monkeypatch
) -> None:
    """One seeded draw was kept unread, and seeds differ in how alike their members are.

    Each draw is seeded from TOPIC_RANDOM_STATE on, so the same corpus keeps
    the same draw twice.
    """
    from topic_modelling import topics

    drawn: list[tuple[object, int]] = []
    kept: list[int] = []
    real, read = topics.Nmf, topics.TopicFitter._topics

    def seeded(**kwargs):
        model = real(**kwargs)
        drawn.append((model, kwargs["random_state"]))
        return model

    def spied(self, model):
        kept.append(next(seed for one, seed in drawn if one is model))
        return read(self, model)

    monkeypatch.setattr(topics, "Nmf", seeded)
    monkeypatch.setattr(topics.TopicFitter, "_topics", spied)
    # The fourth draw, seeded 45, is the most cohesive.
    monkeypatch.setattr(
        topics, "_cohesion", lambda weights, vectors: -abs(len(drawn) % 8 - 4)
    )

    FitterDriver(settings, passages).fit("de")
    FitterDriver(settings, passages).fit("de")

    assert [seed for _, seed in drawn[: topics._DRAWS]] == [
        42 + draw for draw in range(topics._DRAWS)
    ]
    assert kept == [45, 45]


def test_a_passage_with_no_vector_is_left_out_of_the_measure() -> None:
    """One that gained its first fact mid-fit was scored but never weighed."""
    from topic_modelling.models import PassageWeight
    from topic_modelling.topics import _cohesion

    vectors = {1: {0: 1.0}, 2: {0: 1.0}}
    weights = [
        PassageWeight(1, 0, 0.9),
        PassageWeight(2, 0, 0.9),
        PassageWeight(99, 0, 0.9),
    ]

    assert _cohesion(weights, vectors) == 1.0


def test_members_alike_are_more_cohesive_than_members_apart() -> None:
    """The mean likeness of a topic's members, over the topics holding two or more."""
    from topic_modelling.models import PassageWeight
    from topic_modelling.topics import _cohesion

    vectors = {1: {0: 1.0}, 2: {0: 1.0}, 3: {1: 1.0}, 4: {1: 1.0}}
    alike = [PassageWeight(1, 0, 0.9), PassageWeight(2, 0, 0.9)]
    alike += [PassageWeight(3, 1, 0.9), PassageWeight(4, 1, 0.9)]
    apart = [PassageWeight(1, 0, 0.9), PassageWeight(3, 0, 0.9)]
    apart += [PassageWeight(2, 1, 0.9), PassageWeight(4, 1, 0.9)]

    assert _cohesion(alike, vectors) == 1.0
    assert _cohesion(apart, vectors) == 0.0


def test_a_seed_at_the_top_of_its_range_still_fits(settings, passages) -> None:
    """TOPIC_RANDOM_STATE may be 2**32 - 1, and the draws after it wrap round."""
    fitting = FitterDriver(settings | {"random_state": 2**32 - 1}, passages).fit("de")

    assert fitting.fitting.weights


@pytest.mark.parametrize(("domain", "language"), [("bank", "en"), ("shop", "de")])
def test_two_identical_passages_get_identical_memberships(domain, language) -> None:
    """A repeated disclaimer is one text; the fit places both copies alike."""
    base = st.corpus(domain, language, 200, seed=5)
    twins = base + [
        PassageVocabulary(id=10_000 + one.id, lemmas=list(one.lemmas)) for one in base
    ]

    fitted = FitterDriver(dict(st.DEFAULTS), twins).fit(language)

    differ = [
        one.id
        for one in base
        if any(
            abs(
                fitted.weights_of(one.id).get(k, 0.0)
                - fitted.weights_of(10_000 + one.id).get(k, 0.0)
            )
            > 1e-6
            for k in set(fitted.weights_of(one.id))
            | set(fitted.weights_of(10_000 + one.id))
        )
    ]
    assert differ == []


def test_a_language_of_one_distinct_passage_gets_one_topic_holding_it(settings) -> None:
    """One passage, or copies of it, is one subject: a fit has nothing to split."""
    same = ("zinsen", "kredit", "kredit")
    fitting = (
        FitterDriver(settings)
        .with_passage(1, *same)
        .with_passage(2, *same)
        .with_passage(3)
        .fit("de")
        .fitting
    )

    assert [t.top_terms for t in fitting.topics] == [["kredit", "zinsen"]]
    assert {(w.passage_id, w.topic_index, w.weight) for w in fitting.weights} == {
        (1, 0, 1.0),
        (2, 0, 1.0),
    }
    assert fitting.unplaced == (3,)
    assert fitting.space.doc_topic == [[1.0], [1.0]]


@pytest.mark.parametrize(
    "sizing",
    [{"passages_per_topic": 40}, {"num_topics": 7, "passages_per_topic": 0}],
    ids=["sized", "off"],
)
@pytest.mark.parametrize(
    "texts",
    [
        ["kreditkarte gebühr", "kreditkarte gebühr gebühr"],
        ["terms apply"] * 3 + ["terms apply online"],
    ],
)
def test_passages_the_filter_cannot_tell_apart_get_one_topic(
    settings, sizing, texts
) -> None:
    """The same words in other counts, or copies plus a near-copy, still fit.

    With TOPIC_PASSAGES_PER_TOPIC off too, which is a documented value.
    """
    sized = settings | sizing

    fitting = FitterDriver(sized, corpus(*texts)).fit("de").fitting

    assert len(fitting.topics) == 1
    assert {w.passage_id for w in fitting.weights} == set(range(1, len(texts) + 1))


def test_a_corpus_big_enough_for_topics_whose_terms_the_filter_drops_names_the_setting(
    settings,
) -> None:
    """TOPIC_NO_BELOW above every term's count is a misconfiguration, not one topic."""
    many = [f"{word} shared{index % 3}" for index, word in enumerate(_WORDS)]
    sized = settings | {"passages_per_topic": 5, "no_below": 999}

    with pytest.raises(NoVocabulary, match="TOPIC_NO_BELOW"):
        FitterDriver(sized, corpus(*many)).fit("de")


_WORDS = [f"word{index}" for index in range(60)]
