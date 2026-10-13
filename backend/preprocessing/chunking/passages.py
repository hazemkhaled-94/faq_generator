"""Cutting a converted document into passages."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from typing import cast

from docling_core.transforms.chunker.doc_chunk import DocChunk
from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider,
)
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.transforms.serializer.markdown import (
    MarkdownPictureSerializer,
    MarkdownTableSerializer,
)
from docling_core.types.doc.common.reference import RefItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.items.node import DocItem
from docling_core.types.doc.items.text import TextItem
from docling_core.types.doc.labels import DocItemLabel

from nlp.analysis import read
from nlp.language import detect
from nlp.models import Sentence
from nlp.windows import reserved
from preprocessing.chunking.furniture import furniture_of, headed, tidied
from preprocessing.chunking.models import Chunk, Chunking


class NoPassages(Exception):
    """Raised when a document yielded no passages to store."""


class _Markdown(ChunkingSerializerProvider):
    """Renders every kind of block into the passage text, in Markdown."""

    def get_serializer(self, doc: DoclingDocument) -> ChunkingDocSerializer:
        """Builds the serializer the chunker uses for one document."""
        return ChunkingDocSerializer(
            doc=doc,
            table_serializer=MarkdownTableSerializer(),
            picture_serializer=MarkdownPictureSerializer(),
        )


def chunking_of(
    chunks: Iterable,
    *,
    max_tokens: int,
    count_tokens: Callable[[str], int],
    to_passage: Callable[[int, object], Chunk],
) -> Chunking:
    """Numbers every chunk the chunker produced and counts the oversized ones.

    All of the builder's decisions and none of its machinery.

    Args:
        chunks: What the chunker returned.
        max_tokens: The token budget.
        count_tokens: Counts the tokens in a string.
        to_passage: Turns an ordinal and a chunk into a passage.

    Returns:
        The numbered passages and how many exceed the budget.

    Raises:
        NoPassages: If no chunk holds anything but whitespace.
    """
    kept = [chunk for chunk in chunks if chunk.text.strip()]
    if not kept:
        raise NoPassages("the document yielded no passages")

    passages = [to_passage(ordinal, chunk) for ordinal, chunk in enumerate(kept, 1)]
    oversized = sum(
        1 for passage in passages if count_tokens(passage.text) > max_tokens
    )
    return Chunking(passages=passages, oversized=oversized)


def chunks_of(
    document: DoclingDocument, chunker: HybridChunker, language: str | None
) -> tuple[DoclingDocument, list[DocChunk]]:
    """Cuts a document into chunks, chapter by chapter.

    The document's running heads and feet are read first: debris they show
    the converter left in the body comes out, and each chapter they name
    starts with an empty heading trail and leads every trail in it. Then
    every list is kept beside its lead-in.

    Args:
        document: The converted document, which is not modified.
        chunker: The chunker.
        language: The document's language.

    Returns:
        The document the chunks were cut from, which is `document` itself
        unless its furniture changed something, and the chunks.
    """
    furniture = furniture_of(document)
    tidy, titles = tidied(document, furniture)
    chunks = headed(
        cast(list[DocChunk], list(chunker.chunk(tidy))), furniture, titles, language
    )
    return tidy, lead_ins_kept(chunks, chunker, tidy)


#: What a lead-in is: a paragraph, as the converter labels one.
_PROSE = frozenset({DocItemLabel.TEXT, DocItemLabel.PARAGRAPH})


def lead_ins_kept(
    chunks: list[DocChunk], chunker: HybridChunker, document: DoclingDocument
) -> list[DocChunk]:
    """Keeps a list with the sentence that introduces it.

    The chunker closes a chunk wherever the token budget runs out, which can
    be right after a lead-in ending in ":" and before the list it introduces;
    every item of that list then reads as a rule of its own. When a chunk
    ends on such a lead-in and the next, under the same headings, opens with
    a list item, the lead-in moves into the next chunk if that still fits
    the budget, and otherwise is appended to its heading trail, which both
    model stages are shown. A list cut from its lead-in by a sub-heading is
    left as it is: its own heading says what it is under.

    Args:
        chunks: What the chunker returned, in order.
        chunker: The chunker, whose tokenizer and budget a moved lead-in is
            measured by, and whose delimiter it is joined with.
        document: The converted document, which holds the lead-in's text.

    Returns:
        The chunks, with every such lead-in kept beside its list. A chunk the
        move leaves empty is gone.
    """
    # As the chunker cut them: a trail extended below is not a new heading.
    trails = [chunk.meta.headings for chunk in chunks]
    kept: list[DocChunk] = []
    for index, chunk in enumerate(chunks):
        lead = (
            _lead_in(kept[-1], document)
            if kept and trails[index - 1] == trails[index] and _opens_a_list(chunk)
            else None
        )
        if lead is not None:
            item, text = lead
            moved = chunk.model_copy(
                update={
                    "text": text + chunker.delim + chunk.text,
                    "meta": chunk.meta.model_copy(
                        update={"doc_items": [item, *chunk.meta.doc_items]}
                    ),
                }
            )
            if (
                chunker.tokenizer.count_tokens(chunker.contextualize(moved))
                <= chunker.max_tokens
            ):
                before = kept.pop()
                rest = before.text.rstrip()[: -len(text)].rstrip()
                if rest:
                    kept.append(
                        before.model_copy(
                            update={
                                "text": rest,
                                "meta": before.meta.model_copy(
                                    update={"doc_items": before.meta.doc_items[:-1]}
                                ),
                            }
                        )
                    )
                chunk = moved
            else:
                chunk = chunk.model_copy(
                    update={
                        "meta": chunk.meta.model_copy(
                            update={"headings": [*(chunk.meta.headings or []), text]}
                        )
                    }
                )
        kept.append(chunk)
    return kept


def _lead_in(chunk: DocChunk, document: DoclingDocument) -> tuple[DocItem, str] | None:
    """The paragraph ending in ":" a chunk closes on, and its text, or None.

    The chunker hands its items over as bare copies, so the text is read
    off the document the reference names.
    """
    last = chunk.meta.doc_items[-1] if chunk.meta.doc_items else None
    if last is None or last.label not in _PROSE:
        return None
    item = RefItem.model_validate({"$ref": last.self_ref}).resolve(document)
    text = item.text.strip() if isinstance(item, TextItem) else ""
    if text.endswith(":") and chunk.text.rstrip().endswith(text):
        return last, text
    return None


def _opens_a_list(chunk: DocChunk) -> bool:
    """Reports whether a chunk's first item is a list item."""
    return bool(chunk.meta.doc_items) and (
        chunk.meta.doc_items[0].label == DocItemLabel.LIST_ITEM
    )


def lines_of(text: str) -> list[dict]:
    """Locates every non-empty line of a rendered table passage.

    A table has no sentences, so its rows are what a fact cites.

    Args:
        text: The rendered passage text.

    Returns:
        One {i, start, end, predicates} per non-empty line, numbered from
        zero, with offsets into `text`.
    """
    found: list[dict] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped:
            start = offset + line.index(stripped[0])
            found.append(
                {
                    "i": len(found),
                    "start": start,
                    "end": start + len(stripped),
                    "predicates": 0,
                }
            )
        offset += len(line)
    return found


def _prose_counted(text: str, sentences: list[Sentence]) -> list[dict]:
    """Numbers a table passage's lines, counting the finite verbs of its prose.

    A line that is not a Markdown table row carries the predicates of the
    sentences overlapping it; a table row keeps 0.
    """
    numbered = lines_of(text)
    for line in numbered:
        if not text.startswith("|", line["start"]):
            line["predicates"] = sum(
                one.predicates
                for one in sentences
                if one.start < line["end"] and one.end > line["start"]
            )
    return numbered


class PassageBuilder:
    """Splits a converted document into retrievable passages.

    Uses the converter's own hybrid chunker, which cuts on the document's
    structure before merging or dividing by token count, so a passage keeps
    its heading trail.
    """

    def __init__(
        self, *, embedding_model: str, max_tokens: int, merge_peers: bool
    ) -> None:
        """Initialises the builder and its chunker.

        Args:
            embedding_model: The model whose tokenizer sizes a passage.
            max_tokens: The token budget a passage is cut to.
            merge_peers: Whether to combine undersized neighbours that share
                a heading.
        """
        loaded = HuggingFaceTokenizer.from_pretrained(
            model_name=embedding_model, max_tokens=max_tokens
        )
        # Less what the embedder adds, so a passage cut to it fits its window.
        self._max_tokens = max_tokens - reserved(loaded.tokenizer)
        self._tokenizer = loaded.model_copy(update={"max_tokens": self._max_tokens})
        self._chunker = HybridChunker(
            tokenizer=self._tokenizer,
            merge_peers=merge_peers,
            serializer_provider=_Markdown(),
        )

    def build(self, document: DoclingDocument, language: str | None) -> Chunking:
        """Cuts one document into passages and reads their linguistic surface.

        Args:
            document: The converted document.
            language: The document's language, used where a passage is too
                short to detect its own.

        Returns:
            The numbered passages and how many exceed the budget.

        Raises:
            NoPassages: If the document yielded nothing but whitespace.
        """
        tidy, chunks = chunks_of(document, self._chunker, language)
        chunking = chunking_of(
            chunks,
            max_tokens=self._max_tokens,
            count_tokens=self._tokenizer.count_tokens,
            to_passage=lambda ordinal, chunk: self._passage(tidy, ordinal, chunk),
        )
        return replace(chunking, passages=self._read(chunking.passages, language))

    @staticmethod
    def _read(passages: list[Chunk], language: str | None) -> list[Chunk]:
        """Adds each passage's language, numbered units and lemmas.

        The language is detected per passage; one too short to judge keeps
        the document's, and so does a table, whose rendering is padding and
        terms rather than prose. Every passage is read for vocabulary, a table
        included. Only the numbering differs: a table's rows are numbered
        rather than its sentences split. Passages are parsed in one batch per
        language.

        Args:
            passages: The numbered passages.
            language: The document's language.

        Returns:
            The same passages, each carrying its language, units and lemmas.
        """
        spoken = [
            (index, language if p.table_cells else detect(p.text) or language)
            for index, p in enumerate(passages)
        ]
        parsed: dict[int, tuple] = {}
        for code in {found for _, found in spoken}:
            batch = [index for index, found in spoken if found == code]
            parsed |= dict(
                zip(
                    batch,
                    read((passages[index].text for index in batch), code),
                    strict=True,
                )
            )

        by_index = dict(spoken)
        surfaced = []
        for index, passage in enumerate(passages):
            sentences, lemmas = parsed[index]
            numbered = (
                _prose_counted(passage.text, sentences)
                if passage.table_cells
                else [
                    {
                        "i": s.index,
                        "start": s.start,
                        "end": s.end,
                        "predicates": s.predicates,
                    }
                    for s in sentences
                ]
            )
            surfaced.append(
                replace(
                    passage,
                    language=by_index[index],
                    sentences=numbered,
                    lemmas=lemmas,
                )
            )
        return surfaced

    @staticmethod
    def _passage(document: DoclingDocument, ordinal: int, chunk) -> Chunk:
        """Reads one chunk into the values the passages table holds."""
        # Every evidence offset is an index into this string.
        text = chunk.text.strip()
        # Resolved once and handed to both readers below, so the cells and the
        # box drawn over them agree on which rows this passage rendered.
        tables = _tables_rendered(document, chunk.meta.doc_items, text)
        boxes = _boxes(document, chunk.meta.doc_items, tables)
        return Chunk(
            ordinal=ordinal,
            text=text,
            page_from=boxes[0]["page"] if boxes else None,
            page_to=boxes[-1]["page"] if boxes else None,
            section_path=" > ".join(chunk.meta.headings)
            if chunk.meta.headings
            else None,
            block_type=_block_type(chunk.meta.doc_items),
            doc_item_refs=[item.self_ref for item in chunk.meta.doc_items],
            bbox=boxes,
            table_cells=_grids(document, chunk.meta.doc_items, tables),
        )


#: What extraction skips as navigation rather than content.
_NAVIGATION = frozenset({DocItemLabel.CODE, DocItemLabel.DOCUMENT_INDEX})


def _block_type(items: list[DocItem]) -> str | None:
    """Labels a passage for the extractor that will read it.

    A table anywhere in a merged passage wins; otherwise the first item's
    label, passing over code and index items unless every item is one.
    """
    if not items:
        return None
    if any(item.label == DocItemLabel.TABLE for item in items):
        return DocItemLabel.TABLE.value
    return next(
        (item for item in items if item.label not in _NAVIGATION), items[0]
    ).label.value


def _tables_rendered(
    document: DoclingDocument, items: list[DocItem], rendered: str
) -> dict[str, tuple]:
    """Resolves every table in a passage and the rows this passage renders.

    Args:
        document: The converted document.
        items: The items this passage was cut from.
        rendered: The rendered passage text.

    Returns:
        The table and its paired rows, by the item's self reference.
    """
    numbered = lines_of(rendered)
    tables = {}
    for reference in items:
        if reference.label != DocItemLabel.TABLE:
            continue
        # Through the alias rather than the field name: it is the serialised
        # form and the only one a checker sees on the constructor.
        table = RefItem.model_validate({"$ref": reference.self_ref}).resolve(document)
        rows = _rendered_rows(table, rendered, numbered)
        tables[reference.self_ref] = (table, rows)
        # A line one table took is no other table's.
        taken = {line["i"] for _, line in rows if line is not None}
        numbered = [line for line in numbered if line["i"] not in taken]
    return tables


def _cell_box(table, rows: list[tuple[list, dict | None]]) -> tuple[int, list] | None:
    """Locates the rows of a table that one passage renders.

    Header cells are left out although the piece repeats them.

    Args:
        table: The resolved table item.
        rows: Its rows, each paired with the line rendering it or None.

    Returns:
        The page and the cell boxes on it, or None when either is missing.
    """
    boxes = [
        cell.bbox
        for cells, line in rows
        if line is not None
        for cell in cells
        if cell.bbox is not None
    ]
    page = next((prov.page_no for prov in table.prov or []), None)
    # ponytail: one page per table. A table broken across a page boundary
    # would need its cells grouped by which page each one falls on.
    return (page, boxes) if page is not None and boxes else None


def _boxes(
    document: DoclingDocument, items: list[DocItem], tables: dict[str, tuple]
) -> list[dict]:
    """Locates a passage on the pages it spans, one box per page.

    Every box is normalised to a top-left origin.

    Args:
        document: The converted document.
        items: The items this passage was cut from.
        tables: What `_tables_rendered` resolved.

    Returns:
        One {page, l, t, r, b} per page spanned, in page order.
    """
    by_page: dict[int, list] = {}
    for reference in items:
        if reference.self_ref in tables:
            placed = _cell_box(*tables[reference.self_ref])
            if placed is not None:
                page_no, boxes = placed
                by_page.setdefault(page_no, []).extend(boxes)
                continue
        for provenance in reference.prov or []:
            page = document.pages.get(provenance.page_no)
            if page is None:
                continue
            box = provenance.bbox.to_top_left_origin(page_height=page.size.height)
            by_page.setdefault(provenance.page_no, []).append(box)

    return [
        {
            "page": page_no,
            "l": round(min(box.l for box in boxes), 1),
            "t": round(min(box.t for box in boxes), 1),
            "r": round(max(box.r for box in boxes), 1),
            "b": round(max(box.b for box in boxes), 1),
        }
        for page_no, boxes in sorted(by_page.items())
    ]


def _fields(line: str) -> list[str]:
    """Splits one rendered Markdown row into its cell values."""
    return [field.strip() for field in line.strip("|").split("|")]


def _rendered_rows(
    table, rendered: str, numbered: list[dict]
) -> list[tuple[list, dict | None]]:
    """Pairs each row of a table with the numbered line that renders it.

    A row matches by position: every one of its values must sit at its own
    column index. Lines are consumed in order, so two identical rows take two
    different lines. A data row this passage does not render is dropped.
    Header rows are kept whether matched or not, and so carry no line; a
    `row_header` cell does not make its row one.

    Args:
        table: The resolved table item.
        rendered: The rendered passage text.
        numbered: What `lines_of` found in it.

    Returns:
        One (cells, line) per kept row, in row order.
    """
    lines = [
        line
        for line in numbered
        if (text := rendered[line["start"] : line["end"]]).startswith("|")
        and set(text) - set("|-: ")
    ]
    taken = [False] * len(lines)

    by_row: dict[int, list] = {}
    for cell in table.data.table_cells:
        by_row.setdefault(cell.start_row_offset_idx, []).append(cell)

    kept: list[tuple[list, dict | None]] = []
    for _, cells in sorted(by_row.items()):
        if any(cell.column_header for cell in cells):
            kept.append((cells, None))
            continue
        # As the Markdown serializer renders a cell.
        placed = [
            (cell.start_col_offset_idx, shown)
            for cell in cells
            if (shown := cell.text.replace("\n", " ").replace("|", "&#124;").strip())
        ]
        if not placed:
            continue
        for index, line in enumerate(lines):
            if taken[index]:
                continue
            fields = _fields(rendered[line["start"] : line["end"]])
            if all(col < len(fields) and fields[col] == value for col, value in placed):
                taken[index] = True
                kept.append((cells, line))
                break
    return kept


def _grids(
    document: DoclingDocument, items: list[DocItem], tables: dict[str, tuple]
) -> list[dict]:
    """Reads the cell grid out of every table in a passage.

    Header flags, position and spans are all lost in the rendered string.
    Each data cell carries the numbered line it sits in, which is what a fact
    drawn from it cites.

    Args:
        document: The converted document.
        items: The items this passage was cut from.
        tables: What `_tables_rendered` resolved.

    Returns:
        One grid per table, each {caption, num_rows, num_cols, cells}.
    """
    grids = []
    for reference in items:
        if reference.self_ref not in tables:
            continue
        table, rows = tables[reference.self_ref]
        grids.append(
            {
                "caption": table.caption_text(document).strip() or None,
                "num_rows": table.data.num_rows,
                "num_cols": table.data.num_cols,
                "cells": [
                    {
                        "row": cell.start_row_offset_idx,
                        "col": cell.start_col_offset_idx,
                        "row_span": cell.row_span,
                        "col_span": cell.col_span,
                        # Two flags, not one: a corner cell heads its column
                        # and not its row.
                        "column_header": bool(cell.column_header),
                        "row_header": bool(cell.row_header),
                        "text": cell.text,
                        "line": None if line is None else line["i"],
                    }
                    for cells, line in rows
                    for cell in cells
                ],
            }
        )
    return grids
