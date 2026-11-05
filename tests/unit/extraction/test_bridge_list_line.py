"""A bridge citing a list line of a passage's last sentence loses that passage.

The bridge prompt numbers each passage's sentences as the atomic prompt does,
and the atomic check reads an index past the last sentence as one of its list
lines (C-129). `_resolve` drops such an index instead, so the passage the
bridge rests on goes, and the bridge is judged against the other passage
alone and refused.
"""

from __future__ import annotations

import pytest
from drivers import Checker, group

pytestmark = pytest.mark.nlp

#: (language, a passage whose one sentence holds a list, the other passage,
#: a bridge resting on the list's second line and the other passage)
CASES = [
    (
        "de",
        (
            "Für Überweisungen ins Ausland gelten diese Gebühren:\n"
            "- Überweisung in der EU: 0 Euro\n"
            "- Überweisung außerhalb der EU: 25 Euro"
        ),
        "Eine Auslandsüberweisung wird innerhalb von 4 Bankarbeitstagen ausgeführt.",
        "Eine Überweisung außerhalb der EU kostet 25 Euro und wird innerhalb von 4 Bankarbeitstagen ausgeführt.",
    ),
    (
        "en",
        (
            "These fees apply to transfers abroad:\n"
            "- Transfer within the EU: EUR 0\n"
            "- Transfer outside the EU: EUR 25"
        ),
        "A transfer abroad is carried out within 4 business days.",
        "A transfer outside the EU costs EUR 25 and is carried out within 4 business days.",
    ),
    (
        "fr",
        (
            "Ces frais s'appliquent aux virements à l'étranger :\n"
            "- Virement dans l'UE : 0 EUR\n"
            "- Virement hors de l'UE : 25 EUR"
        ),
        "Un virement à l'étranger est exécuté en 4 jours ouvrables.",
        "Un virement hors de l'UE coûte 25 EUR et est exécuté en 4 jours ouvrables.",
    ),
    (
        "el",
        (
            "Αυτά τα τέλη ισχύουν για μεταφορές στο εξωτερικό:\n"
            "- Μεταφορά εντός ΕΕ: 0 EUR\n"
            "- Μεταφορά εκτός ΕΕ: 25 EUR"
        ),
        "Μια μεταφορά στο εξωτερικό εκτελείται εντός 4 εργάσιμων ημερών.",
        "Μια μεταφορά εκτός ΕΕ κοστίζει 25 EUR και εκτελείται εντός 4 εργάσιμων ημερών.",
    ),
]


@pytest.mark.parametrize(("lang", "listed", "other", "statement"), CASES)
def test_a_bridge_citing_a_list_line_keeps_both_passages(
    lang, listed, other, statement
) -> None:
    """The line resolves as it does for an atomic fact, so the bridge rests on two passages."""
    from extraction.validation import _lines_of

    offered = group(listed, other, language=lang)
    last = offered[0].sentences[-1]
    (at,) = [i for i, one in enumerate(_lines_of(last)) if "25" in one.text]
    # German and English keep the list in one sentence, so the line is cited
    # past it (at >= 1). The default pipeline cuts the French and Greek lists
    # into sentences of their own (at == 0): there the citation names the
    # sentence itself, and the case pins that nothing changes for them.
    line = last.index + at
    fact = Checker(offered[0]).bridge(
        statement, offered, cites={0: (line,), 1: (0,)}, relation="limits"
    )
    assert {one.passage_id for one in fact.citations} == {11, 22}, (
        fact.rejection_code,
        fact.validation_error,
    )


@pytest.mark.parametrize(("lang", "listed", "other", "statement"), CASES[:2])
def test_the_control_citing_the_whole_sentence_validates(
    lang, listed, other, statement
) -> None:
    """Cited as sentence 0, the same bridge is validated."""
    offered = group(listed, other, language=lang)
    fact = Checker(offered[0]).bridge(
        statement, offered, cites={0: (0,), 1: (0,)}, relation="limits"
    )
    assert fact.validated, (fact.rejection_code, fact.validation_error)
