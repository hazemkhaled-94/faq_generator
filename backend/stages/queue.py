"""The queue every pipeline stage runs on.

A stage owns a status column, an error column and the timestamp of its claim.
Claiming, failing, sweeping an abandoned claim and requeueing are written here
once against those declarations.

A row arrives `new` and no worker looks at it until something asks for it, so
a stage claims on its own status column and on nothing else. The one thing
read beside it is `RowQueue.ready`, which says which rows may be QUEUED - see
there for why chunking is the only stage that needs it.

Every queue operation takes an optional `within`, which narrows it to part of
the queue - one document, one passage - instead of all of it. A stage says
which narrowings it accepts by declaring `scopes`; the route and the command
line both build theirs through :meth:`StageQueue.narrow`, so neither learns a
column name.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, ClassVar

from sqlalchemy import func, literal_column, or_, select, update
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import InstrumentedAttribute

from database.qa_generator import Status
from database.qa_generator.repository import Repository
from database.qa_generator.revision import applied, heads
from settings.runs import triggered_by

log = logging.getLogger(__name__)

#: Recorded against a row whose worker never came back.
ABANDONED = "the worker did not finish; the run was interrupted"


class Lost(Exception):
    """A row this worker claimed has been claimed by another one since.

    Raised by a finish or a failure, which then writes nothing.
    """


class Gone(Lost):
    """A row this worker claimed no longer exists: it was deleted meanwhile.

    A `Lost` too, since the write goes nowhere, but not another worker's
    doing, and the log must not say it was.
    """


class Unnarrowable(Exception):
    """A narrowing a stage cannot make, and why.

    One exception rather than the KeyError and ValueError `narrow` raises,
    because the route and the command line answer the same two refusals and
    would otherwise each spell out the same two messages. `code` is what the
    API answers with; the command line reads only the message.
    """

    def __init__(self, code: str, detail: str) -> None:
        """Initialises the refusal."""
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True)
class Columns:
    """The pair of columns a stage owns, plus the time of its claim."""

    entity: type
    key: InstrumentedAttribute
    status: InstrumentedAttribute
    error: InstrumentedAttribute
    claimed_at: InstrumentedAttribute
    #: Which run asked for this row, written by whatever queued it and read
    #: back when a worker claims it. Optional so a queue can be declared
    #: without one; every stage here has one.
    trigger: InstrumentedAttribute | None = None


@dataclass(frozen=True)
class QueueState:
    """How much work a stage has waiting, and whether anyone is on it."""

    working: bool
    rows: dict[str, int]
    #: Per status, a digest of which rows it holds and which run asked for
    #: each. Equal counts with another digest are other rows.
    digests: dict[str, str]


class StageQueue(Repository):
    """One stage's view of its queue.

    Subclasses declare which columns are theirs; every method below is written
    against those declarations rather than against a column name.
    """

    #: The three columns this stage owns. Held in a value object rather than
    #: as three class attributes: a mapped column is a descriptor, so naming
    #: one directly on this class would make `self.status` try to read the
    #: repository as if it were a row.
    columns: ClassVar[Columns]
    #: Which columns a caller may narrow an operation to, by the name the
    #: route and the command line take. Empty means this stage answers for
    #: the whole queue only, which is true of anything fitted all at once.
    scopes: ClassVar[dict[str, InstrumentedAttribute]] = {}
    #: Which rows of the table are this queue's at all, when the table holds
    #: rows that are not. Every operation below carries it, so a stage cannot
    #: start, sweep or count a row that is none of its business: topics holds
    #: both the fit requests and the topics, and only the topics are a unit
    #: of question generation.
    base: ClassVar[Any] = None
    #: The status this stage sets when it finishes a row.
    done: ClassVar[Status]
    #: How long a claim may go unrefreshed before a later run treats it as
    #: abandoned. A worker holding a row refreshes it every
    #: `stages.service.HEARTBEAT_SECONDS`, so this bounds how long a DEAD
    #: worker's row stays claimed and not how long the work may take. Ten
    #: missed beats.
    lease: timedelta = timedelta(minutes=5)
    #: Selects the key of the next row this stage should take.
    next_pending: ClassVar[Any]

    _REQUIRED = ("columns", "done", "next_pending")

    def __init_subclass__(cls, *, abstract: bool = False, **kwargs: Any) -> None:
        """Refuses a stage that has not said which columns are its own.

        `abstract=True` exempts a base that declares no columns of its own.
        """
        super().__init_subclass__(**kwargs)
        if abstract:
            return
        missing = [name for name in StageQueue._REQUIRED if not hasattr(cls, name)]
        if missing:
            raise TypeError(
                f"{cls.__name__} is a StageQueue but does not declare "
                f"{', '.join(missing)}."
            )

    def __init__(self, lease: timedelta | None = None) -> None:
        """Binds to the session factory, optionally with a longer lease."""
        super().__init__()
        if lease is not None:
            self.lease = lease
        #: The key of the row this instance holds and the claim time it last
        #: wrote, for `touch` to refresh and for a finish or a failure to
        #: check. Written by the thread that works the row and read by the
        #: one that beats; a lone reference, so neither sees half of it.
        self._held: tuple[Any, Any] | None = None
        #: Taken around every statement that reads or moves the claim time,
        #: so a beat cannot move it between a finish reading it and writing.
        self._lock = threading.Lock()
        #: Whether this instance has said the schema is not the code's head.
        self._behind = False

    def _where(self, *conditions: Any) -> tuple[Any, ...]:
        """This queue's own rows, narrowed by whatever the caller gave.

        `where()` takes no None, and every operation below is written once
        for the narrowed and the whole-queue case.
        """
        return tuple(
            condition for condition in (self.base, *conditions) if condition is not None
        )

    def _claim(self, *returning: InstrumentedAttribute, pending: Any = None):
        """Takes the next pending row and marks it in progress.

        Also adopts whatever run queued the row, so everything this worker
        writes while it holds it is stamped with the run that asked rather
        than with the worker's own process. See `settings.runs`.

        `pending` selects the row to take where it is not `next_pending`.
        """
        trigger = self.columns.trigger
        asked = () if trigger is None else (trigger,)
        # A short transaction, not a held row lock: the work runs for seconds
        # or minutes. The claim is timestamped so a later run can tell it from
        # a live one.
        with self._session.begin() as session:
            claimed = (
                session.execute(
                    update(self.columns.entity)
                    .where(
                        self.columns.key
                        == (self.next_pending if pending is None else pending)
                    )
                    .values(
                        {
                            self.columns.status: Status.IN_PROGRESS,
                            self.columns.claimed_at: func.now(),
                        }
                    )
                    .returning(*returning, self.columns.claimed_at, *asked)
                ).one_or_none()
                if self._at_head(session)
                else None
            )
        # Every caller returns its key column first, which is what `touch`
        # refreshes. Read by name rather than by position, so a stage that
        # returns its columns in another order still beats.
        self._held = (
            None
            if claimed is None
            else (
                getattr(claimed, self.columns.key.key),
                getattr(claimed, self.columns.claimed_at.key),
            )
        )
        # Set on every claim, including to None: a row queued by nobody must
        # not inherit the trigger of the row this worker held before it.
        triggered_by(
            None
            if claimed is None or trigger is None
            else getattr(claimed, trigger.key)
        )
        return claimed

    def _at_head(self, session: Any) -> bool:
        """Whether the database is at the revision this code was written for.

        Code ahead of its schema writes columns that are not there yet, and
        fails every row it claims. Logged the first time only, because an
        idle worker asks on every poll.
        """
        live = applied(session.connection())
        if live == heads():
            return True
        if not self._behind:
            self._behind = True
            log.warning(
                "%s claims nothing: the database is at %s and this code's head "
                "is %s. `make schema` applies it.",
                type(self).__name__,
                ", ".join(sorted(live)) or "no revision",
                ", ".join(sorted(heads())),
            )
        return False

    def _holding(self, key: Any) -> tuple[Any, ...]:
        """What says the row is still the one this instance claimed.

        Its claim time unmoved: a sweep clears it and another claim rewrites
        it. Nothing for a key this instance did not claim, which is written
        by key alone.
        """
        if self._held is None or self._held[0] != key:
            return ()
        return (
            self.columns.status == Status.IN_PROGRESS,
            self.columns.claimed_at == self._held[1],
        )

    def _release(self, key: Any, values: dict[Any, Any], session: Any = None) -> None:
        """Writes a row's outcome and clears its claim.

        Raises:
            Gone: If this instance claimed the row and it was deleted since.
            Lost: If this instance claimed the row and another worker has
                claimed it since.
        """
        with self._lock:
            holding = self._holding(key)
            statement = (
                update(self.columns.entity)
                .where(self.columns.key == key, *holding)
                .values({self.columns.claimed_at: None, **values})
            )
            if session is None:
                with self._session.begin() as opened:
                    written = opened.execute(statement).rowcount
                    exists = bool(written) or self._exists(opened, key)
            else:
                written = session.execute(statement).rowcount
                exists = bool(written) or self._exists(session, key)
            if holding and not written:
                if not exists:
                    raise Gone(f"{key} was deleted while this worker held it")
                raise Lost(f"{key} was claimed by another worker since this one")
            self._held = None

    def _exists(self, session: Any, key: Any) -> bool:
        """Whether the row is still there."""
        return (
            session.scalar(
                select(func.count())
                .select_from(self.columns.entity)
                .where(self.columns.key == key)
            )
            > 0
        )

    def _finish(
        self,
        key: Any,
        *,
        session: Any = None,
        note: str | None = None,
        **values: Any,
    ) -> None:
        """Marks a row done for this stage, releasing the claim.

        `note` is kept in the error column: what a finished row lacks, where
        a failure's reason would be.

        Raises:
            Lost: If another worker has claimed the row since this one did.
        """
        self._release(
            key,
            {self.columns.status: self.done, self.columns.error: note, **values},
            session,
        )

    def fail(self, key: Any, error: str) -> None:
        """Records a row this stage could not process, releasing the claim.

        Raises:
            Lost: If another worker has claimed the row since this one did.
        """
        self._release(
            key, {self.columns.status: Status.FAILED, self.columns.error: error[:2000]}
        )

    def _unclaimed(self) -> dict[Any, Any]:
        """What a row becomes when it is given back unworked."""
        return {self.columns.status: Status.PENDING, self.columns.error: None}

    def release(self, *keys: Any) -> None:
        """Returns rows to the queue unworked, releasing the claim.

        What a drain does with the rows an outage failed, and with the one it
        held: they did not fail on their own account, and a row left failed
        is one a person must remember to retry. Written by key, so it also
        returns a row an earlier `fail` of this instance gave up.

        Raises:
            Lost: If this instance claimed a row and another worker has
                claimed it since.
        """
        for key in keys:
            self._release(key, self._unclaimed())

    def release_held(self) -> bool:
        """Returns the row this instance holds to the queue, if it holds one.

        For a worker told to stop before its row was done. Not the failure
        `abandon` would make of it at the next start: nothing was wrong with
        the row.

        Returns:
            Whether a row was held.

        Raises:
            Lost: If another worker has claimed the row since this one did.
        """
        with self._lock:
            held = self._held
        if held is None:
            return False
        self.release(held[0])
        return True

    def touch(self) -> bool:
        """Refreshes the claim on the row this instance is working.

        What separates a live claim from a dead one. `claimed_at` records
        when work started and nothing else, so a sweep could only ever ask
        "could this still be running?" - and the honest answer is the worst
        case the work might take, which is days for a stage whose unit is a
        whole topic. Beating turns that into "is anyone still on it?", which
        the lease can answer in minutes however long the work runs.

        Refuses to refresh a row this queue no longer holds: `reclaim` moves
        an interrupted row back to pending, a sweep and another claim move
        its claim time, and a beat still in flight must not drag it back.
        Skips a row locked by the transaction finishing it, which would
        otherwise wait on that transaction while holding `_lock` it needs.
        """
        with self._lock:
            if self._held is None:
                return False
            key = self._held[0]
            mine = (
                select(self.columns.key)
                .where(*self._where(self.columns.key == key, *self._holding(key)))
                .with_for_update(skip_locked=True)
                .scalar_subquery()
            )
            with self._session.begin() as session:
                refreshed = session.scalar(
                    update(self.columns.entity)
                    .where(self.columns.key == mine)
                    .values({self.columns.claimed_at: func.now()})
                    .returning(self.columns.claimed_at)
                )
            if refreshed is None:
                return False
            self._held = (key, refreshed)
            return True

    def abandon(self) -> int:
        """Fails every row whose claim has outlived the lease."""
        with self._session.begin() as session:
            return session.execute(
                update(self.columns.entity)
                .where(
                    *self._where(
                        self.columns.status == Status.IN_PROGRESS,
                        # A NULL claim counts as abandoned: such a row matches
                        # no other operation and would sit in_progress forever.
                        or_(
                            self.columns.claimed_at.is_(None),
                            self.columns.claimed_at < func.now() - self.lease,
                        ),
                    )
                )
                .values(
                    {
                        self.columns.claimed_at: None,
                        self.columns.status: Status.FAILED,
                        self.columns.error: ABANDONED,
                    }
                )
            ).rowcount

    def narrow(self, scope: str, value: str) -> Any:
        """Builds the condition one scope's value selects.

        Raises:
            KeyError: If this stage accepts no such scope.
            ValueError: If the value is not what that column holds.
        """
        column = self.scopes[scope]
        # A NUL and an int past bigint are refused by the driver, not matched.
        if "\x00" in value:
            raise ValueError(f"{value!r} carries a NUL")
        cast = column.type.python_type(value)
        if isinstance(cast, int) and not -(2**63) <= cast < 2**63:
            raise ValueError(f"{value!r} is past what a bigint holds")
        return column == cast

    def narrowed(self, scope: str, value: str) -> Any:
        """Builds that condition, refusing a scope or a value with a reason.

        The wording is here rather than at each caller: the route and the
        command line refuse the same two things.

        Raises:
            Unnarrowable: If this stage accepts no such scope, or the value
                is not what that column holds.
        """
        try:
            return self.narrow(scope, value)
        except KeyError:
            accepted = ", ".join(self.scopes) or "nothing"
            raise Unnarrowable(
                "unknown_scope", f"this stage narrows to {accepted}, not {scope!r}"
            ) from None
        except ValueError:
            raise Unnarrowable(
                "invalid_value", f"{value!r} is not a valid {scope}"
            ) from None

    def stop(self, within: Any = None) -> int:
        """Takes back every row this stage has not started yet."""
        with self._session.begin() as session:
            return session.execute(
                update(self.columns.entity)
                .where(*self._where(self.columns.status == Status.PENDING, within))
                .values({self.columns.status: Status.NEW})
            ).rowcount

    def retry(self, within: Any = None, *, trigger: str | None = None) -> int:
        """Returns every failed row to the queue, clearing its error."""
        return self._requeue(
            self.columns.status == Status.FAILED, within, trigger=trigger
        )

    def reclaim(self, within: Any = None, *, trigger: str | None = None) -> int:
        """Returns a row a dead worker still holds, without waiting it out.

        The gap between `retry` and `rerun`, and the only verb that moves
        an `in_progress` row. `retry` takes the failed, `rerun` explicitly
        skips what a worker holds, and `stop` takes back only what has not
        begun - so a worker killed mid-row left that row unreachable until
        its lease ran out.

        `abandon` is the automatic version and stays the normal one: it
        sweeps on a lease, because a row a LIVE worker holds must not be
        given to a second. This is the deliberate one, and the reason it
        is worth having separately is that a person knows the worker is
        gone and the lease cannot.

        **Narrow it.** Nothing here can tell a dead claim from a live one,
        so run it against a named row when a worker may still be up, and
        over the stage only when none is. Two workers on one row is what
        the lease exists to prevent, and this is the verb that can cause
        it.
        """
        return self._requeue(
            self.columns.status == Status.IN_PROGRESS, within, trigger=trigger
        )

    def _requeue(self, *where: Any, trigger: str | None = None) -> int:
        """Moves the rows a condition selects to pending, clearing the error.

        Writes the trigger too, None included: a row requeued by a caller
        that named no run must stop claiming the one that queued it last.
        """
        queued: dict[Any, Any] = {
            self.columns.status: Status.PENDING,
            self.columns.error: None,
        }
        if self.columns.trigger is not None:
            queued[self.columns.trigger] = trigger
        with self._session.begin() as session:
            return session.execute(
                update(self.columns.entity).where(*self._where(*where)).values(queued)
            ).rowcount

    def queue_state(self, within: Any = None, *, digests: bool = False) -> QueueState:
        """Reports the queue depth and whether a worker is on it.

        Args:
            within: A condition narrowing the rows read, or None.
            digests: Whether to hash each status's rows. A hash reads and
                sorts every row of the queue, so a page that polls for counts
                leaves it off; the orchestrator, which compares them between
                ticks, asks.
        """
        # One query for both: a page polls this every few seconds.
        digest = (
            [
                func.md5(
                    func.string_agg(
                        func.concat(
                            self.columns.key,
                            literal_column("':'"),
                            self.columns.trigger,
                        ),
                        aggregate_order_by(literal_column("','"), self.columns.key),
                    )
                )
            ]
            if digests
            else [literal_column("NULL")]
        )
        with self._session() as session:
            rows = session.execute(
                select(
                    self.columns.status,
                    func.count(),
                    func.count().filter(
                        self.columns.claimed_at >= func.now() - self.lease
                    ),
                    *digest,
                )
                .where(*self._where(within))
                .group_by(self.columns.status)
                .order_by(self.columns.status)
            ).all()

        return QueueState(
            working=any(
                status == Status.IN_PROGRESS and live for status, _, live, _ in rows
            ),
            rows={status: total for status, total, _, _ in rows},
            digests={status: hashed for status, _, _, hashed in rows if digests},
        )

    def counts_by_status(self, within: Any = None) -> dict[str, int]:
        """Counts rows in each state of this stage."""
        return self.queue_state(within).rows


class RowQueue(StageQueue, abstract=True):
    """A queue over rows that exist before the stage is asked to run them.

    Separate from :class:`StageQueue` because `start` and `reset` presuppose
    that: topic modelling has no row until a fit is requested, so it extends
    the base without them rather than answering them with something else.
    """

    #: Which of this stage's rows have an input to work on. None means every
    #: one does, which is true wherever the row is created by the stage
    #: before - a passage exists because chunking made it, a topic because a
    #: fit did. Only chunking needs this: it queues over `documents`, and a
    #: document exists from the moment it is uploaded, so `start` without it
    #: queues documents that have not been parsed and whose only possible
    #: outcome is a failure on the missing parsed object.
    #:
    #: Carried by `start` and `reset` and by nothing else. Claiming, failing,
    #: sweeping and `retry` still select on this stage's own status column
    #: alone: this says which rows may ENTER the queue, not which a worker
    #: may take, and a row already queued is worked whatever this says.
    ready: ClassVar[Any] = None

    def start(self, within: Any = None, *, trigger: str | None = None) -> int:
        """Queues the rows this stage has never been asked to do.

        Skips rows the stage before this one has not produced an input for.
        """
        return self._requeue(
            self.columns.status == Status.NEW, within, self.ready, trigger=trigger
        )

    def reset(self, within: Any = None, *, trigger: str | None = None) -> int:
        """Returns every row to the queue, finished ones included.

        Skips rows a worker holds right now, and rows with no input to redo.
        """
        return self._requeue(
            self.columns.status != Status.IN_PROGRESS,
            within,
            self.ready,
            trigger=trigger,
        )
