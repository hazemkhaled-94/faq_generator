"""Database access for the topic modelling service."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from sqlalchemy import case, delete, false, func, insert, select, text, update

from database.qa_generator import (
    Fact,
    FactPassage,
    Passage,
    PassageTopic,
    Status,
    Topic,
)
from database.qa_generator.passage_topics import DOMINANT as _DOMINANT
from database.qa_generator.repository import Repository
from settings.runs import run_id
from stages import Columns, StageQueue
from topic_modelling.models import (
    FittedTopic,
    Fitting,
    LanguageFit,
    PassageVocabulary,
    StoredTopic,
    TopicFit,
    TopicRemoval,
)

log = logging.getLogger(__name__)

#: A row that is a fit request rather than a topic. `topics` is both the queue
#: and the result, and this separates the two.
_OUTSTANDING = Topic.topic_index.is_(None)

#: How many passages to hold at once while streaming the corpus.
_BATCH = 500

#: A passage carrying a validated fact, which is what a fit is over where its
#: language has any. One clause for the corpus a fit reads and the count the
#: stale flag compares it with, so the two cannot come to count different
#: passages.
#:
#: ponytail: a count compares sizes, so one passage gaining its first fact as
#: another loses its last reads as unchanged. The upgrade is to compare the
#: set against the passages `passage_topics` holds.
_BEARING = (
    select(FactPassage.passage_id)
    .join(Fact, Fact.id == FactPassage.fact_id)
    .where(Fact.validated, FactPassage.passage_id == Passage.id)
    .exists()
)

#: Each topic's centroid, as the mean of its passages' vectors normalised back
#: to length 1. Written in SQL rather than by a worker: it is an average of a
#: column, so nothing has to load a model to compute it and it cannot come to
#: disagree with the passages it is the mean of.
#:
#: Unweighted over the members, because pgvector has no vector-by-scalar
#: multiply to weight them with. The membership floor has already dropped the
#: passages a topic barely holds, which is most of what a weighting would do.
_PLACE = text(
    "UPDATE topics t SET embedding = c.centroid FROM ("
    "  SELECT pt.topic_id AS id, l2_normalize(avg(p.embedding)) AS centroid"
    "  FROM passage_topics pt JOIN passages p ON p.id = pt.passage_id"
    "  WHERE p.embedding IS NOT NULL GROUP BY pt.topic_id"
    ") c WHERE t.id = c.id"
)


def _place(session) -> int:
    """Writes every topic's centroid in the caller's transaction."""
    return session.execute(_PLACE).rowcount


#: A passage the fit placed in no topic, put in its language's topic whose
#: centroid is nearest, held as weakly as the fit holds any passage of that
#: language: the vocabulary filter dropped its words, not its subject. One
#: with no vector has no nearest topic and stays out.
_NEAREST = text(
    "INSERT INTO passage_topics (passage_id, topic_id, weight) "
    "SELECT p.id, nearest.id, floor.weight FROM passages p "
    "CROSS JOIN LATERAL ("
    "  SELECT t.id FROM topics t"
    "  WHERE t.language = p.language AND t.embedding IS NOT NULL"
    "  ORDER BY t.embedding <=> p.embedding LIMIT 1"
    ") nearest "
    "CROSS JOIN LATERAL ("
    "  SELECT min(pt.weight) AS weight FROM passage_topics pt"
    "  JOIN topics t ON t.id = pt.topic_id WHERE t.language = p.language"
    ") floor "
    "WHERE p.id = ANY(:ids) AND p.embedding IS NOT NULL AND floor.weight IS NOT NULL "
    "RETURNING passage_id"
)


#: What a person decided about a topic. Only `describe` names one `person`,
#: and only it and the review pull's `cover` in `review/records.py` take one
#: out of coverage; a model's name is given again by the next fit.
_DECIDED = (Topic.labelled_by == "person") | ~Topic.include_in_coverage


def _decisions(session, *criteria) -> dict[str, list[FittedTopic]]:
    """The decisions on the topics `criteria` pick, by language."""
    held: dict[str, list[FittedTopic]] = {}
    for row in session.execute(
        select(
            Topic.language,
            Topic.topic_index,
            Topic.top_terms,
            Topic.label,
            Topic.labelled_by,
            Topic.include_in_coverage,
            Topic.decided_at,
        ).where(Topic.status == Status.MODELLED, _DECIDED, *criteria)
    ):
        held.setdefault(row.language, []).append(
            FittedTopic(
                topic_index=row.topic_index,
                top_terms=list(row.top_terms or []),
                label=row.label,
                labelled_by=row.labelled_by,
                include_in_coverage=row.include_in_coverage,
                decided_at=row.decided_at,
            )
        )
    return held


def _dominant(session, language: str) -> dict[int, int]:
    """Each passage's strongest topic in one language's stored fit, by index."""
    return {
        row.passage_id: row.topic_index
        for row in session.execute(
            select(_DOMINANT.c.passage_id, Topic.topic_index)
            .join(Topic, Topic.id == _DOMINANT.c.topic_id)
            .where(~_OUTSTANDING, Topic.language == language)
        )
    }


#: The next fit to run. Both conditions are load-bearing: status alone would
#: let a fitted topic that somehow reached `pending` be claimed as a request.
_NEXT_PENDING = (
    select(Topic.id)
    .where(_OUTSTANDING, Topic.status == Status.PENDING)
    .order_by(Topic.id)
    .with_for_update(skip_locked=True)
    .limit(1)
    .scalar_subquery()
)


class TopicQueue(StageQueue):
    """Reads the topic modelling queue and stores what each fit produced.

    Extends :class:`StageQueue` rather than :class:`RowQueue`: there is no row
    to start, because asking is what creates one, so this stage answers no
    `start` and no `reset`.
    """

    columns = Columns(
        entity=Topic,
        key=Topic.id,
        status=Topic.status,
        error=Topic.error,
        claimed_at=Topic.claimed_at,
        trigger=Topic.trigger,
    )
    done = Status.MODELLED
    next_pending = _NEXT_PENDING

    def __init__(
        self, lease: timedelta | None = None, version: str | None = None
    ) -> None:
        """Binds to the session factory, with a lease and a settings version.

        Every topic it stores records the configuration that produced it.
        """
        super().__init__(lease)
        self._version = version

    def request(self, trigger: str | None = None) -> int:
        """Asks for a fit by putting a request row on the queue.

        Deletes any request no worker holds first, so asking twice queues one
        fit and asking after a failure clears that failure. A request made
        while a fit is running is queued behind it. The topics themselves stay
        readable until a fit succeeds.

        Args:
            trigger: Which run is asking, adopted by the worker that takes
                the fit. This stage's `start`, since asking is what creates
                the work.

        Returns:
            The id of the new request row.
        """
        with self._session.begin() as session:
            session.execute(
                delete(Topic).where(_OUTSTANDING, Topic.status != Status.IN_PROGRESS)
            )
            return session.scalar(
                insert(Topic)
                .values(top_terms=[], status=Status.PENDING, trigger=trigger)
                .returning(Topic.id)
            )

    def stop(self, within: Any = None) -> int:
        """Withdraws a fit that has been asked for but not started.

        Deletes the request rather than parking it. A fit already running is
        left alone.

        Args:
            within: The base's; this stage declares no scope to narrow to.

        Returns:
            How many requests were withdrawn.
        """
        with self._session.begin() as session:
            return session.execute(
                delete(Topic).where(_OUTSTANDING, Topic.status == Status.PENDING)
            ).rowcount

    def claim(self) -> int | None:
        """Takes the next requested fit off the queue.

        Returns:
            Its id, or None if none is pending.
        """
        claimed = self._claim(Topic.id)
        return claimed.id if claimed else None

    def languages(self) -> list[str]:
        """Lists the languages the corpus holds, commonest first."""
        with self._session() as session:
            return list(
                session.scalars(
                    select(Passage.language)
                    .where(Passage.language.is_not(None))
                    .group_by(Passage.language)
                    .order_by(func.count().desc())
                ).all()
            )

    def passages(self, language: str) -> Iterator[PassageVocabulary]:
        """Streams one language's passages by id, in batches of `_BATCH`.

        Only the passages carrying a validated fact, where the language has
        any: a heading, a page number or a contents page extraction found
        nothing in still has lemmas, and fitted with the rest it pads topics
        and names them. A language with no fact yet is fitted whole, as the
        label pre-check reads it too.

        Yields:
            Each passage's id and the lemmas chunking stored for it.
        """
        with self._session() as session:
            query = select(Passage.id, Passage.lemmas).where(
                Passage.language == language
            )
            if session.scalar(select(query.where(_BEARING).exists())):
                query = query.where(_BEARING)
            rows = session.execute(
                query.order_by(Passage.id).execution_options(yield_per=_BATCH)
            )
            for row in rows:
                yield PassageVocabulary(id=row.id, lemmas=list(row.lemmas or []))

    def excerpts(self, passage_ids: list[int]) -> list[str]:
        """Reads the text of some passages, in no particular order."""
        if not passage_ids:
            return []
        with self._session() as session:
            return list(
                session.scalars(
                    select(Passage.text).where(Passage.id.in_(passage_ids))
                ).all()
            )

    def labelled_topics(self, language: str) -> list[FittedTopic]:
        """Reads one language's topics a person named or took out of coverage.

        Only `describe` and the review pull's `cover` set either, so these
        are what a person decided. A model's name is not read: the next fit
        names its topics afresh.
        """
        with self._session() as session:
            return _decisions(session, Topic.language == language).get(language, [])

    def without_topics(self) -> dict[str, int]:
        """How many of each language's fitted passages no topic holds, as stored.

        After the nearest-centroid placement, so a passage it placed is not
        counted.
        """
        with self._session() as session:
            return dict(
                session.execute(
                    select(Topic.language, func.max(Topic.passages_without_topics))
                    .where(~_OUTSTANDING)
                    .group_by(Topic.language)
                ).all()
            )

    def dominant_passages(self, language: str) -> dict[int, int]:
        """Each passage's strongest topic in one language's stored fit, by index.

        What a decision is carried by: read before `replace` takes the fit
        away.
        """
        with self._session() as session:
            return _dominant(session, language)

    def replace(
        self, fit_id: int, fittings: list[Fitting], *, keep_request: bool = False
    ) -> tuple[int, int] | None:
        """Replaces the topics and memberships of each language one run fitted.

        Every language in one transaction: a corpus holding one language's new
        topics beside another's old memberships has weights pointing at the
        wrong subjects. Takes the claimed request row with them, which is why
        this does not finish it - the new rows are written `modelled` outright.
        A request queued behind this fit is left on the queue.

        Args:
            fit_id: The request row this run claimed.
            fittings: What each language's fit produced.
            keep_request: Leave the claimed request row, for the caller to fail
                with the languages that had no model.

        Returns:
            How many memberships were written and how many decisions a person
            made were lost here, or None when the request was gone or claimed
            again and nothing was written.
        """
        with self._lock, self._session.begin() as session:
            # The request gone, or claimed again since this fit claimed it,
            # and the fit writes nothing. Locked so neither comes between.
            if (
                session.scalar(
                    select(Topic.id)
                    .where(Topic.id == fit_id, _OUTSTANDING, *self._holding(fit_id))
                    .with_for_update()
                )
                is None
            ):
                return None
            # Read as values, not as func.now(): these go into an executemany
            # below, where a SQL function cannot be a bound parameter.
            requested_at, fitted_at = session.execute(
                select(
                    select(Topic.requested_at)
                    .where(Topic.id == fit_id)
                    .scalar_subquery(),
                    func.now(),
                )
            ).one()
            # The fitted languages, and any no passage carries any more: one
            # the fit skipped, or fitted to no topic, keeps its topics, but a
            # language whose last document went is never fitted again.
            fitted = [fitting.language for fitting in fittings if fitting.topics]
            gone = Topic.language.not_in(
                select(Passage.language).where(Passage.language.is_not(None))
            )
            topics = {fitting.language: fitting.topics for fitting in fittings}
            # A decision a person made while this fit ran may postdate the
            # read the service carried decisions from, and would be deleted
            # below. Every one since the fit was asked for that the read did
            # not see is carried here; one it saw is on the topics already, or
            # was logged and counted lost, and is not again. The rows are
            # locked first, so a later one waits for this to commit and then
            # finds its topic gone, which answers 404 rather than losing it
            # quietly.
            session.execute(
                select(Topic.id)
                .where(~_OUTSTANDING, Topic.language.in_(fitted) | gone)
                .with_for_update()
            ).all()
            late = _decisions(
                session,
                Topic.language.in_(fitted),
                *([] if requested_at is None else [Topic.decided_at > requested_at]),
            )
            dropped = 0
            if late:
                # Here rather than at the top: the api reads this module, and
                # that one loads gensim.
                from topic_modelling.topics import carry_labels, dominant

                for fitting in fittings:
                    unseen = [
                        one
                        for one in late.get(fitting.language, [])
                        if one not in fitting.decisions
                    ]
                    if unseen:
                        topics[fitting.language], unmatched = carry_labels(
                            fitting.topics,
                            unseen,
                            before=_dominant(session, fitting.language),
                            after=dominant(fitting.weights),
                        )
                        dropped += unmatched
            # A language no passage carries has no new topic for a decision
            # to go to, so it is lost as one matching no topic is.
            for language, decided in _decisions(
                session, gone, Topic.language.not_in(fitted)
            ).items():
                for lost in decided:
                    log.warning(
                        "the decision on %s topic %r (in coverage: %s; terms %s) "
                        "went with its topics: no passage carries %s any more",
                        language,
                        lost.label,
                        lost.include_in_coverage,
                        ", ".join(lost.top_terms[:5]),
                        language,
                    )
                    dropped += 1
            session.execute(
                delete(Topic).where(
                    (~_OUTSTANDING & (Topic.language.in_(fitted) | gone))
                    | (false() if keep_request else Topic.id == fit_id)
                )
            )

            rows = [
                {
                    "language": fitting.language,
                    "topic_index": topic.topic_index,
                    "top_terms": topic.top_terms,
                    "label": topic.label,
                    "labelled_by": topic.labelled_by,
                    "include_in_coverage": topic.include_in_coverage,
                    "decided_at": topic.decided_at,
                    "status": Status.MODELLED,
                    "requested_at": requested_at or fitted_at,
                    "fitted_at": fitted_at,
                    "corpus_passages": fitting.passages,
                    "corpus_vocabulary": fitting.vocabulary,
                    "passages_without_topics": fitting.without_topics,
                    "settings_version": self._version,
                    "run_id": run_id(),
                    "trace_id": fitting.trace_id or None,
                    "span_id": fitting.span_id or None,
                }
                for fitting in fittings
                for topic in topics[fitting.language]
            ]
            if not rows:
                return 0, dropped
            session.execute(insert(Topic), rows)

            # Read back rather than taken from RETURNING, whose row order for
            # an executemany is not guaranteed to match the parameters. Keyed
            # by language too: an index identifies a topic only within one.
            by_index = {
                (row.language, row.topic_index): row.id
                for row in session.execute(
                    select(Topic.language, Topic.topic_index, Topic.id).where(
                        ~_OUTSTANDING
                    )
                ).all()
            }
            memberships = [
                {
                    "passage_id": weight.passage_id,
                    "topic_id": by_index[(fitting.language, weight.topic_index)],
                    "weight": weight.weight,
                }
                for fitting in fittings
                for weight in fitting.weights
            ]
            # The fit read its passages before minutes of fitting: one deleted
            # since (a document removed, a re-chunk) would fail the foreign
            # key and lose the whole fit, so only those still there are kept.
            if memberships:
                alive = set(
                    session.scalars(
                        select(Passage.id)
                        .where(
                            Passage.id.in_({one["passage_id"] for one in memberships})
                        )
                        .order_by(Passage.id)
                        .with_for_update(read=True)
                    )
                )
                memberships = [one for one in memberships if one["passage_id"] in alive]
            if memberships:
                session.execute(insert(PassageTopic), memberships)
                _place(session)
                unplaced = [one for fitting in fittings for one in fitting.unplaced]
                if unplaced:
                    placed = set(session.scalars(_NEAREST, {"ids": unplaced}).all())
                    # Their topics' centroids move with them.
                    _place(session)
                    # And they are in a topic now, which is what the stored
                    # count says of the rest.
                    for fitting in fittings:
                        if joined := len(placed.intersection(fitting.unplaced)):
                            session.execute(
                                update(Topic)
                                .where(
                                    ~_OUTSTANDING, Topic.language == fitting.language
                                )
                                .values(
                                    passages_without_topics=Topic.passages_without_topics
                                    - joined
                                )
                            )
                    return len(memberships) + len(placed), dropped
        return len(memberships), dropped

    def bearing_facts(self, passage_ids: list[int]) -> set[int]:
        """Which of these passages carry a validated fact.

        What the label pre-check reads. A passage extraction found nothing
        in is one the corpus says nothing about, whatever its terms look
        like, and that is the same signal in any language.
        """
        if not passage_ids:
            return set()
        with self._session() as session:
            return set(
                session.scalars(
                    select(FactPassage.passage_id)
                    .join(Fact, Fact.id == FactPassage.fact_id)
                    .where(Fact.validated, FactPassage.passage_id.in_(passage_ids))
                    .distinct()
                ).all()
            )

    def sizes(self, passage_ids: list[int]) -> dict[int, int]:
        """How many content lemmas each of these passages holds.

        With a passage's weight in a topic, how much of that topic it says:
        what the label excerpts are ranked by.
        """
        if not passage_ids:
            return {}
        with self._session() as session:
            return {
                row.id: row.size
                for row in session.execute(
                    select(
                        Passage.id,
                        func.coalesce(func.cardinality(Passage.lemmas), 0).label(
                            "size"
                        ),
                    ).where(Passage.id.in_(passage_ids))
                )
            }

    def counts(self) -> dict[str, int]:
        """Reports what this service owns, for the status panel.

        Returns:
            Rows by status - `modelled` counts topics, the rest count fits -
            plus the memberships held and the passages holding a topic.
        """
        with self._session() as session:
            memberships = (
                session.scalar(select(func.count()).select_from(PassageTopic)) or 0
            )
            covered = (
                session.scalar(
                    select(func.count(func.distinct(PassageTopic.passage_id)))
                )
                or 0
            )
        return {
            **self.counts_by_status(),
            "memberships": memberships,
            "passages_with_a_topic": covered,
        }

    def unplaced(self) -> int:
        """Counts the passages no topic holds."""
        with self._session() as session:
            return (
                session.scalar(
                    select(func.count())
                    .select_from(Passage)
                    .where(~Passage.id.in_(select(PassageTopic.passage_id)))
                )
                or 0
            )


class _Keep(Enum):
    """The one value meaning "this is not being changed"."""

    KEEP = "keep"


#: A label `TopicCatalog.describe` leaves as it is, with whoever gave it.
#: None cannot say that: None is how a label is cleared.
KEEP = _Keep.KEEP


class TopicCatalog(Repository):
    """Reads the fitted topics, and records what a person decided about one."""

    def describe(
        self,
        topic_id: int,
        *,
        label: str | None | _Keep = KEEP,
        include_in_coverage: bool | None,
        at: datetime | None = None,
    ) -> StoredTopic | None:
        """Records what a person decided about one topic, and when.

        A blank label clears the label and its provenance; a label present
        marks the topic `person`-named, unless it is the label it already has.

        Args:
            topic_id: The topic. A fit request is not one and is not editable.
            label: The name to record, None to clear it, or `KEEP` to leave
                it and its provenance as they are.
            include_in_coverage: Whether it counts toward coverage reporting,
                or None to leave it as it is.
            at: When the person decided, or None for now.

        Returns:
            The topic as it now reads, or None if no topic has that id.
        """
        naming = {}
        if label is not KEEP:
            named = (label or "").strip() or None
            naming = {
                "label": named,
                "labelled_by": None
                if named is None
                else case((Topic.label == named, Topic.labelled_by), else_="person"),
            }
        with self._session.begin() as session:
            changed = session.execute(
                update(Topic)
                .where(Topic.id == topic_id, ~_OUTSTANDING)
                .values(
                    **naming,
                    include_in_coverage=Topic.include_in_coverage
                    if include_in_coverage is None
                    else include_in_coverage,
                    decided_at=func.now() if at is None else at,
                )
            ).rowcount
        if not changed:
            return None
        return next(iter(self.topics(topic_id)), None)

    def delete_all(self) -> TopicRemoval:
        """Removes every topic, and with it every membership.

        Any outstanding request goes too, running or not.

        Returns:
            What went, and the languages whose figures are now orphaned.
        """
        with self._session.begin() as session:
            languages = list(
                session.scalars(
                    select(Topic.language)
                    .where(~_OUTSTANDING, Topic.language.is_not(None))
                    .distinct()
                ).all()
            )
            topics = (
                session.scalar(
                    select(func.count()).select_from(Topic).where(~_OUTSTANDING)
                )
                or 0
            )
            labels = (
                session.scalar(
                    select(func.count())
                    .select_from(Topic)
                    .where(Topic.label.is_not(None))
                )
                or 0
            )
            memberships = (
                session.scalar(select(func.count()).select_from(PassageTopic)) or 0
            )
            session.execute(delete(Topic))
        return TopicRemoval(
            topics=topics,
            memberships=memberships,
            labels=labels,
            languages=languages,
        )

    def fit_state(self) -> TopicFit:
        """Reports the state of the model, one entry per language.

        Each language carries the live passage and membership counts beside
        the ones its fit recorded, which is what makes a stale model readable.
        The live passages are counted as `passages` reads them, so a fit is
        not stale the moment it is written.
        The status and error are the newest request row's.

        Returns:
            The state of the model, or every field empty if nothing is stored.
        """
        with self._session() as session:
            outstanding = session.execute(
                select(Topic.status, Topic.error, Topic.requested_at)
                .where(_OUTSTANDING)
                .order_by(Topic.id.desc())
                .limit(1)
            ).one_or_none()
            fitted = session.execute(
                select(
                    Topic.language,
                    func.count().label("topics"),
                    func.min(Topic.requested_at).label("requested_at"),
                    func.max(Topic.fitted_at).label("fitted_at"),
                    func.max(Topic.corpus_passages).label("corpus_passages"),
                    func.max(Topic.corpus_vocabulary).label("corpus_vocabulary"),
                    func.max(Topic.passages_without_topics).label("without_topics"),
                )
                .where(~_OUTSTANDING)
                .group_by(Topic.language)
                .order_by(Topic.language)
            ).all()
            every = select(Passage.language, func.count()).where(
                Passage.language.is_not(None)
            )
            bearing = dict(
                session.execute(every.where(_BEARING).group_by(Passage.language)).all()
            )
            # What `passages` would fit now: a language with no fact yet is
            # fitted whole.
            live = {
                language: bearing.get(language) or count
                for language, count in session.execute(
                    every.group_by(Passage.language)
                ).all()
            }
            held = dict(
                session.execute(
                    select(Topic.language, func.count(PassageTopic.passage_id))
                    .join(PassageTopic, PassageTopic.topic_id == Topic.id)
                    .where(~_OUTSTANDING)
                    .group_by(Topic.language)
                ).all()
            )
            unplaced = (
                session.scalar(
                    select(func.count())
                    .select_from(Passage)
                    .where(Passage.language.is_(None))
                )
                or 0
            )

        languages = [
            LanguageFit(
                language=row.language,
                topics=row.topics,
                corpus_passages=row.corpus_passages,
                corpus_vocabulary=row.corpus_vocabulary,
                passages_without_topics=row.without_topics,
                fitted_at=row.fitted_at.isoformat() if row.fitted_at else None,
                live_passages=live.get(row.language, 0),
                memberships=held.get(row.language, 0),
            )
            for row in fitted
        ]
        requested_at = (
            outstanding.requested_at
            if outstanding
            else min((row.requested_at for row in fitted), default=None)
        )
        return TopicFit(
            status=(outstanding.status if outstanding else Status.MODELLED)
            if (outstanding or fitted)
            else None,
            error=outstanding.error if outstanding else None,
            requested_at=requested_at.isoformat() if requested_at else None,
            topics=sum(row.topics for row in fitted),
            languages=languages,
            passages_without_language=unplaced,
        )

    def topics(self, topic_id: int | None = None) -> list[StoredTopic]:
        """Reads the fitted topics with how much of the corpus each holds.

        Args:
            topic_id: Only this topic, or None for every one.

        Returns:
            One entry per topic, ordered by language then topic index.
        """
        # Three queries, not one. Folding either of the first two into the
        # aggregate below would join a second row per passage and inflate both
        # the membership count and the mean weight.
        dominant = [] if topic_id is None else [_DOMINANT.c.topic_id == topic_id]
        chosen = [] if topic_id is None else [Topic.id == topic_id]
        with self._session() as session:
            # Over the passages this topic is dominant in rather than every
            # passage holding it: a passage belongs to several topics.
            owned = {
                row.topic_id: row
                for row in session.execute(
                    select(
                        _DOMINANT.c.topic_id,
                        func.count().label("passages"),
                        func.count()
                        .filter(Passage.block_type == "table")
                        .label("tables"),
                    )
                    .join(Passage, Passage.id == _DOMINANT.c.passage_id)
                    .where(*dominant)
                    .group_by(_DOMINANT.c.topic_id)
                ).all()
            }
            drawn = dict(
                session.execute(
                    # Distinct: a bridge rests on several passages, and two
                    # of them dominant in one topic would count it twice.
                    select(_DOMINANT.c.topic_id, func.count(func.distinct(Fact.id)))
                    .join(
                        FactPassage,
                        FactPassage.passage_id == _DOMINANT.c.passage_id,
                    )
                    .join(Fact, (Fact.id == FactPassage.fact_id) & Fact.validated)
                    .where(*dominant)
                    .group_by(_DOMINANT.c.topic_id)
                ).all()
            )
            rows = session.execute(
                select(
                    Topic.id,
                    Topic.language,
                    Topic.topic_index,
                    Topic.top_terms,
                    Topic.label,
                    Topic.labelled_by,
                    Topic.include_in_coverage,
                    func.count(PassageTopic.passage_id).label("passages"),
                    func.coalesce(func.avg(PassageTopic.weight), 0.0).label(
                        "mean_weight"
                    ),
                    func.count(func.distinct(Passage.doc_sha256)).label("documents"),
                )
                .join(PassageTopic, PassageTopic.topic_id == Topic.id, isouter=True)
                .join(Passage, Passage.id == PassageTopic.passage_id, isouter=True)
                .where(~_OUTSTANDING, *chosen)
                .group_by(Topic.id)
                .order_by(Topic.language, Topic.topic_index)
            ).all()
        return [
            StoredTopic(
                id=row.id,
                language=row.language,
                topic_index=row.topic_index,
                top_terms=list(row.top_terms or []),
                label=row.label,
                labelled_by=row.labelled_by,
                include_in_coverage=row.include_in_coverage,
                passages=row.passages,
                dominant_passages=owned[row.id].passages if row.id in owned else 0,
                mean_weight=float(row.mean_weight),
                documents=row.documents,
                table_passages=owned[row.id].tables if row.id in owned else 0,
                validated_facts=drawn.get(row.id, 0),
            )
            for row in rows
        ]
