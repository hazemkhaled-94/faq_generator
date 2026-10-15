"""The PDF pipeline."""

from __future__ import annotations

import io
import logging
import math
import re
import unicodedata
from difflib import SequenceMatcher
from itertools import pairwise
from typing import ClassVar, NamedTuple, cast

import pymupdf
from docling.datamodel.backend_options import ThreadedDoclingParseBackendOptions
from docling.datamodel.base_models import (
    ConversionStatus,
    DocumentStream,
    InputFormat,
)
from docling.datamodel.document import ConversionResult
from docling.datamodel.pipeline_options import (
    HeadingHierarchyOptions,
    PdfPipelineOptions,
    TableFormerMode,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc.base import BoundingBox
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.document import DoclingDocument

from preprocessing.parsing.models import Conversion, SourceDocument
from preprocessing.parsing.pipelines.base import ConversionFailed, Pipeline

log = logging.getLogger(__name__)

#: A discretionary hyphen, spelled either as U+00AD or as the U+0002 some
#: fonts map it to, with whatever space follows it.
_SOFT_HYPHEN = re.compile(r"[\x02\u00ad]\s*")

#: Control characters other than newline and tab.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

#: Zero-width marks.
_INVISIBLE = re.compile(r"[\u200b-\u200d\u2060\ufeff]")

#: The words that complete a hanging hyphen, as in "Zoll- und Steuerrecht".
_JOINING = (
    "und|oder|bzw|sowie|beziehungsweise|als|noch|bis|u|resp|vs|versus|statt|wie"
    "|and|or|nor|to"
)

#: A word the page broke across two lines with a real hyphen: a hyphen after
#: a letter and before a lower-case continuation, unless a word in
#: `_JOINING` follows it.
#:
#: ponytail: punctuation alone cannot separate a broken word from two ratings
#: written side by side in one cell ("Mittel- niedrig"). Telling those apart
#: needs a character language model or the geometry of the cells either side.
_BROKEN_WORD = re.compile(
    rf"(?<=[A-Za-z\u00c4\u00d6\u00dc\u00e4\u00f6\u00fc\u00df])-\s+(?!(?:{_JOINING})\b)(?=[a-z\u00e4\u00f6\u00fc\u00df])"
)

#: Every space that is not U+0020.
_SPACES = re.compile(r"[\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]")

#: Where a deletion stroke sits: above the baseline by this share of the font
#: size, low and high. Through the x-height, so an underline below the
#: baseline and a rule above the capitals are not strikes.
_STRIKE_BAND = (0.15, 0.55)

#: The least share of a word's width one stroke must cross to delete it.
_STRIKE_COVER = 0.6

#: The most a line may rise or fall, in points, and still be horizontal.
_LEVEL = 0.3

#: The shortest line, in points, that can strike a word.
_SHORTEST = 2.0

#: How far, in points, the two readers may disagree on a page's size before
#: the page is left alone rather than matched in the wrong place.
_PAGE_SLACK = 1.0

#: One unit of a string, as the converter spaced it.
_TOKEN = re.compile(r"\S+")


class PdfPipeline(Pipeline):
    """Converts PDFs, tuned for born-digital documents with tables.

    Heading hierarchy and table structure are both on. OCR is not
    implemented, so a scanned document is refused rather than converted into
    an empty one.

    Text comes off the page through Docling's own backend with
    `enforce_same_font` turned off, so a word carrying an f-ligature arrives
    whole rather than split around a bare `f`.

    The converter is built once and reused.
    """

    media_types: ClassVar[tuple[str, ...]] = ("application/pdf",)

    def __init__(
        self,
        *,
        table_mode: str,
        heading_hierarchy: bool,
        document_timeout_seconds: float | None,
        artifacts_path: str | None,
    ) -> None:
        """Initialises the pipeline. Every value comes from the environment.

        Args:
            table_mode: TableFormer mode, `fast` or `accurate`.
            heading_hierarchy: Whether to rebuild the heading tree.
            document_timeout_seconds: Longest one conversion may run.
            artifacts_path: Where the model weights are, or None to let
                Docling download them.
        """
        self._table_mode = TableFormerMode(table_mode)
        self._heading_hierarchy = heading_hierarchy
        self._timeout = document_timeout_seconds
        self._artifacts_path = artifacts_path
        self._built: DocumentConverter | None = None

    def convert(self, source: SourceDocument) -> Conversion:
        """Converts one PDF, refusing a scanned one.

        Args:
            source: The stored file and what is known about it.

        Returns:
            The document, its struck-through words removed, its raised
            ordinal suffixes rejoined and its text mended, and its
            confidences.

        Raises:
            ConversionFailed: If the document needs OCR, or if Docling cannot
                convert all of it.
        """
        # OCR extension point. See this package's README for what enabling
        # it takes.
        if source.scanned:
            raise ConversionFailed(
                "the document carries too little text to read without OCR, "
                "which is not enabled"
            )

        try:
            result = self._converter().convert(
                # Docling picks its input format from the extension, so the
                # stream's name is where this pipeline states its format.
                DocumentStream(
                    name=f"{source.sha256}.pdf", stream=io.BytesIO(source.data)
                )
            )
        except Exception as exc:
            raise ConversionFailed(f"{type(exc).__name__}: {exc}") from exc
        # A timeout or a failed page ends PARTIAL_SUCCESS without raising.
        if result.status != ConversionStatus.SUCCESS:
            errors = dict.fromkeys(error.error_message for error in result.errors)
            raise ConversionFailed(
                f"the conversion ended {result.status.value}: {'; '.join(errors)}"
            )
        return Conversion(
            document=_repaired(
                _rejoined(_unstruck(result.document, source.data), source.data)
            ),
            confidence=_score(result, "mean_score"),
            confidence_low=_score(result, "low_score"),
        )

    def fetch_weights(self) -> None:
        """Builds the converter, which downloads any weight not yet cached.

        Raises:
            LocalEntryNotFoundError: If a weight is not cached and the
                Hugging Face hub is offline.
        """
        self._converter().initialize_pipeline(InputFormat.PDF)

    def _converter(self) -> DocumentConverter:
        """Returns the converter, building it once."""
        if self._built is None:
            options = PdfPipelineOptions(
                do_ocr=False,
                do_table_structure=True,
                table_structure_options=TableStructureOptions(mode=self._table_mode),
                heading_hierarchy_options=HeadingHierarchyOptions(
                    enabled=self._heading_hierarchy
                ),
                # Required by the line above: the hierarchy reads font style
                # off the parsed cells.
                generate_parsed_pages=self._heading_hierarchy,
                document_timeout=self._timeout,
                artifacts_path=self._artifacts_path,
            )
            self._built = DocumentConverter(
                allowed_formats=[InputFormat.PDF],
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=options,
                        # No backend=: Docling's own reports the font style
                        # heading levels are ranked by and the word cells
                        # table structure is matched against.
                        backend_options=ThreadedDoclingParseBackendOptions(  # pyright: ignore[reportCallIssue]
                            enforce_same_font=False
                        ),
                    )
                },
            )
            log.info("built the PDF converter")
        return self._built


def _mend(text: str) -> str:
    """Rejoins a line-broken word and spells the rest so it can be copied.

    Composes to NFC, joins soft and line-break hyphens, drops control and
    zero-width characters, and turns every other kind of space into U+0020.

    Args:
        text: One string as the converter read it.

    Returns:
        The mended string.
    """
    composed = unicodedata.normalize("NFC", text)
    cleaned = _SPACES.sub(
        " ", _INVISIBLE.sub("", _CONTROL.sub("", _SOFT_HYPHEN.sub("", composed)))
    )
    # After the space normalisation, so the broken-word rule sees one kind of
    # space.
    return _BROKEN_WORD.sub("", cleaned)


def _repaired(document: DoclingDocument) -> DoclingDocument:
    """Mends every string a later stage reads out of a converted document.

    Both the text items and the table grid: a passage's text comes from the
    first and its table_cells from the second.

    Args:
        document: The converted document, modified in place.

    Returns:
        The same document.
    """
    for item in document.texts:
        item.text = _mend(item.text)
        item.orig = _mend(item.orig)
    for table in document.tables:
        for cell in table.data.table_cells:
            cell.text = _mend(cell.text)
    return document


class _Word(NamedTuple):
    """One word as pymupdf placed it, with a top-left origin."""

    text: str
    left: float
    top: float
    right: float
    bottom: float
    baseline: float
    size: float


def _unstruck(document: DoclingDocument, data: bytes) -> DoclingDocument:
    """Removes every word the page strikes through from a converted document.

    A PDF marks a deletion with nothing but a drawn line, and no converter
    reads drawn lines, so the struck word reaches the text beside the one
    replacing it. The source is read again with pymupdf, every word a stroke
    runs through is found, and it is removed from each text item, its
    `orig`, and each table cell, whose box holds it. Section headers are
    text items. An item left with no text leaves the body. A page that
    strikes nothing is never touched.

    Args:
        document: The converted document, modified in place.
        data: The PDF it was converted from.

    Returns:
        The same document.
    """
    try:
        marked = _marked(data)
    except Exception as exc:  # noqa: BLE001 - the conversion already succeeded
        log.warning(
            "struck-through words were not looked for: %s: %s",
            type(exc).__name__,
            exc,
        )
        return document

    for number, (width, height, flagged) in marked.items():
        page = document.pages.get(number)
        if page is None or (
            abs(page.size.width - width) > _PAGE_SLACK
            or abs(page.size.height - height) > _PAGE_SLACK
        ):
            log.warning(
                "struck-through words on page %d were left in: the converter "
                "and pymupdf disagree on the page's size",
                number,
            )
            continue
        for item in document.texts:
            words = [
                word
                for prov in item.prov
                if prov.page_no == number
                for word in _inside(flagged, prov.bbox, height)
            ]
            if any(struck for _, struck in words):
                item.text = _without(item.text, words)
                item.orig = _without(item.orig, words)
                if not item.text.strip():
                    # Out of the body, so a struck bullet renders as no
                    # bullet and a struck heading heads nothing; in place,
                    # so no other item's reference moves.
                    item.content_layer = ContentLayer.INVISIBLE
        for table in document.tables:
            if not table.prov or table.prov[0].page_no != number:
                continue
            for cell in table.data.table_cells:
                words = [] if cell.bbox is None else _inside(flagged, cell.bbox, height)
                if any(struck for _, struck in words):
                    cell.text = _without(cell.text, words)
    return document


def _marked(data: bytes) -> dict[int, tuple[float, float, list[tuple[_Word, bool]]]]:
    """Reads every page that strikes a word through.

    Args:
        data: The PDF.

    Returns:
        By page number from 1: the page's width and height, and every word on
        it in reading order, each flagged True when it is struck.
    """
    marked = {}
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        for number in range(1, pdf.page_count + 1):
            page = pdf.load_page(number - 1)
            strokes = _strokes(page)
            if not strokes:
                continue
            flagged = [(word, _struck(word, strokes)) for word in _words(page)]
            if any(struck for _, struck in flagged):
                marked[number] = (page.rect.width, page.rect.height, flagged)
    return marked


def _strokes(page: pymupdf.Page) -> list[tuple[float, float, float, float]]:
    """Every horizontal stroke a page draws, as (left, right, top, bottom).

    Each line of a stroked path made of nothing but horizontal lines,
    carrying the path's width; each rectangle of a filled path made of
    nothing but rectangles, which is how some writers draw a thin bar; and
    any other filled shape whole. One per line or rectangle rather than one
    per path: a writer may draw every deletion on a line, or on a page, as
    one path, and the box around them all runs through the words between
    them, or stands two lines tall and strikes nothing. The edge of an
    outlined shape is not a stroke: a highlight's frame can run through a
    line of text. Whether one strikes a word is `_struck`'s to decide.
    """
    found = []
    for path in page.get_drawings():
        kind, items = path.get("type") or "", path["items"]
        if "s" in kind and all(
            item[0] == "l" and abs(item[2].y - item[1].y) < _LEVEL for item in items
        ):
            half = (path.get("width") or 0.0) / 2
            for _, start, end in items:
                middle = (start.y + end.y) / 2
                found.append(
                    (
                        min(start.x, end.x),
                        max(start.x, end.x),
                        middle - half,
                        middle + half,
                    )
                )
        elif "f" in kind:
            shapes = (
                [item[1] for item in items]
                if items and all(item[0] == "re" for item in items)
                else [path["rect"]]
            )
            found += [(shape.x0, shape.x1, shape.y0, shape.y1) for shape in shapes]
    return [stroke for stroke in found if stroke[1] - stroke[0] > _SHORTEST]


def _words(page: pymupdf.Page) -> list[_Word]:
    """Every word on a page's horizontal lines, in reading order."""
    words: list[_Word] = []
    # The layout as a dict, which the method's annotation does not say.
    for block in cast(dict, page.get_text("rawdict"))["blocks"]:
        for line in block.get("lines", ()):
            if line["dir"] != (1, 0):
                continue
            run: list[tuple[dict, float]] = []
            for span in line["spans"]:
                for char in span["chars"]:
                    if char["c"].isspace():
                        words += _word(run)
                        run = []
                    else:
                        run.append((char, span["size"]))
            words += _word(run)
    return words


def _word(run: list[tuple[dict, float]]) -> list[_Word]:
    """Joins a run of characters into the word they spell, if there is one."""
    if not run:
        return []
    boxes = [char["bbox"] for char, _ in run]
    return [
        _Word(
            text="".join(char["c"] for char, _ in run),
            left=min(box[0] for box in boxes),
            top=min(box[1] for box in boxes),
            right=max(box[2] for box in boxes),
            bottom=max(box[3] for box in boxes),
            baseline=run[0][0]["origin"][1],
            size=max(size for _, size in run),
        )
    ]


def _struck(word: _Word, strokes: list[tuple[float, float, float, float]]) -> bool:
    """Reports whether one stroke runs through a word's x-height, across most of it.

    In any colour: the stroke's position is what marks a deletion.
    """
    low, high = _STRIKE_BAND
    width = word.right - word.left
    return any(
        top >= word.baseline - high * word.size
        and bottom <= word.baseline - low * word.size
        and min(right, word.right) - max(left, word.left) >= _STRIKE_COVER * width
        for left, right, top, bottom in strokes
    )


def _inside(
    flagged: list[tuple[_Word, bool]], bbox: BoundingBox, height: float
) -> list[tuple[_Word, bool]]:
    """The words whose centre lies in one of the converter's boxes.

    The converter's box may count up from the page foot; pymupdf's count down
    from the top, so the box is turned to a top-left origin first.
    """
    box = bbox.to_top_left_origin(page_height=height)
    return [
        (word, struck)
        for word, struck in flagged
        if box.l <= (word.left + word.right) / 2 <= box.r
        and box.t <= (word.top + word.bottom) / 2 <= box.b
    ]


def _without(text: str, words: list[tuple[_Word, bool]]) -> str:
    """Drops the struck words from one string.

    The string is aligned with the page word by word, in reading order, so
    the same word printed unstruck elsewhere in it stays. A word the two
    readers spell differently is not matched, and stays too.

    Args:
        text: The converter's string.
        words: The page's words inside its box, flagged when struck.

    Returns:
        The string without them, each removed with the space before it.
    """
    tokens = list(_TOKEN.finditer(text))
    matcher = SequenceMatcher(
        None,
        [unicodedata.normalize("NFKC", token.group()) for token in tokens],
        [unicodedata.normalize("NFKC", word.text) for word, _ in words],
        autojunk=False,
    )
    gone = {
        block.a + offset
        for block in matcher.get_matching_blocks()
        for offset in range(block.size)
        if words[block.b + offset][1]
    }
    if not gone:
        return text
    kept: list[str] = []
    end = 0
    for index, token in enumerate(tokens):
        gap, end = text[end : token.start()], token.end()
        if index not in gone:
            # The first word kept takes the string's own leading space.
            kept.append((gap if kept else text[: tokens[0].start()]) + token.group())
    return "".join(kept) + text[end:]


def _rejoined(document: DoclingDocument, data: bytes) -> DoclingDocument:
    """Joins a raised ordinal suffix back to the number it follows.

    A converter writes a raised "st", "nd", "rd" or "th" as a word of its own,
    so a page printing "1st July" reaches the text as "1 st July", which then
    reads as an addition to every fact that says "1st". The source is read
    again with pymupdf, every superscript of letters straight after a digit is
    found, and in each text item and table cell whose box holds it the space
    between the number and the suffix is closed. A raised digit, as in a
    footnote mark, or anything that is not letters, is left alone.

    Args:
        document: The converted document, modified in place.
        data: The PDF it was converted from.

    Returns:
        The same document.
    """
    try:
        found = _raised(data)
        for number, (width, height, suffixes) in found.items():
            page = document.pages.get(number)
            if page is None or (
                abs(page.size.width - width) > _PAGE_SLACK
                or abs(page.size.height - height) > _PAGE_SLACK
            ):
                continue
            for item in document.texts:
                for prov in item.prov:
                    if prov.page_no == number:
                        item.text = _joined(item.text, prov.bbox, height, suffixes)
                        item.orig = _joined(item.orig, prov.bbox, height, suffixes)
            for table in document.tables:
                if not table.prov or table.prov[0].page_no != number:
                    continue
                for cell in table.data.table_cells:
                    if cell.bbox is not None:
                        cell.text = _joined(cell.text, cell.bbox, height, suffixes)
    except Exception as exc:  # noqa: BLE001 - the conversion already succeeded
        log.warning(
            "raised ordinal suffixes were not rejoined: %s: %s",
            type(exc).__name__,
            exc,
        )
    return document


def _raised(
    data: bytes,
) -> dict[int, tuple[float, float, list[tuple[str, str, tuple[float, float]]]]]:
    """Reads every raised run of letters that follows a number.

    Args:
        data: The PDF.

    Returns:
        By page number from 1, for each page that has any: its width and
        height, and each as (digits, suffix, centre of the suffix).
    """
    found = {}
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        for number in range(1, pdf.page_count + 1):
            page = pdf.load_page(number - 1)
            suffixes = []
            # The layout as a dict, which the method's annotation does not say.
            for block in cast(dict, page.get_text("rawdict"))["blocks"]:
                for line in block.get("lines", ()):
                    spans = [
                        (span, "".join(char["c"] for char in span["chars"]))
                        for span in line["spans"]
                    ]
                    for (_, before), (span, text) in pairwise(spans):
                        digits = re.search(r"\d+$", before.rstrip())
                        suffix = text.strip()
                        if span["flags"] & 1 and suffix.isalpha() and digits:
                            x0, y0, x1, y1 = span["bbox"]
                            suffixes.append(
                                (digits.group(), suffix, ((x0 + x1) / 2, (y0 + y1) / 2))
                            )
            if suffixes:
                found[number] = (page.rect.width, page.rect.height, suffixes)
    return found


def _joined(
    text: str,
    bbox: BoundingBox,
    height: float,
    suffixes: list[tuple[str, str, tuple[float, float]]],
) -> str:
    """Closes the space before each raised suffix whose centre lies in a box."""
    box = bbox.to_top_left_origin(page_height=height)
    for digits, suffix, (x, y) in suffixes:
        if box.l <= x <= box.r and box.t <= y <= box.b:
            text = re.sub(
                rf"\b({re.escape(digits)})\s+({re.escape(suffix)})\b",
                r"\1\2",
                text,
                count=1,
            )
    return text


def _score(result: ConversionResult, name: str) -> float | None:
    """Reads one confidence score off a conversion.

    Args:
        result: What Docling returned.
        name: The score's attribute name.

    Returns:
        The score, or None when it is absent or NaN.
    """
    value = getattr(getattr(result, "confidence", None), name, None)
    return None if value is None or math.isnan(value) else float(value)
