# Database

The PostgreSQL schema: one module per table (`assessments.py` holds both
`assessments` and `assessment_metrics`), the enums, the connection and the
migrations. It holds no business logic. Each stage owns a repository over
these models.

## Tables

| Table | Holds | Written by |
|---|---|---|
| `ingest_events` | Every upload attempt that declares its length, refused ones included | [ingestion](../ingestion/README.md) |
| `documents` | One row per kept document, keyed by the SHA-256 of its bytes, with each stage's status | ingestion, then each stage's own column |
| `passages` | Text, numbered sentences, lemmas, language, table cells, bounding box, heading trail | [chunking](../preprocessing/chunking/README.md) |
| `facts` | One claim each, with its verdict, rejection code and producing configuration | [extraction](../extraction/README.md) |
| `fact_passages` | Which passages a fact rests on, and the span cited in each | extraction |
| `topics` | Both a fitted topic and a request to refit | [topic modelling](../topic_modelling/README.md), [question generation](../question_generation/README.md) |
| `passage_topics` | How much of each topic a passage holds | topic modelling |
| `questions` | The question, answer, difficulty, thread, embedding, release and the models that wrote and checked it | question generation |
| `question_facts` | Which facts each question cites | question generation |
| `service_settings` | The settings a deployment changed | the API, the CLI, the UI |
| `assessments` | What an independent judge made of one artefact, and its queue | [the assessment phase](../assessment/README.md) |
| `assessment_metrics` | One judgement by one judge about one artefact, with Phoenix's names, labels and scores | the assessment phase |
| `prompts` | One prompt per version per service, stored as composed (system message, user template, answer JSON schema) | each stage, once before its first claim |
| `archived_rows` | Every row deleted from any of the thirteen tables above, as JSON | an AFTER DELETE trigger |

An assessment reaches its artefact (fact, topic or question) through exactly
one of three cascading foreign keys.

`topics` carries two queues. A row with a NULL `topic_index` is a request to
refit and belongs to topic modelling. A row with an index is a topic and
belongs to question generation, which queues over it by `question_status`.
Every question generation operation on topics tests `topic_index IS NOT
NULL`, or a refit request is queued as a subject.

A fact or question reaches its topics through its passages (`fact_passages`,
then `passage_topics`).

## Deletion

Deleting a document deletes its passages and their topic memberships. A
trigger on `fact_passages` then deletes each bridge citing one of those
passages and each other fact left citing none. A trigger on `question_facts`
reaches the questions resting on those facts. Their assessments cascade.

A question that loses a fact is rejected as `source_changed` and leaves its
release. The trigger never deletes a question, so a re-chunk or
re-extraction keeps every accepted, reviewed and released question. A
document deletion by a person deletes the questions resting on its facts
explicitly, before the cascade (`ingestion.repository`).

A third trigger, `questions_release_thread_whole`, removes every follow-up
below a question (through `follows_id`) from the release when that question
stops being accepted. The follow-ups keep their status. A restore applies the
same rule.

The triggers lock the fact or question before deciding. The deleting paths
first call `lock_reached`, which locks the facts, questions and duplicate
refusals the cascade reaches in id order, so two deletions cannot wait on
each other.

`ingest_events.sha256` is a plain column, not a foreign key, so the record of
an upload outlives its document. Topics have no foreign key to a document, so
deleting every document leaves them standing. The next fit replaces the rows
of every language it fits, and `make wipe` runs both in order.

### Archive trigger

Every table carries an `AFTER DELETE ... FOR EACH ROW` trigger that writes
the row into [`archived_rows`](qa_generator/archived_rows.py) without its
embedding, whatever path deleted it. It is not a soft delete: no table has
`deleted_at`. `make archive-purge` finishes a deletion; see
[`archive/`](../archive/README.md).

## Extensions

Installed by the initial revision and by
[`configs/postgres/init.sh`](../../configs/postgres/init.sh), which
`tests/static/test_schema_extensions.py` checks agree.

| Extension | For |
|---|---|
| `vector` | The embedding column on `passages`, `facts`, `topics` and `questions`, and the HNSW indexes the dedup gates probe |
| `pg_trgm` | The trigram indexes behind the substring search on `passages.text`, `facts.statement` and `facts.evidence_text`. Every other `q` box matches without one |

## Migrations

Alembic owns the schema. A revision under
[`migrations/versions/`](migrations/versions/) takes an existing database to
what the models declare.

```bash
make migration m="add the dropped counts"  # write a revision from the models
make schema                                # apply everything outstanding
make schema-status                         # where the database is
make schema-down CONFIRM=<database>        # take the newest revision back off
make schema-reset CONFIRM=<database>       # drop every table and rebuild. Irreversible
make schema-stamp                          # adopt a database that already holds the tables
```

Read the generated revision before applying it. Autogenerate does not see a
CHECK constraint's body, a trigger, a data backfill, an extension, an index
predicate or anything ordered. Declare a partial index as
`Index(..., postgresql_where=...)` in `__table_args__`: `index=True` on the
column renders a plain index.

Every revision is reversible, and
`tests/integration/database/test_migration_rollback.py` applies and reverses
each one on a real PostgreSQL. Five lose information on the way down:

- `20261019_2300`: re-applying turns every compound question into
  `needs_both`.
- `20261020_0100`: drops each bridge's relation and probe question.
- `20261020_1200`: does not put removed follow-ups back in the release.
- `20261021_0100`: deletes the `rubric_` scores, which the narrower CHECK
  refuses.
- `20261021_0200`: drops the stored categories.

Each revision runs in its own transaction with a 5 second lock timeout and a
10 minute statement timeout (`migrations/env.py`). A revision after
`20261021_0300` therefore:

- adds a CHECK as `NOT VALID` (`op.execute("ALTER TABLE ... ADD CONSTRAINT
  ... CHECK (...) NOT VALID")`) and validates it in a later revision.
  `op.create_check_constraint` scans the table under its lock, and
  `tests/static/test_migrations.py` refuses it;
- backfills many rows in batches, committed one at a time, outside the DDL
  transaction;
- builds an index on a table with data `CONCURRENTLY`, in an autocommit block.

Two revisions on `facts` break the last two rules and hold `facts` for their
whole run: `20261024_0100` (builds `ix_facts_twin_id`) and `20261024_1300`
(backfills `facts.language` in one `UPDATE`). On 13,716 facts each took 21 s
with the workers stopped, as [operations](../../docs/operations.md) orders.
On a much larger corpus, time them on a copy first.

`/status` and every queue compare the database's revision with the head in
[`revision.py`](qa_generator/revision.py). Until `make schema` applies the
head, `/status` is not green and no queue claims anything.

### Revisions

The initial revision, `20260927_1913_initial_schema.py`, creates every table,
index, constraint and column comment, the two extensions and, by hand, the
three trigger functions and fifteen triggers. File names say what a later
revision changes, and its docstring says why. Column comments live on the
models, so `\d+ passages` in `psql` shows what a column is for.

## Connections

Each process opens its own pool, sized by `DATABASE_POOL_SIZE` and
`DATABASE_POOL_OVERFLOW`. The total across the API and every worker must stay
under PostgreSQL's `max_connections`. Both are read-only in
`/settings/platform` (`fixed`) and need a restart to change. The URL is
never a setting.

## Grafana role

`grafana_reader` holds `SELECT` and nothing else, on the application's
database and on Phoenix's. On Phoenix's it reads only the five tables the Run
dashboard queries, granted by `make up` and `make dev` through
`make grafana-grants` once Phoenix has created them.

[`configs/postgres/init.sh`](../../configs/postgres/init.sh) creates the
role and runs only on the first boot of an empty volume. On an existing
stack:

```bash
podman compose exec postgres bash /docker-entrypoint-initdb.d/init.sh
```

## Tests

```sh
poetry run pytest tests/integration/database
```

| File | Covers |
|---|---|
| [`test_schema.py`](../../tests/integration/database/test_schema.py) | The schema alembic builds on an empty database |
| [`test_migration_rollback.py`](../../tests/integration/database/test_migration_rollback.py) | Every revision, applied and reversed |
| [`test_constraints.py`](../../tests/integration/database/test_constraints.py), [`test_fact_constraints.py`](../../tests/integration/database/test_fact_constraints.py) | What the database refuses to hold |
| [`test_indexes.py`](../../tests/integration/database/test_indexes.py) | Indexes and column types |
| [`test_trigger.py`](../../tests/integration/database/test_trigger.py) | The delete triggers, two deletions at once included |
| [`test_queue.py`](../../tests/integration/database/test_queue.py), [`test_question_queue.py`](../../tests/integration/database/test_question_queue.py) | Claiming, the lease sweep, two queues on one table |
| [`test_orphans.py`](../../tests/integration/test_orphans.py) | What survives deleting every document |
| [`test_migrations.py`](../../tests/static/test_migrations.py), [`test_schema_extensions.py`](../../tests/static/test_schema_extensions.py) | One revision head. Migrations install the bootstrap's extensions |

These tests skip where no container engine answers.

## Limits

- A CHECK repeats the code check for `unsupported_addition` and
  `unresolved_reference`, so a checker bug cannot store such a fact.
- `make schema-reset` is irreversible. The data is gone; the objects in the
  buckets stay.
- `documents` is the one row two stages write. Parsing owns `parse_status`
  and chunking owns `chunk_status`. Only chunking reads the other's column.
