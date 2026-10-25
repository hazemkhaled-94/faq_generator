"""A paragraph lead-in heads a long list whose first item ends in a colon and
has nested sub-items cut by the chunker: the outer items after the sub-list
keep the paragraph's lead-in."""

from __future__ import annotations

import pytest
from docling_core.types.doc.document import DoclingDocument
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of

CASES = {
    "de": (
        "Die Bank berechnet folgende Entgelte:",
        "für Karten:",
        "die Karte {n} wird jährlich mit einem Entgelt von {n} EUR belastet",
        "für die Überweisung {n} in ein Land außerhalb des Euroraums fällt ein Entgelt an",
    ),
    "en": (
        "The bank charges the following fees:",
        "for cards:",
        "card {n} is charged a yearly fee of {n} EUR on the account",
        "for transfer {n} to a country outside the euro area a fee is charged",
    ),
}


def document(language: str) -> DoclingDocument:
    lead, item, sub, outer = CASES[language]
    doc = DoclingDocument(name="t")
    doc.add_heading(text="Entgelte", level=1)
    doc.add_text(label="text", text=lead)
    group = doc.add_list_group()
    parent = doc.add_list_item(text=item, parent=group)
    children = doc.add_list_group(parent=parent)
    for at in range(6):
        doc.add_list_item(text=sub.format(n=at + 1), parent=children, marker=f"{chr(97 + at)}.")
    for at in range(8):
        doc.add_list_item(text=outer.format(n=at + 1), parent=group)
    return doc


@pytest.mark.parametrize("language", sorted(CASES))
def test_outer_items_after_cut_sub_items_keep_the_paragraph_lead_in(
    language: str,
) -> None:
    lead, item, sub, outer = CASES[language]
    _, chunks = chunks_of(document(language), word_chunker(40), language)
    later = [c for c in chunks if outer.split("{n}")[0].strip() in c.text and lead not in c.text]
    missing = [c.text[:50] for c in later if lead not in (c.meta.headings or [])]
    assert not missing, missing
