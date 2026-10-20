"""When a pronoun is read as standing for something its statement names.

The German correlate `es` is tested on a stand-in token rather than a
sentence: what is under test is how a missing morphology feature is read,
and a pipeline that tags `es` at all tags its number, so no sentence
reliably leaves it off.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


class _Morph:
    """A token's morphology, as `token.morph.get` answers it."""

    def __init__(self, **features: list[str]) -> None:
        self._features = features

    def get(self, name: str) -> list[str]:
        return self._features.get(name, [])


def _es(number: list[str] | None):
    """`es` as subject of a plural verb with an object beside it."""
    head = SimpleNamespace(i=3, pos_="VERB", morph=_Morph(Number=["Plur"]), children=[])
    es = SimpleNamespace(
        i=1,
        text="es",
        morph=_Morph(**({"Number": number} if number else {})),
        doc=SimpleNamespace(lang_="de"),
        head=head,
    )
    head.children = [es, SimpleNamespace(i=2, dep_="oa")]
    return es


def test_an_es_with_its_number_disagreeing_with_the_verb_is_a_correlate() -> None:
    """The shape of "sofern es die Bedingungen gestatten"."""
    from nlp.analysis import _correlate

    assert _correlate(_es(["Sing"]))


def test_an_es_the_tagger_gave_no_number_is_not_a_correlate() -> None:
    """Nothing says it disagrees with its verb, so it stays a pronoun."""
    from nlp.analysis import _correlate

    assert not _correlate(_es(None))


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "statement"),
    [
        ("en", "The customer must return it within 14 days."),
        ("en", "At the branch, the customer must return it within 14 days."),
        ("en", "The customer has the right to return it within 14 days."),
        ("en", "Customers and staff are not allowed to use it."),
        ("de", "In der Filiale muss der Kunde sie zurückgeben."),
        ("de", "Der Kunde hat das Recht, ihn zurückzugeben."),
        ("en", "Customers in the shop have the right to return it within 30 days."),
        ("en", "The customer has the right to a refund after returning it."),
        (
            "en",
            (
                "Holders of a premium account may ask the bank to replace it free "
                "of charge."
            ),
        ),
        ("de", "Kunden im Ausland haben das Recht, es kostenlos zu nutzen."),
    ],
)
def test_a_noun_of_the_pronouns_own_clause_still_does_not_resolve_it(
    language: str, statement: str
) -> None:
    """No noun of the pronoun's own clause names it, a phrase's no more than a subject's.

    `it` in "Customers in the shop have the right to return it" is the goods
    the passage named before, not the shop.
    """
    from nlp.analysis import claim

    assert claim(statement, language).references


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("statement", "pointer"),
    [
        (
            "Geht die Zahlung ein, versendet der Händler sie innerhalb von 2 Tagen.",
            "sie",
        ),
        ("Wird das Konto eröffnet, sendet die Bank es per Post.", "es"),
        (
            (
                "Schreibt die Bank der Kundin, muss sie ihr innerhalb von 14 Tagen "
                "antworten."
            ),
            "ihr",
        ),
    ],
)
def test_a_german_condition_opening_on_its_verb_resolves_no_pronoun(
    statement: str, pointer: str
) -> None:
    """What the merchant ships once the payment arrives is the goods, not the payment."""
    from nlp.analysis import claim

    assert pointer in claim(statement, "de").references


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("statement", "pointer"),
    [
        ("This is blocked if the card is reported stolen.", "this"),
        ("These cards are blocked abroad.", "these"),
    ],
)
def test_an_opening_demonstrative_is_still_a_reference(
    statement: str, pointer: str
) -> None:
    """Nothing before it for the demonstrative to stand for."""
    from nlp.analysis import claim

    assert pointer in claim(statement, "en").references


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("statement", "pointer"),
    [
        ("When a customer opens an account, the bank sends this by post.", "this"),
        ("Before the account is opened, this must be signed by both holders.", "this"),
        ("Customers who open an account online can request this by phone.", "this"),
        ("When customers open an account, the bank sends these by post.", "these"),
    ],
)
def test_an_english_demonstrative_after_a_noun_or_a_clause_is_still_a_reference(
    statement: str, pointer: str
) -> None:
    """What the bank sends when an account is opened is a thing the passage named."""
    from nlp.analysis import claim

    assert pointer in claim(statement, "en").references


@pytest.mark.nlp
def test_it_before_a_condition_is_a_reference_where_nothing_before_is_known() -> None:
    """The statement alone does not say what `it` is, so it reads as pointing outside."""
    from nlp.analysis import claim

    assert claim("It is an offence if the PIN is shared.", "en").references == ("it",)


def _validated(language: str, statement: str, fact: str | None = None):
    """The fact checker's verdict on a fact, cited from a passage holding `statement`."""
    from drivers import Checker, passage

    return Checker(passage(statement, language=language)).atomic(fact or statement)


@pytest.mark.nlp
@pytest.mark.parametrize(
    "statement",
    [
        "Sie können Ihre Karte jederzeit online sperren.",
        "Sie können Ihre Waren innerhalb von 30 Tagen zurückgeben.",
        "Bitte senden Sie die Ware in der Originalverpackung zurück.",
        "Wenn Sie Ihre PIN vergessen haben, können Sie eine neue anfordern.",
        "Wenn Sie Ihr Konto überziehen, berechnet die Bank Zinsen.",
        "Sie erhalten Ihre Bestellung innerhalb von zwei Werktagen.",
    ],
)
def test_the_german_polite_sie_is_no_pronoun_pointing_outside(statement: str) -> None:
    """Formal address is spelled like the third person plural and names the reader."""
    from nlp.analysis import claim

    assert claim(statement, "de").references == ()
    assert _validated("de", statement).validated


@pytest.mark.nlp
@pytest.mark.parametrize(
    "statement",
    [
        "Sie wurde gesperrt.",
        "Sie kann am selben Tag ausgeführt werden.",
        "Sie werden innerhalb von 5 Tagen geliefert.",
        "Sie können Waren innerhalb von 30 Tagen zurückgeben.",
        "Sie haben keinen Anspruch auf Erstattung.",
    ],
)
def test_a_german_third_person_sie_with_no_antecedent_is_still_a_reference(
    statement: str,
) -> None:
    """The singular she, with a verb to say so, is someone the passage named."""
    from nlp.analysis import claim

    assert "sie" in claim(statement, "de").references
    result = _validated("de", statement)
    assert not result.validated
    assert result.rejection_code == "unresolved_reference"


@pytest.mark.nlp
def test_the_english_you_is_unchanged_by_the_polite_table() -> None:
    """English has no polite forms: `you` was never a reference and `they` still is."""
    from nlp.analysis import claim

    assert claim("You can block your card online at any time.", "en").references == ()
    assert claim("They can return items within 30 days.", "en").references == ("they",)


@pytest.mark.nlp
def test_a_lower_case_german_sie_is_the_third_person_whatever_follows_it() -> None:
    """Only the capital makes it polite."""
    from nlp.analysis import claim

    assert claim(
        "Wenn sie ihre Karte verlieren, sperrt die Bank sie.", "de"
    ).references == ("sie",)


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "statement"),
    [
        ("de", "Ein Artikel kann zurückgegeben werden, es sei denn, er wurde benutzt."),
        (
            "de",
            "Eine Überweisung wird am selben Tag ausgeführt, es sei denn, sie wird nach 16 Uhr eingereicht.",
        ),
        ("de", "Das Konto bleibt kostenlos, es sei denn, es wird überzogen."),
        ("de", "Die Karte wird gesperrt, außer sie wurde bereits ersetzt."),
        ("en", "The card is blocked, except when it has already been replaced."),
        ("en", "An item can be returned, provided it is unused."),
        ("en", "The account is free, except where it is overdrawn."),
    ],
)
def test_a_pronoun_after_an_exception_points_back_at_the_subject_of_its_own_sentence(
    language: str, statement: str
) -> None:
    """The exception's clause is the rule's own subject's, whatever the parser hangs it on."""
    from nlp.analysis import claim

    assert claim(statement, language).references == ()
    assert _validated(language, statement).validated


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "statement"),
    [
        ("de", "Es sei denn, sie wird eingereicht."),
        ("en", "Unless it is unused, nothing is refunded."),
        ("en", "Except where it is overdrawn, nothing is charged."),
    ],
)
def test_a_pronoun_after_an_exception_with_no_noun_before_it_is_still_a_reference(
    language: str, statement: str
) -> None:
    """The singular she, with a verb to say so, is someone the passage named."""
    from nlp.analysis import claim

    assert claim(statement, language).references != ()
    assert not _validated(language, statement).validated


@pytest.mark.nlp
@pytest.mark.parametrize(
    "statement",
    [
        "Wenn die Karte gesperrt ist, gilt dies als Kündigung.",
        "Wenn ein Kunde seine Karte verliert, muss er dies sofort melden.",
        "Wenn die Ware beschädigt ankommt, gilt dies als Reklamationsgrund.",
        "Wenn das Konto überzogen wird, teilt die Bank dies dem Kunden mit.",
    ],
)
def test_a_german_dies_standing_for_the_clause_before_it_in_its_sentence_resolves(
    statement: str,
) -> None:
    """The singular she, with a verb to say so, is someone the passage named."""
    from nlp.analysis import claim

    assert claim(statement, "de").references == ()
    assert _validated("de", statement).validated


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("passage_text", "statement"),
    [
        ("Die Karte ist gesperrt.", "Dies gilt als Kündigung."),
        (
            "Die Karte ist gesperrt. Dies gilt als Kündigung.",
            "Dies gilt als Kündigung.",
        ),
        ("Die Ware ist beschädigt.", "Dies ist ein Reklamationsgrund."),
    ],
)
def test_a_german_dies_with_no_clause_before_it_is_still_a_reference(
    passage_text: str, statement: str
) -> None:
    """Only the capital makes it polite."""
    from nlp.analysis import claim

    assert claim(statement, "de").references == ("dies",)
    result = _validated("de", passage_text, statement)
    assert not result.validated
    assert result.rejection_code == "unresolved_reference"


@pytest.mark.nlp
@pytest.mark.parametrize(
    "statement",
    [
        "Für Konten, die Zinsen zahlen, gilt dies nicht.",
        "Bei Filialen, die ihre Kunden bedienen, gilt dies nicht.",
        "Für Kunden, die ihre Ware zurückgeben, gilt dies nicht.",
        "Für Karten, die gesperrt wurden, gilt dies nicht.",
    ],
)
def test_a_german_dies_after_only_a_relative_clause_is_still_a_reference(
    statement: str,
) -> None:
    """A relative clause modifies a noun and states nothing for `dies` to stand for."""
    from nlp.analysis import claim

    assert claim(statement, "de").references == ("dies",)
    result = _validated("de", statement)
    assert not result.validated
    assert result.rejection_code == "unresolved_reference"


@pytest.mark.nlp
@pytest.mark.parametrize(
    "statement",
    [
        "Wenn die Karte gesperrt ist, gilt dies als Kündigung.",
        "Wenn ein Kunde seine Karte verliert, muss er dies sofort melden.",
        "Weil die Ware beschädigt ist, gilt dies als Reklamationsgrund.",
        "Die Bank sperrt das Konto, und dies gilt als Kündigung.",
    ],
)
def test_a_german_dies_after_a_conditional_causal_or_main_clause_resolves(
    statement: str,
) -> None:
    """A wenn or weil clause, or a main clause, is a proposition `dies` may stand for."""
    from nlp.analysis import claim

    assert claim(statement, "de").references == ()
