"""Which passages never reach the model.

A heading or a caption returns its own text back as a fact.
"""

from __future__ import annotations

import pytest
from factories import passage

from extraction.service import skipped

pytestmark = pytest.mark.nlp


def test_a_passage_carrying_a_claim_is_extracted() -> None:
    """Prose asserting something is not skipped."""
    assert skipped(passage()) is None


@pytest.mark.parametrize(
    "text", ["3.2 Lieferung und Versand", "Tabelle 1: Modelle", "Risiko"]
)
def test_a_passage_with_no_finite_verb_is_skipped(text: str) -> None:
    """A heading or a caption asserts nothing."""
    assert skipped(passage(text, language="de")) == "no finite verb", text


@pytest.mark.parametrize(
    ("language", "path", "text"),
    [
        (
            "en",
            "Glossary > Chargeback",
            "Reversal of a card payment by the card issuer.",
        ),
        (
            "en",
            "Glossary > Click and collect",
            "Ordering online and picking the goods up in a store.",
        ),
        (
            "en",
            "Glossary > Dormant account",
            "An account with no payment by its holder for 24 months.",
        ),
        (
            "de",
            "Glossar > Rückbuchung",
            "Rückgängigmachen einer Kartenzahlung durch den Kartenaussteller.",
        ),
        (
            "de",
            "Glossar > Dispositionskredit",
            (
                "Ein Kredit, den die Bank auf dem Girokonto bis zu einem "
                "vereinbarten Rahmen gewährt."
            ),
        ),
        (
            "de",
            "Begriffe > Retoure",
            "Rücksendung einer bestellten Ware an den Händler.",
        ),
    ],
)
def test_a_definition_under_the_term_it_defines_is_read(language, path, text) -> None:
    """A glossary entry has no verb: its heading names what the phrase is."""
    assert skipped(passage(text, language=language, section_path=path)) is None


@pytest.mark.parametrize(
    ("language", "path", "text"),
    [
        ("en", "Fees > Transfers", "See Section 7 for the fees."),
        ("de", "Gebühren > Überweisungen", "Siehe Abschnitt 7."),
        ("en", "Figures > Monthly fees", "Figure 3: Monthly fees by account type."),
        (
            "de",
            "Abbildungen > Gebühren",
            "Abbildung 3: Monatliche Gebühren nach Kontoart.",
        ),
        ("en", "Abbreviations > IBAN", "IBAN: International Bank Account Number."),
        ("de", "Abkürzungen > IBAN", "IBAN – Internationale Bankkontonummer."),
        ("de", "Preise > Preisverzeichnis", "Stand: 1. Januar 2026."),
        ("en", "Notes > Version", "Version 2.1 of the terms of 1 January 2026."),
        ("en", "Overview > Contents", "Fees, cards and transfers."),
        ("en", "Fees > Card fees", "Card fees."),
        (
            "de",
            "Kontakt > Anschrift",
            "Beispielbank AG, Hauptstraße 1, 60311 Frankfurt am Main.",
        ),
    ],
    ids=[
        "cross-reference en",
        "cross-reference de",
        "caption en",
        "caption de",
        "key en",
        "key de",
        "date line de",
        "version line en",
        "contents en",
        "label en",
        "address de",
    ],
)
def test_a_verbless_line_defining_nothing_is_still_skipped(
    language, path, text
) -> None:
    """Under a heading too: a reference, a caption, a key, a label, a list or an address."""
    under = passage(text, language=language, section_path=path)

    assert skipped(under) == "no finite verb", text


def test_a_passage_repeating_its_own_heading_trail_is_skipped() -> None:
    """A heading that carries a verb is still a heading."""
    heading = passage(
        "The device arrives in March.",
        section_path="Intro > The device arrives in March.",
    )
    assert skipped(heading) == "heading", skipped(heading)


def test_a_table_is_not_judged_on_its_sentences() -> None:
    """A table is read from its grid."""
    assert skipped(passage("| a | b |", block_type="table")) is None


@pytest.mark.parametrize("kwargs", [{}, {"block_type": "table"}])
def test_a_passage_with_nothing_numbered_is_skipped(kwargs) -> None:
    """Nothing can cite a passage that has no numbered units, table or not."""
    assert skipped(passage("| a | b |", sentences=[], **kwargs)) == "no sentences"


@pytest.mark.parametrize("block_type", ["document_index", "code"])
def test_a_navigation_passage_is_skipped(block_type: str) -> None:
    """A table of contents says where something is, not what it says."""
    listing = passage("Das Team managen dauert 225 Minuten.", block_type=block_type)

    assert skipped(listing) == f"{block_type}: navigation rather than content"


def test_a_navigation_passage_is_skipped_before_its_sentences_are_read() -> None:
    """It is refused on what kind of block it is, not on what it says."""
    prose = passage(
        "The device weighs 4 kg and runs for 12 hours.", block_type="document_index"
    )

    assert prose.claims, "this passage does assert something"
    assert skipped(prose) is not None


# ── Navigation the parser did not label ────────────────────────────────────
#
# Every text below is a real passage from a corpus, shortened. The parser
# labelled each of them `text`, so the block-type check above never saw
# them; between them they produced questions asking which pages a term
# appears on and how the document is licensed.


def test_an_index_the_parser_labelled_prose_is_skipped() -> None:
    """A term and the pages it appears on, over and over."""
    index = passage(
        "Überdeckung 22, 23, 46, 47, 48, 49, 50, 53 Überdeckung aller Übergänge 49 "
        "rundreiseüberdeckung, 35 schlüsselwort, 13 grenzwertanalyse, 30 "
        "grundursachenanalyse, 58, 76 abstrakter testfall, 13, 18 ad-hoc-review, 52 "
        "technisches review 42 test 16, 17 frühes testen 20, 21 fehlerzustand 19, 24",
        language="de",
    )

    assert skipped(index) == "no finite verb"


def test_a_bibliography_is_skipped() -> None:
    """Names, years and page ranges, which is not a claim about anything."""
    works = passage(
        "- BAKER, Paul; DAI, Zhen Ru; GRABOWSKI, Jens, 2008. Model-Driven Testing. "
        "Springer, pp. 12-48. - ALYAHYA, Sultan, 2020. Crowdsourced Software "
        "Testing: A Systematic Literature Review. In: Journal 61, pp. 1-22. "
        "- Kahler, T. (2008). The Process Therapy Model. Taibi, 1st ed., 340 pp.",
        language="en",
    )

    assert skipped(works) == "no finite verb"


def test_an_index_with_a_stray_verb_is_skipped_as_one() -> None:
    """One claim does not make five hundred characters of page numbers prose."""
    index = passage(
        "Das Register nennt die Seiten. "
        + "Überdeckung 22, 23, 46, 47, 48 Grenzwertanalyse 30, 31 Review 42, 52 " * 8,
        language="de",
    )

    assert index.claims == 1, index.claims
    assert len(index.text) > 500
    assert skipped(index) == (
        "an index, a bibliography or a contents page rather than prose"
    )


def test_a_copyright_notice_is_skipped() -> None:
    """Front matter asserts things, and they are about the document.

    It has to be caught by the glyph rather than by the verb check above:
    a real notice is a paragraph of prose that says who holds what, so it
    carries finite verbs and reads as content to everything else here.
    """
    notice = passage(
        "Dieser Lehrplan ist urheberrechtlich geschützt. Das Urheberrecht © 2019 "
        "gehört den Autoren der englischen Originalausgabe. Die Nutzung ist nur "
        "mit ausdrücklicher Zustimmung der Inhaber gestattet, und jede Ausgabe "
        "nennt die Organisation, die sie herausgegeben hat.",
        language="de",
    )

    assert skipped(notice) == "a copyright notice, which is about the document"


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="No rule skips contact details. Weighing the kinds of contact a "
    "passage gives against its claims also skipped a one-sentence rule naming "
    "two ways to complain, a hotline and an e-mail address, and a national "
    "telephone number has the shape its country's dialling convention gives "
    "it, so no one pattern finds it in every language. Remove this marker when "
    "a rule reads both kinds of passage right.",
)
@pytest.mark.parametrize(
    ("text", "language"),
    [
        (
            (
                "Impressum\n"
                "Beispielbank AG, Hauptstraße 1, 60311 Frankfurt am Main\n"
                "Telefon: 069 1234-0, Telefax: 069 1234-199\n"
                "E-Mail: info@beispielbank.example\n"
                "Die Beispielbank AG ist im Handelsregister des Amtsgerichts "
                "Frankfurt unter HRB 12345 eingetragen."
            ),
            "de",
        ),
        (
            (
                "Get in touch\n"
                "Customer service: 0800 123 4567 (free from UK landlines)\n"
                "Email: help@shop.example\n"
                "Our team is available seven days a week."
            ),
            "en",
        ),
        (
            (
                "London City branch, 1 Bank Street, +44 20 7946 0001\n"
                "Manchester branch, 2 King Street, +44 161 496 0002\n"
                "Edinburgh branch, 3 George Street, +44 131 496 0003\n"
                "All branches are open Monday to Friday from 9 am to 5 pm."
            ),
            "en",
        ),
    ],
    ids=["bank imprint", "shop contact page", "branch list"],
)
def test_a_contact_block_is_skipped(text: str, language: str) -> None:
    """Ways to reach the publisher are about the document, not its subject.

    Each carries a claim, so the verb check reads it, and a question asked
    of it asks for a telephone number.
    """
    assert skipped(passage(text, language=language)) is not None


def test_a_bullet_list_of_content_is_not_skipped() -> None:
    """The false positive the numeric half of the rule exists to prevent.

    A German bullet list is sparse in finite verbs because its points are
    infinitives - `Evaluieren von Arbeitsergebnissen` asserts nothing a
    parser can count - so claim density alone reads it as a list. It
    carries no numbers, and an index is nothing but numbers.
    """
    objectives = passage(
        "Typische Testziele sind: - Evaluieren von Arbeitsergebnissen wie "
        "Anforderungen, User-Storys und Code - Auslösen von Fehlerwirkungen und "
        "Auffinden von Fehlerzuständen - Sicherstellen der erforderlichen "
        "Überdeckung eines Testobjekts - Verringern des Risikos einer "
        "unzureichenden Softwarequalität - Zusammenarbeit mit Stakeholdern, um "
        "die Erfüllung der Akzeptanzkriterien zu überprüfen",
        language="de",
    )

    assert skipped(objectives) is None


def test_a_priced_bullet_list_is_not_an_index() -> None:
    """A price list carries a figure in every item, and each item is a claim.

    Sparse in finite verbs because its items are labels and prices, so its
    room is counted in items as well as in claims, as the cap counts it.
    """
    prices = passage(
        "Für Bestellungen gelten folgende Versandkosten:\n"
        "- Standardversand innerhalb Deutschlands: 4,95 EUR\n"
        "- Expressversand innerhalb Deutschlands: 9,95 EUR\n"
        "- Versand nach Österreich: 7,95 EUR\n"
        "- Versand in die Schweiz: 14,95 EUR\n"
        "- Versand in die übrigen EU-Länder: 12,95 EUR\n"
        "- Sperrgut innerhalb Deutschlands: 29,95 EUR\n"
        "- Sperrgut nach Österreich: 39,95 EUR\n"
        "- Abholung in einer Filiale: kostenlos\n"
        "- Rücksendung innerhalb von 30 Tagen: kostenlos\n"
        "- Geschenkverpackung je Artikel: 2,50 EUR\n"
        "- Nachnahmegebühr: 6,00 EUR\n"
        "- Inselzuschlag: 15,00 EUR",
        language="de",
    )

    assert prices.claims >= 1, "the lead-in asserts something"
    assert len(prices.text) > 500
    assert skipped(prices) is None


def test_prose_carrying_a_reference_is_not_skipped() -> None:
    """One citation in a sentence does not make the sentence a bibliography."""
    prose = passage(
        "KI kann mit einer breiten Palette von Techniken implementiert werden "
        "(siehe [B02] für weitere Informationen), und die Wahl der Technik "
        "bestimmt, wie das System getestet werden muss.",
        language="de",
    )

    assert skipped(prose) is None


def _grid(*texts: str) -> list[dict]:
    """One grid holding the given cell texts."""
    return [
        {
            "cells": [
                {"row": i, "col": 0, "line": None, "text": text}
                for i, text in enumerate(texts)
            ]
        }
    ]


def test_a_grid_of_identifiers_is_skipped() -> None:
    """A traceability matrix asserts nothing a reader would look up.

    Its cells are learning-objective codes and levels, and read as a table
    it gave a fact per cell - "TA-BO1 is traced to TA-3.4.2" - every one of
    them checkable, and about how the document is organised.

    The claim-density signals the other rules read are all zero for a table,
    which is why this one reads the cells instead.
    """
    matrix = passage(
        "| TA-BO1 | TA-3.4.2 |",
        block_type="table",
        table_cells=_grid("TA-BO1", "TA-3.4.2", "K2", "X", "1.7", "TM-2.2.1"),
    )

    assert skipped(matrix) == "a grid of identifiers rather than of statements"


def test_a_fee_table_of_figures_is_read() -> None:
    """A price is a value, not an identifier: a fee schedule is what it states."""
    fees = passage(
        "| Account | Monthly fee | Card fee |",
        block_type="table",
        table_cells=_grid(
            "Basic account", "0", "0.50", "Current account", "5", "12.50"
        ),
    )

    assert skipped(fees) is None


def test_a_table_whose_cells_say_something_is_still_read() -> None:
    """The threshold is set where no table carrying prose reaches it.

    A glossary is the case that matters: one column is a term, which looks
    like an identifier, and the other is its definition. Refusing it would
    lose the definitions, which are the best thing a glossary holds.
    """
    glossary = passage(
        "| Richtig Negativ | Eine Vorhersage ... |",
        block_type="table",
        table_cells=_grid(
            "Richtig Negativ (RN)",
            "Eine Vorhersage, bei der das Modell die negative Klasse korrekt "
            "vorhersagt.",
            "K2",
            "Anpassbarkeit",
            "Die Leichtigkeit, mit der ein System angepasst werden kann.",
        ),
    )

    assert skipped(glossary) is None


def test_a_table_with_no_cells_is_not_judged_on_them() -> None:
    """An empty grid is not a grid of identifiers."""
    empty = passage("| a | b |", block_type="table", table_cells=[])

    assert skipped(empty) is None
