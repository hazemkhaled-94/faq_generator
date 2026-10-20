"""The edges of what a compound or unanswerable slot is dealt.

`test_selection.py` holds the cases a slot is built from. These hold what a
neighbouring mutation would change: the caller's own preference carried into a
compound sample, a bridge dealt alone under every wide shape, a partner found
only among the passages of other topics' bridges, and `holds`.
"""

from __future__ import annotations

import pytest
from factories import bridge, resting, source

from question_generation.selection import Deal, Shape

pytestmark = pytest.mark.nlp

_TEXTS = {
    "en": {
        "mentions": "The account fee is 5 euros a month.",
        "plain": "Standard delivery takes 3 to 5 working days.",
        "far": "Gift wrapping costs 3 euros.",
        "span": "The return period starts on the day the delivery arrives.",
    },
    "de": {
        "mentions": "Die Kontogebühr beträgt 5 Euro im Monat.",
        "plain": "Die Standardlieferung dauert 3 bis 5 Werktage.",
        "far": "Die Geschenkverpackung kostet 3 Euro.",
        "span": "Die Rückgabefrist beginnt am Tag der Lieferung.",
    },
}


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_compound_slot_keeps_the_preference_of_the_caller(language) -> None:
    """A slot that wants a kind of fact is dealt a head that has it, compound or not."""
    t = _TEXTS[language]
    kw = {"language": language, "document": "doc-a"}
    first = source(1, passage_id=1, statement=t["plain"], lemmas=("one",), **kw)
    wanted = source(2, passage_id=2, statement=t["mentions"], lemmas=("two",), **kw)
    deal = Deal([first, wanted], wanted=4, size=2)

    sample = deal.sample(Shape.APART, prefer=lambda fact: "uro" in fact.statement)

    assert sample is not None
    assert sample.facts[0].id == 2, "the head is the passage holding what was preferred"


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("shape", [Shape.BRIDGE, Shape.CROSS])
def test_a_bridge_is_dealt_alone_under_every_wide_shape(language, shape) -> None:
    """It spans two passages by itself, so no third is put beside it."""
    t = _TEXTS[language]
    kw = {"language": language, "lemmas": ("delivery", "return")}
    spanning = bridge(
        resting(5, document="doc-b", language=language),
        fact_id=1,
        passage_id=1,
        document="doc-a",
        statement=t["span"],
        **kw,
    )
    other = source(2, passage_id=2, document="doc-c", statement=t["far"], **kw)
    # A partner a wide shape would pair it with: another document, shared terms.
    sample = Deal([spanning, other], [other], wanted=4, size=3).sample(
        shape, prefer=lambda fact: fact.spans
    )

    assert sample is not None
    assert [fact.id for fact in sample.facts] == [1]


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_wide_shape_pairs_a_plain_head_with_a_second_passage(language) -> None:
    """The other side of the test above: it is the bridge that stops the pairing."""
    t = _TEXTS[language]
    kw = {"language": language, "lemmas": ("delivery", "return")}
    head = source(1, passage_id=1, document="doc-a", statement=t["plain"], **kw)
    other = source(2, passage_id=2, document="doc-c", statement=t["far"], **kw)

    sample = Deal([head, other], wanted=4, size=3).sample(Shape.CROSS)

    assert sample is not None
    assert {fact.passage_id for fact in sample.facts} == {1, 2}


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_sample_offers_single_claims_before_a_summary_unless_asked_otherwise(
    language,
) -> None:
    """`condensed` is off by default: the passage's own claim leads, not its summary."""
    from database.qa_generator import FactKind

    t = _TEXTS[language]
    claim = source(1, passage_id=1, statement=t["plain"], language=language)
    summary = source(
        2, passage_id=1, statement=t["far"], language=language, kind=FactKind.SUMMARY
    )

    plain = Deal([summary, claim], wanted=1, size=1).sample(Shape.SINGLE)
    condensed = Deal([summary, claim], wanted=1, size=1).sample(
        Shape.SINGLE, condensed=True
    )

    assert plain is not None and condensed is not None
    assert [fact.id for fact in plain.facts] == [1]
    assert [fact.id for fact in condensed.facts] == [2]


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_compound_partner_may_be_a_passage_only_another_topics_bridge_reaches(
    language,
) -> None:
    """The partner is looked for among those passages too, claims of its own required."""
    t = _TEXTS[language]
    kw = {"language": language, "document": "doc-a"}
    head = source(1, passage_id=1, statement=t["plain"], lemmas=("one", "shared"), **kw)
    reached = source(
        2,
        passage_id=2,
        statement=t["far"],
        lemmas=("two",),
        **{**kw, "document": "doc-b"},
    )
    deal = Deal([head], [reached], wanted=4, size=2)

    sample = deal.sample(Shape.APART)

    assert sample is not None
    assert {fact.passage_id for fact in sample.facts} == {1, 2}


@pytest.mark.parametrize("language", ["en", "de"])
def test_holds_says_whether_a_passage_left_has_a_fact_the_slot_accepts(
    language,
) -> None:
    """Asked before a sample is dealt, and not by dealing one."""
    t = _TEXTS[language]
    deal = Deal(
        [source(1, passage_id=1, statement=t["plain"], language=language)],
        wanted=2,
        size=1,
    )

    assert deal.holds(
        lambda fact: "Standard" in fact.statement or "Lieferung" in fact.statement
    )
    assert not deal.holds(lambda fact: False)
    assert deal.sample(Shape.SINGLE) is not None, "asking spent nothing"
    assert not deal.holds(lambda fact: True), "nothing is left once it is dealt"


def test_holds_hands_the_fact_to_the_preference() -> None:
    """The preference is asked about facts, so one that reads them is never given None."""
    seen: list = []
    deal = Deal([source(1, statement="Fees are waived.")], wanted=1, size=1)

    deal.holds(lambda fact: seen.append(fact.statement) or True)

    assert seen == ["Fees are waived."]
