"""Cutting a converted document into passages."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from itertools import pairwise
from typing import Any, cast, override

from docling_core.transforms.chunker.doc_chunk import DocChunk
from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider,
)
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.transforms.serializer.base import (
    BaseDocSerializer,
    SerializationResult,
)
from docling_core.transforms.serializer.common import DocSerializer, create_ser_result
from docling_core.transforms.serializer.markdown import (
    MarkdownPictureSerializer,
    MarkdownTableSerializer,
)
from docling_core.types.doc.common.reference import ProvenanceItem, RefItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.items.group import ListGroup
from docling_core.types.doc.items.node import DocItem, NodeItem
from docling_core.types.doc.items.table.table import TableItem
from docling_core.types.doc.items.text import ListItem, TextItem
from docling_core.types.doc.labels import DocItemLabel

from nlp.analysis import read
from nlp.language import detect, detect_surely
from nlp.models import Sentence
from nlp.windows import reserved
from preprocessing.chunking.furniture import furniture_of, headed, tidied
from preprocessing.chunking.models import Chunk, Chunking


class NoPassages(Exception):
    """Raised when a document yielded no passages to store."""


def _footnoted(
    result: SerializationResult,
    table: TableItem,
    document: DoclingDocument,
    serializer: BaseDocSerializer,
    **kwargs: Any,
) -> SerializationResult:
    """A table's rendering followed by the footnotes the converter attached.

    The Markdown table serializer writes captions and no footnotes, and the
    chunker does not walk into them. A note outside the layers the document
    serializer writes (furniture, invisible text), one it excludes, and one
    the table also lists as a caption, which the rendering already holds,
    stay out.
    """
    excluded = serializer.get_excluded_refs(**kwargs)
    layers = serializer.params.layers if isinstance(serializer, DocSerializer) else None
    captions = {ref.cref for ref in table.captions}
    texts = [
        found
        for ref in table.footnotes
        if isinstance(found := ref.resolve(document), TextItem)
        and found.text.strip()
        and found.self_ref not in excluded | captions
        and (layers is None or found.content_layer in layers)
    ]
    if not texts:
        return result
    return create_ser_result(
        text="\n\n".join([result.text, *(t.text.strip() for t in texts)]).strip(),
        span_source=[
            result,
            *(create_ser_result(text=t.text, span_source=t) for t in texts),
        ],
    )


class _Table(MarkdownTableSerializer):
    """A Markdown table with the footnotes attached to it beneath."""

    @override
    def serialize(
        self,
        *,
        item: TableItem,
        doc_serializer: BaseDocSerializer,
        doc: DoclingDocument,
        **kwargs: Any,
    ) -> SerializationResult:
        """Serializes the table, then its footnotes."""
        return _footnoted(
            super().serialize(
                item=item, doc_serializer=doc_serializer, doc=doc, **kwargs
            ),
            item,
            doc,
            doc_serializer,
            **kwargs,
        )


class _Markdown(ChunkingSerializerProvider):
    """Renders every kind of block into the passage text, in Markdown."""

    def get_serializer(self, doc: DoclingDocument) -> ChunkingDocSerializer:
        """Builds the serializer the chunker uses for one document."""
        return ChunkingDocSerializer(
            doc=doc,
            table_serializer=_Table(),
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
    starts with an empty heading trail and leads every trail in it. A list
    the converter flattened is nested again by its indents. Then every list
    is kept beside its lead-in. A chunk ends where its prose changes language.

    Args:
        document: The converted document, which is not modified.
        chunker: The chunker.
        language: The document's language.

    Returns:
        The document the chunks were cut from, which is `document` itself
        unless its furniture changed something, and the chunks.
    """
    furniture = furniture_of(document)
    tidy, titles = tidied(document, furniture, language)
    tidy = nested(tidy)
    chunks = headed(
        cast(list[DocChunk], list(chunker.chunk(tidy))), furniture, titles, language
    )
    chunks = lead_ins_kept(_one_language(chunks, tidy), chunker, tidy)
    return tidy, _indented(chunks, chunker, tidy)


def nested(document: DoclingDocument) -> DoclingDocument:
    """A document whose flattened lists are nested again by their indents.

    The converter builds every list flat, and an item printed indented under
    another then reads as a rule of its own. Within one list, an item whose
    left edge lies more than half a line right of the item before it, in
    the same column of the same page and inside that item's width, nests
    under it; a later item back at an outer edge returns to that level.
    Across a column break no level opens: the item there returns to the
    open level its indent matches, each indent measured from the left edge
    of its own column - the leftmost edge of the page's paragraphs and list
    items reaching across the item's - so depth open at a column's foot is
    not carried into the next. Across a page break no level opens either,
    and the indent is read off the edge before it: a page holding only a
    list's sub-items would put its own edge at theirs. A line is the height
    of the list's shortest item, which is one line in nearly every list: the
    median is a two-line item's wherever items wrap. A nested list is
    rendered as indented Markdown, as the converter renders one it built
    itself.

    Returns:
        `document` itself when no list is indented, otherwise a copy.
    """
    lists: list[list[ListItem]] = []
    for group in document.groups:
        if not isinstance(group, ListGroup):
            continue
        items = [
            one
            for child in group.children
            if isinstance(one := child.resolve(document), ListItem) and one.prov
        ]
        if len(items) > 1:
            lists.append(items)
    if not lists:
        return document
    blocks = _blocks(document)
    plans: list[list[tuple[str, str]]] = []
    for items in lists:
        step = min(abs(one.prov[0].bbox.height) for one in items) / 2
        edge = _column_edge(items[0].prov[0], blocks)
        # The open levels: each one's indent and the item it nests under.
        levels: list[tuple[float, str | None]] = [
            (items[0].prov[0].bbox.l - edge, None)
        ]
        moves: list[tuple[str, str]] = []
        for before, item in pairwise(items):
            here, there = item.prov[0], before.prov[0]
            if here.page_no == there.page_no:
                if here.bbox.l >= there.bbox.r:
                    edge = _column_edge(here, blocks)
                elif there.bbox.l + step < here.bbox.l:
                    levels.append((here.bbox.l - edge, before.self_ref))
            indent = here.bbox.l - edge
            while len(levels) > 1 and indent < levels[-1][0] - step:
                levels.pop()
            if (parent := levels[-1][1]) is not None:
                moves.append((item.self_ref, parent))
        if moves:
            plans.append(moves)
    if not plans:
        return document

    tidy = document.model_copy(deep=True)
    for moves in plans:
        under: dict[str, ListGroup] = {}
        for reference, parent in moves:
            if parent not in under:
                under[parent] = tidy.add_list_group(parent=_node(parent, tidy))
            item = _node(reference, tidy)
            held = item.parent.resolve(tidy) if item.parent else None
            if held is not None:
                held.children = [one for one in held.children if one.cref != reference]
            under[parent].children.append(_ref(reference))
            item.parent = _ref(under[parent].self_ref)
    return tidy


#: The blocks a column's left edge is read off: its paragraphs and list
#: items. A picture, a table or a heading may be set into the margin or run
#: across the page, and is no column's edge.
_COLUMN_BLOCKS = frozenset(
    {DocItemLabel.TEXT, DocItemLabel.PARAGRAPH, DocItemLabel.LIST_ITEM}
)


def _blocks(document: DoclingDocument) -> dict[int, list[tuple[float, float]]]:
    """The left and right edges of every paragraph and list item, by page."""
    found: dict[int, list[tuple[float, float]]] = {}
    for item, _ in document.iterate_items():
        if isinstance(item, DocItem) and item.label in _COLUMN_BLOCKS:
            for prov in item.prov:
                found.setdefault(prov.page_no, []).append((prov.bbox.l, prov.bbox.r))
    return found


def _column_edge(
    prov: ProvenanceItem, blocks: dict[int, list[tuple[float, float]]]
) -> float:
    """The left edge of the column a block starts in, read off its page."""
    left = prov.bbox.l
    return min(
        (start for start, end in blocks.get(prov.page_no, ()) if start <= left < end),
        default=left,
    )


def _ref(reference: str) -> RefItem:
    """A reference to the node at a JSON pointer."""
    return RefItem.model_validate({"$ref": reference})


def _node(reference: str, document: DoclingDocument) -> NodeItem:
    """The node a reference names in a document."""
    return _ref(reference).resolve(document)


#: The indent of one level of a nested list, as the converter renders one.
_INDENT = "    "


def _indented(
    chunks: list[DocChunk], chunker: HybridChunker, document: DoclingDocument
) -> list[DocChunk]:
    """The chunks, with each nested list item indented as deep as it nests.

    The chunker renders each item of a chunk on its own and joins them,
    which drops the indent a nested list's own rendering gives: every item
    would read as one of the outer list. Each item's rendering is found in
    the chunk's text in order, and a nested one gets `_INDENT` per level.
    """
    serializer = chunker.serializer_provider.get_serializer(doc=document)
    kept: list[DocChunk] = []
    for chunk in chunks:
        depths = [_depth(item.self_ref, document) for item in chunk.meta.doc_items]
        if not any(depths):
            kept.append(chunk)
            continue
        text, at, pieces = chunk.text, 0, []
        for item, depth in zip(chunk.meta.doc_items, depths, strict=True):
            rendered = serializer.serialize(item=_node(item.self_ref, document)).text
            found = text.find(rendered, at) if rendered else -1
            if found < 0:
                continue
            pieces += [text[at:found], _INDENT * depth, rendered]
            at = found + len(rendered)
        kept.append(chunk.model_copy(update={"text": "".join([*pieces, text[at:]])}))
    return kept


def _depth(reference: str, document: DoclingDocument) -> int:
    """How many list items a list item is nested under; 0 for anything else."""
    node = _node(reference, document)
    if not isinstance(node, ListItem):
        return 0
    depth = 0
    while node.parent is not None:
        node = node.parent.resolve(document)
        depth += isinstance(node, ListItem)
    return depth


#: What a lead-in is: a paragraph, as the converter labels one.
_PROSE = frozenset({DocItemLabel.TEXT, DocItemLabel.PARAGRAPH})

#: What a lead-in ends on: the colon, in the Latin and the full-width forms.
_LEAD_IN = (":", "：")
# What a lead-in introduces: the chunker cuts a long list or table into pieces.
_LISTED = frozenset({DocItemLabel.LIST_ITEM, DocItemLabel.TABLE})


def lead_ins_kept(
    chunks: list[DocChunk], chunker: HybridChunker, document: DoclingDocument
) -> list[DocChunk]:
    """Keeps a list or table with the sentence that introduces it.

    The chunker closes a chunk wherever the token budget runs out, which can
    be right after a lead-in ending in ":" and before the list it introduces;
    every item of that list then reads as a rule of its own. When a chunk
    ends on such a lead-in and the next, under the same headings, opens with
    a list item, the lead-in moves into the next chunk if that still fits
    the budget, and otherwise is appended to its heading trail, which both
    model stages are shown. A list longer than one chunk goes on carrying
    it: each chunk after, under the same headings, that opens with a list
    item and follows a chunk ending on one has the lead-in of that list
    appended to its trail, wherever the lead-in itself was kept. A lead-in
    followed by a sub-heading introduces what the sub-heading opens: it
    moves into that chunk the same way, and heads every chunk after that
    opens with a list item under a heading below it, until a heading at or
    above its own depth ends what it introduces. A table is kept like a
    list: the lead-in "for customers under 25:" scopes every piece of it.

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
    # The lead-in of the list the last chunk kept closes on, and the trail
    # it was written under, which bounds what it introduces.
    carried: str | None = None
    under: list[str] = []
    for index, chunk in enumerate(chunks):
        same = bool(kept) and trails[index - 1] == trails[index]
        deeper = bool(kept) and _below(trails[index], trails[index - 1])
        continued = same and _opens_a_list(chunk)
        lead = _lead_in(kept[-1], document) if continued or deeper else None
        given = None
        origin = trails[index] or []
        if lead is not None:
            origin = trails[index - 1] or []
            item, text = lead
            given = text
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
                chunk = _headed(chunk, text)
        elif (
            carried is not None
            and _opens_a_list(chunk)
            and (trails[index] or [])[: len(under)] == under
        ):
            given = carried
            chunk = _headed(chunk, carried)
            origin = under
        carried = _introduced(chunk, document, given)
        under = (
            origin if carried is not None and carried == given else trails[index] or []
        )
        kept.append(chunk)
    return kept


def _one_language(chunks: list[DocChunk], document: DoclingDocument) -> list[DocChunk]:
    """Ends a chunk where its prose changes language.

    Merging undersized peers joins neighbours without regard to language, and
    a passage is read as one language, so a bilingual page printing each
    paragraph beside its translation would lose one language's vocabulary. A
    paragraph too short to detect or not surely one language, and any other
    item, stays with the run it follows.

    Args:
        chunks: What the chunker returned, in order.
        document: The converted document, which holds each item's text.

    Returns:
        The chunks, each holding one language; a chunk of one language is
        returned as it was.
    """
    split: list[DocChunk] = []
    for chunk in chunks:
        items = chunk.meta.doc_items
        spoken = [
            detect_surely(text) if (text := _prose_text(item, document)) else None
            for item in items
        ]
        first = next((code for code in spoken if code), None)
        starts, current = [], first
        for index, code in enumerate(spoken):
            if code and code != current:
                starts.append(index)
                current = code
        if not starts:
            split.append(chunk)
            continue
        # Each run's text opens where its first item's text is found.
        cursor, offsets = 0, []
        for index, item in enumerate(items):
            text = _prose_text(item, document)
            found = chunk.text.find(text, cursor) if text is not None else -1
            if text is not None and found >= 0:
                cursor = found + len(text)
                if index in starts:
                    offsets.append(found)
        if len(offsets) != len(starts):
            split.append(chunk)
            continue
        bounds = [0, *starts, len(items)]
        cuts = [0, *offsets, len(chunk.text)]
        for part in range(len(bounds) - 1):
            text = chunk.text[cuts[part] : cuts[part + 1]].strip()
            if text:
                split.append(
                    chunk.model_copy(
                        update={
                            "text": text,
                            "meta": chunk.meta.model_copy(
                                update={
                                    "doc_items": items[bounds[part] : bounds[part + 1]]
                                }
                            ),
                        }
                    )
                )
    return split


def _prose_text(item: DocItem, document: DoclingDocument) -> str | None:
    """The text of a prose item, or None for any other item.

    The chunker hands its items over as bare copies, so the text is read
    off the document the reference names.
    """
    if item.label not in _PROSE:
        return None
    found = RefItem.model_validate({"$ref": item.self_ref}).resolve(document)
    return found.text.strip() if isinstance(found, TextItem) else None


def _below(trail: list[str] | None, above: list[str] | None) -> bool:
    """Whether a heading trail lies under another: it extends it."""
    trail, above = trail or [], above or []
    return len(trail) > len(above) and trail[: len(above)] == above


def _headed(chunk: DocChunk, text: str) -> DocChunk:
    """A chunk with one more entry at the end of its heading trail."""
    return chunk.model_copy(
        update={
            "meta": chunk.meta.model_copy(
                update={"headings": [*(chunk.meta.headings or []), text]}
            )
        }
    )


def _lead_text(item: DocItem, document: DoclingDocument) -> str | None:
    """The text of a paragraph ending in ":", or None for any other item."""
    text = _prose_text(item, document)
    return text if text and text.endswith(_LEAD_IN) else None


def _lead_in(chunk: DocChunk, document: DoclingDocument) -> tuple[DocItem, str] | None:
    """The paragraph ending in ":" a chunk closes on, and its text, or None."""
    last = chunk.meta.doc_items[-1] if chunk.meta.doc_items else None
    text = None if last is None else _lead_text(last, document)
    if last is not None and text is not None and chunk.text.rstrip().endswith(text):
        return last, text
    return None


def _introduced(
    chunk: DocChunk, document: DoclingDocument, given: str | None
) -> str | None:
    """The lead-in of the list or table a chunk closes on, or None.

    The paragraph ending in ":" right before the list items or tables the chunk
    ends on, or, where it is those from the top, `given`: the lead-in it was
    handed. None where it does not end on one, or where it has no lead-in.
    """
    items = chunk.meta.doc_items
    run = len(items)
    while run and items[run - 1].label in _LISTED:
        run -= 1
    if run == len(items):
        return None
    return given if run == 0 else _lead_text(items[run - 1], document)


def _opens_a_list(chunk: DocChunk) -> bool:
    """Reports whether a chunk's first item is a list item or a table."""
    return bool(chunk.meta.doc_items) and (chunk.meta.doc_items[0].label in _LISTED)


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


def _cell_box(table, rows: list[tuple[list, dict | None]]) -> list[tuple[int, list]]:
    """Locates the rows of a table that one passage renders, page by page.

    Header cells are left out although the piece repeats them.

    Args:
        table: The resolved table item.
        rows: Its rows, each paired with the line rendering it or None.

    Returns:
        Each page and the cell boxes on it, in page order; empty when the
        table has no page or the rows no box.
    """
    pages = _row_pages(table)
    by_page: dict[int, list] = {}
    for cells, line in rows:
        if line is None:
            continue
        for cell in cells:
            if cell.bbox is not None and cell.start_row_offset_idx in pages:
                by_page.setdefault(pages[cell.start_row_offset_idx], []).append(
                    cell.bbox
                )
    return sorted(by_page.items())


def _row_pages(table) -> dict[int, int]:
    """The page each row of a table is printed on, by row index.

    A table parsing joined across a page holds one place per piece, in
    order, and each cell's box is on its own piece's page: walked in row
    order, a row whose top lies above the top of the row before it opens
    the next piece. A table in two columns of one page holds both places
    on that page.
    """
    places = [prov.page_no for prov in table.prov or []]
    if not places:
        return {}
    tops: dict[int, float] = {}
    for cell in table.data.table_cells:
        if (box := cell.bbox) is not None:
            row = cell.start_row_offset_idx
            tops[row] = min(box.t, tops[row]) if row in tops else box.t
    pages: dict[int, int] = {}
    piece, above = 0, None
    for row, top in sorted(tops.items()):
        if above is not None and top < above:
            piece = min(piece + 1, len(places) - 1)
        pages[row], above = places[piece], top
    return pages


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
            for page_no, boxes in placed:
                by_page.setdefault(page_no, []).extend(boxes)
            if placed:
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
