"""Reading the questions back, and recording what a person decided about one.

The API's half of the database access, plus the two operations that run over
everything stored rather than over one claimed topic: the release draw and
the re-check. Claiming a topic is the :mod:`question_generation.queue`'s.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    Select,
    Text,
    and_,
    case,
    cast,
    distinct,
    func,
    select,
    text,
    true,
    update,
)
from sqlalchemy.orm import aliased

from confidence import Measurement, scored
from database.qa_generator import (
    Document,
    Fact,
    FactKind,
    FactPassage,
    Passage,
    PassageScope,
    Question,
    QuestionFact,
    QuestionKind,
    QuestionRejection,
    QuestionStatus,
    ReviewVerdict,
    Status,
    Topic,
)
from database.qa_generator.passage_topics import DOMINANT
from database.qa_generator.repository import Repository, matching
from question_generation.balance import Row
from question_generation.models import (
    Citation,
    Criteria,
    JudgedQuestion,
    Neighbour,
    Posed,
    QuestionDetail,
    QuestionQuality,
    QuestionSource,
    StoredQuestion,
    Unanswered,
    pages,
)
from question_generation.queue import AROUND, ASSERTS, HOLDS, IS_TOPIC
from question_generation.types import CHECKED

#: Which columns the search box looks in, by the name the API accepts.
SEARCH_FIELDS = {
    "question": (Question.question_text,),
    "answer": (Question.target_answer, Question.answer_explanation),
    "both": (
        Question.question_text,
        Question.target_answer,
        Question.answer_explanation,
    ),
}

DEFAULT_FIELD = "both"

#: How many questions to hold at once while re-checking them.
_BATCH = 500

#: How many of its nearest accepted questions each one is read against for
#: a twin. The gate reads one; the release has to see past a closer question
#: that is not a twin, and a twin group is a handful of questions at most,
#: so a few cover one without reading the whole pool per question. Below
#: `hnsw.ef_search`, which caps what one index scan returns.
TWIN_NEIGHBOURS = 5

#: Lets an HNSW scan keep going past the rows its filters drop. The filters
#: on status, language and answerability apply over what one scan returns,
#: `hnsw.ef_search` rows, so a question behind that many closer rejected
#: drafts was otherwise not found at all. Strict rather than relaxed order,
#: because `nearest` takes one row and that row has to be the nearest. Local
#: to the transaction it is set in, so no other query on the connection is
#: read this way. pgvector 0.8 or later.
_PAST_THE_FILTERS = text("SET LOCAL hnsw.iterative_scan = strict_order")


def _rejecting(code: str) -> dict[str, Any]:
    """What a re-check writes to reject a question: out of the release too."""
    return {
        "status": QuestionStatus.REJECTED,
        "rejected_reason": code,
        "status_changed_at": func.now(),
        "release_id": None,
    }


#: A fact other than a bridge whose own citation, at position 0, is gone: its
#: passage was read again and it survives on a citation an earlier version's
#: duplicate refusal folded in, which `make extract-dedup` leaves in place.
_OPENING = aliased(FactPassage)
_STRANDED = and_(
    Fact.kind != FactKind.BRIDGE,
    ~select(_OPENING.fact_id)
    .where(_OPENING.fact_id == Fact.id, _OPENING.position == 0)
    .exists(),
)


def _joined(query: Select) -> Select:
    """Joins everything a question is filtered by, placed by and named by.

    Outer throughout. A question reaches its document and its topic through
    its facts, and a question whose last fact has just gone is one the
    trigger is about to delete: it should not disappear from a count before
    it disappears from the table.

    A fact reaches its passages through `fact_passages`, so a bridge reaches
    both of its passages here: the documents a question is filtered by,
    listed under and scored against are the ones its answer actually needs.

    Every join here multiplies a question by its facts, and a bridge by its
    passages on top, so anything counted over this has to be counted
    distinctly - which is why the figures are measured over :func:`_ids`
    instead.
    """
    return (
        query.select_from(Question)
        .join(QuestionFact, QuestionFact.question_id == Question.id, isouter=True)
        .join(Fact, Fact.id == QuestionFact.fact_id, isouter=True)
        .join(FactPassage, FactPassage.fact_id == Fact.id, isouter=True)
        .join(Passage, Passage.id == FactPassage.passage_id, isouter=True)
        .join(DOMINANT, DOMINANT.c.passage_id == Passage.id, isouter=True)
        .join(Topic, Topic.id == DOMINANT.c.topic_id, isouter=True)
    )


#: The columns a caller may narrow to, by the name the API takes. Every one is
#: also a column of the quality report, so a reader can ask for the reasons,
#: the cross-document ones or the hard ones alone.
SCOPES = {
    "passage_scope": Question.passage_scope,
    "document_scope": Question.document_scope,
    "topic_scope": Question.topic_scope,
    "difficulty": Question.difficulty,
    "planned_difficulty": Question.planned_difficulty,
    "question_type": Question.question_type,
    "cognitive_level": Question.cognitive_level,
    "answer_form": Question.answer_form,
}


def _filtered(query, document, topic, search, status, answerable, field, **scopes):
    """Applies every filter a listing and its figures have to agree about.

    One place, so the page of rows and the quality panel above it cannot be
    measured over different sets. The query must already be joined.
    """
    if document:
        query = query.where(Passage.doc_sha256 == document)
    if topic:
        query = query.where(DOMINANT.c.topic_id == topic)
    for name, column in SCOPES.items():
        if scopes.get(name):
            query = query.where(column == scopes[name])
    if scopes.get("follows") is not None:
        query = query.where(
            Question.follows_id.is_not(None)
            if scopes["follows"]
            else Question.follows_id.is_(None)
        )
    if scopes.get("released") is not None:
        query = query.where(
            Question.release_id.is_not(None)
            if scopes["released"]
            else Question.release_id.is_(None)
        )
    if search:
        query = query.where(
            matching(
                search, *SEARCH_FIELDS.get(field or "", SEARCH_FIELDS[DEFAULT_FIELD])
            )
        )
    if status:
        query = query.where(Question.status == status)
    if answerable is not None:
        query = query.where(Question.answerable == answerable)
    return query


def _ids(
    document=None,
    topic=None,
    search=None,
    status=None,
    answerable=None,
    field=None,
    **scopes,
) -> Select:
    """The questions a filter selects, as one id apiece.

    Every figure is measured over this rather than over the joined query,
    because that one carries a question once per fact: counting distinctly
    would fix the counts and leave the mean length weighted by how many
    facts a question happens to cite.
    """
    return _filtered(
        _joined(select(Question.id)),
        document,
        topic,
        search,
        status,
        answerable,
        field,
        **scopes,
    ).distinct()


def _narrowed(query: Select, within) -> Select:
    """Narrows a grouped query to the questions a condition selects, whole.

    By id, as `_ids` selects them, and not on the joined rows: a WHERE is
    applied before the GROUP BY, so `topic=7` there would drop the passages
    a question cites in another topic before they were counted. Uncorrelated,
    for the reason `QuestionCatalog.citations` gives.
    """
    if within is None:
        return query
    return query.where(
        Question.id.in_(_joined(select(Question.id)).where(within).correlate(None))
    )


def _listing() -> Select:
    """One question per row, with what it cites and where that sits.

    The facts are aggregated onto the row rather than left to a second
    query, because every reader of a question wants what it rests on: the
    page draws them, the workbook puts them in the cell beside the answer,
    and a benchmark shipped without them cannot be checked. `Document` is
    joined for the same reason its title is on a :class:`Citation` - a
    sha256 is not a thing anybody can look up by hand - and outer, because
    a passage whose document has just been deleted should not take the
    question out of the listing with it.
    """
    return (
        _joined(
            select(
                Question.id,
                Question.question_text,
                Question.target_answer,
                Question.answer_explanation,
                Question.answerable,
                Question.difficulty,
                Question.kind,
                Question.passage_scope,
                Question.document_scope,
                Question.topic_scope,
                Question.answer_chars,
                Question.language,
                Question.status,
                Question.rejected_reason,
                Question.reviewed_verdict,
                Question.created_at,
                Question.thread_position,
                Question.follows_id,
                Question.question_type,
                Question.cognitive_level,
                Question.answer_form,
                Question.planned_difficulty,
                Question.categories,
                Question.prompt_version,
                Question.trace_id,
                Question.span_id,
                Question.confidence,
                Question.gate_scores,
                Question.attempt,
                Question.release_id.is_not(None).label("released"),
                func.count(func.distinct(QuestionFact.fact_id)).label("facts"),
                func.array_agg(
                    func.distinct(func.coalesce(Document.title, Passage.doc_sha256))
                ).label("documents"),
                func.array_agg(func.distinct(Topic.label)).label("topics"),
                func.array_agg(func.distinct(Fact.statement)).label("statements"),
                func.array_agg(func.distinct(Fact.evidence_text)).label("evidence"),
            )
        )
        .join(Document, Document.sha256 == Passage.doc_sha256, isouter=True)
        .group_by(Question.id)
        .order_by(Question.id)
    )


def _when(moment: datetime | None) -> str | None:
    """Renders a timestamp for the wire."""
    return moment.isoformat() if moment else None


def _present(values: Sequence[Any] | None) -> list[str]:
    """Drops the NULLs an outer join left in an aggregate."""
    return sorted({str(value) for value in values or () if value is not None})


def _stored(row: Any) -> StoredQuestion:
    """Reads one row of the listing back as a question."""
    return StoredQuestion(
        **row._asdict()
        | {
            "created_at": _when(row.created_at),
            "documents": _present(row.documents),
            "topics": _present(row.topics),
            "statements": _present(row.statements),
            "evidence": _present(row.evidence),
            "gate_scores": list(row.gate_scores or ()),
            # As `Category.label` writes one, which is what a reader filters
            # a workbook or groups a report by.
            "categories": [
                f"{one['categorization']}={one['category']}"
                for one in row.categories or ()
            ],
        }
    )


#: How much of the corpus the ACCEPTED questions reach.
#:
#: Four counts in one statement rather than four round trips, and every one
#: of them corpus-wide: coverage is a property of the material, so a filter
#: that selects no question of a passage cannot say that passage is
#: unasked.
#:
#: `passages_with_facts` counts only passages a VALIDATED fact rests on,
#: because that is the most this stage could ever ask about. Measuring
#: against every passage would report extraction's refusals as question
#: generation's gap.
_ASKED_PASSAGES = (
    select(FactPassage.passage_id)
    .join(QuestionFact, QuestionFact.fact_id == FactPassage.fact_id)
    .join(Question, Question.id == QuestionFact.question_id)
    .where(Question.status == QuestionStatus.ACCEPTED)
    .distinct()
    .scalar_subquery()
)

_COVERAGE = select(
    select(func.count()).select_from(Passage).scalar_subquery().label("passages_total"),
    select(func.count(distinct(FactPassage.passage_id)))
    .select_from(FactPassage)
    .join(Fact, Fact.id == FactPassage.fact_id)
    .where(Fact.validated)
    .scalar_subquery()
    .label("passages_with_facts"),
    select(func.count())
    .select_from(_ASKED_PASSAGES.subquery())
    .scalar_subquery()
    .label("passages_asked"),
    select(func.count())
    .select_from(Fact)
    .where(Fact.validated)
    .scalar_subquery()
    .label("facts_validated"),
    select(func.count(distinct(QuestionFact.fact_id)))
    .select_from(QuestionFact)
    .join(Question, Question.id == QuestionFact.question_id)
    .where(Question.status == QuestionStatus.ACCEPTED)
    .scalar_subquery()
    .label("facts_asked"),
)


#: The constant reciprocal rank fusion is usually run with: large enough
#: that a first place in one ranking does not outweigh two good places.
_FUSION = 60


def _fused(*rankings: list[int]) -> list[int]:
    """Ids ranked by reciprocal rank fusion over several rankings, best first.

    Ties go to the lower id, so the same corpus answers the same way twice.
    """
    score: dict[int, float] = {}
    for ranking in rankings:
        for rank, one in enumerate(ranking, 1):
            score[one] = score.get(one, 0.0) + 1 / (_FUSION + rank)
    return sorted(score, key=lambda one: (-score[one], one))


class QuestionCatalog(Repository):
    """Reads back the questions, and records what a person decided about one.

    Separate from the queue: the API serves these and never claims a row.
    """

    def releasable(self, within=None) -> list[Row]:
        """Every accepted question a release may be chosen from.

        Only the columns the choosing reads. A question with no
        difficulty or no type is left out rather than given a bucket: it
        would be chosen into a quota it cannot be counted against, and the
        report would then disagree with the set it describes.
        """
        query = select(
            Question.id,
            Question.answerable,
            Question.difficulty,
            Question.question_type,
            Question.follows_id,
            Question.language,
        ).where(
            Question.status == QuestionStatus.ACCEPTED,
            Question.difficulty.is_not(None),
            Question.question_type.is_not(None),
        )
        if within is not None:
            query = query.where(within)
        with self._session() as session:
            return [
                Row(
                    id=row.id,
                    answerable=row.answerable,
                    difficulty=row.difficulty,
                    question_type=row.question_type,
                    follows_id=row.follows_id,
                    language=row.language,
                )
                for row in session.execute(query.order_by(Question.id))
            ]

    def release(self, ids: Sequence[int]) -> tuple[uuid.UUID, int]:
        """Marks these questions as the release, and clears the last one.

        One release at a time, because the column holds one id and the
        question a report is about is "what would ship today". A previous
        release is not history worth keeping here: every question it held
        is still in the table, and the draw is reproducible from the
        settings that made it.

        Only a question still accepted is written: the draw was read before
        minutes of twin checks, and a person or the fact trigger may have
        rejected one since. The count returned is what was written, so the
        shortfall against the draw is visible. A follow-up whose turn was
        not written is not written either.
        """
        drawn = uuid.uuid4()
        with self._session.begin() as session:
            session.execute(
                update(Question)
                .where(Question.release_id.is_not(None))
                .values(release_id=None)
            )
            if not ids:
                return drawn, 0
            held = dict(
                session.execute(
                    select(Question.id, Question.follows_id)
                    .where(
                        Question.id.in_(list(ids)),
                        Question.status == QuestionStatus.ACCEPTED,
                    )
                    .order_by(Question.id)
                    .with_for_update()
                ).all()
            )
            # A follow-up is released with the turn it follows or not at all:
            # the thread trigger already ran, before this write, for a root
            # rejected since the draw, so nothing else clears what rests on it.
            while cut := [
                one
                for one, follows in held.items()
                if follows is not None and follows not in held
            ]:
                for one in cut:
                    del held[one]
            if not held:
                return drawn, 0
            return drawn, session.execute(
                update(Question)
                .where(Question.id.in_(list(held)))
                .values(release_id=drawn)
            ).rowcount

    def elsewhere(
        self,
        lemmas: Sequence[str],
        language: str,
        skip: Sequence[int],
        limit: int,
        embedding: Sequence[float] | None = None,
    ) -> list[str]:
        """The passages outside this question's own that talk about it most.

        What the `answerable_elsewhere` gate reads. The verifier is shown
        only the passages a question cites, which is right for measuring the
        dataset and wrong for one claim: an unanswerable question is a claim
        about the WHOLE corpus, and a passage nobody cited may answer it. A
        question labelled unanswerable that the material does answer marks a
        correct chatbot wrong, which is the failure the gates exist for.

        Ranked by cosine over `passages.embedding` when the question carries
        a vector and the corpus has been embedded, and by shared content
        lemmas otherwise. On the vector path only, the passages within
        `AROUND` ordinals of each cited one follow the nearest, on top of
        `limit`; the lemma path adds none.

        The vectors matter more here than anywhere else this pair of
        measures is used. A lemma probe finds the passages that REPEAT the
        question's words, and an unanswerable question is written by moving
        a fact just out of reach - so the passage that would answer it is
        the one phrased differently, which is the one a lemma probe ranks
        last. This gate exists to catch a question the corpus answers after
        all, and it was retrieving on the signal least likely to find one.

        Either way it is a retrieval and not a proof: it finds where to
        look, and the model still reads the passages and decides.

        Args:
            lemmas: The question's content lemmas.
            language: Only passages written in this one.
            skip: Passages the question already cites, which the first
                verifier pass has read.
            limit: The most passages to hand back by rank. The cited
                passages' neighbours, on the vector path, are not counted
                against it.
            embedding: The question's vector, when one was computed.

        Returns:
            Their text, nearest first, then the neighbours. Empty when the
            question names nothing the corpus does.
        """
        if embedding is not None:
            found = self._nearest_passages(
                language, skip, limit, list(embedding), lemmas
            )
            if found:
                return found
        return [text for _, text in self._sharing(lemmas, language, skip, limit)]

    def _sharing(
        self, lemmas: Sequence[str], language: str, skip: Sequence[int], limit: int
    ) -> list[tuple[int, str]]:
        """The passages of one language sharing most of these content lemmas.

        By id and text, most shared first. Empty for no lemmas.
        """
        if not lemmas:
            return []
        wanted = cast(list(lemmas), ARRAY(Text))
        # The overlap counted by intersecting the two arrays. The `&&`
        # filter beside it is what the GIN index on lemmas serves, so this
        # only ever orders the rows that filter already kept.
        overlap = func.cardinality(
            func.array(
                select(func.unnest(Passage.lemmas))
                .intersect(select(func.unnest(wanted)))
                .scalar_subquery()
            )
        )
        query = (
            select(Passage.id, Passage.text)
            .where(
                Passage.language == language,
                Passage.lemmas.op("&&")(wanted),
                ASSERTS,
            )
            .order_by(overlap.desc(), Passage.id)
            .limit(limit)
        )
        if skip:
            query = query.where(Passage.id.notin_(skip))
        with self._session() as session:
            return [(row.id, row.text) for row in session.execute(query)]

    def _nearest_passages(
        self,
        language: str,
        skip: Sequence[int],
        limit: int,
        embedding: list[float],
        lemmas: Sequence[str] = (),
    ) -> list[str]:
        """The embedded passages of one language nearest this vector.

        Fused with the passages sharing most of the question's content
        lemmas, by reciprocal rank: the passage that answers a question after
        all may repeat its words and sit far from it in the space, or sit
        close and share none of them, and each ranking alone misses the
        other half. Each is read twice as deep as `limit` before the fusion
        keeps `limit`.

        And then the passages within `AROUND` ordinals of each one it skips,
        in that passage's document: the rest of the rule a cited passage
        starts, which the vector ranks anywhere. `limit` counts the nearest
        only, so the neighbours never crowd the corpus out.

        The language, `ASSERTS` and `skip` apply over an iterative index
        scan, as in `nearest`, so a language holding a small share of the
        passages still gets its `limit`.

        Empty when the corpus carries no vectors, which is what sends
        `elsewhere` back to its lemma probe rather than to nothing.
        """
        distance = Passage.embedding.cosine_distance(embedding)
        query = (
            select(Passage.id, Passage.text)
            .where(
                Passage.language == language,
                Passage.embedding.is_not(None),
                # The same filter the lemma probe applies, and for the same
                # reason: a contents page carries every term in the material
                # and sits near every question in the space, and answers
                # none of them.
                ASSERTS,
            )
            .order_by(distance)
            .limit(2 * limit)
        )
        if skip:
            query = query.where(Passage.id.notin_(skip))
        with self._session() as session:
            session.execute(_PAST_THE_FILTERS)
            near = {row.id: row.text for row in session.execute(query)}
        if not near:
            return []
        sharing = dict(self._sharing(lemmas, language, skip, 2 * limit))
        texts = near | sharing
        found = {one: texts[one] for one in _fused(list(near), list(sharing))[:limit]}
        if not skip:
            return list(found.values())
        with self._session() as session:
            cited = aliased(Passage)
            beside = (
                select(cited.id)
                .where(
                    cited.id.in_(skip),
                    cited.doc_sha256 == Passage.doc_sha256,
                    func.abs(cited.ordinal - Passage.ordinal) <= AROUND,
                )
                .exists()
            )
            for row in session.execute(
                select(Passage.id, Passage.text)
                .where(
                    beside,
                    Passage.id.notin_(skip),
                    Passage.language == language,
                    ASSERTS,
                )
                .order_by(Passage.doc_sha256, Passage.ordinal)
            ):
                found.setdefault(row.id, row.text)
        return list(found.values())

    def nearest(
        self,
        embedding: list[float],
        before: int | None = None,
        excluding: Sequence[int] = (),
        language: str | None = None,
        answerable: bool | None = None,
    ) -> Neighbour | None:
        """The accepted question closest to this vector, or None if there is none.

        `language` looks only at questions written in it. There is no twin
        across languages: a bilingual set asks each language its own
        questions, and a question and its translation are one item each.

        `answerable` looks only at questions of that answerability, so a
        closer question that cannot refuse the one probed for does not hide
        one that can: see `gates.rivals`.

        `before` looks only at questions written earlier. A re-check needs
        it: without it, two questions that are duplicates of each other each
        find the other and both are rejected, which leaves the benchmark
        with neither rather than with one.

        `excluding` drops questions a caller has decided to reject but has
        not written yet. A re-check batches its verdicts, and without this
        the answer depends on whether the batch happened to have been
        flushed - the same pass over the same rows rejecting a different
        set at a different batch size.

        The HNSW index serves the ordering, and every filter here - status,
        language, answerability, `before` - is applied over the candidates
        its scan returns, which number `hnsw.ef_search`. So the scan is
        iterative: where the filters leave nothing among those, it reads on,
        and a language holding a small share of the questions, an
        answerability that is the rarer one, or a question behind many closer
        rejected drafts is still found.
        """
        distance = Question.embedding.cosine_distance(embedding)
        query = (
            select(
                Question.id,
                Question.question_text,
                Question.answerable,
                Question.language,
                distance.label("far"),
            )
            .where(
                Question.status == QuestionStatus.ACCEPTED,
                Question.embedding.is_not(None),
            )
            .order_by(distance)
            .limit(1)
        )
        if before is not None:
            query = query.where(Question.id < before)
        if excluding:
            query = query.where(Question.id.notin_(list(excluding)))
        if language is not None:
            query = query.where(Question.language == language)
        if answerable is not None:
            query = query.where(Question.answerable == answerable)
        with self._session() as session:
            session.execute(_PAST_THE_FILTERS)
            found = session.execute(query).one_or_none()
            if found is None:
                return None
            # Asked apart from the probe, which an aggregate over the join
            # would take off the index.
            cited = session.execute(
                select(QuestionFact.fact_id, FactPassage.passage_id)
                .join(
                    FactPassage,
                    FactPassage.fact_id == QuestionFact.fact_id,
                    isouter=True,
                )
                .where(QuestionFact.question_id == found.id)
            ).all()
        return Neighbour(
            question_text=found.question_text,
            answerable=found.answerable,
            # pgvector answers in cosine distance; the gates read likeness.
            similarity=1.0 - float(found.far),
            fact_ids=frozenset(row.fact_id for row in cited),
            language=found.language,
            id=found.id,
            passage_ids=frozenset(
                row.passage_id for row in cited if row.passage_id is not None
            ),
        )

    def closest_among(self, ids: Sequence[int]) -> list[tuple[Posed, Posed]]:
        """Each of these questions paired with its nearest other among them.

        In one language and one answerability, by vector, each pair once.
        What the release's twin judge is asked about: a pair restating one
        rule as two documents state it shares no citation and sits no closer
        than a pair asking two things, so rank and not a cosine bar picks
        what is put to it. The filters apply over an iterative index scan,
        as in `nearest`.
        """
        if len(ids) < 2:
            return []
        asked, other = aliased(Question), aliased(Question)
        nearest = (
            select(other.id.label("id"))
            .where(
                other.id.in_(ids),
                other.embedding.is_not(None),
                other.language == asked.language,
                other.answerable == asked.answerable,
                other.id != asked.id,
            )
            .order_by(other.embedding.cosine_distance(asked.embedding))
            .limit(1)
            .lateral("nearest")
        )
        pairs = (
            select(
                func.least(asked.id, nearest.c.id).label("first"),
                func.greatest(asked.id, nearest.c.id).label("second"),
            )
            .select_from(asked)
            .join(nearest, true())
            .where(asked.id.in_(ids), asked.embedding.is_not(None))
            .distinct()
            .cte("pairs")
        )
        one, two = aliased(Question), aliased(Question)
        query = (
            select(
                one.id,
                one.question_text,
                one.target_answer,
                two.id.label("other_id"),
                two.question_text.label("other_text"),
                two.target_answer.label("other_answer"),
            )
            .select_from(pairs)
            .join(one, one.id == pairs.c.first)
            .join(two, two.id == pairs.c.second)
            .order_by(pairs.c.first, pairs.c.second)
        )
        with self._session() as session:
            session.execute(_PAST_THE_FILTERS)
            return [
                (
                    Posed(row.id, row.question_text, row.target_answer),
                    Posed(row.other_id, row.other_text, row.other_answer),
                )
                for row in session.execute(query)
            ]

    def twins(self, floor: float) -> list[tuple[Neighbour, Neighbour]]:
        """The pairs of accepted questions at least this alike, in one language.

        What the release reads twins off: `nearest` answers one neighbour
        per question, so a twin behind a closer question that is not one
        gets past the gate, and the release is where it is caught. Pairs of
        one answerability only, because an answerable question is never the
        twin of an unanswerable one. Each side carries what it cites, so the
        caller can hold the pair to the duplicate gate's own rule, and
        `floor` is the lowest bar that rule has.

        Read among each question's `TWIN_NEIGHBOURS` nearest, over the HNSW
        index, rather than over every pair, which is a scan of the pool for
        each question in it. A pair either side holds among its nearest is
        found, so a twin is missed only behind as many closer questions of
        the same language and answerability on both sides. The filters
        apply over an iterative index scan, as in `nearest`.
        """
        asked, other = aliased(Question), aliased(Question)
        distance = other.embedding.cosine_distance(asked.embedding)
        nearest = (
            select(other.id.label("id"), distance.label("far"))
            .where(
                other.status == QuestionStatus.ACCEPTED,
                other.embedding.is_not(None),
                other.language == asked.language,
                other.answerable == asked.answerable,
                other.id != asked.id,
            )
            .order_by(distance)
            .limit(TWIN_NEIGHBOURS)
            .lateral("nearest")
        )
        first = func.least(asked.id, nearest.c.id)
        second = func.greatest(asked.id, nearest.c.id)
        pairs = (
            select(
                first.label("first"),
                second.label("second"),
                func.min(nearest.c.far).label("far"),
            )
            .select_from(asked)
            .join(nearest, true())
            .where(
                asked.status == QuestionStatus.ACCEPTED,
                asked.embedding.is_not(None),
                nearest.c.far <= 1.0 - floor,
            )
            .group_by(first, second)
            .cte("pairs")
        )
        paired = select(pairs.c.first).union(select(pairs.c.second))
        cited = (
            select(
                QuestionFact.question_id.label("id"),
                func.array_agg(func.distinct(QuestionFact.fact_id)).label("facts"),
                func.array_agg(func.distinct(FactPassage.passage_id)).label("passages"),
            )
            .join(
                FactPassage, FactPassage.fact_id == QuestionFact.fact_id, isouter=True
            )
            .where(QuestionFact.question_id.in_(paired))
            .group_by(QuestionFact.question_id)
            .cte("cited")
        )
        query = select(pairs.c.far)
        for name in ("first", "second"):
            held, cites = aliased(Question), cited.alias(f"{name}_cited")
            query = (
                query.add_columns(
                    pairs.c[name].label(f"{name}_id"),
                    held.question_text.label(f"{name}_text"),
                    held.answerable.label(f"{name}_answerable"),
                    held.language.label(f"{name}_language"),
                    cites.c.facts.label(f"{name}_facts"),
                    cites.c.passages.label(f"{name}_passages"),
                )
                .join(held, held.id == pairs.c[name])
                .join(cites, cites.c.id == pairs.c[name], isouter=True)
            )
        query = query.select_from(pairs).order_by(pairs.c.first, pairs.c.second)
        with self._session() as session:
            session.execute(_PAST_THE_FILTERS)
            found = session.execute(query).all()

        def side(row: Any, name: str) -> Neighbour:
            """One half of a pair, as the duplicate gate reads a neighbour."""
            values = row._mapping
            return Neighbour(
                question_text=values[f"{name}_text"],
                answerable=values[f"{name}_answerable"],
                # pgvector answers in cosine distance; the gates read likeness.
                similarity=1.0 - float(values["far"]),
                fact_ids=frozenset(
                    one for one in values[f"{name}_facts"] or () if one is not None
                ),
                language=values[f"{name}_language"],
                id=values[f"{name}_id"],
                passage_ids=frozenset(
                    one for one in values[f"{name}_passages"] or () if one is not None
                ),
            )

        return [(side(row, "first"), side(row, "second")) for row in found]

    def judged(self, within=None) -> Iterator[JudgedQuestion]:
        """Streams every stored question with what a re-check needs.

        One query rather than one per question: whether the facts under it
        still hold, how far they are spread now, and what they say.
        """
        query = (
            _joined(
                select(
                    Question.id,
                    Question.question_text,
                    Question.target_answer,
                    Question.answerable,
                    Question.difficulty,
                    Question.kind,
                    Question.passage_scope,
                    Question.document_scope,
                    Question.topic_scope,
                    Question.follows_id,
                    Question.language,
                    Question.status,
                    Question.reviewed_verdict,
                    Question.embedding,
                    Question.question_type,
                    Question.answer_form,
                    func.coalesce(func.bool_and(HOLDS), False).label("facts_validated"),
                    func.coalesce(func.bool_or(_STRANDED), False).label("stranded"),
                    func.count(func.distinct(Passage.doc_sha256)).label("documents"),
                    func.count(func.distinct(Passage.id)).label("passages"),
                    func.count(func.distinct(DOMINANT.c.topic_id)).label("topics"),
                    func.array_agg(func.distinct(Fact.statement)).label("statements"),
                    func.array_agg(func.distinct(QuestionFact.fact_id)).label(
                        "fact_ids"
                    ),
                    func.array_agg(func.distinct(Passage.id)).label("passage_ids"),
                )
            )
            .group_by(Question.id)
            .order_by(Question.id)
            .execution_options(yield_per=_BATCH)
        )
        query = _narrowed(query, within)
        with self._session() as session:
            for row in session.execute(query):
                yield JudgedQuestion(
                    **row._asdict()
                    | {
                        "embedding": list(row.embedding)
                        if row.embedding is not None
                        else None,
                        "statements": tuple(
                            one for one in row.statements or () if one is not None
                        ),
                        "fact_ids": tuple(
                            one for one in row.fact_ids or () if one is not None
                        ),
                        "passage_ids": tuple(
                            one for one in row.passage_ids or () if one is not None
                        ),
                    }
                )

    def unanswered(self, within=None, version: str | None = None) -> list[Unanswered]:
        """Every accepted question written to have no answer, with its passages.

        What `make questions-rejudge` reads. Released ones included: the
        release is a subset of the accepted, and a released question the
        material answers is the one that marks a correct chatbot wrong.

        `version` is the verifier's prompt version: a question reads as
        judged only when it carries a `settles` verdict given under it, so a
        rewritten prompt asks every question again. None reads any verdict.
        """
        query = (
            _joined(
                select(
                    Question.id,
                    Question.question_text,
                    Question.language,
                    Question.reviewed_verdict,
                    Question.embedding,
                    Question.gate_scores,
                    func.array_agg(func.distinct(Passage.id)).label("passage_ids"),
                )
            )
            .where(
                Question.status == QuestionStatus.ACCEPTED,
                Question.answerable.is_(False),
            )
            .group_by(Question.id)
            .order_by(Question.id)
        )
        query = _narrowed(query, within)
        with self._session() as session:
            rows = session.execute(query).all()
            cited = {one for row in rows for one in row.passage_ids or () if one}
            texts = {
                row.id: row.text
                for row in session.execute(
                    select(Passage.id, Passage.text).where(Passage.id.in_(cited))
                )
            }
        found = []
        for row in rows:
            ids = tuple(sorted(one for one in row.passage_ids or () if one))
            found.append(
                Unanswered(
                    id=row.id,
                    question_text=row.question_text,
                    language=row.language,
                    reviewed_verdict=row.reviewed_verdict,
                    embedding=(
                        list(row.embedding) if row.embedding is not None else None
                    ),
                    passage_ids=ids,
                    passages=tuple(texts[one] for one in ids),
                    judged=any(
                        one.get("gate") == "settles"
                        and (version is None or one.get("version") == version)
                        for one in row.gate_scores or ()
                    ),
                )
            )
        return found

    def opine(
        self,
        question_id: int,
        opinions: Sequence[Measurement],
        rejected: str | None = None,
    ) -> bool:
        """Adds a model's verdicts to one question's `gate_scores`, and rejects it.

        Opinions only. They carry no margin, so the row's confidence stays
        what its measurements made it and nothing here recomputes it; a
        measurement added this way would leave the two disagreeing.

        `rejected` is the code the verdicts refuse it under, or None to keep
        it. One transaction for both: a verdict written without the
        rejection it decided reads as judged, and nothing asks it again.
        The row is locked while its entries are read and written back, so a
        concurrent write of the column waits rather than losing one.

        The rejection is applied only to a row still accepted that no person
        accepted, read under the same lock: the caller decided on a reading
        taken before the call, and a person accepting or rejecting it since
        is not overruled. The verdicts are kept either way.

        Returns:
            Whether the question was rejected.

        Raises:
            ValueError: If any of them is a measurement.
        """
        if any(not one.opinion for one in opinions):
            raise ValueError("only an opinion is added without its confidence")
        if not opinions and not rejected:
            return False
        with self._session.begin() as session:
            stored = session.execute(
                select(Question.gate_scores, Question.status, Question.reviewed_verdict)
                .where(Question.id == question_id)
                .with_for_update()
            ).one_or_none()
            if stored is None:
                return False
            rejecting = bool(rejected) and (
                stored.status == QuestionStatus.ACCEPTED
                and stored.reviewed_verdict != ReviewVerdict.ACCEPTED
            )
            session.execute(
                update(Question)
                .where(Question.id == question_id)
                .values(
                    gate_scores=[*(stored.gate_scores or ()), *scored(opinions)],
                    **(_rejecting(rejected) if rejected and rejecting else {}),
                )
            )
        return rejecting

    def rescore(self, rows: Sequence[tuple[int, Criteria]]) -> int:
        """Writes the scopes and the band a rescore read, one row per question.

        Nothing else on the row moves: not its status, its answer length or
        the band its plan asked for. Bar its kind, which follows the citations
        down: a question that now rests on one passage is `single`, and one
        still resting on two keeps the kind it was written as.
        """
        if not rows:
            return 0
        with self._session.begin() as session:
            # One executemany, read as an ORM bulk update by primary key.
            session.execute(
                update(Question),
                [
                    {
                        "id": question_id,
                        "passage_scope": now.passage_scope,
                        "document_scope": now.document_scope,
                        "topic_scope": now.topic_scope,
                        "difficulty": now.difficulty,
                    }
                    for question_id, now in rows
                ],
            )
            narrowed = [
                question_id
                for question_id, now in rows
                if now.passage_scope == PassageScope.SINGLE
            ]
            if narrowed:
                session.execute(
                    update(Question)
                    .where(Question.id.in_(narrowed))
                    .values(kind=QuestionKind.SINGLE)
                )
        return len(rows)

    def reject(self, verdicts: list[tuple[int, str]]) -> int:
        """Records what a re-check found, one gate code per question.

        The verdicts were decided on a reading taken before this call, so
        a row is rejected only if it is still accepted and no person has
        accepted it since. `source_changed` is the one code that may
        overrule a person: the fact the answer rests on is gone.

        Returns:
            How many rows were rejected.

        ponytail: one UPDATE per question. Upgrade: one executemany with
        bindparam.
        """
        changed = 0
        if not verdicts:
            return changed
        with self._session.begin() as session:
            for question_id, code in verdicts:
                where = [Question.id == question_id]
                if code != QuestionRejection.SOURCE_CHANGED:
                    where += [
                        Question.status == QuestionStatus.ACCEPTED,
                        Question.reviewed_verdict.is_distinct_from(
                            ReviewVerdict.ACCEPTED
                        ),
                    ]
                changed += session.execute(
                    update(Question).where(*where).values(**_rejecting(code))
                ).rowcount
        return changed

    def decide(self, question_id: int, status: str) -> StoredQuestion | None:
        """Records what a person decided about one question.

        Three columns, and they say different things. `status` is what the
        question now IS, `rejected_reason` stays whatever gate stopped it,
        and `reviewed_verdict` is what the person said.

        The reason used to be cleared here, on the grounds that a reason for
        a rejection somebody overturned is a stale one. It is not stale, it
        is the other half of a disagreement: without it, a person accepting
        what a gate refused erased the only record that the two had ever
        disagreed, and the agreement rate a review sample exists to produce
        was not a query. A person rejecting still names no gate, which is
        why the column allows NULL on rows no gate ever touched.

        Putting a question back to `draft` is the one decision that is not a
        verdict - it says "I have not decided" - so it clears the verdict
        rather than recording itself as one, which the column could not hold
        anyway.

        Any status but `accepted` clears `release_id`.
        """
        decided = status in (QuestionStatus.ACCEPTED, QuestionStatus.REJECTED)
        with self._session.begin() as session:
            changed = session.execute(
                update(Question)
                .where(Question.id == question_id)
                .values(
                    status=status,
                    reviewed_verdict=status if decided else None,
                    reviewed_at=func.now() if decided else None,
                    status_changed_at=func.now(),
                    release_id=Question.release_id
                    if status == QuestionStatus.ACCEPTED
                    else None,
                )
            ).rowcount
        if not changed:
            return None
        return self.one(question_id)

    def one(self, question_id: int) -> StoredQuestion | None:
        """Reads one question, as the listing shows it."""
        with self._session() as session:
            row = session.execute(
                _listing().where(Question.id == question_id)
            ).one_or_none()
        return _stored(row) if row else None

    def page(
        self,
        document: str | None = None,
        topic: int | None = None,
        limit: int | None = 50,
        offset: int = 0,
        search: str | None = None,
        status: str | None = None,
        answerable: bool | None = None,
        field: str | None = None,
        **scopes: Any,
    ) -> tuple[int, list[StoredQuestion]]:
        """Reads one page of questions and the total behind it.

        `limit` of None is every row the filter selects, which is what the
        export asks for. It has to be this call and not a count followed by
        a window the size of it: those are two statements, and a question
        written between them is one the window no longer has room for.
        """
        chosen = _ids(document, topic, search, status, answerable, field, **scopes)
        # By id, so a filter narrows which questions are listed and never
        # what each one cites: a WHERE on the joined rows would count only
        # the facts of the chosen document. Uncorrelated, as `_narrowed` is.
        listing = _listing().where(Question.id.in_(chosen.correlate(None)))
        counting = select(func.count()).select_from(chosen.subquery())
        with self._session() as session:
            total = session.scalar(counting) or 0
            rows = session.execute(listing.limit(limit).offset(offset)).all()
        return total, [_stored(row) for row in rows]

    def _thread(self, question: StoredQuestion) -> list[StoredQuestion]:
        """The whole thread this question sits in, oldest first.

        Walked from the root rather than from the question, so a follow-up
        shows what was asked before it as well as after: reading a follow-up
        without its parent is reading half a conversation, and the parent is
        what makes it answerable.

        Both walks stop on a row they have already seen. `follows_id` is a
        self-referential foreign key and nothing in the schema says a thread
        may not close into a loop - `thread_position` counts up and no
        constraint compares it to the parent's - so a cycle written by hand
        or by a bad backfill would have hung the request that read it, which
        is a page that never loads rather than a page that is wrong.

        ponytail: two queries per turn. Upgrade: one recursive CTE.
        """
        root = question
        seen = {root.id}
        while root.follows_id is not None and root.follows_id not in seen:
            found = self.one(root.follows_id)
            if found is None:  # pragma: no cover - the cascade prevents it
                break
            seen.add(found.id)
            root = found

        thread = [root]
        walked = {root.id}
        while True:
            with self._session() as session:
                nxt = session.scalar(
                    select(Question.id).where(Question.follows_id == thread[-1].id)
                )
            if nxt is None or nxt in walked:
                break
            found = self.one(nxt)
            if found is None:  # pragma: no cover
                break
            walked.add(found.id)
            thread.append(found)
        return thread

    def detail(self, question_id: int) -> QuestionDetail | None:
        """Reads one question with the facts it was written from."""
        found = self.one(question_id)
        if found is None:
            return None
        with self._session() as session:
            sources = session.execute(
                select(
                    Fact.id,
                    Fact.statement,
                    Fact.evidence_text,
                    Fact.validated,
                    # A bridge comes back once per passage it rests on, and
                    # the document and the ordinal beside it are that
                    # passage's.
                    Passage.id.label("passage_id"),
                    Passage.doc_sha256,
                    Passage.ordinal,
                )
                .select_from(QuestionFact)
                .join(Fact, Fact.id == QuestionFact.fact_id)
                .join(FactPassage, FactPassage.fact_id == Fact.id)
                .join(Passage, Passage.id == FactPassage.passage_id)
                .where(QuestionFact.question_id == question_id)
                .order_by(Passage.doc_sha256, Passage.ordinal, Fact.id)
            ).all()
        return QuestionDetail(
            question=found,
            thread=self._thread(found),
            sources=[
                QuestionSource(
                    fact_id=row.id,
                    statement=row.statement,
                    evidence_text=row.evidence_text,
                    validated=row.validated,
                    passage_id=row.passage_id,
                    doc_sha256=row.doc_sha256,
                    ordinal=row.ordinal,
                )
                for row in sources
            ],
        )

    def citations(self, **where: Any) -> list[Citation]:
        """What every question a filter selects was written from.

        The same rows :meth:`detail` reads one question at a time, for a
        whole filter in one query. An export runs over thousands of
        questions, and asking per question is that many round trips for a
        join the database does once.

        A question comes back once per (fact, passage) pair, so a bridge
        resting on two passages is two rows. That is the grain a reader
        checking an answer against its source wants: the document and the
        page beside each half of what was cited.

        The chosen ids are JOINED as a derived table rather than put in an
        `IN`, and `correlate(None)` is why the difference matters. `_ids`
        is joined over the same four tables this query selects from, so as
        a WHERE subquery SQLAlchemy correlated those tables to the outer
        query and emptied the subquery's own FROM.
        """
        chosen = _ids(**where).correlate(None).subquery()
        with self._session() as session:
            rows = session.execute(
                select(
                    QuestionFact.question_id,
                    Fact.id.label("fact_id"),
                    Fact.statement,
                    Fact.evidence_text,
                    Fact.validated,
                    Passage.doc_sha256,
                    Passage.ordinal,
                    Passage.page_from,
                    Passage.page_to,
                    Document.title,
                )
                .select_from(QuestionFact)
                .join(chosen, chosen.c.id == QuestionFact.question_id)
                .join(Fact, Fact.id == QuestionFact.fact_id)
                .join(FactPassage, FactPassage.fact_id == Fact.id)
                .join(Passage, Passage.id == FactPassage.passage_id)
                .join(Document, Document.sha256 == Passage.doc_sha256, isouter=True)
                .order_by(QuestionFact.question_id, Passage.doc_sha256, Passage.ordinal)
            ).all()
        return [
            Citation(
                question_id=row.question_id,
                fact_id=row.fact_id,
                statement=row.statement,
                evidence_text=row.evidence_text,
                validated=row.validated,
                document=row.title or row.doc_sha256[:12],
                doc_sha256=row.doc_sha256,
                ordinal=row.ordinal,
                page=pages(row.page_from, row.page_to),
            )
            for row in rows
        ]

    def quality(
        self,
        document: str | None = None,
        topic: int | None = None,
        search: str | None = None,
        status: str | None = None,
        answerable: bool | None = None,
        field: str | None = None,
        **scopes: Any,
    ) -> QuestionQuality:
        """Measures how generation is doing, under the listing's filter.

        Rejections are grouped on the gate that fired, which is what says
        whether the model is writing questions the corpus answers or
        questions that merely look as though it should.
        """
        # One question per row from here on, so a plain count is the right
        # count and the mean is not weighted by how many facts each cites.
        selected = Question.id.in_(
            _ids(document, topic, search, status, answerable, field, **scopes)
        )
        totals = select(
            func.count().label("total"),
            func.count()
            .filter(Question.status == QuestionStatus.ACCEPTED)
            .label("accepted"),
            func.count().filter(Question.status == QuestionStatus.DRAFT).label("draft"),
            func.count().filter(~Question.answerable).label("unanswerable"),
            func.count().filter(Question.follows_id.is_not(None)).label("followups"),
            func.count()
            .filter(Question.difficulty == Question.planned_difficulty)
            .label("planned_met"),
            # How much of `cognitive_level` is a measurement. The level is
            # derived from the type, and only a few types have a label a
            # rule settles; the rest declare one nothing checked.
            func.count(
                case(
                    (
                        and_(
                            Question.status == QuestionStatus.ACCEPTED,
                            Question.question_type.in_(tuple(CHECKED)),
                        ),
                        1,
                    )
                )
            ).label("levels_checked"),
            func.coalesce(func.avg(Question.answer_chars), 0.0).label("answer"),
            func.coalesce(func.avg(func.length(Question.question_text)), 0.0).label(
                "chars"
            ),
        ).where(selected)
        grouped = {
            "rejected": Question.rejected_reason,
            "difficulty": Question.difficulty,
            "planned_difficulty": Question.planned_difficulty,
            "question_type": Question.question_type,
            "cognitive_level": Question.cognitive_level,
            "answer_form": Question.answer_form,
            "passage_scope": Question.passage_scope,
            "document_scope": Question.document_scope,
            "topic_scope": Question.topic_scope,
        }
        with self._session() as session:
            row = session.execute(totals).one()
            spread = {
                name: dict(
                    session.execute(
                        select(column, func.count())
                        .where(selected, column.is_not(None))
                        .group_by(column)
                        .order_by(func.count().desc())
                    ).all()
                )
                for name, column in grouped.items()
            }
            # Corpus-wide rather than filtered: coverage is about the topics
            # that exist, and a filter that selects no question of a topic
            # cannot say that topic is uncovered.
            covered = (
                session.scalar(
                    select(func.count())
                    .select_from(Topic)
                    .where(
                        IS_TOPIC,
                        Topic.include_in_coverage,
                        Topic.question_status == Status.GENERATED,
                    )
                )
                or 0
            )
            in_coverage = (
                session.scalar(
                    select(func.count())
                    .select_from(Topic)
                    .where(IS_TOPIC, Topic.include_in_coverage)
                )
                or 0
            )
            reach = session.execute(_COVERAGE).one()

        return QuestionQuality(
            total=row.total,
            accepted=row.accepted,
            draft=row.draft,
            unanswerable=row.unanswerable,
            followups=row.followups,
            topics_covered=covered,
            topics_in_coverage=in_coverage,
            mean_question_chars=round(float(row.chars), 1),
            mean_answer_chars=round(float(row.answer), 1),
            planned_met=row.planned_met,
            cognitive_level_checked=row.levels_checked,
            **spread,
            **reach._asdict(),
        )
