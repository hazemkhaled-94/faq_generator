"""An answerable question is held to the shape its planned type promises.

An enumeration answered with one thing, a temporal question answered with
one period, an entity question that asks after no party: each is a factoid
wearing a label, and the label feeds the cognitive level. Each is refused as
the wrong type, and its well-shaped counterpart is not.
"""

from __future__ import annotations

import pytest

from database.qa_generator import QuestionRejection, QuestionType

pytestmark = pytest.mark.nlp


def typed(question: str, answer: str, kind: str, language: str):
    """The type rules on an answerable question."""
    from question_generation.gates import typed as gate

    return gate(question, answer, True, kind, language)


@pytest.mark.parametrize(
    ("language", "question", "one", "several"),
    [
        (
            "de",
            "Welche Unterlagen braucht man für die Kontoeröffnung?",
            "einen Reisepass",
            "einen Reisepass, einen Meldenachweis und eine Gehaltsabrechnung",
        ),
        (
            "en",
            "Which documents are needed to open an account?",
            "a passport",
            "a passport, proof of address and a payslip",
        ),
        (
            "fr",
            "Quels documents faut-il pour ouvrir un compte ?",
            "un passeport",
            "un passeport, un justificatif de domicile et une fiche de paie",
        ),
        (
            "el",
            "Ποια έγγραφα χρειάζονται για το άνοιγμα λογαριασμού;",
            "ένα διαβατήριο",
            "ένα διαβατήριο, αποδεικτικό διεύθυνσης και μια μισθοδοσία",
        ),
    ],
)
def test_an_enumeration_answered_with_one_thing_is_the_wrong_type(
    language, question, one, several
) -> None:
    """One thing has no set behind it; a list does."""
    refused = typed(question, one, QuestionType.ENUMERATION, language)

    assert refused is not None and refused[0] == QuestionRejection.WRONG_TYPE
    assert "holds one thing" in refused[1]
    assert typed(question, several, QuestionType.ENUMERATION, language) is None


@pytest.mark.parametrize(
    ("language", "question", "one", "two"),
    [
        (
            "de",
            "Wie hat sich die Kartengebühr im Lauf der Jahre geändert?",
            "Sie beträgt 2 Euro.",
            "Sie betrug bis 2024 2 Euro und beträgt seit 2025 3 Euro.",
        ),
        (
            "en",
            "How did the card fee change over the years?",
            "It is 2 euros.",
            "It was 2 euros until 2024 and is 3 euros since 2025.",
        ),
    ],
)
def test_a_temporal_question_answered_with_one_period_is_the_wrong_type(
    language, question, one, two
) -> None:
    """One period shows no change; two do."""
    refused = typed(question, one, QuestionType.TEMPORAL, language)

    assert refused is not None and refused[0] == QuestionRejection.WRONG_TYPE
    assert "fewer than two periods" in refused[1]
    assert typed(question, two, QuestionType.TEMPORAL, language) is None


@pytest.mark.parametrize(
    ("language", "question", "answer"),
    [
        ("de", "Womit wird eine Überweisung freigegeben?", "mit einem TAN-Generator"),
        ("en", "With what is a transfer approved?", "with a TAN generator"),
    ],
)
def test_an_entity_question_asking_after_no_party_is_the_wrong_type(
    language, question, answer
) -> None:
    """Neither the question word nor the answer names a party."""
    refused = typed(question, answer, QuestionType.ENTITY, language)

    assert refused is not None and refused[0] == QuestionRejection.WRONG_TYPE
    assert "asks after no party" in refused[1]


@pytest.mark.parametrize(
    ("language", "question", "answer"),
    [
        ("fr", "Avec quoi un virement est-il validé ?", "avec un générateur TAN"),
        ("el", "Με τι εγκρίνεται μια μεταφορά;", "με μια γεννήτρια TAN"),
    ],
)
def test_an_unconfigured_entity_question_is_left_alone_or_refused(
    language, question, answer
) -> None:
    """No reading of the party there: inert or the wrong type, nothing else."""
    found = typed(question, answer, QuestionType.ENTITY, language)

    assert found is None or found[0] == QuestionRejection.WRONG_TYPE
