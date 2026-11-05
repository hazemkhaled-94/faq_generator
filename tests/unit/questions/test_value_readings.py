"""How a value is read for the gates: space-grouped amounts, ordinals, the pronoun one, noun phrases."""

from __future__ import annotations

import pytest

from database.qa_generator import AnswerForm, QuestionType
from nlp.analysis import figures
from question_generation.gates import (
    BOUNDS,
    OVERLAP,
    _stated,
    adds_up,
    agrees,
    counts_a_list,
    explains,
    fitting,
    periods,
    relabelled,
    structural,
)

pytestmark = pytest.mark.nlp


@pytest.mark.parametrize(
    "text, language, value",
    [
        ("Ihr Guthaben ist bis zu 100 000 Euro geschützt.", "de", 100000.0),
        ("Der Laptop kostet 1 299,99 EUR.", "de", 1299.99),
        ("The overdraft limit is 12 500.00 GBP.", "en", 12500.0),
        ("Deposits are protected up to EUR 100 000.", "en", 100000.0),
    ],
)
def test_a_space_grouped_amount_reads_as_one_figure(text, language, value):
    """NEW-release-1: `5 000` is one figure, in German and English."""
    assert figures(text, language) == [value]


@pytest.mark.parametrize(
    "recovered, key, language",
    [
        ("Bis zu 5.000 Euro pro Forderung.", "5 000 Euro", "de"),
        (
            "Up to EUR 100,000 per account holder.",
            "EUR 100 000 per account holder",
            "en",
        ),
    ],
)
def test_one_amount_grouped_two_ways_agrees(recovered, key, language):
    """One amount grouped by a space and by a mark agrees."""
    assert agrees(recovered, key, language)


@pytest.mark.parametrize(
    "total, passages, language",
    [
        (
            "300.000 Euro",
            [
                "Ihr Geld ist bis zu 100 000 Euro je Konto geschützt.",
                "Für das Gemeinschaftskonto gelten bis zu 200 000 Euro.",
            ],
            "de",
        ),
        (
            "EUR 300,000",
            [
                "Deposits are protected up to EUR 100 000 per holder.",
                "A joint account is covered up to EUR 200 000.",
            ],
            "en",
        ),
    ],
)
def test_a_right_total_over_space_grouped_amounts_is_not_refused(
    total, passages, language
):
    """A right total over space-grouped amounts is no wrong sum."""
    assert adds_up(total, passages, language) is not False


@pytest.mark.parametrize(
    ("answer", "passages", "language"),
    [
        (
            "15.211.030,51 EUR",
            [
                "Die Bilanzsumme der Sparte A beträgt 6.111.780,03 EUR.",
                "Die Bilanzsumme der Sparte B beträgt 9.099.250,48 EUR.",
            ],
            "de",
        ),
        (
            "USD 15,211,030.51",
            [
                "Segment A reported revenue of USD 6,111,780.03.",
                "Segment B reported revenue of USD 9,099,250.48.",
            ],
            "en",
        ),
    ],
)
def test_a_right_total_of_millions_with_cents_adds_up(answer, passages, language):
    """Float error past 1e-9 on a total in the millions is no wrong sum."""
    assert adds_up(answer, passages, language) is True


def test_a_wrong_total_of_millions_with_cents_still_does_not_add_up():
    """The control: a total a cent off is still refused."""
    assert (
        adds_up("15.211.030,52 EUR", ["6.111.780,03 EUR", "9.099.250,48 EUR"], "de")
        is False
    )


@pytest.mark.parametrize(
    ("answer", "passages", "language"),
    [
        (
            "24.691.357.802,47 EUR",
            [
                "Sparte A hält 12.345.678.901,23 EUR.",
                "Sparte B hält 12.345.678.901,23 EUR.",
            ],
            "de",
        ),
        (
            "USD 24,691,357,802.47",
            [
                "Segment A holds USD 12,345,678,901.23.",
                "Segment B holds USD 12,345,678,901.23.",
            ],
            "en",
        ),
    ],
)
def test_a_total_one_cent_off_in_the_tens_of_billions_is_still_refused(
    answer, passages, language
):
    """The tolerance is float error, not a share of the amount: a cent is a cent at any size."""
    assert adds_up(answer, passages, language) is False
    exact = answer.replace("802,47", "802,46").replace("802.47", "802.46")
    assert adds_up(exact, passages, language) is True


def test_a_total_in_a_language_no_configuration_names_is_not_misread():
    """French groups by spaces and is left to the model; Greek reads as it did."""
    assert (
        adds_up(
            "15 211 030,51 EUR",
            ["Sparte A: 6 111 780,03 EUR", "Sparte B: 9 099 250,48 EUR"],
            "fr",
        )
        is None
    )
    assert (
        adds_up(
            "15.211.030,52 €",
            ["Filiale A: 6.111.780,03 €", "Filiale B: 9.099.250,48 €"],
            "el",
        )
        is False
    )


# N-023: a key that opens on a figure is a count of the cited facts only where the figure is a bare integer.
@pytest.mark.parametrize(
    ("question", "answer", "language", "statements"),
    [
        (
            "Wie hoch ist die Kontoführungsgebühr pro Jahr?",
            "2.000 EUR",
            "de",
            [
                "Die Kontoführungsgebühr beträgt 2.000 EUR pro Jahr.",
                "Die Gebühr wird im Januar belastet.",
            ],
        ),
        (
            "Wie lange dauert die Bearbeitung eines Antrags?",
            "2,5 Werktage",
            "de",
            [
                "Die Bearbeitung eines Antrags dauert 2,5 Werktage.",
                "Anträge werden nach Eingang bearbeitet.",
            ],
        ),
        (
            "Wie lange ist eine Rückgabe möglich?",
            "2–3 Wochen",
            "de",
            [
                "Die Rückgabe ist innerhalb von 2–3 Wochen möglich.",
                "Die Ware muss unbenutzt sein.",
            ],
        ),
        (
            "How much is the annual account fee?",
            "2,000 USD",
            "en",
            [
                "The annual account fee is 2,000 USD.",
                "The fee is charged every January.",
            ],
        ),
        (
            "How long does a refund take?",
            "2.5 days",
            "en",
            [
                "A refund takes 2.5 days on average.",
                "Refunds are paid to the original card.",
            ],
        ),
        (
            "What is the interest rate on the savings account?",
            "3.5%",
            "en",
            [
                "The savings account pays 3.5% interest.",
                "Interest is paid quarterly.",
                "Rates may change monthly.",
            ],
        ),
        # Unconfigured languages: inert today (no count reading), kept as the guard.
        (
            "Quel est le montant des frais annuels?",
            "2.000 EUR",
            "fr",
            [
                "Les frais annuels sont de 2.000 EUR.",
                "Les frais sont prélevés en janvier.",
            ],
        ),
        (
            "Πόσο είναι το ετήσιο τέλος?",
            "2.000 EUR",
            "el",
            ["Το ετήσιο τέλος είναι 2.000 EUR.", "Το τέλος χρεώνεται τον Ιανουάριο."],
        ),
    ],
)
def test_a_value_that_starts_with_a_small_digit_is_not_a_count_of_the_facts(
    question, answer, language, statements
):
    """An amount, a decimal, a range or a percentage is a value, not a count of citations."""
    refused, _ = structural(
        question_text=question,
        target_answer=answer,
        answerable=True,
        language=language,
        statements=statements,
    )
    assert refused is None or "number of facts" not in refused[1], refused


@pytest.mark.parametrize(
    ("question", "answer", "language", "statements"),
    [
        (
            "Wie viele Wochen ist eine Rückgabe möglich?",
            "2 – 3 Wochen",
            "de",
            [
                "Die Rückgabe ist bis zu drei Wochen möglich.",
                "Die Ware muss unbenutzt sein.",
            ],
        ),
        (
            "How many weeks does a refund take?",
            "2 - 3 weeks",
            "en",
            [
                "A refund takes up to three weeks.",
                "Refunds are paid to the original card.",
            ],
        ),
        (
            "Combien de temps dure un remboursement?",
            "2 – 3 semaines",
            "fr",
            [
                "Un remboursement prend trois semaines au plus.",
                "Il est versé sur la carte d'origine.",
            ],
        ),
        (
            "Πόσο διαρκεί η επιστροφή χρημάτων;",
            "2 – 3 εβδομάδες",
            "el",
            [
                "Η επιστροφή διαρκεί έως τρεις εβδομάδες.",
                "Καταβάλλεται στην αρχική κάρτα.",
            ],
        ),
    ],
)
def test_a_range_written_with_spaces_is_not_a_count_of_the_facts(
    question, answer, language, statements
):
    """The dash may stand apart from both figures."""
    refused, _ = structural(
        question_text=question,
        target_answer=answer,
        answerable=True,
        language=language,
        statements=statements,
    )
    assert refused is None or "number of facts" not in refused[1], refused


# N-126: a number that opens a hyphenated compound names a thing, not a count.
@pytest.mark.parametrize(
    ("question", "answer", "language", "statements"),
    [
        (
            "Welches Verfahren schützt die Anmeldung im Online-Banking?",
            "Zwei-Faktor-Authentifizierung",
            "de",
            [
                "Die Anmeldung ist durch die Zwei-Faktor-Authentifizierung geschützt.",
                "Die Zwei-Faktor-Authentifizierung verlangt einen Code per App.",
            ],
        ),
        (
            "Welches Verfahren schützt die Anmeldung im Online-Banking?",
            "2-Faktor-Authentifizierung",
            "de",
            [
                "Die Anmeldung ist durch die 2-Faktor-Authentifizierung geschützt.",
                "Für die Freigabe wird ein Code per App gesendet.",
            ],
        ),
        (
            "Welcher Grundsatz gilt bei der Freigabe von Zahlungen im Amt?",
            "Vier-Augen-Prinzip",
            "de",
            [
                "Zahlungen werden nach dem Vier-Augen-Prinzip freigegeben.",
                "Der erste Mitarbeiter erfasst die Zahlung.",
                "Der zweite Mitarbeiter gibt sie frei.",
                "Die Freigabe wird protokolliert.",
            ],
        ),
        (
            "Which procedure protects the online banking login?",
            "Two-factor authentication",
            "en",
            [
                "The login is protected by two-factor authentication.",
                "Two-factor authentication requires a password and an app code.",
            ],
        ),
        (
            "Quelle procédure protège la connexion à la banque en ligne?",
            "Double authentification",
            "fr",
            [
                "La connexion est protégée par la double authentification.",
                "Un code est envoyé par l'application.",
            ],
        ),
        (
            "Ποια διαδικασία προστατεύει τη σύνδεση στην ηλεκτρονική τραπεζική;",
            "Έλεγχος δύο παραγόντων",
            "el",
            [
                "Η σύνδεση προστατεύεται με έλεγχο δύο παραγόντων.",
                "Ένας κωδικός αποστέλλεται στην εφαρμογή.",
            ],
        ),
    ],
)
def test_a_number_opening_a_compound_is_not_a_count_of_the_facts(
    question, answer, language, statements
):
    """`Zwei-Faktor-Authentifizierung` names a procedure, however many facts cite it."""
    refused, _ = structural(
        question_text=question,
        target_answer=answer,
        answerable=True,
        language=language,
        statements=statements,
    )
    assert refused is None or "number of facts" not in refused[1], refused


F2 = [
    "Für die Anmeldung braucht man ein Passwort.",
    "Für die Freigabe braucht man zusätzlich einen Code aus der App.",
]
DE3 = [
    "Zuerst reichen Sie die Beschwerde schriftlich bei der Filiale ein.",
    "Danach prüft die Beschwerdestelle den Fall.",
    "Zuletzt entscheidet die Schlichtungsstelle.",
]
EN3 = [
    "First you file the complaint in writing at the branch.",
    "The complaints office then reviews the case.",
    "Finally the ombudsman decides.",
]
E2 = [
    "The login asks for a password.",
    "The release also asks for a code from the app.",
]


@pytest.mark.parametrize(
    ("language", "question", "answer", "statements"),
    [
        (
            "de",
            "Wie viele Stufen hat das Beschwerdeverfahren der Bank?",
            "3-stufig",
            DE3,
        ),
        (
            "de",
            "Wie viele Stufen hat das Beschwerdeverfahren der Bank?",
            "Drei-stufig",
            DE3,
        ),
        (
            "de",
            "Wie viele Stufen hat das Beschwerdeverfahren der Bank?",
            "Drei-Stufen-Verfahren",
            DE3,
        ),
        (
            "de",
            "Wie viele Faktoren braucht die Anmeldung im Online-Banking?",
            "Zwei-Faktor",
            F2,
        ),
        (
            "de",
            "Wie viele Faktoren braucht die Anmeldung im Online-Banking?",
            "2-Faktor",
            F2,
        ),
        ("de", "Wie viele Codes werden verlangt?", "2-mal", F2),
        (
            "en",
            "How many stages does the bank's complaint procedure have?",
            "Three-stage process",
            EN3,
        ),
        (
            "en",
            "How many stages does the bank's complaint procedure have?",
            "3-stage",
            EN3,
        ),
        ("en", "How many factors does the login need?", "Two-step", E2),
        ("en", "How many factors does the login need?", "Two-factor", E2),
    ],
)
def test_a_count_of_the_facts_written_as_a_compound_is_refused_when_asked_how_many(
    language, question, answer, statements
):
    """Asked how many, `3-stufig` is the count of the prompt, as `3` is."""
    refused, _ = structural(
        question_text=question,
        target_answer=answer,
        answerable=True,
        language=language,
        statements=statements,
    )
    assert refused is not None and "number of facts" in refused[1], refused


@pytest.mark.parametrize(
    ("language", "question", "answer", "statements", "counts"),
    [
        (
            "de",
            "Aus wie vielen Teilen besteht das Set?",
            "3-teilig",
            ["Das Set besteht aus einem Topf, einer Pfanne und einem Deckel."],
            True,
        ),
        (
            "de",
            "Wie viele Stufen hat das Verfahren?",
            "Drei-Stufen-Verfahren",
            ["Das Verfahren hat eine Prüfung, eine Freigabe und eine Kontrolle."],
            True,
        ),
        (
            "en",
            "How many stages does the procedure have?",
            "Three-stage process",
            ["The procedure has a check, a release and a control."],
            True,
        ),
        (
            "fr",
            "Combien de pièces contient le set?",
            "set 3-pièces",
            ["Le set contient une casserole, une poêle et un couvercle."],
            False,
        ),
        (
            "pl",
            "Ile elementów ma zestaw?",
            "3-elementowy",
            ["Zestaw zawiera garnek, patelnię i pokrywkę."],
            False,
        ),
        (
            "el",
            "Πόσα κομμάτια έχει το σετ;",
            "3-κομματο",
            ["Το σετ περιέχει μια κατσαρόλα, ένα τηγάνι και ένα καπάκι."],
            False,
        ),
    ],
)
def test_a_count_compound_still_counts_the_items_of_the_fact_it_asks_about(
    language, question, answer, statements, counts
):
    """`counts_a_list` reads the compound's number as it did: only the count rule skips it."""
    assert counts_a_list(question, answer, statements, language) is counts


PIN3 = [
    "Die Karte wird nach falschen Eingaben gesperrt.",
    "Die Sperre hebt die Filiale auf.",
    "Eine neue PIN kommt per Post.",
]
BILL2 = [
    "Das Konto wird zum Quartalsende abgerechnet.",
    "Die Abrechnung steht im Postfach.",
]
STEPS3 = [
    "Zuerst prüft die Filiale den Antrag.",
    "Danach prüft die Zentrale.",
    "Zuletzt entscheidet der Vorstand.",
]
PIN3_EN = [
    "The card is blocked after wrong entries.",
    "The branch lifts the block.",
    "A new PIN comes by post.",
]


@pytest.mark.parametrize(
    ("language", "question", "answer", "statements"),
    [
        ("de", "Wie oft kann ich die PIN falsch eingeben?", "3-mal", PIN3),
        ("de", "Wie oft wird das Konto im Jahr abgerechnet?", "2-mal", BILL2),
        ("de", "Wie oft wird das Konto im Jahr abgerechnet?", "Zwei-mal", BILL2),
        ("de", "Wie oft wird die Karte geprüft?", "3-fach", PIN3),
        ("de", "Wie vielstufig ist das Verfahren?", "3-stufig", STEPS3),
        ("de", "Wie viele Stufen hat das Verfahren?", "3-stufig", STEPS3),
        ("de", "Wie oft kann ich die PIN falsch eingeben?", "drei", PIN3),
        ("de", "Wie oft kann ich die PIN falsch eingeben?", "3 mal", PIN3),
        ("de", "Wie oft wird das Konto abgerechnet?", "2-mal jährlich", BILL2),
        ("en", "How often can I enter a wrong PIN?", "3-times", PIN3_EN),
        ("en", "How many times can I enter a wrong PIN?", "3-times", PIN3_EN),
    ],
)
def test_an_adverbial_or_numeral_compound_is_still_a_bare_count(
    language, question, answer, statements
):
    """`3-mal` and `3-times` are counts; only a compound that is a noun names a thing."""
    refused, _ = structural(
        question_text=question,
        target_answer=answer,
        answerable=True,
        language=language,
        statements=statements,
    )
    assert refused is not None and "number of facts" in refused[1], refused


@pytest.mark.parametrize(
    ("language", "question", "answer", "statements"),
    [
        (
            "de",
            "Welches Verfahren schützt die Anmeldung?",
            "Zwei-Faktor-Authentifizierung",
            [
                "Die Anmeldung ist durch ein Passwort geschützt.",
                "Für die Freigabe kommt ein Code per App.",
            ],
        ),
        (
            "de",
            "Welche Methode schützt die Anmeldung?",
            "Zwei-Faktor",
            [
                "Die Anmeldung ist durch ein Passwort geschützt.",
                "Für die Freigabe kommt ein Code per App.",
            ],
        ),
        (
            "de",
            "Welches Modell gilt für die Altersvorsorge?",
            "Zwei-Säulen-Modell",
            BILL2,
        ),
        ("de", "Wie oft kann ich die PIN falsch eingeben?", "dreimal", PIN3),
        ("de", "Wie oft kann ich die PIN falsch eingeben?", "3-mal am Tag", PIN3),
        (
            "en",
            "Which procedure protects the login?",
            "Two-factor authentication",
            [
                "The login is protected by a password.",
                "A code from the app confirms it.",
            ],
        ),
    ],
)
def test_a_compound_that_is_a_noun_or_a_longer_answer_is_not_a_bare_count(
    language, question, answer, statements
):
    """The F-04 cases stay kept, and so do answers that were never a bare count."""
    refused, _ = structural(
        question_text=question,
        target_answer=answer,
        answerable=True,
        language=language,
        statements=statements,
    )
    assert refused is None or "number of facts" not in refused[1], refused


def test_a_bare_count_equal_to_the_cited_facts_is_still_refused():
    """The control: the bare key 2 over two cited facts counts its own citations."""
    refused, _ = structural(
        question_text="Wie hoch ist die Kontoführungsgebühr pro Jahr?",
        target_answer="2",
        answerable=True,
        language="de",
        statements=[
            "Die Gebühr beträgt jährlich 5 EUR.",
            "Die Gebühr wird im Januar belastet.",
        ],
    )
    assert refused is not None and "number of facts" in refused[1]


@pytest.mark.parametrize(
    ("question", "answer", "statement", "language"),
    [
        (
            "Wie viele Tage dauert die Bearbeitung von Anträgen und Beschwerden insgesamt?",
            "2,5 Tage",
            "Die Bearbeitung von Anträgen und Beschwerden dauert jeweils 1,25 Tage.",
            "de",
        ),
        (
            "How many days does handling refunds and complaints take in total?",
            "2.5 days",
            "Handling refunds and complaints takes 1.25 days each.",
            "en",
        ),
    ],
)
def test_a_decimal_total_is_not_a_count_of_listed_items(
    question, answer, statement, language
):
    """The same leading-figure reading, in the lookup-or-sum check."""
    assert counts_a_list(question, answer, [statement], language) is False


def test_a_true_count_of_listed_items_still_is():
    """The control: a bare 3 over a statement listing three things."""
    assert counts_a_list(
        "Wie viele Gebühren berechnet die Bank?",
        "3",
        [
            (
                "Die Bank berechnet eine Kontoführungsgebühr, eine Kartengebühr und "
                "eine Gebühr für Auslandsüberweisungen."
            )
        ],
        "de",
    )


# N-029: a grouped amount or a five-digit figure is no period.
@pytest.mark.parametrize(
    "answer, language",
    [
        ("Die Gebühr stieg von 1.900 EUR auf 2.050 EUR.", "de"),
        ("Das Limit stieg von 18.500 EUR auf 20.000 EUR.", "de"),
        ("The limit went from 12000 to 20000 units.", "en"),
        ("Les frais sont passés de 1 900 EUR à 2 050 EUR.", "fr"),
        ("Οι χρεώσεις αυξήθηκαν από 1 900 EUR σε 2 050 EUR.", "el"),
    ],
)
def test_two_amounts_are_not_two_periods(answer, language):
    """German groups its thousands with a full stop, which is no day and month."""
    assert periods(answer, language) is False


@pytest.mark.parametrize(
    "answer, language",
    [
        ("Von 2024 auf 2025 stieg die Gebühr von 5 auf 7 EUR.", "de"),
        ("From 2024 to 2025 the fee rose from 5 to 7 EUR.", "en"),
        ("Vom 01.03.2024 bis zum 15.04.2025 galt der Tarif.", "de"),
        ("Der Tarif galt von 03/2024 bis 05/2025.", "de"),
        ("The rate applied from 03/2024 to 05/2025.", "en"),
        ("FY2023 and FY2024", "en"),
        ("The rate for 2023/24 and 2024/25.", "en"),
        ("Der Satz für 2023/24 und 2024/25.", "de"),
        ("De 2024 à 2025 les frais ont augmenté.", "fr"),
        ("Από το 2024 στο 2025 αυξήθηκαν οι χρεώσεις.", "el"),
    ],
)
def test_two_years_or_dates_are_two_periods(answer, language):
    """The controls: years and dated days still count."""
    assert periods(answer, language) is True


# N-040: the question mark is a per-language table, and no language but a configured one is held to it.
@pytest.mark.parametrize(
    ("language", "question"),
    [
        ("de", "Wie viel kostet die Karte im Jahr?"),
        ("en", "How much does the card cost per year?"),
        ("fr", "Combien coûte la carte par an ?"),
        ("el", "Πόσο κοστίζει η κάρτα τον χρόνο;"),
        ("ar", "كم تكلفة البطاقة في السنة؟"),
    ],
)
def test_a_question_in_its_own_script_is_not_refused_for_its_mark(language, question):
    """The ending and the count read the language's own mark, and a language with none is not held to one."""
    failed, _ = structural(
        question_text=question,
        target_answer="5 EUR",
        answerable=True,
        language=language,
    )
    assert failed is None or "question mark" not in failed[1], failed


@pytest.mark.parametrize(
    ("language", "question"),
    [
        ("de", "Wie viel kostet die Karte im Jahr"),
        ("en", "How much does the card cost per year."),
    ],
)
def test_a_configured_language_still_needs_its_mark(language, question):
    """The controls: no mark is refused, and so are two."""
    failed, _ = structural(
        question_text=question,
        target_answer="5 EUR",
        answerable=True,
        language=language,
    )
    assert failed is not None and "question mark" in failed[1]


@pytest.mark.parametrize(
    ("language", "question"),
    [("de", "Wie viel kostet die Karte? Und wann?"), ("en", "What is it? And when?")],
)
def test_two_marks_are_two_questions(language, question):
    """The count reads the same table."""
    failed, _ = structural(
        question_text=question,
        target_answer="5 EUR",
        answerable=True,
        language=language,
    )
    assert failed is not None and "2 things" in failed[1]


# N-045: only a sure reading of another language refuses a question for its language.
@pytest.mark.parametrize(
    ("language", "question", "answer"),
    [
        (
            "de",
            "Wie hoch ist die monatliche Gebühr für das Girokonto?",
            "5 EUR pro Monat",
        ),
        ("en", "How much is the monthly fee for the current account?", "5 EUR a month"),
        ("de", "Was kostet die Mastercard Gold Business Edition?", "120 EUR"),
        ("de", "Wie viel kostet Express Shipping mit Same Day Delivery?", "9,90 EUR"),
        ("en", "How much is the Girokonto Klassik per month?", "5 EUR"),
        ("en", "What does the Sparkasse Kreditkarte Gold cost?", "50 EUR a year"),
    ],
)
def test_a_question_naming_a_product_in_another_language_is_not_malformed(
    language, question, answer
):
    """A product name in the other language tips a two-way pick, and no more than that."""
    failed, _ = structural(
        question_text=question, target_answer=answer, answerable=True, language=language
    )
    assert failed is None or "it is written in" not in failed[1], failed


@pytest.mark.parametrize(
    ("language", "question", "answer"),
    [
        (
            "de",
            "Does the warranty on the vacuum cleaner also cover the battery?",
            "Yes, two years in total",
        ),
        (
            "en",
            "Gilt die Garantie auf den Staubsauger auch für den Akku?",
            "Ja, insgesamt zwei Jahre lang",
        ),
    ],
)
def test_a_question_surely_in_another_language_is_still_refused(
    language, question, answer
):
    """The controls: a whole sentence of the other configured language."""
    failed, _ = structural(
        question_text=question, target_answer=answer, answerable=True, language=language
    )
    assert failed is not None and "it is written in" in failed[1]


@pytest.mark.parametrize(
    ("question", "answer", "written"),
    [
        (
            "Quel est le montant des frais annuels de la carte bancaire Gold?",
            "5 EUR par an",
            "fr",
        ),
        (
            "Πόσο κοστίζει η ετήσια κάρτα Gold της τράπεζας για κάθε πελάτη?",
            "5 EUR το χρόνο",
            "el",
        ),
        (
            "Ile wynoszą roczne opłaty za kartę bankową Gold dla każdego klienta?",
            "5 EUR rocznie",
            "pl",
        ),
    ],
)
def test_a_question_in_a_language_no_configuration_names_is_refused(
    question, answer, written
):
    """A language neither pick can name is found out, as a French question under German facts was."""
    failed, _ = structural(
        question_text=question, target_answer=answer, answerable=True, language="de"
    )
    assert failed is not None
    assert f"it is written in {written} and its facts are in de" in failed[1]


def test_a_space_grouped_amount_is_one_number_to_relabelled():
    """An aggregation keyed with `EUR 100 000` holds one number."""
    kind = relabelled(QuestionType.AGGREGATION, AnswerForm.VALUE, "EUR 100 000", "en")
    assert kind == QuestionType.AGGREGATION


# QAB-qg-check-6: an ordinal written as a word on one side and a figure on the other.
@pytest.mark.parametrize(
    ("recovered", "key", "language", "question", "passage"),
    [
        (
            "A fee is charged from the 3rd reminder.",
            "the third reminder",
            "en",
            "From which reminder is a fee charged?",
            "A fee of 5 EUR is charged from the 3rd reminder.",
        ),
        (
            "Ab der dritten Mahnung wird eine Gebühr fällig.",
            "ab der 3. Mahnung",
            "de",
            "Ab welcher Mahnung wird eine Gebühr fällig?",
            "Ab der dritten Mahnung wird eine Gebühr von 5 EUR fällig.",
        ),
        (
            "A fee is charged from the third reminder.",
            "the 3rd reminder",
            "en",
            "From which reminder is a fee charged?",
            "A fee of 5 EUR is charged from the third reminder.",
        ),
    ],
)
def test_qab_qg_check_6_an_ordinal_word_agrees_with_its_figure(
    recovered, key, language, question, passage
):
    """QAB-qg-check-6: `the third reminder` and `the 3rd reminder` agree."""
    assert agrees(
        recovered, key, language, AnswerForm.VALUE, OVERLAP, question, "", (passage,)
    )


# NEW-qg-writer-gates-4: an explanation writing an ordinal as a figure the passage spells out.
@pytest.mark.parametrize(
    ("explanation", "key", "passage", "language"),
    [
        (
            (
                "The shop sends reminders for unpaid invoices. The first two reminders cost "
                "nothing, but from the 3rd reminder onwards a fee of 5 EUR is added to the "
                "invoice, so a customer who pays after two reminders pays no fee."
            ),
            "from the third reminder",
            (
                "A fee of 5 EUR is charged from the third reminder onwards. The first and "
                "second reminders are free of charge."
            ),
            "en",
        ),
        (
            (
                "Der Shop verschickt Mahnungen für offene Rechnungen. Die ersten beiden "
                "Mahnungen kosten nichts, doch ab der 3. Mahnung wird eine Gebühr von 5 EUR "
                "auf die Rechnung aufgeschlagen, sodass nur spätes Zahlen etwas kostet."
            ),
            "ab der dritten Mahnung",
            (
                "Ab der dritten Mahnung wird eine Gebühr von 5 EUR fällig. Die erste und "
                "zweite Mahnung sind kostenlos."
            ),
            "de",
        ),
    ],
)
def test_new_4_an_ordinal_figure_in_an_explanation_is_carried_by_its_word(
    explanation, key, passage, language
):
    """NEW-qg-writer-gates-4: `3rd` in an explanation is carried by `third`."""
    assert explains(explanation, key, (passage,), language)


@pytest.mark.parametrize(
    ("statements", "language"),
    [
        (
            ["The second reminder costs 5 euros.", "A late fee applies after 14 days."],
            "en",
        ),
        (
            ["The 2nd reminder costs 5 euros.", "A late fee applies after 14 days."],
            "en",
        ),
        (
            ["Die zweite Mahnung kostet 5 Euro.", "Nach 14 Tagen gilt eine Gebühr."],
            "de",
        ),
    ],
)
def test_an_ordinal_is_no_stated_count(statements, language):
    """`the second reminder` states no count of 2."""
    assert not _stated(2, statements, language)


@pytest.mark.parametrize(
    ("recovered", "key"),
    [("The 5th day.", "5 days"), ("At the third reminder.", "3 reminders")],
)
def test_an_ordinal_does_not_agree_with_a_cardinal(recovered, key):
    """An ordinal is the same ordinal in another form, never a count."""
    assert not agrees(recovered, key, "en")


@pytest.mark.parametrize(
    "answer", ["3 cards, the one on file included", "3 accounts, no one more"]
)
def test_var_number_readings_1_the_pronoun_one_keeps_a_count_a_count(answer):
    """The pronoun `one` is no second number, so the count stays an aggregation."""
    kind = relabelled(QuestionType.AGGREGATION, AnswerForm.VALUE, answer, "en")
    assert kind == QuestionType.AGGREGATION


# NEW-qg-writer-gates-6: the frame must not turn an imperative into a value.
@pytest.mark.parametrize(
    ("key", "language"),
    [
        ("Sign the contract", "en"),
        ("Open the app and tap Pay", "en"),
        ("Rufen Sie die Hotline an", "de"),
        ("Füllen Sie das Formular aus", "de"),
    ],
)
def test_an_imperative_key_is_still_an_action(key, language):
    """An imperative is an action, not a value."""
    _, stopped = fitting(key, [AnswerForm.VALUE], BOUNDS, language)
    assert stopped is not None, f"{key!r} passed as a value"


@pytest.mark.parametrize(
    ("recovered", "key"),
    [
        ("Ab der 3. Mahnung fallen 5 Euro an.", "3 Mahnungen"),
        ("Die Rückgabe ist bis zum 14. möglich.", "14"),
    ],
)
def test_a_german_ordinal_figure_does_not_agree_with_a_cardinal(recovered, key):
    """English `the 14th` against `14` disagrees; German `zum 14.` must too."""
    assert not agrees(recovered, key, "de")


def test_a_german_ordinal_figure_is_no_stated_count():
    """`Ab der 3. Mahnung` states no count of 3."""
    assert not _stated(
        3, ["Ab der 3. Mahnung gilt eine Gebühr.", "Y gilt.", "Z gilt."], "de"
    )


# QA-questions-3: an ordinal spelled past twelve.


@pytest.mark.parametrize(
    ("recovered", "key", "language"),
    [
        (
            "The fee applies from the thirteenth month on.",
            "from the 13th month on",
            "en",
        ),
        ("Die Gebühr gilt ab dem dreizehnten Monat.", "ab dem 13. Monat", "de"),
        ("Payment is due by the twentieth day.", "by the 20th day", "en"),
        ("Die Gebühr gilt ab dem einundzwanzigsten Monat.", "ab dem 21. Monat", "de"),
        ("Die Gebühr gilt ab dem hundertsten Tag.", "ab dem 100. Tag", "de"),
    ],
)
def test_qa_questions_3_an_ordinal_past_twelve_agrees_with_its_figure(
    recovered, key, language
):
    """`third` agrees with `3rd`; `thirteenth` must agree with `13th`."""
    assert agrees(recovered, key, language, AnswerForm.VALUE)


def test_qa_questions_3_an_ordinal_past_twelve_does_not_agree_with_its_cardinal():
    """`thirteenth` is the ordinal, never the count 13."""
    assert not agrees("It applies from the thirteenth month.", "13 months", "en")
