"""The PDF pipeline."""

from __future__ import annotations

import io
import logging
import math
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable
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
from docling_core.types.doc.items.node import DocItem
from docling_core.types.doc.items.table.table import TableItem
from docling_core.types.doc.items.table.table_data import TableCell
from docling_core.types.doc.labels import DocItemLabel

from nlp.text import printed, rejoined, unfinished
from preprocessing.parsing.models import Conversion, SourceDocument
from preprocessing.parsing.pipelines.base import ConversionFailed, Pipeline

log = logging.getLogger(__name__)

#: A discretionary hyphen, spelled either as U+00AD or as the U+0002 some
#: fonts map it to. A soft hyphen is invisible unless its line breaks there,
#: so it is dropped unless a space, a digit or a capital follows it, where it is
#: the hyphen a font drew with that code, or unless its document draws every
#: hyphen so (`_draws`).
_SOFT_HYPHEN = re.compile(r"[\x02\u00ad]")

#: Control characters other than newline and tab.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

#: The C1 controls but U+0085, which `_SPACES` folds to a space: a legacy
#: cp1252 character the converter read as its Unicode control, an en dash as
#: U+0096.
_C1 = re.compile(r"[\x80-\x84\x86-\x9f]")

#: Every space that is not U+0020.
_SPACES = re.compile(r"[\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]")

#: Where a deletion stroke sits: above the baseline by this share of the font
#: size, low and high. Through the x-height, so an underline below the
#: baseline and a rule above the capitals are not strikes.
_STRIKE_BAND = (0.15, 0.55)

#: The least share of a word's width one stroke must cross to delete it.
_STRIKE_COVER = 0.6

#: The least share of a punctuation mark's width one stroke must cross to
#: delete it.
_PUNCTUATION_COVER = 0.5

#: Typographic marks and what they are compared as: curly apostrophes and
#: quotes as the straight ones, every dash as a hyphen. For matching only.
_FOLDED = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u2032": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
    }
)

#: The most a line may rise or fall, in points, and still be horizontal.
_LEVEL = 0.3

#: The shortest line, in points, that can strike a word.
_SHORTEST = 2.0

#: How far, in points, the two readers may disagree on a page's size before
#: the page is left alone rather than matched in the wrong place.
_PAGE_SLACK = 1.0

#: What pymupdf extracts when the page's clip is not applied, so text a clip
#: path hides is returned.
_UNCLIPPED = pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_MEDIABOX_CLIP

#: How far apart, in points, two reads of one page may place a character and
#: still mean one glyph. Float noise between two extractions of the same
#: content stream, not a distance on the page.
_SAME_PLACE = 1.0

#: How far, in points, a character may stand past the page's edge and still
#: be on it.
_EDGE = 0.5

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
        ocr_char_threshold: int = 0,
    ) -> None:
        """Initialises the pipeline. Every value comes from the environment.

        Args:
            table_mode: TableFormer mode, `fast` or `accurate`.
            heading_hierarchy: Whether to rebuild the heading tree.
            document_timeout_seconds: Longest one conversion may run.
            artifacts_path: Where the model weights are, or None to let
                Docling download them.
            ocr_char_threshold: The characters a page may hold and still be
                named image-only when a picture covers it; 0 names only a
                page with no text.
        """
        self._ocr_characters = ocr_char_threshold
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
            ordinal suffixes rejoined, its text mended and its broken tables
            joined, and its confidences.

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
            document=_tabled(
                _repaired(
                    _rejoined(_unstruck(result.document, source.data), source.data)
                ),
                source.data,
            ),
            confidence=_score(result, "mean_score"),
            confidence_low=_score(result, "low_score"),
            unread_pages=image_only_pages(source.data, self._ocr_characters),
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


def _drawn(after: str) -> bool:
    """Whether what follows a soft hyphen shows it was drawn: a space, a digit or a capital."""
    return after != "" and (after.isspace() or after.isdigit() or after.isupper())


def _softened(text: str, drawn: bool = False) -> str:
    """Spells a soft hyphen "-" where it was drawn, else drops it.

    Drawn before a space, a digit or a capital in every text layer, and
    before anything else too where `drawn` says the layer uses U+00AD as its
    hyphen. Otherwise, inside a word, between letters of a script without
    case, or after a hyphen, it is invisible. What follows a spelled hyphen,
    a space at a line break, is left for `rejoined`, which joins the broken
    word and keeps "Kredit- oder".
    """

    def spelled(found: re.Match[str]) -> str:
        after = found.string[found.end() : found.end() + 1]
        before = found.string[max(found.start() - 1, 0) : found.start()]
        keep = _drawn(after) or (drawn and after != "")
        return "-" if keep and before != "-" else ""

    return _SOFT_HYPHEN.sub(spelled, text)


def _draws(document: DoclingDocument) -> bool:
    """Whether a document's text layer uses U+00AD as its hyphen.

    It does when one stands before a space, a digit or a capital, or when the
    document prints no U+002D at all: an undrawn discretionary hyphen does not
    reach a text layer in the middle of a line. A document that also prints
    U+002D and shows no such mark keeps dropping one before a lower-case
    letter.
    """
    joined = "\n".join(
        [
            *(item.text for item in document.texts),
            *(
                cell.text
                for table in document.tables
                for cell in table.data.table_cells
            ),
        ]
    )
    return "-" not in joined or any(
        _drawn(joined[found.end() : found.end() + 1])
        for found in _SOFT_HYPHEN.finditer(joined)
    )


#: The share of a page a picture must cover for the page to count as a scan.
_SCAN_COVER = 0.5


def _union_area(rects: list[pymupdf.Rect]) -> float:
    """Returns the area covered by rectangles, overlaps counted once."""
    rects = [rect for rect in rects if not rect.is_empty]
    xs = sorted({x for rect in rects for x in (rect.x0, rect.x1)})
    total = 0.0
    for left, right in pairwise(xs):
        spans = sorted(
            (rect.y0, rect.y1) for rect in rects if rect.x0 <= left and rect.x1 >= right
        )
        top = float("-inf")
        for start, end in spans:
            total += (right - left) * max(0.0, end - max(start, top))
            top = max(top, end)
    return total


def image_only_pages(data: bytes, characters: int = 0) -> tuple[int, ...]:
    """Names the pages that are a picture and carry next to no text layer.

    A document's mean characters per page hides one scanned page among
    digital ones, and OCR is not enabled, so such a page converts to nothing
    but a stamp a merge tool put on it, `Seite 2 von 3`.

    Args:
        data: The raw PDF bytes.
        characters: The most characters a page may hold and still be named,
            PARSING_OCR_CHAR_THRESHOLD: the least a text page has.

    Returns:
        The 1-based numbers of the pages with that little text and pictures
        covering most of the page.
    """
    pages: list[int] = []
    with pymupdf.open(stream=data, filetype="pdf") as document:
        for number in range(1, document.page_count + 1):
            page = document[number - 1]
            if len(str(page.get_text()).strip()) > characters:
                continue
            area = abs(page.rect)
            covered = _union_area(
                [
                    pymupdf.Rect(info["bbox"]) & page.rect
                    for info in page.get_image_info()
                ]
            )
            if area and covered / area >= _SCAN_COVER:
                pages.append(number)
    return tuple(pages)


def _legacy(found: re.Match[str]) -> str:
    """A C1 control as the cp1252 character it stands for, or nothing if none."""
    try:
        return found.group().encode("latin-1").decode("cp1252")
    except UnicodeDecodeError:
        return ""


def _mend(
    text: str, whole: frozenset[tuple[str, str]] = frozenset(), drawn: bool = False
) -> str:
    """Rejoins a line-broken word and spells the rest so it can be copied.

    Composes to NFC, joins soft and line-break hyphens, drops control and
    format characters, reads a C1 control as the cp1252 character it stands
    for, and turns every other kind of space into U+0020.

    Args:
        text: One string as the converter read it.
        whole: The words its document prints whole around a hyphen, which
            keep theirs where a line breaks them there.
        drawn: Whether its document uses U+00AD as its hyphen, `_draws`.

    Returns:
        The mended string.
    """
    composed = unicodedata.normalize("NFC", text)
    # Every format character, zero-width marks and bidi marks and isolates
    # alike, renders as nothing and so cannot be quoted.
    formatted = "".join(
        char
        for char in _softened(composed, drawn)
        if unicodedata.category(char) != "Cf"
    )
    cleaned = _SPACES.sub(" ", _C1.sub(_legacy, _CONTROL.sub("", formatted)))
    # After the space normalisation, so the broken-word rule sees one kind of
    # space.
    return rejoined(cleaned, whole)


def _repaired(document: DoclingDocument) -> DoclingDocument:
    """Mends every string a later stage reads out of a converted document.

    Both the text items and the table grid: a passage's text comes from the
    first and its table_cells from the second. A word broken at its own
    hyphen keeps it where the document prints it whole elsewhere.

    Args:
        document: The converted document, modified in place.

    Returns:
        The same document.
    """
    whole, drawn = _printed(document), _draws(document)
    for item in document.texts:
        item.text = _mend(item.text, whole, drawn)
        item.orig = _mend(item.orig, whole, drawn)
    for table in document.tables:
        for cell in table.data.table_cells:
            cell.text = _mend(cell.text, whole, drawn)
    return document


def _printed(document: DoclingDocument) -> frozenset[tuple[str, str]]:
    """The words a document's texts and cells print whole around a hyphen."""
    return printed(
        [
            *(item.text for item in document.texts),
            *(
                cell.text
                for table in document.tables
                for cell in table.data.table_cells
            ),
        ]
    )


#: What ends a sentence in a cell: a cell ending on one is complete, and the
#: row below it is a row of its own. Not a colon, which in a cell opens what
#: follows - `Impact:` over `goal kick`.
_SENTENCE_END = (".", "!", "?")

#: A font as a page sets text in it: its name, and its size in whole points.
_Font = tuple[str, int]


def _tabled(document: DoclingDocument, data: bytes | None = None) -> DoclingDocument:
    """Joins the tables the converter broke at a page or inside a wrapped cell.

    A table running onto the next page comes out as two, and the second has
    no header: a table with no header row, the next body item after a table
    of its width on the same page or the one after, is that table's rest and
    joins it, moving to the furniture layer so no reference the passages
    store moves; a picture between the two, a page's decoration, does not
    part them. And a cell wrapped onto a second line comes out as a row of
    its own: a row with no label in its first column, a cell of which goes
    on in lower case, and over which no cell ends a sentence, is the rest of
    the row above and joins it; and a row holding a label and nothing else,
    over a row whose label opens in lower case, is that label's head. Read
    off the grid and the case alone, never off a word, so it holds for any
    table in any language with case; a script without case joins no row,
    which is the safe side.

    The converter may take the rest's first row for a header. That row is
    data, and the rest joins, when each of its cells is set in the font most
    of the first table's data in its column is set in, and not in the font of
    that column's header: the type the PDF itself sets the two in, so a
    second table whose header is set as the first's stays apart, and so does
    the rest of a table whose header is set as its data. Nor does a row join
    that holds no figure in a column most of the first table's data holds
    one in: a second schedule headed in its data's type names its columns
    where the first's rows priced them.

    Args:
        document: The converted document, modified in place.
        data: The PDF it was converted from, which the fonts are read off,
            or None to read the grid alone and keep every headed rest apart.

    Returns:
        The same document.
    """
    font = _typeface(data)
    # The table the next body item would continue: the item right before it,
    # where that is a table, or the table that one already joined; and the
    # rows it printed on its own page, before any rest joined it.
    anchor: TableItem | None = None
    own = 0
    for item, _ in document.iterate_items():
        if not isinstance(item, DocItem) or item.content_layer != ContentLayer.BODY:
            continue
        if item.label == DocItemLabel.PICTURE:
            continue
        if not isinstance(item, TableItem):
            anchor = None
        elif anchor is not None and _continues(anchor, own, item, font):
            for cell in item.data.table_cells:
                cell.column_header = False
            _append(anchor, item)
            item.content_layer = ContentLayer.FURNITURE
        else:
            anchor, own = item, item.data.num_rows
    whole = _printed(document)
    for table in document.tables:
        if table.content_layer == ContentLayer.BODY:
            _unwrapped(table, whole)
    return document


def _continues(
    table: TableItem,
    own: int,
    rest: TableItem,
    font: Callable[[int, BoundingBox], _Font | None],
) -> bool:
    """Whether a table is the rest of the one before it, broken at a page.

    A rest holding a header is one only where the header is its first row,
    set and filled as the table's data is: `_set_as_data`.
    """
    if rest.data.num_cols != table.data.num_cols or not table.prov or not rest.prov:
        return False
    gap = rest.prov[0].page_no - table.prov[-1].page_no
    if gap not in (0, 1):
        return False
    heads = [cell for cell in rest.data.table_cells if cell.column_header]
    return not heads or _set_as_data(table, own, rest, heads, font)


def _set_as_data(
    table: TableItem,
    own: int,
    rest: TableItem,
    heads: list[TableCell],
    font: Callable[[int, BoundingBox], _Font | None],
) -> bool:
    """Whether a rest's header cells are its first row, set as `table`'s data.

    Each is set in the font most of the table's data cells in its column are,
    and not in the font of the table's header cell there. And the row holds a
    figure in each column most of whose data cells hold one, as a fee's does,
    so a second schedule headed in the data's type, its `Frist` over a column
    of prices, stays apart. Only the rows the table printed on its own page
    are read, where `font` looks for them.
    """
    if any(cell.start_row_offset_idx != 0 or cell.bbox is None for cell in heads):
        return False
    page = rest.prov[0].page_no
    first = table.prov[0].page_no
    headed = {
        cell.start_col_offset_idx: cell.bbox
        for cell in table.data.table_cells
        if cell.column_header and cell.bbox is not None
    }
    if not headed:
        return False
    usual: dict[int, Counter[_Font | None]] = defaultdict(Counter)
    figured: dict[int, Counter[bool]] = defaultdict(Counter)
    for cell in table.data.table_cells:
        if (
            not cell.column_header
            and cell.bbox is not None
            and cell.text.strip()
            and cell.start_row_offset_idx < own
        ):
            usual[cell.start_col_offset_idx][font(first, cell.bbox)] += 1
            figured[cell.start_col_offset_idx][_figured(cell.text)] += 1
    # The columns most of whose data cells hold a figure, as a fee column does.
    figures = {column for column, held in figured.items() if held[True] > held[False]}
    if any(
        cell.start_row_offset_idx == 0
        and cell.start_col_offset_idx in figures
        and not _figured(cell.text)
        for cell in rest.data.table_cells
    ):
        return False
    for cell in heads:
        column = cell.start_col_offset_idx
        set_in = font(page, cast(BoundingBox, cell.bbox))
        commonest = usual[column].most_common(1)
        if (
            set_in is None
            or not commonest
            or set_in != commonest[0][0]
            or (column in headed and set_in == font(first, headed[column]))
        ):
            return False
    return True


def _figured(text: str) -> bool:
    """Whether a cell holds a figure: a price, a rate, a count or a date."""
    return any(character.isdigit() for character in text)


def _typeface(data: bytes | None) -> Callable[[int, BoundingBox], _Font | None]:
    """Reads the font a box's text is set in, reading each page once.

    The font most of the box's characters are set in. None with no PDF, for
    a box holding no text, and on a page that cannot be read.
    """
    pages: dict[int, tuple[float, list[dict]] | None] = {}

    def font(page_no: int, bbox: BoundingBox) -> _Font | None:
        if data is None:
            return None
        if page_no not in pages:
            pages[page_no] = _spans(data, page_no)
        read = pages[page_no]
        if read is None:
            return None
        height, spans = read
        box = bbox.to_top_left_origin(page_height=height)
        counted: Counter[_Font] = Counter()
        for span in spans:
            left, top, right, bottom = span["bbox"]
            if (
                box.l - _SAME_PLACE <= (left + right) / 2 <= box.r + _SAME_PLACE
                and box.t - _SAME_PLACE <= (top + bottom) / 2 <= box.b + _SAME_PLACE
            ):
                counted[(span["font"], round(span["size"]))] += len(span["text"])
        return counted.most_common(1)[0][0] if counted else None

    return font


def _spans(data: bytes, page_no: int) -> tuple[float, list[dict]] | None:
    """A page's height and every span of text it shows, or None if unreadable."""
    try:
        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            page = pdf.load_page(page_no - 1)
            # The layout as a dict, which the method's annotation does not say.
            return page.rect.height, [
                span
                for block in cast(dict, page.get_text("dict"))["blocks"]
                for line in block.get("lines", ())
                for span in line["spans"]
                if span["text"].strip()
            ]
    except Exception as exc:  # noqa: BLE001 - the conversion already succeeded
        log.warning(
            "the fonts on page %d were not read: %s: %s",
            page_no,
            type(exc).__name__,
            exc,
        )
        return None


def _append(table: TableItem, rest: TableItem) -> None:
    """Puts the rows of `rest` under the rows of `table`."""
    offset = table.data.num_rows
    for cell in rest.data.table_cells:
        table.data.table_cells.append(
            cell.model_copy(
                update={
                    "start_row_offset_idx": cell.start_row_offset_idx + offset,
                    "end_row_offset_idx": cell.end_row_offset_idx + offset,
                }
            )
        )
    table.data.num_rows += rest.data.num_rows
    table.prov.extend(rest.prov)


def _unwrapped(table: TableItem, whole: frozenset[tuple[str, str]]) -> None:
    """Joins each row that is the wrapped rest of the row above it into it.

    A label alone on a row that opens in lower case, or closes a bracket the
    label above it opened, is the last line of that label (a top-aligned
    table whose other cells stay on the first line, each of them filled). One that opens in upper
    case heads the row below, as a wrapped label's first line does.

    A row a spanning cell or a header covers is left as it is, on either
    side of a join: the cell holds more than one row, and a header names the
    columns rather than continuing a cell. A word the wrap broke is mended,
    keeping a hyphen `whole` says the document prints.
    """
    rows: dict[int, dict[int, TableCell]] = {}
    held: set[int] = set()
    for cell in table.data.table_cells:
        if cell.row_span == 1 and cell.col_span == 1 and not cell.column_header:
            rows.setdefault(cell.start_row_offset_idx, {})[
                cell.start_col_offset_idx
            ] = cell
        else:
            held.update(range(cell.start_row_offset_idx, cell.end_row_offset_idx))
    order = sorted(set(rows) - held)
    gone: set[int] = set()
    for before, row in pairwise(order):
        # The nearest row still standing, so a label wrapped over three lines
        # joins one line after the other.
        above = rows.get(_kept(row, gone))
        label = rows[row].get(0)
        top = above.get(0) if above else None
        if (
            row == before + 1
            and table.data.num_cols > 1
            and label is not None
            and above is not None
            and top is not None
            and _label_only(rows[row])
            and all(
                above_cell is not None and above_cell.text.strip()
                for above_cell in map(above.get, range(1, table.data.num_cols))
            )
            and _tail(top.text, label.text)
        ):
            top.text = rejoined(f"{top.text.rstrip()} {label.text.strip()}", whole)
            gone.add(row)
    for place, (row, below) in enumerate(pairwise(order)):
        cells, first = rows[row], rows[below].get(0)
        if (
            row not in gone
            and below == row + 1
            and table.data.num_cols > 1
            and _label_only(cells)
            and first is not None
            and first.text.strip()[:1].islower()
            and (
                unfinished(cells[0].text) or not _lower_items(rows, order[place + 2 :])
            )
        ):
            first.text = rejoined(
                f"{cells[0].text.strip()} {first.text.strip()}", whole
            )
            gone.add(row)
    for row in order[1:]:
        if row in gone or _kept(row, gone) in held:
            continue
        cells, above = rows[row], rows.get(_kept(row, gone))
        filled = {col: cell for col, cell in cells.items() if cell.text.strip()}
        if (
            above is None
            or not filled
            or 0 in filled
            or not any(cell.text.lstrip()[0].islower() for cell in filled.values())
            or any(
                not above.get(col) or above[col].text.rstrip().endswith(_SENTENCE_END)
                for col in filled
            )
        ):
            continue
        for col, cell in filled.items():
            above[col].text = rejoined(
                f"{above[col].text.rstrip()} {cell.text.strip()}", whole
            )
        gone.add(row)
    if not gone:
        return
    kept = [
        cell for cell in table.data.table_cells if cell.start_row_offset_idx not in gone
    ]
    for cell in kept:
        shift = sum(1 for one in gone if one < cell.start_row_offset_idx)
        cell.start_row_offset_idx -= shift
        cell.end_row_offset_idx -= shift
    table.data.table_cells = kept
    table.data.num_rows -= len(gone)


def _tail(label: str, rest: str) -> bool:
    """Whether `rest` is the last line of the label above it.

    It opens in lower case, or closes the bracket the label left open and
    opens none of its own.
    """
    closing, bracket, _ = rest.partition(")")
    return rest.strip()[:1].islower() or (
        bool(bracket) and "(" not in closing and label.count("(") > label.count(")")
    )


def _label_only(cells: dict[int, TableCell]) -> bool:
    """Whether a row holds a label and nothing in its other cells."""
    return {col for col, cell in cells.items() if cell.text.strip()} == {0}


def _lower_items(rows: dict[int, dict[int, TableCell]], order: list[int]) -> bool:
    """Whether the next row down opens its label in lower case and has data.

    A label alone over one such row is a wrapped label; over several it is a
    group row heading them, and a wrapped label continues exactly one row.
    """
    if not order:
        return False
    label = rows[order[0]].get(0)
    return (
        label is not None
        and label.text.strip()[:1].islower()
        and not _label_only(rows[order[0]])
    )


def _kept(row: int, gone: set[int]) -> int:
    """The row a wrapped row joins: the nearest above it still standing."""
    above = row - 1
    while above in gone:
        above -= 1
    return above


class _Word(NamedTuple):
    """One word as pymupdf placed it, with a top-left origin."""

    text: str
    left: float
    top: float
    right: float
    bottom: float
    baseline: float
    size: float
    #: Each character as (character, left, right, top, bottom).
    chars: tuple[tuple[str, float, float, float, float], ...]


#: A page word with a flag per character, True when it is struck or hidden.
_Marked = tuple[_Word, tuple[bool, ...]]


def _unstruck(document: DoclingDocument, data: bytes) -> DoclingDocument:
    """Removes every word the page does not show from a converted document.

    A PDF marks a deletion with nothing but a drawn line, and no converter
    reads drawn lines, so the struck word reaches the text beside the one
    replacing it. A diagram's label layer drawn under a clip reaches the
    converter too, although no reader sees it. The source is read again with
    pymupdf, every word a stroke runs through and every word a clip hides is
    found, and each is removed from each text item, its `orig`, and each
    table cell, whose box holds it. Section headers are text items. An item
    left with no text leaves the body. Invisible text is not hidden: a
    scanned page's OCR layer is drawn invisible and is the only text there
    is. A page that strikes and hides nothing is never touched.

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

    for number, (width, height, flagged, hidden) in marked.items():
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
            if any(any(struck) for _, struck in words):
                item.text = _without(item.text, words, hidden)
                item.orig = _without(item.orig, words, hidden)
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
                if any(any(struck) for _, struck in words):
                    cell.text = _without(cell.text, words, hidden)
    return document


def _marked(
    data: bytes,
) -> dict[int, tuple[float, float, list[_Marked], frozenset[_Word]]]:
    """Reads every page that strikes a word through or hides one.

    A page's characters are read twice: as a reader sees them, with the
    page's clip applied, and as the converter may, without it. A character of
    the second read is hidden when the first has no same character in the
    same place, and is flagged as a struck one is. Matched one character to
    another, not by position alone: a label hidden over a visible line, or
    inside a large letter's box, lies where shown characters are. What the
    second read sets past the page's edge is dropped first, as the converter
    drops it, so a label cut at the edge reads as the converter spells it.
    Text drawn invisible is returned by both reads, so it is not hidden: a
    scanned page's OCR layer is drawn that way.

    Args:
        data: The PDF.

    Returns:
        By page number from 1: the page's width and height; every word on it
        in reading order, each with a flag per character, True when it is
        struck or hidden; and the words every character of which is hidden.
    """
    marked = {}
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        for number in range(1, pdf.page_count + 1):
            page = pdf.load_page(number - 1)
            strokes = _strokes(page)
            words = [
                kept
                for word in _words(page, _UNCLIPPED)
                if (kept := _on_page(word, page.rect)) is not None
            ]
            hidden = _hidden(words, _words(page, None))
            flagged: list[_Marked] = []
            for word, gone in zip(words, hidden, strict=True):
                struck = _struck_segments(word, strokes)
                if gone is not None:
                    struck = tuple(a or b for a, b in zip(gone, struck, strict=True))
                flagged.append((word, struck))
            if any(any(struck) for _, struck in flagged):
                marked[number] = (
                    page.rect.width,
                    page.rect.height,
                    flagged,
                    frozenset(
                        word
                        for word, gone in zip(words, hidden, strict=True)
                        if gone is not None and all(gone)
                    ),
                )
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
    line of text. Whether one strikes a word is `_struck_segments`'s to decide.
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


def _hidden(words: list[_Word], shown: list[_Word]) -> list[tuple[bool, ...] | None]:
    """Flags each character of `words` True when `shown` does not hold it.

    `shown` holds a character when one of its words has the same character
    within `_SAME_PLACE` of its top-left corner. A word drawn twice for a
    bold face is in both reads twice, so both copies are held.

    Returns:
        One entry per word: its flags, or None when nothing in it is hidden.
    """
    if [word.text for word in words] == [word.text for word in shown]:
        return [None] * len(words)
    placed: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for word in shown:
        for char, left, _, top, _ in word.chars:
            placed[char].append((left, top))
    found: list[tuple[bool, ...] | None] = []
    for word in words:
        flags = tuple(
            not any(
                abs(left - x) <= _SAME_PLACE and abs(top - y) <= _SAME_PLACE
                for x, y in placed.get(char, ())
            )
            for char, left, _, top, _ in word.chars
        )
        found.append(flags if any(flags) else None)
    return found


def _on_page(word: _Word, rect: pymupdf.Rect) -> _Word | None:
    """The part of a word that lies on the page, or None when none of it does.

    The read without the clip returns characters set past the page's edge,
    which the converter never sees: a label cut at the edge is `SHIP` to it
    and `SHIPPING` here, and the two would never be matched.
    """
    chars = tuple(
        char
        for char in word.chars
        if char[1] >= rect.x0 - _EDGE
        and char[2] <= rect.x1 + _EDGE
        and char[3] >= rect.y0 - _EDGE
        and char[4] <= rect.y1 + _EDGE
    )
    if len(chars) == len(word.chars):
        return word
    if not chars:
        return None
    return word._replace(
        text="".join(char[0] for char in chars),
        left=min(char[1] for char in chars),
        right=max(char[2] for char in chars),
        top=min(char[3] for char in chars),
        bottom=max(char[4] for char in chars),
        chars=chars,
    )


def _words(page: pymupdf.Page, flags: int | None) -> list[_Word]:
    """Every word on a page's horizontal lines, in reading order.

    Args:
        page: The page.
        flags: What pymupdf extracts, or None for its default, which clips
            text to the page.
    """
    words: list[_Word] = []
    # The layout as a dict, which the method's annotation does not say.
    for block in cast(dict, page.get_text("rawdict", flags=flags))["blocks"]:
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
            chars=tuple(
                (char["c"], box[0], box[2], box[1], box[3])
                for (char, _), box in zip(run, boxes, strict=True)
            ),
        )
    ]


def _struck_segments(
    word: _Word, strokes: list[tuple[float, float, float, float]]
) -> tuple[bool, ...]:
    """Flags each character of a word True when a stroke deletes its segment.

    A word is cut into segments: each maximal run of letters or digits, and
    each other character on its own. A run is struck when one stroke through
    the x-height crosses at least `_STRIKE_COVER` of its width; a punctuation
    mark when one crosses at least `_PUNCTUATION_COVER` of its width. So a
    stroke through "six" in "six/eight", or through "not" in "(not", leaves
    the rest of the word standing, while a stroke across part of a run
    removes nothing. In any colour: the stroke's position is what marks a
    deletion.

    Returns:
        One flag per character of `word.chars`, all False when nothing in
        the word is struck.
    """
    low, high = _STRIKE_BAND
    level = [
        (left, right)
        for left, right, top, bottom in strokes
        if top >= word.baseline - high * word.size
        and bottom <= word.baseline - low * word.size
    ]
    flags: list[bool] = []
    start = 0
    while start < len(word.chars):
        end = start + 1
        solid = word.chars[start][0].isalnum()
        while solid and end < len(word.chars) and word.chars[end][0].isalnum():
            end += 1
        left, right = word.chars[start][1], word.chars[end - 1][2]
        cover = _STRIKE_COVER if solid else _PUNCTUATION_COVER
        flags += [
            any(
                min(stroke_right, right) - max(stroke_left, left)
                >= cover * (right - left)
                for stroke_left, stroke_right in level
            )
        ] * (end - start)
        start = end
    return tuple(flags)


def _inside(flagged: list[_Marked], bbox: BoundingBox, height: float) -> list[_Marked]:
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


def _folded(text: str) -> str:
    """Spells text so two readers' typography compares equal.

    NFKC, then curly quotes as straight ones and every dash as a hyphen.
    """
    return unicodedata.normalize("NFKC", text).translate(_FOLDED)


def _remainder(
    token: str, word: _Word, struck: tuple[bool, ...]
) -> tuple[str, bool, bool]:
    """What stays of one converter token whose page word is partly struck.

    The struck flags are laid one to one over the token's characters when the
    two have the same length after NFKC; when they differ, the whole token
    goes if the struck characters cross `_STRIKE_COVER` of the word's width,
    and stays if not.

    Returns:
        The characters kept, whether the first kept one had struck characters
        before it, and whether struck characters follow the last kept one.
        Nothing is kept when every character is struck.
    """
    letters = [
        flag
        for (char, *_), flag in zip(word.chars, struck, strict=True)
        for _ in unicodedata.normalize("NFKC", char)
    ]
    if len(token) != len(unicodedata.normalize("NFKC", token)) or len(token) != len(
        letters
    ):
        width = sum(right - left for _, left, right, _, _ in word.chars)
        crossed = sum(
            right - left
            for (_, left, right, _, _), flag in zip(word.chars, struck, strict=True)
            if flag
        )
        return (
            ("", False, False)
            if crossed >= _STRIKE_COVER * width
            else (token, False, False)
        )
    kept = [index for index, flag in enumerate(letters) if not flag]
    if not kept:
        return "", False, False
    return (
        "".join(token[index] for index in kept),
        kept[0] > 0,
        kept[-1] < len(token) - 1,
    )


def _without(text: str, words: list[_Marked], hidden: frozenset[_Word]) -> str:
    """Drops the struck words, and the struck parts of words, from one string.

    The string is aligned with the page word by word, in reading order, so
    the same word printed unstruck elsewhere in it stays. Words are compared
    with typographic marks folded (a curly apostrophe is a straight one, any
    dash a hyphen), because converters respell them; the string keeps its own
    characters. A word the two readers still spell differently is not
    matched, and stays.

    A word every segment of which is struck is removed with the space before
    it. A word struck in part keeps its unstruck characters, so the bracket
    beside a deleted word stays, and so does the half of "six/eight" that was
    not deleted. What remains takes no space before it when it starts with
    punctuation after struck characters, and the next word takes none after
    it when it ends with an opening bracket or quote whose struck characters
    follow, so "(not credits)" with "not" struck reads "(credits)".

    A string every page word in whose box is wholly hidden is a label the
    page hides, and goes whole, however the converter spelled it: tracked
    letters reach it as `S A L E`, which matches no word.

    Args:
        text: The converter's string.
        words: The page's words inside its box, each with a flag per
            character, True when struck.
        hidden: The page's words every character of which is hidden.

    Returns:
        The string without them.
    """
    if words and all(word in hidden for word, _ in words):
        return ""
    tokens = list(_TOKEN.finditer(text))
    matcher = SequenceMatcher(
        None,
        [_folded(token.group()) for token in tokens],
        [_folded(word.text) for word, _ in words],
        autojunk=False,
    )
    cut = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            word, struck = words[block.b + offset]
            if any(struck):
                cut[block.a + offset] = _remainder(
                    tokens[block.a + offset].group(), word, struck
                )
    if not cut:
        return text
    kept: list[str] = []
    end = 0
    joined = False
    for index, token in enumerate(tokens):
        gap, end = text[end : token.start()], token.end()
        remainder, head, tail = cut.get(index, (token.group(), False, False))
        if not remainder:
            continue
        if not kept:
            # The first word kept takes the string's own leading space.
            gap = text[: tokens[0].start()]
        elif joined or (head and not remainder[0].isalnum()):
            gap = ""
        kept.append(gap + remainder)
        joined = tail and unicodedata.category(remainder[-1]) in ("Ps", "Pi")
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
