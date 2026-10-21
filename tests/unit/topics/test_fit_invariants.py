"""What every fit holds, whatever corpus it is over.

Each passage is placed or named unplaced, once; no number in the fitted space
is NaN; weights sit in the documented ranges; and the same passages read in
the same order give the same fit in every process.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import event, given
from hypothesis import strategies as hs
from synth_topics import DEFAULTS
from synth_topics import corpus as synthetic
from topic_drivers import LabellerDriver, ServiceDriver, corpus

from topic_modelling.models import Fitting, PassageVocabulary
from topic_modelling.space import load
from topic_modelling.topics import NoVocabulary, TopicFitter, dominant

#: Lemmas as chunking stores them: ASCII, umlauts, a ligature-free sharp s,
#: CJK and an accented Romance word, so no term is assumed to be ASCII.
_WORDS = [
    "konto",
    "karte",
    "gebühr",
    "straße",
    "lieferung",
    "rücksendung",
    "fee",
    "card",
    "refund",
    "frais",
    "remboursement",
    "銀行",
    "口座",
]


def _fit(passages: list[PassageVocabulary], language: str = "de") -> Fitting:
    """Fits under the shipped settings."""
    return TopicFitter(**DEFAULTS).fit(lambda: iter(passages), language)


def _holds_every_invariant(passages: list[PassageVocabulary], fitting: Fitting) -> None:
    """The fitted space and the memberships say what the models document."""
    ids = {one.id for one in passages}
    placed = {weight.passage_id for weight in fitting.weights}
    # Every passage scored once: placed, or named for the store to place.
    assert placed | set(fitting.unplaced) == ids
    assert not placed & set(fitting.unplaced)
    assert len(fitting.unplaced) == len(set(fitting.unplaced)) == fitting.without_topics
    assert fitting.passages == len(passages)

    floor = DEFAULTS["min_weight"]
    sums: dict[int, float] = {}
    for weight in fitting.weights:
        assert floor < weight.weight <= 1.0
        assert 0 <= weight.topic_index < len(fitting.topics)
        sums[weight.passage_id] = sums.get(weight.passage_id, 0.0) + weight.weight
    assert all(total <= 1.0 + 1e-9 for total in sums.values())
    pairs = [(w.passage_id, w.topic_index) for w in fitting.weights]
    assert len(pairs) == len(set(pairs))

    space = fitting.space
    numbers = [x for row in space.topic_term + space.doc_topic for x in row]
    assert all(math.isfinite(x) for x in numbers)
    assert len(space.topic_term) == len(fitting.topics)
    for row in space.topic_term:
        assert len(row) == len(space.vocabulary)
        assert math.isclose(sum(row), 1.0, abs_tol=1e-6)
    for row in space.doc_topic:
        assert len(row) == len(fitting.topics)
        assert math.isclose(sum(row), 1.0, abs_tol=1e-6)
    assert len(space.doc_topic) == len(space.doc_lengths)
    assert len(space.term_frequency) == len(space.vocabulary) == fitting.vocabulary
    assert len(set(space.vocabulary)) == len(space.vocabulary)
    for topic in fitting.topics:
        assert 1 <= len(topic.top_terms) <= DEFAULTS["top_terms"]
        assert set(topic.top_terms) <= set(space.vocabulary)


_PASSAGE = hs.lists(hs.sampled_from(_WORDS), max_size=8)


@given(texts=hs.lists(_PASSAGE, min_size=1, max_size=30))
def test_any_small_corpus_is_fitted_whole_or_refused_by_name(texts) -> None:
    """A fit places each passage once and holds no NaN, or says why it cannot fit."""
    passages = [PassageVocabulary(i + 1, list(t)) for i, t in enumerate(texts)]

    try:
        fitting = _fit(passages)
    except NoVocabulary:
        # Only a corpus with nothing to read or nothing to tell apart.
        event("refused")
        return

    event(f"{len(fitting.topics)} topic(s)")
    _holds_every_invariant(passages, fitting)


@given(
    copies=hs.integers(1, 120),
    lemmas=hs.lists(hs.sampled_from(_WORDS), min_size=1, max_size=6),
)
def test_copies_of_one_text_are_one_topic_holding_each_copy_wholly(
    copies, lemmas
) -> None:
    """However many copies, each holds the one topic with weight 1."""
    passages = [PassageVocabulary(i + 1, list(lemmas)) for i in range(copies)]

    fitting = _fit(passages)

    assert len(fitting.topics) == 1
    assert sorted((w.passage_id, w.weight) for w in fitting.weights) == [
        (i + 1, 1.0) for i in range(copies)
    ]
    _holds_every_invariant(passages, fitting)


@pytest.mark.parametrize(
    ("domain", "language", "size"),
    [("bank", "de", 400), ("bank", "en", 7), ("shop", "de", 2), ("shop", "en", 250)],
)
def test_a_synthetic_language_of_any_size_holds_every_invariant(
    domain, language, size
) -> None:
    """Bank and shop corpora, tiny to large, in both languages."""
    passages = synthetic(domain, language, size, seed=11)

    _holds_every_invariant(passages, _fit(passages, language))


def test_the_same_passages_under_other_ids_in_the_same_order_fit_alike() -> None:
    """An id is a label: renumbering keeps every topic and membership."""
    passages = synthetic("bank", "en", 200, seed=7)
    moved = [PassageVocabulary(one.id + 5_000, one.lemmas) for one in passages]

    first, second = _fit(passages), _fit(moved)

    assert [t.top_terms for t in first.topics] == [t.top_terms for t in second.topics]
    assert [(w.passage_id + 5_000, w.topic_index, w.weight) for w in first.weights] == [
        (w.passage_id, w.topic_index, w.weight) for w in second.weights
    ]


#: Fits two corpora and prints them, in a fresh interpreter.
_SCRIPT = """
import json, sys
sys.path[:0] = sys.argv[1:]
from synth_topics import DEFAULTS, corpus
from topic_modelling.models import PassageVocabulary
from topic_modelling.topics import TopicFitter
out = []
for passages in (
    corpus("shop", "de", 120, seed=3),
    [PassageVocabulary(i, ["zins", "kredit", "kredit"]) for i in range(1, 4)],
):
    fit = TopicFitter(**DEFAULTS).fit(lambda: iter(passages), "de")
    out.append([[t.top_terms for t in fit.topics],
                [[w.passage_id, w.topic_index, w.weight] for w in fit.weights],
                fit.space.vocabulary])
print(json.dumps(out))
"""


def test_the_same_corpus_gives_the_same_fit_under_any_hash_seed() -> None:
    """A rebuild is another process: string hashing must not decide a topic."""
    root = Path(__file__).resolve().parents[3]
    paths = [str(root / "backend"), str(root), str(Path(__file__).parent)]

    def run(seed: str) -> str:
        env = os.environ | {"PYTHONHASHSEED": seed}
        done = subprocess.run(
            [sys.executable, "-c", _SCRIPT, *paths],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        return done.stdout

    first, second = run("1"), run("2")

    assert json.loads(first) == json.loads(second)


def test_the_same_passages_read_in_the_same_order_fall_into_the_same_topics() -> None:
    """What the README promises, and only that.

    The fit follows the order it reads passages in, by id in the store: a
    document deleted and chunked again comes back under higher ids, is read
    last, and can regroup other documents' passages. Every refit after reads
    that same order, and gives the same topics.
    """
    passages = synthetic("bank", "en", 200, seed=7)
    # The first document's 20 passages, chunked again: same lemmas, new ids, read last.
    rechunked = passages[20:] + [
        PassageVocabulary(one.id + 1_000, one.lemmas) for one in passages[:20]
    ]

    first, second = _fit(rechunked, "en"), _fit(list(rechunked), "en")

    assert [t.top_terms for t in first.topics] == [t.top_terms for t in second.topics]
    assert first.weights == second.weights
    assert first.unplaced == second.unplaced


def test_a_tiny_a_huge_and_a_third_language_are_fitted_named_and_kept_side_by_side() -> (
    None
):
    """One stray English passage and five French ones beside 400 German.

    French has no TOPIC_LANGUAGE_NAMES row, so its prompt names it by code;
    each language still gets its own topics, names, figure and model.
    """
    french = [
        "frais carte bancaire annuel",
        "frais carte bancaire retrait",
        "virement étranger devise iban",
        "virement étranger devise sepa",
        "compte épargne ouverture solde",
    ]
    labeller = LabellerDriver(
        *(f"Thema {i}" for i in range(1, 200)),
        languages={"de": "German", "en": "English"},
    )
    driver = ServiceDriver(
        settings=DEFAULTS,
        corpora={
            "de": synthetic("bank", "de", 400, seed=2),
            "en": corpus("deposit guarantee scheme protects savings", first_id=5_001),
            "fr": corpus(*french, first_id=6_001),
        },
        labeller=labeller,
    )

    driver.request_and_run()

    assert driver.failure is None
    assert sorted(driver.languages_stored) == ["de", "en", "fr"]
    assert len(driver.topics_of("en")) == 1
    asked = [str(call["user"]) for call in labeller.model.asked]
    assert sum(text.startswith("Language: fr\n") for text in asked) == 1
    assert sum(text.startswith("Language: German\n") for text in asked) == 1
    assert sorted(driver.figures) == ["de", "en", "fr"]
    for fitting in driver.stored:
        held = set(dominant(fitting.weights).values())
        assert all(t.label for t in fitting.topics if t.topic_index in held)
        space = load(driver.models.models[f"topics/{fitting.language}.npz"])
        assert space.vocabulary == fitting.space.vocabulary
        assert all(
            math.isfinite(x) for row in space.topic_term + space.doc_topic for x in row
        )
