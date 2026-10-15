"""The verdicts the checks have always reached, pinned as a table.

One row per candidate somebody has actually seen, with the verdict it is
meant to get. The unit tests say why a check exists; this says what the whole
set of them does to a corpus, so a change to one check that quietly moves
another shows up as a diff rather than as a number on a page.

Every row here is a case that mattered: a parser limitation, a false refusal
that was fixed, or a failure mode the prompt exists to prevent.
"""

from __future__ import annotations

import pytest
from drivers import Checker, group, passage

from database.qa_generator import FactKind, Rejection

pytestmark = pytest.mark.nlp

#: The two-sentence English passage, whose first sentence carries two claims.
PROSE = (
    "The device weighs 4 kg and runs for 12 hours. "
    "It arrives in March 2026 from the Hamburg plant."
)

#: A German passage, which is the other language this deployment reads.
GERMAN = (
    "Im Jahr 2026 überwacht die Bafin die Kreditrisiken der Institute. "
    "Ein Risikobericht muss mindestens vierteljährlich erstellt werden."
)

#: (name, statement, cited sentence, expected code or None), over PROSE.
ATOMIC: tuple[tuple[str, str, int, str | None], ...] = (
    ("one claim, its own words", "The device weighs 4 kg.", 0, None),
    ("the other claim of the same sentence", "The device runs for 12 hours.", 0, None),
    (
        "a quoted sentence carrying one claim",
        "It arrives in March 2026 from the Hamburg plant.",
        1,
        Rejection.UNRESOLVED_REFERENCE,
    ),
    (
        "the sentence copied whole",
        "The device weighs 4 kg and runs for 12 hours.",
        0,
        Rejection.COPIED,
    ),
    (
        "two claims joined by and",
        "The device weighs 4 kg and it runs for 12 hours.",
        0,
        Rejection.NOT_ATOMIC,
    ),
    ("a noun phrase", "The 4 kg device.", 0, Rejection.ASSERTS_NOTHING),
    ("a heading", "Delivery and dispatch", 0, Rejection.ASSERTS_NOTHING),
    (
        "a number the source never gave",
        "The device weighs 7 kg.",
        0,
        Rejection.UNSUPPORTED_ADDITION,
    ),
    (
        "a name the source never gave",
        "The Bundesbank delivers the device in March 2026.",
        1,
        Rejection.UNSUPPORTED_ADDITION,
    ),
    (
        "a dangling pronoun",
        "It arrives in March 2026.",
        1,
        Rejection.UNRESOLVED_REFERENCE,
    ),
    (
        "a subject taken from the other sentence",
        "The device arrives in March 2026.",
        1,
        None,
    ),
)

#: The same table in German, where the parser behaves differently enough to
#: be worth its own rows.
GERMAN_ATOMIC: tuple[tuple[str, str, int, str | None], ...] = (
    (
        "a modal passive, which the small pipeline reads as no claim at all",
        "Ein Risikobericht muss vierteljährlich erstellt werden.",
        1,
        None,
    ),
    (
        "a year with a full stop attached is the same year",
        "Die Bafin überwacht die Kreditrisiken im Jahr 2026.",
        0,
        None,
    ),
    (
        "a reflexive belongs to its own verb",
        "Die Überwachung ergibt sich aus den Kreditrisiken.",
        0,
        None,
    ),
    (
        "an invented figure",
        "Ein Risikobericht muss monatlich in 12 Ausfertigungen erstellt werden.",
        1,
        Rejection.UNSUPPORTED_ADDITION,
    ),
)

#: (name, language, the cited excerpt, statement, expected code or None):
#: stored rules kept whole with their exception, refused as `not_atomic`
#: when the parser hung "es sei denn" or "außer" beside the main verb as a
#: second clause. A rule and the case it leaves out are one claim. Three move
#: on to the pronoun reading, which is its own row; the rest are two claims
#: and stay refused.
KEPT_WHOLE: tuple[tuple[str, str, str, str, str | None], ...] = (
    (
        "a restart and the case it leaves out (F4383)",
        "de",
        (
            "Wenn der ausführende Spieler bei einer erneuten Berührung jedoch ein "
            "Handspielvergehen begeht:\n- wird ein direkter Freistoss verhängt,\n"
            "- wird ein Strafstoss verhängt, wenn das Vergehen innerhalb des "
            "Strafraums des ausführenden Spielers erfolgte, es sei denn, der "
            "ausführende Spieler war der Torhüter."
        ),
        (
            "Ein Strafstoss wird verhängt, wenn das Handspielvergehen des "
            "ausführenden Spielers innerhalb seines eigenen Strafraums erfolgt, "
            "es sei denn, der ausführende Spieler war der Torhüter."
        ),
        None,
    ),
    (
        "the same rule with its clauses the other way round (F4541)",
        "de",
        (
            "Wenn der ausführende Spieler bei der erneuten Berührung jedoch ein "
            "Handspielvergehen begeht:\n- wird ein direkter Freistoss verhängt,\n"
            "- wird ein Strafstoss verhängt, wenn das Vergehen innerhalb des "
            "Strafraums des ausführenden Spielers erfolgte, es sei denn, der "
            "ausführende Spieler war der Torhüter."
        ),
        (
            "Ein Strafstoss wird verhängt, wenn das Handspielvergehen des "
            "ausführenden Spielers innerhalb seines Strafraums erfolgt, es sei "
            "denn, der ausführende Spieler war der Torhüter."
        ),
        None,
    ),
    (
        "and in the order it was validated in (F4517)",
        "de",
        (
            "Wenn der ausführende Spieler bei der erneuten Berührung jedoch ein "
            "Handspielvergehen begeht:\n- wird ein direkter Freistoss verhängt,\n"
            "- wird ein Strafstoss verhängt, wenn das Vergehen innerhalb des "
            "Strafraums des ausführenden Spielers erfolgte, es sei denn, der "
            "ausführende Spieler war der Torhüter."
        ),
        (
            "Wenn das Handspielvergehen des ausführenden Spielers innerhalb seines "
            "Strafraums erfolgt, wird ein Strafstoss verhängt, es sei denn, der "
            "ausführende Spieler war der Torhüter."
        ),
        None,
    ),
    (
        "an exception opened by außer (F4346)",
        "de",
        (
            "Wenn der Schiedsrichter das Spiel aufgrund eines Vergehens eines "
            "Spielers inner- oder ausserhalb des Spielfelds gegen eine Drittperson "
            "unterbricht, wird das Spiel mit einem Schiedsrichterball fortgesetzt, "
            "es sei denn, das Vergehen wird mit einem indirekten Freistoss "
            "geahndet, weil der Spieler das Spielfeld ohne die Erlaubnis des "
            "Schiedsrichters verlassen hat."
        ),
        (
            "Wenn der Schiedsrichter das Spiel wegen eines Vergehens eines Spielers "
            "gegen eine Drittperson unterbricht, wird das Spiel mit einem "
            "Schiedsrichterball fortgesetzt, außer das Vergehen wird mit einem "
            "indirekten Freistoss geahndet, weil der Spieler das Spielfeld ohne "
            "Erlaubnis verlassen hat."
        ),
        None,
    ),
    (
        "a list item kept with the lead-in's only (F5861)",
        "en",
        (
            "- if a player who is to be substituted refuses to leave, play "
            "continues\nThe substitute only enters:\n- during a stoppage in play\n"
            "- at the halfway line\n- after the player being replaced has left\n"
            "- after receiving a signal from the referee\nThe substitution is "
            "completed when a substitute enters the field of play; from that "
            "moment, the replaced player becomes a substituted player and the "
            "substitute becomes a player and can take any restart.\n"
        ),
        "A substitute only enters after the player being replaced has left.",
        None,
    ),
    (
        "an exception whose es the pronoun reading then refuses (F4210)",
        "de",
        (
            "Bei grobem Foulspiel, einer Tätlichkeit oder einem zweiten "
            "verwarnungswürdigen Vergehen sollte nicht auf Vorteil entschieden "
            "werden, es sei denn, es ergibt sich eine offensichtliche Torchance."
        ),
        (
            "Bei grobem Foulspiel, einer Tätlichkeit oder einem zweiten "
            "verwarnungswürdigen Vergehen sollte nicht auf Vorteil entschieden "
            "werden, ausser es ergibt sich eine offensichtliche Torchance."
        ),
        Rejection.UNRESOLVED_REFERENCE,
    ),
    (
        "a repeated free kick and its exception (F4375)",
        "de",
        (
            "Wenn ein Gegner bei einem Freistoss den erforderlichen Abstand zum "
            "Ball nicht einhält, wird der Freistoss wiederholt, es sei denn, es "
            "kann auf Vorteil entschieden werden."
        ),
        (
            "Ein Freistoss wird wiederholt, wenn ein Gegner den erforderlichen "
            "Abstand zum Ball nicht einhält, es sei denn, es kann auf Vorteil "
            "entschieden werden."
        ),
        Rejection.UNRESOLVED_REFERENCE,
    ),
    (
        "a place and the case that moves it (F4862)",
        "de",
        (
            "Der Schiedsrichterball erfolgt an der Stelle, an der sich der Ball "
            "zum Zeitpunkt der Spielunterbrechung befand, es sei denn, er hat "
            "einen Spieloffiziellen oder eine Drittperson getroffen."
        ),
        (
            "Der Schiedsrichterball erfolgt an der Stelle, an der sich der Ball "
            "zum Zeitpunkt der Spielunterbrechung befand, es sei denn, der Ball "
            "hat einen Spieloffiziellen oder eine Drittperson getroffen."
        ),
        Rejection.UNRESOLVED_REFERENCE,
    ),
    (
        "two duties of one subject are two claims (F3757)",
        "de",
        (
            "Der Schiedsrichter:\n- setzt die Spielregeln durch,\n- leitet das "
            "Spiel zusammen mit den weiteren Spieloffiziellen,\n- fungiert als "
            "Zeitnehmer, macht Aufzeichnungen über das Spiel und lässt den "
            "zuständigen Instanzen einen Spielbericht zukommen, einschliesslich "
            "Angaben zu Disziplinarmassnahmen oder sonstigen Zwischenfällen vor, "
            "während oder nach dem Spiel,\n- überwacht die Fortsetzung des Spiels "
            "und/oder zeigt diese an,"
        ),
        (
            "Der Schiedsrichter macht Aufzeichnungen über das Spiel und lässt den "
            "zuständigen Instanzen einen Spielbericht zukommen."
        ),
        Rejection.NOT_ATOMIC,
    ),
    (
        "taking a measure and restarting play are two claims (F4663)",
        "de",
        (
            "- Der Schiedsrichter ergreift/ändert/annulliert alle nötigen "
            "Disziplinarmassnahmen und setzt das Spiel gemäss Spielregeln fort."
        ),
        (
            "Der Schiedsrichter ergreift, ändert oder annulliert alle nötigen "
            "Disziplinarmaßnahmen und setzt das Spiel gemäss Spielregeln fort."
        ),
        Rejection.NOT_ATOMIC,
    ),
    (
        "a width and a ceiling on it are two claims (F5740)",
        "en",
        "All lines must be of the same width, which must not be more than 12cm (5ins).",
        (
            "All field markings lines must be of the same width and must not be "
            "more than 12 centimetres (5 inches)."
        ),
        Rejection.NOT_ATOMIC,
    ),
    (
        "a provided-clause the parser still counts: what the rule misses (F5531)",
        "en",
        (
            "A player is not required to leave the field of play for one minute "
            "when:\n- the player:\n- indicates that they do not require medical "
            "attention, except where play was stopped for the injury; or\n"
            "- voluntarily leaves the field during play or a stoppage, provided "
            "that this does not delay the restart"
        ),
        (
            "A player is not required to leave the field for one minute if they "
            "voluntarily leave during play or a stoppage, provided this does not "
            "delay the restart."
        ),
        Rejection.NOT_ATOMIC,
    ),
)

#: (name, the cited excerpt, statement, expected code or None): stored German
#: claims whose pronoun points back inside the statement, to the subject the
#: condition is about. Refused as dangling before the reading looked behind
#: the pronoun.
SELF_RESOLVED: tuple[tuple[str, str, str, str | None], ...] = (
    (
        "the ball, then a condition on it",
        (
            "Der Ball ist aus dem Spiel, wenn:\n"
            "- er auf dem Boden oder in der Luft die Tor- oder Seitenlinie "
            "vollständig überquert hat,"
        ),
        "Der Ball ist aus dem Spiel, wenn er die Torlinie vollständig überquert hat.",
        None,
    ),
    (
        "the ball touching an official",
        (
            "Der Ball ist zu jedem anderen Zeitpunkt im Spiel, auch wenn er einen "
            "Spieloffiziellen berührt oder von einem Torpfosten, der Querlatte "
            "oder einer Eckfahnenstange zurückspringt und auf dem Spielfeld "
            "bleibt."
        ),
        "Der Ball bleibt im Spiel, wenn er einen Spieloffiziellen berührt.",
        None,
    ),
    (
        "a player, then what he attempts",
        (
            "Ein Spieler ist wegen unsportlichen Verhaltens zu verwarnen, wenn er:\n"
            "- den Schiedsrichter zu täuschen versucht, z. B. durch das Simulieren "
            "einer\nVerletzung oder eines Fouls (Schwalbe),"
        ),
        (
            "Ein Spieler ist wegen unsportlichen Verhaltens zu verwarnen, wenn er "
            "den Schiedsrichter zu täuschen versucht."
        ),
        None,
    ),
)

#: (name, statement, expected code or None), over PROSE as a summary.
SUMMARIES: tuple[tuple[str, str, str | None], ...] = (
    ("a condensed reading", "The device weighs 4 kg. It arrives in March 2026.", None),
    (
        "several claims, which is what a summary is for",
        "The device weighs 4 kg and runs for 12 hours.",
        None,
    ),
    ("the passage copied whole", PROSE, Rejection.NOT_CONDENSED),
    (
        "a label rather than a reading",
        "The 4 kg device from Hamburg.",
        Rejection.ASSERTS_NOTHING,
    ),
    (
        "a figure the passage does not carry",
        "The device weighs 9 kg.",
        Rejection.UNSUPPORTED_ADDITION,
    ),
)

#: (name, points, expected code or None), over PROSE as an outline.
OUTLINES: tuple[tuple[str, tuple[str, ...], str | None], ...] = (
    (
        "telegraphic points, which carry no finite verb",
        ("Weighs 4 kg", "Runs for 12 hours"),
        None,
    ),
    (
        "points written as sentences",
        ("It weighs 4 kg.", "It runs for 12 hours."),
        None,
    ),
    ("one point, which is a label", ("Weighs 4 kg",), Rejection.NOT_LISTED),
    ("no points at all", (), Rejection.NOT_LISTED),
    (
        "a point naming a figure the passage does not",
        ("Weighs 9 kg", "Runs for 12 hours"),
        Rejection.UNSUPPORTED_ADDITION,
    ),
)

#: (name, statement, positions, expected code or None), over two passages.
BRIDGES: tuple[tuple[str, str, tuple[int, ...], str | None], ...] = (
    (
        "one claim needing both",
        (
            "Support response times are stated separately for standard and "
            "urgent requests."
        ),
        (0, 1),
        None,
    ),
    (
        "a value carried by the second passage",
        "An urgent request waits 4 hours.",
        (0, 1),
        None,
    ),
    (
        "a claim one passage states alone",
        "Standard requests are answered within 48 hours.",
        (0,),
        Rejection.NOT_BRIDGING,
    ),
    (
        "arithmetic nobody wrote down",
        "The response times differ by 44 hours.",
        (0, 1),
        Rejection.UNSUPPORTED_ADDITION,
    ),
    (
        "two claims in one bridge",
        "Standard requests wait 48 hours and urgent requests wait 4 hours.",
        (0, 1),
        Rejection.NOT_ATOMIC,
    ),
    (
        "a claim resting on nothing",
        "Anything at all happens.",
        (),
        Rejection.EVIDENCE_ABSENT,
    ),
)


def verdict(checked) -> str | None:
    """The code a fact was refused under, or None when it passed."""
    return checked.rejection_code


@pytest.fixture(scope="module")
def english() -> Checker:
    """The English passage every atomic and digest row is read against."""
    return Checker(passage(PROSE))


@pytest.fixture(scope="module")
def german() -> Checker:
    """The German passage the German rows are read against."""
    return Checker(passage(GERMAN, language="de"))


@pytest.fixture(scope="module")
def offered():
    """Two passages of two documents, as a topic group offers them."""
    return group(
        "Standard requests are answered within 48 hours.",
        "Urgent requests are answered within 4 hours.",
    )


@pytest.mark.parametrize(
    ("statement", "cited", "expected"),
    [row[1:] for row in ATOMIC],
    ids=[row[0] for row in ATOMIC],
)
def test_an_atomic_candidate_reaches_its_recorded_verdict(
    english, statement, cited, expected
) -> None:
    """One claim, from one sentence, with nothing added and nothing dangling."""
    assert verdict(english.atomic(statement, cited)) == expected


@pytest.mark.parametrize(
    ("statement", "cited", "expected"),
    [row[1:] for row in GERMAN_ATOMIC],
    ids=[row[0] for row in GERMAN_ATOMIC],
)
def test_a_german_candidate_reaches_its_recorded_verdict(
    german, statement, cited, expected
) -> None:
    """The other language, where the parser behaves differently enough."""
    assert verdict(german.atomic(statement, cited)) == expected


@pytest.mark.parametrize(
    ("language", "excerpt", "statement", "expected"),
    [row[1:] for row in KEPT_WHOLE],
    ids=[row[0] for row in KEPT_WHOLE],
)
def test_a_rule_kept_with_its_exception_reaches_its_verdict(
    language, excerpt, statement, expected
) -> None:
    """An exception or an alternative is part of the claim it qualifies."""
    checked = Checker(passage(excerpt, language=language)).atomic(statement, 0)

    assert verdict(checked) == expected, checked.validation_error


@pytest.mark.parametrize(
    ("excerpt", "statement", "expected"),
    [row[1:] for row in SELF_RESOLVED],
    ids=[row[0] for row in SELF_RESOLVED],
)
def test_a_pronoun_its_statement_resolves_reaches_its_verdict(
    excerpt, statement, expected
) -> None:
    """The subject named first is what the pronoun after it names."""
    checked = Checker(passage(excerpt, language="de")).atomic(statement, 0)

    assert verdict(checked) == expected, checked.validation_error
    assert not checked.unresolved_references


@pytest.mark.parametrize(
    ("statement", "expected"),
    [row[1:] for row in SUMMARIES],
    ids=[row[0] for row in SUMMARIES],
)
def test_a_summary_reaches_its_recorded_verdict(english, statement, expected) -> None:
    """Shorter than its passage, asserting something, inventing nothing."""
    assert verdict(english.summary(statement)) == expected


@pytest.mark.parametrize(
    ("points", "expected"),
    [row[1:] for row in OUTLINES],
    ids=[row[0] for row in OUTLINES],
)
def test_an_outline_reaches_its_recorded_verdict(english, points, expected) -> None:
    """Two points or more, inventing nothing, judged on shape not grammar."""
    assert verdict(english.outline(*points)) == expected


@pytest.mark.parametrize(
    ("statement", "positions", "expected"),
    [row[1:] for row in BRIDGES],
    ids=[row[0] for row in BRIDGES],
)
def test_a_bridge_reaches_its_recorded_verdict(
    english, offered, statement, positions, expected
) -> None:
    """One claim, over two passages, computed from neither."""
    assert verdict(english.bridge(statement, offered, positions)) == expected


def test_every_kind_appears_in_this_table() -> None:
    """A kind with no rows here is a kind nothing pins."""
    tables = {
        FactKind.ATOMIC: [*ATOMIC, *GERMAN_ATOMIC],
        FactKind.SUMMARY: SUMMARIES,
        FactKind.OUTLINE: OUTLINES,
        FactKind.BRIDGE: BRIDGES,
    }

    assert {kind for kind, rows in tables.items() if rows} == set(FactKind)


def test_every_refusal_appears_in_this_table() -> None:
    """A code with no row here is a code that could stop firing unnoticed."""
    pinned = {
        expected
        for rows in (ATOMIC, GERMAN_ATOMIC)
        for *_, expected in rows
        if expected
    }
    pinned |= {expected for *_, expected in SUMMARIES if expected}
    pinned |= {expected for *_, expected in OUTLINES if expected}
    pinned |= {expected for *_, expected in BRIDGES if expected}

    # Two verdicts no check reaches, so no statement here could pin either:
    # both are the service refusing facts the checks passed, on something no
    # one statement can be read for. `over_cap` is the passage yielding more
    # atomic facts than EXTRACTION_MIN_OTHER_SHARE leaves room for, and
    # `duplicate` is the corpus already holding the statement, both pinned
    # in tests/unit/extraction/test_extraction_service.py.
    service_only = {Rejection.OVER_CAP, Rejection.DUPLICATE}
    assert pinned == set(Rejection) - service_only, sorted(
        set(Rejection) - service_only - pinned
    )


def test_an_accepted_fact_carries_a_span_that_resolves_in_its_passage(
    english, offered
) -> None:
    """The invariant every reader of fact_passages relies on."""
    under = english.passage
    for statement, cited, expected in [row[1:] for row in ATOMIC]:
        checked = english.atomic(statement, cited)
        if expected == Rejection.EVIDENCE_ABSENT:
            continue
        ((one,),) = [checked.citations]
        assert one.passage_id == under.id, statement
        assert under.text[one.start : one.end] == checked.evidence_text, statement

    bridged = english.bridge("An urgent request waits 4 hours.", offered)
    by_id = {one.id: one for one in offered}
    assert bridged.evidence_text == "\n".join(
        by_id[one.passage_id].text[one.start : one.end] for one in bridged.citations
    )
