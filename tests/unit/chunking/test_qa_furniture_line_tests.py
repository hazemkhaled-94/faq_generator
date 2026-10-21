"""The furniture filter's line tests at their edges, each pinned by a surviving mutant.

A targeted mutation run over fields, _page_number, _follows_lead_in, _repeats,
_broken, _continued and _dividers left these edges unasserted.
"""

from __future__ import annotations

from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
from docling_core.types.doc.labels import DocItemLabel
from factories import word_chunker

from preprocessing.chunking.passages import chunks_of


def on(page: int, top: float, left: float = 54) -> ProvenanceItem:
    """Provenance on one page, a line high."""
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=left, t=top, r=500, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
        ),
        charspan=(0, 1),
    )


def pages(count: int) -> DoclingDocument:
    """An empty document of `count` A4 pages, headed."""
    document = DoclingDocument(name="t")
    for page in range(1, count + 1):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    document.add_heading(text="Konditionen", level=1, prov=on(1, 50))
    return document


def texts(document: DoclingDocument, language: str = "de") -> list[str]:
    """Every chunk's text."""
    _, chunks = chunks_of(document, word_chunker(200), language)
    return [chunk.text for chunk in chunks]


def test_a_five_digit_number_in_the_margin_is_no_page_number() -> None:
    """A page number has at most four digits; an order number has more."""
    document = pages(1)
    document.add_text(label=DocItemLabel.TEXT, text="Ihre Bestellung.", prov=on(1, 100))
    document.add_text(label=DocItemLabel.TEXT, text="12345", prov=on(1, 820))

    assert "12345" in "\n".join(texts(document)).split()


def test_an_integer_above_the_foot_margin_is_no_page_number() -> None:
    """At 86 % of the page's height it is body, not the foot's margin."""
    document = pages(1)
    document.add_text(
        label=DocItemLabel.TEXT, text="Das Konto kostet.", prov=on(1, 100)
    )
    document.add_text(label=DocItemLabel.TEXT, text="7", prov=on(1, 725))

    assert "7" in "\n".join(texts(document)).split()


def test_a_margin_integer_off_the_running_numbers_stays() -> None:
    """Pages print their own number; `30` on page 2 is not page 2's."""
    document = pages(3)
    for page in (1, 2, 3):
        document.add_text(
            label=DocItemLabel.PAGE_FOOTER,
            text=str(page),
            prov=on(page, 830),
            content_layer=ContentLayer.FURNITURE,
        )
    document.add_text(
        label=DocItemLabel.TEXT, text="Rückgabe in Tagen.", prov=on(2, 100)
    )
    document.add_text(label=DocItemLabel.TEXT, text="30", prov=on(2, 800))

    assert "30" in "\n".join(texts(document)).split()


def test_a_value_after_a_full_width_colon_stays() -> None:
    """The full-width colon is a lead-in's too."""
    document = pages(1)
    document.add_text(label=DocItemLabel.TEXT, text="Frist in Tagen：", prov=on(1, 780))
    document.add_text(label=DocItemLabel.TEXT, text="14", prov=on(1, 800))

    assert "14" in "\n".join(texts(document)).split()


def test_a_line_sharing_only_the_foots_first_field_stays() -> None:
    """`Musterbank AG | Kontakt` is not the foot `Musterbank AG | Preisverzeichnis`."""
    document = pages(3)
    for page in (1, 2, 3):
        document.add_text(
            label=DocItemLabel.PAGE_FOOTER,
            text=f"Musterbank AG | Preisverzeichnis | {page}",
            prov=on(page, 830),
            content_layer=ContentLayer.FURNITURE,
        )
    document.add_text(
        label=DocItemLabel.TEXT, text="Musterbank AG | Kontakt", prov=on(2, 100)
    )

    assert any("Kontakt" in text for text in texts(document))


def test_a_sentence_is_not_joined_across_a_missing_page() -> None:
    """Page 1's foot and page 3's top are not one break."""
    document = pages(3)
    document.add_text(label=DocItemLabel.TEXT, text="Die Karte ist", prov=on(1, 780))
    document.add_text(label=DocItemLabel.TEXT, text="kostenlos.", prov=on(3, 100))

    assert "Die Karte ist kostenlos." not in texts(document)


def test_an_indented_block_below_in_one_column_is_not_a_column_break() -> None:
    """Further right but overlapping the block above: the document's own break."""
    document = pages(1)
    document.add_text(label=DocItemLabel.TEXT, text="Die Karte ist", prov=on(1, 100))
    document.add_text(
        label=DocItemLabel.TEXT, text="kostenlos.", prov=on(1, 140, left=80)
    )

    assert "Die Karte ist kostenlos." not in texts(document)


def test_a_block_ending_on_a_semicolon_is_not_joined() -> None:
    """A semicolon ends what it closes, as a full stop does."""
    document = pages(2)
    document.add_text(
        label=DocItemLabel.TEXT, text="Die Karte ist kostenlos;", prov=on(1, 780)
    )
    document.add_text(
        label=DocItemLabel.TEXT, text="danach kostet sie 2 EUR.", prov=on(2, 100)
    )

    assert "Die Karte ist kostenlos; danach kostet sie 2 EUR." not in texts(document)
