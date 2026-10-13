"""Which stored `reason` questions rested on evidence that states a reason.

The cited evidence of reviewed rows, read the way the deal now reads a fact
before it hands a `reason` slot anything. A row reading False would not be
dealt as a `reason` today; its slot takes another kind.
"""

from __future__ import annotations

import pytest

from question_generation.gates import states_a_reason

pytestmark = pytest.mark.nlp

#: (question id, language, cited evidence or the sentence of it that
#: decides, whether it states a reason).
ROWS: tuple[tuple[int, str, str, bool], ...] = (
    # Circular: the rule restated as its own reason.
    (
        42,
        "de",
        (
            "Mit einem Anstoss werden die beiden Halbzeiten der regulären Spielzeit "
            "und der Verlängerung begonnen sowie das Spiel nach einem Tor fortgesetzt."
        ),
        False,
    ),
    # A list of sanctions, which says what and never why.
    (
        77,
        "de",
        (
            "Spieler, Einwechselspieler oder ausgewechselte Spieler, die eines der "
            "folgenden Vergehen begehen, werden des Feldes verwiesen:\n- grobes "
            "Foulspiel\n- Tätlichkeit\n- zweite Verwarnung im selben Spiel\n- "
            "Betreten des Video Operation Room (VOR)"
        ),
        False,
    ),
    # Invalid: the reason given was invented.
    (
        191,
        "de",
        (
            "Die maximal zulässige Anzahl Auswechslungen bei offiziellen Wettbewerben "
            "wird von der FIFA, der Konföderation oder dem nationalen Fussballverband "
            "festgelegt und darf fünf nicht übersteigen."
        ),
        False,
    ),
    # A condition, `indem`, and no purpose.
    (
        468,
        "de",
        (
            "Ein Spieler, der sich zum Zeitpunkt, in dem ein Mitspieler den Ball "
            "spielt oder berührt, in einer Abseitsstellung befindet, wird nur "
            "bestraft, wenn er aktiv am Spiel teilnimmt, indem er ins Spiel eingreift."
        ),
        False,
    ),
    # `For the purposes of` names a scope.
    (
        1248,
        "en",
        (
            "For the purposes of determining offside, the upper boundary of the arm "
            "is in line with the bottom of the armpit."
        ),
        False,
    ),
    # Sound, and stated.
    (
        178,
        "de",
        (
            "Zu diesem Zweck haben Wettbewerbe die Möglichkeit, zusätzliche dauerhafte "
            "Auswechslungen wegen Gehirnerschütterung zu erlauben."
        ),
        True,
    ),
    (
        384,
        "de",
        (
            "Der Schiedsrichter steht möglichst nahe beim Spielgeschehen, um dieses "
            "optimal zu verfolgen, ohne das Spiel zu beeinflussen."
        ),
        True,
    ),
    (
        1115,
        "en",
        (
            "If a player, while correctly taking a corner kick, deliberately kicks the "
            "ball at an opponent in order to play the ball again, the referee allows "
            "play to continue."
        ),
        True,
    ),
)


@pytest.mark.parametrize(
    ("qid", "language", "evidence", "stated"),
    ROWS,
    ids=[f"Q{row[0]}" for row in ROWS],
)
def test_the_stored_evidence_reads_as_it_was_reviewed(
    qid: int, language: str, evidence: str, stated: bool
) -> None:
    """The evidence states a reason exactly when the row says it does."""
    assert states_a_reason(evidence, language) is stated
