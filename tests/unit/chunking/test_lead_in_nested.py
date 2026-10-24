"""A list item ending in a colon introduces the sub-items nested under it.

When the chunker cuts such a list inside the sub-items, the pieces after the
first read as rules of their own unless the item that introduces them goes
with them, wherever the cut falls, a page break included.
"""

from __future__ import annotations

import pytest
from docling_core.types.doc.document import DoclingDocument
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of

CASES = {
    "de": (
        "Das Konto kann in folgenden Fällen gekündigt werden:",
        "die Karte {n} wurde im Ausland gestohlen und der Diebstahl ist angezeigt",
        "Eine andere Regel gilt für Firmenkonten.",
    ),
    "en": (
        "The account may be closed in the following cases:",
        "the card {n} was stolen abroad and the theft has been reported",
        "A different rule applies to business accounts.",
    ),
    "es": (
        "La cuenta puede cancelarse en los casos siguientes:",
        "la tarjeta {n} fue robada en el extranjero y el robo fue denunciado",
        "Otra norma se aplica a las cuentas de empresa.",
    ),
}


def nested_list(language: str, count: int = 9) -> DoclingDocument:
    """A heading, a list item ending in a colon, its sub-items, then a sibling."""
    lead, case, sibling = CASES[language]
    document = DoclingDocument(name="t")
    document.add_heading(text="Konten", level=1)
    group = document.add_list_group()
    parent = document.add_list_item(text=lead, parent=group)
    children = document.add_list_group(parent=parent)
    for at in range(count):
        document.add_list_item(
            text=case.format(n=at + 1), parent=children, marker=f"{chr(97 + at)}."
        )
    document.add_list_item(text=sibling, parent=group)
    return document


@pytest.mark.parametrize("language", sorted(CASES))
def test_every_piece_of_a_cut_sub_list_carries_the_item_that_introduces_it(
    language: str,
) -> None:
    """In its text, or in its trail: a condition without its rule is a wrong fact."""
    lead, case, _ = CASES[language]
    _, chunks = chunks_of(nested_list(language), word_chunker(40), language)

    pieces = [c for c in chunks if case.split("{n}")[0].strip() in c.text]
    assert len(pieces) > 1, [c.text for c in chunks]
    for piece in pieces:
        assert lead in piece.text or lead in (piece.meta.headings or []), (
            piece.meta.headings,
            piece.text[:80],
        )


@pytest.mark.parametrize("count", range(6, 14))
@pytest.mark.parametrize("language", sorted(CASES))
def test_a_sibling_opening_a_piece_after_the_sub_list_does_not_carry_the_lead_in(
    language: str, count: int
) -> None:
    """The next item of the outer list is not one of the conditions."""
    lead, _, sibling = CASES[language]
    _, chunks = chunks_of(nested_list(language, count), word_chunker(40), language)

    for chunk in chunks:
        if chunk.text.lstrip("- ").startswith(sibling):
            assert lead not in (chunk.meta.headings or []), chunk.meta.headings
