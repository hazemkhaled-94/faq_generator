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
#: second clause. A rule and the case it leaves out are one claim. The "es"
#: of "es kann auf Vorteil entschieden werden" still reads as a pronoun; the
#: rows read as two claims stay refused.
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
        "an exception whose es is part of es sei denn (F4210)",
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
        None,
    ),
    (
        "an impersonal es the pronoun reading still refuses (F4375)",
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
        None,
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

#: (name, language, the cited excerpt, statement, expected code or None):
#: stored rules refused for a second verb that states no second claim: a
#: limit opened by "sondern" with no subject of its own, and a rule the
#: parser rooted on its condition. A contrastive clause with a subject of
#: its own still states a second claim, and the rows reading so stay refused.
ONE_RULE_READ: tuple[tuple[str, str, str, str, str | None], ...] = (
    (
        "a limit with no subject of its own (F11533)",
        "de",
        (
            "Wenn ein Team weniger als sieben Spieler hat, weil ein oder mehrere "
            "Spieler absichtlich das Spielfeld verlassen haben, muss der "
            "Schiedsrichter das Spiel nicht unterbrechen, sondern kann Vorteil geben."
        ),
        (
            "Wenn ein Team weniger als sieben Spieler hat, weil ein oder mehrere "
            "Spieler absichtlich das Spielfeld verlassen haben, muss der "
            "Schiedsrichter das Spiel nicht unterbrechen, sondern kann Vorteil geben."
        ),
        None,
    ),
    (
        "a rule the parse roots on its condition (F13825)",
        "en",
        (
            "- If the kicker accidentally kicks the ball with both feet "
            "simultaneously or the ball touches their non-kicking foot or leg "
            "immediately after the kick:\n"
            "    - if the ball enters the goal from the kick, the kick is retaken\n"
            "    - if the ball does not enter the goal from the kick, the kick is "
            "recorded as missed"
        ),
        (
            "If the kicker accidentally kicks the ball with both feet "
            "simultaneously or the ball touches their non-kicking foot or leg "
            "immediately after the kick and the ball does not enter the goal, the "
            "kick is recorded as missed."
        ),
        None,
    ),
    (
        "the same rule before the ball is in play (F14128)",
        "en",
        (
            "If, before the ball is in play, one of the following occurs:\n"
            "- the kicker accidentally kicks the ball with both feet "
            "simultaneously or the ball touches their non-kicking foot or leg "
            "immediately after the kick:\n"
            "    - if the ball enters the goal from the kick, the kick is retaken\n"
            "    - if the ball does not enter the goal from the kick, an indirect "
            "free kick is awarded"
        ),
        (
            "If, before the ball is in play, the kicker accidentally kicks the ball "
            "with both feet simultaneously or the ball touches their non-kicking "
            "foot or leg immediately after the kick and the ball does not enter the "
            "goal, an indirect free kick is awarded."
        ),
        None,
    ),
    (
        "a but clause with a subject of its own (F13698)",
        "en",
        (
            "They will assist the referee in controlling the match in accordance "
            "with the Laws of the Game but the final decision will always be taken "
            "by the referee."
        ),
        (
            "Other match officials assist the referee in controlling the match in "
            "accordance with the Laws of the Game, but the final decision is always "
            "taken by the referee."
        ),
        Rejection.NOT_ATOMIC,
    ),
    (
        "an aber clause with a subject of its own (F12493)",
        "de",
        (
            "- Der Schiedsrichter kann andere/weitere Winkel/Geschwindigkeiten "
            "verlangen, grundsätzlich sollte die Zeitlupe aber nur für objektive "
            "Entscheidungen verwendet werden."
        ),
        (
            "Der Schiedsrichter kann andere oder weitere Winkel und "
            "Geschwindigkeiten verlangen, grundsätzlich sollte die Zeitlupe aber nur "
            "für objektive Entscheidungen verwendet werden."
        ),
        Rejection.NOT_ATOMIC,
    ),
)

#: (name, language, the cited excerpt, statement, expected code or None):
#: stored claims refused as `unresolved_reference` although their own words
#: name what the pronoun points to: a singular "their", the "es" of "es sei
#: denn", a "sie" agreeing with a plural or a feminine noun, a relative
#: clause the tagger read without a finite verb. The last three are pronouns
#: that point outside the statement and stay refused.
RESOLVED_BY_GRAMMAR: tuple[tuple[str, str, str, str, str | None], ...] = (
    (
        "a singular their (F5541)",
        "en",
        (
            "When the referee determines that a throw-in/goal kick is being "
            "deliberately delayed by the team taking the restart:\n- The referee "
            "may use their whistle and/or voice to indicate that the player "
            "should hurry up/not delay the restart."
        ),
        (
            "The referee may use their whistle or voice to indicate that the "
            "player should hurry up or not delay the restart when a throw-in or "
            "goal kick is being deliberately delayed."
        ),
        None,
    ),
    (
        "the es of es sei denn (F4237)",
        "de",
        (
            "- ein Handspiel begeht, um einen aussichtsreichen Angriff zu "
            "verhindern oder zu unterbinden, es sei denn, der Schiedsrichter "
            "entscheidet auf Strafstoss für ein unabsichtliches "
            "Handspielvergehen,"
        ),
        (
            "Ein Spieler wird verwarnt, wenn er ein Handspiel begeht, um einen "
            "aussichtsreichen Angriff zu verhindern oder zu unterbinden, es sei "
            "denn, der Schiedsrichter entscheidet auf Strafstoss für ein "
            "unabsichtliches Handspielvergehen."
        ),
        None,
    ),
    (
        "a relative clause the tagger read without a finite verb (F3659)",
        "de",
        (
            "- Die beiden Teams tragen Farben, durch die sie sich klar "
            "voneinander sowie von den Spieloffiziellen unterscheiden.\n"
        ),
        "Die beiden Teams tragen Farben, durch die sie sich klar voneinander unterscheiden.",
        None,
    ),
    (
        "a plural sie naming the officials before it (F4644)",
        "de",
        (
            "Die übrigen Spieloffiziellen dürfen sich die TV-Bilder nur ansehen, "
            "wenn sie der Schiedsrichter - in Ausnahmefällen - darum bittet."
        ),
        (
            "Die übrigen Spieloffiziellen dürfen sich die TV-Bilder nur ansehen, "
            "wenn sie der Schiedsrichter in Ausnahmefällen darum bittet."
        ),
        None,
    ),
    (
        "a demonstrative naming the official before it (F4711)",
        "de",
        (
            '"Die\nWettbewerbsbestimmungen müssen eindeutig festhalten, wer einen '
            "Spieloffiziellen ersetzt, wenn dieser das Spiel nicht beginnen oder "
            'fortsetzen kann, einschliesslich der damit verbundenen Wechsel."'
        ),
        (
            "Die Wettbewerbsbestimmungen müssen eindeutig festlegen, wer einen "
            "Spieloffiziellen ersetzt, wenn dieser das Spiel nicht beginnen oder "
            "fortsetzen kann."
        ),
        None,
    ),
    (
        "a this-rule naming a rule the statement never states (F3347)",
        "de",
        (
            "- Wenn eine Zeitstrafe am Ende der ersten Halbzeit noch nicht "
            "abgelaufen ist, muss der Rest zu Beginn der zweiten Halbzeit "
            "verbüsst werden (dies gilt auch für eine etwaige Verlängerung).\n"
        ),
        "Diese Regel gilt auch für eine etwaige Verlängerung.",
        Rejection.UNRESOLVED_REFERENCE,
    ),
    (
        "these lines, named only in the passage (F3422)",
        "de",
        (
            "Diese Linien erstrecken sich 5,5 m (6 yds) in das Spielfeld hinein "
            "und sind durch eine zur Torlinie parallel verlaufende Linie "
            "miteinander verbunden."
        ),
        "Diese Linien erstrecken sich 5,5 m in das Spielfeld hinein.",
        Rejection.UNRESOLVED_REFERENCE,
    ),
    (
        "these competitions, named only in the passage (F5581)",
        "en",
        (
            "Temporary dismissals (sin bins) for all or some cautionable (YC) "
            "offences are an option in youth, veterans, disability and "
            "grassroots football competitions, subject to the approval of the "
            "competition's national FA, confederation or FIFA (whichever is "
            "appropriate).\n"
        ),
        (
            "The use of temporary dismissals in these competitions is subject to "
            "approval by the competition's national FA, confederation or FIFA."
        ),
        Rejection.UNRESOLVED_REFERENCE,
    ),
)

#: (name, language, the cited excerpt, statement, expected code or None):
#: stored claims refused as `asserts_nothing` because the tagger read their
#: one verb as an infinitive or a bare form: English after a plural or a
#: name, German where the third person plural is spelled as the infinitive.
#: A heading still asserts nothing.
MISTAGGED_VERBS: tuple[tuple[str, str, str, str, str | None], ...] = (
    (
        "a verb after a name read as its bare form (F5643)",
        "en",
        (
            "Following approval at the 131 st Annual General Meeting of The IFAB "
            "held in London on 3 rd March 2017, the Laws of the Game permit the "
            "use of return substitutes in youth, veterans, disability and "
            "grassroots football, subject to the approval of the competition's "
            "national FA, confederation or FIFA, whichever is appropriate.\n"
        ),
        (
            "The Laws of the Game permit the use of return substitutes in youth "
            "football, veterans football, disability football, and grassroots "
            "football."
        ),
        None,
    ),
    (
        "a verb after a plural subject read as its bare form (F5673)",
        "en",
        (
            "However, if a team makes a 'normal substitution' at the same time "
            "as a 'concussion substitution', this will count as one of its "
            "'normal substitution' opportunities.\n"
        ),
        (
            "A normal substitution made simultaneously with a concussion "
            "substitution counts as a normal substitution opportunity."
        ),
        None,
    ),
    (
        "a third person plural read as the infinitive (F3325)",
        "de",
        (
            "- Die Wettbewerbsorganisatoren oder nationalen Fussballverbände "
            "entscheiden, ob Zeitstrafen den zuständigen Instanzen zu melden "
            "sind und weitere Disziplinarmassnahmen verhängt werden (z. B. "
            "Sperre bei einer bestimmten Anzahl Zeitstrafen wie bei "
            "Verwarnungen)."
        ),
        (
            "Die Wettbewerbsorganisatoren oder nationalen Fussballverbände "
            "entscheiden, ob weitere Disziplinarmassnahmen verhängt werden."
        ),
        None,
    ),
    (
        "a modal in the plural read as the infinitive (F3544)",
        "de",
        (
            "Die nationalen Fussballverbände können bei ihren Wettbewerben "
            "verlangen, dass ausschliesslich Bälle eingesetzt werden, die eines "
            "dieser Gütesiegel tragen.\n"
        ),
        (
            "Nationale Fussballverbände können verlangen, dass bei ihren "
            "Wettbewerben nur Bälle mit einem Gütesiegel eingesetzt werden."
        ),
        None,
    ),
    (
        "a heading of a returns policy",
        "en",
        "Returns and refunds. Goods may be returned within 30 days.",
        "Returns and refunds",
        Rejection.ASSERTS_NOTHING,
    ),
    (
        "a German heading of a fee schedule",
        "de",
        "Gebühren und Entgelte. Die Kontoführung kostet 5 Euro im Monat.",
        "Gebühren und Entgelte",
        Rejection.ASSERTS_NOTHING,
    ),
    (
        "a German heading ending on its infinitive",
        "de",
        "Konto online eröffnen. Die Eröffnung dauert zehn Minuten.",
        "Konto online eröffnen",
        Rejection.ASSERTS_NOTHING,
    ),
    (
        "a German heading ending on a verb chain",
        "de",
        "Karte sperren lassen. Die Sperre gilt sofort.",
        "Karte sperren lassen",
        Rejection.ASSERTS_NOTHING,
    ),
)

#: (name, language, the cited excerpt, its section path, statement, expected
#: code or None): stored claims refused as `unsupported_addition` for a name
#: the section path carries, a superscript ordinal parsed apart from its
#: number, or a unit the tagger wrote with a full stop. The last row is a
#: number word the rule still reads as added.
UNITS_READ_RIGHT: tuple[tuple[str, str, str, str, str, str | None], ...] = (
    (
        "a room the section path names (F3504)",
        "de",
        (
            "Im VOR arbeiten der Video-Schiedsrichterassistent (VAR), der "
            "Assistent des VAR (AVAR) und der Replay-Operateur (RO)."
        ),
        (
            "Regel 1 > Spielfeld > 14. Video-Schiedsrichterassistenten (VAR) > "
            "Video Operation Room (VOR)"
        ),
        (
            "Im Video Operation Room (VOR) arbeiten der Video-"
            "Schiedsrichterassistent (VAR), der Assistent des VAR (AVAR) und der "
            "Replay-Operateur (RO)."
        ),
        None,
    ),
    (
        "a standard the section path names (F4692)",
        "de",
        (
            "Bei den Tests für diesen Standard wird geprüft, ob grundlegende "
            "Kriterien bezüglich Leistungsfähigkeit, Präzision, Sicherheit und "
            "Langlebigkeit im Fussball erfüllt sind."
        ),
        "4. Vorgehen > FIFAQualitätsprogramm > FIFA Basic*",
        (
            "Die Tests für den FIFA Basic Standard prüfen grundlegende Kriterien "
            "bezüglich Leistungsfähigkeit, Präzision, Sicherheit und Langlebigkeit "
            "im Fussball."
        ),
        None,
    ),
    (
        "an ordinal parsed apart from its number (F5382)",
        "en",
        "Effective from 1 st July 2026\n",
        "Laws of the Game 26/27 > The International Football Association Board",
        "The Laws of the Game 2026/27 are effective from 1st July 2026.",
        None,
    ),
    (
        "a unit the tagger wrote with its full stop (F3490)",
        "de",
        "Der Abstand zwischen den Innenseiten der Torpfosten beträgt 7,32 m (8 yds).",
        "Regel 1 > Spielfeld > 10. Tore",
        "Der Abstand zwischen den Innenseiten der Torpfosten beträgt 7,32 m.",
        None,
    ),
    (
        "a season the section path abbreviates (F3074)",
        "de",
        "Gültig ab 1. Juli 2026\n",
        "Spielregeln 26/27",
        "Die Spielregeln 2026/27 sind ab dem 1. Juli 2026 gültig.",
        None,
    ),
    (
        "a count written as a word the evidence never states (F5710)",
        "en",
        (
            "These lines extend into the field of play for 5.5 m (6yds) and are "
            "joined by a line drawn parallel with the goal line."
        ),
        "Law 1 > The Field of Play > 5. The goal area",
        (
            "The two lines of the goal area are joined by a line drawn parallel "
            "with the goal line."
        ),
        Rejection.UNSUPPORTED_ADDITION,
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
    ("language", "excerpt", "statement", "expected"),
    [row[1:] for row in ONE_RULE_READ],
    ids=[row[0] for row in ONE_RULE_READ],
)
def test_a_rule_whose_second_verb_states_nothing_new_reaches_its_verdict(
    language, excerpt, statement, expected
) -> None:
    """A limit with no subject of its own, or a misrooted parse, is one claim."""
    checked = Checker(passage(excerpt, language=language)).atomic(statement, 0)

    assert verdict(checked) == expected, checked.validation_error


@pytest.mark.parametrize(
    ("language", "excerpt", "statement", "expected"),
    [row[1:] for row in RESOLVED_BY_GRAMMAR],
    ids=[row[0] for row in RESOLVED_BY_GRAMMAR],
)
def test_a_pronoun_the_grammar_resolves_reaches_its_verdict(
    language, excerpt, statement, expected
) -> None:
    """Agreement read as the language marks it, not as one feature list for all."""
    read = passage(excerpt, language=language)
    cited = tuple(sentence.index for sentence in read.sentences)
    checked = Checker(read).atomic(statement, cited)

    assert verdict(checked) == expected, checked.validation_error


@pytest.mark.parametrize(
    ("language", "excerpt", "statement", "expected"),
    [row[1:] for row in MISTAGGED_VERBS],
    ids=[row[0] for row in MISTAGGED_VERBS],
)
def test_a_claim_whose_verb_the_tagger_misread_reaches_its_verdict(
    language, excerpt, statement, expected
) -> None:
    """A verb the tagger read as a bare form still makes its sentence a claim."""
    read = passage(excerpt, language=language)
    checked = Checker(read).atomic(statement, 0)

    assert verdict(checked) == expected, checked.validation_error


@pytest.mark.parametrize(
    ("language", "excerpt", "section", "statement", "expected"),
    [row[1:] for row in UNITS_READ_RIGHT],
    ids=[row[0] for row in UNITS_READ_RIGHT],
)
def test_a_unit_its_heading_or_spelling_supports_reaches_its_verdict(
    language, excerpt, section, statement, expected
) -> None:
    """A name the heading trail carries, or a number spelled another way, is no addition."""
    read = passage(excerpt, language=language, section_path=section)
    cited = tuple(sentence.index for sentence in read.sentences)
    checked = Checker(read).atomic(statement, cited)

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
