# Archive

Every deletion is the first of two. This is what the first one leaves behind,
and the second one that takes it.

```bash
make archive                          # what is held, by table, with its age
make archive-purge TABLE=questions    # one table's rows
make archive-purge DAYS=30            # everything held longer than that
make archive-purge ALL=1              # the whole thing, objects included
```

## Nothing here archives anything

The archiving is a **trigger**, not code in this package:

```
DELETE on any table  ──▶  archive_deleted_row()  ──▶  archived_rows
                                                       (table_name, payload, archived_at)
```

An `AFTER DELETE ... FOR EACH ROW` trigger on all thirteen tables, one shared
function, declared beside the table it fills in
[`archived_rows.py`](../database/qa_generator/archived_rows.py).

A trigger because the services are not where most of the deleting happens.
`make delete SHA=...` removes one row; the foreign keys take its passages,
their memberships and their citations, then
`fact_passages_delete_orphan_fact` takes every fact resting on a passage that
is gone, then `question_facts_delete_orphan_question` takes every question
left with no fact, then the cascade on `follows_id` takes their follow-ups.
One command, six tables, and only the first row passes through Python.

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
make restore-documents                         # the deletions held, by minute
make restore-documents SINCE=2026-10-07T09:14  # everything archived from then on
```

It puts every row archived at or after `SINCE` back with
`jsonb_populate_record`, in foreign-key order, primary keys included, and
copies the files, parsed forms, figures and models of the documents and
topics among them back out of the bucket. It is a copy: the archive keeps
what it held.

- **A row whose key a live row holds is skipped**, and so is an object
  already in its bucket. A second run restores nothing.
- **A row or an object archived twice comes back as its newest copy.** The
  newest object is the one the store wrote last, whatever `SINCE` says.
- **A row whose parent is gone restores nothing at all.** The rows go back
  in one transaction.
- **`SINCE` is required.** The archive also holds every row a rerun
  replaced, and restoring those would put them beside their replacements.

The `embedding` comes back NULL. It is the one column not kept — a vector
renders as about 13 kB of text a row, ten times everything else a fact holds
— and it is recomputed from the text it belongs to. `extract-embed` puts the
passages' and the facts' back; nothing writes a stored question's again.

The key is dropped from the jsonb rather than the column named per table, and
`jsonb - text` on a row without that key is the row unchanged, so one
function serves the four tables carrying a vector and the nine that do not.

## What a purge measures its age by

Each half measures it **by the clock that wrote it**: `archived_at` against
the database's `now()`, an object's age against its own `LastModified`. A
host computing one cutoff for both would purge by however far its clock has
drifted from theirs.

`TABLE=` is about rows and leaves the bucket alone — an archived upload
belongs to no table. `DAYS=` and `ALL=1` take the objects too.

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

The trigger and the table are in
[`database/qa_generator/archived_rows.py`](../database/qa_generator/archived_rows.py),
and the bucket is
[`blob_store/s3/archive.py`](../blob_store/s3/archive.py).
Neither imports this package.

## Tests

```sh
poetry run pytest tests/integration/test_archive.py
```

[`test_archive.py`](../../tests/integration/test_archive.py) covers the rows
a cascade archives, the objects a deletion moves, and each shape of purge.
Every test deletes through a path a person uses and reads `archived_rows`
afterwards; one inserting into it directly would pass against no trigger at
all.

`test_every_table_archives_its_deletions` compares the triggers against
`Base.metadata`, so a table added without one fails rather than deleting for
good.

## Limits

- **Nothing is ever purged automatically.**
- **`TRUNCATE` fires no row trigger and archives nothing.**
  `make schema-reset` and the test fixtures empty tables without a copy.
- **The embedding does not come back.** Restored rows carry NULL until the
  stage that writes it runs again.
- **A purge is not archived.** Otherwise it would write one row for every row
  it took.
- **`make delete` twice is not a way to purge.** `make archive-purge` is the
  only thing that empties the archive.
