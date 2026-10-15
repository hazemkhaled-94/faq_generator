"""Removing the words a PDF strikes through.

A deletion drawn as a line through a word leaves the word in the text layer:
no annotation, no font flag and no colour marks it, so the converter reads
"a maximum of six eight" where the page shows only "eight". Each test draws
a page with pymupdf and builds the document the converter would hand over
for it, with the provenance boxes it would give.
"""

from __future__ import annotations

import logging
from typing import Any

import pymupdf
import pytest
from docling.datamodel.base_models import ConfidenceReport, ConversionStatus
from docling.datamodel.document import ConversionResult
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import (
    DoclingDocument,
    ProvenanceItem,
    TableCell,
    TableData,
)
from docling_core.types.doc.labels import DocItemLabel
from hypothesis import given, settings
from hypothesis import strategies as st

from preprocessing.parsing.models import SourceDocument
from preprocessing.parsing.pipelines.pdf import PdfPipeline, _unstruck

WIDTH, HEIGHT = 839.0, 595.0
FONT = 9.0
LEFT = 58.0
BASELINE = 380.0
INK = (0.27, 0.44, 0.51)
INSERTED = (0.88, 0.90, 0.35)

PRINTED = "Each charger supports a maximum of six eight devices."
CURRENT = "Each charger supports a maximum of eight devices."


def printed(*lines: tuple[float, float, str]) -> tuple[Any, Any]:
    """A one-page PDF printing each (x, baseline, text)."""
    pdf = pymupdf.open()
    page = pdf.new_page(width=WIDTH, height=HEIGHT)
    for x, baseline, text in lines:
        page.insert_text((x, baseline), text, fontsize=FONT, color=INK)
    return pdf, page


def word(page, text: str, baseline: float = BASELINE):
    """Where one printed word landed on the line at `baseline`."""
    return next(
        pymupdf.Rect(found[:4])
        for found in page.get_text("words")
        if found[4] == text and found[1] < baseline < found[3]
    )


def strike(page, text: str, baseline: float = BASELINE, *, filled: bool = False):
    """Draws a deletion: a line through the word, a third of the face up."""
    box, height = word(page, text, baseline), baseline - 0.33 * FONT
    if filled:
        page.draw_rect(
            pymupdf.Rect(box.x0, height - 0.4, box.x1, height + 0.4),
            color=None,
            fill=INK,
        )
    else:
        page.draw_line((box.x0, height), (box.x1, height), color=INK, width=1)


def underline(page, text: str, baseline: float = BASELINE) -> None:
    """Draws an insertion mark: a line just below the baseline."""
    box = word(page, text, baseline)
    page.draw_line(
        (box.x0, baseline + 1.3), (box.x1, baseline + 1.3), color=INSERTED, width=1
    )


def rule(page, height: float) -> None:
    """Draws a table rule across the whole page."""
    page.draw_line((40, height), (WIDTH - 40, height), color=INK, width=0.5)


def box(page, text: str, baseline: float = BASELINE) -> tuple[float, ...]:
    """The box a converter gives the printed `text`, with a top-left origin."""
    found = next(r for r in page.search_for(text) if r.y0 < baseline < r.y1)
    return found.x0, found.y0, found.x1, found.y1


def provenance(
    edges: tuple[float, ...], origin: CoordOrigin = CoordOrigin.TOPLEFT
) -> ProvenanceItem:
    """Provenance on page 1 for a top-left box, in the origin asked for."""
    left, top, right, bottom = edges
    placed = BoundingBox(
        l=left, t=top, r=right, b=bottom, coord_origin=CoordOrigin.TOPLEFT
    )
    if origin is CoordOrigin.BOTTOMLEFT:
        placed = placed.to_bottom_left_origin(page_height=HEIGHT)
    return ProvenanceItem(page_no=1, bbox=placed, charspan=(0, 0))


def document() -> DoclingDocument:
    """An empty converted document with page 1 the size drawn."""
    converted = DoclingDocument(name="t")
    converted.add_page(page_no=1, size=Size(width=WIDTH, height=HEIGHT))
    return converted


def paragraph(page, text: str = PRINTED, **origin: Any) -> DoclingDocument:
    """The converter's reading of a page holding one paragraph."""
    converted = document()
    converted.add_text(
        label=DocItemLabel.TEXT, text=text, prov=provenance(box(page, text), **origin)
    )
    return converted


def unstruck(pdf, converted: DoclingDocument) -> DoclingDocument:
    """Runs the pass over the drawn page."""
    return _unstruck(converted, pdf.tobytes())


class _Converted:
    """Stands in for Docling, returning a document built beforehand."""

    def __init__(self, converted: DoclingDocument) -> None:
        """Initialises the stand-in with what it will return."""
        self._converted = converted

    def convert(self, source: Any) -> ConversionResult:
        """What Docling returns for the page: every word, no strike."""
        return ConversionResult.model_construct(
            status=ConversionStatus.SUCCESS,
            errors=[],
            document=self._converted,
            confidence=ConfidenceReport.model_validate(
                {"mean_score": 0.9, "low_score": 0.8}
            ),
        )


def test_a_struck_word_does_not_survive_conversion() -> None:
    """The converted text reads the current wording, not deleted and new."""
    pdf, page = printed((LEFT, BASELINE, PRINTED))
    strike(page, "six")
    underline(page, "eight")
    pipeline = PdfPipeline(
        table_mode="fast",
        heading_hierarchy=False,
        document_timeout_seconds=1.0,
        artifacts_path=None,
    )
    pipeline._built = _Converted(paragraph(page))

    converted = pipeline.convert(
        SourceDocument(sha256="a" * 64, data=pdf.tobytes(), scanned=False)
    )

    assert converted.document.texts[0].text == CURRENT


def test_a_struck_word_leaves_the_original_spelling_too() -> None:
    """`orig` is what a re-serialisation reads, so it loses the word as well."""
    pdf, page = printed((LEFT, BASELINE, PRINTED))
    strike(page, "six")

    (item,) = unstruck(pdf, paragraph(page)).texts

    assert (item.text, item.orig) == (CURRENT, CURRENT)


def test_a_thin_filled_bar_strikes_as_a_line_does() -> None:
    """Some writers draw the stroke as a filled rectangle rather than a line."""
    pdf, page = printed((LEFT, BASELINE, PRINTED))
    strike(page, "six", filled=True)

    assert unstruck(pdf, paragraph(page)).texts[0].text == CURRENT


def test_a_box_with_a_bottom_left_origin_is_matched_where_it_is() -> None:
    """The converter's text boxes count up from the page foot; pymupdf's down."""
    pdf, page = printed((LEFT, BASELINE, PRINTED))
    strike(page, "six")

    converted = paragraph(page, origin=CoordOrigin.BOTTOMLEFT)

    assert unstruck(pdf, converted).texts[0].text == CURRENT


def test_every_word_a_stroke_runs_through_goes() -> None:
    """One line through a run of words deletes the whole run."""
    text = "Refunds are paid within thirty days of the request."
    pdf, page = printed((LEFT, BASELINE, text))
    start, end = word(page, "within"), word(page, "days")
    height = BASELINE - 0.33 * FONT
    page.draw_line((start.x0, height), (end.x1, height), color=INK, width=1)

    assert (
        unstruck(pdf, paragraph(page, text)).texts[0].text
        == "Refunds are paid of the request."
    )


def strokes(page, *struck: tuple[str, float], filled: bool = False) -> None:
    """Draws one deletion per (word, baseline), all of them as one path."""
    path = page.new_shape()
    for text, baseline in struck:
        box, height = word(page, text, baseline), baseline - 0.33 * FONT
        if filled:
            path.draw_rect(pymupdf.Rect(box.x0, height - 0.4, box.x1, height + 0.4))
        else:
            path.draw_line((box.x0, height), (box.x1, height))
    if filled:
        path.finish(color=None, fill=INK)
    else:
        path.finish(color=INK, width=1)
    path.commit()


@pytest.mark.parametrize("filled", [False, True])
def test_one_path_through_two_words_keeps_the_word_between(filled: bool) -> None:
    """Each line of a path is a stroke, not the box around all of them."""
    text = "Each charger supports six seven eight devices."
    pdf, page = printed((LEFT, BASELINE, text))
    strokes(page, ("six", BASELINE), ("eight", BASELINE), filled=filled)

    assert (
        unstruck(pdf, paragraph(page, text)).texts[0].text
        == "Each charger supports seven devices."
    )


def test_one_path_through_two_lines_strikes_a_word_on_each() -> None:
    """The box around both lines is a line's height tall and strikes nothing."""
    first, second = "The fee is six euros.", "The cap is nine euros."
    pdf, page = printed((LEFT, BASELINE, first), (LEFT, BASELINE + 14, second))
    strokes(page, ("six", BASELINE), ("nine", BASELINE + 14))
    converted = document()
    for text, line in ((first, BASELINE), (second, BASELINE + 14)):
        converted.add_text(
            label=DocItemLabel.TEXT, text=text, prov=provenance(box(page, text, line))
        )

    texts = [item.text for item in unstruck(pdf, converted).texts]

    assert texts == ["The fee is euros.", "The cap is euros."]


def test_the_edge_of_an_outlined_shape_strikes_nothing() -> None:
    """A frame's top can run through the x-height of the line it frames."""
    text = "Transfers settle within two business days."
    pdf, page = printed((LEFT, BASELINE, text))
    height = BASELINE - 0.33 * FONT
    frame = page.new_shape()
    frame.draw_polyline(
        [
            (40, BASELINE + 6),
            (40, height),
            (WIDTH - 40, height),
            (WIDTH - 40, BASELINE + 6),
        ]
    )
    frame.finish(color=INK, width=1)
    frame.commit()

    assert unstruck(pdf, paragraph(page, text)).texts[0].text == text


def test_a_wholly_struck_item_leaves_the_body() -> None:
    """A struck bullet is not an empty bullet, and a struck heading no heading."""
    heading, kept, gone = "Old fees", "Card fees apply.", "Cash fees apply."
    pdf, page = printed(
        (LEFT, BASELINE, heading),
        (LEFT, BASELINE + 20, kept),
        (LEFT, BASELINE + 40, gone),
    )
    height = BASELINE - 0.33 * FONT
    for line, text in ((BASELINE, heading), (BASELINE + 40, gone)):
        start, end = (
            word(page, text.split()[0], line),
            word(page, text.split()[-1], line),
        )
        line_height = line - BASELINE + height
        page.draw_line((start.x0, line_height), (end.x1, line_height), color=INK)
    converted = document()
    converted.add_heading(text=heading, prov=provenance(box(page, heading)))
    group = converted.add_list_group()
    for line, text in ((BASELINE + 20, kept), (BASELINE + 40, gone)):
        converted.add_list_item(
            text=text, parent=group, prov=provenance(box(page, text, line))
        )

    rendered = unstruck(pdf, converted).export_to_markdown()

    assert rendered.strip() == f"- {kept}", rendered


def test_an_underline_removes_nothing() -> None:
    """An insertion is marked below the baseline, not through the word."""
    text = "The account is closed after nine months."
    pdf, page = printed((LEFT, BASELINE, text))
    underline(page, "nine")

    assert unstruck(pdf, paragraph(page, text)).texts[0].text == text


def test_a_table_rule_removes_nothing() -> None:
    """A rule above the capitals or below the descenders crosses no x-height."""
    text = "Transfers settle within two business days."
    pdf, page = printed((LEFT, BASELINE, text))
    rule(page, BASELINE + 3)
    rule(page, BASELINE - 1.1 * FONT)

    assert unstruck(pdf, paragraph(page, text)).texts[0].text == text


def test_a_stroke_across_part_of_a_word_removes_nothing() -> None:
    """A stroke must cross most of a word to delete it."""
    text = "Each charger supports a maximum of sixteen devices."
    pdf, page = printed((LEFT, BASELINE, text))
    target, height = word(page, "sixteen"), BASELINE - 0.33 * FONT
    page.draw_line(
        (target.x0, height),
        (target.x0 + 0.4 * target.width, height),
        color=INK,
        width=1,
    )

    assert unstruck(pdf, paragraph(page, text)).texts[0].text == text


def test_a_struck_heading_loses_the_word() -> None:
    """A heading becomes the section path every passage under it carries."""
    heading = "Warranty for two three years"
    pdf, page = printed((LEFT, BASELINE, heading))
    strike(page, "two")
    converted = document()
    converted.add_heading(text=heading, prov=provenance(box(page, heading)))

    assert unstruck(pdf, converted).texts[0].text == "Warranty for three years"


def test_a_struck_table_cell_loses_the_word() -> None:
    """A passage's table cells come from the grid, not from the text items."""
    pdf, page = printed((LEFT, BASELINE, "Battery"), (300, BASELINE, "six eight hours"))
    strike(page, "six")
    cells = [
        TableCell(
            text=text,
            bbox=BoundingBox(
                l=edges[0],
                t=edges[1],
                r=edges[2],
                b=edges[3],
                coord_origin=CoordOrigin.TOPLEFT,
            ),
            start_row_offset_idx=0,
            end_row_offset_idx=1,
            start_col_offset_idx=col,
            end_col_offset_idx=col + 1,
        )
        for col, (text, edges) in enumerate(
            [
                ("Battery", box(page, "Battery")),
                ("six eight hours", box(page, "six eight hours")),
            ]
        )
    ]
    converted = document()
    converted.add_table(
        data=TableData(num_rows=1, num_cols=2, table_cells=cells),
        prov=provenance((LEFT, BASELINE - 12, 500, BASELINE + 4)),
    )

    grid = unstruck(pdf, converted).tables[0].data.table_cells

    assert [cell.text for cell in grid] == ["Battery", "eight hours"]


def test_only_the_item_the_stroke_crosses_changes() -> None:
    """The same word printed elsewhere on the page is kept."""
    first, second = "The fee is six euros.", "The cap is six euros."
    pdf, page = printed((LEFT, BASELINE, first), (LEFT, BASELINE + 20, second))
    strike(page, "six", BASELINE + 20)
    converted = document()
    converted.add_text(
        label=DocItemLabel.TEXT, text=first, prov=provenance(box(page, first))
    )
    converted.add_text(
        label=DocItemLabel.TEXT,
        text=second,
        prov=provenance(box(page, second, BASELINE + 20)),
    )

    texts = [item.text for item in unstruck(pdf, converted).texts]

    assert texts == [first, "The cap is euros."]


def test_an_unreadable_source_changes_nothing(caplog) -> None:
    """The conversion already succeeded; the strike pass cannot fail it."""
    _, page = printed((LEFT, BASELINE, PRINTED))
    converted = paragraph(page)
    before = converted.export_to_dict()

    with caplog.at_level(logging.WARNING):
        after = _unstruck(converted, b"%PDF-1.4 not really")

    assert after.export_to_dict() == before
    assert "struck" in caplog.text


#: A word pymupdf's base font prints and splits back out as one word.
WORD = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,;()-",
    min_size=1,
    max_size=10,
)


@given(
    words=st.lists(WORD, min_size=1, max_size=12),
    underlined=st.lists(st.integers(0, 11), max_size=3),
    rules=st.lists(st.sampled_from([3.0, -1.1 * FONT, 6.0]), max_size=2),
)
@settings(deadline=None)
def test_a_page_with_no_strike_comes_out_unchanged(words, underlined, rules) -> None:
    """Underlines and rules are not strikes, and nothing else is touched."""
    text = " ".join(words)
    pdf, page = printed((LEFT, BASELINE, text))
    for index in {i for i in underlined if i < len(words)}:
        found = page.get_text("words")
        if index < len(found):
            target = pymupdf.Rect(found[index][:4])
            page.draw_line(
                (target.x0, BASELINE + 1.3), (target.x1, BASELINE + 1.3), width=1
            )
    for offset in rules:
        rule(page, BASELINE + offset)
    converted = paragraph(page, text)
    before = converted.export_to_dict()

    assert unstruck(pdf, converted).export_to_dict() == before


# ── Part of a word, and a word spelled with other quotes ──────────────────


def converted(pdf, converted_document: DoclingDocument) -> DoclingDocument:
    """What the pipeline makes of a drawn page the converter read as given."""
    pipeline = PdfPipeline(
        table_mode="fast",
        heading_hierarchy=False,
        document_timeout_seconds=1.0,
        artifacts_path=None,
    )
    pipeline._built = _Converted(converted_document)
    return pipeline.convert(
        SourceDocument(sha256="a" * 64, data=pdf.tobytes(), scanned=False)
    ).document


def test_a_struck_word_spelled_with_a_curly_apostrophe_goes() -> None:
    """The converter writes a straight apostrophe where the page prints a curly one.

    Drawn with MuPDF's built-in Unicode fonts: the base-14 Helvetica the
    other tests print with cannot encode the curly apostrophe.
    """
    text = "Read FIFA’s handbook and the IFAB guide."
    pdf = pymupdf.open()
    page = pdf.new_page(width=WIDTH, height=HEIGHT)
    page.insert_htmlbox(pymupdf.Rect(LEFT, 360, WIDTH - LEFT, 400), text)
    line = next(
        line
        for block in page.get_text("rawdict")["blocks"]
        for line in block.get("lines", ())
    )
    baseline = line["spans"][0]["chars"][0]["origin"][1]
    size = line["spans"][0]["size"]
    target = word(page, "FIFA’s", baseline - 1)
    height = baseline - 0.33 * size
    page.draw_line((target.x0, height), (target.x1, height), color=INK, width=1)
    reading = document()
    reading.add_text(
        label=DocItemLabel.TEXT,
        text="Read FIFA's handbook and the IFAB guide.",
        prov=provenance((LEFT - 1, 355, WIDTH - LEFT, 405)),
    )

    assert converted(pdf, reading).texts[0].text == "Read handbook and the IFAB guide."


def test_unstruck_punctuation_beside_a_struck_word_stays() -> None:
    """A bracket printed beside a deleted word was not deleted with it."""
    text = "Refunds (not credits) are paid."
    pdf, page = printed((LEFT, BASELINE, text))
    found = word(page, "(not")
    bracket = pymupdf.get_text_length("(", fontsize=FONT)
    height = BASELINE - 0.33 * FONT
    page.draw_line((found.x0 + bracket, height), (found.x1, height), color=INK, width=1)

    assert (
        converted(pdf, paragraph(page, text)).texts[0].text
        == "Refunds (credits) are paid."
    )


def test_the_struck_half_of_a_slash_joined_word_goes() -> None:
    """A deleted "six" before "/eight" keeps the alternative printed beside it."""
    text = "Each charger supports six/eight devices."
    pdf, page = printed((LEFT, BASELINE, text))
    found = word(page, "six/eight")
    six = pymupdf.get_text_length("six", fontsize=FONT)
    height = BASELINE - 0.33 * FONT
    page.draw_line((found.x0, height), (found.x0 + six, height), color=INK, width=1)

    result = converted(pdf, paragraph(page, text)).texts[0].text

    assert "six" not in result
    assert "eight devices." in result


# ── Text the page does not paint ───────────────────────────────────────────


def test_text_the_page_clips_out_of_view_is_dropped() -> None:
    """A diagram's hidden layer reaches the converter, but no reader sees it.

    The page's whole content is drawn under a clip path covering its top
    half, so the label printed in the bottom half is in the content stream
    and shows nowhere.
    """
    pdf, page = printed((LEFT, 200, "Card fees"), (LEFT, 500, "HIDDEN LABEL"))
    shown, hidden = box(page, "Card fees", 200), box(page, "HIDDEN LABEL", 500)
    streams = page.get_contents()
    clip = b"q 0 %d %d %d re W n\n" % (int(HEIGHT) - 300, int(WIDTH), 300)
    pdf.update_stream(streams[0], clip + pdf.xref_stream(streams[0]))
    pdf.update_stream(streams[-1], pdf.xref_stream(streams[-1]) + b"\nQ")
    reading = document()
    reading.add_text(label=DocItemLabel.TEXT, text="Card fees", prov=provenance(shown))
    reading.add_text(
        label=DocItemLabel.TEXT, text="HIDDEN LABEL", prov=provenance(hidden)
    )

    texts = [one.text for one in converted(pdf, reading).texts if one.text.strip()]

    assert texts == ["Card fees"]


def test_an_ocr_layer_drawn_invisible_is_kept() -> None:
    """A scan's text layer is invisible by design, and it is the only text there is."""
    pdf = pymupdf.open()
    page = pdf.new_page(width=WIDTH, height=HEIGHT)
    page.insert_text((LEFT, BASELINE), PRINTED, fontsize=FONT, render_mode=3)

    assert converted(pdf, paragraph(page)).texts[0].text == PRINTED


# ── Superscripts ───────────────────────────────────────────────────────────


def raised(page, before: str, suffix: str, after: str, baseline: float = BASELINE):
    """Prints `before`, then `suffix` raised and smaller, then `after`."""
    page.insert_text((LEFT, baseline), before, fontsize=FONT, color=INK)
    x = LEFT + pymupdf.get_text_length(before, fontsize=FONT) + 0.2
    page.insert_text((x, baseline - 3), suffix, fontsize=5, color=INK)
    x += pymupdf.get_text_length(suffix, fontsize=5) + 2.5
    page.insert_text((x, baseline), after, fontsize=FONT, color=INK)


def test_a_superscript_ordinal_joins_its_number() -> None:
    """A converter writes a raised "st" as "1 st"; the page prints "1st"."""
    pdf = pymupdf.open()
    page = pdf.new_page(width=WIDTH, height=HEIGHT)
    raised(page, "Effective from 1", "st", "July 2026")
    reading = document()
    reading.add_text(
        label=DocItemLabel.TEXT,
        text="Effective from 1 st July 2026",
        prov=provenance((LEFT - 1, BASELINE - 12, LEFT + 200, BASELINE + 3)),
    )

    assert converted(pdf, reading).texts[0].text == "Effective from 1st July 2026"


def test_a_raised_footnote_number_is_left_alone() -> None:
    """A raised digit after a word is a footnote mark, not part of the word."""
    pdf = pymupdf.open()
    page = pdf.new_page(width=WIDTH, height=HEIGHT)
    raised(page, "Fees apply", "2", "to all cards")
    reading = document()
    reading.add_text(
        label=DocItemLabel.TEXT,
        text="Fees apply 2 to all cards",
        prov=provenance((LEFT - 1, BASELINE - 12, LEFT + 200, BASELINE + 3)),
    )

    assert converted(pdf, reading).texts[0].text == "Fees apply 2 to all cards"
