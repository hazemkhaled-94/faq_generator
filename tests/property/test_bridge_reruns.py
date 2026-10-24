"""What a bridge pass leaves stored, for any corpus and any run of passes before it.

`tests/property/test_bridge_scope.py` holds the queries to their meaning on a
database; this holds `service.bridge` to it over a store that keeps what the
queries mean: a pass narrowed to some topics clears the bridges headed there,
a pass for the missing clears nothing and skips the topics holding one, and no
pass offers a pair a stored bridge already rests on.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from drivers import DIGEST_SHARE, Catalogue, Model, passage
from hypothesis import given
from hypothesis import strategies as st

from extraction.extractors.bridge import BridgeExtractor
from extraction.service import bridge
from extraction.validation import FactChecker

pytestmark = pytest.mark.nlp

ANSWER = {
    "relation": "contrast",
    "facts": [{"excerpt": 0, "fact": 0}, {"excerpt": 1, "fact": 0}],
    "statement": "A transfer costs less than a card.",
    "question": "Which costs less, a transfer or a card?",
    "answer": "a transfer",
}

_PARENTS = ("Fees", "Cards", "Returns")


class Store(Catalogue):
    """An in-memory catalogue whose bridges stay stored between passes.

    `within` is the set of topic ids a pass is narrowed to, standing in for
    the SQL condition the repository takes.
    """

    def __init__(self, **topics) -> None:
        super().__init__(**topics)
        self.topic_of = {
            one.id: topic
            for topic, ones in enumerate(self._topics, start=1)
            for one in ones
        }
        self.bridges: list[tuple[tuple[int, ...], int]] = []

    def by_topic(self, within=None):
        """Streams each topic's passages, recording the scope asked for."""
        self.narrowed.append(within)
        for topic, ones in enumerate(self._topics, start=1):
            if within is None or topic in within:
                yield topic, ones

    def _in(self, head: int, within) -> bool:
        return within is None or self.topic_of[head] in within

    def clear_bridges(self, within=None) -> int:
        """Deletes the bridges headed in scope, as the repository does."""
        kept = [one for one in self.bridges if not self._in(one[1], within)]
        cleared, self.bridges = len(self.bridges) - len(kept), kept
        return cleared

    def bridged_topics(self, within=None) -> frozenset[int]:
        """The topics in scope whose passages head a stored bridge."""
        return frozenset(
            self.topic_of[head] for _, head in self.bridges if self._in(head, within)
        )

    def bridged_pairs(
        self, within=None, replaced: bool = False
    ) -> frozenset[frozenset[int]]:
        """The passage pairs a stored bridge links, less those a clear would delete."""
        return frozenset(
            frozenset(rests[:2])
            for rests, head in self.bridges
            if not (replaced and self._in(head, within))
        )

    def add_bridges(self, facts) -> int:
        """Stores each bridge under the passage that headed its link."""
        for fact in facts:
            rests = tuple(one.passage_id for one in fact.citations)
            head = (fact.bridge or {}).get("head", rests[0])
            self.bridges.append((rests, head))
        return len(facts)

    @property
    def held(self) -> list[tuple[frozenset[int], int]]:
        """What is stored, as each bridge's pair and head, sorted."""
        return sorted(
            ((frozenset(rests[:2]), head) for rests, head in self.bridges),
            key=lambda one: (sorted(one[0]), one[1]),
        )


@st.composite
def corpora(draw):
    """Passages under a few parent headings, some naming another's, over two or three topics."""
    count = draw(st.integers(2, 7))
    topics = draw(st.integers(2, 3))
    placed = [
        (
            draw(st.sampled_from(_PARENTS)),
            draw(st.integers(1, topics)),
            draw(st.none() | st.integers(1, count)),
        )
        for _ in range(count)
    ]
    by_topic: dict[int, list] = {topic: [] for topic in range(1, topics + 1)}
    for i, (parent, topic, names) in enumerate(placed, start=1):
        # A passage naming another's heading links to it as a reference.
        named = f" Its terms are set out in Section {names}." if names else ""
        by_topic[topic].append(
            replace(
                passage(
                    f"Item {i} costs {i} EUR a month.{named}",
                    section_path=f"{parent} > Section {i}",
                    id=i,
                ),
                doc_sha256="doc-a",
            )
        )
    return {f"t{topic}": ones for topic, ones in by_topic.items()}


#: A pass: whole, narrowed to one topic, or for the missing.
PASSES = st.lists(
    st.one_of(
        st.just(("whole", None)),
        st.just(("missing", None)),
        st.integers(1, 3).map(lambda topic: ("scoped", frozenset({topic}))),
    ),
    max_size=4,
)


def run(store: Store, how: str, within, wanted: int) -> None:
    """Runs one bridge pass, whole, narrowed or missing."""
    bridge(
        store,  # type: ignore[arg-type]
        BridgeExtractor(Model(ANSWER)),  # type: ignore[arg-type]
        FactChecker(DIGEST_SHARE),
        wanted,
        2,
        within,
        missing=how == "missing",
    )


def fresh(topics, wanted: int) -> Store:
    """A store holding the corpus's stated facts and no bridge yet."""
    store = Store(**topics)
    store.stating()
    return store


@given(topics=corpora(), history=PASSES, wanted=st.integers(1, 3))
def test_no_pair_ever_holds_two_bridges(topics, history, wanted) -> None:
    """Whatever passes ran, in whatever order, a pair carries one bridge at most."""
    store = fresh(topics, wanted)
    for how, within in history:
        run(store, how, within, wanted)
        pairs = [pair for pair, _ in store.held]
        assert len(pairs) == len(set(pairs)), (how, within, store.held)


_TWICE = (
    "QA-extraction-9: a pass for the missing, run twice, can add a bridge the first "
    "run left out, when a topic's only pair rests on a bridge headed in another "
    "topic; the first run counts the pair as held, the second finds the topic "
    "missing one"
)


@pytest.mark.xfail(strict=False, reason=_TWICE)
@given(
    topics=corpora(),
    history=PASSES,
    again=st.sampled_from(["whole", "missing", "scoped"]),
    topic=st.integers(1, 3),
    wanted=st.integers(1, 3),
)
def test_a_pass_run_twice_leaves_what_it_left_once(
    topics, history, again, topic, wanted
) -> None:
    """Re-running a pass writes back exactly what it cleared: the store stays put."""
    store = fresh(topics, wanted)
    for how, within in history:
        run(store, how, within, wanted)
    within = frozenset({topic}) if again == "scoped" else None
    run(store, again, within, wanted)
    once = store.held
    run(store, again, within, wanted)

    assert store.held == once


@given(topics=corpora(), history=PASSES, wanted=st.integers(1, 3))
def test_a_whole_pass_forgets_every_pass_before_it(topics, history, wanted) -> None:
    """A whole pass replaces everything, so what came before cannot show."""
    clean = fresh(topics, wanted)
    run(clean, "whole", None, wanted)
    store = fresh(topics, wanted)
    for how, within in history:
        run(store, how, within, wanted)
    run(store, "whole", None, wanted)

    assert store.held == clean.held


def _placed(i: int, topic_names: str | None = None):
    """Passage i under Fees, naming another's section when asked."""
    named = f" Its terms are set out in Section {topic_names}." if topic_names else ""
    return replace(
        passage(
            f"Item {i} costs {i} EUR a month.{named}",
            section_path=f"Fees > Section {i}",
            id=i,
        ),
        doc_sha256="doc-a",
    )


@pytest.mark.xfail(strict=True, reason=_TWICE)
def test_a_pass_for_the_missing_run_twice_adds_nothing() -> None:
    """Two topics, one passage of the second naming a section of the first.

    The case CI's property run found: the first pass for the missing bridges
    passages 1 and 2 under the first topic; the second finds the second topic
    holding no bridge headed there and bridges passages 2 and 3.
    """
    topics = {"t1": [_placed(1), _placed(3)], "t2": [_placed(2, "3")]}
    store = fresh(topics, 1)
    run(store, "missing", None, 1)
    once = store.held
    run(store, "missing", None, 1)

    assert store.held == once
