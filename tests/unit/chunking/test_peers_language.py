"""A merged passage holds one language: merge_peers does not join paragraphs of two."""

from __future__ import annotations

import pytest
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of

PAIRS = [
    (
        "Kontoführung / Account maintenance",
        "Die Bank berechnet für die Führung des Girokontos ein monatliches Entgelt von 4,90 EUR. Das Entgelt entfällt bei einem Geldeingang von mindestens 1.000 EUR im Monat.",
        "The bank charges a monthly fee of 4.90 EUR for maintaining the current account. The fee is waived if at least 1,000 EUR are paid in during the month.",
    ),
    (
        "Versand / Shipping",
        "Wir liefern Bestellungen innerhalb von drei Werktagen an die angegebene Adresse. Der Versand ist ab 50 EUR kostenlos.",
        "We deliver orders to the address you give within three working days. Shipping is free of charge for orders above 50 EUR.",
    ),
    (
        "Rücksendung / Returns",
        "Sie können Waren innerhalb von 30 Tagen zurücksenden. Die Rücksendung ist kostenlos.",
        "You may return goods within 30 days of delivery. Returns are free of charge for all orders placed online.",
    ),
]


@pytest.mark.parametrize(("heading", "german", "english"), PAIRS)
def test_a_passage_never_holds_a_german_and_an_english_paragraph(
    heading, german, english
) -> None:
    """One language per passage, or one of them is read by the wrong pipeline."""
    document = DoclingDocument(name="t")
    document.add_heading(text=heading, level=1)
    document.add_text(label=DocItemLabel.TEXT, text=german)
    document.add_text(label=DocItemLabel.TEXT, text=english)

    _, chunks = chunks_of(document, word_chunker(200, merge_peers=True), None)

    assert not any(german in c.text and english in c.text for c in chunks), [
        c.text for c in chunks
    ]


def test_paragraphs_of_one_language_still_merge() -> None:
    """Only a change of language ends a passage; two English peers stay one."""
    document = DoclingDocument(name="t")
    document.add_heading(text="Returns", level=1)
    first = "You may return goods within 30 days of delivery of your order."
    second = "Returns are free of charge for all orders placed online with us."
    document.add_text(label=DocItemLabel.TEXT, text=first)
    document.add_text(label=DocItemLabel.TEXT, text=second)

    _, chunks = chunks_of(document, word_chunker(200, merge_peers=True), None)

    assert [c.text for c in chunks if first in c.text and second in c.text]


def test_the_two_halves_keep_their_own_text_and_heading() -> None:
    """The split loses no text and both halves sit under the same heading."""
    document = DoclingDocument(name="t")
    document.add_heading(text="Rücksendung / Returns", level=1)
    german, english = PAIRS[1][1], PAIRS[1][2]
    document.add_text(label=DocItemLabel.TEXT, text=german)
    document.add_text(label=DocItemLabel.TEXT, text=english)

    _, chunks = chunks_of(document, word_chunker(200, merge_peers=True), None)

    assert [c.text for c in chunks] == [german, english]
    assert all(c.meta.headings == ["Rücksendung / Returns"] for c in chunks)


LOANWORDS = [
    (
        "Aktionen",
        "Mit dem Online-Banking können Sie Ihre Überweisungen jederzeit selbst erledigen.",
        "Unser Black Friday Sale Deal Gutschein Code SPRING2026 Free Shipping ab 50 Euro",
        "Der Kunde erhält einen Refund, wenn das Produkt innerhalb von 14 Tagen zurückgesendet wird.",
    ),
    (
        "Online banking",
        "Our online banking lets you send a Überweisung or a SEPA Lastschrift at any time of day.",
        "Please contact our Kundenservice by phone or via the Servicecenter during opening hours.",
        "The bank charges a monthly fee of 4.90 EUR for maintaining the current account.",
    ),
    (
        "Shop",
        "Unser Customer Service Team ist per Live Chat und Hotline erreichbar.",
        "Das Cashback wird nach dem Checkout im Online-Shop automatisch gutgeschrieben.",
        "Die Rücksendung ist innerhalb von 30 Tagen kostenlos und ohne Angabe von Gründen möglich.",
    ),
    (
        "Shop",
        "Welcome to our shop: Gratis Versand, Rückgabe innerhalb von 30 Tagen, free returns worldwide.",
        "You may return goods within 30 days of delivery of your order.",
        "Returns are free of charge for all orders placed online with us.",
    ),
]


@pytest.mark.parametrize(("heading", "one", "two", "three"), LOANWORDS)
def test_loanwords_and_foreign_names_do_not_split_a_passage(
    heading, one, two, three
) -> None:
    """Three paragraphs of one language stay one passage however many loanwords."""
    document = DoclingDocument(name="t")
    document.add_heading(text=heading, level=1)
    for text in (one, two, three):
        document.add_text(label=DocItemLabel.TEXT, text=text)

    _, chunks = chunks_of(document, word_chunker(200, merge_peers=True), None)

    assert len(chunks) == 1, [c.text for c in chunks]
