"""Put back what the deletions archived from a given time on.

Run after an accidental `make wipe`, before `make archive-purge`, naming
when the wipe began:

    make restore-documents SINCE=2026-10-07T09:14

Without SINCE it lists the archived rows by the minute they were deleted and
restores nothing.
"""

from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from blob_store.s3 import (
    ArchiveBucket,
    DocumentsBucket,
    ExportBucket,
    ModelsBucket,
    ParsedBucket,
)
from database.qa_generator import ArchivedRow, Base, engine

#: Every table the triggers archive, each after the tables it refers to.
TABLES = [
    table.name
    for table in Base.metadata.sorted_tables
    if table.name != ArchivedRow.__tablename__
]

#: One table's archived rows, newest copy first. A row whose primary or
#: unique key a live row holds is skipped.
#:
#: ponytail: two ceilings. Passages restored after `make delete-derived` sit
#: under a document still marked chunk_status `new`, an UPDATE the archive
#: never recorded, so the next chunk-start re-chunks them; the upgrade is to
#: set chunk_status from the restored passages. And jsonb_populate_record
#: fills a key missing from an older payload with NULL, not the column's
#: default, so a NOT NULL column added since the row was archived rolls the
#: whole restore back; the upgrade is to coalesce missing keys to defaults.
_RESTORE = """
INSERT INTO {table}
SELECT r.* FROM archived_rows a, jsonb_populate_record(NULL::{table}, a.payload) r
WHERE a.table_name = :table AND a.archived_at >= :since
ORDER BY a.archived_at DESC, a.id DESC
ON CONFLICT DO NOTHING
"""


def _deletions(connection: Connection) -> None:
    """Lists the archived rows by the minute they were deleted, newest first."""
    print("Name when the deletion began: make restore-documents SINCE=<time>\n")
    # ponytail: the newest 20 minutes only; an older start is read off archived_rows.
    for minute, rows in connection.execute(
        text(
            "SELECT date_trunc('minute', archived_at) AS minute, count(*) "
            "FROM archived_rows GROUP BY minute ORDER BY minute DESC LIMIT 20"
        )
    ):
        print(f"  {minute.isoformat()}  {rows:>8} row(s)")


def _objects(connection: Connection, since: datetime) -> list[tuple[str, str]]:
    """Copies back the objects of the documents and topics archived since.

    Returns:
        The (bucket, key) of each object in neither its bucket nor the archive.
    """
    wanted = []
    for sha256, mime_type in connection.execute(
        text(
            "SELECT DISTINCT payload->>'sha256', payload->>'mime_type' "
            "FROM archived_rows WHERE table_name = 'documents' AND archived_at >= :since"
        ),
        {"since": since},
    ):
        wanted += [
            (DocumentsBucket.name, DocumentsBucket.key_for(sha256, mime_type)),
            (ParsedBucket.name, ParsedBucket.key_for(sha256)),
        ]
    for language in connection.execute(
        text(
            "SELECT DISTINCT payload->>'language' FROM archived_rows "
            "WHERE table_name = 'topics' AND archived_at >= :since "
            "AND payload->>'topic_index' IS NOT NULL"
        ),
        {"since": since},
    ).scalars():
        wanted += [
            (ExportBucket.name, ExportBucket.topic_visualisation_key(language)),
            (ModelsBucket.name, ModelsBucket.topic_model_key(language)),
        ]
    archive = ArchiveBucket()
    return [
        (bucket, key) for bucket, key in wanted if not archive.give_back(bucket, key)
    ]


def main() -> int:
    """Puts back every row and object archived at or after SINCE.

    The rows go back in one transaction, so a row whose parent is gone
    restores nothing at all.

    Returns:
        0, 1 when nothing was restored or an upload is in neither bucket,
        or 2 when SINCE is unset.
    """
    named = os.environ.get("SINCE")
    with engine().connect() as connection:
        if not named:
            _deletions(connection)
            return 2
        since = connection.execute(
            text("SELECT CAST(:since AS timestamptz)"), {"since": named}
        ).scalar_one()
        print(f"Restoring what was archived at or after {since.isoformat()}.\n")

        held = {
            table: rows
            for table, rows in connection.execute(
                text(
                    "SELECT table_name, count(*) FROM archived_rows "
                    "WHERE archived_at >= :since GROUP BY table_name"
                ),
                {"since": since},
            )
        }
        try:
            for table in (one for one in TABLES if one in held):
                restored = connection.execute(
                    text(_RESTORE.format(table=table)),
                    {"table": table, "since": since},
                ).rowcount
                print(f"  {table:<20} {restored:>8} of {held[table]} row(s)")
        except IntegrityError as exc:
            connection.rollback()
            print(f"\nNothing restored: {exc.orig}")
            return 1

        missing = _objects(connection, since)
        connection.commit()

    for bucket, key in missing:
        print(f"  {bucket}/{key} is in neither its bucket nor the archive")
    print(
        "\nVectors are not archived, so the restored rows carry none: "
        "`make extract-embed` writes the passages' and the facts' again. "
        "Nothing writes a question's, so re-verifying a restored question "
        "skips the duplicate veto."
    )
    return 1 if any(bucket == DocumentsBucket.name for bucket, _ in missing) else 0


if __name__ == "__main__":
    raise SystemExit(main())
