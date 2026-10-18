"""Fitting a topic model over one language's vocabulary."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import replace
from itertools import batched
from typing import cast

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
        min_weight: float,
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
            min_weight: Smallest membership weight kept, in (0, 1).
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
        if not 0 < min_weight < 1:
            raise ValueError(
                f"TOPIC_MIN_WEIGHT={min_weight} is not a probability floor; it "
                "must be above 0 and below 1, since a membership is kept only "
                "above it"
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
        self._min_weight = min_weight
        self._no_below = no_below
        self._no_above = no_above
        self._passages_per_topic = passages_per_topic

    def fit(self, corpus: Corpus, language: str) -> Fitting:
        """Fits one language's model and scores its passages against it.

        The corpus is walked rather than held: once to build the vocabulary,
        once per pass, and once more to score.

        Args:
            corpus: Hands back a fresh walk over the passages each time it is
                called.
            language: The ISO 639-1 code the fit is recorded against.

        Returns:
            The topics, the memberships above the weight floor, and the whole
            fitted space.

        Raises:
            NoVocabulary: If the corpus is empty, if the frequency filter left
                no terms, if a second walk yields nothing, or if tf-idf weighs
                every term zero.
        """
        dictionary = corpora.Dictionary()
        counted = 0
        for batch in batched((p.lemmas for p in corpus()), _BATCH):
            dictionary.add_documents(batch, prune_at=None)  # pyright: ignore[reportArgumentType]
            counted += len(batch)

        if not counted:
            raise NoVocabulary(
                f"there are no {language} passages to fit a topic model over"
            )

        before = len(dictionary)
        dictionary.filter_extremes(
            no_below=self._no_below,
            no_above=self._no_above,
            keep_n=None,  # pyright: ignore[reportArgumentType]
        )
        if not dictionary:
            raise NoVocabulary(
                f"the frequency filter left no terms: {before} were found across "
                f"{counted} passage(s), and none appears in at least "
                f"{self._no_below} of them and at most {self._no_above:.0%}"
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
        model = Nmf(
            corpus=weighting[bows],
            id2word=dictionary,
            num_topics=wanted,
            passes=self._passes,
            random_state=self._random_state,
        )

        weights, unplaced, space = self._score(model, corpus, dictionary, weighting)
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
            The memberships above the weight floor, the passages holding
            none, and the space the visualisation is drawn from.
        """
        weights: list[PassageWeight] = []
        doc_topic: list[list[float]] = []
        doc_lengths: list[int] = []
        without: list[int] = []
        for passage in corpus():
            bow = cast("list[tuple[int, int]]", dictionary.doc2bow(passage.lemmas))
            found = model.get_document_topics(weighting[bow], minimum_probability=0)
            if found:
                row = [0.0] * model.num_topics
                for index, weight in found:
                    row[int(index)] = float(weight)
                total = sum(row)
                doc_topic.append([value / total for value in row])
                doc_lengths.append(sum(count for _, count in bow))

            kept = [
                (index, weight) for index, weight in found if weight > self._min_weight
            ]
            # Counts both a passage holding none of the vocabulary and one
            # whose every weight fell below the floor.
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
        if without:
            log.warning(
                "%d passage(s) came out with no topic; each goes to the topic "
                "whose centroid is nearest, where it has a vector",
                len(without),
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
