"""Database access for the extraction service."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Collection, Iterator
from contextlib import contextmanager
from itertools import groupby
from typing import Any, ClassVar, cast

import numpy as np
from sqlalchemy import (
    ARRAY,
    BigInteger,
    ColumnElement,
    Integer,
    Select,
    Table,
    and_,
    any_,
    bindparam,
    delete,
    func,
    insert,
    or_,
    select,
    text,
    true,
    update,
)
from sqlalchemy.orm import InstrumentedAttribute, aliased

from database.qa_generator import (
    Document,
    Fact,
    FactKind,
    FactPassage,
    Passage,
    Question,
    QuestionFact,
    QuestionStatus,
    Rejection,
    Status,
    engine,
)
from database.qa_generator.passage_topics import DOMINANT
from database.qa_generator.repository import Repository, matching
from extraction.models import (
    REPAIRED,
    WRITTEN,
    CandidateFact,
    CheckedFact,
    Cited,
    FactQuality,
    FactSource,
    PassageToExtract,
    Refused,
    StoredFact,
    Twin,
)
from nlp.models import Sentence
from settings.runs import run_id
from stages import Columns, RowQueue
from telemetry.evaluations import current_ids

#: The next passage to read. This stage's own column and nothing else: it
#: does not join documents to ask what chunking did. FOR UPDATE SKIP LOCKED
#: lets a second worker take the following row.
_NEXT_PENDING = (
    select(Passage.id)
    .where(Passage.extract_status == Status.PENDING)
    .order_by(Passage.id)
    .with_for_update(skip_locked=True)
    .limit(1)
    .scalar_subquery()
)

#: What `extract_error` opens with on a passage that finished without its
#: digest, followed by the reason. The service writes it and `DigestQueue`
#: finds the passages by it.
DIGEST_FAILED = "digest failed: "

#: Which columns the search box looks in, by the name the API accepts.
SEARCH_FIELDS = {
    "statement": (Fact.statement,),
    "evidence": (Fact.evidence_text,),
    "both": (Fact.statement, Fact.evidence_text),
}

DEFAULT_FIELD = "both"

#: How many facts to hold at once while re-judging them.
_BATCH = 500

#: How many of the nearest facts a dedup probe reads for its caller to
#: choose among: the nearest may name other numbers where one a little
#: further off names the candidate's own.
_PROBED = 5

#: Lets the dedup probe's HNSW scan keep going past the rows its filters
#: drop. The filters on language, kind and the passage read again apply over
#: what one scan returns, `hnsw.ef_search` rows, so a fact behind that many
#: closer facts of another language or kind was otherwise not found at all.
#: Strict order, because the caller takes the closest it would call a twin.
#: Local to the transaction. pgvector 0.8 or later.
_PAST_THE_FILTERS = text("SET LOCAL hnsw.iterative_scan = strict_order")

#: The advisory lock a dedup replay holds, so two workers' replays never
#: interleave. Beside the one a pipeline launch holds, and not that one.
_REPLAYING = 0x5155_4444

#: The facts table itself, for the bulk update a re-judgement writes.
_FACTS = cast("Table", Fact.__table__)

#: The link table itself, for the same reason.
_LINKS = cast("Table", FactPassage.__table__)

#: The passages table itself, for the bulk update the backfill writes.
_PASSAGES = cast("Table", Passage.__table__)

#: What one passage of a bridge group is read as. The same columns `claim`
#: reads, so a group and a queued passage are the same object.
_PASSAGE_COLUMNS = (
    Passage.id,
    Passage.text,
    Passage.section_path,
    Passage.block_type,
    Passage.language,
    Passage.sentences,
    Passage.table_cells,
    Passage.doc_sha256,
    Passage.embedding,
)


def _sentences(text: str, stored: list[dict] | None) -> list[Sentence]:
    """Rebuilds a passage's numbered sentences from the stored offsets."""
    return [
        Sentence(
            index=entry["i"],
            start=entry["start"],
            end=entry["end"],
            text=text[entry["start"] : entry["end"]],
            predicates=entry.get("predicates", 0),
        )
        for entry in stored or []
    ]


def _passage(row, language: str | None, title: str | None = None) -> PassageToExtract:
    """Reads one row of `_PASSAGE_COLUMNS` as a passage to extract from.

    Args:
        row: The selected columns.
        language: The document's language, which is the fallback.
        title: The document's title, or None where it has none.

    Returns:
        The passage, reading in its own language where it has one. Chunking
        detects the language per passage and segmented this one under it, so
        the document's label would judge a statement with one pipeline
        against sentence counts another produced. One file carries a German
        report and its English summary, which is what the column is for.
    """
    return PassageToExtract(
        id=row.id,
        text=row.text,
        section_path=row.section_path,
        block_type=row.block_type,
        language=row.language or language,
        sentences=_sentences(row.text, row.sentences),
        table_cells=row.table_cells or [],
        doc_sha256=row.doc_sha256,
        embedding=(
            np.asarray(row.embedding, dtype=np.float32)
            if row.embedding is not None
            else None
        ),
        title=title,
    )


#: The link a listing is placed and ordered by: the passage the fact opens
#: on. Aliased, because the document filter reaches the table again to ask
#: about every other passage the fact rests on.
_OPENS = aliased(FactPassage)


def _topics(within) -> Select:
    """The topics holding a passage the condition selects."""
    return (
        select(DOMINANT.c.topic_id)
        .join(Passage, Passage.id == DOMINANT.c.passage_id)
        .where(within)
    )


def _resting(condition) -> ColumnElement[bool]:
    """Matches a fact resting on any passage the condition selects.

    Any rather than the one it opens on: a bridge across two documents
    belongs to both, and narrowing to the second is asking for the facts its
    passages support. Written as a subquery on the fact rather than as a join
    so the narrowing selects facts whole - joining it would drop the half of
    a bridge that sits outside the narrowing.
    """
    return Fact.id.in_(
        select(FactPassage.fact_id)
        .join(Passage, Passage.id == FactPassage.passage_id)
        .where(condition)
    )


def _head() -> ColumnElement[int]:
    """The passage that headed a bridge's link.

    Its reading names it; a bridge read before the reading did is taken to be
    headed by the passage it opens on, which a reference link always is.
    """
    return func.coalesce(
        Fact.bridge["head"].as_integer(),
        select(FactPassage.passage_id)
        .where(FactPassage.fact_id == Fact.id, FactPassage.position == 0)
        .scalar_subquery(),
    )


def _bridges(within) -> Select:
    """The bridge facts a pass narrowed by `within` replaces.

    Every bridge when `within` is None. Otherwise the bridges headed by a
    passage of a topic holding a selected passage: those are the heads a
    narrowed pass reads again, so those are the ones it can write back. A
    bridge headed elsewhere stays, wherever it opens and however its partner
    is placed, because the pass would not offer it again; one gone stale is
    removed with the passage whose text changed, not by this.
    """
    chosen = select(Fact.id).where(Fact.kind == FactKind.BRIDGE)
    if within is None:
        return chosen
    return chosen.where(
        _head().in_(
            select(DOMINANT.c.passage_id).where(
                DOMINANT.c.topic_id.in_(_topics(within))
            )
        )
    )


def _filtered(query, document, search, method, field, kind=None):
    """Applies the document, text, method and kind filters to a fact query.

    One place, so a listing and its count cannot disagree about what they are
    looking at. The query must already be joined by :func:`_joined`.
    """
    if document:
        query = query.where(_resting(Passage.doc_sha256 == document))
    if search:
        query = query.where(
            matching(
                search, *SEARCH_FIELDS.get(field or "", SEARCH_FIELDS[DEFAULT_FIELD])
            )
        )
    if method:
        query = query.where(Fact.extraction_method == method)
    if kind:
        query = query.where(Fact.kind == kind)
    return query


def _joined(query: Select) -> Select:
    """Joins the passage a fact is ordered by: the one it opens on.

    One row per fact, not one per passage it rests on: a listing that
    multiplied a bridge by its passages would page through it twice.
    """
    return (
        query.select_from(Fact)
        .join(_OPENS, (_OPENS.fact_id == Fact.id) & (_OPENS.position == 0))
        .join(Passage, Passage.id == _OPENS.passage_id)
    )


#: One fact's passages, in the order the model was shown them. Read for the
#: page of facts a listing returned rather than joined into it, which would
#: give a bridge one row per passage.
_SOURCES = (
    select(
        FactPassage.fact_id,
        FactPassage.passage_id,
        FactPassage.position,
        Passage.doc_sha256,
        Passage.ordinal,
        Passage.page_from,
    )
    .select_from(FactPassage)
    .join(Passage, Passage.id == FactPassage.passage_id)
    .order_by(FactPassage.fact_id, FactPassage.position)
)


def _nearest_fact(
    session,
    embedding: list[float],
    excluding: int | None,
    language: str | None,
    kind: str | None,
    alike: Callable[[Twin], bool] | None = None,
) -> Twin | None:
    """The validated passage fact closest to this vector, or None.

    Over the whole corpus, which is what dedup wants: a duplicate written
    from another document is still a duplicate.

    `excluding` is a passage being read again: a fact citing it and no
    other passage is one its `store` replaces, so it is no twin.

    `language` and `kind` narrow it to the candidate's own, None to any.
    A fact's language is the one the passage it opens on was read in, kept
    on the fact itself so the narrowing is a filter on the index scan rather
    than a join the planner runs first. A
    translation is its own language's fact, and a summary or an outline
    that repeats an atomic fact is caught beside it in its own passage:
    across passages a digest and a claim are two kinds of thing.

    `alike` is what the caller would take as a twin, None for any: the
    closest of the `_PROBED` nearest it takes. The dedup gate turns down a
    fact naming other numbers, and taking the nearest alone would let a
    nearer fee of another amount hide the one that repeats this one.
    """
    distance = Fact.embedding.cosine_distance(embedding)
    query = (
        select(Fact.id, Fact.statement, distance.label("far"))
        .where(
            Fact.validated,
            Fact.embedding.is_not(None),
            Fact.kind != FactKind.BRIDGE,
        )
        .order_by(distance)
        .limit(_PROBED)
    )
    if language is not None:
        query = query.where(Fact.language == language)
    if kind is not None:
        query = query.where(Fact.kind == kind)
    if excluding is not None:
        query = query.where(
            Fact.id.not_in(
                select(FactPassage.fact_id)
                .where(
                    FactPassage.fact_id.in_(
                        select(FactPassage.fact_id).where(
                            FactPassage.passage_id == excluding
                        )
                    )
                )
                .group_by(FactPassage.fact_id)
                .having(func.count() == 1)
            )
        )
    session.execute(_PAST_THE_FILTERS)
    for found in session.execute(query):
        # pgvector answers in cosine distance; the gate reads likeness.
        twin = Twin(
            fact_id=found.id,
            statement=found.statement,
            similarity=1.0 - float(found.far),
        )
        if alike is None or alike(twin):
            return twin
    return None


def _room(session, cap: int, passages: Select):
    """Each passage's room under `cap`, as a table, or None for none.

    Read off each passage in Python, through `PassageToExtract.room`, so the
    cap a recap applies and the one a passage in flight is held to are one
    reading rather than two that could drift.

    Bound as two arrays and unnested, not as a VALUES row per passage: a
    statement binds at most 65,535 parameters, which a pair per passage
    outgrows on a corpus of 32,768.
    """
    ids: list[int] = []
    rooms: list[int | None] = []
    for row in session.execute(
        select(Passage.id, Passage.text, Passage.sentences).where(
            Passage.id.in_(passages)
        )
    ):
        ids.append(row.id)
        rooms.append(
            PassageToExtract(
                id=row.id,
                text=row.text,
                section_path=None,
                block_type=None,
                language=None,
                sentences=_sentences(row.text, row.sentences),
            ).room(cap)
        )
    if not ids:
        return None
    return select(
        func.unnest(bindparam("ids", ids, type_=ARRAY(BigInteger))).label("passage_id"),
        func.unnest(bindparam("rooms", rooms, type_=ARRAY(Integer))).label("room"),
    ).subquery("room")


class PassageQueue(RowQueue):
    """Reads the extraction queue and records what became of each passage.

    Holds the settings version, which every fact it writes records. Built
    without one, it writes NULL.
    """

    columns = Columns(
        entity=Passage,
        key=Passage.id,
        status=Passage.extract_status,
        error=Passage.extract_error,
        claimed_at=Passage.extract_claimed_at,
        trigger=Passage.extract_trigger,
    )
    #: This stage queues over passages, so it answers for one of those and for
    #: every passage of one document - which is the unit a person thinks in.
    scopes: ClassVar[dict[str, InstrumentedAttribute]] = {
        "document": Passage.doc_sha256,
        "passage": Passage.id,
    }
    done = Status.EXTRACTED
    next_pending = _NEXT_PENDING

    def __init__(self, version: str | None = None) -> None:
        """Binds to the session factory, with a settings version."""
        super().__init__()
        self._version = version

    def claim(self) -> PassageToExtract | None:
        """Takes the next unread passage off the queue.

        Returns:
            The passage, or None when nothing is queued.
        """
        claimed = self._claim(*_PASSAGE_COLUMNS, pending=self._next())
        if claimed is None:
            return None
        # Asked here rather than joined into the claim, which is an UPDATE.
        # The language only for a passage too short to tell its own; the
        # title for every passage, which is what the document is about.
        with self._session() as session:
            document = session.execute(
                select(Document.language, Document.title).where(
                    Document.sha256 == claimed.doc_sha256
                )
            ).one_or_none()
        language, title = document if document else (None, None)
        return _passage(claimed, language, title)

    def _next(self) -> Any:
        """The selection of the passage to take, which `claim` reads."""
        return self.next_pending

    def store(
        self,
        passage_id: int,
        facts: list[CheckedFact],
        embedding: list[float] | None = None,
        *,
        note: str | None = None,
        settle: Callable[[list[CheckedFact]], list[CheckedFact]] | None = None,
    ) -> int:
        """Replaces one passage's facts, in one transaction, and finishes it.

        Scoped to the passage, so two workers on two passages of the same
        document do not delete each other's results. Bridge facts resting
        here are left alone: they are the bridge pass's to write and to
        replace.

        With `settle`, the facts are judged again inside the transaction,
        after taking a lock for each language and kind among them. The dedup
        probe before it read what was committed then, and a second drain's
        probe read the same: two passages restating one claim were each told
        no twin existed. The lock puts the drains' stores in a line and the
        second `settle` reads what the first committed, so it refuses the new
        twin. One lock to a (language, kind), so drains writing different
        ones do not wait on each other.

        Args:
            passage_id: The passage that was read.
            facts: Everything it yielded, refused facts included.
            embedding: The passage's own vector, or None to leave the column
                as it is. Written here rather than by chunking because this
                is the worker that has the model loaded.
            note: What the finished passage lacks, kept in its error column:
                `DIGEST_FAILED` and the reason where the digest could not be
                had, so `DigestQueue` can find it.
            settle: Judges the facts again against what is stored now, and
                returns the facts to write. None writes them as given.

        Returns:
            How many facts were written.
        """
        with self._session.begin() as session:
            if settle is not None:
                language = _languages(session, {passage_id}).get(passage_id) or ""
                for kind in sorted({fact.kind for fact in facts if fact.validated}):
                    session.execute(
                        select(
                            func.pg_advisory_xact_lock(
                                func.hashtext(f"{language}:{kind}")
                            )
                        )
                    )
                facts = settle(facts)
            # The citations, not the facts: the orphan trigger deletes a fact
            # left citing nothing, and keeps one another passage still cites.
            session.execute(
                delete(FactPassage).where(
                    FactPassage.passage_id == passage_id,
                    FactPassage.fact_id.in_(
                        select(Fact.id).where(Fact.kind != FactKind.BRIDGE)
                    ),
                )
            )
            _write(session, facts, self._version)
            if embedding is not None:
                session.execute(
                    update(Passage)
                    .where(Passage.id == passage_id)
                    .values(embedding=embedding)
                )
            self._finish(passage_id, session=session, note=note)
        return len(facts)

    def cited(self, passage_id: int) -> bool:
        """Whether a fact other than a bridge cites this passage already.

        What its `store` replaces: a passage read again, whose facts a
        refusal elsewhere may name as its twin.
        """
        with self._session() as session:
            return bool(
                session.scalar(
                    select(
                        select(FactPassage.fact_id)
                        .join(Fact, Fact.id == FactPassage.fact_id)
                        .where(
                            FactPassage.passage_id == passage_id,
                            Fact.kind != FactKind.BRIDGE,
                        )
                        .exists()
                    )
                )
            )

    def nearest_fact(
        self,
        embedding: list[float],
        excluding: int | None = None,
        language: str | None = None,
        kind: str | None = None,
        alike: Callable[[Twin], bool] | None = None,
    ) -> Twin | None:
        """The validated passage fact closest to this vector, or None.

        See `_nearest_fact`, which the dedup replay probes through as well.
        """
        with self._session() as session:
            return _nearest_fact(session, embedding, excluding, language, kind, alike)

    def counts(self) -> dict[str, int]:
        """Reports what this service owns, for the status panel."""
        with self._session() as session:
            total = session.scalar(select(func.count()).select_from(Fact))
            valid = session.scalar(
                select(func.count()).select_from(Fact).where(Fact.validated)
            )
        return {**self.counts_by_status(), "facts": total, "validated": valid}


def _next_undigested(after: int, min_chars: int):
    """The next extracted passage that lacks its digest, past `after`.

    One the extraction left a note on, or one long enough to be worth a digest
    that holds none. Long enough by its stored text, which is what the digest
    floor reads; the claims floor needs the sentences and is the service's.
    """
    has_digest = (
        select(FactPassage.fact_id)
        .join(Fact, Fact.id == FactPassage.fact_id)
        .where(
            FactPassage.passage_id == Passage.id,
            Fact.kind.in_((FactKind.SUMMARY, FactKind.OUTLINE)),
        )
        .exists()
    )
    return (
        select(Passage.id)
        .where(
            Passage.extract_status == Status.EXTRACTED,
            Passage.id > after,
            or_(
                Passage.extract_error.startswith(DIGEST_FAILED),
                and_(func.length(Passage.text) >= min_chars, ~has_digest),
            ),
        )
        .order_by(Passage.id)
        .with_for_update(skip_locked=True)
        .limit(1)
        .scalar_subquery()
    )


class DigestQueue(PassageQueue):
    """The passages that finished extraction without their digest.

    Those the extraction left a note on, and those above the digest's length
    floor that hold none: a floor lowered since they were read reaches them
    here, without reading the passage again and replacing the facts questions
    rest on. Claims an extracted passage rather than a pending one, and each
    passage once per drain: one whose digest fails again keeps its note and is
    not the next claim.
    """

    def __init__(self, version: str | None = None, min_chars: int = 0) -> None:
        """Binds to the session factory, with a settings version.

        Args:
            version: The configuration the digests are written under.
            min_chars: EXTRACTION_DIGEST_MIN_CHARS, the shortest passage a
                digest is looked for on.
        """
        super().__init__(version)
        self._after = 0
        self._min_chars = min_chars

    def _next(self) -> Any:
        """The next passage without a digest, past the last one claimed."""
        return _next_undigested(self._after, self._min_chars)

    def claim(self) -> PassageToExtract | None:
        """Takes the next passage without a digest, in id order."""
        claimed = super().claim()
        if claimed is not None:
            self._after = claimed.id
        return claimed

    def _unclaimed(self) -> dict[Any, Any]:
        """Back to extracted with its note: pending would read it again."""
        return {self.columns.status: Status.EXTRACTED}

    def fail(self, key: int, error: str) -> None:
        """Records a digest that could not be given, and leaves the passage extracted.

        Its atomic facts stand, and so do the questions on them: the reason
        becomes the digest note, which this queue finds by its opening and
        `make extract-retry`, which reads failed passages again, never sees.

        Raises:
            Lost: If another worker has claimed the row since this one did.
        """
        self._release(
            key,
            {
                self.columns.status: Status.EXTRACTED,
                self.columns.error: f"{DIGEST_FAILED}{error}"[:2000],
            },
        )

    def store_digests(
        self, passage_id: int, facts: list[CheckedFact], note: str | None = None
    ) -> int:
        """Replaces one passage's digest, and nothing else, and finishes it.

        The summary and the outline only: the citations of the atomic facts
        stay, so their ids and the questions resting on them do not move.

        Args:
            passage_id: The passage that was digested.
            facts: The digest facts, refused ones included. None when the
                digest could not be had.
            note: What the passage still lacks, as `store` keeps it. None
                when the digest came.

        Returns:
            How many facts were written.
        """
        with self._session.begin() as session:
            session.execute(
                delete(FactPassage).where(
                    FactPassage.passage_id == passage_id,
                    FactPassage.fact_id.in_(
                        select(Fact.id).where(
                            Fact.kind.in_((FactKind.SUMMARY, FactKind.OUTLINE))
                        )
                    ),
                )
            )
            _write(session, facts, self._version)
            self._finish(passage_id, session=session, note=note)
        return len(facts)


def _write(session, facts: list[CheckedFact], version: str | None = None) -> int:
    """Writes facts and the passages each rests on, in the caller's transaction.

    Args:
        session: The open transaction.
        facts: Checked facts of any kind, refused ones included.
        version: The configuration these were extracted under, recorded on
            each of them.

    Returns:
        How many facts were written.
    """
    if not facts:
        return 0
    # sort_by_parameter_order: the links below are matched to the facts by
    # position, so the ids have to come back in the order they went in rather
    # than in whatever order the insert chose.
    languages = _languages(
        session, {fact.citations[0].passage_id for fact in facts if fact.citations}
    )
    ids = session.scalars(
        insert(Fact).returning(Fact.id, sort_by_parameter_order=True),
        [
            _row(
                fact,
                version,
                languages.get(fact.citations[0].passage_id) if fact.citations else None,
            )
            for fact in facts
        ],
    ).all()
    links = [
        {
            "fact_id": fact_id,
            "passage_id": cited.passage_id,
            "position": position,
            "sentence_ids": cited.sentence_ids,
            "evidence_start": cited.start,
            "evidence_end": cited.end,
        }
        for fact_id, fact in zip(ids, facts, strict=True)
        for position, cited in enumerate(fact.citations)
    ]
    if links:
        session.execute(insert(FactPassage), links)
    return len(facts)


def _languages(session, passage_ids: set[int]) -> dict[int, str | None]:
    """The language each of these passages was read in.

    Its own where chunking could tell, and where the passage was too short to
    its document's: the one `claim` hands the extractor, and so the one a
    candidate is probed under.
    """
    if not passage_ids:
        return {}
    return {
        row.id: row.language
        for row in session.execute(
            select(
                Passage.id,
                func.coalesce(Passage.language, Document.language).label("language"),
            )
            .join(Document, Document.sha256 == Passage.doc_sha256)
            .where(Passage.id.in_(passage_ids))
        )
    }


def _row(
    fact: CheckedFact, version: str | None = None, language: str | None = None
) -> dict:
    """Turns one checked fact into the columns the facts table holds."""
    trace_id, span_id = current_ids()
    return {
        "language": language,
        "settings_version": version,
        "run_id": run_id(),
        "trace_id": trace_id or None,
        "span_id": span_id or None,
        "kind": fact.kind,
        "statement": fact.statement,
        "evidence_text": fact.evidence_text,
        "extraction_method": fact.extraction_method,
        "validated": fact.validated,
        "rejection_code": fact.rejection_code,
        "validation_error": fact.validation_error,
        "statement_predicates": fact.statement_predicates,
        "evidence_predicates": fact.evidence_predicates,
        "units_statement": fact.units_statement,
        "units_added": fact.units_added,
        "unresolved_references": fact.unresolved_references,
        "extraction_model": fact.extraction_model,
        "prompt_version": fact.prompt_version,
        "extraction_temperature": fact.extraction_temperature,
        "spacy_model": fact.spacy_model,
        "spacy_version": fact.spacy_version,
        "embedding": fact.embedding,
        "gate_scores": fact.gate_scores or None,
        "confidence": fact.confidence,
        "bridge": fact.bridge,
    }


class FactCatalog(Repository):
    """Reads back the facts extraction produced, and writes the bridges.

    Separate from the queue: the API serves these and never claims a row.

    Holds the settings version for the two operations that write a verdict,
    a bridge pass and a re-judgement. The API builds this without one.
    """

    def __init__(self, version: str | None = None) -> None:
        """Binds to the session factory, with the settings version to record."""
        super().__init__()
        self._version = version

    def by_topic(self, within=None) -> Iterator[tuple[int, list[PassageToExtract]]]:
        """Streams each topic's passages, in document and reading order.

        A passage belongs to the topic it carries most strongly, which is
        what puts two of them in the same group.

        Args:
            within: A condition selecting passages, or None for the corpus.
                Every topic holding one of them is read WHOLE, which is not
                the same as reading the passages it selects. `clear_bridges`
                deletes any bridge resting on a selected passage, and a
                bridge rests on two - so narrowing the read to one document
                would delete the cross-document bridges and then be unable
                to write them again, having kept only one side of each. The
                cross-document bridge is the one worth having.

        Yields:
            One topic's id and its passages.
        """
        query = (
            select(
                *_PASSAGE_COLUMNS,
                # Labelled, because `_PASSAGE_COLUMNS` now carries the
                # passage's own and two `language` keys in one row is one
                # key too few.
                Document.language.label("document_language"),
                Document.title.label("document_title"),
                DOMINANT.c.topic_id,
            )
            .select_from(Passage)
            .join(Document, Document.sha256 == Passage.doc_sha256)
            .join(DOMINANT, DOMINANT.c.passage_id == Passage.id)
            .where(Passage.sentences.is_not(None))
            .order_by(DOMINANT.c.topic_id, Passage.doc_sha256, Passage.ordinal)
        )
        if within is not None:
            query = query.where(DOMINANT.c.topic_id.in_(_topics(within)))

        with self._session() as session:
            for topic_id, rows in groupby(
                session.execute(query), key=lambda row: row.topic_id
            ):
                yield (
                    topic_id,
                    [
                        _passage(row, row.document_language, row.document_title)
                        for row in rows
                    ],
                )

    def recap(self, cap: int | None, reason: str, within=None) -> int:
        """Refuses the atomic facts already stored above the cap.

        And gives back a fact an earlier, lower cap refused that is inside
        this one. None caps nothing and gives back every one.

        The counterpart of `extract-revalidate` and the same bargain: what
        the model wrote is the record of one extraction and is kept; only
        the verdict moves, stamped with the settings it moved under. No model is called, so a corpus extracted before
        EXTRACTION_MIN_OTHER_SHARE existed is re-balanced rather than re-read.

        Ranked exactly as `over_cap` ranks a passage in flight - the facts
        a model wrote, asserting a number, a date or a name first, ties by
        id - and against the room each passage has, as in flight, so a
        passage re-extracted later keeps the same facts this leaves. A fact
        the repair call wrote never competes, and one an earlier recap or
        extraction refused is given back.

        Args:
            cap: The most validated atomic facts one passage may keep. A
                passage stating more sentences and list items keeps that many,
                as `PassageToExtract.room` reads it.
            reason: What to record on the ones refused.
            within: A condition on Passage narrowing which are read, or None.

        Returns:
            How many facts were refused or given back.
        """
        ranked = (
            select(
                Fact.id,
                FactPassage.passage_id,
                func.row_number()
                .over(
                    partition_by=FactPassage.passage_id,
                    order_by=(
                        func.coalesce(func.cardinality(Fact.units_statement), 0) == 0,
                        Fact.id,
                    ),
                )
                .label("rank"),
            )
            .select_from(Fact)
            .join(
                FactPassage,
                (FactPassage.fact_id == Fact.id) & (FactPassage.position == 0),
            )
            .where(
                Fact.kind == FactKind.ATOMIC,
                Fact.validated | (Fact.rejection_code == Rejection.OVER_CAP),
                # As `over_cap` ranks one in flight: a statement composed
                # from a grid does not compete. The cap exists to leave room
                # for the digests, and a table yields none.
                Fact.extraction_method == WRITTEN,
                # As `over_cap` ranks one in flight: a fact the repair call
                # wrote does not compete.
                ~func.coalesce(Fact.prompt_version, "").startswith(REPAIRED),
            )
        )
        if within is not None:
            ranked = ranked.where(_resting(within))
        over = ranked.subquery()
        chosen = select(over.c.id)
        pieces = select(Fact.id).where(
            Fact.rejection_code == Rejection.OVER_CAP,
            func.coalesce(Fact.prompt_version, "").startswith(REPAIRED),
        )
        if within is not None:
            pieces = pieces.where(_resting(within))
        with self._session.begin() as session:
            freed = session.execute(
                update(Fact)
                .where(Fact.id.in_(pieces))
                .values(
                    validated=True,
                    rejection_code=None,
                    validation_error=None,
                    settings_version=self._version,
                )
            ).rowcount
            if cap is None:
                inside = true()
            else:
                room = _room(session, cap, select(over.c.passage_id))
                if room is None:
                    return freed
                chosen = chosen.join(room, room.c.passage_id == over.c.passage_id)
                inside = over.c.rank <= room.c.room
            refused = session.execute(
                update(Fact)
                .where(
                    Fact.validated,
                    Fact.id.in_(chosen.where(~inside)),
                )
                .values(
                    validated=False,
                    rejection_code=Rejection.OVER_CAP,
                    validation_error=reason,
                    settings_version=self._version,
                )
            ).rowcount
            returned = session.execute(
                update(Fact)
                .where(
                    Fact.rejection_code == Rejection.OVER_CAP,
                    Fact.id.in_(chosen.where(inside)),
                )
                .values(
                    validated=True,
                    rejection_code=None,
                    validation_error=None,
                    settings_version=self._version,
                )
            ).rowcount
        return refused + returned + freed

    def nearest_fact(
        self,
        embedding: list[float],
        excluding: int | None = None,
        language: str | None = None,
        kind: str | None = None,
        alike: Callable[[Twin], bool] | None = None,
    ) -> Twin | None:
        """The validated passage fact closest to this vector, as the queue probes."""
        with self._session() as session:
            return _nearest_fact(session, embedding, excluding, language, kind, alike)

    @contextmanager
    def replaying(self) -> Iterator[None]:
        """Holds the dedup replay's lock for as long as the body runs.

        At session level, on a connection held for it, because the replay
        commits in many transactions of its own. A second caller waits for
        the first to let go, and Postgres lets go of a lock whose process
        died holding it.
        """
        with engine().connect() as connection:
            connection.execute(select(func.pg_advisory_lock(_REPLAYING)))
            connection.commit()
            try:
                yield
            finally:
                connection.execute(select(func.pg_advisory_unlock(_REPLAYING)))
                connection.commit()

    def duplicates(self, within=None) -> list[Refused]:
        """Every stored `duplicate` refusal, as the dedup replay re-decides it.

        Read off the passage each was read from, which is its citation at 0,
        and in id order, which is the order they were refused in. Read whole
        rather than streamed: the replay writes between reads.

        Args:
            within: A condition on Passage narrowing which are read, or None.

        Returns:
            The refusals carrying the vector they were refused on.
        """
        conditions = [
            Fact.rejection_code == Rejection.DUPLICATE,
            Fact.embedding.is_not(None),
        ]
        if within is not None:
            conditions.append(_resting(within))
        return self._refusals(*conditions)

    def refused(self, fact_ids: list[int]) -> list[Refused]:
        """Those of these facts stored refused, as a dedup probe reads them.

        What a re-judgement asks of the facts its checks now validate: the
        ones found here were refused by a check when read, and so faced
        neither the dedup gate nor the cap. Of any code, and carrying their
        vector where they were stored with one.

        Args:
            fact_ids: The facts to look up.

        Returns:
            The refused ones, in id order.
        """
        if not fact_ids:
            return []
        return self._refusals(
            Fact.validated.is_(False),
            Fact.id == any_(bindparam("ids", fact_ids, type_=ARRAY(BigInteger))),
        )

    def _refusals(self, *conditions) -> list[Refused]:
        """The refusals these conditions select, read off their citation at 0."""
        query = (
            select(
                Fact.id,
                FactPassage.passage_id,
                func.coalesce(Passage.language, Document.language).label("language"),
                Fact.kind,
                Fact.statement,
                Fact.embedding,
            )
            .select_from(Fact)
            .join(
                FactPassage,
                (FactPassage.fact_id == Fact.id) & (FactPassage.position == 0),
            )
            .join(Passage, Passage.id == FactPassage.passage_id)
            .join(Document, Document.sha256 == Passage.doc_sha256)
            .where(Fact.kind != FactKind.BRIDGE, *conditions)
            .order_by(Fact.id)
        )
        with self._session() as session:
            return [
                Refused(
                    fact_id=row.id,
                    passage_id=row.passage_id,
                    language=row.language,
                    kind=row.kind,
                    statement=row.statement,
                    # As pgvector reads it, which is a list of floats
                    # already, rather than built again element by element.
                    embedding=row.embedding,
                )
                for row in session.execute(query)
            ]

    def kept(self, passage_id: int) -> list[tuple[str, str, list[float]]]:
        """What one passage keeps, as (statement, kind, vector).

        Its validated facts carrying a vector, read through their citation
        at 0, in the order they were written: what `written` holds for a
        passage in flight.
        """
        query = (
            select(Fact.statement, Fact.kind, Fact.embedding)
            .join(
                FactPassage,
                (FactPassage.fact_id == Fact.id) & (FactPassage.position == 0),
            )
            .where(
                FactPassage.passage_id == passage_id,
                Fact.validated,
                Fact.kind != FactKind.BRIDGE,
                Fact.embedding.is_not(None),
            )
            .order_by(Fact.id)
        )
        with self._session() as session:
            return [
                (row.statement, row.kind, [float(one) for one in row.embedding])
                for row in session.execute(query)
            ]

    def give_back(
        self,
        fact_id: int,
        gate_scores: list[dict] | None = None,
        confidence: float | None = None,
    ) -> int:
        """Validates one `duplicate` refusal again, as it was judged when read.

        The verdict moves, stamped with the settings it moved under, as a
        recap stamps one, and so does the dedup reading: the refusal's own
        margin is replaced by the one the caller read against today's bar,
        or cleared. Nothing where the fact is no longer a refusal.

        Args:
            fact_id: The refusal.
            gate_scores: The reading to store, or None for none.
            confidence: Its margin, or None with it.

        Returns:
            How many facts were given back: 1, or 0.
        """
        with self._session.begin() as session:
            return session.execute(
                update(Fact)
                .where(Fact.id == fact_id, Fact.rejection_code == Rejection.DUPLICATE)
                .values(
                    validated=True,
                    rejection_code=None,
                    validation_error=None,
                    settings_version=self._version,
                    gate_scores=gate_scores or None,
                    confidence=confidence,
                )
            ).rowcount

    def unfold(
        self, cited: Callable[[PassageToExtract, list[Sentence]], str], within=None
    ) -> tuple[int, int]:
        """Deletes the citations duplicate refusals folded into their twins.

        A fold is a citation at position 1 or more on a fact other than a
        bridge: `_write` gives such a fact one citation, at 0, and before a
        refusal stopped citing its twin the refusal was the only thing that
        added another. A bridge's later positions are what it rests on.

        Each fact unfolded has its evidence rebuilt from the citation it
        keeps, through `cited`, which is how the checker joins the sentences
        a citation names.

        A fact whose citation at 0 is gone - its own passage was read again
        and it survived on a fold - keeps its folds: taking them out would
        delete it, and the questions resting on it with it.

        Args:
            cited: The text a citation rests on, given its passage and the
                sentences it names.
            within: A condition on Passage narrowing which facts are read, or
                None.

        Returns:
            How many facts were unfolded, and how many were left their folds.
        """
        opening = aliased(FactPassage)
        anchored = (
            select(opening.fact_id)
            .where(opening.fact_id == FactPassage.fact_id, opening.position == 0)
            .exists()
        )
        folded = (
            select(FactPassage.fact_id, anchored.label("anchored"))
            .join(Fact, Fact.id == FactPassage.fact_id)
            .where(Fact.kind != FactKind.BRIDGE, FactPassage.position >= 1)
            .distinct()
        )
        if within is not None:
            folded = folded.where(_resting(within))
        with self._session.begin() as session:
            found = session.execute(folded).all()
            unfolded = sorted(row.fact_id for row in found if row.anchored)
            left = len({row.fact_id for row in found if not row.anchored})
            if not unfolded:
                return 0, left
            session.execute(
                delete(FactPassage).where(
                    FactPassage.fact_id.in_(unfolded), FactPassage.position >= 1
                )
            )
            kept = session.execute(
                select(
                    FactPassage.fact_id,
                    FactPassage.sentence_ids,
                    Passage.id,
                    Passage.text,
                    Passage.sentences,
                )
                .join(Passage, Passage.id == FactPassage.passage_id)
                .where(FactPassage.fact_id.in_(unfolded))
            )
            evidence = []
            for row in kept:
                passage = PassageToExtract(
                    id=row.id,
                    text=row.text,
                    section_path=None,
                    block_type=None,
                    language=None,
                    sentences=_sentences(row.text, row.sentences),
                )
                named = [
                    passage.sentences[at]
                    for at in row.sentence_ids or ()
                    if 0 <= at < len(passage.sentences)
                ]
                evidence.append(
                    {
                        "row": row.fact_id,
                        "evidence_text": cited(passage, named) if named else "",
                    }
                )
            session.execute(
                update(_FACTS).where(_FACTS.c.id == bindparam("row")), evidence
            )
        return len(unfolded), left

    def unembedded(self, limit: int, within=None) -> list[tuple[int, str]]:
        """The next facts carrying no vector, as (id, statement).

        Args:
            limit: How many to read at once.
            within: A condition on Passage narrowing which are read, or None.

        Returns:
            Up to `limit` of them, empty when every fact is embedded.
        """
        query = select(Fact.id, Fact.statement).where(Fact.embedding.is_(None))
        if within is not None:
            query = query.where(_resting(within))
        with self._session() as session:
            return [
                (row.id, row.statement)
                for row in session.execute(query.order_by(Fact.id).limit(limit))
            ]

    def embed_facts(self, vectors: list[tuple[int, list[float]]]) -> int:
        """Writes a vector onto each of the given facts."""
        return self._embed(_FACTS, vectors)

    def unembedded_passages(self, limit: int, within=None) -> list[tuple[int, str]]:
        """The next passages carrying no vector, as (id, text)."""
        query = select(Passage.id, Passage.text).where(Passage.embedding.is_(None))
        if within is not None:
            query = query.where(within)
        with self._session() as session:
            return [
                (row.id, row.text)
                for row in session.execute(query.order_by(Passage.id).limit(limit))
            ]

    def embed_passages(self, vectors: list[tuple[int, list[float]]]) -> int:
        """Writes a vector onto each of the given passages."""
        return self._embed(_PASSAGES, vectors)

    def _embed(self, table: Table, vectors: list[tuple[int, list[float]]]) -> int:
        """Writes a vector onto each of the given rows of one table."""
        if not vectors:
            return 0
        with self._session.begin() as session:
            # The table rather than the entity, as `rejudge` does: an
            # executemany against the mapped class is read as an ORM bulk
            # update by primary key, which refuses a WHERE of its own.
            return session.execute(
                update(table).where(table.c.id == bindparam("row")),
                [{"row": row, "embedding": one} for row, one in vectors],
            ).rowcount

    def atomic_of(
        self, passage_ids: Collection[int]
    ) -> dict[int, list[tuple[int, str, tuple[int, ...]]]]:
        """Reads the validated atomic facts of some passages.

        What a bridge is composed from: each is a claim already checked
        against its own sentences.

        Args:
            passage_ids: The passages to read.

        Returns:
            Per passage, its facts as (fact id, statement, the sentence
            numbers it cites), in fact order. A passage with none is absent.
        """
        query = (
            select(
                FactPassage.passage_id,
                Fact.id,
                Fact.statement,
                FactPassage.sentence_ids,
            )
            .join(Fact, Fact.id == FactPassage.fact_id)
            .where(
                FactPassage.passage_id
                == any_(bindparam("ids", type_=ARRAY(BigInteger))),
                FactPassage.position == 0,
                FactPassage.sentence_ids.is_not(None),
                Fact.kind == FactKind.ATOMIC,
                Fact.validated.is_(True),
            )
            .order_by(Fact.id)
        )
        found: dict[int, list[tuple[int, str, tuple[int, ...]]]] = defaultdict(list)
        with self._session() as session:
            for passage, fact, statement, sentences in session.execute(
                query, {"ids": list(passage_ids)}
            ):
                found[passage].append((fact, statement, tuple(sentences)))
        return dict(found)

    def clear_bridges(self, within=None) -> int:
        """Deletes the bridge facts a fresh pass is about to replace.

        Args:
            within: A condition on Passage narrowing which bridges go, or
                None for every one of them. Every bridge opening on a passage
                of a topic holding a selected passage goes, as `by_topic`
                reads those whole.

        Returns:
            How many were deleted.
        """
        with self._session.begin() as session:
            return session.execute(
                delete(Fact).where(Fact.id.in_(_bridges(within)))
            ).rowcount

    def bridged_topics(self, within=None) -> frozenset[int]:
        """The topics a bridge already rests in, by the passage that headed it.

        Only its head counts: the others are partners, which may sit in a
        topic whose own heads the bridge says nothing about.

        Args:
            within: A condition on Passage narrowing which topics are read,
                as `by_topic` takes it, or None for the corpus.
        """
        query = (
            select(DOMINANT.c.topic_id)
            .select_from(Fact)
            .join(DOMINANT, DOMINANT.c.passage_id == _head())
            .where(Fact.kind == FactKind.BRIDGE)
            .distinct()
        )
        if within is not None:
            query = query.where(DOMINANT.c.topic_id.in_(_topics(within)))
        with self._session() as session:
            return frozenset(session.scalars(query))

    def bridged_pairs(
        self, within=None, replaced: bool = False
    ) -> frozenset[frozenset[int]]:
        """The passage pairs a stored bridge opens on, as unordered sets.

        The first two passages of each bridge: the pair a link was offered
        as, whichever of the two headed it. What a pass must not offer again.

        Args:
            within: The narrowing the pass was asked for, as `clear_bridges`
                takes it.
            replaced: Leave out the bridges `clear_bridges(within)` is about
                to delete. A pass deals its links before it clears, and the
                pairs it must not offer again are those that stay.
        """
        query = (
            select(FactPassage.fact_id, FactPassage.passage_id)
            .join(Fact, Fact.id == FactPassage.fact_id)
            .where(Fact.kind == FactKind.BRIDGE, FactPassage.position < 2)
        )
        if replaced:
            query = query.where(Fact.id.not_in(_bridges(within)))
        pairs: dict[int, set[int]] = defaultdict(set)
        with self._session() as session:
            for fact, passage in session.execute(query):
                pairs[fact].add(passage)
        return frozenset(frozenset(ids) for ids in pairs.values())

    def accepted_on_bridges(self, within=None) -> int:
        """Counts the accepted questions citing a bridge `clear_bridges` deletes.

        Args:
            within: The same narrowing `clear_bridges` takes.

        Returns:
            How many there are.
        """
        with self._session() as session:
            return (
                session.scalar(
                    select(func.count(func.distinct(QuestionFact.question_id)))
                    .join(Question, Question.id == QuestionFact.question_id)
                    .where(
                        QuestionFact.fact_id.in_(_bridges(within)),
                        Question.status == QuestionStatus.ACCEPTED,
                    )
                )
                or 0
            )

    def add_bridges(self, facts: list[CheckedFact]) -> int:
        """Writes bridge facts and the passages each rests on.

        Args:
            facts: Checked bridge facts, refused ones included.

        Returns:
            How many were written.
        """
        with self._session.begin() as session:
            return _write(session, facts, self._version)

    def judged(
        self, within=None
    ) -> Iterator[tuple[int, list[PassageToExtract], CandidateFact, str]]:
        """Streams every stored fact beside the passages it was drawn from.

        Yields the fact's id, those passages, what the extractor proposed and
        the method that proposed it, which is everything a re-judgement
        needs: the model is not called again.

        Args:
            within: A condition narrowing which facts are read, or None.

        Yields:
            One fact's id, passages, candidate and method.
        """
        query = (
            select(
                Fact.id.label("fact_id"),
                Fact.kind,
                Fact.statement,
                Fact.extraction_method,
                Fact.bridge,
                FactPassage.sentence_ids,
                *_PASSAGE_COLUMNS,
                Document.language.label("document_language"),
                Document.title.label("document_title"),
            )
            .select_from(Fact)
            .join(FactPassage, FactPassage.fact_id == Fact.id)
            .join(Passage, Passage.id == FactPassage.passage_id)
            .join(Document, Document.sha256 == Passage.doc_sha256)
            # Never a fact the cap refused. `over_cap` is the only verdict
            # here that no check reaches: it says the passage had no room
            # left, which is a fact about the passage's budget and not about
            # this claim. A re-judgement asks the checks what they make of a
            # statement, they make nothing of that, and the row would come
            # back validated - quietly undoing EXTRACTION_MIN_OTHER_SHARE
            # across the corpus. `make extract-recap` is what re-applies it.
            # Nor a duplicate, which the dedup probe decided and no check
            # reproduces.
            .where(
                Fact.rejection_code.is_distinct_from(Rejection.OVER_CAP),
                Fact.rejection_code.is_distinct_from(Rejection.DUPLICATE),
            )
            # One row per passage, consecutive per fact, so a fact is read off
            # the run of rows carrying its id.
            .order_by(Fact.id, FactPassage.position)
            .execution_options(yield_per=_BATCH)
        )
        if within is not None:
            query = query.where(_resting(within))

        with self._session() as session:
            for fact_id, found in groupby(
                session.execute(query), key=lambda row: row.fact_id
            ):
                rows = list(found)
                reading = rows[0].bridge
                yield (
                    fact_id,
                    [
                        _passage(row, row.document_language, row.document_title)
                        for row in rows
                    ],
                    CandidateFact(
                        statement=rows[0].statement,
                        sentences=tuple(rows[0].sentence_ids or ()),
                        kind=rows[0].kind,
                        passages=tuple(
                            Cited(
                                position=position,
                                sentences=tuple(row.sentence_ids or ()),
                            )
                            for position, row in enumerate(rows)
                        ),
                        probe=(reading["question"], reading["answer"])
                        if reading
                        else None,
                        relation=reading["relation"] if reading else None,
                    ),
                    rows[0].extraction_method,
                )

    def rejudge(self, verdicts: list[tuple[int, CheckedFact]]) -> int:
        """Writes back what the checks read, leaving what the model wrote.

        The statement, the kind, the method and the model's own provenance
        are the record of one extraction and are never rewritten here. The
        spans in fact_passages are: they are what the checks resolved, and a
        fact keeping yesterday's offsets beside today's verdict cites text it
        was not judged on.

        Args:
            verdicts: Each fact's id beside its new verdict.

        Returns:
            How many rows were written.
        """
        if not verdicts:
            return 0
        with self._session.begin() as session:
            # The table rather than the entity: an executemany against the
            # mapped class is read as an ORM bulk update by primary key, which
            # wants the key among the values being set.
            session.execute(
                update(_FACTS).where(_FACTS.c.id == bindparam("row")),
                [
                    {
                        "row": fact_id,
                        "evidence_text": checked.evidence_text,
                        "validated": checked.validated,
                        "rejection_code": checked.rejection_code,
                        "validation_error": checked.validation_error,
                        "statement_predicates": checked.statement_predicates,
                        "evidence_predicates": checked.evidence_predicates,
                        "units_statement": checked.units_statement,
                        "units_added": checked.units_added,
                        "unresolved_references": checked.unresolved_references,
                        "spacy_model": checked.spacy_model,
                        "spacy_version": checked.spacy_version,
                        # Rewritten with the verdict it was reached under.
                        "settings_version": self._version,
                    }
                    for fact_id, checked in verdicts
                ],
            )
            # Only the passages the verdict cites; None clears a span.
            # ponytail: a bridge passage the checker no longer resolves is not
            # among them, so its row keeps its old span. Upgrade: for a bridge,
            # clear the spans of its rows whose passage the verdict omits.
            spans = [
                {
                    "row": fact_id,
                    "passage": cited.passage_id,
                    "sentence_ids": cited.sentence_ids,
                    "evidence_start": cited.start,
                    "evidence_end": cited.end,
                }
                for fact_id, checked in verdicts
                for cited in checked.citations
            ]
            if spans:
                session.execute(
                    update(_LINKS).where(
                        _LINKS.c.fact_id == bindparam("row"),
                        _LINKS.c.passage_id == bindparam("passage"),
                    ),
                    spans,
                )
        return len(verdicts)

    def passages_of(self, fact_id: int) -> list[int]:
        """The passages one fact rests on, in the order the model saw them.

        Args:
            fact_id: The fact to read.

        Returns:
            Their ids; one for an atomic fact, a summary and an outline, two
            or more for a bridge.
        """
        with self._session() as session:
            return list(
                session.scalars(
                    select(FactPassage.passage_id)
                    .where(FactPassage.fact_id == fact_id)
                    .order_by(FactPassage.position)
                )
            )

    def page(
        self,
        document: str | None = None,
        limit: int = 100,
        offset: int = 0,
        search: str | None = None,
        method: str | None = None,
        field: str | None = None,
        kind: str | None = None,
    ) -> tuple[int, list[StoredFact]]:
        """Reads one page of facts and the total behind it.

        Args:
            document: Only facts resting on a passage of this document.
            limit: How many rows to return.
            offset: How many to skip.
            search: Text to match, in the columns `field` names.
            method: Only facts drawn this way.
            field: Which columns `search` looks in.
            kind: Only facts of this kind.

        Returns:
            The total matching the filter, and one page of it.
        """
        listing = _filtered(
            _joined(
                select(
                    Fact.id,
                    Fact.statement,
                    Fact.evidence_text,
                    Fact.kind,
                    Fact.extraction_method,
                    Fact.validated,
                    Fact.rejection_code,
                    Fact.validation_error,
                    Fact.statement_predicates,
                    Fact.evidence_predicates,
                    Fact.units_added,
                    Fact.unresolved_references,
                    Fact.confidence,
                    Fact.gate_scores,
                )
            ).order_by(Passage.doc_sha256, Passage.ordinal, Fact.id),
            document,
            search,
            method,
            field,
            kind,
        )
        counting = _filtered(
            _joined(select(func.count())), document, search, method, field, kind
        )
        with self._session() as session:
            total = session.scalar(counting) or 0
            rows = session.execute(listing.limit(limit).offset(offset)).all()
            sources = self._sources(session, [row.id for row in rows])
        return total, [
            StoredFact(
                **(row._asdict() | {"gate_scores": list(row.gate_scores or ())}),
                passages=sources.get(row.id, []),
            )
            for row in rows
        ]

    @staticmethod
    def _sources(session, fact_ids: list[int]) -> dict[int, list[FactSource]]:
        """Reads the passages one page of facts rests on, by fact id."""
        if not fact_ids:
            return {}
        found: dict[int, list[FactSource]] = {}
        for row in session.execute(_SOURCES.where(FactPassage.fact_id.in_(fact_ids))):
            found.setdefault(row.fact_id, []).append(
                FactSource(
                    passage_id=row.passage_id,
                    doc_sha256=row.doc_sha256,
                    ordinal=row.ordinal,
                    page_from=row.page_from,
                    position=row.position,
                )
            )
        return found

    def quality(
        self,
        document: str | None = None,
        search: str | None = None,
        method: str | None = None,
        field: str | None = None,
        kind: str | None = None,
    ) -> FactQuality:
        """Measures how well extraction is doing, under the listing's filter.

        Rejections are grouped on the code rather than the message: a message
        carrying a measurement gives one bucket per measurement.

        The counts are over everything the filter selects, refused facts
        included - that rate is the measurement. The means are over the
        accepted ones only. They are there to answer whether the model is
        decomposing a passage or restating it, and a fact refused as
        `evidence_absent` carries no evidence at all: it enters both
        evidence means as a zero and pulls the ratio the README reads as
        "claims per statement against claims per cited sentence" towards a
        number describing the failures rather than the work.

        Args:
            document: Only facts resting on a passage of this document.
            search: Text to match, in the columns `field` names.
            method: Only facts drawn this way.
            field: Which columns `search` looks in.
            kind: Only facts of this kind.

        Returns:
            The figures over everything the filter selects.
        """
        totals = _filtered(
            _joined(
                select(
                    func.count().label("total"),
                    func.count().filter(Fact.validated).label("validated"),
                    func.count(func.distinct(_OPENS.passage_id)).label("passages"),
                    func.coalesce(
                        func.avg(func.length(Fact.statement)).filter(Fact.validated),
                        0.0,
                    ).label("statement_chars"),
                    func.coalesce(
                        func.avg(func.length(Fact.evidence_text)).filter(
                            Fact.validated
                        ),
                        0.0,
                    ).label("evidence_chars"),
                    func.coalesce(
                        func.avg(Fact.statement_predicates).filter(Fact.validated), 0.0
                    ).label("statement_predicates"),
                    func.coalesce(
                        func.avg(Fact.evidence_predicates).filter(Fact.validated), 0.0
                    ).label("evidence_predicates"),
                )
            ),
            document,
            search,
            method,
            field,
            kind,
        )
        reasons = _filtered(
            _joined(select(Fact.rejection_code, func.count()))
            .where(Fact.rejection_code.is_not(None))
            .group_by(Fact.rejection_code)
            .order_by(func.count().desc()),
            document,
            search,
            method,
            field,
            kind,
        )
        kinds = _filtered(
            _joined(select(Fact.kind, func.count())).group_by(Fact.kind),
            document,
            search,
            method,
            field,
            kind,
        )
        with self._session() as session:
            row = session.execute(totals).one()
            rejected = dict(session.execute(reasons).all())
            held = dict(session.execute(kinds).all())
        return FactQuality(
            total=row.total,
            validated=row.validated,
            mean_statement_chars=round(float(row.statement_chars), 1),
            mean_evidence_chars=round(float(row.evidence_chars), 1),
            mean_statement_predicates=round(float(row.statement_predicates), 2),
            mean_evidence_predicates=round(float(row.evidence_predicates), 2),
            facts_per_passage=round(row.total / row.passages, 1)
            if row.passages
            else 0.0,
            rejected=rejected,
            kinds=held,
        )
