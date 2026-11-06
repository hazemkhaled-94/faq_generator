"""A citation of a sentence and a later list line takes the lines between.

A line of the last sentence keeps that sentence's index, so `_cited_text`
reads [sentence 0, line 2 of sentence 1] as the adjacent run 0..1 and takes
the covering range: the uncited line 1 joins the evidence. The swap guard then
reads that line's figure as cited, and a statement lifting it is validated.
Cited alone, the same line refuses it. French and Greek read no finite verb
(no pipeline names them) and refuse the statement either way; the span they
store still holds the uncited line.
"""

from __future__ import annotations

import pytest
from drivers import Checker, passage

from database.qa_generator import Rejection

pytestmark = pytest.mark.nlp

#: (language, passage: a lead-in sentence and a list in the last sentence,
#: a statement giving the transfer the card line's figure, the line index
#: past the last sentence that names the transfer line)
CASES = [
    (
        "de",
        (
            "Die Bank erhebt für jede Leistung eine Gebühr. Die Gebühren je Vorgang sind:\n"
            "- Kartenzahlung im Ausland: 5 Euro\n"
            "- Überweisung an eine andere Bank: 10 Euro\n"
            "- Barabhebung: 2 Euro"
        ),
        "Eine Überweisung an eine andere Bank kostet 5 Euro.",
    ),
    (
        "en",
        (
            "The bank charges a fee for each service. The fees per transaction are:\n"
            "- Card payment abroad: EUR 5\n"
            "- Transfer to another bank: EUR 10\n"
            "- Cash withdrawal: EUR 2"
        ),
        "A transfer to another bank costs EUR 5.",
    ),
    (
        "fr",
        (
            "La banque facture des frais pour chaque service. Les frais par opération sont :\n"
            "- Paiement par carte à l'étranger : 5 EUR\n"
            "- Virement vers une autre banque : 10 EUR\n"
            "- Retrait d'espèces : 2 EUR"
        ),
        "Un virement vers une autre banque coûte 5 EUR.",
    ),
    (
        "el",
        (
            "Η τράπεζα χρεώνει τέλος για κάθε υπηρεσία. Τα τέλη ανά συναλλαγή είναι:\n"
            "- Πληρωμή με κάρτα στο εξωτερικό: 5 EUR\n"
            "- Μεταφορά σε άλλη τράπεζα: 10 EUR\n"
            "- Ανάληψη μετρητών: 2 EUR"
        ),
        "Μια μεταφορά σε άλλη τράπεζα κοστίζει 5 EUR.",
    ),
]

#: The line no citation names, which holds the lifted figure.
UNCITED = {"de": "Kartenzahlung", "en": "EUR 5", "fr": "Paiement", "el": "Πληρωμή"}


def _transfer_line(read) -> int:
    """The citation index of the transfer line, counted on past the last sentence."""
    from extraction.validation import _lines_of

    last = len(read.sentences) - 1
    lines = _lines_of(read.sentences[-1])
    (at,) = [i for i, one in enumerate(lines) if "10" in one.text]
    assert at >= 1, [one.text for one in lines]
    return last + at


@pytest.mark.parametrize(("lang", "text", "statement"), CASES)
def test_the_line_cited_alone_refuses_the_lifted_figure(lang, text, statement) -> None:
    """The control: the swap guard reads the cited line's 10 against the 5."""
    read = passage(text, language=lang)
    fact = Checker(read).atomic(statement, (_transfer_line(read),))
    assert not fact.validated, fact.evidence_text
    if lang in ("de", "en"):
        assert fact.rejection_code == Rejection.UNSUPPORTED_ADDITION, (
            fact.validation_error
        )


@pytest.mark.parametrize(("lang", "text", "statement"), CASES)
def test_a_lead_in_cited_with_the_line_does_not_bring_the_uncited_lines(
    lang, text, statement
) -> None:
    """The evidence is the sentence before the list's sentence and the cited line, nothing between."""
    read = passage(text, language=lang)
    before = len(read.sentences) - 2
    fact = Checker(read).atomic(statement, (before, _transfer_line(read)))
    assert UNCITED[lang] not in fact.evidence_text, fact.evidence_text
    assert not fact.validated, fact.evidence_text
