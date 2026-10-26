# Archive

Every deletion is the first of two. This is what the first one leaves behind,
and the second one that takes it.

```bash
make archive                          # what is held, by table, with its age
make archive-purge TABLE=questions    # one table's rows
make archive-purge DAYS=30            # everything held longer than that
make archive-purge ALL=1              # the whole thing, objects included
# a purge deletes 10,000 rows per committed transaction; `python -m archive.run --size` estimates rows and size from pg_class
```

## Nothing here archives anything

The archiving is a **trigger**, not code in this package:

```
DELETE on any table  ──▶  archive_deleted_row()  ──▶  archived_rows
                                                       (table_name, payload, archived_at)
```

An `AFTER DELETE ... FOR EACH ROW` trigger on all thirteen tables and one
shared function, both created by the first migration,
[`20260927_1913_initial_schema.py`](../database/migrations/versions/20260927_1913_initial_schema.py).
The table it fills is declared in
[`archived_rows.py`](../database/qa_generator/archived_rows.py).

A trigger because the services are not where most of the deleting happens.
`make delete SHA=...` removes one row; the foreign keys take its passages,
their memberships and their citations, then
`fact_passages_delete_orphan_fact` takes every bridge resting on a passage
that is gone and every other fact left resting on none, then
`question_facts_delete_orphan_question` rejects every question left with no
fact as `source_changed` and keeps it; the questions resting on the
document's removed facts were deleted first, explicitly, by the repository, so the cascade
on `follows_id` takes their follow-ups and the cascades on `assessments`
their judgements. One command, up to nine tables,
and only the first row passes through Python.

The objects are the other half: the removal paths **move** them to the
`archive` bucket, keyed `{origin}/{key}@{UTC time}`, so a second deletion of
the same key keeps a second copy. A copy taken before the stamp is keyed
`{origin}/{key}`.

| Deletion | What it archives |
|---|---|
| `make delete SHA=` | The document's rows and everything cascading from them; its file and its parsed form |
| `make delete-derived SHA=` | Its passages, and by cascade its facts and questions |
| `make wipe` | All of that for every document, plus the upload history and the topics |
| `make topics-delete` | Every topic and membership, the stored factorisations and the pyLDAvis figures |
| A re-chunk, a re-extraction, a rerun | Whatever the new run replaced |
| Anything typed into psql or Adminer | The same |

## Not a soft delete

There is no `deleted_at` anywhere. That would be a predicate every query in
every repository has to grow and one of them will forget, and the partial
indexes serving the queue columns would have to carry it too. The live tables
still lose the row, so nothing that already works reads differently and the
archive is a table nothing joins to.

The cost is that there is no undo, only a restore:

```bash
make restore-documents                         # the newest deleting transactions
make restore-documents SINCE=2026-10-07T09:14  # every one from then on (only lists)
make restore-documents AT=<archived_at>[,...]  # put those deletions back
```

The listing names each deleting transaction by its exact `archived_at` with
the rows it took per table. `AT` puts back those transactions and nothing
archived beside them: the facts a re-extraction replaced and a setting
somebody cleared stay as they are. It puts the rows back with
`jsonb_populate_record`, in foreign-key order, primary keys included, and
copies the files, parsed forms, figures and models of the documents and
topics among them back out of the bucket. It is a copy: the archive keeps
what it held.

- **A row whose key a live row holds is skipped**, and so is an object
  already in its bucket. A second run restores nothing.
- **A row or an object archived twice comes back as its newest copy.** The
  newest object is the one the store wrote last, whatever `SINCE` says.
- **A row whose parent is gone is left behind.** It rests on nothing, so it
  stays in the archive and the run counts it; the other rows go back in one
  transaction.
- **A restored question keeps its release only where it still belongs to
  one.** The release stays where a question live all along holds the same id,
  and a follow-up also needs the turn it follows still accepted and released in it; otherwise the
  question comes back accepted but undrawn.
- **A duplicate refusal whose twin is gone comes back pointing at none.** Its
  twin, a fact of another passage, may have been deleted or read again since;
  where it is neither live nor put back by the same restore, `twin_id` comes
  back NULL, which marks the refusal for the dedup replay that points it at a
  twin again, rather than failing its foreign key and the whole restore.
- **A fact left resting on no passage is dropped.** Its citations were left
  behind, and the trigger that drops such a fact fires only on `DELETE`, so
  the restore does it, with the question links that cascade from it.
- **`AT` is required, and `SINCE` only lists.** The archive also holds every
  row a rerun replaced, and restoring those would put them beside their
  replacements.
- **`service_settings` and `prompts` are skipped** unless `TABLES` names them;
  `TABLES=a,b` restricts the restore to those tables.
- **A refit's transaction is listed as not restorable.** Its topics and
  memberships were deleted and a later fit holds the same topics under their
  unique key; it is skipped, and the run fails if nothing else was chosen.
- **A restored document with passages is marked `chunked`**, in the restore's
  transaction.
- **Rejected questions whose facts are all back are listed** with their ids.
  No command reopens them (`make questions-reverify` skips every rejected
  question): a person accepts each again, with `PATCH /questions/<id>`.

The `embedding` comes back NULL. It is the one column not kept — a vector
renders as about 13 kB of text a row, ten times everything else a fact holds
— and it is recomputed from the text it belongs to. `extract-embed` puts the
passages' and the facts' back; nothing writes a stored question's again.

The key is dropped from the jsonb rather than the column named per table, and
`jsonb - text` on a row without that key is the row unchanged, so one
function serves the four tables carrying a vector and the nine that do not.

## What a purge measures its age by

**The database's clock, read once.** The purge reads `now()` less the age
from the database and cuts both halves at that moment: `archived_at` and an
object's `LastModified` alike. The host running the purge is not asked.

`TABLE=` is about rows and leaves the bucket alone — an archived upload
belongs to no table. `DAYS=` and `ALL=1` take the objects too.

`DAYS=` refuses an age below zero, and `DAYS=0` is everything held until
now. `DAYS=` and `ALL=1` each warn and pause first, and `ALL=1` beside
`TABLE=` or `DAYS=` is refused.

## It grows on ordinary runs

A re-extraction deletes the facts it replaces, a re-chunk deletes the
passages, and the topic queue deletes its own pending rows; all of that is
archived. `make archive` is how you see it, and there is **no automatic
retention**.

## Layout

| File | Holds |
|---|---|
| [`store.py`](store.py) | Reading the archive and emptying it, over both the table and the bucket |
| [`run.py`](run.py) | The command line |
| [`restore.py`](restore.py) | Putting archived rows and objects back, before a purge makes the archive unreadable |

The table is in
[`database/qa_generator/archived_rows.py`](../database/qa_generator/archived_rows.py),
the trigger in the first migration, and the bucket is
[`blob_store/s3/archive.py`](../blob_store/s3/archive.py).
Neither imports this package.

## Tests

```sh
poetry run pytest tests/integration/test_archive.py tests/integration/test_restore.py
poetry run pytest tests/unit/archive
```

[`test_archive.py`](../../tests/integration/test_archive.py) covers the rows
a cascade archives, the objects a deletion moves, and each shape of purge.
Every test deletes through a path a person uses and reads `archived_rows`
afterwards; one inserting into it directly would pass against no trigger at
all.

`test_every_table_archives_its_deletions` compares the triggers against
`Base.metadata`, so a table added without one fails rather than deleting for
good.

[`test_restore.py`](../../tests/integration/test_restore.py) restores a
wipe and its edge cases, and
[`test_archive_cli.py`](../../tests/unit/archive/test_archive_cli.py) covers
which purges the command line refuses.

## Limits

- **Nothing is ever purged automatically.**
- **`TRUNCATE` fires no row trigger and archives nothing.**
  `make schema-reset` and the test fixtures empty tables without a copy.
- **The embedding does not come back.** Restored passages and facts carry
  NULL until `make extract-embed`; a restored question keeps NULL.
- **A question the deletion rejected comes back rejected.** A partial
  `make delete SHA=` rejects, as `source_changed`, every question that loses
  one fact and keeps another. That was an update, which nothing archives, so
  the restore puts every fact link back and leaves the status as it is;
  a person decides it again.
- **A column added `NOT NULL` since a row was archived** takes its server
  default; with no default the restore stops, naming the column, and puts
  nothing back.
- **A purge is not archived.** Otherwise it would write one row for every row
  it took.
- **`make delete` twice is not a way to purge.** `make archive-purge` is the
  only thing that empties the archive.
