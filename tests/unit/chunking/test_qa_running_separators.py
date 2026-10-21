"""A running head or foot whose fields are parted by a dash, a dot or a space."""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of


def on(page: int, top: float) -> ProvenanceItem:
    """Provenance on one page, a line high."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=54, t=top, r=500, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def pages(count: int) -> DoclingDocument:
    """An empty document of `count` A4 pages."""
    document = DoclingDocument(name="t")
    for page in range(1, count + 1):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    return document


@pytest.mark.parametrize("separator", [" | ", "  "], ids=["bar", "spaces"])
def test_a_chapter_named_between_bars_or_spaces_leads_the_trail(separator) -> None:
    """The control: the separators the reader knows."""
    assert chapter_of_last_page(separator) == ["Kreditkarten"]


@pytest.mark.parametrize(
    "separator", [" – ", " · ", " • "], ids=["dash", "dot", "bullet"]
)
def test_a_chapter_named_between_dashes_or_dots_leads_the_trail(separator) -> None:
    """`Preisverzeichnis – Kreditkarten – Seite 4` names the chapter of page 4."""
    assert chapter_of_last_page(separator) == ["Kreditkarten"]


def chapter_of_last_page(separator: str) -> list[str] | None:
    """The trail of the last passage of a two-chapter price list."""
    document = pages(4)
    for page, chapter in [
        (1, "Girokonto"),
        (2, "Girokonto"),
        (3, "Kreditkarten"),
        (4, "Kreditkarten"),
    ]:
        document.add_text(
            label=DocItemLabel.PAGE_HEADER,
            text=separator.join(["Preisverzeichnis", chapter, f"Seite {page}"]),
            prov=on(page, 20),
            content_layer=ContentLayer.FURNITURE,
        )
    document.add_heading(text="1.1 Kontoführung", level=2, prov=on(1, 50))
    for page in (1, 2, 3, 4):
        document.add_text(
            label=DocItemLabel.TEXT,
            text=f"Der Preis beträgt {page} EUR im Monat.",
            prov=on(page, 100),
        )
    _, chunks = chunks_of(document, word_chunker(8), "de")
    return chunks[-1].meta.headings


@pytest.mark.parametrize(
    ("lang", "foot"),
    [
        ("de", "Musterbank AG | Seite {page} von 3"),
        ("en", "Example Shop Ltd | Page {page} of 3"),
    ],
)
def test_a_foot_between_bars_read_as_body_text_is_not_passage_text(lang, foot) -> None:
    """The control: the foot printed on pages 1 and 3, read as text on page 2."""
    assert foot.format(page=2) not in body_with_foot_read_as_text(foot, lang)


@pytest.mark.parametrize(
    ("lang", "foot"),
    [
        ("de", "Musterbank AG · Seite {page} von 3"),
        ("de", "Musterbank AG – Seite {page}"),
        ("en", "Example Shop Ltd – Page {page} of 3"),
        ("fr", "Banque Exemple • page {page} sur 3"),
    ],
)
def test_a_foot_between_dashes_read_as_body_text_is_not_passage_text(
    lang, foot
) -> None:
    """The same foot with another separator is still the foot."""
    assert foot.format(page=2) not in body_with_foot_read_as_text(foot, lang)


def body_with_foot_read_as_text(foot: str, lang: str) -> str:
    """Every chunk of a three-page document whose page 2 foot is read as body."""
    document = pages(3)
    for page in (1, 3):
        document.add_text(
            label=DocItemLabel.PAGE_FOOTER,
            text=foot.format(page=page),
            prov=on(page, 820),
            content_layer=ContentLayer.FURNITURE,
        )
    document.add_heading(text="Konditionen", level=1, prov=on(1, 50))
    for page in (1, 2, 3):
        document.add_text(
            label=DocItemLabel.TEXT,
            text=f"Das Konto kostet {page} EUR.",
            prov=on(page, 100),
        )
    document.add_text(
        label=DocItemLabel.TEXT, text=foot.format(page=2), prov=on(2, 820)
    )
    _, chunks = chunks_of(document, word_chunker(200), lang)
    return "\n".join(chunk.text for chunk in chunks)
