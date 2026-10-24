"""How many claims a sentence reads as.

A German obligation is stated with a modal and a participle. de_core_news_sm
tags no finite verb in that shape at all; a failure here means NLP_MODELS has
been pointed at a smaller model.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.nlp


@pytest.mark.parametrize(
    "sentence",
    [
        "Ein Risikobericht muss mindestens vierteljährlich erstellt werden.",
        "Bei abweichenden Voten muss der Kredit abgelehnt werden.",
        "Die Geschäftsleitung muss für die Umsetzung Sorge tragen.",
        "Die vereinfachte Umsetzung muss unter Risikogesichtspunkten vertretbar sein.",
        "Das interne Kontrollsystem umfasst eine Risikocontrolling-Funktion.",
    ],
)
def test_a_german_obligation_is_one_claim(sentence: str) -> None:
    """A modal and its participle read as a single claim."""
    from nlp.analysis import claim

    found = claim(sentence, "de").predicates
    assert found == 1, f"{found} claim(s) read in {sentence!r}; expected 1"


def test_two_coordinated_clauses_are_two_claims() -> None:
    """A sentence joining two finite verbs reads as two."""
    from nlp.analysis import claim

    sentence = "Der Antrag wird geprüft und das Ergebnis wird mitgeteilt."
    assert claim(sentence, "de").predicates == 2


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        ("de", "Die Karte wird gesperrt, es sei denn, der Kunde widerspricht."),
        (
            "de",
            "Die Rückerstattung erfolgt binnen 14 Tagen, ausser die Ware ist beschädigt.",
        ),
        (
            "en",
            "Refunds are issued within 14 days, except where the goods are damaged.",
        ),
        (
            "en",
            "Customers may return goods within 14 days, provided they keep the receipt.",
        ),
    ],
)
def test_a_rule_and_the_case_it_leaves_out_are_one_claim(
    language: str, sentence: str
) -> None:
    """An exception narrows the rule it follows rather than saying something else."""
    from nlp.analysis import claim

    found = claim(sentence, language).predicates
    assert found == 1, f"{found} claim(s) read in {sentence!r}; expected 1"


def test_a_main_verb_provided_is_a_claim() -> None:
    """`provided` as the verb a clause states is no exception opening."""
    from nlp.analysis import claim

    sentence = "The bank provided the card and the customer signed the form."
    assert claim(sentence, "en").predicates == 2


def test_an_exceptive_provided_still_restricts() -> None:
    """`provided` opening a condition still narrows the rule before it."""
    from nlp.analysis import claim

    sentence = "The voucher is valid provided the customer pays."
    assert claim(sentence, "en").predicates == 1


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        ("en", "The bank refunds the fee or it credits the account."),
        ("de", "Der Händler erstattet den Betrag oder er liefert die Ware neu."),
    ],
)
def test_two_alternatives_are_one_claim(language: str, sentence: str) -> None:
    """`A or B` does not say A, so it cannot be split into A and B."""
    from nlp.analysis import claim

    found = claim(sentence, language).predicates
    assert found == 1, f"{found} claim(s) read in {sentence!r}; expected 1"


def test_two_duties_of_one_subject_are_still_two_claims() -> None:
    """Coordination with `and` keeps counting: each duty is a claim of its own."""
    from nlp.analysis import claim

    assert (
        claim("The device weighs 4 kg and it runs for 12 hours.", "en").predicates == 2
    )


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        (
            "en",
            "The bank blocks the card at once but sends a replacement within 5 days.",
        ),
        ("en", "The shop opens at 9:00 but closes at 14:00 on Saturdays."),
        ("de", "Die Filiale öffnet um 9 Uhr, aber schließt samstags um 14 Uhr."),
        (
            "de",
            "Das Sparkonto bringt 2 % Zinsen, aber erlaubt nur 3 Abhebungen im Monat.",
        ),
    ],
)
def test_a_but_clause_with_no_subject_of_its_own_is_still_a_second_claim(
    language: str, sentence: str
) -> None:
    """`opens at 9:00 but closes at 14:00` says two things of one shop."""
    from nlp.analysis import claim

    found = claim(sentence, language).predicates
    assert found == 2, f"{found} claim(s) read in {sentence!r}; expected 2"


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        (
            "en",
            (
                "Customers may return goods within 30 days, but refunds are only paid "
                "to the original card."
            ),
        ),
        (
            "de",
            (
                "Kunden können Waren binnen 30 Tagen zurückgeben, aber die Erstattung "
                "erfolgt nur auf die ursprüngliche Karte."
            ),
        ),
        (
            "en",
            (
                "The card is free of charge in the first year, but a fee of 30 EUR is "
                "charged from the second year."
            ),
        ),
        (
            "de",
            (
                "Die Karte ist im ersten Jahr gebührenfrei, jedoch wird ab dem zweiten "
                "Jahr eine Gebühr von 30 EUR berechnet."
            ),
        ),
        ("en", "The card is blocked and the account is closed."),
    ],
)
def test_a_clause_with_its_own_subject_is_still_a_second_claim(
    language: str, sentence: str
) -> None:
    """`X, but refunds are paid only to the card` says a second thing."""
    from nlp.analysis import claim

    found = claim(sentence, language).predicates
    assert found == 2, f"{found} claim(s) read in {sentence!r}; expected 2"


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        ("en", "A transfer can be cancelled, but only if it has not been executed."),
        (
            "de",
            (
                "Eine Überweisung kann storniert werden, aber nur wenn sie noch nicht "
                "ausgeführt wurde."
            ),
        ),
        ("en", "Goods can be returned, but only if they are unused."),
        ("de", "Waren können zurückgegeben werden, aber nur wenn sie unbenutzt sind."),
    ],
)
def test_a_coordinated_condition_is_one_claim_with_its_rule(
    language: str, sentence: str
) -> None:
    """`but only if` opens a condition the parser hangs as a conjunct; it restricts the rule."""
    from nlp.analysis import claim

    found = claim(sentence, language).predicates
    assert found == 1, f"{found} claim(s) read in {sentence!r}; expected 1"


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        (
            "de",
            (
                "Die Karte wird gesperrt, es sei denn, der Kunde ruft an und bestätigt "
                "die Zahlung."
            ),
        ),
        (
            "de",
            (
                "Das Paket wird zurückgeschickt, es sei denn, der Kunde holt es ab und "
                "zahlt die Gebühr."
            ),
        ),
        (
            "en",
            "The card is blocked unless the customer calls and confirms the payment.",
        ),
    ],
)
def test_every_member_of_the_case_left_out_restricts_the_rule(
    language: str, sentence: str
) -> None:
    """`es sei denn, A und B` leaves out one case; B is part of it, not a second rule."""
    from nlp.analysis import claim

    found = claim(sentence, language).predicates
    assert found == 1, f"{found} claim(s) read in {sentence!r}; expected 1"


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        (
            "en",
            (
                "Unless otherwise agreed, the bank charges a fee of 5 EUR, debits "
                "the account and informs the customer."
            ),
        ),
        (
            "de",
            (
                "Außer in Notfällen sperrt die Bank die Karte, informiert den Kunden "
                "und erstattet die Gebühr."
            ),
        ),
    ],
)
def test_rules_after_an_opening_exception_still_count(
    language: str, sentence: str
) -> None:
    """An exception opening the sentence restricts the rules after it, which are still several."""
    from nlp.analysis import claim

    found = claim(sentence, language).predicates
    assert found >= 2, f"{found} claim(s) read in {sentence!r}; expected at least 2"


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        (
            "en",
            (
                "The fee is charged on every transfer, but the bank refunds it if the "
                "transfer fails."
            ),
        ),
        (
            "de",
            (
                "Die Gebühr wird bei jeder Überweisung berechnet, aber die Bank erstattet "
                "sie, wenn die Überweisung scheitert."
            ),
        ),
        (
            "en",
            "The card is blocked and the account is closed unless the customer calls.",
        ),
        (
            "de",
            (
                "Die Karte wird gesperrt und das Konto wird geschlossen, es sei denn, der "
                "Kunde ruft an."
            ),
        ),
    ],
)
def test_a_second_rule_with_a_condition_of_its_own_is_still_a_claim(
    language: str, sentence: str
) -> None:
    """The condition belongs to the second rule, which is still said beside the first."""
    from nlp.analysis import claim

    found = claim(sentence, language).predicates
    assert found == 2, f"{found} claim(s) read in {sentence!r}; expected 2"


@pytest.mark.parametrize(
    "sentence",
    [
        (
            "If the customer accidentally enters the PIN incorrectly three times or "
            "the terminal rejects the card and the payment does not go through, the "
            "card is blocked."
        ),
        (
            "If the order was cancelled and the goods were already shipped and the "
            "shop cannot determine which parcel was sent first, the customer keeps "
            "the first parcel."
        ),
    ],
)
def test_a_parse_rooted_on_its_condition_is_one_claim(sentence: str) -> None:
    """The parser made the `if` clause the main one; the rule is still one."""
    from nlp.analysis import _read, claim

    roots = [token for token in _read(sentence, "en") if token.head == token]
    assert any(child.dep_ == "mark" for root in roots for child in root.children), (
        "the parse no longer roots this sentence on its condition"
    )
    assert claim(sentence, "en").predicates == 1


def _tagged(words, pos, tags, deps, heads):
    """A German Doc carrying the parse given rather than the tagger's."""
    from spacy.tokens import Doc

    from nlp.pipelines import pipeline

    return Doc(
        pipeline("de").vocab, words=words, pos=pos, tags=tags, deps=deps, heads=heads
    )


def test_a_finite_fine_tag_is_a_claim_when_the_morphology_drops_it() -> None:
    """`genügen` tagged VVFIN with the part of speech of an adjective still says something."""
    from nlp.analysis import _predicates, _untagged_claim

    statement = _tagged(
        ["Bei", "Kartenzahlungen", "genügen", "PIN", "und", "Unterschrift", "."],
        ["ADP", "NOUN", "ADJ", "PROPN", "CCONJ", "NOUN", "PUNCT"],
        ["APPR", "NN", "VVFIN", "NE", "KON", "NN", "$."],
        ["mo", "nk", "ROOT", "sb", "cd", "cj", "punct"],
        [2, 0, 2, 2, 3, 4, 2],
    )

    assert _predicates(statement) == 0, "the morphology carries no finite verb"
    assert _untagged_claim(statement)


def test_a_heading_tagged_with_no_finite_verb_still_asserts_nothing() -> None:
    """A German heading ending on its infinitive carries no finite fine tag."""
    from nlp.analysis import _untagged_claim

    heading = _tagged(
        ["Konto", "online", "eröffnen"],
        ["NOUN", "ADV", "VERB"],
        ["NN", "ADV", "VVINF"],
        ["oa", "mo", "ROOT"],
        [2, 2, 2],
    )

    assert not _untagged_claim(heading)


def test_a_noun_phrase_asserts_nothing() -> None:
    """A phrase with no finite verb reads as no claim."""
    from nlp.analysis import claim

    phrase = "Die Erhöhung der Eigenkapitalquote auf 12,5 Prozent"
    assert claim(phrase, "de").predicates == 0


@pytest.mark.parametrize(
    ("language", "statement", "figures"),
    [
        ("de", "Die Filiale öffnet um 08:00 Uhr.", ("08:00",)),
        ("en", "The limit is 2.5x the salary.", ("2.5x",)),
    ],
)
def test_a_time_or_glued_figure_is_a_figure(language, statement, figures) -> None:
    """A figure `like_num` does not mark is still one the statement states."""
    from nlp.analysis import claim

    assert claim(statement, language).figures == figures


def test_a_compound_carrying_a_figure_is_not_one() -> None:
    """`90-minütige` is a word with a number in it, not a figure."""
    from nlp.analysis import claim

    statement = "Das 90-minütige Beratungsgespräch ist kostenlos."
    assert claim(statement, "de").figures == ()


def test_a_hyphenated_compound_is_a_content_lemma() -> None:
    """`die KI-Verordnung der EU` is not about the EU alone."""
    from nlp.analysis import content

    assert "ki-verordnung" in content("die KI-Verordnung der EU", "de")


def test_a_name_written_with_a_lower_case_initial_is_kept() -> None:
    """`eGovernment` is a German noun with a capital, just not the first."""
    from nlp.analysis import content

    assert "egovernment" in content("Das eGovernment erfordert Tests.", "de")


@pytest.mark.parametrize(
    ("question", "asked"),
    [
        ("What happens when a test fails?", ("What",)),
        ("What is the tool that supports the review?", ("What",)),
        ("Wann wird ein Test wiederholt?", ("Wann",)),
    ],
)
def test_a_relative_or_subordinate_word_is_not_a_question_word(
    question: str, asked: tuple[str, ...]
) -> None:
    """`when a test fails` sets a condition; it asks nothing."""
    from nlp.analysis import interrogatives

    language = "de" if question.startswith("Wann") else "en"
    assert interrogatives(question, language) == asked


def test_a_german_relative_adverb_is_not_a_question_word() -> None:
    """`wo` opening a relative clause is tagged as a question word and asks nothing."""
    from nlp.analysis import interrogatives

    question = (
        "Ich wohne in einem Ort, wo es keine Filiale gibt. Warum muss ich zahlen?"
    )
    assert interrogatives(question, "de") == ("Warum",)


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        (
            "de",
            (
                "Die Bank erstattet den Betrag, wenn der Kunde die Ware innerhalb von "
                "14 Tagen zurücksendet, und der Kunde die Ware weder beschädigt noch "
                "benutzt hat."
            ),
        ),
        (
            "de",
            (
                "Die Bank erstattet den Betrag, wenn der Kunde die Ware zurücksendet, "
                "und die Ware unbeschädigt ist."
            ),
        ),
        (
            "de",
            (
                "Die Bank gewährt den Kredit auch ohne Bürgen, vorausgesetzt, der Kunde "
                "legt einen Gehaltsnachweis vor."
            ),
        ),
        (
            "de",
            (
                "Der Händler erstattet den Betrag, sofern die Ware unbeschädigt "
                "zurückkommt."
            ),
        ),
        ("en", "Employees may work from home provided their manager agrees."),
        (
            "en",
            "The bank refunds the fee as long as the card is not misused.",
        ),
        (
            "de",
            (
                "Der Kunde sendet die Ware zurück, tauscht sie um oder lässt sie "
                "reparieren."
            ),
        ),
        (
            "de",
            "Die Zahlung kann entweder per Karte oder per Überweisung erfolgen.",
        ),
        ("en", "The customer either returns the item or has it repaired."),
        (
            "en",
            (
                "The Terms changes in circular no. 33 are not included in the physical "
                "Terms of Sale book due to production timelines."
            ),
        ),
    ],
)
def test_one_rule_with_its_condition_or_alternatives_is_one_claim(
    language: str, sentence: str
) -> None:
    """A proviso, a verb-final condition, a list closed by "or" and a cut abbreviation."""
    from nlp.analysis import claim

    found = claim(sentence, language).predicates
    assert found == 1, f"{found} claim(s) read in {sentence!r}; expected 1"


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        ("en", "The bank blocks the card and the customer receives a letter."),
        ("de", "Die Bank sperrt die Karte und der Kunde erhält einen Brief."),
        (
            "en",
            (
                "The bank blocks the card, provided the card is lost, and the customer "
                "receives a letter."
            ),
        ),
        (
            "de",
            (
                "Die Bank sperrt die Karte, und der Kunde erhält einen Brief, weil die "
                "Karte verloren wurde."
            ),
        ),
    ],
)
def test_two_independent_main_clauses_are_still_two_claims(
    language: str, sentence: str
) -> None:
    """The repairs read a condition or an alternative, never a second assertion."""
    from nlp.analysis import claim

    found = claim(sentence, language).predicates
    assert found == 2, f"{found} claim(s) read in {sentence!r}; expected 2"


def test_a_language_with_no_row_reads_its_clauses_as_it_always_did() -> None:
    """A French pipeline is not configured: the same attachment rule, unchanged."""
    from nlp.analysis import claim

    sentence = (
        "La banque bloque la carte, pourvu que le client soit informé, et le "
        "client reçoit une lettre."
    )

    assert claim(sentence, "fr").predicates == 0
