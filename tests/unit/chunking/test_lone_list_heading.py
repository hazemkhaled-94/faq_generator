"""A list item alone in its list that repeats a heading is that heading.

The converter reads the same numbered sub-heading as a heading in one column
and as a one-item list in the other; the item says nothing the heading has not.
"""

from __future__ import annotations

import pytest
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of

CASES = {
    "de": ("4.", "Disziplinarmassnahmen", "Die Strafe wird vom Gremium verhängt."),
    "en": ("4.", "Disciplinary action", "The penalty is imposed by the body."),
    "es": ("4.", "Medidas disciplinarias", "La sanción la impone el órgano."),
}


def boxed(language: str, alone: bool, text: str | None = None) -> DoclingDocument:
    """A heading, the same label as a list item, and a paragraph."""
    marker, label, rule = CASES[language]
    document = DoclingDocument(name="t")
    document.add_heading(text="Penalties", level=1)
    document.add_heading(text=f"{marker} {label}", level=2)
    document.add_text(label=DocItemLabel.TEXT, text=rule)
    group = document.add_list_group()
    document.add_list_item(text=text or label, marker=marker, parent=group)
    if not alone:
        document.add_list_item(text="A second entry of the list", parent=group)
    document.add_heading(text="5. Appeals", level=2)
    return document


def cut(document: DoclingDocument, language: str) -> str:
    """Every chunk's text, joined."""
    _, chunks = chunks_of(document, word_chunker(200), language)
    return "\n".join(chunk.text for chunk in chunks)


@pytest.mark.parametrize("language", sorted(CASES))
def test_a_lone_list_item_repeating_a_heading_leaves_the_body(language: str) -> None:
    """Marker and text together are the heading's own words."""
    rule = CASES[language][2]

    assert cut(boxed(language, alone=True), language) == rule


@pytest.mark.parametrize("language", sorted(CASES))
def test_the_same_item_in_a_longer_list_stays(language: str) -> None:
    """An entry among others is an entry."""
    _, label, _ = CASES[language]

    assert label in cut(boxed(language, alone=False), language)


@pytest.mark.parametrize("language", sorted(CASES))
def test_a_lone_list_item_with_body_text_stays(language: str) -> None:
    """It repeats no heading."""
    text = "The customer pays the fee when the card is issued"

    assert text in cut(boxed(language, alone=True, text=text), language)
