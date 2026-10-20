"""What a topic's deal hands a compound or an unanswerable slot, for any topic.

A bridge is one claim resting on two passages. A compound question asks about
two passages nobody relates, and an unanswerable one moves a single claim of a
single passage out of reach, so neither is ever written from a bridge: the
bridge waits for a slot that may rest on it. These hold that for every
arrangement of passages, plain claims and bridges the strategy can build,
rather than for the few the example tests name.
"""

from __future__ import annotations

import pytest
from factories import bridge, resting, source
from hypothesis import given
from hypothesis import strategies as st

from question_generation.selection import Deal, Shape

pytestmark = pytest.mark.nlp

LEMMAS = st.lists(st.sampled_from("abcdefgh"), max_size=4, unique=True).map(tuple)


@st.composite
def topics(draw):
    """Plain claims and bridges over a handful of passages in a few documents.

    Returns the topic's own facts and the facts of the passages other topics'
    bridges reach, as `Deal` takes them.
    """
    passages = draw(st.integers(1, 6))
    document = {
        p: draw(st.sampled_from(["doc-a", "doc-b", "doc-c"]))
        for p in range(1, passages + 1)
    }
    lemmas = {p: draw(LEMMAS) for p in document}
    own: list = []
    foreign: list = []
    fact_id = 0
    for passage, home in document.items():
        for _ in range(draw(st.integers(1, 3))):
            fact_id += 1
            spans = draw(st.booleans())
            kw = {
                "fact_id": fact_id,
                "passage_id": passage,
                "document": home,
                "lemmas": lemmas[passage],
                "statement": f"Claim {fact_id} costs {fact_id} EUR.",
            }
            if spans:
                fact = bridge(resting(passage + 10, document="doc-z"), **kw)
            else:
                fact = source(**kw)
            (foreign if draw(st.integers(0, 4)) == 0 else own).append(fact)
    return own, foreign


def _spans(fact) -> bool:
    return len(fact.passages) > 1


def _drain(deal, shape, prefer=None):
    """Every sample the deal gives in `shape`, until it says none is left."""
    samples = []
    for _ in range(60):
        sample = deal.sample(shape, prefer=prefer)
        if sample is None:
            return samples
        samples.append(sample)
    raise AssertionError("the deal never ran out")


@given(topic=topics(), size=st.integers(1, 4), rounds=st.integers(1, 3))
def test_a_compound_sample_never_holds_a_fact_resting_on_two_passages(
    topic, size, rounds
) -> None:
    """Whatever else is in the topic, a bridge is not dealt to a compound slot."""
    own, foreign = topic
    deal = Deal(own, foreign, wanted=10, size=size, rounds=rounds)

    for sample in _drain(deal, Shape.APART):
        assert not any(_spans(fact) for fact in sample.facts), [
            fact.id for fact in sample.facts
        ]


@given(
    topic=topics(),
    shape=st.sampled_from([Shape.SINGLE, Shape.CROSS, Shape.BRIDGE, Shape.APART]),
    size=st.integers(1, 4),
)
def test_a_slot_that_prefers_one_passage_facts_is_dealt_no_bridge_in_any_shape(
    topic, shape, size
) -> None:
    """An unanswerable slot prefers claims of one passage, in whatever shape the plan gave it."""
    own, foreign = topic
    deal = Deal(own, foreign, wanted=10, size=size)

    for sample in _drain(deal, shape, prefer=lambda fact: not _spans(fact)):
        assert not any(_spans(fact) for fact in sample.facts), (
            shape,
            [fact.id for fact in sample.facts],
        )


@given(topic=topics(), size=st.integers(1, 4))
def test_a_compound_slot_is_exhausted_exactly_when_no_plain_claim_is_left(
    topic, size
) -> None:
    """A compound deal gives up only when the claims of one passage are all spent."""
    own, foreign = topic
    deal = Deal(own, foreign, wanted=10, size=size, rounds=10)

    dealt = {fact.id for sample in _drain(deal, Shape.APART) for fact in sample.facts}

    plain_of_own_topic = {fact.id for fact in own if not _spans(fact)}
    assert plain_of_own_topic <= dealt, "a plain claim of the topic was left undealt"
    assert deal.holds(lambda fact: not _spans(fact)) is False


@given(topic=topics(), size=st.integers(1, 4))
def test_holds_agrees_with_what_sample_would_deal_first(topic, size) -> None:
    """Asking whether a preferred fact is left spends nothing and never contradicts the deal."""
    own, foreign = topic
    deal = Deal(own, foreign, wanted=10, size=size)

    def prefer(fact) -> bool:
        return not _spans(fact)

    asked = deal.holds(prefer)
    again = deal.holds(prefer)
    sample = deal.sample(Shape.SINGLE, prefer=prefer)

    assert asked == again
    assert asked == (sample is not None)
