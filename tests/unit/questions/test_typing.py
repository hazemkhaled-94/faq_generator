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
