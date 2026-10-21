"""preprocessing-2: a U+00AD standing for a drawn hyphen must survive the mend."""

from __future__ import annotations

import pytest
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

from preprocessing.parsing.pipelines.pdf import _mend, _repaired


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


def _repaired_text(*lines: str) -> list[str]:
    """What `_repaired` leaves of a document of these paragraphs."""
    document = DoclingDocument(name="t")
    for line in lines:
        document.add_text(label=DocItemLabel.TEXT, text=line)
    return [item.text for item in _repaired(document).texts]


@pytest.mark.parametrize(
    ("raw", "drawn"),
    [
        ("Abholung im Markt (pick\xadup) ist kostenlos.", "pick-up"),
        ("Online check\xadin ab 24 Stunden vorher.", "check-in"),
        ("Add\xadon services cost 4.95 EUR.", "Add-on"),
        ("ein 3\xadfacher Schutz für Ihre Karte", "3-facher"),
    ],
)
def test_a_document_drawing_its_hyphen_as_u00ad_keeps_it_before_a_lower_case_letter(
    raw, drawn
) -> None:
    """Mid-line, with no line break at it, a U+00AD in a text layer is a drawn glyph."""
    assert drawn in _repaired_text(raw)[0]


def test_a_document_that_prints_a_hyphen_drops_one_before_a_lower_case_letter() -> None:
    """Its text layer draws U+002D itself, so a U+00AD in a word was never drawn."""
    found = _repaired_text(
        "Online\xadbanking und E-Mail", "Die Rückerstat\xadtung folgt."
    )

    assert found == ["Onlinebanking und E-Mail", "Die Rückerstattung folgt."]


def test_a_document_with_no_hyphen_of_its_own_draws_every_one_as_u00ad() -> None:
    """With no U+002D anywhere, the compound's hyphen is the U+00AD."""
    found = _repaired_text("Abholung (pick\xadup) und check\xadin ab 24 Stunden")

    assert found == ["Abholung (pick-up) und check-in ab 24 Stunden"]


def test_a_document_with_a_marked_u00ad_draws_every_one_as_u00ad() -> None:
    """A U+00AD before a digit shows the font draws its hyphen with that code."""
    found = _repaired_text("Mo\xadFr 8\xad18 Uhr, E-Mail und pick\xadup")

    assert found == ["Mo-Fr 8-18 Uhr, E-Mail und pick-up"]
