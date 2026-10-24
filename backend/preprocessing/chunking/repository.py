"""Database access for the chunking service."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import ClassVar, cast

from sqlalchemy import Table, bindparam, delete, func, insert, select, update
from sqlalchemy.orm import InstrumentedAttribute

from database.qa_generator import Document, Fact, FactPassage, Passage, Status
from database.qa_generator.repository import Repository, matching
from preprocessing.chunking.models import (
    Chunk,
    Chunking,
    ClaimedDocument,
    PassageDetail,
    StoredPassage,
)
from settings.runs import run_id
from stages import Columns, RowQueue
from telemetry.evaluations import current_ids

#: The next document to chunk. This stage's own column and nothing else: what
#: keeps an unparsed document out of the queue is `ready` below, applied when
#: a row is queued rather than when one is claimed.
_NEXT_PENDING = (
    select(Document.sha256)
    .where(Document.chunk_status == Status.PENDING)
    .order_by(Document.sha256)
    .with_for_update(skip_locked=True)
    .limit(1)
    .scalar_subquery()
)

#: Which columns the search box looks in, by the name the API accepts.
SEARCH_FIELDS = {
    "text": (Passage.text,),
    "section": (Passage.section_path,),
    "both": (Passage.text, Passage.section_path),
}

DEFAULT_FIELD = "text"

#: The passages table itself, for the bulk update a re-read writes.
_PASSAGES = cast("Table", Passage.__table__)
_FACTS = cast("Table", Fact.__table__)


def _filtered(query, document, search, block_type, field):
    """Applies the document, text and type filters to a passage query."""
    if document:
        query = query.where(Passage.doc_sha256 == document)
    if search:
        query = query.where(
            matching(
                search, *SEARCH_FIELDS.get(field or "", SEARCH_FIELDS[DEFAULT_FIELD])
            )
        )
    if block_type:
        query = query.where(Passage.block_type == block_type)
    return query


class ChunkQueue(RowQueue):
    """Reads the chunking queue and records what became of each document."""

    columns = Columns(
        entity=Document,
        key=Document.sha256,
        status=Document.chunk_status,
        error=Document.chunk_error,
        claimed_at=Document.chunk_claimed_at,
        trigger=Document.chunk_trigger,
    )
    #: The narrowings this stage accepts.
    scopes: ClassVar[dict[str, InstrumentedAttribute]] = {"document": Document.sha256}
    done = Status.CHUNKED
    next_pending = _NEXT_PENDING
    #: A document with no parsed form has nothing to chunk. The only stage
    #: that declares this, because it is the only one queueing over rows it
    #: did not create: a passage exists because chunking made it, but a
    #: document exists because somebody uploaded one, and `start` over a
    #: corpus half way through parsing used to queue the other half and fail
    #: every row of it on the missing object.
    ready = Document.parse_status == Status.PARSED

    def claim(self) -> ClaimedDocument | None:
        """Takes the next unchunked document off the queue.

        Returns:
            The claimed document, or None when the queue is empty.
        """
        claimed = self._claim(Document.sha256, Document.language)
        if claimed is None:
            return None
        return ClaimedDocument(sha256=claimed.sha256, language=claimed.language)

    def replace(self, sha256: str, chunking: Chunking) -> int:
        """Replaces a document's passages with a new set, then finishes it.

        A stored passage the new set repeats - the same text, heading trail,
        sentences and cell grid - is kept rather than replaced: it keeps its
        id, and so the facts, topic memberships and embedding resting on it,
        and takes the new one's ordinal, pages and every other column in
        place. So a re-chunk after a parsing fix rebuilds only the passages
        the fix changed. Two passages repeated alike pair off in order.

        One transaction: the passages, the oversized count and the status
        land together. The delete of every other stored passage cascades to
        the facts drawn from it and to the topic memberships it held.

        Args:
            sha256: The document's digest.
            chunking: What the builder produced.

        Returns:
            Passages stored.
        """
        chunks: list[Chunk] = chunking.passages
        trace_id, span_id = current_ids()
        run = {
            "run_id": run_id(),
            "trace_id": trace_id or None,
            "span_id": span_id or None,
        }
        with self._session.begin() as session:
            stored = session.execute(
                select(
                    Passage.id,
                    Passage.ordinal,
                    Passage.text,
                    Passage.section_path,
                    Passage.sentences,
                    Passage.table_cells,
                )
                .where(Passage.doc_sha256 == sha256)
                .order_by(Passage.ordinal)
            ).all()
            held: dict[tuple, list[int]] = defaultdict(list)
            for row in stored:
                held[
                    _identity(
                        row.text, row.section_path, row.sentences, row.table_cells
                    )
                ].append(row.id)
            kept: dict[int, Chunk] = {}
            added: list[Chunk] = []
            for chunk in chunks:
                twins = held[
                    _identity(
                        chunk.text,
                        chunk.section_path,
                        chunk.sentences or None,
                        chunk.table_cells or None,
                    )
                ]
                if twins:
                    kept[twins.pop(0)] = chunk
                else:
                    added.append(chunk)
            gone = [row.id for row in stored if row.id not in kept]
            if gone:
                session.execute(delete(Passage).where(Passage.id.in_(gone)))
            if kept:
                # (doc_sha256, ordinal) is unique and Postgres checks it row by
                # row, so every kept passage first steps past any ordinal held
                # before or after, then takes its own.
                past = max([row.ordinal for row in stored] + [len(chunks)])
                renumbered = update(_PASSAGES).where(_PASSAGES.c.id == bindparam("row"))
                session.execute(
                    renumbered,
                    [
                        {"row": passage_id, "ordinal": past + chunk.ordinal}
                        for passage_id, chunk in kept.items()
                    ],
                )
                session.execute(
                    renumbered,
                    [
                        {"row": passage_id, **run, **_columns(chunk)}
                        for passage_id, chunk in kept.items()
                    ],
                )
            if added:
                session.execute(
                    insert(Passage),
                    [
                        {"doc_sha256": sha256, **run, **_columns(chunk)}
                        for chunk in added
                    ],
                )
            self._finish(sha256, session=session, oversized=chunking.oversized)
        return len(chunks)

    def counts(self) -> dict[str, int]:
        """Reports what this service owns, for the status panel."""
        with self._session() as session:
            passages = session.scalar(select(func.count()).select_from(Passage))
        return {**self.counts_by_status(), "passages": passages}


def _identity(
    text: str,
    section_path: str | None,
    sentences: list[dict] | None,
    table_cells: list[dict] | None,
) -> tuple:
    """What a fact on a passage was drawn from and cites, comparably.

    The sentences and the cell grid beside the text and the trail: a fact
    cites a sentence by index and a table row by its line, so a passage
    whose text stays but whose boundaries moved is a new one.
    """
    return (
        text,
        section_path,
        json.dumps(sentences, sort_keys=True),
        json.dumps(table_cells, sort_keys=True),
    )


def _columns(chunk: Chunk) -> dict:
    """The columns a passage takes from the chunk it was cut as."""
    return {
        "ordinal": chunk.ordinal,
        "text": chunk.text,
        "language": chunk.language,
        "sentences": chunk.sentences or None,
        "lemmas": chunk.lemmas,
        "page_from": chunk.page_from,
        "page_to": chunk.page_to,
        "section_path": chunk.section_path,
        "block_type": chunk.block_type,
        "doc_item_refs": chunk.doc_item_refs,
        "bbox": chunk.bbox or None,
        "table_cells": chunk.table_cells or None,
    }


class PassageCatalog(Repository):
    """Reads back the passages chunking produced.

    Separate from the queue: the API serves these and never claims a row.
    """

    def texts(self, within=None) -> list[tuple[int, str, str | None, bool]]:
        """Reads every passage's id, text, document's language and table flag.

        The document's language and not the passage's: it is the fallback a
        re-read applies, and what a table passage takes. Joined to the
        document so `--only document=` narrows here too.

        Args:
            within: A condition narrowing which passages, or None for all.

        Returns:
            One (id, text, document language, holds a table) per passage.
        """
        query = (
            select(
                Passage.id,
                Passage.text,
                Document.language,
                Passage.table_cells.is_not(None).label("table"),
            )
            .join(Document, Document.sha256 == Passage.doc_sha256)
            .order_by(Document.language, Passage.id)
        )
        if within is not None:
            query = query.where(within)
        with self._session() as session:
            return [
                (row.id, row.text, row.language, row.table)
                for row in session.execute(query)
            ]

    def languages(self, within=None) -> dict[int, str | None]:
        """What each passage's own language column says now.

        The passage's, where `texts` reads the document's. A re-read that
        moves one is what leaves `sentences` behind: those offsets and the
        predicate count on each were produced by the pipeline the passage
        USED to be read under, and this is what lets the caller say so.

        Args:
            within: A condition narrowing which passages, or None for all.

        Returns:
            One entry per passage, the language or None.
        """
        query = select(Passage.id, Passage.language).join(
            Document, Document.sha256 == Passage.doc_sha256
        )
        if within is not None:
            query = query.where(within)
        with self._session() as session:
            return {row.id: row.language for row in session.execute(query)}

    def revocabulary(self, read: list[tuple[int, str | None, list[str]]]) -> int:
        """Replaces the stored language and lemmas, and nothing else.

        Sentence offsets are left alone: a fact cites one by index. The
        language of each fact that opens on a moved passage moves with it, to
        what the extraction store would write now: the passage's, and its
        document's where the passage names none. The dedup probe filters on
        that copy.

        Args:
            read: One (passage id, language, lemmas) per passage.

        Returns:
            Passages rewritten.
        """
        if not read:
            return 0
        with self._session.begin() as session:
            # The table rather than the entity: an executemany against the
            # mapped class is read as an ORM bulk update by primary key, which
            # wants the key among the values being set.
            session.execute(
                update(_PASSAGES).where(_PASSAGES.c.id == bindparam("row")),
                [
                    {"row": passage_id, "language": language, "lemmas": terms}
                    for passage_id, language, terms in read
                ],
            )
            session.execute(
                update(_FACTS)
                .where(
                    _FACTS.c.id.in_(
                        select(FactPassage.fact_id).where(
                            FactPassage.position == 0,
                            FactPassage.passage_id == bindparam("row"),
                        )
                    )
                )
                .values(
                    language=func.coalesce(
                        bindparam("language", type_=Passage.language.type),
                        select(Document.language)
                        .where(
                            Document.sha256 == Passage.doc_sha256,
                            Passage.id == bindparam("row"),
                        )
                        .scalar_subquery(),
                    )
                ),
                [
                    {"row": passage_id, "language": language}
                    for passage_id, language, _ in read
                ],
            )
        return len(read)

    def block_types(self) -> list[str]:
        """Lists the block types actually present, for a filter to offer."""
        with self._session() as session:
            return list(
                session.scalars(
                    select(Passage.block_type)
                    .where(Passage.block_type.is_not(None))
                    .distinct()
                    .order_by(Passage.block_type)
                ).all()
            )

    def page(
        self,
        document: str | None = None,
        limit: int = 100,
        offset: int = 0,
        search: str | None = None,
        block_type: str | None = None,
        field: str | None = None,
    ) -> tuple[int, list[StoredPassage]]:
        """Reads one page of passages and the total behind it.

        Args:
            document: A digest to narrow to, or None for the corpus.
            limit: Rows to return.
            offset: Rows to skip.
            search: Text to match.
            block_type: A block type to narrow to.
            field: Which columns `search` looks in, a key of SEARCH_FIELDS.

        Returns:
            The total matching the filters, and the requested page.
        """
        narrowed = _filtered(
            select(Passage).order_by(Passage.doc_sha256, Passage.ordinal),
            document,
            search,
            block_type,
            field,
        )
        counting = _filtered(
            select(func.count()).select_from(Passage),
            document,
            search,
            block_type,
            field,
        )
        with self._session() as session:
            total = session.scalar(counting) or 0
            rows = session.scalars(narrowed.limit(limit).offset(offset)).all()
        return total, [_stored(row) for row in rows]

    def passage(self, passage_id: int) -> PassageDetail | None:
        """Reads one passage in full, its cell grids and sentences included.

        Args:
            passage_id: The passage's row id.

        Returns:
            The passage, or None if no passage has that id.
        """
        with self._session() as session:
            row = session.get(Passage, passage_id)
            if row is None:
                return None
            return PassageDetail(
                passage=_stored(row),
                table_cells=row.table_cells or [],
                sentences=row.sentences or [],
                extract_status=row.extract_status,
                extract_error=row.extract_error,
            )


def _stored(row: Passage) -> StoredPassage:
    """Reads one passage row into the shape the API publishes."""
    return StoredPassage(
        id=row.id,
        doc_sha256=row.doc_sha256,
        ordinal=row.ordinal,
        text=row.text,
        page_from=row.page_from,
        page_to=row.page_to,
        section_path=row.section_path,
        block_type=row.block_type,
        language=row.language,
        doc_item_refs=row.doc_item_refs or [],
        bbox=row.bbox or [],
        table_count=len(row.table_cells or []),
        sentence_count=len(row.sentences or []),
    )
