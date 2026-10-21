"""What a question is typed as, read off how it opens.

A question opening `Wann` asks for a condition whatever slot it was written
for, and refusing it as the wrong type throws away a question that is
right about what it asks. It is typed by its opening instead, and then held
to that type's rules. The opener table is keyed by language.
"""

from __future__ import annotations

import pytest

from database.qa_generator import AnswerForm, QuestionType

pytestmark = pytest.mark.nlp


@pytest.mark.parametrize(
    ("question", "language", "written_as", "expected"),
    [
        (
            "What is the reason refunds are paid only to account holders?",
            "en",
            QuestionType.DEFINITION,
            QuestionType.REASON,
        ),
        (
            "When is a card blocked?",
            "en",
            QuestionType.DEFINITION,
            QuestionType.CONDITION,
        ),
        (
            "Wann wird eine Karte gesperrt?",
            "de",
            QuestionType.CONSEQUENCE,
            QuestionType.CONDITION,
        ),
        (
            "Wie viele Karten darf ein Kunde besitzen?",
            "de",
            QuestionType.PROCEDURE,
            QuestionType.FACTOID,
        ),
        (
            "What happens if a payment is late?",
            "en",
            QuestionType.FACTOID,
            QuestionType.CONSEQUENCE,
        ),
        (
            "What is a standing order?",
            "en",
            QuestionType.DEFINITION,
            QuestionType.DEFINITION,
        ),
        (
            "Which fees apply abroad?",
            "en",
            QuestionType.ENUMERATION,
            QuestionType.ENUMERATION,
        ),
        (
            "Quand la carte est-elle bloquée ?",
            "fr",
            QuestionType.DEFINITION,
            QuestionType.DEFINITION,
        ),
    ],
)
def test_a_question_is_typed_by_what_its_opening_asks(
    question, language, written_as, expected
) -> None:
    """The slot's type where the opening names none or names it; the opening's otherwise."""
    from question_generation.gates import retyped

    assert retyped(question, written_as, language) == expected


@pytest.mark.parametrize(
    ("question", "language", "written_as", "expected"),
    [
        (
            "Ich bin neu bei der Bank. Wann wird eine Karte gesperrt?",
            "de",
            QuestionType.CONSEQUENCE,
            QuestionType.CONDITION,
        ),
        (
            "Als neuer Kunde, warum wird mein Konto geprüft?",
            "de",
            QuestionType.DEFINITION,
            QuestionType.REASON,
        ),
        (
            "Ich habe ein Girokonto: Wie viele Karten darf ich besitzen?",
            "de",
            QuestionType.PROCEDURE,
            QuestionType.FACTOID,
        ),
        (
            "Ich bestelle online. Was passiert, wenn das Paket verloren geht?",
            "de",
            QuestionType.FACTOID,
            QuestionType.CONSEQUENCE,
        ),
        (
            "I'm a new customer. When is a card blocked?",
            "en",
            QuestionType.DEFINITION,
            QuestionType.CONDITION,
        ),
        (
            "As a new customer, why are refunds paid only to account holders?",
            "en",
            QuestionType.DEFINITION,
            QuestionType.REASON,
        ),
        (
            "I'm moving abroad: what happens if a payment is late?",
            "en",
            QuestionType.FACTOID,
            QuestionType.CONSEQUENCE,
        ),
        (
            "For a joint account, how many cards may each holder have?",
            "en",
            QuestionType.PROCEDURE,
            QuestionType.FACTOID,
        ),
        (
            "I run a small shop; what does chargeback mean?",
            "en",
            QuestionType.FACTOID,
            QuestionType.DEFINITION,
        ),
    ],
)
def test_a_question_behind_a_premise_is_typed_by_its_own_opening(
    question, language, written_as, expected
) -> None:
    """The opening is read where the question begins, after what the asker says first."""
    from question_generation.gates import retyped

    assert retyped(question, written_as, language) == expected


@pytest.mark.parametrize(
    ("question", "language", "written_as", "expected"),
    [
        (
            "Who decides, when the branch and the call centre disagree?",
            "en",
            QuestionType.ENTITY,
            QuestionType.ENTITY,
        ),
        (
            "Wer entscheidet, wann eine Karte gesperrt wird?",
            "de",
            QuestionType.ENTITY,
            QuestionType.ENTITY,
        ),
        (
            "Was ist ein Dauerauftrag?",
            "de",
            QuestionType.DEFINITION,
            QuestionType.DEFINITION,
        ),
    ],
)
def test_a_direct_question_is_typed_by_its_opening_as_before(
    question, language, written_as, expected
) -> None:
    """A clause after the question word is no premise, and an opening read at the start stands."""
    from question_generation.gates import retyped

    assert retyped(question, written_as, language) == expected


@pytest.mark.parametrize(
    ("language", "question", "kind"),
    [
        (
            "en",
            "When I travel abroad with my debit card, why is it blocked at some cash machines?",
            QuestionType.REASON,
        ),
        (
            "en",
            "When my parcel arrives damaged, how do I return it?",
            QuestionType.PROCEDURE,
        ),
        (
            "en",
            (
                "When I pay by card abroad, what is the difference between the "
                "exchange fee and the card fee?"
            ),
            QuestionType.COMPARISON,
        ),
        (
            "en",
            "When the branch is closed, what happens to a deposit?",
            QuestionType.CONSEQUENCE,
        ),
        # The German twin read right before: `Wenn` is no question word.
        (
            "de",
            "Wenn ich ins Ausland reise, warum wird meine Karte gesperrt?",
            QuestionType.REASON,
        ),
    ],
)
def test_a_premise_opening_on_when_is_typed_by_the_question_behind_it(
    language, question, kind
) -> None:
    """A subordinate `When ...,` is the premise; the main clause's question word asks."""
    from question_generation.gates import retyped

    assert retyped(question, kind, language) == kind


@pytest.mark.parametrize(
    ("language", "question", "behind"),
    [
        (
            "en",
            "I have a savings account, which I opened in 2020. Why is a fee charged now?",
            "Why is a fee charged now?",
        ),
        (
            "en",
            "As a customer who travels a lot, why is my card blocked abroad?",
            "why is my card blocked abroad?",
        ),
        (
            "de",
            (
                "Ich wohne in einem Ort, wo es keine Filiale gibt. Warum muss ich "
                "ein Konto online eröffnen?"
            ),
            "Warum muss ich ein Konto online eröffnen?",
        ),
    ],
)
def test_a_relative_word_in_the_premise_is_not_where_the_question_begins(
    language, question, behind
) -> None:
    """A question word inside a relative or adverbial clause asks nothing."""
    from nlp.analysis import asked

    assert asked(question, language) == behind


def test_a_question_word_behind_a_premise_is_held_to_its_type() -> None:
    """The question-word check reads past the premise too, both ways."""
    from database.qa_generator import QuestionRejection
    from question_generation.gates import typed

    question = "Ich bin neu bei der Bank. Warum wird mein Konto geprüft?"

    refused = typed(question, None, False, QuestionType.ENUMERATION, "de")
    assert refused is not None
    assert refused[0] == QuestionRejection.WRONG_TYPE
    assert typed(question, None, False, QuestionType.REASON, "de") is None


@pytest.mark.parametrize(
    ("form", "answer", "expected"),
    [
        (AnswerForm.LIST, "a passport and proof of address", QuestionType.ENUMERATION),
        (AnswerForm.VALUE, "the account holder", QuestionType.FACTOID),
        (AnswerForm.VALUE, "3 cards", QuestionType.AGGREGATION),
    ],
)
def test_a_count_whose_answer_is_no_figure_is_labelled_by_its_form(
    form, answer, expected
) -> None:
    """An aggregation keyed with a list is an enumeration; with one figure it stays."""
    from question_generation.gates import relabelled

    assert relabelled(QuestionType.AGGREGATION, form, answer, "en") == expected


def test_a_type_that_derives_nothing_keeps_its_label() -> None:
    """Only the arithmetic kinds are read for a figure."""
    from question_generation.gates import relabelled

    assert (
        relabelled(
            QuestionType.CONDITION, AnswerForm.EXPLANATION, "when it is lost", "en"
        )
        == QuestionType.CONDITION
    )


@pytest.mark.parametrize(
    ("answer", "language", "expected"),
    [
        ("Junioren-, Senioren-, Behinderten- und Breitenfussball", "de", True),
        ("short- and long-term savings accounts", "en", True),
        ("Breitenfussball", "de", False),
    ],
)
def test_an_elided_compound_counts_each_part_as_an_item(
    answer, language, expected
) -> None:
    """`Junioren-, Senioren- und Breitenfussball` names three kinds of football."""
    from question_generation.gates import enumerates

    assert enumerates(answer, language) is expected


@pytest.mark.parametrize(
    ("question", "answer", "language"),
    [
        (
            "Welche Gebühr gilt, wenn das Konto im Plus ist?",
            "keine Gebühr",
            "de",
        ),
        (
            "If the branch and the call centre disagree, who decides on a refund?",
            "The branch decides on a refund.",
            "en",
        ),
    ],
)
def test_a_short_answer_whose_new_word_is_its_polarity_or_party_says_something(
    question, answer, language
) -> None:
    """`keine` against a question that asked which fee, `who` answered by a party."""
    from question_generation.gates import restates

    assert not restates(question, answer, language)


def test_a_why_answered_with_its_own_rule_negated_still_restates() -> None:
    """A negative said back to a `why` is the rule, not the reason."""
    from question_generation.gates import restates

    assert restates(
        "Why is a transfer not released before a senior officer signs it?",
        "A transfer is not released before a senior officer signs it.",
        "en",
    )


def test_an_explanation_naming_a_term_the_passages_do_not_is_still_usable() -> None:
    """A name an explanation uses to describe is not a claim; a figure is."""
    from question_generation.gates import explains

    passages = ["Refunds are paid within 14 days of the request."]
    good = (
        "The bank pays a refund within 14 days of the request, so the Northbank "
        "customer service desk does not need to chase it; the period starts with the request."
    )
    bad = (
        "The bank pays a refund within 30 days of the request, so the customer does "
        "not need to chase it; the period starts with the request itself."
    )

    assert explains(good, "within 14 days", passages, "en")
    assert not explains(bad, "within 14 days", passages, "en")
