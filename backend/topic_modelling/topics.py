"""Fitting a topic model over one language's vocabulary."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import replace
from itertools import batched
from typing import cast

import numpy as np
from gensim import corpora
from gensim.models import Nmf, TfidfModel

from topic_modelling.models import (
    FittedTopic,
    Fitting,
    PassageVocabulary,
    PassageWeight,
    TopicSpace,
)

log = logging.getLogger(__name__)

#: How many passages to hold at once while building the vocabulary.
_BATCH = 500

#: The fewest topics a fit is worth. Below two nothing is partitioned.
_FEWEST = 2

#: How many seeded draws a fit makes, from TOPIC_RANDOM_STATE on, keeping the
#: one whose members are most alike. Seeds over one corpus differed in that
#: by as much as two rebuilds' topics did, so keeping the first unread
#: re-rolled how coherent the topics came out. A draw is a second or two.
_DRAWS = 8

#: The corpus, as the fitter takes it: a callable handing back a fresh walk
#: over every passage.
Corpus = Callable[[], Iterable[PassageVocabulary]]


class NoVocabulary(Exception):
    """Raised when there is nothing to fit a model on."""


class _BagsOfWords:
    """The corpus as bags of words, rebuilt on every walk."""

    def __init__(self, corpus: Corpus, dictionary: corpora.Dictionary) -> None:
        """Initialises the view."""
        self._corpus = corpus
        self._dictionary = dictionary

    def __iter__(self) -> Iterator[list[tuple[int, int]]]:
        """Walks the corpus once."""
        for passage in self._corpus():
            yield cast(
                "list[tuple[int, int]]", self._dictionary.doc2bow(passage.lemmas)
            )


class TopicFitter:
    """Fits topics over the terms one language's passages use.

    Non-negative matrix factorisation over a tf-idf weighted space. The
    vocabulary is the content lemmas chunking stored. The weights returned
    are normalised, and the fit is seeded.
    """

    def __init__(
        self,
        *,
        num_topics: int,
        passes: int,
        random_state: int,
        top_terms: int,
        relative_weight: float,
        no_below: int,
        no_above: float,
        passages_per_topic: int = 0,
    ) -> None:
        """Initialises the fitter.

        Args:
            num_topics: Topics to fit, at least 2. The ceiling when
                `passages_per_topic` is set.
            passes: Times the factorisation walks the corpus.
            random_state: Seed for the factorisation.
            top_terms: Terms kept as a topic's signature, at least 1.
            relative_weight: Share of a passage's strongest membership weight a
                weaker one must reach to be kept, in (0, 1).
            no_below: Fewest passages a term must appear in.
            no_above: Largest share of passages a term may appear in, in
                (0, 1].
            passages_per_topic: How many passages one topic is worth, which
                scales the count to each language's share of the corpus. 0
                fits `num_topics` whatever the corpus is.

        Raises:
            ValueError: If a setting is outside the range named above.
        """
        if num_topics < _FEWEST:
            raise ValueError(
                f"TOPIC_NUM_TOPICS={num_topics} is not a partition of anything; "
                f"it must be at least {_FEWEST}"
            )
        if top_terms < 1:
            raise ValueError(
                f"TOPIC_TOP_TERMS={top_terms} leaves a topic with no signature; "
                "it must be at least 1"
            )
        if not 0 < relative_weight < 1:
            raise ValueError(
                f"TOPIC_RELATIVE_WEIGHT={relative_weight} is not a share of a "
                "passage's strongest membership; it must be above 0 and below 1, "
                "since a membership is kept only within that share of the "
                "strongest, which is always kept"
            )
        if not 0 < no_above <= 1:
            raise ValueError(
                f"TOPIC_NO_ABOVE={no_above} is not a share of the corpus; it must "
                "be above 0 and at most 1"
            )
        self._num_topics = num_topics
        self._passes = passes
        self._random_state = random_state
        self._top_terms = top_terms
        self._relative_weight = relative_weight
        self._no_below = no_below
        self._no_above = no_above
        self._passages_per_topic = passages_per_topic

    def fit(self, corpus: Corpus, language: str) -> Fitting:
        """Fits one language's model and scores its passages against it.

        The corpus is walked rather than held: once to build the vocabulary,
        once to read each passage's tf-idf vector, and for each of the
        `_DRAWS` draws once per pass and once more to score. Those vectors,
        one per passage, are what is held.

        Args:
            corpus: Hands back a fresh walk over the passages each time it is
                called.
            language: The ISO 639-1 code the fit is recorded against.

        Returns:
            The topics, the memberships within the share of each passage's
            strongest, and the whole fitted space.

        Passages that cannot be told apart, one passage or copies of it, are
        not fitted: where the frequency filter leaves no term or tf-idf
        weighs every term zero, and the language has too few passages for two
        topics by TOPIC_PASSAGES_PER_TOPIC, or fewer than TOPIC_NUM_TOPICS
        with that off, they get one topic holding them.

        Raises:
            NoVocabulary: If the corpus is empty, if no passage has a lemma, if
                the frequency filter left no terms or tf-idf weighs every term
                zero in a corpus large enough for more than one topic, or if a
                second walk yields nothing.
        """
        dictionary = corpora.Dictionary()
        counted = 0
        distinct: set[int] = set()
        for batch in batched((p.lemmas for p in corpus()), _BATCH):
            dictionary.add_documents(batch, prune_at=None)  # pyright: ignore[reportArgumentType]
            counted += len(batch)
            distinct.update(hash(tuple(sorted(one))) for one in batch if one)

        if not counted:
            raise NoVocabulary(
                f"there are no {language} passages to fit a topic model over"
            )

        # One text however many times it is stored has nothing to split.
        if len(distinct) == 1:
            return self._single(corpus, language, counted)

        before = len(dictionary)
        # A count against a share is unsatisfiable on a small corpus: no term
        # is in at least 3 and at most half of 5 passages. So the count is held
        # to what the share allows, and the share to what the count needs; from
        # 6 passages up both are as set.
        no_below = min(self._no_below, max(1, int(self._no_above * counted)))
        no_above = min(1.0, max(self._no_above, (no_below + 0.5) / counted))
        dictionary.filter_extremes(
            no_below=no_below,
            no_above=no_above,
            keep_n=None,  # pyright: ignore[reportArgumentType]
        )
        if before and not dictionary and self._small(len(distinct)):
            # Terms exist but none can tell a passage from another, as with
            # one passage or copies of it, and there are too few passages to
            # be given more than one topic anyway.
            return self._single(corpus, language, counted)
        if not dictionary:
            raise NoVocabulary(
                f"the frequency filter left no terms: {before} were found across "
                f"{counted} passage(s), and none appears in at least "
                f"{no_below} of them and at most {no_above:.0%} (TOPIC_NO_BELOW is "
                f"{self._no_below}, TOPIC_NO_ABOVE {self._no_above:.0%})"
            )

        bows = _BagsOfWords(corpus, dictionary)
        # A corpus that cannot be walked twice.
        if not any(bool(bow) for bow in bows):
            raise NoVocabulary(
                f"a second walk over the corpus yielded none of the "
                f"{len(dictionary)} terms the first one found. A fit walks it "
                f"once per pass, so it must be re-readable."
            )

        # From the dictionary, which already holds the document frequencies.
        weighting = TfidfModel(dictionary=dictionary)
        # A term in every passage has an idf of zero. When every surviving term
        # does, the whole weighted matrix is zero, and the factorisation
        # divides by its norm and returns a model of NaN.
        if not any(bool(weighted) for weighted in weighting[bows]):
            if self._small(len(distinct)):
                return self._single(corpus, language, counted)
            raise NoVocabulary(
                f"every one of the {len(dictionary)} terms kept appears in all "
                f"{counted} {language} passage(s), so tf-idf weighs each of them "
                f"zero and nothing separates one passage from another. Lower "
                f"TOPIC_NO_ABOVE, which is {self._no_above:.0%}, to drop them."
            )

        wanted = self._count(counted)
        log.info(
            "%s: fitting %d topics over %d passage(s), %d term(s) of %d kept",
            language,
            wanted,
            counted,
            len(dictionary),
            before,
        )
        vectors = {
            passage.id: dict(
                cast(
                    "list[tuple[int, float]]",
                    weighting[dictionary.doc2bow(passage.lemmas)],
                )
            )
            for passage in corpus()
        }
        best = None
        for draw in range(_DRAWS):
            model = Nmf(
                corpus=weighting[bows],
                id2word=dictionary,
                num_topics=wanted,
                passes=self._passes,
                # Wrapped, so a seed at the top of its range still draws.
                random_state=(self._random_state + draw) % 2**32,
            )
            scored = self._score(model, corpus, dictionary, weighting)
            held = _cohesion(scored[0], vectors)
            if best is None or held > best[0]:
                best = (held, draw, model, scored)
        assert best is not None, "_DRAWS is at least one"
        held, draw, model, (weights, unplaced, space) = best
        log.info(
            "%s: kept the draw seeded %d of %d, its members %.3f alike, "
            "%.3f nearest their own topic's centroid",
            language,
            (self._random_state + draw) % 2**32,
            _DRAWS,
            held,
            _centroid_share(weights, vectors),
        )
        if unplaced:
            log.warning(
                "%s: %d passage(s) came out with no topic; each goes to the topic "
                "whose centroid is nearest, where it has a vector",
                language,
                len(unplaced),
            )
        return Fitting(
            language=language,
            topics=self._topics(model),
            weights=weights,
            passages=counted,
            without_topics=len(unplaced),
            vocabulary=len(dictionary),
            space=space,
            unplaced=tuple(unplaced),
        )

    def _small(self, passages: int) -> bool:
        """Whether this many passages are too few to split into topics.

        By the same sizing `_count` uses: one topic is worth
        TOPIC_PASSAGES_PER_TOPIC passages and a fit has at least two. With
        that off a fit is TOPIC_NUM_TOPICS topics, which takes as many
        passages.
        """
        if self._passages_per_topic <= 0:
            return passages < self._num_topics
        return passages < _FEWEST * self._passages_per_topic

    def _single(self, corpus: Corpus, language: str, counted: int) -> Fitting:
        """The fit of a language too small to split, whose passages cannot be told apart.

        One passage, copies of it, or too few passages for the frequency
        filter or tf-idf to leave a term that separates them. The one topic holds every passage that
        has lemmas, so the facts they carry reach a question unit; a passage
        with none is left unplaced, as in any fit.
        """
        terms: Counter[str] = Counter()
        held: list[PassageVocabulary] = []
        without: list[int] = []
        for passage in corpus():
            if passage.lemmas:
                terms.update(passage.lemmas)
                held.append(passage)
            else:
                without.append(passage.id)
        vocabulary = [term for term, _ in terms.most_common()]
        total = sum(terms.values())
        log.info(
            "%s: %d passage(s) are one text, so one topic holds them", language, counted
        )
        return Fitting(
            language=language,
            topics=[
                FittedTopic(topic_index=0, top_terms=vocabulary[: self._top_terms])
            ],
            weights=[PassageWeight(one.id, 0, 1.0) for one in held],
            passages=counted,
            without_topics=len(without),
            vocabulary=len(vocabulary),
            space=TopicSpace(
                topic_term=[[terms[term] / total for term in vocabulary]],
                doc_topic=[[1.0] for _ in held],
                doc_lengths=[len(one.lemmas) for one in held],
                vocabulary=vocabulary,
                term_frequency=[terms[term] for term in vocabulary],
            ),
            unplaced=tuple(without),
        )

    def _count(self, passages: int) -> int:
        """How many topics to fit over this many passages.

        TOPIC_NUM_TOPICS is the ceiling and TOPIC_PASSAGES_PER_TOPIC turns
        it into a count that follows the corpus. One fit runs per language
        and two languages are rarely the same size: the same count over each
        gives subjects on one side and slivers on the other. The slivers are
        what a question is written about, so they are worth not making.

        0 turns it off and the ceiling is taken as written.
        """
        if self._passages_per_topic <= 0:
            return self._num_topics
        return max(_FEWEST, min(self._num_topics, passages // self._passages_per_topic))

    def _topics(self, model: Nmf) -> list[FittedTopic]:
        """Reads each topic's signature out of the fitted model."""
        return [
            FittedTopic(
                topic_index=index,
                top_terms=[
                    term for term, _ in model.show_topic(index, topn=self._top_terms)
                ],
            )
            for index in range(model.num_topics)
        ]

    def _score(
        self,
        model: Nmf,
        corpus: Corpus,
        dictionary: corpora.Dictionary,
        weighting: TfidfModel,
    ) -> tuple[list[PassageWeight], list[int], TopicSpace]:
        """Scores every passage against the fitted model, in one walk.

        Returns:
            The memberships within the share of each passage's strongest, the
            passages holding none, and the space the visualisation is drawn from.
        """
        weights: list[PassageWeight] = []
        doc_topic: list[list[float]] = []
        doc_lengths: list[int] = []
        without: list[int] = []
        for passage in corpus():
            bow = cast("list[tuple[int, int]]", dictionary.doc2bow(passage.lemmas))
            # The projection draws its coordinate order from the model's one
            # generator, so reseeded here a passage's weights depend on its
            # vector alone, not on how many passages were scored before it.
            model.random_state = np.random.RandomState(self._random_state)
            found = model.get_document_topics(weighting[bow], minimum_probability=0)
            if found:
                row = [0.0] * model.num_topics
                for index, weight in found:
                    row[int(index)] = float(weight)
                total = sum(row)
                doc_topic.append([value / total for value in row])
                doc_lengths.append(sum(count for _, count in bow))

            kept = memberships(found, self._relative_weight)
            # A passage holding none of the vocabulary: the strongest
            # membership of any other is always kept.
            if not kept:
                without.append(passage.id)
                continue
            weights.extend(
                PassageWeight(
                    passage_id=passage.id,
                    topic_index=int(index),
                    # Clamped to the CHECK on passage_topics.weight.
                    weight=min(1.0, float(weight)),
                )
                for index, weight in kept
            )
        return (
            weights,
            without,
            TopicSpace(
                topic_term=model.get_topics(normalize=True).tolist(),
                doc_topic=doc_topic,
                doc_lengths=doc_lengths,
                vocabulary=[dictionary[i] for i in range(len(dictionary))],
                term_frequency=[dictionary.cfs[i] for i in range(len(dictionary))],
            ),
        )


def memberships(
    found: Iterable[tuple[int, float]], relative_weight: float
) -> list[tuple[int, float]]:
    """The topics one passage belongs to: those within a share of its strongest.

    The weights a passage gets spread over the topics, so any absolute floor
    is a share of one over their count and moves with it; a share of the
    passage's own strongest does not. The strongest is always kept, a tie for
    it too, and a weight of zero never is.
    """
    found = list(found)
    top = max((weight for _, weight in found), default=0.0)
    return [
        (index, weight)
        for index, weight in found
        if weight > 0 and weight >= relative_weight * top
    ]


def _centroid_share(
    weights: Iterable[PassageWeight], vectors: Mapping[int, Mapping[int, float]]
) -> float:
    """The share of a fit's members that sit nearest their own topic's centroid.

    A topic's centroid is its members' tf-idf vectors summed and scaled to length
    1. The mean over topics of the share of each one's members nearer to it than
    to any other: it tracks a reviewer's reading of whether a topic is coherent
    better than `_cohesion` does, and is only logged, so it picks no draw.
    """
    members: dict[int, list[int]] = {}
    for weight in weights:
        if weight.passage_id in vectors:
            members.setdefault(weight.topic_index, []).append(weight.passage_id)
    centroids: dict[int, dict[int, float]] = {}
    for topic, held in members.items():
        summed: dict[int, float] = {}
        for passage in held:
            for term, value in vectors[passage].items():
                summed[term] = summed.get(term, 0.0) + value
        length = sum(value * value for value in summed.values()) ** 0.5 or 1.0
        centroids[topic] = {term: value / length for term, value in summed.items()}
    shares = []
    for topic, held in members.items():
        own = 0
        for passage in held:
            vector = vectors[passage]
            nearest = max(
                centroids,
                key=lambda one: (
                    sum(
                        value * centroids[one].get(term, 0.0)
                        for term, value in vector.items()
                    ),
                    -one,
                ),
            )
            own += nearest == topic
        shares.append(own / len(held))
    return sum(shares) / len(shares) if shares else 0.0


def _cohesion(
    weights: Iterable[PassageWeight], vectors: Mapping[int, Mapping[int, float]]
) -> float:
    """How alike a fit's members are: the mean over its topics of their members' mean likeness.

    Likeness is the cosine of two passages' tf-idf vectors, which the fit
    normalised to length 1. A topic of one passage says nothing and is left out.
    """
    members: dict[int, list[Mapping[int, float]]] = {}
    for weight in weights:
        # A passage that gained its first fact during the fit was scored but
        # never weighed: it has no vector, and it is left out of the measure.
        if weight.passage_id in vectors:
            members.setdefault(weight.topic_index, []).append(
                vectors[weight.passage_id]
            )
    means = []
    for held in members.values():
        if len(held) < 2:
            continue
        # The sum of every pair's cosine, from the length of the members' sum:
        # |sum u|^2 counts each pair twice beside each member's own length.
        summed: dict[int, float] = {}
        for vector in held:
            for term, value in vector.items():
                summed[term] = summed.get(term, 0.0) + value
        together = sum(value * value for value in summed.values())
        alone = sum(value * value for vector in held for value in vector.values())
        means.append((together - alone) / (len(held) * (len(held) - 1)))
    return sum(means) / len(means) if means else 0.0


def dominant(weights: Iterable[PassageWeight]) -> dict[int, int]:
    """Each passage's strongest topic, by index.

    A tie goes to the lower index, as the store's `DOMINANT` breaks one on
    the topic id, which a fit numbers in index order.
    """
    strongest: dict[int, PassageWeight] = {}
    for weight in weights:
        held = strongest.get(weight.passage_id)
        if held is None or (weight.weight, -weight.topic_index) > (
            held.weight,
            -held.topic_index,
        ):
            strongest[weight.passage_id] = weight
    return {passage: one.topic_index for passage, one in strongest.items()}


def carry_labels(
    fitted: list[FittedTopic],
    previous: list[FittedTopic],
    *,
    before: Mapping[int, int],
    after: Mapping[int, int],
) -> tuple[list[FittedTopic], int]:
    """Re-attaches what a person decided about the previous fit's topics.

    An old topic and a new one are the same topic when each holds more than
    half of the other's dominant passages: all of the old topic's, so one
    passage left of many cannot carry it onto a topic of passages new to the
    corpus, and the new topic's among the passages both fits hold, so a
    topic grown by new passages still matches. Two topics cannot both hold
    more than half of one, so a decision has at most one match and none is
    used twice. The coverage
    choice and the decision time travel; the label and what named it travel
    only when a person named it, since a model's name is given again to
    the new topic with the rest of the fit's.

    Args:
        fitted: The topics this run produced.
        previous: The topics a person said something about.
        before: Each passage's dominant topic index in the fit being
            replaced.
        after: Each passage's dominant topic index in this one.

    Returns:
        `fitted`, each topic carrying the decision it matched or none, and
        how many decisions matched no topic.
    """
    common = before.keys() & after.keys()
    old = Counter(before.values())
    new = Counter(after[one] for one in common)
    shared = Counter((before[one], after[one]) for one in common)
    same = {
        now: was
        for (was, now), held in shared.items()
        if 2 * held > old[was] and 2 * held > new[now]
    }
    decisions = {one.topic_index: one for one in previous}
    carried: list[FittedTopic] = []
    for topic in fitted:
        was = same.get(topic.topic_index)
        decision = None if was is None else decisions.pop(was, None)
        if decision is None:
            carried.append(topic)
            continue
        person = decision.labelled_by == "person"
        carried.append(
            replace(
                topic,
                label=decision.label if person else topic.label,
                labelled_by=decision.labelled_by if person else topic.labelled_by,
                include_in_coverage=decision.include_in_coverage,
                decided_at=decision.decided_at,
            )
        )
    for lost in decisions.values():
        log.warning(
            "the decision on topic %r (in coverage: %s; terms %s) matched no "
            "topic holding most of its passages; set it again",
            lost.label,
            lost.include_in_coverage,
            ", ".join(lost.top_terms[:5]),
        )
    return carried, len(decisions)
