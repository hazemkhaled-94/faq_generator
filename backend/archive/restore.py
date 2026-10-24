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
#: unique key a live row holds is skipped, and so is a row whose foreign-key
#: parent is absent: a refit or a re-chunk replaced the parent under its
#: unique key, so the archived row has nothing to rest on.
#:
#: ponytail: two ceilings. Passages restored after `make delete-derived` sit
#: under a document still marked chunk_status `new`, an UPDATE the archive
#: never recorded, so the next chunk-start re-chunks them; the upgrade is to
#: set chunk_status from the restored passages. And jsonb_populate_record
#: fills a key missing from an older payload with NULL, not the column's
#: default, so a NOT NULL column added since the row was archived rolls the
#: whole restore back; the upgrade is to coalesce missing keys to defaults.
_FROM = """
FROM archived_rows a, jsonb_populate_record(NULL::{table}, a.payload) r
WHERE a.table_name = :table AND a.archived_at >= :since
"""
_RESTORE = (
    "INSERT INTO {table} SELECT r.* "
    + _FROM
    + """{parents}
ORDER BY a.archived_at DESC, a.id DESC
ON CONFLICT DO NOTHING
"""
)
_ORPHANS = "SELECT count(*) " + _FROM + "AND NOT ({parents})"


def _parents(table: str) -> str:
    """The condition that every foreign key of a row has its parent.

    A key to the table's own rows is left out: its parent comes back in the
    same statement, which cannot see it yet. A NULL key rests on nothing.
    """
    conditions = [
        "("
        + " AND ".join(f"r.{column.name} IS NULL" for column in key.columns)
        + " OR EXISTS (SELECT 1 FROM "
        + f"{key.referred_table.name} p WHERE "
        + " AND ".join(
            f"p.{element.column.name} = r.{element.parent.name}"
            for element in key.elements
        )
        + "))"
        for key in Base.metadata.tables[table].foreign_key_constraints
        if key.referred_table.name != table
    ]
    return " AND ".join(conditions) or "true"


#: A restored question's release_id belonged to the draw of its day. It stays
#: only where a question that was live all along still holds that release;
#: otherwise a later draw superseded it or the release was cleared, and the
#: question comes back accepted but undrawn.
_RESTORED = """
SELECT (a.payload->>'id')::bigint FROM archived_rows a
WHERE a.table_name = 'questions' AND a.archived_at >= :since
"""
_SUPERSEDED = (
    """
UPDATE questions q SET release_id = NULL
WHERE q.release_id IS NOT NULL
  AND q.id IN ("""
    + _RESTORED
    + """)
  AND NOT EXISTS (
    SELECT 1 FROM questions o
    WHERE o.release_id = q.release_id AND o.id NOT IN ("""
    + _RESTORED
    + """))
"""
)

#: A thread is released whole, so a restored follow-up keeps its release only
#: under the turn it follows still released in it: a parent that is not
#: accepted, or sits in no release or another one, takes the follow-up and
#: every turn below it out. The trigger that clears a thread fires on a root's
#: UPDATE, and the follow-up was in the archive then, so this applies the rule
#: of that trigger's upgrade to the restored rows.
_ROOTLESS = (
    """
WITH RECURSIVE below AS (
    SELECT q.id FROM questions q JOIN questions r ON q.follows_id = r.id
    WHERE r.status <> 'accepted' OR r.release_id IS DISTINCT FROM q.release_id
    UNION SELECT q.id FROM questions q JOIN below b ON q.follows_id = b.id)
UPDATE questions SET release_id = NULL
WHERE release_id IS NOT NULL AND id IN (SELECT id FROM below)
  AND id IN ("""
    + _RESTORED
    + """)
"""
)


#: A restored fact whose citations were left behind rests on nothing, and a
#: bridge needs two passages. The triggers that drop such a fact fire only on
#: DELETE, so the restore does it: the cascade takes its question links, and
#: the question trigger the question left with no fact.
_UNSOURCED = """
DELETE FROM facts f
WHERE f.id IN (
    SELECT (a.payload->>'id')::bigint FROM archived_rows a
    WHERE a.table_name = 'facts' AND a.archived_at >= :since)
  AND (SELECT count(*) FROM fact_passages p WHERE p.fact_id = f.id)
      < CASE WHEN f.kind = 'bridge' THEN 2 ELSE 1 END
"""

#: A fact archived before facts carried a language comes back with none, and
#: the dedup probe filters on it. Read again from the citation at position 0,
#: as the revision that added the column filled the rest.
_LANGUAGED = """
UPDATE facts SET language = coalesce(p.language, d.language)
FROM fact_passages fp
JOIN passages p ON p.id = fp.passage_id
JOIN documents d ON d.sha256 = p.doc_sha256
WHERE fp.fact_id = facts.id AND fp.position = 0 AND facts.language IS NULL
  AND facts.id IN (
    SELECT (a.payload->>'id')::bigint FROM archived_rows a
    WHERE a.table_name = 'facts' AND a.archived_at >= :since)
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

    The rows go back in one transaction. A row whose parent is absent is
    left behind and counted, so the rest still comes back.

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
        behind: dict[str, int] = {}
        try:
            for table in (one for one in TABLES if one in held):
                parents = _parents(table)
                left = connection.execute(
                    text(_ORPHANS.format(table=table, parents=parents)),
                    {"table": table, "since": since},
                ).scalar_one()
                restored = connection.execute(
                    text(_RESTORE.format(table=table, parents="AND " + parents)),
                    {"table": table, "since": since},
                ).rowcount
                print(f"  {table:<20} {restored:>8} of {held[table]} row(s)")
                if left:
                    behind[table] = left
                if table == "questions":
                    connection.execute(text(_SUPERSEDED), {"since": since})
                    connection.execute(text(_ROOTLESS), {"since": since})
            dropped = connection.execute(text(_UNSOURCED), {"since": since}).rowcount
            connection.execute(text(_LANGUAGED), {"since": since})
        except IntegrityError as exc:
            connection.rollback()
            print(f"\nNothing restored: {exc.orig}")
            return 1

        missing = _objects(connection, since)
        connection.commit()

    for table, rows in behind.items():
        print(f"  {table}: {rows} row(s) left behind, their parent is not there")
    if dropped:
        print(
            f"  facts: {dropped} restored fact(s) dropped, left resting on no passage"
        )
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
