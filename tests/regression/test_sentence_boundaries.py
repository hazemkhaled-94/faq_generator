"""Where the sentence splitter ends a sentence, pinned on stored passages.

Every citation resolves against these sentences, so one cut in the middle
leaves a fact's evidence holding half a rule: the word before a slash in one
sentence and the word after it in the next, a clause opened by a comma
filed under the sentence after it, an item's number left on the item
before. Each row is text a run stored, beside the sentences it must read
as; the last rows are cuts that are right and must stay.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.nlp

#: (name, language, text, the sentences it reads as).
ROWS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "two names for one restart joined by a slash",
        "de",
        (
            "Wird der Ball nach vorne gespielt und berührt er keinen Spieler, die "
            "Querlatte oder einen Torpfosten, wird der Strafstoss/Elfmeter "
            "wiederholt."
        ),
        (
            (
                "Wird der Ball nach vorne gespielt und berührt er keinen Spieler, die "
                "Querlatte oder einen Torpfosten, wird der Strafstoss/Elfmeter "
                "wiederholt."
            ),
        ),
    ),
    (
        "a main clause opened by a comma after its condition",
        "de",
        (
            "Zeigt der Schiedsrichter nicht an, dass es sich um einen indirekten "
            "Freistoss handelt, und geht der Ball direkt ins Tor, so muss der "
            "indirekte Freistoss wiederholt werden."
        ),
        (
            (
                "Zeigt der Schiedsrichter nicht an, dass es sich um einen indirekten "
                "Freistoss handelt, und geht der Ball direkt ins Tor, so muss der "
                "indirekte Freistoss wiederholt werden."
            ),
        ),
    ),
    (
        "an item number kept with its item",
        "de",
        (
            "1. Ein VAR ist ein Spieloffizieller, der den Schiedsrichter "
            "unterstützt.\n2. Der Schiedsrichter muss immer eine Entscheidung "
            "fällen."
        ),
        (
            "1. Ein VAR ist ein Spieloffizieller, der den Schiedsrichter unterstützt.",
            "2. Der Schiedsrichter muss immer eine Entscheidung fällen.",
        ),
    ),
    (
        "etc. before a lower-case word ends nothing",
        "en",
        (
            "For a factual decision such as offside, ball out of play etc. a "
            "'VAR-only review' is usually appropriate."
        ),
        (
            (
                "For a factual decision such as offside, ball out of play etc. a "
                "'VAR-only review' is usually appropriate."
            ),
        ),
    ),
    (
        "etc. before a capital at a line end does end a sentence",
        "en",
        (
            "The referee keeps records of time, goals, misconduct etc.\n"
            "Competition rules must state who replaces an official."
        ),
        (
            "The referee keeps records of time, goals, misconduct etc.",
            "Competition rules must state who replaces an official.",
        ),
    ),
    (
        "a full stop with no space after it still ends a sentence",
        "en",
        "The fee is due on the first day.Payment follows within 14 days.",
        ("The fee is due on the first day.", "Payment follows within 14 days."),
    ),
    (
        "two fees joined by a slash in a bank's schedule",
        "de",
        "Die Gebühren/Entgelte werden am Monatsende belastet.",
        ("Die Gebühren/Entgelte werden am Monatsende belastet.",),
    ),
    (
        "an abbreviation before a figure ends nothing",
        "en",
        "Delivery takes approx. 3 days. Express delivery is faster.",
        ("Delivery takes approx. 3 days.", "Express delivery is faster."),
    ),
    (
        "incl. before a rate ends nothing",
        "en",
        "Prices are shown incl. 19 % VAT. Shipping is extra.",
        ("Prices are shown incl. 19 % VAT.", "Shipping is extra."),
    ),
    (
        "an abbreviation ending a numbered item ends it",
        "en",
        "1. Account fees, transfers etc.\n2. Card fees and cash.",
        ("1. Account fees, transfers etc.", "2. Card fees and cash."),
    ),
    (
        "a dash after a full stop and a space opens a sentence",
        "en",
        "The fee is 50 EUR. - Repeat offenders pay 100 EUR.",
        ("The fee is 50 EUR.", "- Repeat offenders pay 100 EUR."),
    ),
    (
        "a negative figure after a full stop opens a sentence",
        "en",
        "The card is blocked. -5 points are deducted for each late payment.",
        ("The card is blocked.", "-5 points are deducted for each late payment."),
    ),
    (
        "a free slash after a full stop goes with what follows",
        "de",
        "Der Rückversand ist kostenlos. / Ausnahmen regelt Nr. 4.",
        ("Der Rückversand ist kostenlos.", "/ Ausnahmen regelt Nr. 4."),
    ),
    (
        "a free slash after an abbreviation ends nothing",
        "de",
        "Alle Preise inkl. / zzgl. Versand sind ausgewiesen.",
        ("Alle Preise inkl. / zzgl. Versand sind ausgewiesen.",),
    ),
    (
        "a free dash after an abbreviation ends nothing",
        "en",
        "The fee is approx. - depending on the card - 20 EUR.",
        ("The fee is approx. - depending on the card - 20 EUR.",),
    ),
    (
        # The parser cuts after the second bullet's dash, as it does in a
        # stored list of rules, and leaves the dash on the rule before.
        "two bulleted rules each ending in a full stop are two sentences",
        "en",
        (
            "- A replacement card may be ordered regardless of the number of "
            "cards already issued.\n- In branches with no counter, the card is "
            "sent by post."
        ),
        (
            (
                "- A replacement card may be ordered regardless of the number of "
                "cards already issued."
            ),
            "- In branches with no counter, the card is sent by post.",
        ),
    ),
    (
        # The parser cuts after the first bullet's dash here too; with no
        # sentence ended before it, the dash stays with its lead-in.
        "a lead-in keeps its first bullet",
        "de",
        (
            "Für dieses Konto gelten die folgenden Bestimmungen:\n- Die "
            "Kontoführung kostet 4,90 EUR im Monat.\n- Die Karte ist im ersten "
            "Jahr kostenlos."
        ),
        (
            (
                "Für dieses Konto gelten die folgenden Bestimmungen:\n- Die "
                "Kontoführung kostet 4,90 EUR im Monat."
            ),
            "- Die Karte ist im ersten Jahr kostenlos.",
        ),
    ),
    (
        "a label dash stays one sentence",
        "de",
        "Abschnitt 6 - Entgelte für Karten lautet wie folgt:",
        ("Abschnitt 6 - Entgelte für Karten lautet wie folgt:",),
    ),
    (
        "a slash a PDF spaced inside a word joins",
        "de",
        "Ist die Ware beschädigt/ unvollständig, erstattet der Händler den Preis.",
        ("Ist die Ware beschädigt/ unvollständig, erstattet der Händler den Preis.",),
    ),
    (
        "a clause cited by its number ends nothing",
        "de",
        "Die Gebühr nach Art. 12 der AGB beträgt 5 EUR.",
        ("Die Gebühr nach Art. 12 der AGB beträgt 5 EUR.",),
    ),
    (
        "an abbreviation before a capitalised one ends nothing",
        "de",
        "Die Gebühr beträgt gem. Ziff. 3 des Preisverzeichnisses 5 EUR.",
        ("Die Gebühr beträgt gem. Ziff. 3 des Preisverzeichnisses 5 EUR.",),
    ),
    (
        "a yearly fee abbreviated before a lower-case word ends nothing",
        "de",
        "Das Konto kostet 58,80 EUR jährl. inkl. aller Buchungen.",
        ("Das Konto kostet 58,80 EUR jährl. inkl. aller Buchungen.",),
    ),
    (
        "a range of weekdays ends nothing",
        "de",
        "Der Kundenservice ist Mo.–Fr. von 8 bis 18 Uhr erreichbar.",
        ("Der Kundenservice ist Mo.–Fr. von 8 bis 18 Uhr erreichbar.",),
    ),
    (
        "a limit abbreviated before its figure ends nothing",
        "en",
        "Withdrawals are limited to max. 1,000 EUR per day.",
        ("Withdrawals are limited to max. 1,000 EUR per day.",),
    ),
    (
        "an article cited by its number ends nothing",
        "en",
        "Per Art. 6 of the GDPR, we process your data.",
        ("Per Art. 6 of the GDPR, we process your data.",),
    ),
    (
        "weekdays abbreviated before lower-case words end nothing",
        "en",
        "Returns are accepted Mon. to Fri. at the counter.",
        ("Returns are accepted Mon. to Fri. at the counter.",),
    ),
    (
        "incl. before a capitalised word ends nothing",
        "en",
        "Prices are shown incl. VAT and shipping.",
        ("Prices are shown incl. VAT and shipping.",),
    ),
    (
        "incl. inside a subject ends nothing",
        "en",
        "The price incl. VAT is 20 EUR.",
        ("The price incl. VAT is 20 EUR.",),
    ),
    (
        "cf. before a section's name ends nothing",
        "en",
        "Compare our accounts, cf. Section 4 of the terms.",
        ("Compare our accounts, cf. Section 4 of the terms.",),
    ),
    (
        "approx. before a capitalised number ends nothing",
        "en",
        "Delivery takes approx. Two days.",
        ("Delivery takes approx. Two days.",),
    ),
    (
        "etc. before a capital does end a sentence",
        "en",
        "We accept Visa, Mastercard etc. Payment is immediate.",
        ("We accept Visa, Mastercard etc.", "Payment is immediate."),
    ),
    (
        "u. a. closing a list ends a sentence",
        "de",
        "Wir bieten Girokonten, Sparkonten u. a. Die Karte kostet 5 EUR.",
        ("Wir bieten Girokonten, Sparkonten u. a.", "Die Karte kostet 5 EUR."),
    ),
    (
        "the word no ends a sentence",
        "en",
        "Is a transfer free? No. A transfer costs 1 EUR.",
        ("Is a transfer free?", "No.", "A transfer costs 1 EUR."),
    ),
)


@pytest.mark.parametrize(
    ("language", "text", "expected"),
    [row[1:] for row in ROWS],
    ids=[row[0] for row in ROWS],
)
def test_a_stored_passage_splits_where_its_sentences_end(
    language, text, expected
) -> None:
    """The sentences read off the text, each stripped of its spacing."""
    from nlp.analysis import sentences

    found = tuple(sentence.text.strip() for sentence in sentences(text, language))

    assert found == expected
