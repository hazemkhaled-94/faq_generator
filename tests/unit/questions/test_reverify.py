"""What a re-check does with a question a person accepted.

No rule gate overrules a person: a question a person accepted is rejected on
re-check only when the facts it rests on no longer hold.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from database.qa_generator import QuestionRejection, ReviewVerdict
from question_generation.config import Settings
from question_generation.models import JudgedQuestion, Neighbour
from question_generation.service import _recheck, reverify


class _Twin:
    """A catalogue whose nearest accepted question is the same question."""

    def nearest(self, embedding, before=None, excluding=(), **_):
        return Neighbour("What does the device weigh?", True, similarity=1.0)


def _stored(**columns) -> JudgedQuestion:
    """One accepted, answerable English question resting on one fact."""
    return JudgedQuestion(
        **{
            "id": 2,
            "question_text": "What does the device weigh?",
            "target_answer": "4 kg",
            "answerable": True,
            "difficulty": "easy",
            "passage_scope": None,
            "document_scope": None,
            "topic_scope": None,
            "language": "en",
            "status": "accepted",
            "embedding": None,
            "statements": ("The device weighs 4 kg.",),
            "facts_validated": True,
            "documents": 1,
            "passages": 1,
            "topics": 1,
            "follows_id": None,
            **columns,
        }
    )


#: (name, columns, catalogue, the code a rule gate stores when nobody looked).
REFUSED = (
    (
        "malformed",
        {"question_text": "What does the device weigh"},
        None,
        QuestionRejection.MALFORMED,
    ),
    (
        "scope moved",
        {"passage_scope": "multi_passage"},
        None,
        QuestionRejection.SOURCE_CHANGED,
    ),
    (
        "duplicate",
        {"embedding": [1.0]},
        _Twin(),
        QuestionRejection.DUPLICATE,
    ),
)


@pytest.mark.parametrize(
    ("columns", "catalog"),
    [row[1:3] for row in REFUSED],
    ids=[row[0] for row in REFUSED],
)
def test_no_rule_gate_rejects_a_question_a_person_accepted(columns, catalog) -> None:
    """Malformed, a moved scope and a near twin all leave it standing."""
    stored = _stored(reviewed_verdict=ReviewVerdict.ACCEPTED, **columns)

    assert _recheck(catalog, Settings.load(), stored) is None


@pytest.mark.parametrize(
    ("columns", "expected"),
    [(row[1], row[3]) for row in REFUSED[:2]],
    ids=[row[0] for row in REFUSED[:2]],
)
def test_a_rule_gate_still_rejects_a_question_nobody_reviewed(
    columns, expected
) -> None:
    """The same rows, unreviewed, are rejected as before."""
    failed = _recheck(None, Settings.load(), _stored(**columns))  # type: ignore[arg-type]

    assert failed is not None and failed[0] == expected


def test_a_question_a_person_accepted_falls_with_its_facts() -> None:
    """A fact that no longer holds rejects it, the person's accept or not."""
    stored = replace(
        _stored(reviewed_verdict=ReviewVerdict.ACCEPTED), facts_validated=False
    )

    failed = _recheck(None, Settings.load(), stored)  # type: ignore[arg-type]

    assert failed is not None and failed[0] == QuestionRejection.SOURCE_CHANGED


class _Rejected:
    """A catalogue holding one rejected question, whose probe must not run."""

    def judged(self, within=None):
        yield _stored(status="rejected", embedding=[1.0])

    def nearest(self, embedding, before=None, excluding=(), **_):
        raise AssertionError("a rejected question was probed")

    def reject(self, verdicts) -> int:
        return len(verdicts)


def test_a_rejected_question_is_not_checked_again() -> None:
    """It can only be rejected, so the parse and the probe are skipped."""
    assert reverify(_Rejected(), Settings.load()) == 0  # type: ignore[arg-type]


class _Stored:
    """A catalogue of accepted questions whose probe honours what it is asked."""

    def __init__(self, *stored: Neighbour) -> None:
        self.stored = stored

    def nearest(self, embedding, before=None, excluding=(), language=None, **asked):
        """The nearest stored question that is earlier, kept and of this kind."""
        answerable = asked.get("answerable")
        fitting = [
            one
            for one in self.stored
            if (before is None or (one.id or 0) < before)
            and one.id not in excluding
            and language in (None, one.language)
            and answerable in (None, one.answerable)
        ]
        return max(fitting, key=lambda one: one.similarity, default=None)


@pytest.mark.parametrize(("unanswerable", "answerable"), [(10, 20), (20, 10)])
def test_an_answered_twin_rejects_an_unanswerable_question_whichever_came_first(
    unanswerable: int, answerable: int
) -> None:
    """Nearness to an answered question on its own fact is an answer.

    Not a duplicate, so the earlier-only rule that keeps one of two twins
    has nothing to decide: the answered one refuses it however the two
    were ordered when written.
    """
    answered = Neighbour(
        "What does the device weigh?",
        True,
        similarity=0.95,
        fact_ids=frozenset({1}),
        language="en",
        id=answerable,
    )
    asked = _stored(
        id=unanswerable,
        question_text="What does the device weigh on the moon?",
        target_answer=None,
        answerable=False,
        embedding=[1.0],
        fact_ids=(1,),
    )

    failed = _recheck(_Stored(answered), Settings.load(), asked)  # type: ignore[arg-type]

    assert failed is not None and failed[0] == QuestionRejection.ANSWERABLE_AFTER_ALL


#: A compound row per language and domain: two unrelated asks joined by "and".
COMPOUND = (
    (
        "en",
        "What is the daily cash limit at a cash machine, and how is an account closed?",
        "1,000 euros; by a signed letter",
    ),
    (
        "de",
        "Wie hoch ist das tägliche Bargeldlimit am Automaten, und wie wird ein Konto geschlossen?",
        "1.000 Euro; durch einen Brief",
    ),
    (
        "en",
        "How long does standard delivery take, and within what period may goods be returned?",
        "3 to 5 days; 30 days",
    ),
    (
        "de",
        "Wie lange dauert die Standardlieferung, und bis wann können Waren zurückgegeben werden?",
        "3 bis 5 Tage; 30 Tage",
    ),
)


@pytest.mark.nlp
@pytest.mark.parametrize(("language", "question", "key"), COMPOUND)
def test_a_stored_compound_question_is_kept_by_a_re_check(
    language: str, question: str, key: str
) -> None:
    """Its two question words are what it is: the stored kind reaches the gate."""
    stored = _stored(
        question_text=question,
        target_answer=key,
        language=language,
        kind="compound",
        passages=2,
        documents=2,
    )

    assert _recheck(None, Settings.load(), stored) is None  # type: ignore[arg-type]


@pytest.mark.nlp
def test_a_single_passage_row_with_two_questions_is_still_refused() -> None:
    """Only the compound kind is let through the two-question-word gate."""
    stored = _stored(
        question_text="What is the daily cash limit at a cash machine, and how is an account closed?",
        target_answer="1,000 euros; by a signed letter",
    )

    failed = _recheck(None, Settings.load(), stored)  # type: ignore[arg-type]

    assert failed is not None and failed[0] == QuestionRejection.COMPOUND
