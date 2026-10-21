"""Defects the QA pass of the finalize session found in question generation, kept red.

Each test states what the documented behaviour asks and fails on the code
under test; `strict` makes a fix announce itself by turning the test green.
"""

from __future__ import annotations

import pytest

from database.qa_generator import AnswerForm, QuestionRejection
from nlp.analysis import figures
from question_generation.gates import adds_up, agrees, explains, structural

pytestmark = pytest.mark.nlp


# ── QA-qg-1: a space-grouped amount asserts nothing an explanation is held to ──

#: A passage, the key it answers, and an explanation stating another amount.
_PROTECTED = {
    "en": (
        "Deposits are protected up to EUR 100 000 per customer. Savings and "
        "current accounts count together.",
        "up to EUR 100 000",
        "Deposit protection covers each customer's balances at the bank. Savings "
        "and current accounts are added together and protected up to EUR 200 000 "
        "per customer, so larger balances are not covered in full.",
    ),
    "de": (
        "Guthaben sind bis zu 100 000 Euro je Kunde geschützt. Spar- und "
        "Girokonten zählen zusammen.",
        "bis zu 100 000 Euro",
        "Die Einlagensicherung schützt die Guthaben eines Kunden bei der Bank. "
        "Spar- und Girokonten werden zusammengerechnet und sind bis zu 200 000 "
        "Euro je Kunde geschützt, darüber hinaus nicht.",
    ),
}


@pytest.mark.xfail(
    strict=True,
    reason=(
        "QA-qg-1: an explanation stating a space-grouped amount the passages do "
        "not (EUR 200 000 against EUR 100 000) passes explains(), because the "
        "merged token is not like_num and claim().units drops it"
    ),
)
@pytest.mark.parametrize("language", ["en", "de"])
def test_qa_qg_1_an_explanation_with_a_wrong_space_grouped_amount_is_unusable(
    language,
) -> None:
    """`EUR 200,000` is refused; `EUR 200 000`, the same wrong amount, must be too."""
    passage, key, explanation = _PROTECTED[language]

    assert not explains(explanation, key, (passage,), language)


def test_qa_qg_1_the_same_wrong_amount_with_a_thousands_mark_is_refused() -> None:
    """The control: the gate does hold an explanation's figures to the passages."""
    passage, key, explanation = _PROTECTED["en"]

    assert not explains(
        explanation.replace("EUR 200 000", "EUR 200,000"), key, (passage,), "en"
    )


# ── QA-qg-2: an inflected title after an attribution ───────────────────────


@pytest.mark.xfail(
    strict=True,
    reason=(
        "QA-qg-2: _quotes matches a title word for word as written, so 'Laut den "
        "Allgemeinen Geschäftsbedingungen' never quotes the title 'Allgemeine "
        "Geschäftsbedingungen' and the attribution half of the free rule misses it"
    ),
)
def test_qa_qg_2_an_attribution_to_an_inflected_title_is_a_source() -> None:
    """`Laut dem Preis- und Leistungsverzeichnis` is refused; a declined adjective must be too."""
    statement = (
        "Allgemeine Geschäftsbedingungen: Die Kündigungsfrist des Girokontos "
        "beträgt einen Monat."
    )
    failed, _ = structural(
        question_text=(
            "Laut den Allgemeinen Geschäftsbedingungen, wie lange ist die "
            "Kündigungsfrist des Girokontos?"
        ),
        target_answer="einen Monat",
        answerable=True,
        language="de",
        statements=(statement,),
        passages=(statement,),
        titles=("Allgemeine Geschäftsbedingungen",),
    )

    assert failed is not None and failed[0] == QuestionRejection.LEAKS_SOURCE


# ── QA-qg-3: ordinals past twelve ──────────────────────────────────────────


@pytest.mark.xfail(
    strict=True,
    reason=(
        "QA-qg-3: _ORDINALS stops at twelfth/zwölften, so a spelled ordinal past "
        "twelve never agrees with its figure (thirteenth/13th, dreizehnten/13.)"
    ),
)
@pytest.mark.parametrize(
    ("recovered", "key", "language"),
    [
        ("The fee applies from the thirteenth month on.", "from the 13th month on", "en"),
        ("Die Gebühr gilt ab dem dreizehnten Monat.", "ab dem 13. Monat", "de"),
        ("Payment is due by the twentieth day.", "by the 20th day", "en"),
    ],
)
def test_qa_qg_3_an_ordinal_past_twelve_agrees_with_its_figure(
    recovered, key, language
) -> None:
    """`third` agrees with `3rd` (QAB-qg-check-6); `thirteenth` must agree with `13th`."""
    assert agrees(recovered, key, language, AnswerForm.VALUE)


# ── QA-qg-4: a currency word carrying a suffix ─────────────────────────────


@pytest.mark.xfail(
    strict=True,
    reason=(
        "QA-qg-4: _amount reads the word beside a space-grouped run stripped of "
        ".,;:() only, so 'Euro/Kunde', 'Euro*' and '5 000,- EUR' are no currency "
        "word and the run is read as two figures"
    ),
)
@pytest.mark.parametrize(
    "text",
    [
        "Guthaben sind bis 100 000 Euro/Kunde geschützt.",
        "Guthaben sind bis 100 000 Euro* geschützt.",
        "Der Dispositionskredit beträgt 5 000,- EUR.",
    ],
)
def test_qa_qg_4_a_space_grouped_amount_beside_a_marked_currency_is_one_figure(
    text,
) -> None:
    """`100 000 Euro` is one figure (NEW-release-1); so is `100 000 Euro/Kunde`."""
    assert len(figures(text, "de")) == 1, figures(text, "de")


@pytest.mark.xfail(
    strict=True,
    reason=(
        "QA-qg-4: a right total over amounts written '100 000 Euro/Kunde' is "
        "refused by adds_up as a wrong sum, without a model call"
    ),
)
def test_qa_qg_4_a_right_total_over_marked_amounts_is_not_refused() -> None:
    """The same passages with `je Kunde` add up; with `/Kunde` they must too."""
    assert (
        adds_up(
            "300.000 Euro",
            [
                "Ihr Geld ist bis zu 100 000 Euro/Kunde geschützt.",
                "Für das Gemeinschaftskonto gelten bis zu 200 000 Euro/Kunde.",
            ],
            "de",
        )
        is not False
    )


# ── QA-qg-5: a title of no noun or adjective ───────────────────────────────


@pytest.mark.xfail(
    strict=True,
    reason=(
        "QA-qg-5: _quotes returns True for a quoted title with no noun or "
        "adjective ('return not terms or ...'), so a help page titled 'How can I "
        "pay?' or 'Wie kann ich bezahlen?' refuses every question opening on "
        "the same words as leaks_source, with no model call"
    ),
)
@pytest.mark.parametrize(
    ("question", "answer", "title", "statement", "language"),
    [
        (
            "Wie kann ich bezahlen, wenn ich keine Kreditkarte habe?",
            "per Rechnung",
            "Wie kann ich bezahlen?",
            "Ohne Kreditkarte können Sie per Rechnung bezahlen.",
            "de",
        ),
        (
            "How can I pay if I have no credit card?",
            "by invoice",
            "How can I pay?",
            "Customers without a credit card can pay by invoice.",
            "en",
        ),
    ],
)
def test_qa_qg_5_a_question_opening_like_a_faq_title_names_no_source(
    question, answer, title, statement, language
) -> None:
    """Per the README a title is a source when its material lacks a noun or adjective of it; this one has none."""
    failed, _ = structural(
        question_text=question,
        target_answer=answer,
        answerable=True,
        language=language,
        statements=(statement,),
        passages=(statement,),
        titles=(title,),
    )

    assert failed is None, failed
