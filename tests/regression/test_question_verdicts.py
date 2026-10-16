"""The verdicts a re-check reaches on stored questions, pinned as a table.

Rows docs/bugs.md quotes, each beside the code re-verify has to store for it,
and one sound row. A rule added to the checker's type gates that re-verify
does not run leaves the stored release as it was.

`LISTED_ROWS` and `ROUND_TRIP_ROWS` are the exception: stored keys read as
the round trip reads them, which re-verify does not repeat.
"""

from __future__ import annotations

from dataclasses import replace
from typing import NamedTuple

import pytest

from database.qa_generator import AnswerForm, QuestionRejection, QuestionType
from question_generation.config import Settings
from question_generation.gates import (
    BOUNDS,
    adds_up,
    agrees,
    counts_something_else,
    fitting,
    incomplete,
    near_verdict,
    structural,
)
from question_generation.models import JudgedQuestion, Neighbour
from question_generation.service import _recheck
from question_generation.types import spec

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
        "a why question typed as a procedure is held as a reason",
        "Why does the release draw whole threads?",
        "because a follow-up reads only after the turn it follows",
        QuestionType.PROCEDURE,
        AnswerForm.EXPLANATION,
        None,
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

    def nearest(self, embedding, before=None, excluding=(), **_):
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
        # Passes only because `interrogatives` reads no question word in
        # `Wodurch`, so the question-word veto abstains: B21 territory.
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
        "shares only a passage, below QUESTIONS_DUPLICATE_COSINE",
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
        "shares only a passage, below QUESTIONS_DUPLICATE_COSINE",
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


#: Rows this corpus stored, read in their own language: (name, question,
#: answer, language, statements, type, form, expected code or None).
#: `statements` holds what a row cites where a gate reads it, and is empty
#: where none does.
STORED_ROWS: tuple[
    tuple[str, str, str, str, tuple[str, ...], str, str, str | None], ...
] = (
    (
        "Q70: a count its cited statement states",
        (
            "Wie viele Verwarnungen gibt es für zwei separate verwarnungswürdige "
            "Vergehen, auch wenn sie unmittelbar aufeinanderfolgen?"
        ),
        "zwei Verwarnungen",
        "de",
        (
            "Ein Spieler wird bei Verzögerung der Spielfortsetzung verwarnt.",
            (
                "Der Auszug listet die Vergehen auf, für die Spieler, "
                "Einwechselspieler und ausgewechselte Spieler verwarnt werden. "
                "Außerdem wird klargestellt, dass bei zwei separaten "
                "verwarnungswürdigen Vergehen jeweils eine eigene Verwarnung "
                "ausgesprochen wird, auch wenn sie direkt nacheinander erfolgen."
            ),
        ),
        QuestionType.FACTOID,
        AnswerForm.VALUE,
        None,
    ),
    (
        "Q71: a count its cited statement states",
        (
            "Wie viele Verwarnungen gibt es für zwei unmittelbar "
            "aufeinanderfolgende separate verwarnungswürdige Vergehen wie die "
            "Verzögerung der Spielfortsetzung und ein weiteres solches Vergehen?"
        ),
        "zwei Verwarnungen",
        "de",
        (
            "Ein Spieler wird bei Verzögerung der Spielfortsetzung verwarnt.",
            (
                "Der Auszug listet die Vergehen auf, für die Spieler, "
                "Einwechselspieler und ausgewechselte Spieler verwarnt werden. "
                "Außerdem wird klargestellt, dass bei zwei separaten "
                "verwarnungswürdigen Vergehen jeweils eine eigene Verwarnung "
                "ausgesprochen wird, auch wenn sie direkt nacheinander erfolgen."
            ),
        ),
        QuestionType.FACTOID,
        AnswerForm.VALUE,
        None,
    ),
    (
        "Q1384: a count its cited statement states",
        (
            "How many concussion substitution protocols were used during the "
            "trials before a single protocol was approved for competitions?"
        ),
        "two different protocols",
        "en",
        (
            (
                "Additional permanent concussion substitutions must accord with "
                "the protocol listed under 'Notes and modifications'."
            ),
            "Two different protocols were used during the trials.",
        ),
        QuestionType.FACTOID,
        AnswerForm.VALUE,
        None,
    ),
    (
        "Q598: a which question answered with the count of its facts",
        (
            "Welche zwei Ausrüstungs- oder Regelvorgaben werden für den "
            "Schiedsrichter und den Umgang mit beleidigendem Verhalten genannt?"
        ),
        "zwei",
        "de",
        (
            (
                "Regel 12 verlangt Disziplinarmassnahmen gegen einen Spieler bei "
                "anstössigen, beleidigenden oder schmähenden Äusserungen oder "
                "Handlungen."
            ),
            (
                "Der Schiedsrichter muss über einen Notizblock oder ein sonstiges "
                "Mittel für Aufzeichnungen über das Spiel verfügen."
            ),
        ),
        QuestionType.AGGREGATION,
        AnswerForm.VALUE,
        QuestionRejection.MALFORMED,
    ),
    (
        "Q258: a which question answered with the count of its facts",
        (
            "Welche Folgen führen bei einem Einwurf dazu, dass das gegnerische "
            "Team den Einwurf erhält?"
        ),
        "zwei Fälle",
        "de",
        (
            (
                "Bei Verzögerung eines Einwurfs für das eigene Team wird auf "
                "Einwurf für das gegnerische Team entschieden."
            ),
            (
                "Das gegnerische Team führt den Einwurf aus, wenn der Einwurf "
                "nicht korrekt ausgeführt wird."
            ),
        ),
        QuestionType.AGGREGATION,
        AnswerForm.VALUE,
        QuestionRejection.MALFORMED,
    ),
    (
        "Q790: a count no cited statement states",
        (
            "How many player actions are expressly forbidden in these rules "
            "about safety and injuries?"
        ),
        "2",
        "en",
        (
            "A player must not use dangerous equipment.",
            "An injured player may not be treated on the field of play.",
        ),
        QuestionType.AGGREGATION,
        AnswerForm.VALUE,
        QuestionRejection.MALFORMED,
    ),
    (
        "Q280: a comparison split at its und, not at the wenn clause",
        "Wodurch unterscheiden sich Anstoss und Elfmeter, wenn der Ball beschädigt wird?",
        (
            "Wiederholung der Spielfortsetzung beim Anstoss und Wiederholung des "
            "Elfmeters, wenn der Ball sich nach vorne bewegt"
        ),
        "de",
        (),
        QuestionType.COMPARISON,
        AnswerForm.EXPLANATION,
        None,
    ),
    (
        "Q845: two definitions, one carrying a comparative of its own",
        (
            "How do an electronic performance and tracking system and excessive "
            "force differ?"
        ),
        (
            "an electronic performance and tracking system records data about the "
            "physical performance of a player, excessive force is using more force "
            "than is necessary"
        ),
        "en",
        (),
        QuestionType.COMPARISON,
        AnswerForm.EXPLANATION,
        QuestionRejection.WRONG_TYPE,
    ),
    (
        "Q1469: two definitions sharing an incidental word",
        "How do the technical area and a shirt differ?",
        (
            "a defined area in stadiums for team officials, part of a team's "
            "uniform worn over a player's upper body"
        ),
        "en",
        (),
        QuestionType.COMPARISON,
        AnswerForm.EXPLANATION,
        QuestionRejection.WRONG_TYPE,
    ),
    (
        "Q439: a comparison answered in one piece",
        (
            "Was können zusätzliche Schiedsrichterassistenten anzeigen, wenn es um "
            "das vollständige Überqueren der Torlinie durch den Ball geht?"
        ),
        "dass der Ball die Torlinie vollständig überquert hat",
        "de",
        (),
        QuestionType.COMPARISON,
        AnswerForm.EXPLANATION,
        QuestionRejection.WRONG_TYPE,
    ),
    (
        "Q82: two descriptions of one zone, one mis-tagged as a comparative",
        (
            "Wodurch unterscheiden sich ein Einwechselspieler und ein "
            "Teamoffizieller in Bezug auf technische Zone und Disziplinarmassnahme?"
        ),
        (
            "Person in der technischen Zone, Ermahnung bei gelegentlichem "
            "Verlassen der eigenen technischen Zone ohne weiteres Vergehen"
        ),
        "de",
        (),
        QuestionType.COMPARISON,
        AnswerForm.LIST,
        QuestionRejection.WRONG_TYPE,
    ),
    (
        "Q1246: the question's two sides said back, its comparative included",
        (
            "How does touching the ball with the hand or arm deliberately differ "
            "from touching it when the hand or arm has made the body unnaturally "
            "bigger?"
        ),
        (
            "deliberately touching the ball with the hand or arm, touching it when "
            "the hand or arm has made the body unnaturally bigger"
        ),
        "en",
        (),
        QuestionType.COMPARISON,
        AnswerForm.EXPLANATION,
        QuestionRejection.WRONG_TYPE,
    ),
    (
        "Q987: `cautioned` decides it",
        (
            "What does a referee do if a player refuses to comply with an order to "
            "remove dangerous or unauthorised equipment?"
        ),
        "The player must be cautioned.",
        "en",
        (),
        QuestionType.DEFINITION,
        AnswerForm.EXPLANATION,
        None,
    ),
    (
        "Q1021: `permitted` decides it",
        "What are sports spectacles treated as in the rules on equipment?",
        "Sports spectacles are permitted.",
        "en",
        (),
        QuestionType.DEFINITION,
        AnswerForm.EXPLANATION,
        None,
    ),
    (
        "Q1256: `caution` decides it",
        (
            "What action must a referee take if a player kicks or carries the ball "
            "away to delay the restart of play?"
        ),
        "The referee must caution the player.",
        "en",
        (),
        QuestionType.IMPLICATION,
        AnswerForm.EXPLANATION,
        None,
    ),
    (
        "Q1269: `recorded as missed` decides it",
        (
            "What happens to a penalty shoot-out kick if the ball hits the kicker's "
            "non-kicking foot or leg immediately after the kick and still does not "
            "enter the goal?"
        ),
        "The kick is recorded as missed.",
        "en",
        (),
        QuestionType.CONSEQUENCE,
        AnswerForm.EXPLANATION,
        None,
    ),
    (
        "Q1142: `retaken` decides it",
        (
            "How is a free kick restarted if an opponent is too close when the ball is "
            "kicked and clearly moves?"
        ),
        "The kick is retaken.",
        "en",
        (),
        QuestionType.APPLICATION,
        AnswerForm.EXPLANATION,
        None,
    ),
    (
        "Q1110: `disallowed` decides it",
        (
            "What happens to a goal once play has restarted after the kick-off that "
            "begins the next half or restarts play after a goal?"
        ),
        "The goal cannot be disallowed after play has restarted.",
        "en",
        (),
        QuestionType.DEFINITION,
        AnswerForm.EXPLANATION,
        None,
    ),
    (
        "Q965: `assist` decides it",
        "How do other match officials relate to the referee on the field of play?",
        "They assist the referee, who operates on the field of play.",
        "en",
        (),
        QuestionType.IMPLICATION,
        AnswerForm.EXPLANATION,
        None,
    ),
    (
        "Q889: `decide` decides it",
        (
            "What happens with reporting to the appropriate authorities when a player "
            "receives a temporary dismissal instead of a caution?"
        ),
        (
            "Competitions will decide whether temporary dismissals must be reported to "
            "the appropriate authorities."
        ),
        "en",
        (),
        QuestionType.CONSEQUENCE,
        AnswerForm.EXPLANATION,
        None,
    ),
    (
        "Q502: `wiederholt` decides it",
        (
            "Was geschieht bei einem Strafstoss, wenn eine Drittperson den Ball "
            "während seiner Vorwärtsbewegung berührt?"
        ),
        "Der Strafstoss wird wiederholt.",
        "de",
        (),
        QuestionType.DEFINITION,
        AnswerForm.EXPLANATION,
        None,
    ),
    (
        "Q654: `respektvoll und angemessen` decides it",
        "Wie müssen sich die Kapitäne dem Schiedsrichter gegenüber verhalten?",
        (
            "Die Kapitäne müssen sich dem Schiedsrichter gegenüber respektvoll und "
            "angemessen verhalten."
        ),
        "de",
        (),
        QuestionType.IMPLICATION,
        AnswerForm.EXPLANATION,
        None,
    ),
    (
        "Q226: `rechtwinklig` decides it",
        "Wie verlaufen die beiden Linien des Torraums zur Torlinie?",
        "rechtwinklig zur Torlinie",
        "de",
        (),
        QuestionType.FACTOID,
        AnswerForm.VALUE,
        None,
    ),
    (
        "an elided compound naming four kinds (Q1889)",
        "Für welche Fussballbereiche gilt die Kapitänsregelung mit dem 4-Meter-Abstand zum Schiedsrichter?",
        "Junioren-, Senioren-, Behinderten- und Breitenfussball",
        "de",
        (
            "Die Bestimmungen gelten nur für den Junioren-, Senioren-, Behinderten- und Breitenfussball.",
        ),
        QuestionType.ENUMERATION,
        AnswerForm.LIST,
        None,
    ),
    (
        "a short answer whose new word is its polarity (Q1905)",
        "Welche Disziplinarmassnahme gilt beim Vereiteln einer offensichtlichen Torchance, wenn das gegnerische Team nach Vorteil ein Tor erzielt?",
        "keine Disziplinarmassnahme",
        "de",
        (
            "Ein Spieler wird wegen unsportlichen Verhaltens verwarnt, wenn er eine offensichtliche Torchance vereitelt, außer das gegnerische Team erzielt infolge des Vorteils ein Tor.",
            "Wenn das gegnerische Team infolge des Vorteils ein Tor erzielt, wird keine Disziplinarmassnahme verhängt.",
        ),
        QuestionType.FACTOID,
        AnswerForm.VALUE,
        None,
    ),
    (
        "a who answered by the party it names (Q2057)",
        "Wenn ein Videoassistent dem Schiedsrichter widerspricht, wer trifft dann die endgültige Entscheidung?",
        "Der Schiedsrichter trifft immer die endgültige Entscheidung.",
        "de",
        (
            "- Für Spiele können verschiedene Spieloffizielle eingesetzt werden, darunter VAR und AVAR.\n- Der Schiedsrichter trifft immer die endgültige Entscheidung.\n- Spieloffizielle auf dem Spielfeld unterstützen den Schiedsrichter und melden Fehlverhalten.\n- VAR und AVAR sind Video-Spieloffizielle und unterstützen gemäß VAR-Protokoll.\n- Der Schiedsrichter kann Offizielle bei Fehlverhalten ihres Amtes entheben.\n- Spieloffizielle kontrollieren Spielfeld, Bälle, Ausrüstung und notieren relevante Ereignisse.",
            "Der VAR und der AVAR sind die Video-Spieloffiziellen (VMO).",
        ),
        QuestionType.APPLICATION,
        AnswerForm.EXPLANATION,
        None,
    ),
)


@pytest.mark.parametrize(
    ("question", "answer", "language", "statements", "kind", "form", "expected"),
    [row[1:] for row in STORED_ROWS],
    ids=[row[0] for row in STORED_ROWS],
)
def test_a_stored_question_is_rechecked_in_its_own_language(
    question: str,
    answer: str,
    language: str,
    statements: tuple[str, ...],
    kind: str,
    form: str,
    expected: str | None,
) -> None:
    """What re-verify stores for a row, read in its language over what it cites."""
    stored = replace(
        _stored(question, answer, kind, form),
        language=language,
        statements=statements,
    )

    failed = _recheck(None, Settings.load(), stored)  # type: ignore[arg-type]

    assert (failed[0] if failed else None) == expected, failed


#: The passage Q741 cites: every offence a player is cautioned for.
_CAUTIONS = (
    "A player is cautioned if guilty of:\n"
    "- delaying the restart of play (as outlined below in 'Delaying the restart "
    "of play')\n"
    "- dissent by word or action\n"
    "- entering, re-entering or deliberately leaving the field of play without "
    "the referee's permission\n"
    "- failing to respect the required distance when play is restarted with a "
    "dropped ball, corner kick, free kick or throw-in\n"
    "- persistent offences (no specific number or pattern of offences "
    "constitutes 'persistent')\n"
    "- unsporting behaviour\n"
    "- entering the referee review area (RRA)\n"
    "- excessively using the 'review' (TV screen) signal\n"
    "A substitute or substituted player is cautioned if guilty of:\n"
    "- delaying the restart of play\n"
    "- dissent by word or action\n"
    "- entering or re-entering the field of play without the referee's "
    "permission\n"
    "- unsporting behaviour\n"
    "- entering the referee review area (RRA)\n"
    "- excessively using the 'review' (TV screen) signal\n"
    "Where two separate cautionable offences are committed (even in close "
    "proximity), they should result in two cautions, for example if a player "
    "enters the field of play without the required permission and commits a "
    "reckless tackle or stops a promising attack with a foul/handball, etc."
)

#: Keys this corpus stored, beside the passage they cite: (name, type, key,
#: passage, language, whether the key names much less than the passage).
#: Read as the round trip reads them - in the form `fitting` finds among the
#: type's, against the most the cited passage gives back.
LISTED_ROWS: tuple[tuple[str, str, str, str, str, bool], ...] = (
    (
        "Q741: two of the offences a player is cautioned for",
        QuestionType.CONDITION,
        "for dissent by word or action, and for persistent offences",
        _CAUTIONS,
        "en",
        True,
    ),
    (
        "Q304: both of the two cases its passage names",
        QuestionType.CONDITION,
        (
            "bei einer Auswechslung des ernannten Spielers und bei einem "
            "Feldverweis des ernannten Spielers"
        ),
        (
            "- Bei einer Auswechslung oder einem Feldverweis des ernannten "
            "Spielers muss ein anderer Spieler ernannt werden."
        ),
        "de",
        False,
    ),
    (
        "Q663: both of the two conditions its passage names",
        QuestionType.CONDITION,
        "unter Aufsicht des Schiedsrichters, wenn sie die Anforderungen von Regel 2 erfüllen",
        (
            "Zusätzliche Bälle dürfen um das Spielfeld herum bereitgehalten "
            "werden, wenn sie die Anforderungen von Regel 2 erfüllen und ihr "
            "Einsatz unter Aufsicht des Schiedsrichters erfolgt.\n"
        ),
        "de",
        False,
    ),
)


@pytest.mark.parametrize(
    ("kind", "key", "passage", "language", "expected"),
    [row[1:] for row in LISTED_ROWS],
    ids=[row[0] for row in LISTED_ROWS],
)
def test_a_stored_key_is_held_to_the_list_its_type_asked_for(
    kind: str, key: str, passage: str, language: str, expected: bool
) -> None:
    """A key naming part of its cited list is incomplete; a whole one is not."""
    form, failed = fitting(key, spec(kind).forms, BOUNDS, language)

    assert failed is None
    assert incomplete(passage, key, language, form) is expected, form


#: The sentence P441 holds, which Q1001 and Q1002 were written from. The
#: verifier is told to answer in the passage's words, so this is the best
#: recovery either could get.
_P441 = (
    "Any incident in which more than one unauthorised player from a team enters "
    "the captain-only zone must be reported to the appropriate authorities after "
    "the match"
)

#: Keys this corpus stored, against what the passage they cite gives back:
#: (name, question, recovery, key, language). Each agrees.
ROUND_TRIP_ROWS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "Q1001: a report for must be reported",
        (
            "What must happen after a match if more than one unauthorised player "
            "from a team enters the captain-only zone?"
        ),
        _P441,
        "a report to the appropriate authorities",
        "en",
    ),
    (
        "Q1002: a report for must be reported",
        (
            "What must happen after the match if more than one unauthorised "
            "player from a team enters the captain-only zone?"
        ),
        _P441,
        "a report to the appropriate authorities",
        "en",
    ),
)


@pytest.mark.parametrize(
    ("question", "recovered", "key", "language"),
    [row[1:] for row in ROUND_TRIP_ROWS],
    ids=[row[0] for row in ROUND_TRIP_ROWS],
)
def test_a_stored_value_key_agrees_with_the_sentence_it_was_written_from(
    question: str, recovered: str, key: str, language: str
) -> None:
    """A value compared on its verbs too meets the passage's own sentence."""
    assert agrees(recovered, key, language, AnswerForm.VALUE, question=question)


#: The passage Q117 and Q118 count from: four things a ball may rebound off,
#: and not one figure.
_P143 = (
    "- sich einen Vorteil verschafft, indem er den Ball spielt oder einen Gegner "
    "beeinflusst, nachdem der Ball:\n- von einem Torpfosten, der Querlatte, einem "
    "Spieloffiziellen oder einem Gegner zurückgeprallt oder abgelenkt worden ist,\n"
    "- bei einer absichtlichen Torverhinderungsaktion des Gegners abgewehrt wurde."
)


@pytest.mark.parametrize("name", ["Q117", "Q118"])
def test_a_stored_count_of_what_a_passage_lists_is_left_to_the_model(
    name: str,
) -> None:
    """`4` counts what P143 lists, which no sum of its figures could find."""
    assert adds_up("4", [_P143]) is None, name


#: Questions this corpus stored that ask one thing through a clause opened by
#: a question word: (name, question, answer, language, form). None is a
#: second question.
EMBEDDED_ROWS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "Q1141: differ in where",
        "How do free kicks and penalty kicks differ in where they are taken from?",
        (
            "free kicks from the place of the offence with stated exceptions, penalty "
            "kicks from the penalty mark"
        ),
        "en",
        AnswerForm.LIST,
    ),
    (
        "Q1089: does where",
        (
            "Why does where the offence was committed matter when deciding whether to "
            "apply advantage?"
        ),
        (
            "Because the closer to the opponent's goal the offence was committed, the "
            "more effective the advantage can be."
        ),
        "en",
        AnswerForm.EXPLANATION,
    ),
    (
        "Q1294: differ in where",
        (
            "How do the penalty area and the corner area differ in where they are "
            "defined on the field?"
        ),
        (
            "the area bounded by the lines and the goal line, the corner area nearest "
            "to the point where the ball passed over the goal line"
        ),
        "en",
        AnswerForm.LIST,
    ),
    (
        "Q1295: in where",
        (
            "What sets the penalty area apart from the corner area in where the ball "
            "is placed?"
        ),
        (
            "the area bounded by the lines and the goal line, the corner area nearest "
            "to where the ball passed over the goal line"
        ),
        "en",
        AnswerForm.LIST,
    ),
    (
        "Q1039: differ in who",
        (
            "How do a kick-off and a goal kick differ in who last touched the ball "
            "before each restart?"
        ),
        (
            "a kick-off follows a goal, and a goal kick follows the ball last touching "
            "an attacking player"
        ),
        "en",
        AnswerForm.LIST,
    ),
    (
        "Q710: darin, wen",
        (
            "Wie unterscheiden sich Antäuschen und Ablenken darin, wen sie verwirren "
            "sollen?"
        ),
        "Antäuschen einen Gegner, Ablenken eine Person",
        "de",
        AnswerForm.VALUE,
    ),
    (
        "Q915: on who",
        (
            "What is the rule on who may convey tactical instructions from the "
            "technical area?"
        ),
        (
            "Only one person at a time is authorised to convey tactical instructions "
            "from the technical area."
        ),
        "en",
        AnswerForm.EXPLANATION,
    ),
    (
        "Q210: ab, wann",
        (
            "Wovon hängt ab, wann ein Spieler nach der Minute ausserhalb des "
            "Spielfelds zurückkehren darf?"
        ),
        (
            "vom Ende der Minute, das der Schiedsrichter bestimmt, und von der "
            "Erlaubnis des Schiedsrichters"
        ),
        "de",
        AnswerForm.LIST,
    ),
)


@pytest.mark.parametrize(
    ("question", "answer", "language", "form"),
    [row[1:] for row in EMBEDDED_ROWS],
    ids=[row[0] for row in EMBEDDED_ROWS],
)
def test_a_stored_question_with_an_embedded_question_word_is_not_compound(
    question: str, answer: str, language: str, form: str
) -> None:
    """Only a question word a conjunction introduces is a second question."""
    failed, _ = structural(
        question_text=question,
        target_answer=answer,
        answerable=True,
        language=language,
        forms=(form,),
        bounds=BOUNDS,
    )

    assert (failed[0] if failed else None) != QuestionRejection.COMPOUND, failed


#: The passage Q1296 cites: a height and a distance, in metres and in feet.
_P469 = (
    "A flagpost, at least 1.5 m (5 ft) high, with a non-pointed top and a flag "
    "must be placed at each corner.\nFlagposts may be placed at each end of the "
    "halfway line, at least 1m (1yd) outside the touchline."
)


def test_a_stored_count_over_figures_of_something_else_is_left_to_the_model() -> None:
    """Q1296 counts corner flagposts, and P469's figures count metres and feet."""
    assert counts_something_else(
        "How many corner flagposts must be placed around the field of play?",
        [_P469],
        "en",
    )


#: Stored rows the gates still misjudge, each with the verdict it should get
#: and why it does not: (name, question, answer, language, type, form, the
#: right code, reason). Strict, so a fix that reaches one says so.
MISJUDGED_ROWS: tuple[tuple[str, str, str, str, str, str, str | None, str], ...] = (
    (
        "Q1268",
        (
            "How is the dropped-ball position decided when play is stopped for contact "
            "with a match official or an outside agent?"
        ),
        (
            "The ball is dropped at the position of the interference when there is "
            "interference by a match official. The ball is dropped where the contact "
            "occurred if play is stopped because the ball makes contact with an "
            "outside agent."
        ),
        "en",
        QuestionType.PROCEDURE,
        AnswerForm.EXPLANATION,
        None,
        (
            "its deciding words are too small a share of an answer repeating the "
            "question's setup"
        ),
    ),
    (
        "Q1410",
        (
            "What happens if a player, substitute, substituted player or team official "
            "enters the video operation room?"
        ),
        (
            "A player, substitute, substituted player or team official who enters the "
            "video operation room will be sent off."
        ),
        "en",
        QuestionType.PROCEDURE,
        AnswerForm.LIST,
        None,
        (
            "its one deciding verb is too small a share of an answer repeating the "
            "question's parties"
        ),
    ),
    (
        "Q140",
        (
            "Worin unterscheidet sich die Rolle des VAR von der des Schiedsrichters "
            "bei Entscheidungen?"
        ),
        "beratende Rolle des VAR und endgültige Entscheidung des Schiedsrichters",
        "de",
        QuestionType.COMPARISON,
        AnswerForm.LIST,
        None,
        "the sides share no word the question lacks: its axis is in the question",
    ),
    (
        "Q152",
        (
            "Wodurch unterscheiden sich bei VAR-Entscheidungen subjektive und "
            "objektive Fälle?"
        ),
        (
            "bei subjektiven Fällen ist ein OFR sinnvoll, bei objektiven erfolgt "
            "üblicherweise eine VAR-Konsultation"
        ),
        "de",
        QuestionType.COMPARISON,
        AnswerForm.EXPLANATION,
        None,
        "only one side names a subject of the question, as the parser lemmatises it",
    ),
    (
        "Q48",
        (
            "Worin unterscheidet sich das bei unabsichtlichem und absichtlichem "
            "Handspiel zur Vereitelung einer offensichtlichen Torchance?"
        ),
        (
            "Verwarnung bei unabsichtlichem Handspiel mit Strafstoss und Feldverweis "
            "bei absichtlichem Handspiel"
        ),
        "de",
        QuestionType.COMPARISON,
        AnswerForm.LIST,
        None,
        "the sides share no word the question lacks: its axis is in the question",
    ),
    (
        "Q807",
        (
            "How do verbal offences and offences against outside agents differ in the "
            "restart?"
        ),
        "indirect free kick, dropped ball",
        "en",
        QuestionType.COMPARISON,
        AnswerForm.EXPLANATION,
        None,
        "its two values name neither subject and share no word the question lacks",
    ),
    (
        "Q385",
        (
            "Worin unterscheidet sich die Spielfortsetzung bei einer eingreifenden "
            "Drittperson von der bei einem eingreifenden Teamangehörigen des "
            "erzielenden Teams?"
        ),
        "Schiedsrichterball und direkter Freistoss",
        "de",
        QuestionType.COMPARISON,
        AnswerForm.LIST,
        None,
        "the sides share no word the question lacks: its axis is in the question",
    ),
    (
        "Q220",
        (
            "Wie unterscheiden sich die zulässigen Breiten von Spielfeldlinien und von "
            "Torpfosten mit Querlatte?"
        ),
        (
            "höchstens 12 cm bei den Spielfeldlinien und höchstens 12 cm bei "
            "Torpfosten und Querlatte"
        ),
        "de",
        QuestionType.COMPARISON,
        AnswerForm.LIST,
        None,
        "the sides share no word the question lacks: its axis is in the question",
    ),
    (
        "Q469",
        (
            "Wodurch unterscheiden sich Eingreifen ins Spiel und Beeinflussung eines "
            "Gegners?"
        ),
        "Spielen oder Berühren des Balls, Hindern oder Beeinflussen eines Gegners",
        "de",
        QuestionType.COMPARISON,
        AnswerForm.LIST,
        None,
        "only one side names a subject of the question, as the parser lemmatises it",
    ),
    (
        "Q480",
        (
            "Wodurch unterscheiden sich ein Handspielvergehen bei absichtlicher "
            "Ballberührung und eines bei unnatürlicher Vergrösserung des Körpers?"
        ),
        (
            "absichtliche Ballberührung mit der Hand oder dem Arm und unnatürliche "
            "Vergrösserung des Körpers durch die Hand- oder Armhaltung"
        ),
        "de",
        QuestionType.COMPARISON,
        AnswerForm.LIST,
        None,
        "the sides share no word the question lacks: its axis is in the question",
    ),
    (
        "Q595",
        (
            "Worin unterscheiden sich die Anforderungen an Schienbeinschoner und "
            "EPTS-Technologie?"
        ),
        (
            "geeignetes Material bei Schienbeinschonern und Erfüllung des "
            "FIFA-Qualitätsprogramms bei EPTS-Technologie"
        ),
        "de",
        QuestionType.COMPARISON,
        AnswerForm.LIST,
        None,
        "the sides share no word the question lacks: its axis is in the question",
    ),
    (
        "Q1376",
        (
            "What distinguishes the assistant referee's role from the fourth "
            "official's in a requested substitution?"
        ),
        (
            "signalling the request to the referee at the next stoppage, supervising "
            "the substitution procedure"
        ),
        "en",
        QuestionType.COMPARISON,
        AnswerForm.EXPLANATION,
        None,
        "its two values name neither subject and share no word the question lacks",
    ),
    (
        "Q700",
        (
            "Worin unterscheiden sich die Änderungen beim Zeichen für Strafstoss und "
            "beim Zeichen für Eckstoss?"
        ),
        "geändertes Zeichen für Strafstoss und geändertes Zeichen für Eckstoss",
        "de",
        QuestionType.COMPARISON,
        AnswerForm.LIST,
        QuestionRejection.WRONG_TYPE,
        (
            "both sides share geändert, which the question carries only as the noun "
            "Änderungen"
        ),
    ),
)


@pytest.mark.parametrize(
    ("question", "answer", "language", "kind", "form", "expected"),
    [
        pytest.param(
            *row[1:7],
            id=row[0],
            marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason=row[7]),
        )
        for row in MISJUDGED_ROWS
    ],
)
def test_a_stored_question_the_gates_still_misjudge(
    question: str,
    answer: str,
    language: str,
    kind: str,
    form: str,
    expected: str | None,
) -> None:
    """The verdict re-verify should store, which it does not yet."""
    stored = replace(_stored(question, answer, kind, form), language=language)

    failed = _recheck(None, Settings.load(), stored)  # type: ignore[arg-type]

    assert (failed[0] if failed else None) == expected, failed
