# Database

One PostgreSQL schema, one module per table (`assessments.py` holds both
`assessments` and `assessment_metrics`), and the engine every process opens
its own pool against.

This package builds the connection to PostgreSQL. It holds **no business
logic**: a stage owns a repository over these models, and this package owns
the tables, the enums, the connection and the migrations.

## The tables

| Table | Holds | Written by |
|---|---|---|
| `ingest_events` | Every upload attempt that declares its length, refused ones included | [ingestion](../ingestion/README.md) |
| `documents` | One row per kept document, keyed by the SHA-256 of its bytes, carrying every stage's status | ingestion, then each stage's own column |
| `passages` | Text, numbered sentences, lemmas, language, table cells, bounding box, heading trail | [chunking](../preprocessing/chunking/README.md) |
| `facts` | One claim each, with its verdict, its rejection code and the configuration it was produced under | [extraction](../extraction/README.md) |
| `fact_passages` | Which passages a fact rests on, and the span it cited in each | extraction |
| `topics` | Both a fitted topic and a request to refit | [topic modelling](../topic_modelling/README.md), [question generation](../question_generation/README.md) |
| `passage_topics` | How much of each topic a passage holds | topic modelling |
| `questions` | The question, its answer, its derived difficulty, its thread, its embedding, its release and the models that wrote and checked it | question generation |
| `question_facts` | Which facts each question cites | question generation |
| `service_settings` | The settings a deployment changed | the API, the CLI, the UI |
| `assessments` | What an independent judge made of one artefact, and the queue the phase claims over | [the assessment phase](../assessment/README.md) |
| `assessment_metrics` | One judgement one judge made about one artefact — the name, the labels and the scores are Phoenix's, so a metric means the same here as anywhere else that posts one | the assessment phase |
| `prompts` | One prompt per version per service, stored **as composed** — the system message, the user message as its template, and the JSON schema the answer came back in | each stage, once before its first claim |
| `archived_rows` | Every row deleted from any of the thirteen above, as JSON | an AFTER DELETE trigger |

### `assessments` reaches its artefact through one of three keys

A fact, a topic or a question — exactly one foreign key is set and each
cascades. An assessment of a fact that has been deleted is an opinion about
nothing, and a polymorphic `(kind, id)` pair would have left it behind for
a trigger to sweep.

### `topics` carries two queues

A row with a **NULL `topic_index`** is a request to refit and belongs to
topic modelling. A row that **is** a topic belongs to question generation,
which queues over it by `question_status`.

Every operation on the second carries `topic_index IS NOT NULL`, because
without it `start` would queue the asking as though it were a subject and the
two workers would fight over one row.

### How a row reaches its topics

A fact or a question reaches its topics by **joining through its passages** —
`fact_passages` → `passage_topics` — rather than holding a topic of its own,
so no two rows can disagree about which topic a passage is in.

### Cascades and triggers

Deleting a document takes its passages, their topic memberships and, through
a trigger on `fact_passages`, each bridge citing one of them and each other
fact left citing no passage. A trigger on `question_facts` then reaches the
questions resting on those facts.

The `question_facts` trigger exists because a cascade cannot express it: a
question rests on *several* facts, so `ON DELETE CASCADE` from `facts` would
take the question when its **first** citation went rather than its last. A
question that loses a fact and keeps another is rejected as `source_changed`
instead, and its release cleared.

Both triggers lock the fact or the question before deciding, so two
deletions at once leave neither a fact with no citation nor a question with
no fact. The assessments of whatever goes cascade with it.

`ingest_events.sha256` is a plain column, not a foreign key, so the record
that an upload happened outlives the document and keeps its digest.

What a deletion does **not** take is `topics`, which has no foreign key to a
document. Deleting every document leaves the topics standing, describing
passages that are gone; the next fit replaces the rows of every language it
fits, and `make wipe` runs both in order.

### Nothing is deleted without a copy

Every table carries an `AFTER DELETE ... FOR EACH ROW` trigger that writes
the row into [`archived_rows`](qa_generator/archived_rows.py) as
`to_jsonb(OLD) - 'embedding'`. One shared function, because `to_jsonb` names
no column.

A trigger and not the services: one `make delete` reaches up to nine tables
and only the first row of it passes through any Python. A re-chunk, a re-extraction
and a statement typed into Adminer are archived the same way.

It is not a soft delete. There is no `deleted_at` on any table and the live
tables still lose the row. `make archive-purge` finishes a deletion; see
[`archive/`](../archive/README.md).

## Extensions

Installed by the initial revision and by
[`configs/postgres/init.sh`](../../configs/postgres/init.sh) alike:

| Extension | For |
|---|---|
| `vector` | The embedding column on `passages`, `facts`, `topics` and `questions`, and the HNSW indexes the dedup gates probe |
| `pg_trgm` | The trigram indexes behind the substring search on `passages.text`, `facts.statement` and `facts.evidence_text`; every other `q` box matches with no trigram index |

`tests/static/test_schema_extensions.py` checks that both routes build the
same database.

## Migrations

Alembic owns the schema. The models say what the tables should be; a revision
under [`migrations/versions/`](migrations/versions/) says how to get an
existing database there.

```bash
make migration m="add the dropped counts"  # write a revision from the models
make schema                                # apply everything outstanding
make schema-status                         # where the database is
make schema-down                           # take the newest revision back off
make schema-reset                          # drop every table and rebuild. Irreversible
make schema-stamp                          # adopt a database that already holds the tables
```

**Read the generated revision before applying it.** Autogenerate compares
tables, columns, indexes, foreign keys and column comments; it does not see
a CHECK constraint's body, a trigger, a data backfill, an extension, or
anything ordered. The three trigger functions, the fifteen triggers and the
two extensions in the initial revision are written by hand for that reason,
and `test_schema.py` compares every CHECK body against the models.

It does not compare an index *predicate* either. A partial index therefore
belongs in `__table_args__` as an `Index(..., postgresql_where=...)` rather
than as `index=True` on the column: the second renders a plain index, and
nothing downstream reports the difference.

Every revision is reversible, and
`tests/integration/database/test_migration_rollback.py` applies and takes
back out every one of them on a real PostgreSQL.

A revision's docstring says **why**; the diff says what.

`/status` and every queue compare the revision the database records with the
head these carry ([`revision.py`](qa_generator/revision.py)): until
`make schema` has applied it, `/status` is not green and a queue claims
nothing.

The eighteen revisions, oldest first:

| File | Changes |
|---|---|
| `20260927_1913_initial_schema.py` | Every table, index, constraint and column comment, the two extensions, the three trigger functions and the fifteen triggers |
| `20261001_1730_fact_keeps_its_other_citations.py` | A bridge goes with any citation it loses; any other fact only with its last |
| `20261008_1700_released_question_is_accepted.py` | A CHECK: a question in the release is `accepted` |
| `20261008_1710_question_losing_a_fact_is_rejected.py` | A question that loses one of its facts is rejected as `source_changed` and leaves the release; one left with none is deleted |
| `20261008_1720_upload_keeps_its_digest.py` | `ingest_events.sha256` is a plain column, no longer a foreign key to `documents` |
| `20261008_1730_topic_records_its_decision.py` | Adds `topics.decided_at`, when a person last named a topic or set its coverage |
| `20261008_1800_question_names_its_models.py` | Adds `questions.writer_model`, `verifier_model` and `phrasing_model` |
| `20261008_1810_orphan_triggers_lock_the_parent.py` | Both orphan triggers lock the fact or the question before deciding |
| `20261008_1820_citation_carries_both_bounds.py` | A citation that names its sentences must carry both evidence bounds |
| `20261008_1830_column_comments_say_what_is_there.py` | Comments only: `fact_passages.passage_id`, `assessment_metrics.metric`, `questions.question_type`, `questions.settings_version` |
| `20261008_1840_oversized_names_the_real_budget.py` | Comment only: `documents.oversized` names the budget the chunker cuts to |
| `20261009_1000_settings_version_comments.py` | Comments only: `settings_version` on `facts`, `topics` and `assessments`, and `questions.prompt_version` |
| `20261009_1200_column_comments_after_the_fixes.py` | Comments only: `prompts.version`, `prompts.digest`, `facts.prompt_version`, `topics.embedding` |
| `20261009_2000_refit_and_reader_comments.py` | Comments only: `topics.question_status`, `assessments.topic_id`, `prompts.service`, and the `service_settings` table |
| `20261013_2300_settles_opinion_comment.py` | Comment only: `questions.gate_scores` carries `settles` verdicts as opinions |
| `20261013_1200_a_refusal_cites_nothing.py` | Comment only: `fact_passages.position` says what a later position on a passage fact is |
| `20261013_1210_a_capped_prompt_names_its_floor.py` | Comments only: `facts.prompt_version` and `prompts.version` name the capped atomic prompt as 10+cap4 |
| `20261018_1200_passages_comment_says_what_a_rechunk_keeps.py` | Comment only: the `passages` table says a re-chunk keeps every passage it cuts again unchanged |

## Column comments

Column comments live on the models and are carried into the database by the
migrations, so `\d+ passages` in `psql` and Adminer's column list both say
what a column is for.

## Connections

Each process opens its **own** pool, sized by `DATABASE_POOL_SIZE` and
`DATABASE_POOL_OVERFLOW`. The total across the API and every worker has to
stay under PostgreSQL's `max_connections`.

Both are read before a service could ask a database for anything, so they are
served read-only through `/settings/platform` and marked `fixed`. Changing
one needs a restart. The URL is assembled from the credentials in `.env` and
is never a setting.

## Grafana reads as a different role

`grafana_reader` holds `SELECT` and nothing else. It is granted on **two**
databases, the application's and Phoenix's, which the Run dashboard reads
together. On Phoenix's it reads only the five tables that dashboard queries,
granted by `make up` and `make dev` through `make grafana-grants` once
Phoenix has made them.

The role is created by
[`configs/postgres/init.sh`](../../configs/postgres/init.sh), which only runs
on the first boot of an empty volume. On a stack that already has one:

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
| [`test_migration_rollback.py`](../../tests/integration/database/test_migration_rollback.py) | Every revision, applied and taken back out |
| [`test_constraints.py`](../../tests/integration/database/test_constraints.py), [`test_fact_constraints.py`](../../tests/integration/database/test_fact_constraints.py) | What the database refuses to hold |
| [`test_indexes.py`](../../tests/integration/database/test_indexes.py) | The indexes and column types the queries are written against |
| [`test_trigger.py`](../../tests/integration/database/test_trigger.py) | The triggers that delete a fact or a question once its last source is gone, two deletions at once included |
| [`test_queue.py`](../../tests/integration/database/test_queue.py), [`test_question_queue.py`](../../tests/integration/database/test_question_queue.py) | Claiming, the lease sweep, and two queues on one table |
| [`test_orphans.py`](../../tests/integration/test_orphans.py) | What survives deleting every document |
| [`tests/static/test_migrations.py`](../../tests/static/test_migrations.py) | The revision chain: one head, no gaps |
| [`tests/static/test_schema_extensions.py`](../../tests/static/test_schema_extensions.py) | The migrations install every extension the bootstrap does |

These start a PostgreSQL of their own through testcontainers and skip, with a
reason, where no container engine answers.

## Limits

- **A CHECK constraint duplicates a check the code already makes.** That is
  deliberate for `unsupported_addition` and `unresolved_reference`, so a bug
  in the checker cannot store a fact that contradicts them.
- **`make schema-reset` is irreversible.** The data is gone; the objects in
  the buckets are not.
- **Autogenerate will not notice a trigger.**
- **`documents` is the one row two stages both write.** Parsing owns
  `parse_status` and chunking owns `chunk_status`. Chunking reads
  `parse_status` to know which documents may be queued; parsing never reads
  `chunk_status`.
- **Deleting every document does not empty the corpus.** The topics survive.
