"""A deterministic statement that is its one-claim sentence is the fact.

A grid reader may compose exactly the sentence it read. Evidence carrying one
claim already is the fact, so the copy is kept; evidence carrying two is
refused as copied. Languages no configuration names are refused at parse
(docs/bugs.md, C-252), so they never reach this check.
"""

from __future__ import annotations

import pytest
from drivers import Checker, passage

from database.qa_generator import Rejection

pytestmark = pytest.mark.nlp


@pytest.mark.parametrize(
    ("language", "text"),
    [
        ("de", "Die Kontoführung kostet 4 Euro im Monat. Die Karte ist kostenlos."),
        ("en", "The account costs 4 euros a month. The card is free of charge."),
    ],
)
def test_a_composed_copy_of_a_one_claim_sentence_is_kept(language, text) -> None:
    """The first sentence, verbatim, carries one claim and is accepted."""
    checker = Checker(passage(text, language=language))
    first = checker.passage.sentences[0]
    assert first.predicates == 1

    kept = checker.composed(first.text, 0)

    assert kept.validated, (kept.rejection_code, kept.validation_error)


@pytest.mark.parametrize(
    ("language", "text"),
    [
        ("de", "Die Kontoführung kostet 4 Euro und die Karte ist kostenlos."),
        ("en", "The account costs 4 euros and the card is free of charge."),
    ],
)
def test_a_composed_copy_of_a_two_claim_sentence_is_refused(language, text) -> None:
    """Two claims copied are a quotation, not a fact."""
    checker = Checker(passage(text, language=language))
    assert checker.passage.sentences[0].predicates == 2

    copied = checker.composed(checker.passage.sentences[0].text, 0)

    assert copied.rejection_code == Rejection.COPIED, copied.validation_error
