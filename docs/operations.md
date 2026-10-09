# Operations

Running the stack, watching it, and what goes wrong.

## The services

Once `make dev` reports ready:

| Service | URL | Purpose |
|---|---|---|
| Frontend | <http://localhost:8501> | Run each stage, browse what it produced |
| API | <http://localhost:8000/docs> | OpenAPI documentation |
| Phoenix | <http://localhost:6006> | Traces, gate verdicts, judgements, prompts, experiments, the playground |
| Grafana | <http://localhost:3001> | Logs and pipeline dashboards |
| Argilla | <http://localhost:6900> | Review what the models decided |
| Adminer | <http://localhost:9001> | Database browser |
| Dagster | <http://localhost:3000> | The asset graph and run history |

Behind them: PostgreSQL, SeaweedFS, Elasticsearch, Redis, Filebeat, the
Dagster daemon and the six stage workers — twenty-four containers in all.

Every published port binds to 127.0.0.1, so each URL above answers on this
machine only. PostgreSQL and SeaweedFS's S3 gateway publish a port for the
host commands; SeaweedFS's master, filer and volume servers publish none.
The api answers only the host names in `API_ALLOWED_HOSTS`, and refuses with
403 a write a browser sends from another site.

`make services` and the System health page both ask `GET /services`, which
probes the catalogue in
[`backend/api/services.py`](../backend/api/services.py) live. Use that for
what is actually up.

Credentials are `PHOENIX_DEFAULT_ADMIN_INITIAL_PASSWORD` for Phoenix (sign in
as `admin@localhost`), `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`, and
`ARGILLA_USERNAME` / `ARGILLA_PASSWORD`.

## Scaling

`parse-worker`, `chunk-worker` and `extract-worker` scale horizontally — each
claims one row at a time with `FOR UPDATE SKIP LOCKED`:

```bash
export COMPOSE_ENV_FILES=configs/env/deployment.env,.env
podman compose up -d --scale extract-worker=4
```

`question-worker` scales the same way but has less to divide: its queue is
one row per topic. `topic-worker` can be scaled and there is no point — a fit
is one request row.

`question-worker` loads `EMBEDDING_MODEL`, 2.2 GB, before it claims anything,
and downloads it into the `models` volume if extract-worker has not. The
topics sit `pending` until it finishes and `make logs` says so. The container is given 6 GB for it and
`NLI_MODEL`'s weights, and the weights are per container, not per lane.

`assess-worker` is the cheapest of the six to scale and the only one that
loads **no** weights at all: it asks a served model two to six questions
about text it already has. 1 GB and one CPU. It also does nothing until
`ASSESSMENT_ENABLED` is true, so a deployment that never turns the
evaluation phase on pays for one container polling an empty queue.

## What the model costs

Per-call latency and per-stage spend for the last run are in
[measurements.md](measurements.md). A passage whose sentences carry no finite
verb is skipped before the call rather than sent.

Live, that is the **2 · What each stage is doing** dashboard and Phoenix. Over a
finished run, off a captured log:

```bash
make spend LOG=run.log
make spend LOG=run.log SINCE=2026-09-19
```

`LOG` is required and names the text log a terminal saw, not the shipped
JSON.

## Replaying a call in the Phoenix playground

Open any `completion` span in Phoenix and replay it against a model you pick
— the prompt as it was sent.

Against Ollama only: every other provider Phoenix offers wants an API key.
Wired by two lines on the `phoenix` service — `OLLAMA_BASE_URL` set to
`OLLAMA_CONTAINER_URL`, and an `extra_hosts` entry so
`host.docker.internal` resolves. With `OLLAMA_CONTAINER_URL` unset, Phoenix
falls back to `localhost:11434`, which inside that container is Phoenix.

A prompt is selectable there rather than pasted in: a stage publishes what
it records when it starts, and `make prompts-publish` republishes the lot.

## Dashboards

Four, provisioned from `configs/grafana/` over three datasources.

Numbered in reading order, and each opens with what it answers and which
tool to use for the rest.

| Dashboard | Reads | Shows |
|---|---|---|
| 1 · Where the corpus is now | PostgreSQL | Queue depth per stage, failures with reasons, fact and question acceptance, topic coverage |
| 2 · What each stage is doing | Elasticsearch | Units finished per interval, model latency at p50/p95/p99, facts and questions accepted against refused |
| 3 · One run, end to end | all three | One run on one page: what it produced, what it cost, its Phoenix projects, the gate verdicts, every line it wrote |
| 4 · Every line every process wrote | Elasticsearch | Lines per level, what failed and where |

Logs say what happened once; the tables say what is true now. A row a worker
died holding logged nothing and is still counted in **1 · Where the corpus
is now**.

**3 · One run, end to end** crosses that split, which is why there is a
third datasource: a run is `questions.run_id` on one side and a Phoenix
project named `<position>-<stage>-<RUN_ID>` on the other. Only a run named
with `RUN_ID` gets a project of its own; an unnamed run's spans sit in its
stage's shared project, and the Phoenix panels show nothing for it. The
`Phoenix` datasource is the same PostgreSQL server, a different database,
read by the same `grafana_reader`.

Grafana holds state and logs and nothing else. For how one artefact was
produced, open it on its own page in the application and read the **How
this was produced** fold; for the calls behind a step, Phoenix; for which
run produced it, Dagster.

The panel worth watching during a long run is **model latency p99**. A call
that runs past `LLM_TIMEOUT_SECONDS` is tried again, up to
`LLM_MAX_ATTEMPTS` times, and then fails its row, so a p99 climbing towards
the timeout is a stage about to fail rows.

`grafana_reader` holds `SELECT` and nothing else. It is created by
`configs/postgres/init.sh`, which only runs on the first boot of an empty
volume. On a stack that already has one:

```bash
export COMPOSE_ENV_FILES=configs/env/deployment.env,.env
podman compose exec postgres bash /docker-entrypoint-initdb.d/init.sh
```

Its `SELECT` on the five Phoenix tables the run dashboard queries is granted
by `make up`, once Phoenix has made them. `make grafana-grants` grants them
on its own, for a stack started some other way.

### Rotating `GRAFANA_SECRET_KEY`

Grafana encrypts the secrets it stores in its database with
`GRAFANA_SECRET_KEY`, so a new key has to reach them in order:

1. Snapshot the `grafana_data` volume.
2. With Grafana still running under the old key, rotate its data keys:
   `POST /api/admin/encryption/rotate-data-keys` as `GRAFANA_ADMIN_USER`.
   It answers 204.
3. Remove the signing keys Grafana stored encrypted under the old key, so
   it mints its own. Left in place, `/api/signing-keys/keys` answers 500.
   The repository has no command for this step.
4. Put the new `GRAFANA_SECRET_KEY` in `.env` and recreate the `grafana`
   container, which `make up` does once the value has changed. compose
   hands it over as `GF_SECURITY_SECRET_KEY` and refuses to start Grafana
   without it.
5. Check that the three provisioned datasources report healthy, and that
   alerting, the dashboards and search load.

## Logs

```bash
make logs                # everything, from the container engine
make logs-api
make logs-shipper        # why nothing is arriving
make logs-retention      # how long Elasticsearch keeps them. Run once
make logs-prune          # delete the files on the volume
make logs-wipe           # every line and every file. What make wipe runs
```

Only this project's processes are shipped to Elasticsearch, but all of them
wherever they ran: a container writes to the `logs` volume and a host command
to `./logs`, and filebeat reads both into one data stream. `host.name`
separates them.

The other containers — Postgres, SeaweedFS, Redis, Elasticsearch, Phoenix,
Argilla, Grafana, Adminer and Filebeat — keep the `json-file` driver and are
read with `make logs`.

Retention has two halves. `make logs-retention` ages what Elasticsearch
holds; `make logs-prune` ages the files. Until the first has run, nothing is
deleted. Each process writes `{service}-{host}-{pid}.log`, so nothing else
removes one.

See [`telemetry/`](../telemetry/README.md) for the field names.

## Failure

A row a worker died holding is failed by the next run of that stage with the
reason recorded, and `retry` returns it to the queue. There is no state a row
can reach that nothing can move it out of.

A stage's failure is never an HTTP 500 — it is recorded against the row and
read back through `/{stage}/status`.

## Things that go wrong

| Symptom | Usually |
|---|---|
| Topics sit `pending`, nothing in the logs | `question-worker` is downloading 2.2 GB of embedding weights |
| `make assess` prints one line and stops | `ASSESSMENT_ENABLED` is not true in `.env` |
| `make assess` refuses before it claims anything | `ASSESSMENT_JUDGE_MODEL` names a model that is not served |
| A queue fills and nothing drains it | That stage has no container. `make up` |
| Grafana panels are empty | The shipper. `make logs-shipper` |
| A panel that groups by `stage` finds nothing | A field missing from `append_fields` in `filebeat.yml` |
| An edit to `filebeat.yml` changed nothing | `setup.template.overwrite` is false |
| Grafana cannot read the database | `init.sh` has not run on this volume |
| The run dashboard's Phoenix panels cannot read their tables | The grants `make up` makes have not run. `make grafana-grants` |
| Streamlit refuses a file the API would accept | `server.maxUploadSize` is below `MAX_FILE_SIZE_MB` |
| The frontend will not start, naming a variable | It is declared but not in the `streamlit` service's `environment` |
| Argilla refuses the key | `ARGILLA_API_KEY` is under "My settings". It is not `ARGILLA_PASSWORD` |
| A p99 climbing towards `LLM_TIMEOUT_SECONDS` | Calls about to time out, be tried again and fail their rows. Raise the timeout |
| A scanned PDF is refused rather than parsed | OCR is not enabled |

## Deleting things

```bash
make delete SHA=<sha256>          # a document and everything from it
make delete-derived SHA=<sha256>  # only its passages and facts
make wipe                         # every document, then the topics
make topics-delete                # every topic, membership, model and figure
```

Each is the first of two deletions. An AFTER DELETE trigger copies the row
into `archived_rows`, and the removal paths move objects into the `archive`
bucket:

```bash
make archive                      # what is held, by table, with its age
make restore-documents SINCE=<time>  # put back what was archived from then on
make archive-purge DAYS=30        # the second deletion. This one is final
```

Nothing purges itself, so the archive grows on ordinary runs too — a
re-extraction and a re-chunk delete what they replace. See
[`backend/archive/`](../backend/archive/README.md).

These two archive nothing, because `TRUNCATE` and a dropped volume fire no
row trigger:

```bash
make down-volumes                 # the containers' data, all of it
make schema-reset                 # every table, rebuilt from the revisions
```

Deleting a document takes everything derived from it. What it does **not**
take is `topics`: a fit is over the corpus rather than over a file, so
`make wipe` is one command that runs both.
