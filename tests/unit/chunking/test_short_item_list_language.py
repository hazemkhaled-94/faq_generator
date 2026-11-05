"""A list of short items in a language no pipeline is configured for is labelled none.

`outside` reads a passage line by line over every language, and a line under
the shortest length worth reading counts for neither side. A list whose every
item is short therefore read as inside, and `passage_language` fell back to
the detector of the configured languages, which can only answer German or
English, or to the document's language. The same lines joined are long
enough: French, Polish, Greek, Dutch and Swedish lists read surely as their
language at the all-language gate, and a German or English list of loanwords,
brands or codes does not.
"""

from __future__ import annotations

import pytest

from nlp.language import document_language, passage_language
from preprocessing.chunking.models import Chunk
from preprocessing.chunking.passages import PassageBuilder

pytestmark = pytest.mark.nlp

#: Four short items each: a bank's fee list, a shop's terms, an office's papers.
LISTS = {
    "fr": "- Frais de tenue de compte\n- Carte de débit gratuite\n- Virement SEPA en ligne\n- Retrait au guichet de la banque",
    "pl": "- Opłata za prowadzenie konta\n- Karta debetowa bez opłat\n- Przelew krajowy online\n- Wypłata z bankomatu",
    "el": "- Έξοδα τήρησης λογαριασμού\n- Δωρεάν χρεωστική κάρτα\n- Μεταφορά χρημάτων online\n- Ανάληψη από ATM",
    "nl": "- Kosten voor het aanhouden van de rekening\n- Gratis betaalpas\n- Overschrijving binnen Nederland\n- Geld opnemen aan het loket",
    "sv": "- Avgift för kontoföring\n- Gratis betalkort\n- Överföring inom Sverige\n- Uttag i bankens kassa",
}
#: The controls: the same kinds of lists in the configured languages keep theirs.
CONFIGURED = {
    "de": "- Kontoführungsgebühr pro Monat\n- Kostenlose Debitkarte\n- Online-Überweisung im Inland\n- Bargeld am Automaten",
    "en": "- Monthly account maintenance fee\n- Free debit card\n- Domestic online transfer\n- Cash withdrawal at the ATM",
}
#: Items that carry no language of their own: loanwords, brands and codes.
UNDECIDED = (
    "- Online Banking\n- Cashback\n- Newsletter\n- Update\n- Smartphone",
    "- IBAN DE89 3704 0044\n- BIC COBADEFF\n- Ref 2026-114\n- Konto 4711",
)


@pytest.mark.parametrize("guest", sorted(LISTS))
def test_the_whole_list_reads_surely_as_its_language(guest: str) -> None:
    """The premise: joined, each list is surely its language at the document gate."""
    found = document_language(LISTS[guest])
    assert found is not None and found[0] == guest


@pytest.mark.parametrize("host", ["de", "en"])
@pytest.mark.parametrize("guest", sorted(LISTS))
def test_a_list_of_short_items_in_an_unconfigured_language_reads_none(
    host: str, guest: str
) -> None:
    """As a paragraph in that language reads, so it is not extracted."""
    assert passage_language(LISTS[guest], host) is None


@pytest.mark.parametrize("guest", sorted(LISTS))
def test_the_chunker_does_not_extract_such_a_list(guest: str) -> None:
    """Through the passage builder: no language, and extraction may not read it."""
    (read,) = PassageBuilder._read([Chunk(1, LISTS[guest], 1, 1, None, "text")], "de")
    assert (read.language, read.extractable) == (None, False)


@pytest.mark.parametrize("language", sorted(CONFIGURED))
def test_a_configured_list_keeps_its_language(language: str) -> None:
    """Control: the same list in a configured language is read in it."""
    other = "en" if language == "de" else "de"
    assert passage_language(CONFIGURED[language], other) == language


@pytest.mark.parametrize("host", ["de", "en"])
@pytest.mark.parametrize("text", UNDECIDED)
def test_a_list_that_names_no_language_keeps_the_documents(
    host: str, text: str
) -> None:
    """Loanwords and codes are no evidence of another language."""
    assert passage_language(text, host) is not None
