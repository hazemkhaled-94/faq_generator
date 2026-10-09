"""The queue this stage claims artefacts from, and what it writes back.

Reads the database models directly and no other service's repository. That
is the independence contract in `.importlinter`, and it is also the right
shape here: this stage is about facts, topics and questions at once, and a
package importing all three services to read them would weld the four
together.
"""

from __future__ import annotations

from typing import Any, ClassVar

from sqlalchemy import (
    Select,
    Text,
    and_,
    case,
    delete,
    func,
    literal,
    literal_column,
    or_,
    select,
    union_all,
    update,
)
from sqlalchemy import insert as sa_insert
from sqlalchemy.dialects.postgresql import aggregate_order_by, array_agg, insert
from sqlalchemy.orm import InstrumentedAttribute

from assessment.models import (
    ArtifactToJudge,
    Assessed,
    AssessmentQuality,
    MetricQuality,
    StoredAssessment,
    StoredMetric,
)
from assessment.templates import TEMPLATES, direction_of
from database.qa_generator import (
    ArtifactKind,
    Assessment,
    AssessmentMetric,
    Fact,
    FactPassage,
    Passage,
    Question,
    QuestionFact,
    QuestionStatus,
    Status,
    Topic,
)
from database.qa_generator.repository import Repository, matching
from settings.runs import run_id
from stages import Columns, RowQueue

#: A topic rather than a request to refit. `topics` carries both queues on
#: one table, and only the topics are artefacts anybody has an opinion
#: about.
_IS_TOPIC = Topic.topic_index.is_not(None)

#: The questions this stage judges. Answerable and answered: two of the
#: three metrics ask whether the facts support the answer, and an unanswerable question has
#: no answer for them to support. Those are written deliberately, to test
#: whether a chatbot admits it does not know, and scoring them here would
#: report the pipeline's most careful output as its worst.
_JUDGEABLE_QUESTION = and_(
    Question.answerable.is_(True),
    Question.target_answer.is_not(None),
    Question.status != QuestionStatus.DRAFT,
)

#: The next artefact to judge. FOR UPDATE SKIP LOCKED, so scaling the
#: worker past one takes the next row rather than the same one.
_NEXT_PENDING = (
    select(Assessment.id)
    .where(Assessment.assess_status == Status.PENDING)
    .order_by(Assessment.id)
    .with_for_update(skip_locked=True)
    .limit(1)
    .scalar_subquery()
)

#: A verdict standing on fewer metrics than its version asked for.
_THIN = and_(
    Assessment.metrics_due.is_not(None),
    select(func.count())
    .select_from(AssessmentMetric)
    .where(AssessmentMetric.assessment_id == Assessment.id)
    .scalar_subquery()
    < Assessment.metrics_due,
)

#: `approved` as every reader takes it: NULL for a thin verdict, which is
#: neither approved nor refused.
APPROVED = case((_THIN, None), else_=Assessment.approved)

#: How many facts one question's judgement is shown. A question rests on
#: one or two, so this is a ceiling against a pathological row rather than
#: a sample: past it the prompt outgrows the window, and a prompt over the
#: window is truncated and answered anyway.
_FACTS_SHOWN = 8

#: What the pipeline's own checker or gates decided about each artefact,
#: as one word. `accepted` where nothing refused it or a person accepted a
#: question over a gate, so it reads the same for all three kinds and the
#: judge's verdict can be put beside it.
_VERDICT: dict[str, Any] = {
    ArtifactKind.FACT: func.coalesce(Fact.rejection_code, "accepted"),
    ArtifactKind.TOPIC: case(
        (Topic.include_in_coverage.is_(True), "accepted"), else_="out_of_coverage"
    ),
    ArtifactKind.QUESTION: case(
        (Question.status == QuestionStatus.ACCEPTED, "accepted"),
        else_=func.coalesce(Question.rejected_reason, Question.status),
    ),
}

#: The artefact in one line, for a table cell and a workbook row.
_SUMMARY: dict[str, Any] = {
    ArtifactKind.FACT: Fact.statement,
    ArtifactKind.TOPIC: func.coalesce(Topic.label, "(the model named nothing)"),
    ArtifactKind.QUESTION: Question.question_text,
}

#: Which column links an assessment to each kind's table.
_LINK: dict[str, tuple[Any, Any, Any]] = {
    ArtifactKind.FACT: (Assessment.fact_id, Fact, Fact.id),
    ArtifactKind.TOPIC: (Assessment.topic_id, Topic, Topic.id),
    ArtifactKind.QUESTION: (Assessment.question_id, Question, Question.id),
}


def _question_facts():
    """The facts one question rests on, as the list a template takes."""
    # The first _FACTS_SHOWN by id, so two runs show one question the same list.
    listed = array_agg(aggregate_order_by(func.concat("- ", Fact.statement), Fact.id))
    return (
        select(func.array_to_string(listed[1:_FACTS_SHOWN], "\n"))
        .select_from(QuestionFact)
        .join(Fact, Fact.id == QuestionFact.fact_id)
        .where(QuestionFact.question_id == Question.id)
        .scalar_subquery()
    )


def _fields_query(kind: str, artifact_id: int) -> Select:
    """What one artefact's templates substitute, as a query for one row."""
    if kind == ArtifactKind.FACT:
        return select(
            Fact.statement.label("statement"), Fact.evidence_text.label("evidence")
        ).where(Fact.id == artifact_id)
    if kind == ArtifactKind.TOPIC:
        return select(
            func.array_to_string(Topic.top_terms, ", ").label("terms"),
            func.coalesce(Topic.label, "(the model named nothing)").label("label"),
        ).where(Topic.id == artifact_id)
    return select(
        Question.question_text.label("question"),
        func.coalesce(Question.target_answer, "").label("answer"),
        func.coalesce(_question_facts(), "(none recorded)").label("facts"),
    ).where(Question.id == artifact_id)


class AssessmentQueue(RowQueue):
    """The assessments queue: enrolling artefacts, and judging them.

    Unlike every other row-based stage, nothing upstream creates these
    rows. Extraction hands its facts to nobody and topic modelling hands
    its topics to nobody, so `start` **enrols** whatever has no assessment
    and then queues it. That is topic modelling's arrangement - asking is
    what creates the work - reached from the other direction.

    Enrolment ignores any narrowing, and `start` narrows only the requeue
    after it. A row sitting `new` costs nothing and no worker looks at one,
    so enrolling a kind nobody asked to judge yet is free; the alternative
    was reading a value back out of a SQLAlchemy condition, which is a
    thing this codebase does nowhere else.
    """

    columns: ClassVar[Columns] = Columns(
        entity=Assessment,
        key=Assessment.id,
        status=Assessment.assess_status,
        error=Assessment.assess_error,
        claimed_at=Assessment.assess_claimed_at,
        trigger=Assessment.assess_trigger,
    )
    #: Narrowed to one kind, which is how `--only kind=question` judges the
    #: questions without paying for twenty thousand facts.
    scopes: ClassVar[dict[str, InstrumentedAttribute]] = {
        "kind": Assessment.artifact_kind
    }
    done: ClassVar[Status] = Status.ASSESSED
    next_pending: ClassVar[Any] = _NEXT_PENDING

    def __init__(
        self,
        *,
        kinds: tuple[str, ...] | None = None,
        sample: int | None = None,
        stratify: bool | None = None,
        version: str | None = None,
    ) -> None:
        """Binds the queue, with what to enrol and what to stamp on a verdict.

        `kinds` and `sample` of None are read from the SETTINGS when an
        enrolment actually happens, rather than defaulted here. The worker
        passes both, because it has already resolved them to stamp the
        version beside them; the api passes neither, and a default of
        "every kind, every row" is what that turned into.

        That default enrolled 11,392 artefacts the first time
        `POST /assessment/enrol` was called against a deployment whose
        ASSESSMENT_SAMPLE was 200 - and `start`, which enrols and then
        queues, would have put all of them in front of the judge at three
        to six model calls each.
        """
        super().__init__()
        self._kinds = tuple(kinds) if kinds else None
        self._sample = sample
        self._stratify = stratify
        self._version = version

    def _asked(self) -> tuple[tuple[str, ...], int, bool]:
        """Which kinds to enrol, how many of each and how, as they stand now.

        Read per call rather than per instance: the api builds this queue
        once at import and serves it for the life of the process, so a
        setting changed through the Configuration panel has to reach it
        without a restart.
        """
        if (
            self._kinds is not None
            and self._sample is not None
            and self._stratify is not None
        ):
            return self._kinds, self._sample, self._stratify
        from assessment.config import Settings, judged_kinds
        from settings.store import resolved

        settings = Settings.load(resolved())
        if not settings.enabled:
            # The phase off enrols nothing, as ASSESSMENT_ENABLED says.
            return (), 0, False
        return (
            self._kinds if self._kinds is not None else judged_kinds(settings),
            self._sample if self._sample is not None else settings.sample,
            self._stratify if self._stratify is not None else settings.stratify,
        )

    # ── Enrolling ────────────────────────────────────────────────────────

    def enrol(self) -> int:
        """Creates a `new` assessment for every artefact that has none.

        `ON CONFLICT DO NOTHING` against each kind's unique key, so running
        this twice enrols only what arrived in between: a re-run over a
        judged corpus costs one statement per kind rather than a model call
        per row.

        Returns:
            How many artefacts were enrolled.
        """
        kinds, sample, stratify = self._asked()
        with self._session.begin() as session:
            # Counted off RETURNING rather than off `rowcount`. An
            # `ON CONFLICT DO NOTHING` that inserted nothing reports -1,
            # not 0, so three kinds already enrolled summed to -3 and a
            # second `start` claimed to have un-enrolled the corpus.
            return sum(
                len(session.execute(self._enrolment(kind, sample, stratify)).fetchall())
                for kind in kinds
            )

    def _enrolment(self, kind: str, sample: int, stratify: bool = False):
        """The INSERT that enrols one kind's artefacts."""
        enrolled: dict[str, tuple[Select, str, tuple]] = {
            ArtifactKind.FACT: (
                select(Fact.id)
                .join(
                    FactPassage,
                    (FactPassage.fact_id == Fact.id) & (FactPassage.position == 0),
                )
                .join(Passage, Passage.id == FactPassage.passage_id)
                .order_by(Fact.id.desc()),
                "fact_id",
                (Passage.language,),
            ),
            ArtifactKind.TOPIC: (
                select(Topic.id).where(_IS_TOPIC).order_by(Topic.id.desc()),
                "topic_id",
                (Topic.language,),
            ),
            ArtifactKind.QUESTION: (
                select(Question.id)
                .where(_JUDGEABLE_QUESTION)
                .order_by(Question.id.desc()),
                "question_id",
                (Question.language, Question.question_type),
            ),
        }
        source, column, bands = enrolled[kind]
        # Newest first, so a sample of a corpus judged once already is the
        # part that arrived since rather than the part judged before.
        # Stratified, the first of every band in an order fixed by a hash of
        # the id, then the second, so a sample spans every band and a second
        # draw over the same corpus is the first.
        # ponytail: an artefact arriving after a draw that hashes into its
        # band's first places is enrolled by the next stratified start, so
        # the sample grows with the corpus. The upgrade is recording which
        # draw enrolled a row, which needs a column.
        if stratify:
            shuffled = func.md5(source.selected_columns[0].cast(Text))
            source = source.order_by(None).order_by(
                func.row_number().over(partition_by=bands, order_by=shuffled),
                shuffled,
            )
        if sample > 0:
            source = source.limit(sample)
        chosen = source.subquery()
        return (
            insert(Assessment)
            .from_select(
                ["artifact_kind", column],
                select(literal(kind), chosen.c.id).select_from(chosen),
            )
            .on_conflict_do_nothing(index_elements=[column])
            .returning(Assessment.id)
        )

    def start(self, within: Any = None, *, trigger: str | None = None) -> int:
        """Enrols whatever has no assessment, then queues everything new.

        Both halves, because a `start` that only requeued would do nothing
        at all the first time: there would be no row to move.
        """
        self.enrol()
        return super().start(within, trigger=trigger)

    def reset(self, within: Any = None, *, trigger: str | None = None) -> int:
        """Enrols anything new, then queues every row again.

        A re-run under a changed template is what this serves. The verdict
        of every row queued again is cleared first, so a row waiting to be
        judged, or one whose re-run fails, holds no opinion from a template
        version that is no longer current.
        """
        self.enrol()
        chosen = select(Assessment.id).where(
            Assessment.assess_status != Status.IN_PROGRESS
        )
        if within is not None:
            chosen = chosen.where(within)
        with self._session.begin() as session:
            session.execute(
                delete(AssessmentMetric).where(
                    AssessmentMetric.assessment_id.in_(chosen)
                )
            )
            session.execute(
                update(Assessment)
                .where(Assessment.id.in_(chosen))
                .values(
                    approved=None,
                    assessed_at=None,
                    metrics_due=None,
                    judge_model=None,
                    prompt_version=None,
                )
            )
        return super().reset(within, trigger=trigger)

    # ── Claiming and recording ───────────────────────────────────────────

    def claim(self) -> ArtifactToJudge | None:
        """Takes the next artefact and reads the text its templates need.

        Two statements rather than one join. The claim has to be a short
        transaction because the judging after it takes minutes, and the
        text is read once the row is safely this worker's.
        """
        while True:
            taken = self._claim(
                Assessment.id,
                Assessment.artifact_kind,
                Assessment.fact_id,
                Assessment.topic_id,
                Assessment.question_id,
            )
            if taken is None:
                return None
            # By name rather than by position: `_claim` appends the row's
            # trigger to whatever a stage asked it to return.
            assessment_id, kind = taken.id, taken.artifact_kind
            held: dict[str, int] = {
                ArtifactKind.FACT: taken.fact_id,
                ArtifactKind.TOPIC: taken.topic_id,
                ArtifactKind.QUESTION: taken.question_id,
            }
            artifact_id = held[kind]
            with self._session() as session:
                row = (
                    session.execute(_fields_query(kind, artifact_id)).mappings().first()
                )
            if row is not None:
                return ArtifactToJudge(
                    assessment_id=assessment_id,
                    kind=kind,
                    artifact_id=artifact_id,
                    fields={name: str(value) for name, value in row.items()},
                )
            # The artefact went between the claim and this read: a delete
            # landed mid-drain. Nothing to judge, so the next row is taken.
            self._finish(assessment_id)

    def record(self, assessed: Assessed) -> None:
        """Writes one artefact's verdict and every metric behind it.

        One transaction: a verdict whose metrics did not land would be a
        row saying the judge approved with nothing saying why.
        """
        with self._session.begin() as session:
            # Deleted rather than upserted. A re-run under a template
            # version asking fewer metrics would otherwise leave the metric
            # it no longer asks about sitting under the new verdict.
            session.execute(
                delete(AssessmentMetric).where(
                    AssessmentMetric.assessment_id == assessed.assessment_id
                )
            )
            if assessed.judgements:
                session.execute(
                    sa_insert(AssessmentMetric),
                    [
                        {
                            "assessment_id": assessed.assessment_id,
                            "metric": one.metric,
                            "label": one.label,
                            "score": one.score,
                            "approved": one.approved,
                            "explanation": one.explanation,
                        }
                        for one in assessed.judgements
                    ],
                )
            self._finish(
                assessed.assessment_id,
                session=session,
                approved=assessed.approved,
                judge_model=assessed.judge_model,
                prompt_version=assessed.prompt_version,
                metrics_due=assessed.metrics_due or None,
                settings_version=self._version,
                run_id=run_id(),
                trace_id=assessed.trace_id or None,
                span_id=assessed.span_id or None,
                assessed_at=func.now(),
            )

    def counts(self) -> dict[str, int]:
        """The queue depth, and how the verdicts came out.

        What the system status panel shows for this stage, in the shape the
        other five answer in.
        """
        counts = dict(self.counts_by_status())
        with self._session() as session:
            counts |= (
                session.execute(
                    select(
                        func.count().filter(APPROVED.is_(True)).label("approved"),
                        func.count().filter(APPROVED.is_(False)).label("refused"),
                        # Counted here rather than left to whoever writes the
                        # query, because the row is `assessed` either way and
                        # `retry` cannot find it: nothing failed, the judge was
                        # simply unreachable for part of it. `metrics_due` is
                        # what makes this SQL rather than code.
                        func.count().filter(_THIN).label("thin"),
                    ).select_from(Assessment)
                )
                .one()
                ._asdict()
            )
        return counts


class AssessmentCatalog(Repository):
    """Reading the verdicts back. Never claims a row.

    The API's half, and the page's and the workbook's. Separate from the
    queue for the reason every other stage keeps the pair: the api process
    must be able to read what a worker produced without holding anything
    that could claim it.
    """

    def page(
        self,
        kind: str | None = None,
        approved: bool | None = None,
        metric: str | None = None,
        disagreements: bool = False,
        search: str | None = None,
        field: str = "both",
        limit: int | None = 50,
        offset: int = 0,
    ) -> tuple[int, list[StoredAssessment]]:
        """One page of assessments, and the total behind it.

        `disagreements` narrows to the rows worth a person's time: the
        artefacts the pipeline KEPT and the judge refused. One direction
        only - the other is usually a rejection for something the judge was never asked about.
        """
        kinds = self._kinds(kind)
        # UNION ALL of the three per-kind selects, windowed once over the
        # result. Each kind reaches its artefact through a different
        # foreign key, so there is no one join that serves all three - but
        # paging each kind separately and slicing afterwards is not the
        # same query: page two would be each kind's second page, which
        # skips rows nobody asked to skip and repeats rows already shown.
        wanted = union_all(
            *(
                self._of_kind(one, approved, metric, disagreements, search, field)
                for one in kinds
            )
        )
        counting = select(func.count()).select_from(wanted.subquery())
        paged = wanted.order_by(literal_column("id").desc())
        if limit is not None:
            paged = paged.limit(limit).offset(offset)

        with self._session() as session:
            total = session.execute(counting).scalar() or 0
            found = session.execute(paged).all()
            metrics = self._metrics(session, [row.id for row in found])

        return total, [
            StoredAssessment(**row._asdict(), metrics=metrics.get(row.id, []))
            for row in found
        ]

    @staticmethod
    def _kinds(kind: str | None) -> tuple[str, ...]:
        """Which kinds a filter selects."""
        return (kind,) if kind else tuple(TEMPLATES)

    def _selected(
        self,
        kind: str,
        approved: bool | None,
        metric: str | None,
        disagreements: bool,
        search: str | None = None,
        field: str = "both",
    ):
        """The conditions one kind's filter selects."""
        link, entity, key = _LINK[kind]
        where: list[Any] = [Assessment.artifact_kind == kind]
        if approved is not None:
            where.append(APPROVED.is_(approved))
        if disagreements:
            where.append(APPROVED.is_(False))
            where.append(_VERDICT[kind] == "accepted")
        if metric:
            where.append(
                select(literal(1))
                .select_from(AssessmentMetric)
                .where(
                    AssessmentMetric.assessment_id == Assessment.id,
                    AssessmentMetric.metric == metric,
                    AssessmentMetric.approved.is_(False),
                )
                .exists()
            )
        if search:
            where.append(self._searched(kind, search, field))
        return link, entity, key, where

    @staticmethod
    def _searched(kind: str, search: str, field: str):
        """The condition a search box's words select.

        Two places worth looking, and they answer different questions. The
        ARTEFACT is "which fact was this about"; the judge's EXPLANATION is
        "what did it say about them" - and the second is the one nothing
        else in this repository can search, because until this phase there
        were no model opinions stored to search.

        `matching` rather than a hand-rolled ILIKE, for the reason it
        exists: without `autoescape` a `%` somebody typed is a wildcard.
        """
        artefact = matching(search, _SUMMARY[kind])
        explained = (
            select(literal(1))
            .select_from(AssessmentMetric)
            .where(
                AssessmentMetric.assessment_id == Assessment.id,
                matching(search, AssessmentMetric.explanation),
            )
            .exists()
        )
        if field == "artifact":
            return artefact
        if field == "explanation":
            return explained
        return or_(artefact, explained)

    def _of_kind(
        self,
        kind: str,
        approved: bool | None,
        metric: str | None,
        disagreements: bool,
        search: str | None = None,
        field: str = "both",
    ) -> Select:
        """One kind's rows, as a select the union windows over.

        Every kind produces the same fourteen columns in the same order,
        which is what lets the three be unioned. `verdict` and `summary`
        are the two that differ per kind: a fact's verdict is its
        rejection code, a topic's is whether it is in coverage, and a
        question's is its gate.
        """
        link, entity, key, where = self._selected(
            kind, approved, metric, disagreements, search, field
        )
        return (
            select(
                Assessment.id.label("id"),
                Assessment.artifact_kind.label("kind"),
                link.label("artifact_id"),
                Assessment.assess_status.label("status"),
                APPROVED.label("approved"),
                Assessment.judge_model.label("judge_model"),
                Assessment.prompt_version.label("prompt_version"),
                Assessment.run_id.label("run_id"),
                Assessment.trace_id.label("trace_id"),
                Assessment.span_id.label("span_id"),
                Assessment.assessed_at.label("assessed_at"),
                Assessment.assess_error.label("error"),
                _VERDICT[kind].label("verdict"),
                _SUMMARY[kind].label("summary"),
            )
            .join(entity, key == link)
            .where(*where)
        )

    @staticmethod
    def _metrics(session: Any, ids: list[int]) -> dict[int, list[StoredMetric]]:
        """Every metric of some assessments, by assessment.

        One query for the page rather than one per row: a table of fifty
        rows is fifty round trips otherwise, and the page polls.
        """
        if not ids:
            return {}
        held: dict[int, list[StoredMetric]] = {}
        for row in session.execute(
            select(
                AssessmentMetric.assessment_id,
                AssessmentMetric.metric,
                AssessmentMetric.label,
                AssessmentMetric.score,
                AssessmentMetric.approved,
                AssessmentMetric.explanation,
            )
            .where(AssessmentMetric.assessment_id.in_(ids))
            .order_by(AssessmentMetric.assessment_id, AssessmentMetric.metric)
        ).all():
            fields = row._asdict()
            held.setdefault(fields.pop("assessment_id"), []).append(
                StoredMetric(**fields)
            )
        return held

    def quality(self, kind: str | None = None) -> AssessmentQuality:
        """What the judge made of the corpus, as counts.

        Served by the API, drawn by the page and written onto the
        workbook's own sheet, so the figures in an export are the figures
        that were on screen.
        """
        kinds = self._kinds(kind)
        with self._session() as session:
            by_kind: dict[str, int] = {}
            approved_by_kind: dict[str, int] = {}
            disagreements = 0
            total = judged = approved = 0
            for one in kinds:
                link, entity, key = _LINK[one]
                counted, judged_one, approved_one, disagreed = session.execute(
                    select(
                        func.count(),
                        func.count().filter(APPROVED.is_not(None)),
                        func.count().filter(APPROVED.is_(True)),
                        func.count().filter(
                            and_(
                                APPROVED.is_(False),
                                _VERDICT[one] == "accepted",
                            )
                        ),
                    )
                    .select_from(Assessment)
                    .join(entity, key == link)
                    .where(Assessment.artifact_kind == one)
                ).one()
                by_kind[one] = counted
                approved_by_kind[one] = approved_one
                total += counted
                judged += judged_one
                approved += approved_one
                disagreements += disagreed

            metrics = [
                MetricQuality(**row._asdict(), direction=direction_of(row.metric))
                for row in session.execute(
                    select(
                        AssessmentMetric.metric,
                        func.count().label("judged"),
                        func.count()
                        .filter(AssessmentMetric.approved.is_(True))
                        .label("approved"),
                    )
                    .join(Assessment, Assessment.id == AssessmentMetric.assessment_id)
                    .where(Assessment.artifact_kind.in_(kinds))
                    .group_by(AssessmentMetric.metric)
                    .order_by(AssessmentMetric.metric)
                ).all()
            ]
            models = list(
                session.scalars(
                    select(Assessment.judge_model)
                    .where(
                        Assessment.judge_model.is_not(None),
                        Assessment.artifact_kind.in_(kinds),
                    )
                    .distinct()
                    .order_by(Assessment.judge_model)
                ).all()
            )

        return AssessmentQuality(
            total=total,
            judged=judged,
            approved=approved,
            refused=judged - approved,
            disagreements=disagreements,
            by_kind=by_kind,
            approved_by_kind=approved_by_kind,
            metrics=metrics,
            judge_models=models,
            outstanding=total - judged,
        )

    def verdicts_for(self, kind: str, ids: list[int]) -> dict[int, StoredAssessment]:
        """The assessments of some artefacts, by artefact id.

        What `review/` and the workbook need: they hold rows already and
        want the judge's opinion attached to each, without a query per row.
        """
        if not ids:
            return {}
        link, entity, key = _LINK[kind]
        with self._session() as session:
            found = session.execute(
                select(
                    Assessment.id,
                    link.label("artifact_id"),
                    APPROVED.label("approved"),
                    Assessment.judge_model,
                    Assessment.assessed_at,
                    _VERDICT[kind].label("verdict"),
                    Assessment.assess_status.label("status"),
                )
                .join(entity, key == link)
                .where(Assessment.artifact_kind == kind, link.in_(ids))
            ).all()
            metrics = self._metrics(session, [row.id for row in found])
        return {
            row.artifact_id: StoredAssessment(
                **row._asdict(),
                kind=kind,
                prompt_version=None,
                run_id=None,
                trace_id=None,
                span_id=None,
                error=None,
                metrics=metrics.get(row.id, []),
            )
            for row in found
        }
