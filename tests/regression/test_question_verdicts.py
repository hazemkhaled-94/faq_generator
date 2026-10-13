"""The verdicts a re-check reaches on stored questions, pinned as a table.

Rows docs/bugs.md quotes, each beside the code re-verify has to store for it,
and one sound row. A rule added to the checker's type gates that re-verify
does not run leaves the stored release as it was.
"""

from __future__ import annotations

from dataclasses import replace
from typing import NamedTuple

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

    def nearest(self, embedding, before=None, excluding=(), language=None):
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


class Pair(NamedTuple):
    """A question, the accepted one the duplicate probe set it against, and why.

    Stored rows from the review of the football corpus, at the cosine the
    gate read, with what each of the two cites.
    """

    name: str
    question: str
    neighbour: str
    cosine: float
    answerable: bool
    neighbour_answerable: bool
    language: str
    facts: tuple[int, ...]
    passages: tuple[int, ...]
    neighbour_facts: tuple[int, ...]
    neighbour_passages: tuple[int, ...]
    #: What the reviewers found it to be: a twin is a duplicate.
    expected: str | None
    #: Why the rule does not reach that verdict, where it does not.
    missed: str | None


#: The false duplicates the cosine alone refused and the twins it let
#: through. A tier the citations set, and the question-word veto on every
#: tier, reach some of them; the rest are pinned as what the rule misses.
PAIRS: tuple[Pair, ...] = (
    Pair(
        "Q407 near Q364, no twin, and answerable against unanswerable",
        "In wie vielen Fällen darf ein Schiedsrichterassistent das Spielfeld betreten?",
        "Wie viele Schiedsrichterassistenten dürfen bei einem Spiel eingesetzt werden?",
        0.9455,
        True,
        False,
        "de",
        (1493, 1497),
        (383, 384),
        (521,),
        (116,),
        None,
        None,
    ),
    Pair(
        "Q446 near Q259, an own goal from a kick-off and from a throw-in",
        "Was wird entschieden, wenn ein Spieler beim Anstoss den Ball direkt ins eigene Tor schiesst?",
        "Was wird entschieden, wenn der Ball nach einem Einwurf direkt ins Tor des einwerfenden Teams geht?",
        0.9497,
        True,
        True,
        "de",
        (572,),
        (129, 175, 190, 193),
        (852, 880),
        (187, 193, 272),
        None,
        "shares a passage and its question word, above QUESTIONS_DUPLICATE_COSINE",
    ),
    Pair(
        "Q434 near Q383, no twin, and no citation in common",
        "Warum unterbricht der Schiedsrichter bei zusätzlichen oder unbefugten Personen auf dem Spielfeld das Spiel nicht immer sofort?",
        "Warum muss der Schiedsrichter auch abseits des Balls aufmerksam bleiben und eine zusätzliche Person auf dem Spielfeld in jedem Fall vom Feld weisen?",
        0.9423,
        True,
        True,
        "de",
        (364, 477),
        (85, 86, 107),
        (376, 1454),
        (87, 372),
        None,
        None,
    ),
    Pair(
        "Q656 near Q150, no twin, and answerable against unanswerable",
        "Warum muss bei Spielen mit VAR mindestens eine Review Area vorhanden sein?",
        "Warum darf der VAR die TV-Bilder nicht selbst in der Review Area ansehen, um die endgültige Entscheidung zu treffen?",
        0.9312,
        True,
        False,
        "de",
        (286,),
        (67, 69),
        (949,),
        (208,),
        None,
        None,
    ),
    Pair(
        "Q919 near Q897, no twin, and no citation in common",
        "Why does each team get one additional substitution opportunity in extra time?",
        "Why does the other team get the option of an additional substitute when one is used?",
        0.9575,
        True,
        True,
        "en",
        (1911,),
        (486,),
        (1798,),
        (457, 710),
        None,
        None,
    ),
    Pair(
        "Q1173 near Q992, no twin, and answerable against unanswerable",
        "Why is a substitute allowed to enter if the player being replaced is very close to or crossing the boundary line when the referee reaches the end of the countdown?",
        "Why would a substitute player ever be allowed to approach the referee during a match?",
        0.934,
        True,
        False,
        "en",
        (1674, 1684),
        (429, 431),
        (1712,),
        (438,),
        None,
        None,
    ),
    Pair(
        "Q421 near Q397, no twin, and answerable against unanswerable",
        "Wie handelt der Schiedsrichterassistent, wenn der Ball zwischen den Torpfosten die Torlinie eindeutig vollständig überquert hat und wenn er bei der Einwurfrichtung weitab unsicher ist?",
        "Wie verständigt der Schiedsrichter den Schiedsrichterassistenten, wenn der Ball die Torlinie nicht vollständig überquert hat, das Spiel aber unterbrochen wurde?",
        0.9531,
        True,
        False,
        "de",
        (1552, 1571),
        (398, 402),
        (1473,),
        (377,),
        None,
        None,
    ),
    Pair(
        "Q689 near Q202, two consequences listed in one passage",
        "Was darf der gemeldete Einwechselspieler insgesamt, wenn er ohne Information des Schiedsrichters anstelle eines gemeldeten Spielers beginnt oder in der Pause eingewechselt wird?",
        "Was passiert mit einem gemeldeten Einwechselspieler, gegen den der Schiedsrichter vor dem Wechsel nicht informiert wurde, wenn die erste Halbzeit vor Ablauf der Minute ausserhalb des Spielfelds endet?",
        0.9342,
        True,
        True,
        "de",
        (347,),
        (82,),
        (92, 348),
        (22, 82),
        None,
        "shares a passage and its question word, above QUESTIONS_DUPLICATE_COSINE",
    ),
    Pair(
        "Q269 near Q214, no twin, and no citation in common",
        "Warum zeigt der Schiedsrichter beim Abstoss einen Fünf-Sekunden-Countdown mit erhobener Hand an?",
        "Warum muss der Schiedsrichter mit dem Start des Fünf-Sekunden-Countdowns nicht warten, bis ein Spieler in Ballbesitz ist?",
        0.9315,
        True,
        True,
        "de",
        (1173,),
        (270,),
        (105, 108),
        (25, 436),
        None,
        None,
    ),
    Pair(
        "Q471 near Q256, answerable against unanswerable",
        "Wann ist beim Abstoss ein Eckstoss für das gegnerische Team fällig?",
        "Wann wird auf Eckstoss entschieden, wenn der Ball nach einem Einwurf ins Tor des gegnerischen Teams geht?",
        0.9384,
        True,
        False,
        "de",
        (874,),
        (192, 270, 271),
        (849,),
        (187,),
        None,
        None,
    ),
    Pair(
        "Q254 near Q253, a follow-up repeating its parent's fact",
        "Wodurch unterscheiden sich ein Sieg und ein Unentschieden?",
        "Warum endet das Spiel unentschieden?",
        0.8997,
        True,
        True,
        "de",
        (600, 601),
        (136,),
        (601,),
        (136,),
        QuestionRejection.DUPLICATE,
        None,
    ),
    Pair(
        "Q324 near Q319, one sending-off power, asked as the act and as the condition",
        "Was darf der Schiedsrichter tun, wenn ein Spieler oder Teamoffizieller vor dem Betreten des Spielfelds zum Spielbeginn ein feldverweiswürdiges Vergehen begeht?",
        "Unter welchen Umständen darf der Schiedsrichter einen Spieler von der Spielteilnahme ausschliessen, obwohl ungefährliche Schutzausrüstung erlaubt ist?",
        0.8924,
        True,
        True,
        "de",
        (460, 696),
        (104, 154),
        (396, 455),
        (92, 104),
        QuestionRejection.DUPLICATE,
        "shares only a passage, below QUESTIONS_DUPLICATE_COSINE, and asks with another word",
    ),
    Pair(
        "Q361 near Q360, a special case of the same rule",
        "Was muss bei Wettbewerbsbestimmungen zum Ersatz des Schiedsrichters durch den vierten Offiziellen klar geregelt sein?",
        "Was müssen Wettbewerbsbestimmungen zur Vertretung eines Spieloffiziellen eindeutig festhalten?",
        0.9037,
        True,
        True,
        "de",
        (517,),
        (115,),
        (515, 516),
        (115, 214),
        QuestionRejection.DUPLICATE,
        "shares only a passage, below QUESTIONS_DUPLICATE_COSINE",
    ),
    Pair(
        "Q497 near Q85, one sanction for excessive force",
        "Welche Disziplinarmassnahme gilt für eine Tätlichkeit mit übermässig hartem Vorgehen ohne Kampf um den Ball?",
        "Welche Disziplinarmassnahme trifft der Schiedsrichter, wenn er ein solches Foulspiel als übermässig hart einstuft?",
        0.9185,
        True,
        True,
        "de",
        (665, 746),
        (148, 165, 170),
        (766, 1386),
        (170, 346),
        QuestionRejection.DUPLICATE,
        "shares only a passage, below QUESTIONS_DUPLICATE_COSINE",
    ),
    Pair(
        "Q266 near Q258, one set of throw-in faults, cited from other passages",
        "Welche Folgen kann ein regelwidrig oder verzögert ausgeführter Einwurf haben?",
        "Welche Folgen führen bei einem Einwurf dazu, dass das gegnerische Team den Einwurf erhält?",
        0.9161,
        True,
        True,
        "de",
        (1083, 1171),
        (242, 269),
        (851, 855),
        (187, 188, 227, 262),
        QuestionRejection.DUPLICATE,
        "shares no cited passage or fact, below the near-identical bar",
    ),
    Pair(
        "Q651 near Q548, one list of permitted modifications",
        "Welchen Spielraum haben nationale Fussballverbände im Junioren-, Senioren-, Behinderten- und Breitenfussball bei den organisatorischen Spielregeln?",
        "Welche Regelvarianten sind im Junioren-, Senioren-, Behinderten- und Breitenfussball zulässig?",
        0.9288,
        True,
        True,
        "de",
        (46, 59),
        (13, 15),
        (60,),
        (15,),
        QuestionRejection.DUPLICATE,
        "its question word differs in form, which lifts it to the near-identical bar",
    ),
    Pair(
        "Q384 near Q382, a follow-up repeating the positioning rule",
        "Warum bewegt sich der Schiedsrichter in der Regel grossräumig und diagonal über den Platz?",
        "Wann müssen Schiedsrichter und erster Schiedsrichterassistent so positioniert sein, dass der Schiedsrichter das Spielgeschehen und den Assistenten im Blick hat und der Assistent auf Höhe des vorletzten Spielers des verteidigenden Teams steht?",
        0.8785,
        True,
        True,
        "de",
        (1450, 1454),
        (372,),
        (1453, 1455),
        (372, 373, 376, 380),
        QuestionRejection.DUPLICATE,
        "asks with another word, which lifts it to the near-identical bar",
    ),
    Pair(
        "Q536 near Q401, where the assistant goes, each with half of the answer",
        "Wohin begibt sich der Schiedsrichterassistent nach der Freigabe des Balls durch den Torhüter, wenn er ein Vergehen des Torhüters anzeigen muss?",
        "Wie geht der Schiedsrichterassistent bei der Freigabe des Balls durch den Torhüter vor?",
        0.9509,
        True,
        True,
        "de",
        (1483, 1562),
        (379, 400),
        (1480, 1481),
        (379, 382),
        QuestionRejection.DUPLICATE,
        "asks with another word, which lifts it to the near-identical bar",
    ),
    Pair(
        "Q1025 near Q1024, a follow-up repeating the head-cover rule",
        "Why must players of the same team wear the same head-cover colour?",
        "When must players' head covers match in colour?",
        0.945,
        True,
        True,
        "en",
        (1980, 1981),
        (502,),
        (1980, 1981),
        (502,),
        QuestionRejection.DUPLICATE,
        "asks with another word, which lifts it to the near-identical bar",
    ),
    Pair(
        "Q259 near Q256, an answerable and an unanswerable question on one sentence pair",
        "Was wird entschieden, wenn der Ball nach einem Einwurf direkt ins Tor des einwerfenden Teams geht?",
        "Wann wird auf Eckstoss entschieden, wenn der Ball nach einem Einwurf ins Tor des gegnerischen Teams geht?",
        0.9322,
        True,
        False,
        "de",
        (852, 880),
        (187, 193, 272),
        (849,),
        (187,),
        QuestionRejection.DUPLICATE,
        "answerable against unanswerable is never a duplicate; the unanswerable checks own Q256",
    ),
)


@pytest.mark.parametrize(
    "pair",
    [
        pytest.param(
            pair,
            id=pair.name,
            marks=()
            if pair.missed is None
            else pytest.mark.xfail(
                strict=True, raises=AssertionError, reason=pair.missed
            ),
        )
        for pair in PAIRS
    ],
)
def test_the_duplicate_probe_tells_a_twin_from_a_neighbour(pair: Pair) -> None:
    """What the gate makes of a pair, by what the two cite and ask with."""
    settings = Settings.load()

    got = near_verdict(
        Neighbour(
            pair.neighbour,
            pair.neighbour_answerable,
            similarity=pair.cosine,
            fact_ids=frozenset(pair.neighbour_facts),
            language=pair.language,
            passage_ids=frozenset(pair.neighbour_passages),
        ),
        answerable=pair.answerable,
        threshold=settings.duplicate_cosine,
        shared_threshold=settings.duplicate_shared_cosine,
        question=pair.question,
        language=pair.language,
        passages=pair.passages,
        facts=pair.facts,
    )

    assert (got[0] if got else None) == pair.expected, got


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
                "cites; the settles judgement (stream S4) is meant to catch it "
                "by reading the probe passages",
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
