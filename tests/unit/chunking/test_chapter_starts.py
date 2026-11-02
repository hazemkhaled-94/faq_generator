"""Finding where each chapter opens costs time in step with the pages.

A running head that changes on most pages makes most pages a chapter start,
and each start looked for its heading through every block after it. A long
regulation or terms document then chunked in time that grew with the square
of its pages.
"""

from __future__ import annotations

import time

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.reference import ProvenanceItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

from preprocessing.chunking.furniture import Furniture, _chapter_starts

#: The label of chapter `n` and the heading that names it, by language.
HEADINGS = {
    "de": (
        "Kapitel {n} Allgemeine Bestimmungen",
        "Kapitel {n} Allgemeine Bestimmungen",
    ),
    "en": ("Chapter {n} General provisions", "Chapter {n} General provisions"),
    "fr": (
        "Chapitre {n} Dispositions générales",
        "Chapitre {n} Dispositions générales",
    ),
    "el": ("Κεφάλαιο {n} Γενικές διατάξεις", "Κεφάλαιο {n} Γενικές διατάξεις"),
}


def on(page: int, top: float) -> ProvenanceItem:
    """Provenance on one page, a line high."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=54, t=top, r=500, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def pages(count: int, heading: str | None = None) -> tuple[DoclingDocument, Furniture]:
    """A document of `count` pages, each its own chapter by its running head.

    With `heading`, each page holds the heading of its chapter after its body.
    """
    document = DoclingDocument(name="regulations")
    for page in range(1, count + 1):
        document.add_page(page_no=page, size=Size(width=595, height=842))
        for line in range(3):
            document.add_text(
                label=DocItemLabel.TEXT,
                text=f"Body {page}.{line}",
                prov=on(page, 100 + 30 * line),
            )
        if heading:
            document.add_heading(
                text=heading.format(n=page), level=1, prov=on(page, 400)
            )
    labels = tuple(
        (heading.format(n=page),) if heading else (f"Chapter {page}",)
        for page in range(1, count + 1)
    )
    return document, Furniture(starts=tuple(range(1, count + 1)), labels=labels)


def seconds(count: int) -> float:
    """The best of three runs of the search over `count` one-page chapters."""
    document, furniture = pages(count)
    best = float("inf")
    for _ in range(3):
        started = time.perf_counter()
        _chapter_starts(document, furniture, set())
        best = min(best, time.perf_counter() - started)
    return best


def test_the_search_grows_with_the_pages_and_not_their_square() -> None:
    """Four times the pages, well under sixteen times the time.

    A linear search takes about four times as long, a quadratic one about
    sixteen; the bound sits between them.
    """
    assert seconds(4000) < 9 * seconds(1000)


@pytest.mark.parametrize("language", sorted(HEADINGS))
def test_a_chapter_opens_on_the_heading_that_names_it(language: str) -> None:
    """The opening is the heading's block where the page holds one, else the first."""
    template = HEADINGS[language][0]
    document, furniture = pages(40, template)

    found = _chapter_starts(document, furniture, set())

    headings = [
        text.self_ref
        for text in document.texts
        if text.label == DocItemLabel.SECTION_HEADER
    ]
    assert [reference for reference, _ in found] == headings
    assert [label for _, label in found] == [
        (template.format(n=page),) for page in range(1, 41)
    ]


def test_a_chapter_with_no_heading_opens_on_its_first_block() -> None:
    """A page whose head names a chapter and holds no heading opens on its first block."""
    document, furniture = pages(40)

    found = _chapter_starts(document, furniture, set())

    firsts = [text.self_ref for text in document.texts if text.text.endswith(".0")]
    assert [reference for reference, _ in found] == firsts
