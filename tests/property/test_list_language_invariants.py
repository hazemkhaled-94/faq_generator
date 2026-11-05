"""A list is labelled by the language of its items, over five languages."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nlp.language import passage_language

pytestmark = pytest.mark.nlp

ITEMS = {
    "de": [
        "Kontoführungsgebühr pro Monat",
        "Kostenlose Debitkarte",
        "Überweisung im Inland",
        "Bargeld am Automaten",
        "Antrag beim Bürgeramt",
        "Rückgabe innerhalb von 14 Tagen",
    ],
    "en": [
        "Monthly account fee",
        "Free debit card",
        "Domestic transfer online",
        "Cash at the ATM",
        "Application at the town hall",
        "Returns within 14 days",
    ],
    "fr": [
        "Frais de tenue de compte",
        "Carte de débit gratuite",
        "Virement SEPA en ligne",
        "Retrait au guichet",
        "Demande à la mairie",
        "Retour sous quatorze jours",
    ],
    "pl": [
        "Opłata za prowadzenie konta",
        "Karta debetowa bez opłat",
        "Przelew krajowy online",
        "Wypłata z bankomatu",
        "Wniosek w urzędzie gminy",
        "Zwrot w ciągu czternastu dni",
    ],
    "el": [
        "Έξοδα τήρησης λογαριασμού",
        "Δωρεάν χρεωστική κάρτα",
        "Μεταφορά χρημάτων",
        "Ανάληψη από ταμείο",
        "Αίτηση στο δημαρχείο",
        "Επιστροφή σε δεκατέσσερις ημέρες",
    ],
}


@settings(deadline=None)
@given(
    language=st.sampled_from(sorted(ITEMS)),
    host=st.sampled_from(["de", "en"]),
    data=st.data(),
)
def test_a_list_is_labelled_by_its_items_language(language, host, data) -> None:
    """A configured language names its list; any other leaves it with none."""
    items = data.draw(
        st.lists(st.sampled_from(ITEMS[language]), min_size=3, max_size=6, unique=True)
    )
    text = "\n".join(f"- {one}" for one in items)
    expected = language if language in ("de", "en") else None
    assert passage_language(text, host) == expected
