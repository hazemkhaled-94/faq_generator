# Archive

Every deletion keeps a copy of what it removed. This package lists, restores
and purges those copies.

```bash
make archive                                           # what is held, by table, with its age
make archive-purge TABLE=questions CONFIRM=<database>  # one table's rows
make archive-purge DAYS=30 CONFIRM=<database>          # everything held longer than that
make archive-purge ALL=1 CONFIRM=<database>            # the whole thing, objects included
# a purge deletes 10,000 rows per committed transaction; `python -m archive.run --size` estimates rows and size from pg_class
```

## How rows are archived

A trigger archives, not this package.

```
DELETE on any table  ──▶  archive_deleted_row()  ──▶  archived_rows
                                                       (table_name, payload, archived_at)
```

An `AFTER DELETE ... FOR EACH ROW` trigger on all thirteen tables calls one
shared function, both from the first migration,
[`20260927_1913_initial_schema.py`](../database/migrations/versions/20260927_1913_initial_schema.py).
It covers deletions that never pass through Python: the foreign keys and
orphan triggers behind one `make delete SHA=... CONFIRM=<database>` are
described in the [database README](../database/README.md#deletion).

The removal paths move objects to the `archive` bucket, keyed
`{origin}/{key}@{UTC time}` (`{origin}/{key}` for a copy taken before the
stamp existed).

| Deletion | What it archives |
|---|---|
| `make delete SHA= CONFIRM=<database>` | The document's rows, everything cascading from them, its file and its parsed form |
| `make delete-derived SHA= CONFIRM=<database>` | Its passages, and by cascade its facts and questions |
| `make wipe CONFIRM=<database>` | All of that for every document, plus the upload history and the topics |
| `make topics-delete CONFIRM=<database>` | Every topic and membership, the stored models and the figures |
| A re-chunk, a re-extraction, a rerun, or SQL typed into psql or Adminer | Whatever the new run or statement replaced |

This is not a soft delete: no table has `deleted_at`. There is no undo,
only a restore.

## Restoring

```bash
make restore-documents                         # lists the newest deleting transactions
make restore-documents SINCE=2026-10-07T09:14  # lists every one from then on (only lists)
make restore-documents AT=<archived_at>[,...]  # puts those deletions back
```

The listing names each deleting transaction by its `archived_at` with the
rows it took per table. `AT` is required: it restores those transactions and
nothing archived beside them, with the files, parsed forms, figures and
models they own. `SINCE` only lists, because the archive also holds every row
a rerun replaced. The archive keeps what it held.

- A row whose key a live row holds is skipped, as is an object already in its
  bucket, so a second run restores nothing. Twice-archived items come back as
  the newest copy.
- A row whose parent is gone, or a follow-up whose root is gone (with every
  turn below it), stays in the archive and is counted. The rest goes back in
  one transaction.
- A restored question keeps its release only where a live question holds the
  same id. A follow-up also needs the turn it follows accepted and released.
- A duplicate refusal whose twin is neither live nor restored comes back with
  `twin_id` NULL.
- A fact left resting on no passage is dropped, with its question links.
- `service_settings` and `prompts` are skipped unless `TABLES` names them.
  `TABLES=a,b` restricts the restore to those tables.
- A refit's transaction is not restorable. A restored document with passages
  is marked `chunked`.
- Rejected questions whose facts are all back are listed. Accept each with
  `PATCH /questions/<id>`: no command reopens them.

The `embedding` comes back NULL. `make extract-embed` recomputes the
passages' and facts' vectors, but nothing recomputes a question's.

## Purging

A purge reads the database's clock once and cuts both `archived_at` and an
object's `LastModified` at that moment.

`TABLE=` deletes rows only. `DAYS=` and `ALL=1` also delete objects, and
each warns and pauses first. `DAYS=0` means everything held until now, and a
negative age is refused, as is `ALL=1` beside `TABLE=` or `DAYS=`.

A re-extraction or re-chunk archives what it replaces, so the archive grows
on ordinary runs. There is no automatic retention.

## Layout

[`store.py`](store.py) reads and empties the archive,
[`run.py`](run.py) is the command line and [`restore.py`](restore.py) puts
rows and objects back. The table is
[`archived_rows.py`](../database/qa_generator/archived_rows.py) and the bucket
[`blob_store/s3/archive.py`](../blob_store/s3/archive.py). Neither imports
this package.

## Tests

```sh
poetry run pytest tests/integration/test_archive.py tests/integration/test_restore.py
poetry run pytest tests/unit/archive
```

`test_every_table_archives_its_deletions` in
[`test_archive.py`](../../tests/integration/test_archive.py) fails for a table
added without a trigger.

## Limits

- Nothing is purged automatically. A purge is not archived.
- `TRUNCATE` archives nothing, so `make schema-reset CONFIRM=<database>` and
  the test fixtures empty tables without a copy. `make down-volumes
  CONFIRM=all-volumes` removes the archive with all other container data.
- A question that a partial `make delete SHA= CONFIRM=<database>` rejected as
  `source_changed` comes back rejected, because nothing archives an update.
  The restore puts its fact links back. A person decides it again.
- A column added `NOT NULL` since a row was archived takes its server
  default, or the restore stops and names the column.
- Only `make archive-purge` empties the archive. Running `make delete` twice
  does not.
