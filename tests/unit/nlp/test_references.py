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
    "statement",
    [
        "A cover worn by a customer must not be dangerous to the person wearing it.",
        "The card is replaced free of charge for a customer losing it abroad.",
        "A fee is charged to the holder of the account for closing it early.",
    ],
)
def test_a_pronoun_of_a_participle_is_resolved_by_a_noun_of_its_phrase(
    statement: str,
) -> None:
    """`wearing it` has no subject a reader takes the person for."""
    from nlp.analysis import claim

    assert claim(statement, "en").references == ()


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
    ],
)
def test_a_noun_of_the_pronouns_own_clause_still_does_not_resolve_it(
    language: str, statement: str
) -> None:
    """A finite verb's clause, or a participle's subject or object, names it not."""
    from nlp.analysis import claim

    assert claim(statement, language).references


@pytest.mark.nlp
@pytest.mark.parametrize(
    "statement",
    [
        "Wird die Karte gesperrt, muss der Kunde sie zurückgeben.",
        "Geht die Karte verloren, sperrt die Bank sie sofort.",
        "Kommt die Ware beschädigt an, erstattet der Händler sie.",
    ],
)
def test_a_german_condition_opening_on_its_verb_is_a_clause_of_its_own(
    statement: str,
) -> None:
    """`Geht die Karte verloren, ...` names the card the main clause's `sie` is."""
    from nlp.analysis import claim

    assert claim(statement, "de").references == ()


@pytest.mark.nlp
@pytest.mark.parametrize(
    "statement",
    [
        "If the card is lost, this must be reported to the bank at once.",
        "The bank refunds the fee if this is requested in writing.",
        "The card is blocked if this is reported stolen.",
    ],
)
def test_an_english_demonstrative_standing_for_an_earlier_clause_is_resolved(
    statement: str,
) -> None:
    """`this` after `If the card is lost` is the loss, as German `dies` would be."""
    from nlp.analysis import claim

    assert claim(statement, "en").references == ()


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
    ("language", "statement", "before"),
    [
        ("en", "It is an offence if the PIN is shared.", "Payments are checked daily."),
        (
            "de",
            "Es ist ein Verstoß, wenn die PIN weitergegeben wird.",
            "Zahlungen werden täglich geprüft.",
        ),
        (
            "en",
            "It is very important for the customer to keep the PIN secret.",
            "The card is personal.",
        ),
    ],
)
def test_it_anticipating_the_clause_after_its_predicate_is_no_reference(
    language: str, statement: str, before: str
) -> None:
    """An infinitive, or a condition nothing said before could be named by `it`."""
    from nlp.analysis import claim

    assert claim(statement, language, before=before).references == ()


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "statement", "before"),
    [
        (
            "en",
            "It is free of charge if at least 1,000 EUR is paid in each month.",
            "The current account costs 5 EUR a month.",
        ),
        (
            "de",
            "Es ist gebührenfrei, wenn monatlich mindestens 1.000 EUR eingehen.",
            "Das Girokonto kostet 5 EUR im Monat.",
        ),
        (
            "de",
            "Es ist ein Verstoß, wenn die PIN weitergegeben wird.",
            "Das Konto ist persönlich.",
        ),
    ],
)
def test_it_before_a_condition_names_what_was_said_before(
    language: str, statement: str, before: str
) -> None:
    """After `The current account costs 5 EUR`, `It is free if ...` is the account."""
    from nlp.analysis import claim

    assert claim(statement, language, before=before).references


@pytest.mark.nlp
def test_it_before_a_condition_is_a_reference_where_nothing_before_is_known() -> None:
    """A question gate passes no context, and reads what it always read."""
    from nlp.analysis import claim

    assert claim("It is an offence if the PIN is shared.", "en").references == ("it",)
