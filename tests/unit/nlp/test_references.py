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
