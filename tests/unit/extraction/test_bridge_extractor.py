"""The message a group of passages becomes, and what comes back from it.

A bridge candidate names the passages it rests on by position, so what the
prompt numbers and what the checker resolves have to be the same numbering.
"""

from __future__ import annotations

import pytest
from drivers import Model, group

from database.qa_generator import FactKind, Rejection
from extraction.extractors.base import ExtractionFailed
from extraction.extractors.bridge import PROMPT_VERSION, BridgeExtractor
from extraction.links import Link
from extraction.models import Cited
from extraction.validation import FactChecker
from llm.client import ModelUnavailable

pytestmark = pytest.mark.nlp

ANSWER = {
    "relation": "contrast",
    "facts": [{"excerpt": 0, "fact": 0}, {"excerpt": 1, "fact": 0}],
    "statement": "Urgent requests are answered sooner than standard ones.",
    "question": "Which is answered sooner, a standard or an urgent request?",
    "answer": "an urgent request",
}

FACTS = {
    11: [(901, "Standard requests are answered within 48 hours.", (0,))],
    22: [(902, "Urgent requests are answered within 4 hours.", (0,))],
}


@pytest.fixture
def offered():
    """Two passages of two documents, as a topic group offers them."""
    return group(
        "Standard requests are answered within 48 hours.",
        "Urgent requests are answered within 4 hours.",
    )


def test_the_provenance_names_the_model_and_the_prompt() -> None:
    """Two prompts are two datasets, so the version is recorded per fact."""
    provenance = BridgeExtractor(Model()).provenance

    assert provenance.model == "ollama/test-model"
    assert provenance.prompt_version == PROMPT_VERSION
    assert provenance.temperature == 0.0


def test_a_group_of_one_is_never_sent(offered) -> None:
    """There is nothing to bridge, so the call is not worth making."""
    model = Model(ANSWER)

    assert BridgeExtractor(model).extract(offered[:1]) == []
    assert BridgeExtractor(model).extract([]) == []
    assert model.calls == 0


def test_the_passages_are_sent_numbered_from_zero(offered) -> None:
    """The number is what a candidate's position resolves against."""
    model = Model(ANSWER)
    BridgeExtractor(model).extract(offered)

    sent = model.sent["user"]
    assert "[P0]" in sent and "[P1]" in sent
    assert sent.index("[P0]") < sent.index("[P1]")
    assert all(one.text in sent for one in offered)


def test_a_heading_is_carried_beside_its_passage(offered) -> None:
    """Which passage a heading belongs to is what makes it worth sending."""
    from dataclasses import replace

    model = Model(ANSWER)
    BridgeExtractor(model).extract(
        [replace(offered[0], section_path="Support > Times"), offered[1]]
    )

    assert "[P0] (Support > Times)" in model.sent["user"]


def test_a_returned_claim_becomes_a_bridge_candidate(offered) -> None:
    """The statement, the sentences of the facts chosen, and the probe."""
    facts = BridgeExtractor(Model(ANSWER)).extract(offered, None, FACTS)

    assert len(facts) == 1
    assert facts[0].kind == FactKind.BRIDGE
    assert [(one.position, one.sentences) for one in facts[0].passages] == [
        (0, (0,)),
        (1, (0,)),
    ]
    assert facts[0].sentences == (), "a bridge cites each passage separately"
    assert facts[0].probe == (ANSWER["question"], ANSWER["answer"])


def test_none_is_no_candidate(offered) -> None:
    """The first relation, and the usual answer."""
    assert (
        BridgeExtractor(Model({"relation": "none"})).extract(offered, None, FACTS) == []
    )


def test_a_blank_statement_is_no_candidate(offered) -> None:
    """Nothing was said, so there is nothing to check."""
    answer = {**ANSWER, "statement": "   "}

    assert BridgeExtractor(Model(answer)).extract(offered, None, FACTS) == []


LINKS = [
    ("en", "reference", "Section 7", '[P0] names the heading "Section 7" of [P1].'),
    ("de", "reference", "Abschnitt 7", '[P0] names the heading "Abschnitt 7" of [P1].'),
    (
        "en",
        "sibling",
        "Fees",
        '[P0] and [P1] are sections under the same heading "Fees".',
    ),
    (
        "en",
        "term",
        "express",
        '[P0] and [P1] are among the few excerpts using "express".',
    ),
]


@pytest.mark.parametrize(("language", "kind", "named", "line"), LINKS)
def test_the_link_is_named_in_the_message(language, kind, named, line) -> None:
    """The model is told why the documents put the two together."""
    first, second = group("A costs 1 EUR.", "B costs 2 EUR.", language=language)
    model = Model(ANSWER)

    BridgeExtractor(model).extract([first, second], Link((first, second), kind, named))

    assert line in model.sent["user"]


@pytest.mark.parametrize(
    ("language", "first", "second"),
    [
        (
            "en",
            "An account is dormant when its holder has made no payment for 24 months.",
            "A dormant account is charged a yearly fee of 10 EUR.",
        ),
        (
            "de",
            "Ein Konto ruht, wenn der Inhaber 24 Monate lang keine Zahlung geleistet hat.",
            "Für ein ruhendes Konto wird eine Jahresgebühr von 10 EUR erhoben.",
        ),
    ],
)
def test_each_excerpt_lists_its_validated_facts(language, first, second) -> None:
    """The halves of the claim are the facts already checked."""
    one, two = group(first, second, language=language)
    model = Model(ANSWER)

    BridgeExtractor(model).extract(
        [one, two], None, {one.id: [(901, first, (0,))], two.id: [(902, second, (0,))]}
    )

    sent = model.sent["user"]
    assert f"  [F0] {first}" in sent and f"  [F0] {second}" in sent
    assert sent.index("[P0]") < sent.index(f"  [F0] {first}") < sent.index("[P1]")


@pytest.mark.parametrize(
    ("language", "first", "second", "statement", "question", "answer"),
    [
        (
            "en",
            "An account is dormant when its holder has made no payment for 24 months.",
            "A dormant account is charged a yearly fee of 10 EUR.",
            "An account whose holder has made no payment for 24 months is charged a yearly fee of 10 EUR.",
            "What yearly fee is charged on an account whose holder has made no payment for 24 months?",
            "10 EUR",
        ),
        (
            "de",
            "Ein Konto ruht, wenn der Inhaber 24 Monate lang keine Zahlung geleistet hat.",
            "Für ein ruhendes Konto wird eine Jahresgebühr von 10 EUR erhoben.",
            "Für ein Konto, dessen Inhaber 24 Monate lang keine Zahlung geleistet hat, wird eine Jahresgebühr von 10 EUR erhoben.",
            "Welche Jahresgebühr wird für ein Konto erhoben, dessen Inhaber 24 Monate lang keine Zahlung geleistet hat?",
            "10 EUR",
        ),
    ],
)
def test_a_bridge_cites_the_sentences_of_the_facts_it_chose(
    language, first, second, statement, question, answer
) -> None:
    """Facts are chosen by number; the citation is theirs."""
    one, two = group(first, second, language=language)
    model = Model(
        {
            "relation": "defines",
            "facts": [{"excerpt": 0, "fact": 0}, {"excerpt": 1, "fact": 0}],
            "statement": statement,
            "question": question,
            "answer": answer,
        }
    )

    (candidate,) = BridgeExtractor(model).extract(
        [one, two], None, {one.id: [(901, first, (0,))], two.id: [(902, second, (0,))]}
    )

    assert candidate.passages == (Cited(0, (0,)), Cited(1, (0,)))
    assert candidate.probe == (question, answer)
    assert candidate.statement == statement


def test_a_fact_number_the_excerpt_does_not_have_is_dropped(offered) -> None:
    """The citation falls away, and the checker refuses it as one passage."""
    answer = {**ANSWER, "facts": [{"excerpt": 0, "fact": 0}, {"excerpt": 1, "fact": 5}]}

    (candidate,) = BridgeExtractor(Model(answer)).extract(offered, None, FACTS)

    assert [one.position for one in candidate.passages] == [0]
    checked = FactChecker(0.6).check_bridge(offered, candidate)
    assert checked.rejection_code == Rejection.NOT_BRIDGING


@pytest.mark.parametrize(
    ("language", "first", "second", "statement", "question", "answer"),
    [
        (
            "en",
            "Standard requests are answered within 48 hours.",
            "Urgent requests are answered within 4 hours.",
            "Urgent requests are answered sooner than standard requests.",
            "Which is answered sooner, a standard or an urgent request?",
            "an urgent request",
        ),
        (
            "de",
            "Standardanfragen werden innerhalb von 48 Stunden beantwortet.",
            "Dringende Anfragen werden innerhalb von 4 Stunden beantwortet.",
            "Dringende Anfragen werden schneller beantwortet als Standardanfragen.",
            "Was wird schneller beantwortet, eine Standardanfrage oder eine dringende Anfrage?",
            "eine dringende Anfrage",
        ),
    ],
)
def test_a_contrast_is_a_bridge(
    language, first, second, statement, question, answer
) -> None:
    """Two subjects, each excerpt one side, are a bridge the checker keeps."""
    one, two = group(first, second, language=language)
    model = Model(
        {
            "relation": "contrast",
            "facts": [{"excerpt": 0, "fact": 0}, {"excerpt": 1, "fact": 0}],
            "statement": statement,
            "question": question,
            "answer": answer,
        }
    )

    (candidate,) = BridgeExtractor(model).extract(
        [one, two], None, {one.id: [(901, first, (0,))], two.id: [(902, second, (0,))]}
    )

    assert candidate.probe == (question, answer)
    assert FactChecker(0.6).check_bridge([one, two], candidate).validated


@pytest.mark.parametrize(
    "returned",
    [{"facts": []}, {"facts": [{"excerpt": 0, "fact": 0}]}],
)
def test_a_claim_citing_too_little_reaches_the_checker(offered, returned) -> None:
    """It is stored refused, so the refusal rate counts it."""
    (candidate,) = BridgeExtractor(Model({**ANSWER, **returned})).extract(
        offered, None, FACTS
    )

    checked = FactChecker(0.6).check_bridge(offered, candidate)
    assert checked.rejection_code in (Rejection.EVIDENCE_ABSENT, Rejection.NOT_BRIDGING)


def test_an_empty_answer_is_a_correct_answer(offered) -> None:
    """Passages that merely share a topic need bridge nothing."""
    assert BridgeExtractor(Model({"relation": "none"})).extract(offered) == []


def test_a_model_that_will_not_answer_fails_the_group(offered) -> None:
    """The group is skipped with the reason, not left mid-extraction."""
    model = Model(ModelUnavailable("Timeout: took too long"))

    with pytest.raises(ExtractionFailed, match="took too long"):
        BridgeExtractor(model).extract(offered)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (
            "Standard requests are answered within 48 hours.",
            "Urgent requests are answered within 4 hours.",
        ),
        (
            "Standardanfragen werden innerhalb von 48 Stunden beantwortet.",
            "Dringende Anfragen werden innerhalb von 4 Stunden beantwortet.",
        ),
    ],
)
def test_the_relation_named_is_carried(first, second) -> None:
    """The candidate keeps the relation the model named; none is no candidate."""
    offered = group(first, second)

    (fact,) = BridgeExtractor(Model(ANSWER)).extract(offered, None, FACTS)
    assert fact.relation == "contrast"
    assert fact.probe == (ANSWER["question"], ANSWER["answer"])

    assert BridgeExtractor(Model({**ANSWER, "relation": "none"})).extract(offered) == []
