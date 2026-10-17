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
        ("en", "Customers may return goods within 30 days but must keep the receipt."),
        ("en", "The bank may refuse the payment but must tell the customer why."),
        (
            "de",
            "Die Bank muss den Betrag nicht sofort erstatten, sondern kann ihn "
            "zunächst prüfen.",
        ),
    ],
)
def test_a_permission_with_its_but_limit_is_one_claim(
    language: str, sentence: str
) -> None:
    """A `but` clause with no subject of its own limits the rule it follows."""
    from nlp.analysis import claim

    found = claim(sentence, language).predicates
    assert found == 1, f"{found} claim(s) read in {sentence!r}; expected 1"


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        (
            "en",
            "Customers may return goods within 30 days, but refunds are only paid "
            "to the original card.",
        ),
        (
            "de",
            "Kunden können Waren binnen 30 Tagen zurückgeben, aber die Erstattung "
            "erfolgt nur auf die ursprüngliche Karte.",
        ),
        (
            "en",
            "The card is free of charge in the first year, but a fee of 30 EUR is "
            "charged from the second year.",
        ),
        (
            "de",
            "Die Karte ist im ersten Jahr gebührenfrei, jedoch wird ab dem zweiten "
            "Jahr eine Gebühr von 30 EUR berechnet.",
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
