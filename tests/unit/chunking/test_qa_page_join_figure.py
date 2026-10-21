"""A sentence a page break cuts before a figure is joined like one cut before a word."""

from __future__ import annotations

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
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


def joined(head: str, rest: str, lang: str) -> list[str]:
    """The chunk texts of a sentence cut at the foot of page 1."""
    document = DoclingDocument(name="t")
    for page in (1, 2):
        document.add_page(page_no=page, size=Size(width=595, height=842))
    document.add_heading(text="Konto", level=1, prov=on(1, 50))
    document.add_text(label=DocItemLabel.TEXT, text=head, prov=on(1, 780))
    document.add_text(label=DocItemLabel.TEXT, text=rest, prov=on(2, 100))
    _, chunks = chunks_of(document, word_chunker(200), lang)
    return [chunk.text for chunk in chunks]


def test_a_rest_opening_in_lower_case_is_joined() -> None:
    """The control."""
    assert joined(
        "Die Karte ist im ersten Jahr", "kostenlos und danach günstig.", "de"
    ) == ["Die Karte ist im ersten Jahr kostenlos und danach günstig."]


@pytest.mark.parametrize(
    ("lang", "head", "rest"),
    [
        ("de", "Die Kontoführung ist für die ersten", "12 Monate kostenlos."),
        ("en", "Orders are delivered within", "3 to 5 working days."),
        pytest.param(
            "en",
            "The card costs",
            "€25 a year after the first year.",
            marks=pytest.mark.xfail(
                strict=True,
                reason=(
                    "A block ending on a full verb is not joined to a figure: a "
                    "finite verb can close its clause (`Free delivery applies` "
                    "over `30-day returns.`), and the tags do not tell one "
                    "missing its object"
                ),
            ),
        ),
    ],
)
def test_a_rest_opening_with_a_figure_is_joined(lang, head, rest) -> None:
    """One sentence, so one paragraph, as the converter would have read it."""
    assert joined(head, rest, lang) == [f"{head} {rest}"]
