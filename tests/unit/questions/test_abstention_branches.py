"""The two later phrasing judgements leave a trace when they abstain, too.

`names_something` is asked of a question the parse calls thin, and
`self_contained` of one that points outward. An unreachable judge must not
reject either, and must not let it read as having cleared a gate nobody
ran; the same judge answering False does reject, so the gate is reached.
"""

from __future__ import annotations

import pytest
from factories import candidate, group, source
from test_abstention import Judge, build

from database.qa_generator import QuestionRejection

pytestmark = pytest.mark.nlp

THIN = {"de": "Was ist enthalten?", "en": "What is included?"}

POINTING = {
    "de": "Wie viel kosten diese beiden Konten einen Kunden der Sparkasse im Monat?",
    "en": "How much do these two accounts cost a customer of the savings bank each month?",
}

UNCONFIGURED = {
    "fr": "Combien coûtent ces deux comptes à un client de la caisse d'épargne ?",
    "el": "Πόσο κοστίζουν αυτοί οι δύο λογαριασμοί σε έναν πελάτη της τράπεζας;",
}


def phrased(question: str, language: str, answer: bool | None):
    """The phrasing verdict, what abstained and what was asked."""
    judge, abstained = Judge(answer), []
    asked = candidate(question_text=question, facts=group(source(language=language)))
    return build(judge)._phrasing(asked, abstained), abstained, judge.asked


@pytest.mark.parametrize(
    ("gate", "questions"), [("names_something", THIN), ("self_contained", POINTING)]
)
@pytest.mark.parametrize("language", ["de", "en"])
def test_an_abstaining_later_judgement_is_recorded_and_rejects_nothing(
    gate, questions, language
) -> None:
    """Recorded by name; the question is not refused for it."""
    failed, abstained, _ = phrased(questions[language], language, None)

    assert failed is None
    assert gate in abstained


@pytest.mark.parametrize(
    ("gate", "questions"), [("names_something", THIN), ("self_contained", POINTING)]
)
@pytest.mark.parametrize("language", ["de", "en"])
def test_the_same_judgement_answering_false_rejects(gate, questions, language) -> None:
    """The control: the gate is reached and its False refuses."""
    failed, abstained, asked = phrased(questions[language], language, False)

    assert gate in asked
    assert failed is not None and failed[0] == QuestionRejection.UNANCHORED
    assert abstained == []


@pytest.mark.parametrize("language", sorted(UNCONFIGURED))
def test_an_unconfigured_language_abstention_rejects_nothing_and_is_recorded(
    language,
) -> None:
    """Whatever the parse asks there, an abstention is a trace, not a verdict."""
    failed, abstained, asked = phrased(UNCONFIGURED[language], language, None)

    assert failed is None
    assert abstained == asked
