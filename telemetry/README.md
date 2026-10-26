# Telemetry

Logging and tracing, configured identically in every process (the API, the six
workers, the frontend, the orchestrator and the host commands) and called
before anything else.

## Which store holds what

| Tool | Holds | Does not hold |
|---|---|---|
| The application | The artefacts and the chain between them, with a link into each tool below | Anything about a run not stored on a row |
| Phoenix | Every stage's spans, every model call with its shape and prompt version, and every validation as an annotation | HTTP, SQL, object store and frontend spans |
| Grafana | Every line every process writes, joined to its trace and run | Infrastructure container logs |
| Argilla | The artefacts a person judged, one dataset per kind | |
| Dagster | What ran, what it produced, in what order | Row-level lineage |

### One number, in all five

[`pipeline.py`](pipeline.py) holds the seven stages once. The number in a name
is the stage's place in the pipeline, so each tool's alphabetical order is the
pipeline's order:

| Stage | Phoenix project (a run named with `RUN_ID` adds `-<name>`) | Argilla dataset | Dagster group |
|---|---|---|---|
| 1 ingestion | `1-ingestion` (host commands only; an upload sends nothing) | none | none |
| 2 parsing | `2-parsing` | none | `stage_2_parsing` |
| 3 chunking | `3-chunking` | none | `stage_3_chunking` |
| 4 extraction | `4-extraction` | `4-facts` | `stage_4_extraction` |
| 5 topic modelling | `5-topic_modelling` | `5-topic-labels` | `stage_5_topic_modelling` |
| 6 question generation | `6-question_generation` | `6-questions` | `stage_6_question_generation` |
| 7 assessment | `7-assessment` | none | `stage_7_assessment` |

`pipeline.py` also names each stage's Dagster asset and Argilla dataset.
[`tests/static/test_tool_names.py`](../tests/static/test_tool_names.py) fails
if a copy has gone stale.

### Where a person starts

`GET /lineage/{kind}/{id}` and the How this was produced fold on every
artefact page walk a question to its facts, a fact to its passages and a
passage to its document, each step linked to its span.

Two rules in [`traces.py`](traces.py) keep that line:

- Only a run exports. `configure(name, run=...)` builds an exporter only when
  `run` is given. A stage and the ingestion host commands pass
  `settings.runs.run_id()`. Everything else passes nothing.
- Only the logic is instrumented: litellm, and the spans the stages open. No
  requests, no botocore, no FastAPI. The database is instrumented only behind
  `TRACE_DATABASE`.

`make extract-bridge`, `make questions-balance` and `make questions-rejudge`
configure the exporter through `stages.cli.trace` after their preflight. The
bridge pass opens one `bridge_link` span per link.

A run's id is `questions.run_id` on the rows and `run.id` on every Phoenix
span and log line. The Run dashboard joins them.

## Logs

Each record is rendered twice: as text on stdout (`make logs`), and as one
JSON object per line in a file that reaches Elasticsearch.

```
api, 6 workers, streamlit, dagster  ──▶  logs volume  ─┐
                                                       ├─▶  filebeat  ──▶  elasticsearch  ──▶  grafana
a make target, dagster dev, by hand  ──▶  ./logs  ─────┘
```

Every level from `LOG_LEVEL` upwards is shipped. An exception is written
whole: `error.type`, `error.message` and the entire traceback in
`error.stack_trace`.

### Field names

`log.level`, `service.name`, `log.logger` and `error.type` are
[ECS](https://www.elastic.co/guide/en/ecs/current/index.html) names that
Elasticsearch's template already maps as keywords. `trace.id` ties a line to
its span, and `run.id` to its run.

Each stage binds its unit of work where it claims it, and every line beneath
carries it:

```python
with working(span, "extract", {"stage": self.name, "passage.id": passage.id}):
    log.info(
        "passage %d: %d fact(s)", passage.id, stored, extra={"facts.stored": stored}
    )
```

One call sets both, so a trace and its logs use the same names. `stage`,
`document.sha256`, `passage.id`, `topic.id`, `llm.duration_ms`, `facts.stored`
and the rest are fields, not prose in `message`. They are not ECS, so they are
declared in `setup.template.append_fields` in
[`configs/filebeat/filebeat.yml`](../configs/filebeat/filebeat.yml). Under
dynamic mapping a string arrives as `text`, and panels grouping by `stage`
find nothing.

### The log file

The file is named `{service}-{host}-{pid}.log`, unique per writer, because two
processes rotating one file take each other's lines. `make logs-prune` sweeps
files by age, and `make logs-wipe`, which `make wipe` runs, deletes every one.
Files rotate at 50 MB, three kept.

| Where | `LOG_DIR` | Set by |
|---|---|---|
| A container | `/var/log/qa`, the `logs` volume | compose |
| The host | `./logs`, bind-mounted into filebeat read-only | `configs/env/deployment.env` |
| Anywhere else | unset: stdout only | nothing |

Filebeat reads both paths in one input, so a `make` target's lines land in
Grafana beside a worker's, on the same trace. `host.name` tells them apart.
`make up` creates `./logs`.

## Traces

OpenTelemetry, to Phoenix. A span per unit of work, annotated with the log
field names.

A stage passes `settings.runs.run_id()` to `configure`, which sets
`openinference.project.name`. The project is the numbered stage. A run gets a
project of its own only when named:

```bash
make questions                      # 6-question_generation
make questions RUN_ID=a-gpt-4.1     # 6-question_generation-a-gpt-4.1
```

`run.id` is on every span, so two runs sharing a project stay separable by
filter.

The id a row carries is the run that asked for it, not the worker that took
it: a Dagster run, a Start button or a `make …-start` (see
[`settings/README.md`](../backend/settings/README.md)). The span attribute
carries the same value on every span begun while the row is worked, so a fact,
its log lines and its model calls filter on one id. A run named with `RUN_ID`
writes the name on its rows and files its spans under a project of that name.

The exporter is installed after the preflight, because a project is created by
the first span filed under it. `stages/cli.py` and `topic_modelling/run.py`
configure tracing only once the process will claim rows.

```bash
make phoenix-projects   # what Phoenix holds
make phoenix-prune      # take back the ones in which no work happened
```

`prune` takes a project only when every span in it is a model call and it
could read every span. A project too big to read in a page is left alone.
Neither `prune` nor `make phoenix-purge` takes `default`.

Each question's span carries the gate that stopped it and every gate that read
it, in order, as `question.gates_ran`.

`telemetry.asking` adds two attributes the instrumentor cannot know:

| On the span | Is |
|---|---|
| `tag.tags` | the Pydantic shape (`_Answered`, `_NamesItsSource`, `_Recovered`), spelled as `llm.shape` in the log |
| `llm.prompt_template.version` | the caller's `PROMPT_VERSION`. A caller that names none sets none |

The span carries the prompt filled in. The template is in the `prompts` table
(see [`backend/stages/prompts.py`](../backend/stages/prompts.py)).

### How much reaches Phoenix, and when

| | Carries | Sent |
|---|---|---|
| Spans | a stage's unit of work, and one `completion` per model call | batched: every 5 s or 512 spans |
| Annotations | gate verdicts, extraction's validations and the judge's | batched at 100, flushed after every passage in extraction and every topic in question generation, and by the judge when its queue empties and at the end of a drain |
| Prompts | what a version asked for | when a stage starts and finds one changed. `make prompts-publish` republishes all |
| Datasets | the golden cases | only on `make eval-upload` or `make eval-phrasing` |

OpenTelemetry batches spans itself, configured by `OTEL_BSP_MAX_QUEUE_SIZE`,
`OTEL_BSP_SCHEDULE_DELAY` and `OTEL_BSP_MAX_EXPORT_BATCH_SIZE`. A full queue
logs `Queue full, dropping spans`.

When Phoenix is down, spans and annotations are dropped. `evaluations.py`
warns once per outage and posts nothing for five minutes. The verdict is in
Postgres either way.

## Verdicts

A gate verdict is written three times: the row in Postgres (the truth), the
span attribute (what a trace is filtered by), and the annotation in Phoenix's
Evaluations view ([`evaluations.py`](evaluations.py), through
`arize-phoenix-client`). `annotator_kind` is CODE for every gate, phrasing
included, and every extraction validation.

The evaluation phase writes the LLM annotations: one per metric, named as
`arize-phoenix-evals` names it (`hallucination`, `relevance`,
`qa_correctness`, `summarization`, `toxicity`, `conciseness`, `refusal`), plus
an `assessment` summary per artefact. See
[`backend/assessment/`](../backend/assessment/README.md). `hallucination`
scores 1.0 for the bad label (direction minimise). Each annotation carries its
`direction` as metadata.

A question gets a `gate` summary (what stopped it, or `accepted`) and one
annotation per gate that read it, `gate 1: structural` through `gate 6:
round_trip`:

| Annotation | On an accepted question | On one refused at phrasing |
|---|---|---|
| `gate` | `accepted`, 1.0 | `leaks_source`, 0.0 |
| `gate 1: structural` | `passed`, 1.0 | `passed`, 1.0 |
| `gate 5: phrasing` | `passed`, 1.0 | **`refused`, 0.0** |
| `gate 6: round_trip` | `passed`, 1.0 | absent |

Only gates that ran are annotated, so a gate's rate is over the questions that
reached it. The number is the gate's fixed position, because Phoenix sorts
columns by name.

`PHOENIX_BASE_URL` is where they are posted. The bearer is `PHOENIX_API_KEY`
where compose set it and `PHOENIX_ADMIN_SECRET` where `.env` did.

## Configuration

| Setting | Where | What it does |
| --- | --- | --- |
| `LOG_LEVEL` | `configs/env/deployment.env` | Every service, the frontend included |
| `LOG_DIR` | `configs/env/deployment.env`, set over in `compose.yaml` | Where the JSON file goes. Unset means stdout only |
| `OTEL_CONTAINER_ENDPOINT` | `configs/env/deployment.env` | Trace collector, as the containers reach it |
| `TRACE_DATABASE` | unset | A span per SQL statement and per pool connect |

`LOG_DIR` is read through a variable, so the static settings scan cannot see
it. It is checked by hand.

## Spend

The cost log is the spend of record, and `make spend` reads it. The cost
Phoenix shows on a span is indicative, since Phoenix prices a model from its
own table.

## Retention

```bash
make logs-retention                        # 30 days in Elasticsearch
make logs-retention LOGS_RETENTION_DAYS=90
make logs-prune                            # 30 days of files on the volume
make logs-prune LOGS_KEEP_DAYS=7
```

Run `logs-retention` once against a running stack, after the shipper has
written something. Until then, nothing is deleted.

`logs-prune` deletes by mtime, through the api container, which mounts the
volume writable.

The retention belongs to the data stream, not to an ILM policy. The index is
`qa-logs`, not `qa-logs-<date>`, because a date in the name creates a second
data stream every midnight. Naming an ILM policy in `filebeat.yml` does not
work: Filebeat strips `index.lifecycle` from the template when
`setup.ilm.enabled` is false. `setup.template.overwrite: true` makes an edit
to `filebeat.yml` take effect at all.

## What is shipped, and what is not

Only this project's processes. The other containers (Postgres, SeaweedFS,
Redis, Elasticsearch, Phoenix, Argilla, Grafana, Adminer and Filebeat) keep
the `json-file` driver and are read with `make logs`.

`make logs-shipper` shows why nothing is arriving.

## Tests

```sh
poetry run pytest tests/unit/telemetry
```

| File | Covers |
|---|---|
| [`test_logs.py`](../tests/unit/telemetry/test_logs.py) | The JSON line and its fields |
| [`test_evaluations.py`](../tests/unit/telemetry/test_evaluations.py) | Annotations, and a run surviving a Phoenix that is down |
| [`test_traces.py`](../tests/unit/telemetry/test_traces.py) | Only a run exports, and only the logic is instrumented |
| [`test_projects.py`](../tests/unit/telemetry/test_projects.py) | Which projects a prune takes back |
| [`test_dashboards.py`](../tests/static/test_dashboards.py), [`test_log_fields.py`](../tests/static/test_log_fields.py) | Dashboards and bound fields against the datasources and the shipper |

## Limits

- `make logs-retention` never deletes a file: `make logs-prune` does.
- The api and the frontend produce no span: no exporter, and no Phoenix
  secret.
- An HTTP call and an S3 GET produce no span. SQL statements produce none
  unless `TRACE_DATABASE` is set.
- A new bound field needs adding to `append_fields`, or it arrives as `text`.
  A declared field reaches the template at once and the index at rollover.
- Elasticsearch shares its heap with Argilla. `ES_JAVA_OPTS` raises it.

## One server, many databases

Each Phoenix, Argilla and log name carries the database. `pipeline.scoped`
appends `__<database>`, read from `DATABASE_URL` or `APP_DB_NAME`: a Phoenix
project is `4-extraction__qa_generator`, and `make phoenix-purge` takes only
the projects that end so. A project filed before names carried the database
belongs to none and is left unless `ALL_DATABASES=1`.

Every log line carries a `db` field, which `make logs-wipe` deletes by. The
corpus job tags each Dagster run with the database, and `make dagster-wipe`
deletes the runs so tagged.

Phoenix datasets (the golden cases) are named `<name>__<database>`. `make
eval-upload` and `make eval-phrasing` upload this database's, and `make
phoenix-purge` takes only those unless `KEEP=golden`. A set uploaded before
names carried the database is taken only with `ALL_DATABASES=1`: upload it
again.
