"""The parts reading of a needs_both question: what it is asked, what it logs, when it is skipped."""

from __future__ import annotations

import logging

import pytest
from factories import candidate
from test_verification import (
    _CASES,
    _DORMANT,
    _STATED_ONE,
    ByParts,
    StatedClient,
    _ask,
    _needs_both,
    _two,
    build,
)

from question_generation.verifier import Part


class _Spy(ByParts):
    """Records every argument the parts reading was asked with."""

    def stated(self, question, key, passages, thread=()):
        """Records the ask, then answers as scripted."""
        self.args = (question, key, tuple(passages), tuple(thread))
        return super().stated(question, key, passages, thread)


@pytest.mark.parametrize("language", ["en", "de"])
def test_the_reading_is_asked_the_question_the_key_the_passages_and_the_thread(
    language: str,
) -> None:
    """Every cited passage in citation order, and the turns before the question."""
    first, second, question, key = _DORMANT[language]
    thread = (("Was ist ein ruhendes Konto?", "ein Konto ohne Zahlung"),)
    spy = _Spy((Part("a", (first,)), Part("b", (second,))), recovers=key)

    build(spy).check(
        candidate(
            question_text=question,
            target_answer=key,
            facts=_two(first, second, language),
            kind="needs_both",
            thread=thread,
        )
    )

    asked, given, passages, turns = spy.args
    assert (asked, given, turns) == (question, key, thread)
    assert len(passages) == 2
    assert passages[0].startswith(first)
    assert passages[1].startswith(second)


def test_the_opinion_carries_the_half_threshold() -> None:
    """Recorded against 0.5, with no margin."""
    first, second, question, key = _DORMANT["en"]
    _, result = _ask(
        (Part("a", (first,)), Part("b", (second,))), first, second, question, key
    )

    one = [m for m in result.readings if m.gate == "needs_both"]
    assert [(m.value, m.threshold, m.opinion) for m in one] == [(1.0, 0.5, True)]


def test_an_unanswerable_question_is_never_read_for_its_parts() -> None:
    """Nothing is stated by a passage for a question written to have no answer."""
    first, second, question, _key = _DORMANT["en"]
    spy = _Spy((), recovers=None)

    build(spy).check(
        candidate(
            question_text=question,
            target_answer=None,
            answerable=False,
            facts=_two(first, second),
            kind="needs_both",
        )
    )

    assert spy.stated_asked == 0


def _log(caplog, parts, first, second, question, key, **kw):
    caplog.set_level(logging.INFO, logger="question_generation.checker")
    _ask(parts, first, second, question, key, **kw)
    return [(r.levelno, r.getMessage()) for r in caplog.records]


def test_nothing_held_logs_the_question_and_that_it_was_kept(caplog) -> None:
    """A reading that quotes nothing any passage holds says so."""
    first, second, question, key = _DORMANT["en"]
    got = _log(caplog, (Part("x", ("nowhere",)),), first, second, question, key)

    assert (
        logging.INFO,
        f"{question!r}: no passage holds a quoted part, kept as cited",
    ) in got


def test_a_tie_on_a_conjunction_logs_that_both_were_kept(caplog) -> None:
    """Both passages state the same part and the question joins cases."""
    first = "Returns are accepted within 30 days of delivery."
    second = "Returns are accepted within 30 days of delivery. Refunds take 5 days."
    question = "Within how many days can a shirt and a coat be returned?"
    got = _log(
        caplog, (Part("p", (first,)),), first, second, question, "within 30 days"
    )

    assert (
        logging.INFO,
        (
            f"{question!r}: every cited passage states every part and the "
            "question joins cases: kept two-passage"
        ),
    ) in got


def test_a_model_that_cannot_be_reached_logs_a_warning_with_the_cause(caplog) -> None:
    """The question is kept; the loss is said."""
    from llm.client import ModelUnavailable

    class Down(ByParts):
        def stated(self, *args, **kwargs):
            raise ModelUnavailable("gateway timeout")

    first, second, question, key = _DORMANT["en"]
    caplog.set_level(logging.INFO, logger="question_generation.checker")
    recording = Down((), recovers=key)
    build(recording).check(
        candidate(
            question_text=question,
            target_answer=key,
            facts=_two(first, second),
            kind="needs_both",
        )
    )

    assert (
        logging.WARNING,
        f"no parts reading for {question!r}: gateway timeout",
    ) in [(r.levelno, r.getMessage()) for r in caplog.records]


def test_narrowing_logs_the_passage_it_cites(caplog) -> None:
    """The kept passage's id is in the line."""
    first, second, question, key, again = _STATED_ONE["en"]
    got = _log(caplog, (Part("p", (first, again)),), first, second, question, key)

    assert (logging.INFO, f"{question!r} is cited from passage 1 alone") in got


def test_a_thread_needing_both_logs_that_both_were_kept(caplog) -> None:
    """The narrowed citation would ask nothing new."""
    first = "Eine Auslandsüberweisung kostet pauschal 5 Euro."
    second = "Auslandsüberweisungen über 10.000 Euro werden zusätzlich manuell geprüft."
    question = "Gilt der Preis auch über 10.000 Euro?"
    got = _log(
        caplog,
        (Part("der Preis", (first,)),),
        first,
        second,
        question,
        "ja, pauschal 5 Euro",
        language="de",
        thread=(("Was kostet eine Auslandsüberweisung?", "5 Euro"),),
        root_facts=(1,),
        parent_passages=(1,),
    )

    assert (
        logging.INFO,
        (
            f"{question!r} is stated by one passage but its thread needs both: "
            "kept two-passage"
        ),
    ) in got


def test_needs_both_helpers_agree_on_the_cases_fixture() -> None:
    """Two cases named in one question each hold a part of their own."""
    first, second, question, key = _CASES["en"]
    _, result = _ask(
        (Part("a", (first,)), Part("b", (second,))), first, second, question, key
    )
    assert _needs_both(result) == [(1.0, True)]


def test_a_bridge_cited_alone_logs_that_both_were_kept(caplog) -> None:
    """The line names the question and why the narrowing did not happen."""
    from factories import bridge, group, resting

    one = "Gift cards bought in a store can be redeemed in the online shop."
    two = "In the online shop a gift card cannot be combined with a discount code."
    fact = bridge(
        resting(2, text=two, topic_id=2),
        statement="A gift card bought in a store can be redeemed in the online shop, "
        "where it cannot be combined with a discount code.",
        passage_text=one,
        topic_id=1,
        fact_id=7,
    )
    question = "Where can a gift card bought in a store be redeemed besides the store?"
    caplog.set_level(logging.INFO, logger="question_generation.checker")

    build(ByParts((Part("where", (one,)),), recovers="in the online shop")).check(
        candidate(
            question_text=question,
            target_answer="in the online shop",
            facts=group(fact),
            kind="needs_both",
        )
    )

    assert (
        logging.INFO,
        f"{question!r} is stated by one passage but cites a bridge: kept two-passage",
    ) in [(r.levelno, r.getMessage()) for r in caplog.records]


def test_the_user_message_is_exactly_passages_conversation_question_key() -> None:
    """Passages numbered from 1 and blank-line separated; a null answer is said so."""
    from question_generation.verifier import Verifier

    client = StatedClient([])
    Verifier(client).stated(
        "Und bei Filialen?",
        "ja",
        ["Erste Regel.", "Zweite Regel."],
        thread=(("Wie hoch ist die Gebühr?", "5 Euro"), ("Und online?", None)),
    )
    bare = StatedClient([])
    Verifier(bare).stated("Is it free?", "yes", ["Shipping is free."])

    assert client.asked[0][1] == (
        'Passages:\n<material name="passages">\n'
        "[1] Erste Regel.\n\n[2] Zweite Regel.\n</material>\n\n"
        '<material name="conversation">\n'
        "Q: Wie hoch ist die Gebühr?\nA: 5 Euro\n"
        "Q: Und online?\nA: not in the material\n</material>\n"
        "Question: Und bei Filialen?\nKey: ja"
    )
    assert bare.asked[0][1] == (
        'Passages:\n<material name="passages">\n[1] Shipping is free.\n'
        "</material>\n\nQuestion: Is it free?\nKey: yes"
    )
