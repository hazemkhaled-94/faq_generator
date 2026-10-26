"""Put back the deletions chosen from the archive.

Run after an accidental `make wipe`, before `make archive-purge`. One
deleting transaction is one `archived_at`, and the listing names each with
the tables it took rows from:

    make restore-documents                         the newest deletions
    make restore-documents SINCE=2026-10-07T09:14  every deletion from then on
    make restore-documents AT=<archived_at>[,...]  put those deletions back

SINCE only lists. A restore puts back the transactions AT names and nothing
archived beside them: a fact a re-extraction replaced, or a setting somebody
cleared, stays as it is. `service_settings` and `prompts` are skipped unless
TABLES names them; TABLES restricts a restore to the tables it names.
"""

from __future__ import annotations

import json
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

#: A restore leaves these out unless TABLES names them: a setting is a
#: decision about now, and an older prompt text is not the live one.
OPT_IN = ("service_settings", "prompts")

#: What the rows of one restore are, by when their deleting transaction ran.
_CHOSEN = "a.archived_at = ANY(CAST(:chosen AS timestamptz[]))"

#: One table's archived rows, newest copy first. A row whose primary or
#: unique key a live row holds is skipped, and so is a row whose foreign-key
#: parent is absent: a refit or a re-chunk replaced the parent under its
#: unique key, so the archived row has nothing to rest on.
#:
#: A key missing from an older payload is filled from :defaults, the column's
#: server default, which jsonb_populate_record would leave NULL, and a SET NULL
#: key to the table's own rows is cleared where its row is gone (`_cleared`).
_FROM = (
    """
FROM archived_rows a,
     jsonb_populate_record(
         NULL::{table}, CAST(:defaults AS jsonb) || a.payload{cleared}) r
WHERE a.table_name = :table AND """
    + _CHOSEN
    + "\n"
)
_RESTORE = (
    "INSERT INTO {table} SELECT r.* "
    + _FROM
    + """{parents}
ORDER BY a.archived_at DESC, a.id DESC
ON CONFLICT DO NOTHING
"""
)
_ORPHANS = "SELECT count(*) " + _FROM + "AND NOT ({parents})"


def _own(table: str, action: str) -> list[str]:
    """The table's single-column keys to its own rows whose ON DELETE is `action`."""
    return [
        key.elements[0].parent.name
        for key in Base.metadata.tables[table].foreign_key_constraints
        if key.referred_table.name == table
        and len(key.elements) == 1
        and (key.ondelete or "").upper() == action
    ]


def _back(table: str, named: str) -> str:
    """That the row of `table` whose id is `named` is live or among the chosen rows."""
    return (
        f"(EXISTS (SELECT 1 FROM {table} t WHERE t.id = {named})"
        " OR EXISTS (SELECT 1 FROM archived_rows c"
        f" WHERE c.table_name = '{table}'"
        " AND c.archived_at = ANY(CAST(:chosen AS timestamptz[]))"
        f" AND (c.payload->>'id')::bigint = {named}))"
    )


def _cleared(table: str) -> str:
    """What `_FROM` adds to a payload: a SET NULL key to its own table cleared where that row is gone.

    As the delete of that row would have left it: a duplicate refusal's twin,
    deleted or read again since. NULL is what marks a refusal for the dedup
    replay, which points it at a twin again; kept, the key would fail the
    foreign key and roll the whole restore back.
    """
    return "".join(
        f" || CASE WHEN a.payload->>'{column}' IS NULL OR "
        + _back(table, f"(a.payload->>'{column}')::bigint")
        + f" THEN '{{}}'::jsonb ELSE jsonb_build_object('{column}', NULL) END"
        for column in _own(table, "SET NULL")
    )


def _stranded(table: str) -> list[str]:
    """That a CASCADE key to the row's own table reaches a live or restored row.

    As the delete of that row would have taken this one: a follow-up whose
    root a later transaction deleted is left behind, with every turn below it,
    and counted, rather than failing the foreign key and the whole restore.
    """
    return [
        "r.id NOT IN (WITH RECURSIVE chosen AS ("
        f"SELECT (c.payload->>'id')::bigint AS id, (c.payload->>'{column}')::bigint AS up "
        f"FROM archived_rows c WHERE c.table_name = '{table}' "
        "AND c.archived_at = ANY(CAST(:chosen AS timestamptz[]))), "
        "stranded AS (SELECT x.id FROM chosen x WHERE x.up IS NOT NULL "
        f"AND NOT EXISTS (SELECT 1 FROM {table} t WHERE t.id = x.up) "
        "AND NOT EXISTS (SELECT 1 FROM chosen y WHERE y.id = x.up) "
        "UNION SELECT x.id FROM chosen x JOIN stranded s ON x.up = s.id) "
        "SELECT id FROM stranded)"
        for column in _own(table, "CASCADE")
    ]


def _parents(table: str) -> str:
    """The condition that every foreign key of a row has its parent.

    A key to the table's own rows is read apart: its row may come back in the
    same statement, which cannot see it yet, so it holds where that row is
    live or among the chosen ones, and otherwise `_stranded` and `_cleared`
    do what its ON DELETE would have done. A NULL key rests on nothing.
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
    ] + _stranded(table)
    return " AND ".join(conditions) or "true"


#: A restored question's release_id belonged to the draw of its day. It stays
#: only where a question that was live all along still holds that release;
#: otherwise a later draw superseded it or the release was cleared, and the
#: question comes back accepted but undrawn.
_RESTORED = (
    """
SELECT (a.payload->>'id')::bigint FROM archived_rows a
WHERE a.table_name = 'questions' AND """
    + _CHOSEN
    + """
"""
)
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
#: DELETE, so the restore does it, and the cascade takes its question links.
#: The question trigger rejects the question left with no fact and keeps it;
#: with no citation left to read, nothing would stamp it with its document, so
#: `_UNSOURCED_STAMP` does first, from the archived citations, and a later
#: delete of the document takes it.
_UNSOURCED_FACTS = (
    """
SELECT f.id FROM facts f
WHERE f.id IN (
    SELECT (a.payload->>'id')::bigint FROM archived_rows a
    WHERE a.table_name = 'facts' AND """
    + _CHOSEN
    + """)
  AND (SELECT count(*) FROM fact_passages p WHERE p.fact_id = f.id)
      < CASE WHEN f.kind = 'bridge' THEN 2 ELSE 1 END
"""
)

_UNSOURCED = "DELETE FROM facts WHERE id IN (" + _UNSOURCED_FACTS + ")"

_UNSOURCED_STAMP = (
    """
UPDATE questions q
SET source_digests = ARRAY(
    SELECT DISTINCT unnest(coalesce(q.source_digests, '{}') || s.digests))
FROM (
    SELECT qf.question_id,
           array_agg(DISTINCT CAST(ap.payload->>'doc_sha256' AS char(64))) AS digests
    FROM question_facts qf
    JOIN archived_rows afp ON afp.table_name = 'fact_passages'
         AND (afp.payload->>'fact_id')::bigint = qf.fact_id
         AND afp.archived_at = ANY(CAST(:chosen AS timestamptz[]))
    JOIN archived_rows ap ON ap.table_name = 'passages'
         AND (ap.payload->>'id')::bigint = (afp.payload->>'passage_id')::bigint
         AND ap.archived_at = ANY(CAST(:chosen AS timestamptz[]))
    WHERE qf.fact_id IN ("""
    + _UNSOURCED_FACTS
    + """)
    GROUP BY qf.question_id) s
WHERE q.id = s.question_id
"""
)


#: A fact archived before facts carried a language comes back with none, and
#: the dedup probe filters on it. Read again from the citation at position 0,
#: as the revision that added the column filled the rest.
_LANGUAGED = (
    """
UPDATE facts SET language = coalesce(p.language, d.language)
FROM fact_passages fp
JOIN passages p ON p.id = fp.passage_id
JOIN documents d ON d.sha256 = p.doc_sha256
WHERE fp.fact_id = facts.id AND fp.position = 0 AND facts.language IS NULL
  AND facts.id IN (
    SELECT (a.payload->>'id')::bigint FROM archived_rows a
    WHERE a.table_name = 'facts' AND """
    + _CHOSEN
    + """)
"""
)


#: The tables a fit writes. A transaction that took rows from these alone is
#: a topics deletion or a refit's replacement of them.
_FIT_TABLES = frozenset({"topics", "passage_topics"})


def _replaced(connection: Connection, at: datetime, tables: set[str]) -> bool:
    """Whether a later fit holds the topics a deletion took, under their unique key.

    Such a transaction is a refit's: its topics and memberships rest on
    nothing the live ones do, and putting them back would run into them.
    """
    return (
        bool(tables)
        and tables <= _FIT_TABLES
        and bool(
            connection.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM archived_rows a JOIN topics t "
                    "ON t.language = a.payload->>'language' "
                    "AND t.topic_index::text = a.payload->>'topic_index' "
                    "WHERE a.table_name = 'topics' AND a.archived_at = :at)"
                ),
                {"at": at},
            ).scalar_one()
        )
    )


def _transactions(
    connection: Connection, since: datetime | None
) -> list[tuple[datetime, dict[str, int]]]:
    """The deleting transactions, newest first, with the rows each took per table."""
    found: dict[datetime, dict[str, int]] = {}
    for at, table, rows in connection.execute(
        text(
            "SELECT archived_at, table_name, count(*) FROM archived_rows "
            "WHERE archived_at >= COALESCE(CAST(:since AS timestamptz), '-infinity') "
            "GROUP BY archived_at, table_name ORDER BY archived_at DESC, table_name"
        ),
        {"since": since},
    ):
        found.setdefault(at, {})[table] = rows
    return list(found.items())


def _deletions(connection: Connection, since: datetime | None) -> None:
    """Lists the deleting transactions, each as the value AT takes."""
    print("Name the deletions to put back: make restore-documents AT=<time>[,<time>]\n")
    # ponytail: the newest 20 transactions without SINCE; an older start is read off archived_rows.
    listed = _transactions(connection, since)
    for at, tables in listed if since is not None else listed[:20]:
        took = ", ".join(f"{table} {rows}" for table, rows in tables.items())
        note = (
            "  (not restorable: a later fit replaced these topics)"
            if _replaced(connection, at, set(tables))
            else ""
        )
        print(f"  {at.isoformat()}  {took}{note}")


def _defaults(connection: Connection, table: str, chosen: list[datetime]) -> str:
    """The server default of every column some chosen payload has no key for.

    A NOT NULL column added since the rows were archived has no value in
    their payloads. Where it has a default the row takes it; where it has none
    the restore refuses, naming the column, rather than rolling back on an
    anonymous violation.

    Returns:
        The defaults as a JSON object, `{}` when no payload lacks a key.

    Raises:
        ValueError: If a column with no default and no NULL lacks a key.
    """
    filled: dict[str, str] = {}
    for column in connection.execute(
        text(
            "SELECT column_name, column_default, is_nullable, is_identity "
            "FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = :table"
        ),
        {"table": table},
    ).all():
        name, default, nullable, identity = column
        lacking = connection.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM archived_rows a WHERE a.table_name = :table "
                "AND " + _CHOSEN + " AND NOT jsonb_exists(a.payload, :column))"
            ),
            {"table": table, "chosen": chosen, "column": name},
        ).scalar_one()
        if not lacking:
            continue
        if default is not None:
            filled[name] = connection.exec_driver_sql(
                f"SELECT to_jsonb({default})"
            ).scalar_one()
        elif nullable == "NO" and identity == "NO":
            raise ValueError(
                f"{table}.{name} is NOT NULL with no default, and a row archived "
                "before it existed has no value for it"
            )
    return json.dumps(filled)


def _objects(connection: Connection, chosen: list[datetime]) -> list[tuple[str, str]]:
    """Copies back the objects of the documents and topics the chosen deletions took.

    Returns:
        The (bucket, key) of each object in neither its bucket nor the archive.
    """
    wanted = []
    for sha256, mime_type in connection.execute(
        text(
            "SELECT DISTINCT payload->>'sha256', payload->>'mime_type' "
            "FROM archived_rows a WHERE table_name = 'documents' AND " + _CHOSEN
        ),
        {"chosen": chosen},
    ):
        wanted += [
            (DocumentsBucket.name, DocumentsBucket.key_for(sha256, mime_type)),
            (ParsedBucket.name, ParsedBucket.key_for(sha256)),
        ]
    for language in connection.execute(
        text(
            "SELECT DISTINCT payload->>'language' FROM archived_rows a "
            "WHERE table_name = 'topics' AND " + _CHOSEN + " "
            "AND payload->>'topic_index' IS NOT NULL"
        ),
        {"chosen": chosen},
    ).scalars():
        wanted += [
            (ExportBucket.name, ExportBucket.topic_visualisation_key(language)),
            (ModelsBucket.name, ModelsBucket.topic_model_key(language)),
        ]
    archive = ArchiveBucket()
    return [
        (bucket, key) for bucket, key in wanted if not archive.give_back(bucket, key)
    ]


#: A document one of whose archived passages is back is chunked, which the delete-derived
#: that took them never undid and the archive never recorded.
_CHUNKED = (
    """
UPDATE documents d SET chunk_status = 'chunked'
WHERE d.chunk_status::text <> 'chunked'
  AND EXISTS (
    SELECT 1 FROM passages p WHERE p.doc_sha256 = d.sha256 AND p.id IN (
      SELECT (a.payload->>'id')::bigint FROM archived_rows a
      WHERE a.table_name = 'passages' AND """
    + _CHOSEN
    + """))
"""
)

#: How many ids the restore prints of the questions it can reopen.
_LISTED = 20

#: Questions a fact's deletion rejected as source_changed, and whose facts
#: the restore has put back. Nothing re-opens them: that is `questions-reverify`.
_REOPENABLE = (
    """
SELECT q.id FROM questions q
WHERE q.status = 'rejected' AND q.rejected_reason = 'source_changed'
  AND q.id IN (SELECT (a.payload->>'question_id')::bigint FROM archived_rows a
               WHERE a.table_name = 'question_facts' AND """
    + _CHOSEN
    + """)
  AND NOT EXISTS (
    SELECT 1 FROM archived_rows a
    WHERE a.table_name = 'question_facts' AND """
    + _CHOSEN
    + """
      AND (a.payload->>'question_id')::bigint = q.id
      AND NOT EXISTS (SELECT 1 FROM question_facts f WHERE f.question_id = q.id
                      AND f.fact_id = (a.payload->>'fact_id')::bigint))
ORDER BY q.id
"""
)


def _chosen(connection: Connection, named: str) -> list[datetime] | None:
    """Reads AT as the archived_at values it names, or None if one holds nothing."""
    chosen = [
        connection.execute(
            text("SELECT CAST(:at AS timestamptz)"), {"at": one.strip()}
        ).scalar_one()
        for one in named.split(",")
        if one.strip()
    ]
    for at in chosen:
        if not connection.execute(
            text("SELECT EXISTS (SELECT 1 FROM archived_rows WHERE archived_at = :at)"),
            {"at": at},
        ).scalar_one():
            print(f"Nothing was archived at {at.isoformat()}: list them without AT.")
            return None
    return chosen


def main() -> int:
    """Puts back the rows and objects of the deleting transactions AT names.

    The rows go back in one transaction. A row whose parent is absent is
    left behind and counted, so the rest still comes back.

    Returns:
        0, 1 when nothing was restored or an upload is in neither bucket,
        or 2 when AT is unset and the deletions were only listed.
    """
    named = os.environ.get("AT")
    since_named = os.environ.get("SINCE")
    with engine().connect() as connection:
        if not named:
            since = (
                connection.execute(
                    text("SELECT CAST(:since AS timestamptz)"), {"since": since_named}
                ).scalar_one()
                if since_named
                else None
            )
            _deletions(connection, since)
            return 2
        chosen = _chosen(connection, named)
        if not chosen:
            return 1
        restorable = []
        for at in chosen:
            tables = {
                table
                for (table,) in connection.execute(
                    text(
                        "SELECT DISTINCT table_name FROM archived_rows "
                        "WHERE archived_at = :at"
                    ),
                    {"at": at},
                )
            }
            if _replaced(connection, at, tables):
                print(
                    f"Not restorable: {at.isoformat()} is a refit's replacement of "
                    "the topics, and a later fit holds them."
                )
            else:
                restorable.append(at)
        if not restorable:
            return 1
        chosen = restorable
        held = {
            table: rows
            for table, rows in connection.execute(
                text(
                    "SELECT table_name, count(*) FROM archived_rows a "
                    "WHERE " + _CHOSEN + " GROUP BY table_name"
                ),
                {"chosen": chosen},
            )
        }
        wanted = [
            name.strip()
            for name in os.environ.get("TABLES", "").split(",")
            if name.strip()
        ]
        if unknown := [name for name in wanted if name not in TABLES]:
            print(f"TABLES names no table: {', '.join(unknown)}")
            return 1
        names = [
            one
            for one in TABLES
            if one in held and (one in wanted if wanted else one not in OPT_IN)
        ]
        print(
            f"Restoring {len(chosen)} deletion(s): "
            + ", ".join(at.isoformat() for at in chosen)
            + "\n"
        )
        skipped = [one for one in held if one not in names]
        behind: dict[str, int] = {}
        try:
            for table in names:
                parameters = {
                    "table": table,
                    "chosen": chosen,
                    "defaults": _defaults(connection, table, chosen),
                }
                parents = _parents(table)
                cleared = _cleared(table)
                left = connection.execute(
                    text(
                        _ORPHANS.format(table=table, parents=parents, cleared=cleared)
                    ),
                    parameters,
                ).scalar_one()
                restored = connection.execute(
                    text(
                        _RESTORE.format(
                            table=table, parents="AND " + parents, cleared=cleared
                        )
                    ),
                    parameters,
                ).rowcount
                print(f"  {table:<20} {restored:>8} of {held[table]} row(s)")
                if left:
                    behind[table] = left
                if table == "questions":
                    connection.execute(text(_SUPERSEDED), {"chosen": chosen})
                    connection.execute(text(_ROOTLESS), {"chosen": chosen})
            connection.execute(text(_UNSOURCED_STAMP), {"chosen": chosen})
            dropped = connection.execute(text(_UNSOURCED), {"chosen": chosen}).rowcount
            connection.execute(text(_LANGUAGED), {"chosen": chosen})
            connection.execute(text(_CHUNKED), {"chosen": chosen})
            reopenable = (
                connection.execute(text(_REOPENABLE), {"chosen": chosen})
                .scalars()
                .all()
            )
        except (IntegrityError, ValueError) as exc:
            connection.rollback()
            print(f"\nNothing restored: {getattr(exc, 'orig', exc)}")
            return 1

        missing = _objects(connection, chosen)
        connection.commit()

    for table in skipped:
        print(f"  {table}: left as it is; name it in TABLES to put it back")
    for table, rows in behind.items():
        print(f"  {table}: {rows} row(s) left behind, their parent is not there")
    if dropped:
        print(
            f"  facts: {dropped} restored fact(s) dropped, left resting on no passage"
        )
    if reopenable:
        print(
            f"  questions: {len(reopenable)} rejected as source_changed have all their "
            f"facts back (the first {_LISTED}: "
            f"{', '.join(map(str, reopenable[:_LISTED]))}); no command "
            "reopens them: accept each again with PATCH /questions/<id>"
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
