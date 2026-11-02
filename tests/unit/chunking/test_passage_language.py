"""A passage in a language no pipeline is configured for is labelled none.

The detector the passages are labelled with knows only the configured
languages, so it names a French or a Greek paragraph inside a German or
English document one of them, and the paragraph is segmented, lemmatised and
fed to the topic vocabulary by that pipeline.
"""

from __future__ import annotations

import pytest
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.models import Chunk
from preprocessing.chunking.passages import PassageBuilder, chunks_of
from preprocessing.chunking.service import revocabulary

HOST = {
    "de": "Der Händler muss Sie vor der Zahlung über den Gesamtpreis einschließlich aller Steuern und Zusatzgebühren informieren.",
    "en": "The seller must tell you the total price, including all taxes and extra charges, before you pay for your order.",
}
GUEST = {
    "fr": "Le vendeur doit vous informer du prix total, y compris toutes les taxes et les frais supplémentaires, avant que vous ne payiez.",
    "pl": "Sprzedawca musi poinformować Cię o całkowitej cenie, w tym o wszystkich podatkach i dodatkowych opłatach, zanim zapłacisz.",
    "el": "Ο πωλητής πρέπει να σας ενημερώσει για τη συνολική τιμή, συμπεριλαμβανομένων όλων των φόρων και των πρόσθετων χρεώσεων, πριν πληρώσετε.",
}
#: A price-list row: figures and units say nothing against the document's language.
ROW = "Adult 12.50 EUR | Child 6.00 EUR | Family 30.00 EUR"


def passage(ordinal: int, text: str) -> Chunk:
    """A passage of text, as the chunker cuts one."""
    return Chunk(ordinal, text, 1, 1, None, "text")


@pytest.mark.parametrize("host", sorted(HOST))
@pytest.mark.parametrize("guest", sorted(GUEST))
def test_a_guest_passage_reads_none_and_the_host_keeps_its_language(
    host: str, guest: str
) -> None:
    """The passage builder labels each passage; a guest one has no pipeline."""
    read = PassageBuilder._read(
        [passage(1, HOST[host]), passage(2, GUEST[guest]), passage(3, ROW)], host
    )

    assert read[0].language == host
    assert read[1].language is None
    assert read[2].language is not None
    assert [one.extractable for one in read] == [True, False, True]


@pytest.mark.parametrize("guest", sorted(GUEST))
def test_a_document_with_no_language_extracts_every_passage(guest: str) -> None:
    """Nothing is read under a language that was never named, so nothing is skipped."""
    read = PassageBuilder._read([passage(1, GUEST[guest])], None)

    assert read[0].language is None
    assert read[0].extractable


@pytest.mark.parametrize("host", sorted(HOST))
@pytest.mark.parametrize("guest", sorted(GUEST))
def test_a_re_read_labels_a_guest_passage_none(host: str, guest: str) -> None:
    """`make chunk-revocabulary` reads the same as chunking does."""

    class Catalog:
        """A stand-in PassageCatalog holding one guest passage."""

        def __init__(self) -> None:
            self.written: list = []

        def texts(self, within=None):
            return [(1, GUEST[guest], host, False), (2, HOST[host], host, False)]

        def languages(self, within=None):
            return {1: host, 2: host}

        def revocabulary(self, found):
            self.written += found
            return len(found)

    catalog = Catalog()
    revocabulary(catalog)  # type: ignore[arg-type]

    assert {one: language for one, language, _ in catalog.written} == {1: None, 2: host}


@pytest.mark.parametrize("host", sorted(HOST))
@pytest.mark.parametrize("guest", sorted(GUEST))
def test_a_guest_paragraph_is_cut_from_its_neighbours(host: str, guest: str) -> None:
    """Merged peers of two languages are split where the language changes."""
    document = DoclingDocument(name="terms")
    document.add_heading(text="Terms", level=1)
    document.add_text(label=DocItemLabel.TEXT, text=HOST[host])
    document.add_text(label=DocItemLabel.TEXT, text=GUEST[guest])

    _, chunks = chunks_of(document, word_chunker(200), host)

    assert not any(HOST[host] in c.text and GUEST[guest] in c.text for c in chunks)
