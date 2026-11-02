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
    "passage_text",
    [
        "Sie erhalten die Erstattung innerhalb von 14 Tagen. Bitte geben Sie dafür Ihre IBAN an.",
        "Sie erhalten die Erstattung innerhalb von 14 Tagen. Die Gutschrift erfolgt auf Ihr Girokonto.",
        "Sie erhalten die Erstattung innerhalb von 14 Tagen. Die Rücksendung ist für Sie kostenlos.",
    ],
)
def test_an_opening_sie_is_polite_where_its_passage_addresses_the_reader(
    passage_text: str,
) -> None:
    """A polite form inside a sentence of the cited passage says who `Sie` is."""
    from nlp.analysis import claim

    statement = "Sie erhalten die Erstattung innerhalb von 14 Tagen."
    assert claim(statement, "de", (passage_text,)).references == ()
    assert claim(statement, "de").references == ("sie",), "no passage, no address"
    result = _validated("de", passage_text, statement)
    assert result.validated, (result.rejection_code, result.validation_error)


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("passage_text", "cites"),
    [
        (
            "Die Händler prüfen jede Ware. Sie erstatten den Preis innerhalb von 14 Tagen.",
            1,
        ),
        (
            "Sie erstatten den Preis innerhalb von 14 Tagen. Ihre Prüfung dauert zwei Tage.",
            0,
        ),
        (
            "Die Banken prüfen, ob sie zahlen. Sie erstatten den Preis innerhalb von 14 Tagen.",
            1,
        ),
    ],
)
def test_an_opening_sie_stays_a_reference_where_its_passage_addresses_no_one(
    passage_text: str, cites: int
) -> None:
    """A polite form opening a sentence is capitalised either way, so it says nothing."""
    from drivers import Checker, passage

    statement = "Sie erstatten den Preis innerhalb von 14 Tagen."
    result = Checker(passage(passage_text, language="de")).atomic(statement, cites)
    assert not result.validated
    assert result.rejection_code == "unresolved_reference"


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("passage_text", "statement"),
    [
        (
            (
                "Bitte geben Sie Ihre IBAN an. Händler, die am Programm "
                "teilnehmen, werben neue Kunden. Sie erhalten dafür eine "
                "Provision von 20 Euro."
            ),
            "Sie erhalten eine Provision von 20 Euro.",
        ),
        (
            (
                "Bitte prüfen Sie Ihre Kontoauszüge. Die Banken melden jeden "
                "Fehler. Sie erstatten den Betrag innerhalb von 14 Tagen."
            ),
            "Sie erstatten den Betrag innerhalb von 14 Tagen.",
        ),
    ],
)
def test_an_opening_sie_after_a_plural_subject_stays_a_reference(
    passage_text: str, statement: str
) -> None:
    """The passage addresses its reader, but the Sie can be the plural just named."""
    from drivers import Checker, passage

    result = Checker(passage(passage_text, language="de")).atomic(statement, 2)
    assert not result.validated
    assert result.rejection_code == "unresolved_reference"


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
        "Wer die Karte verliert, muss dies sofort melden.",
        "Wer eine Ware beschädigt zurückschickt, muss dies vorher anzeigen.",
        "Wer sein Konto überzieht, muss dies innerhalb von 30 Tagen ausgleichen.",
    ],
)
def test_a_german_dies_after_a_free_relative_clause_resolves(statement: str) -> None:
    """A `wer` clause with no noun to modify states the event, as a `wenn` clause does."""
    from nlp.analysis import claim

    assert claim(statement, "de").references == ()
    result = _validated("de", statement)
    assert result.validated, (result.rejection_code, result.validation_error)


@pytest.mark.nlp
@pytest.mark.xfail(
    strict=True,
    reason="known limit (nlp README): dies after a wenn clause or a free relative "
    "is read as standing for that clause even where it names a thing received "
    "or paid, which the parse cannot tell from an event",
)
@pytest.mark.parametrize(
    "statement",
    [
        "Wer ein Konto eröffnet, erhält dies per Post.",
        "Wer bestellt, zahlt dies per Rechnung.",
    ],
)
def test_dies_received_after_a_free_relative_stays_a_reference(statement: str) -> None:
    """What one receives or pays is a thing named elsewhere, not the event."""
    from nlp.analysis import claim

    assert "dies" in claim(statement, "de").references


@pytest.mark.nlp
@pytest.mark.parametrize(
    "statement",
    [
        "Wenn die Karte gesperrt wurde, gilt dies als Kündigung.",
        "Wenn die Ware beschädigt geliefert wurde, gilt dies als Reklamationsgrund.",
    ],
)
def test_a_german_dies_after_a_finite_auxiliary_of_a_conditional_resolves(
    statement: str,
) -> None:
    """The auxiliary heads nothing, but it sits in the condition and not in the clause of `dies`."""
    from nlp.analysis import claim

    assert claim(statement, "de").references == ()


@pytest.mark.nlp
@pytest.mark.parametrize(
    "statement",
    [
        "Nach Artikel 5 gilt dies als Kündigung.",
        "Laut den Bedingungen ist dies ein Reklamationsgrund.",
    ],
)
def test_a_german_dies_after_only_the_verb_of_its_own_clause_is_still_a_reference(
    statement: str,
) -> None:
    """The finite verb before it is its own clause's, so nothing earlier is stood for."""
    from nlp.analysis import claim

    assert claim(statement, "de").references == ("dies",)


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


@pytest.mark.nlp
@pytest.mark.parametrize(
    "statement",
    [
        "Die Karte ist gesperrt; dies gilt als Kündigung.",
        "Das Konto ist überzogen; dies gilt als Vertragsverletzung.",
        "Die Ware ist beschädigt; dies ist ein Reklamationsgrund.",
    ],
)
def test_a_german_dies_standing_for_a_clause_before_a_semicolon_resolves(
    statement: str,
) -> None:
    """The verb before it is finite and in a clause of its own, though it carries no conjunction."""
    from nlp.analysis import claim

    assert claim(statement, "de").references == ()


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "statement", "pointer"),
    [
        ("de", "Die Bank und deren Lieferanten halten die Regeln ein.", "deren"),
        ("de", "Der Händler und dessen Lieferant haften gemeinsam.", "dessen"),
        ("en", "All fees apply except those related to the price cap.", "those"),
        (
            "en",
            "The bank refunds charges other than those levied by third parties.",
            "those",
        ),
    ],
)
def test_a_pronoun_whose_antecedent_or_clause_is_in_the_statement_resolves(
    language: str, statement: str, pointer: str
) -> None:
    """A genitive "of whom" names the noun before it; "those" with its own clause names what it says."""
    from nlp.analysis import claim

    assert pointer not in claim(statement, language).references


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("statement", "pointer"),
    [
        ("Those are blocked abroad.", "those"),
        ("Deren Lieferanten halten die Regeln ein.", "deren"),
    ],
)
def test_a_genitive_or_those_with_nothing_before_it_still_points_outside(
    statement: str, pointer: str
) -> None:
    """No noun before it, and no clause of its own, so the passage is where it points."""
    from nlp.analysis import claim

    language = "de" if pointer == "deren" else "en"
    assert pointer in claim(statement, language).references


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "statement", "title", "pointer", "names_document"),
    [
        (
            "en",
            "These terms apply to every order placed online.",
            "General Terms and Conditions of Sale",
            "these",
            True,
        ),
        (
            "de",
            "Diese Bedingungen gelten für jede Bestellung im Onlineshop.",
            "Allgemeine Geschäftsbedingungen",
            "diese",
            True,
        ),
        (
            "en",
            "These regulations apply to every customer.",
            "Customer Regulations\nEdition 2026",
            "these",
            True,
        ),
        (
            "en",
            "These regulations apply to every customer.",
            "Customer Regulations / Edition 2026",
            "these",
            True,
        ),
        (
            "en",
            "These provisions apply to every customer.",
            "Customer Regulations / Edition 2026",
            "these",
            False,
        ),
        (
            "en",
            "These provisions apply to every customer.",
            "Bank Customer Regulations Edition 2026",
            "these",
            False,
        ),
        (
            "en",
            "These terms apply to every order placed online.",
            None,
            "these",
            False,
        ),
        (
            "de",
            "Diese Bedingungen gelten für jedes Sparkonto.",
            "Sparkonto Sonderbedingungen",
            "diese",
            True,
        ),
        (
            "en",
            "These regulations apply to every customer.",
            "Bank Customer Regulations Edition 2026",
            "these",
            True,
        ),
        (
            "en",
            "This bank pays interest every month.",
            "Bank Customer Regulations Edition 2026",
            "this",
            False,
        ),
        (
            "en",
            "These terms apply to every order placed online.",
            "Online Store Terms Version 3",
            "these",
            True,
        ),
        (
            "en",
            "This shop opens at 9 am.",
            "Online Shop Terms Version 3",
            "this",
            False,
        ),
        # A number after a head that is not a plural names nothing before it.
        (
            "en",
            "This card may be used abroad.",
            "Credit Card Conditions 2025",
            "this",
            False,
        ),
        (
            "en",
            "This card may be used abroad.",
            "Debit Card Rules 2026",
            "this",
            False,
        ),
        (
            "en",
            "This fee is waived for students.",
            "Fee Schedule 2026",
            "this",
            False,
        ),
        (
            "en",
            "This price includes VAT.",
            "Price List 2026",
            "this",
            False,
        ),
        (
            "en",
            "This account pays interest monthly.",
            "Savings Account Terms 2025",
            "this",
            False,
        ),
        (
            "en",
            "This shop opens at 9 am.",
            "Online Shop Terms 2025",
            "this",
            False,
        ),
        (
            "de",
            "Dieses Konto wird monatlich verzinst.",
            "Sonderbedingungen Sparkonto 2025",
            "dieses",
            False,
        ),
        (
            "de",
            "Diese Karte kann im Ausland genutzt werden.",
            "Kreditkartenbedingungen Ausgabe 2025",
            "diese",
            False,
        ),
        # A modifier of the title's head noun is not what the title names.
        ("en", "This card can be used abroad.", "Credit Card Agreement", "this", False),
        (
            "en",
            "This card can be used abroad.",
            "Credit Card Terms and Conditions",
            "this",
            False,
        ),
        (
            "en",
            "This account pays interest every month.",
            "Savings Account Conditions",
            "this",
            False,
        ),
        (
            "en",
            "This product must be returned in its original packaging.",
            "Product Return Policy",
            "this",
            False,
        ),
        ("en", "This store opens at 9 am.", "Online Store Terms of Use", "this", False),
        (
            "de",
            "Dieses Konto wird monatlich abgerechnet.",
            "Sparkonto Sonderbedingungen",
            "dieses",
            False,
        ),
        (
            "de",
            "Diese Karte ist drei Jahre gültig.",
            "Kreditkarte Bedingungen",
            "diese",
            False,
        ),
        (
            "en",
            "These services are free of charge.",
            "Payment Services Terms 2026",
            "these",
            False,
        ),
        (
            "en",
            "These cards can be used abroad.",
            "Payment Cards Terms 2025",
            "these",
            False,
        ),
        (
            "en",
            "These funds may lose value.",
            "Investment Funds Terms 2026",
            "these",
            False,
        ),
        (
            "en",
            "These terms apply to every payment.",
            "Payment Services Terms 2026",
            "these",
            True,
        ),
        (
            "de",
            "Dieses Konto wird monatlich abgerechnet.",
            "Girokonto Preisverzeichnis 2026",
            "dieses",
            False,
        ),
        (
            "de",
            "Dieser Onlineshop liefert nur nach Deutschland.",
            "Onlineshop AGB",
            "dieser",
            False,
        ),
        (
            "de",
            "Diese Karten können im Ausland genutzt werden.",
            "Kreditkarten Bedingungen 2025",
            "diese",
            False,
        ),
        (
            "en",
            "These terms apply to all accounts.",
            "Terms and Conditions",
            "these",
            True,
        ),
    ],
)
def test_a_demonstrative_naming_the_head_of_the_documents_title_names_the_document(
    language, statement, title, pointer, names_document
) -> None:
    """Under a title about terms, "these terms" is the document itself."""
    from nlp.analysis import claim

    found = claim(statement, language, title=title).references

    assert (pointer not in found) == names_document, found


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "statement", "title"),
    [
        (
            "fr",
            "Ces conditions s'appliquent à toute commande.",
            "Conditions générales de vente",
        ),
        (
            "fr",
            "Cette carte peut être utilisée à l'étranger.",
            "Contrat de carte de crédit",
        ),
        (
            "pl",
            "Te warunki obowiązują wszystkie zamówienia.",
            "Ogólne warunki sprzedaży",
        ),
    ],
)
def test_a_title_changes_nothing_in_a_language_no_pipeline_is_configured_for(
    language: str, statement: str, title: str
) -> None:
    """French and Polish read no demonstrative here, with or without a title."""
    from nlp.analysis import claim

    titled = claim(statement, language, title=title)

    assert titled.references == claim(statement, language).references


# ── Words that point back, read as the question side reads them ──────────


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "statement"),
    [
        ("en", "The latter costs 5 EUR a month."),
        ("en", "The former is free of charge."),
        ("en", "The latter card costs 5 EUR a month."),
        ("de", "Letztere kosten 5 Euro im Monat."),
        ("de", "Die letztere Karte kostet 5 Euro im Monat."),
        ("de", "Der erstere ist kostenlos."),
        ("de", "Die oben genannte Gebühr gilt für jedes Konto."),
    ],
)
def test_a_word_pointing_back_leaves_a_reference(language: str, statement: str) -> None:
    """The fact check reads the words the question side reads as the head of its phrase."""
    from nlp.analysis import claim

    assert claim(statement, language).references, statement


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "statement"),
    [
        ("en", "The debit card is free, and the latter of the two cards costs 5 EUR."),
        (
            "de",
            "Die Debitkarte ist kostenlos, die letztere der beiden Karten kostet 5 Euro.",
        ),
    ],
)
def test_a_pointing_word_inside_a_statement_naming_both_leaves_nothing(
    language: str, statement: str
) -> None:
    """Only a word opening the statement, before its verb, points outside it."""
    from nlp.analysis import claim

    assert not claim(statement, language).references, statement


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "statement"),
    [
        ("fr", "Le dernier coûte 5 euros par mois."),
        ("fr", "Les frais mentionnés ci-dessus s'appliquent."),
        ("pl", "Ten drugi kosztuje 5 euro miesięcznie."),
        ("el", "Ο τελευταίος κοστίζει 5 ευρώ τον μήνα."),
    ],
)
def test_a_language_with_no_row_in_the_pointing_table_reads_no_such_word(
    language: str, statement: str
) -> None:
    """The table is keyed by language: a word of another one is never read as a pointer."""
    from nlp.analysis import _ANAPHORIC, _opens, parse

    assert language not in _ANAPHORIC
    assert not any(_opens(token) for token in parse(statement, language)[:3])


# ── A pronoun with no noun of its own opening the statement ──────────────


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "statement"),
    [
        ("en", "Both cost 5 EUR a month."),
        ("en", "The others are free of charge."),
        ("en", "Some require a deposit."),
        ("de", "Beide kosten 5 Euro im Monat."),
        ("de", "Die anderen sind kostenlos."),
        ("de", "Alle zahlen 5 Euro im Monat."),
    ],
)
def test_a_bare_quantifier_as_the_subject_is_a_reference(
    language: str, statement: str
) -> None:
    """Both, the others, some: stand for something the statement never named."""
    from nlp.analysis import claim

    assert claim(statement, language).references, statement


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "statement"),
    [
        ("en", "Anyone may open an account."),
        ("en", "Everyone must sign the form."),
        ("en", "Nobody may withdraw more than 500 EUR."),
        ("de", "Jeder kann ein Konto eröffnen."),
        ("de", "Jeder Kunde kann ein Konto eröffnen."),
        ("de", "Man darf höchstens 500 Euro abheben."),
        ("de", "Niemand darf mehr abheben."),
        ("en", "Both cards cost 5 EUR a month."),
        ("de", "Beide Karten kosten 5 Euro im Monat."),
    ],
)
def test_a_person_generic_subject_or_one_with_its_noun_is_no_reference(
    language: str, statement: str
) -> None:
    """A singular generic person names nobody earlier, and a quantifier with a noun has one."""
    from nlp.analysis import claim

    assert not claim(statement, language).references, statement


def _quantifier(language: str, lemma: str, pos: str, morph: str):
    """A subject made by hand, in a language no pipeline here reads."""
    import spacy
    from spacy.tokens import Doc

    return Doc(
        spacy.blank(language).vocab,
        words=[lemma, "x", "y", "."],
        lemmas=[lemma, "x", "y", "."],
        heads=[1, 1, 1, 1],
        deps=["nsubj", "ROOT", "obj", "punct"],
        pos=[pos, "VERB", "NOUN", "PUNCT"],
        morphs=[morph, "", "", ""],
    )[0]


@pytest.mark.nlp
def test_the_reading_is_by_morphology_so_a_language_not_configured_reads_the_same() -> (
    None
):
    """A plural total pronoun is a reference in French and Greek as in German; its 'other' word is in no table."""
    from nlp.analysis import _refers

    assert _refers(_quantifier("fr", "tous", "PRON", "Number=Plur|PronType=Tot"))
    assert _refers(_quantifier("el", "όλοι", "PRON", "Number=Plur|PronType=Tot"))
    assert not _refers(_quantifier("fr", "chacun", "PRON", "Number=Sing|PronType=Ind"))
    # 'les autres' is a noun to the tagger and French has no row in the table of
    # nominalised 'other': inert.
    assert not _refers(_quantifier("fr", "autre", "NOUN", "Number=Plur"))
    assert not _refers(_quantifier("el", "άλλος", "NOUN", "Number=Plur"))


# ── A German placeholder es before its clause ────────────────────────────


@pytest.mark.nlp
@pytest.mark.parametrize(
    "statement",
    [
        "Es ist verboten, die PIN auf der Karte zu notieren.",
        "Es ist wichtig, dass der Kunde die PIN geheim hält.",
        "Es ist kostenlos, Kontoauszüge online abzurufen.",
        "Es wird empfohlen, die PIN regelmäßig zu ändern.",
    ],
)
def test_a_german_placeholder_before_its_clause_is_no_reference(statement: str) -> None:
    """The parse hangs the zu-infinitive or dass clause on the pronoun itself."""
    from nlp.analysis import claim

    assert not claim(statement, "de").references


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "statement", "refused"),
    [
        ("de", "Es kostet 5 Euro im Monat.", True),
        ("en", "It costs 5 EUR a month.", True),
        ("en", "It is forbidden to write the PIN on the card.", False),
        ("en", "It is important that the customer keeps the PIN secret.", False),
    ],
)
def test_a_pronoun_with_no_clause_after_it_still_points_outside(
    language: str, statement: str, refused: bool
) -> None:
    """The English twins are unchanged; a bare es is still a pronoun."""
    from nlp.analysis import claim

    assert bool(claim(statement, language).references) is refused


def _placeholder(language: str, gender: str):
    """'It is possible to close the account', parsed by hand in a language of its own."""
    import spacy
    from spacy.tokens import Doc

    return Doc(
        spacy.blank(language).vocab,
        words=["It", "is", "possible", "to", "close", "the", "account", "."],
        heads=[1, 1, 1, 4, 1, 6, 4, 1],
        deps=["nsubj", "ROOT", "acomp", "mark", "xcomp", "det", "dobj", "punct"],
        pos=["PRON", "AUX", "ADJ", "PART", "VERB", "DET", "NOUN", "PUNCT"],
        morphs=[
            f"Gender={gender}|Number=Sing|Person=3|PronType=Prs",
            "",
            "",
            "",
            "VerbForm=Inf",
            "",
            "Number=Sing",
            "",
        ],
    )[0]


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "gender", "is_placeholder"),
    [
        ("en", "Neut", True),
        ("en", "Masc", True),
        ("de", "Neut", True),
        ("de", "Masc", False),
        ("fr", "Masc", False),
        ("pl", "Neut", False),
        ("el", "Neut", False),
    ],
)
def test_the_gender_a_placeholder_carries_comes_from_the_languages_table(
    language: str, gender: str, is_placeholder: bool
) -> None:
    """No language code is branched on: one with no row reads no placeholder."""
    from nlp.analysis import _clausal_correlate

    assert _clausal_correlate(_placeholder(language, gender)) is is_placeholder


@pytest.mark.nlp
def test_a_newly_configured_language_supplies_its_row_and_nothing_else(
    monkeypatch,
) -> None:
    """French 'Il est possible de ...': one row of the table makes the pronoun a placeholder."""
    from nlp import analysis

    monkeypatch.setitem(analysis._PLACEHOLDER_GENDER, "fr", "Masc")

    assert analysis._clausal_correlate(_placeholder("fr", "Masc"))
    assert not analysis._clausal_correlate(_placeholder("fr", "Fem"))


# ── What names the document ──────────────────────────────────────────────


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "statement"),
    [
        ("en", "This section applies to all current accounts."),
        ("en", "This clause applies to all current accounts."),
        ("en", "This brochure applies to all current accounts."),
        ("de", "Dieser Abschnitt gilt für alle Girokonten."),
        ("de", "Diese Ziffer gilt für alle Girokonten."),
        ("de", "Dieses Merkblatt gilt für alle Girokonten."),
    ],
)
def test_a_part_of_a_document_or_its_genre_noun_points_like_any_noun(
    language: str, statement: str
) -> None:
    """With no title naming it, 'this section' and 'this clause' are judged alike."""
    from nlp.analysis import claim

    assert claim(statement, language).references, statement


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "statement", "title"),
    [
        ("en", "This brochure applies to all current accounts.", "Account brochure"),
        ("de", "Dieses Merkblatt gilt für alle Girokonten.", "Merkblatt zum Girokonto"),
        ("en", "This policy applies to all current accounts.", "Privacy policy"),
    ],
)
def test_a_demonstrative_naming_the_title_head_noun_still_names_the_document(
    language: str, statement: str, title: str
) -> None:
    """The document's own title says what it is called."""
    from nlp.analysis import claim

    assert not claim(statement, language, title=title).references


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "statement", "title"),
    [
        ("fr", "Cette brochure s'applique à tous les comptes.", "Brochure du compte"),
        (
            "el",
            "Αυτό το φυλλάδιο ισχύει για όλους τους λογαριασμούς.",
            "Φυλλάδιο λογαριασμού",
        ),
    ],
)
def test_a_language_no_pipeline_is_configured_for_reads_no_source_noun_either(
    language: str, statement: str, title: str
) -> None:
    """No table of nouns is consulted, so a title changes nothing there."""
    from nlp.analysis import claim

    assert (
        claim(statement, language, title=title).references
        == claim(statement, language).references
    )


# ── Where no language has a noun_chunks iterator ─────────────────────────


@pytest.mark.parametrize("language", ["pl", "cs", "ro", "hr", "sl", "lt"])
def test_phrases_are_none_where_spacy_has_no_noun_chunks_for_the_language(
    language: str, monkeypatch
) -> None:
    """The gates reading phrases() then abstain; a configured Polish does not crash them."""
    import spacy
    from spacy.tokens import Doc

    from nlp import analysis

    doc = Doc(
        spacy.blank(language).vocab,
        words=["Klient", "składa", "wniosek", "."],
        heads=[1, 1, 1, 1],
        deps=["nsubj", "ROOT", "obj", "punct"],
        pos=["NOUN", "VERB", "NOUN", "PUNCT"],
    )
    monkeypatch.setattr(analysis, "_read", lambda text, language: doc)

    assert analysis.phrases("Klient składa wniosek.", language) == ()


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("language", "text"),
    [
        ("de", "Der Kunde eröffnet ein Konto."),
        ("en", "The customer opens an account."),
    ],
)
def test_phrases_are_read_where_the_language_has_noun_chunks(
    language: str, text: str
) -> None:
    """The two configured languages are unchanged."""
    from nlp.analysis import phrases

    assert phrases(text, language)


# ── The reader a polite Sie opens a statement for ────────────────────────

_ADDRESSED = {
    "de": "Bitte geben Sie Ihre IBAN an. Die Karte ist kostenlos. {statement}",
}


@pytest.mark.nlp
@pytest.mark.parametrize(
    "statement",
    [
        "Sie gilt drei Jahre.",
        "Sie wird monatlich abgebucht.",
        "Sie dauert zwei Werktage.",
    ],
)
def test_an_opening_sie_with_a_singular_verb_is_the_feminine_third_person(
    statement: str,
) -> None:
    """Polite Sie takes a plural verb: 'Sie gilt' stands for 'die Karte' and dangles."""
    from drivers import Checker, passage

    text = _ADDRESSED["de"].format(statement=statement)
    judged = Checker(passage(text, language="de")).atomic(statement, 2)

    assert not judged.validated
    assert judged.rejection_code == "unresolved_reference"


@pytest.mark.nlp
def test_the_english_twin_of_a_dangling_sie_is_refused_too() -> None:
    """Control: the same shape in English."""
    from drivers import Checker, passage

    text = "Please enter your IBAN. The card is free. It is valid for three years."
    judged = Checker(passage(text, language="en")).atomic(
        "It is valid for three years.", 2
    )

    assert judged.rejection_code == "unresolved_reference"


@pytest.mark.nlp
@pytest.mark.parametrize(
    ("text", "statement", "cites"),
    [
        (
            "Bitte geben Sie Ihre IBAN an. Sie erhalten eine Bestätigung per E-Mail.",
            "Sie erhalten eine Bestätigung per E-Mail.",
            1,
        ),
        (
            (
                "Bei kostenlosen Diensten haben Sie das Recht zu erfahren, wie Ihre Daten "
                "verwendet werden. Sie sollten auch die Vertragsdauer kennen."
            ),
            "Sie sollten die Vertragsdauer kennen.",
            1,
        ),
        (
            (
                "Bei kostenlosen Diensten haben Sie das Recht zu erfahren, wie Ihr Konto "
                "geführt wird. Sie sollten auch die Vertragsdauer kennen."
            ),
            "Sie sollten die Vertragsdauer kennen.",
            1,
        ),
    ],
)
def test_a_polite_sie_stays_polite_whatever_number_a_clause_before_it_holds(
    text: str, statement: str, cites: int
) -> None:
    """The reader addressed in the sentence before is the reader, embedded plural or not."""
    from drivers import Checker, passage

    judged = Checker(passage(text, language="de")).atomic(statement, cites)

    assert judged.validated, (judged.rejection_code, judged.validation_error)


@pytest.mark.nlp
def test_a_third_person_plural_after_a_plural_subject_is_still_a_reference() -> None:
    """The rival reading the rule exists for: 'Händler werben Kunden. Sie erhalten ...'."""
    from drivers import Checker, passage

    judged = Checker(
        passage("Händler werben Kunden. Sie erhalten Rabatte.", language="de")
    ).atomic("Sie erhalten Rabatte.", 1)

    assert not judged.validated
