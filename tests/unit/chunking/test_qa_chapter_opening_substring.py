"""A sub-heading whose words are part of the chapter's label is not its opening."""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of

INTRO = "This chapter lists what the bank charges for its services."


def on(page: int, top: float) -> ProvenanceItem:
    """Provenance on one page, a line high."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=54, t=top, r=500, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def trail_of_intro(heading: str, chapters: tuple[str, str], lang: str) -> list[str]:
    """The trail of the paragraph opening the second chapter's first page."""
    document = DoclingDocument(name="t")
    for page in range(1, 5):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    for page, chapter in [
        (1, chapters[0]),
        (2, chapters[0]),
        (3, chapters[1]),
        (4, chapters[1]),
    ]:
        document.add_text(
            label=DocItemLabel.PAGE_HEADER,
            text=f"Musterbank | {chapter}",
            prov=on(page, 20),
            content_layer=ContentLayer.FURNITURE,
        )
    document.add_heading(text="Opening an account", level=1, prov=on(1, 50))
    document.add_text(
        label=DocItemLabel.TEXT, text="You can open an account online.", prov=on(1, 100)
    )
    document.add_text(
        label=DocItemLabel.TEXT, text="Statements are sent monthly.", prov=on(2, 100)
    )
    document.add_text(label=DocItemLabel.TEXT, text=INTRO, prov=on(3, 100))
    document.add_heading(text=heading, level=2, prov=on(3, 300))
    document.add_text(
        label=DocItemLabel.TEXT,
        text="The account costs 5 EUR a month.",
        prov=on(3, 320),
    )
    _, chunks = chunks_of(document, word_chunker(40), lang)
    (holding,) = [chunk for chunk in chunks if INTRO in chunk.text]
    return holding.meta.headings


def test_a_sub_heading_unlike_the_label_leaves_the_text_above_in_its_chapter() -> None:
    """The control: 'Card charges' is not in 'Fees and charges'."""
    assert trail_of_intro("Card charges", ("Accounts", "Fees and charges"), "en")[
        0
    ] == ("Fees and charges")


@pytest.mark.parametrize(
    ("heading", "chapters", "lang"),
    [
        ("Fees", ("Accounts", "Fees and charges"), "en"),
        ("Karten", ("Girokonto", "Kreditkarten"), "de"),
        ("Konto", ("Karten", "Girokonto"), "de"),
        ("Kreditkarten", ("Girokonto", "Karten"), "de"),
        ("Expressversand", ("Bestellung", "Versand"), "de"),
        ("Late fees", ("Accounts", "Fees"), "en"),
        ("Fees", ("Accounts", "Charges and fees"), "en"),
    ],
)
def test_a_sub_heading_inside_the_label_leaves_the_text_above_in_its_chapter(
    heading, chapters, lang
) -> None:
    """The page opens the chapter at its top; a later sub-heading does not."""
    assert trail_of_intro(heading, chapters, lang)[0] == chapters[1]


@pytest.mark.parametrize(
    ("heading", "chapters", "lang"),
    [
        ("Kapitel 3: Gebühren", ("Konten", "Gebühren"), "de"),
        ("3 Fees", ("Accounts", "Fees"), "en"),
        ("B Business", ("Kapitel A: Personal", "Kapitel B: Business"), "en"),
        ("a) Allgemeines", ("Konten", "Allgemeines"), "de"),
        ("b. Allgemeines", ("Konten", "Allgemeines"), "de"),
        ("ii. Allgemeines", ("Konten", "Allgemeines"), "de"),
        ("A) General terms", ("Accounts", "General terms"), "en"),
        ("IV. General terms", ("Accounts", "General terms"), "en"),
    ],
)
def test_the_chapters_own_heading_numbered_on_one_side_only_opens_it(
    heading, chapters, lang
) -> None:
    """A number the head or the heading adds is no new section: the text above stays."""
    assert trail_of_intro(heading, chapters, lang)[0] == chapters[0]


def test_a_title_holding_the_chapters_numeral_does_not_open_it() -> None:
    """`TITLE I – SUBSTANTIVE LAW` above `I – General provisions` is not chapter I's."""
    document = DoclingDocument(name="t")
    for page in range(1, 5):
        document.add_page(page_no=page, size=Size(width=595, height=842))
        document.add_text(
            label=DocItemLabel.PAGE_HEADER,
            text="Definitions" if page < 3 else "I – General provisions",
            prov=on(page, 20),
            content_layer=ContentLayer.FURNITURE,
        )
    document.add_heading(text="Definitions", level=1, prov=on(1, 50))
    for page in (1, 2):
        document.add_text(
            label=DocItemLabel.TEXT, text=f"Term {page} is defined.", prov=on(page, 100)
        )
    document.add_text(label=DocItemLabel.TEXT, text=INTRO, prov=on(3, 60))
    document.add_heading(text="TITLE I – SUBSTANTIVE LAW", level=1, prov=on(3, 200))
    document.add_heading(text="I – General provisions", level=2, prov=on(3, 300))
    document.add_heading(text="Article 6", level=3, prov=on(3, 320))
    document.add_text(
        label=DocItemLabel.TEXT, text="These rules apply to all.", prov=on(3, 340)
    )
    _, chunks = chunks_of(document, word_chunker(40), "en")
    (article,) = [chunk for chunk in chunks if "apply to all" in chunk.text]
    assert article.meta.headings == ["I", "General provisions", "Article 6"]
