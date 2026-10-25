"""Reading the archive, and emptying it."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, text

from blob_store.s3 import ArchiveBucket
from database.qa_generator.archived_rows import ArchivedRow
from database.qa_generator.engine import sessions

log = logging.getLogger(__name__)

#: Rows a purge deletes per transaction: one DELETE over a table the size of a
#: corpus holds its locks, and writes its log, until the very end.
BATCH = 10_000


@dataclass(frozen=True)
class Held:
    """What one table has in the archive."""

    table_name: str
    rows: int
    bytes: int
    oldest: datetime
    newest: datetime


@dataclass(frozen=True)
class Purged:
    """What a purge took."""

    rows: int
    objects: int


class Archive:
    """The rows and objects the deletions left behind."""

    def __init__(self) -> None:
        """Binds to the session factory and the archive bucket."""
        self._session = sessions()
        self._bucket = ArchiveBucket()

    def rows(self) -> list[Held]:
        """What is held, by table, most rows first."""
        with self._session() as session:
            return [
                Held(
                    table_name=row.table_name,
                    rows=row.rows,
                    bytes=row.bytes,
                    oldest=row.oldest,
                    newest=row.newest,
                )
                for row in session.execute(
                    select(
                        ArchivedRow.table_name,
                        func.count().label("rows"),
                        func.sum(func.pg_column_size(ArchivedRow.payload)).label(
                            "bytes"
                        ),
                        func.min(ArchivedRow.archived_at).label("oldest"),
                        func.max(ArchivedRow.archived_at).label("newest"),
                    )
                    .group_by(ArchivedRow.table_name)
                    .order_by(func.count().desc())
                ).all()
            ]

    def estimate(self) -> tuple[int, int]:
        """Rows and bytes the archive table holds, as the planner knows them.

        Read from `pg_class`, so it costs nothing however large the archive
        has grown, where `rows` reads every payload. An estimate: a table
        never analysed reports none.
        """
        with self._session() as session:
            rows, size = session.execute(
                text(
                    "SELECT greatest(reltuples, 0)::bigint, "
                    "pg_total_relation_size(oid) FROM pg_class "
                    "WHERE oid = 'archived_rows'::regclass"
                )
            ).one()
        return int(rows), int(size)

    def objects(self) -> tuple[int, int]:
        """How many objects the archive bucket holds, and how many bytes."""
        held = self._bucket.held()
        return len(held), sum(size for _, size in held)

    def purge(
        self, *, table: str | None = None, older_than_days: int | None = None
    ) -> Purged:
        """Deletes what the archive holds. Irreversible: this is the second one.

        The objects go when no table is named, because an object belongs to
        no table: naming `questions` is about rows, and naming nothing at
        all means the whole archive.

        An age is cut at one moment read off the database's clock, for the
        rows' `archived_at` and the objects' `LastModified` alike. Without
        an age the rows are cut at the moment the purge started, so a row
        archived while the batches run is left, and so is the loop's end.

        Args:
            table: Only rows deleted from this table, or every table.
            older_than_days: Only what has been held this long, or all of it.

        Returns:
            How many rows and how many objects were deleted.
        """
        wanted = select(ArchivedRow.id)
        if table is not None:
            wanted = wanted.where(ArchivedRow.table_name == table)

        with self._session.begin() as session:
            cutoff = (
                None
                if older_than_days is None
                else session.execute(
                    select(func.now() - timedelta(days=older_than_days))
                ).scalar_one()
            )
            started = cutoff or session.execute(select(func.now())).scalar_one()
        wanted = wanted.where(ArchivedRow.archived_at < started)
        # Listed now, before the batches: an object archived while they run
        # belongs to a deletion whose rows this purge leaves.
        listed = None if table is not None else self._bucket.held(before=cutoff)

        rows = 0
        while True:
            with self._session.begin() as session:
                taken = session.execute(
                    delete(ArchivedRow).where(
                        ArchivedRow.id.in_(wanted.limit(BATCH).scalar_subquery())
                    )
                ).rowcount
            rows += taken
            if taken < BATCH:
                break

        objects = 0 if table is not None else self._bucket.purge(held=listed)
        log.info("purged %d archived row(s) and %d archived object(s)", rows, objects)
        return Purged(rows=rows, objects=objects)
