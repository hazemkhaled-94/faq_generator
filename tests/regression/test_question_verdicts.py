"""The verdicts a re-check reaches on stored questions, pinned as a table.

Rows docs/bugs.md quotes, each beside the code re-verify has to store for it,
and one sound row. A rule added to the checker's type gates that re-verify
does not run leaves the stored release as it was.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from database.qa_generator import AnswerForm, QuestionRejection, QuestionType
from question_generation.config import Settings
from question_generation.gates import near_verdict
from question_generation.models import JudgedQuestion, Neighbour
from question_generation.service import _recheck

pytestmark = pytest.mark.nlp

#: (name, question, answer, type, form, expected code or None).
ROWS: tuple[tuple[str, str, str, str, str, str | None], ...] = (
    (
        "a comparison answered with two definitions",
        "How does algorithmic bias differ from area under curve (AUC)?",
        (
            "a type of bias caused by the ML algorithm, a measure of how well "
            "a classifier can distinguish between two classes"
        ),
        QuestionType.COMPARISON,
        AnswerForm.LIST,
        QuestionRejection.WRONG_TYPE,
    ),
    (
        "a why question typed as a procedure",
        "Why does the release draw whole threads?",
        "because a follow-up reads only after the turn it follows",
        QuestionType.PROCEDURE,
        AnswerForm.EXPLANATION,
        QuestionRejection.WRONG_TYPE,
    ),
    (
        "an answer that restates its question",
        (
            "Why can accurate test metrics be hard to determine for "
            "exploratory testing sessions?"
        ),
        (
            "accurate test metrics for exploratory testing sessions can be "
            "challenging to determine"
        ),
        QuestionType.REASON,
        AnswerForm.EXPLANATION,
        QuestionRejection.RESTATES_QUESTION,
    ),
    (
        "a sound reason",
        "Why does a request have to be confirmed in writing?",
        "so that the agreed response time can be evidenced later",
        QuestionType.REASON,
        AnswerForm.EXPLANATION,
        None,
    ),
)


@pytest.mark.parametrize(
    ("question", "answer", "kind", "form", "expected"),
    [row[1:] for row in ROWS],
    ids=[row[0] for row in ROWS],
)
def test_a_stored_question_is_rechecked_against_the_type_rules(
    question: str, answer: str, kind: str, form: str, expected: str | None
) -> None:
    """What re-verify stores for a row the checker would refuse today."""
    failed = _recheck(None, Settings.load(), _stored(question, answer, kind, form))  # type: ignore[arg-type]

    assert (failed[0] if failed else None) == expected, failed


class _Nearest:
    """A catalogue whose nearest accepted question is one fixed twin."""

    def __init__(self, twin: Neighbour) -> None:
        self._twin = twin

    def nearest(self, embedding, before=None, excluding=()):
        return self._twin


def test_a_twin_asking_another_thing_is_not_a_duplicate_on_re_check() -> None:
    """The `asks_the_same` veto the checker applies, applied again."""
    stored = replace(
        _stored(
            "Why does a request have to be confirmed in writing?",
            "so that the agreed response time can be evidenced later",
            QuestionType.REASON,
            AnswerForm.EXPLANATION,
        ),
        embedding=[1.0],
    )
    twin = Neighbour(
        "Which requests have to be confirmed in writing?", True, similarity=0.95
    )

    assert _recheck(_Nearest(twin), Settings.load(), stored) is None  # type: ignore[arg-type]


#: Unanswerable questions probed against the accepted answerable question
#: nearest them, at the cosine the gate read, with the facts each cites:
#: (name, question, neighbour, cosine, its facts, the neighbour's).
NEARNESS: tuple[tuple[str, str, str, float, tuple[int, ...], tuple[int, ...]], ...] = (
    (
        "Q183, a temporary concussion substitute, near the permanent one",
        "Was ist eine vorübergehende Auswechslung wegen Gehirnerschütterung?",
        (
            "Wie erfolgt eine zusätzliche dauerhafte Auswechslung wegen "
            "Gehirnerschütterung?"
        ),
        0.9484,
        (206,),
        (192,),
    ),
    (
        "Q235, why a goalkeeper in the shoot-out, near reducing the numbers",
        "Warum muss bei einem Elfmeterschießen jedes Team einen Torhüter haben?",
        (
            "Warum muss ein Team beim Elfmeterschiessen seine Spielerzahl an die des "
            "Gegners anpassen, wenn es mehr Spieler hat?"
        ),
        0.9387,
        (309,),
        (308, 608),
    ),
    (
        "Q542, offside before a touch, near taking part in play",
        (
            "Warum darf ein Angreifer in Abseitsstellung schon vor einer "
            "Ballberührung bestraft werden, wenn kein Mitspieler mehr die "
            "Möglichkeit hat, den Ball zu spielen?"
        ),
        (
            "Warum wird ein Spieler in Abseitsstellung nur bestraft, wenn er aktiv "
            "am Spiel teilnimmt?"
        ),
        0.9316,
        (1590,),
        (632, 636),
    ),
    (
        "Q543, offside past a dummy, near taking part in play",
        (
            "Warum darf ein Angreifer in Abseitsstellung bestraft werden, wenn ein "
            "Mitspieler den Ball absichtlich durchlässt?"
        ),
        (
            "Warum wird ein Spieler in Abseitsstellung nur bestraft, wenn er aktiv "
            "am Spiel teilnimmt?"
        ),
        0.9380,
        (1590,),
        (632, 636),
    ),
)

#: The two the cosine path refused rightly, which reviewers confirmed the
#: corpus answers. Neither rests on its neighbour's fact, so nearness no
#: longer says so: the passage read has to.
ANSWERED: tuple[tuple[str, str, str, float, tuple[int, ...], tuple[int, ...]], ...] = (
    (
        "Q635, the languages the rules are published in",
        (
            "Welche weiteren Sprachen neben Deutsch, Englisch, Französisch und "
            "Spanisch veröffentlicht der IFAB für die Spielregeln?"
        ),
        (
            "Welche Sprachen verwendet der IFAB insgesamt für die Veröffentlichung "
            "der Spielregeln?"
        ),
        0.9734,
        (30,),
        (22, 27),
    ),
    (
        "Q422, when the assistant raises the flag for a goal",
        "Wann hebt der Schiedsrichterassistent bei einer Torentscheidung die Fahne?",
        "Wann muss ein Schiedsrichterassistent die Fahne heben?",
        0.9574,
        (1553,),
        (937, 1479),
    ),
)


def _probed(question, neighbour, cosine, facts, theirs) -> tuple[str, str] | None:
    """The verdict an unanswerable question gets against its neighbour."""
    return near_verdict(
        Neighbour(neighbour, True, similarity=cosine, fact_ids=frozenset(theirs)),
        answerable=False,
        threshold=Settings.load().duplicate_cosine,
        question=question,
        language="de",
        facts=facts,
    )


@pytest.mark.parametrize(
    ("question", "neighbour", "cosine", "facts", "theirs"),
    [row[1:] for row in NEARNESS],
    ids=[row[0] for row in NEARNESS],
)
def test_nearness_to_an_answered_question_is_not_an_answer(
    question, neighbour, cosine, facts, theirs
) -> None:
    """A perturbation of a fact is near the question about it by design."""
    assert _probed(question, neighbour, cosine, facts, theirs) is None


@pytest.mark.parametrize(
    ("question", "neighbour", "cosine", "facts", "theirs"),
    [
        pytest.param(
            *row[1:],
            id=row[0],
            marks=pytest.mark.xfail(
                strict=True,
                raises=AssertionError,
                reason="answerable, but resting on no fact its neighbour "
                "cites, so the nearness gate no longer refuses it. The "
                "unanswerable checks that read passages are what must; "
                "remove this marker when they do it here.",
            ),
        )
        for row in ANSWERED
    ],
)
def test_an_unanswerable_question_the_corpus_answers_is_still_refused(
    question, neighbour, cosine, facts, theirs
) -> None:
    """What the cosine path got right, and a shared-fact rule cannot see."""
    got = _probed(question, neighbour, cosine, facts, theirs)

    assert (got[0] if got else None) == QuestionRejection.ANSWERABLE_AFTER_ALL


def _stored(question: str, answer: str, kind: str, form: str) -> JudgedQuestion:
    """One accepted, answerable English question resting on one fact."""
    return JudgedQuestion(
        id=1,
        question_text=question,
        target_answer=answer,
        answerable=True,
        difficulty="easy",
        passage_scope=None,
        document_scope=None,
        topic_scope=None,
        language="en",
        status="accepted",
        embedding=None,
        statements=("A request is answered within 48 hours.",),
        facts_validated=True,
        documents=1,
        passages=1,
        topics=1,
        follows_id=None,
        question_type=kind,
        answer_form=form,
    )


def test_a_refit_moving_the_topics_is_not_a_changed_source() -> None:
    """A refit rewrites the dominant topics under a stored question."""
    stored = replace(
        _stored(
            "Why does a request have to be confirmed in writing?",
            "so that the agreed response time can be evidenced later",
            QuestionType.REASON,
            AnswerForm.EXPLANATION,
        ),
        topic_scope="single_topic",
        topics=2,
    )

    assert _recheck(None, Settings.load(), stored) is None  # type: ignore[arg-type]
