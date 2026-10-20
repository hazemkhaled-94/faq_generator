"""preprocessing-2: a U+00AD standing for a drawn hyphen must survive the mend."""

from __future__ import annotations

import pytest

from preprocessing.parsing.pipelines.pdf import _mend


@pytest.mark.parametrize(
    ("raw", "kept"),
    [
        ("Die Lieferzeit beträgt 3\xad5 Werktage.", "3-5 Werktage"),
        ("Hotline Mo\xadFr von 8\xad18 Uhr", "Mo-Fr von 8-18 Uhr"),
        ("per Kredit\xad oder Debitkarte", "Kredit- oder Debitkarte"),
        ("Delivery takes 3\xad5 business days.", "3-5 business days"),
        (
            "Zinssatz 1\xad2 % p. a., Mo\xadFr 9\xad17 Uhr",
            "1-2 % p. a., Mo-Fr 9-17 Uhr",
        ),
        ("Preis\xad und Leistungsverzeichnis", "Preis- und Leistungsverzeichnis"),
        ("Zahlung per Karte\xad oder Überweisung", "Karte- oder Überweisung"),
        ("Open Mon\xadFri 8\xad18, card\xad or cash", "Mon-Fri 8-18, card- or cash"),
        ("Free returns within 14\xad30 days", "14-30 days"),
    ],
)
def test_a_drawn_hyphen_is_not_deleted_as_a_discretionary_one(raw, kept) -> None:
    """The font maps its visible hyphen to U+00AD; ranges and compounds keep it."""
    assert kept in _mend(raw)


@pytest.mark.parametrize(
    ("raw", "kept"),
    [
        ("Kunden\xad anspruch", "Kundenanspruch"),
        ("Rückerstat\xadtung", "Rückerstattung"),
        ("Dispo\xadkredit und Karte", "Dispokredit und Karte"),
        ("Con\xad firmation of the or\xadder", "Confirmation of the order"),
    ],
)
def test_a_real_soft_hyphen_still_joins_a_broken_word(raw, kept) -> None:
    """Invisible unless the line breaks there: the word is whole again."""
    assert kept in _mend(raw)


@pytest.mark.parametrize(
    ("raw", "kept"),
    [
        ("用户\xad账户", "用户账户"),
        ("كلمة\xadكلمة", "كلمةكلمة"),
        ("Kredit-\xad oder Debitkarte", "Kredit- oder Debitkarte"),
        ("Online\xadBanking", "Online-Banking"),
        ("E\xadMail", "E-Mail"),
        ("Konto\xadführung", "Kontoführung"),
        ("Order\xadtracking", "Ordertracking"),
    ],
)
def test_a_soft_hyphen_between_caseless_letters_or_after_a_hyphen_is_dropped(
    raw, kept
) -> None:
    """Only a space, a digit or a capital after it makes it a drawn hyphen."""
    assert kept in _mend(raw)
