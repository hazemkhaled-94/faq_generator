"""A corpus ten times this build's: more topics than 40 a language, all named.

At the go-live size one language holds about 10,000 passages. A ceiling of 40
topics left a topic worth 250 passages and a slot count that stopped growing,
and one naming call over hundreds of topics is a prompt no model reads.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from topic_drivers import LabellerDriver, ServiceDriver, corpus

from llm.client import ModelUnavailable
from topic_modelling.labels import TopicLabeller
from topic_modelling.models import FittedTopic
from topic_modelling.topics import TopicFitter, dominant

ROOT = Path(__file__).resolve().parents[3]


def _shipped(name: str) -> int:
    """What configs/env/backend.env ships a setting as."""
    found = re.search(
        rf"^{name}=(\d+)$", (ROOT / "configs/env/backend.env").read_text(), re.MULTILINE
    )
    assert found, name
    return int(found[1])


def _topics(count: int) -> list[tuple[FittedTopic, list[str]]]:
    """`count` topics, each with terms and an excerpt of its own."""
    return [
        (FittedTopic(index, [f"term{index}a", f"term{index}b"]), [f"Text {index}."])
        for index in range(count)
    ]


class Scripted:
    """A served model naming every topic it is shown, as the labeller reads one."""

    model = "test-model"

    def __init__(self, refuses=lambda asked, call: False) -> None:
        self.asked: list[str] = []
        self._refuses = refuses

    def answer(self, **kwargs):
        """Names what it was shown, or refuses as the test says."""
        user = str(kwargs["user"])
        shown = [int(n) for n in re.findall(r"^Topic (\d+)$", user, re.MULTILINE)]
        self.asked.append(user)
        if self._refuses(shown, len(self.asked)):
            raise ModelUnavailable("too long")
        labels = [
            type("N", (), {"topic": n, "label": f"Name {n}", "no_subject": False})()
            for n in shown
        ]
        return type("A", (), {"labels": labels})()


@pytest.mark.parametrize("language", ["de", "en", "fr"])
def test_a_language_s_topics_are_named_in_batches_of_a_fixed_size(language) -> None:
    """Sixty topics are three calls, and every one is named.

    The language is any code: a batch is a count of topics, not a reading of
    their words.
    """
    model = Scripted()
    labeller = TopicLabeller(model, {"de": "German", "en": "English"})

    named = labeller.label_all(_topics(60), language)

    assert sorted(named) == list(range(60))
    assert len(model.asked) == 3
    shown = [re.findall(r"^Topic (\d+)$", user, re.MULTILINE) for user in model.asked]
    assert [len(one) for one in shown] == [25, 25, 10]


def test_each_batch_carries_the_names_already_given() -> None:
    """So a later batch cannot take a name an earlier one did."""
    model = Scripted()

    TopicLabeller(model, {"en": "English"}).label_all(_topics(60), "en")

    assert "Names already taken" not in model.asked[0]
    assert "Name 0" in model.asked[1] and "Name 24" in model.asked[1]
    assert "Name 49" in model.asked[2]


def test_a_set_of_one_batch_is_one_call() -> None:
    """The 20 or 21 topics of this build are named as they were."""
    model = Scripted()

    TopicLabeller(model, {"en": "English"}).label_all(_topics(21), "en")

    assert len(model.asked) == 1


def test_a_batch_the_model_refuses_is_split_once_and_each_half_asked() -> None:
    """A model that cannot read 25 topics at once can read 13."""
    model = Scripted(refuses=lambda shown, call: len(shown) > 13)

    named = TopicLabeller(model, {"en": "English"}).label_all(_topics(25), "en")

    assert sorted(named) == list(range(25))
    assert len(model.asked) == 3


def test_a_half_that_is_refused_again_is_left_unnamed_and_the_rest_named() -> None:
    """Split once, not down to one topic a call."""
    model = Scripted(refuses=lambda shown, call: len(shown) > 12)

    named = TopicLabeller(model, {"en": "English"}).label_all(_topics(25), "en")

    assert sorted(named) == list(range(13, 25))
    assert len(model.asked) == 3


def test_one_batch_refused_leaves_the_others_named() -> None:
    """The second of three is refused throughout; the first and third are named."""
    model = Scripted(refuses=lambda shown, call: 25 in shown or 30 in shown)

    named = TopicLabeller(model, {"en": "English"}).label_all(_topics(60), "en")

    assert set(range(25)) <= set(named)
    assert set(range(50, 60)) <= set(named)
    assert not set(range(25, 50)) <= set(named)


def test_the_ceiling_follows_a_corpus_ten_times_this_one() -> None:
    """10,000 passages of a language are 250 topics, where 40 was the ceiling."""
    fitter = TopicFitter(
        num_topics=_shipped("TOPIC_NUM_TOPICS"),
        passes=1,
        random_state=1,
        top_terms=5,
        relative_weight=0.5,
        no_below=2,
        no_above=0.9,
        passages_per_topic=_shipped("TOPIC_PASSAGES_PER_TOPIC"),
    )

    assert fitter._count(10_000) > 40
    assert fitter._count(10_000) == 10_000 // _shipped("TOPIC_PASSAGES_PER_TOPIC")
    assert fitter._count(1_000) == 25, "a corpus of this build's size is unchanged"


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_fit_above_the_old_ceiling_names_every_topic(language) -> None:
    """120 subjects of 5 passages each: 120 topics, named in five calls."""
    passages = corpus(
        *(
            " ".join(f"s{subject}w{word}" for word in range(10))
            for subject in range(120)
            for _ in range(5)
        )
    )
    labeller = LabellerDriver(
        *[f"Name {i}" for i in range(400)], languages={language: language}
    )
    flow = ServiceDriver(
        settings={
            "num_topics": _shipped("TOPIC_NUM_TOPICS"),
            "passes": 3,
            "random_state": 42,
            "top_terms": 5,
            "relative_weight": 0.5,
            "no_below": 2,
            "no_above": 0.5,
            "passages_per_topic": 5,
        },
        corpora={language: passages},
        texts={one.id: f"Passage {one.id}." for one in passages},
        labeller=labeller,
    )
    flow.queue.bearing = {one.id for one in passages}

    flow.request_and_run()

    fitting = flow.stored[0]
    topics = fitting.topics
    held = set(dominant(fitting.weights).values())
    assert len(topics) > 40
    assert all(topic.label for topic in topics if topic.topic_index in held)
    assert labeller.model.calls == -(-len(held) // 25)
