"""How a value is read for the gates: space-grouped amounts, ordinals, the pronoun one, noun phrases."""

from __future__ import annotations

import pytest

from database.qa_generator import AnswerForm, QuestionType
from nlp.analysis import figures
from question_generation.gates import (
    BOUNDS,
    OVERLAP,
    _stated,
    adds_up,
    agrees,
    explains,
    fitting,
    relabelled,
)

pytestmark = pytest.mark.nlp


@pytest.mark.parametrize(
    "text, language, value",
    [
        ("Ihr Guthaben ist bis zu 100 000 Euro geschützt.", "de", 100000.0),
        ("Der Laptop kostet 1 299,99 EUR.", "de", 1299.99),
        ("The overdraft limit is 12 500.00 GBP.", "en", 12500.0),
        ("Deposits are protected up to EUR 100 000.", "en", 100000.0),
    ],
)
def test_a_space_grouped_amount_reads_as_one_figure(text, language, value):
    """NEW-release-1: `5 000` is one figure, in German and English."""
    assert figures(text, language) == [value]


@pytest.mark.parametrize(
    "recovered, key, language",
    [
        ("Bis zu 5.000 Euro pro Forderung.", "5 000 Euro", "de"),
        (
            "Up to EUR 100,000 per account holder.",
            "EUR 100 000 per account holder",
            "en",
        ),
    ],
)
def test_one_amount_grouped_two_ways_agrees(recovered, key, language):
    """One amount grouped by a space and by a mark agrees."""
    assert agrees(recovered, key, language)


@pytest.mark.parametrize(
    "total, passages, language",
    [
        (
            "300.000 Euro",
            [
                "Ihr Geld ist bis zu 100 000 Euro je Konto geschützt.",
                "Für das Gemeinschaftskonto gelten bis zu 200 000 Euro.",
            ],
            "de",
        ),
        (
            "EUR 300,000",
            [
                "Deposits are protected up to EUR 100 000 per holder.",
                "A joint account is covered up to EUR 200 000.",
            ],
            "en",
        ),
    ],
)
def test_a_right_total_over_space_grouped_amounts_is_not_refused(
    total, passages, language
):
    """A right total over space-grouped amounts is no wrong sum."""
    assert adds_up(total, passages, language) is not False


def test_a_space_grouped_amount_is_one_number_to_relabelled():
    """An aggregation keyed with `EUR 100 000` holds one number."""
    kind = relabelled(QuestionType.AGGREGATION, AnswerForm.VALUE, "EUR 100 000", "en")
    assert kind == QuestionType.AGGREGATION


# QAB-qg-check-6: an ordinal written as a word on one side and a figure on the other.
@pytest.mark.parametrize(
    ("recovered", "key", "language", "question", "passage"),
    [
        (
            "A fee is charged from the 3rd reminder.",
            "the third reminder",
            "en",
            "From which reminder is a fee charged?",
            "A fee of 5 EUR is charged from the 3rd reminder.",
        ),
        (
            "Ab der dritten Mahnung wird eine Gebühr fällig.",
            "ab der 3. Mahnung",
            "de",
            "Ab welcher Mahnung wird eine Gebühr fällig?",
            "Ab der dritten Mahnung wird eine Gebühr von 5 EUR fällig.",
        ),
        (
            "A fee is charged from the third reminder.",
            "the 3rd reminder",
            "en",
            "From which reminder is a fee charged?",
            "A fee of 5 EUR is charged from the third reminder.",
        ),
    ],
)
def test_qab_qg_check_6_an_ordinal_word_agrees_with_its_figure(
    recovered, key, language, question, passage
):
    """QAB-qg-check-6: `the third reminder` and `the 3rd reminder` agree."""
    assert agrees(
        recovered, key, language, AnswerForm.VALUE, OVERLAP, question, "", (passage,)
    )


# NEW-qg-writer-gates-4: an explanation writing an ordinal as a figure the passage spells out.
@pytest.mark.parametrize(
    ("explanation", "key", "passage", "language"),
    [
        (
            (
                "The shop sends reminders for unpaid invoices. The first two reminders cost "
                "nothing, but from the 3rd reminder onwards a fee of 5 EUR is added to the "
                "invoice, so a customer who pays after two reminders pays no fee."
            ),
            "from the third reminder",
            (
                "A fee of 5 EUR is charged from the third reminder onwards. The first and "
                "second reminders are free of charge."
            ),
            "en",
        ),
        (
            (
                "Der Shop verschickt Mahnungen für offene Rechnungen. Die ersten beiden "
                "Mahnungen kosten nichts, doch ab der 3. Mahnung wird eine Gebühr von 5 EUR "
                "auf die Rechnung aufgeschlagen, sodass nur spätes Zahlen etwas kostet."
            ),
            "ab der dritten Mahnung",
            (
                "Ab der dritten Mahnung wird eine Gebühr von 5 EUR fällig. Die erste und "
                "zweite Mahnung sind kostenlos."
            ),
            "de",
        ),
    ],
)
def test_new_4_an_ordinal_figure_in_an_explanation_is_carried_by_its_word(
    explanation, key, passage, language
):
    """NEW-qg-writer-gates-4: `3rd` in an explanation is carried by `third`."""
    assert explains(explanation, key, (passage,), language)


@pytest.mark.parametrize(
    ("statements", "language"),
    [
        (
            ["The second reminder costs 5 euros.", "A late fee applies after 14 days."],
            "en",
        ),
        (
            ["The 2nd reminder costs 5 euros.", "A late fee applies after 14 days."],
            "en",
        ),
        (
            ["Die zweite Mahnung kostet 5 Euro.", "Nach 14 Tagen gilt eine Gebühr."],
            "de",
        ),
    ],
)
def test_an_ordinal_is_no_stated_count(statements, language):
    """`the second reminder` states no count of 2."""
    assert not _stated(2, statements, language)


@pytest.mark.parametrize(
    ("recovered", "key"),
    [("The 5th day.", "5 days"), ("At the third reminder.", "3 reminders")],
)
def test_an_ordinal_does_not_agree_with_a_cardinal(recovered, key):
    """An ordinal is the same ordinal in another form, never a count."""
    assert not agrees(recovered, key, "en")


@pytest.mark.parametrize(
    "answer", ["3 cards, the one on file included", "3 accounts, no one more"]
)
def test_var_number_readings_1_the_pronoun_one_keeps_a_count_a_count(answer):
    """The pronoun `one` is no second number, so the count stays an aggregation."""
    kind = relabelled(QuestionType.AGGREGATION, AnswerForm.VALUE, answer, "en")
    assert kind == QuestionType.AGGREGATION


# NEW-qg-writer-gates-6: the frame must not turn an imperative into a value.
@pytest.mark.parametrize(
    ("key", "language"),
    [
        ("Sign the contract", "en"),
        ("Open the app and tap Pay", "en"),
        ("Rufen Sie die Hotline an", "de"),
        ("Füllen Sie das Formular aus", "de"),
    ],
)
def test_an_imperative_key_is_still_an_action(key, language):
    """An imperative is an action, not a value."""
    _, stopped = fitting(key, [AnswerForm.VALUE], BOUNDS, language)
    assert stopped is not None, f"{key!r} passed as a value"


@pytest.mark.parametrize(
    ("recovered", "key"),
    [
        ("Ab der 3. Mahnung fallen 5 Euro an.", "3 Mahnungen"),
        ("Die Rückgabe ist bis zum 14. möglich.", "14"),
    ],
)
def test_a_german_ordinal_figure_does_not_agree_with_a_cardinal(recovered, key):
    """English `the 14th` against `14` disagrees; German `zum 14.` must too."""
    assert not agrees(recovered, key, "de")


def test_a_german_ordinal_figure_is_no_stated_count():
    """`Ab der 3. Mahnung` states no count of 3."""
    assert not _stated(
        3, ["Ab der 3. Mahnung gilt eine Gebühr.", "Y gilt.", "Z gilt."], "de"
    )
