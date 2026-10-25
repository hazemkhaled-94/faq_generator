# Operations

Running the stack, watching it, and what goes wrong.

## The services

Once `make dev` reports ready, at the default ports
`configs/env/deployment.env` sets ([a second stack](#a-second-stack-beside-the-first)
moves them):

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
Dagster daemon and the six stage workers — twenty-three containers in all.

Every published port binds to 127.0.0.1, so each URL above answers on this
machine only. PostgreSQL and SeaweedFS's S3 gateway publish a port for the
host commands; SeaweedFS's master, filer and volume servers publish none.
The api answers only the host names in `API_ALLOWED_HOSTS`, and refuses with
403 any request a browser sends from another site, and a write from another origin.

Every write to the api, and every read of `/settings`, must also carry the
shared secret `API_TOKEN` as the `X-API-Token` header, and is refused with 401
`unauthorized` without it. `make setup` generates it into `.env`; the
frontend, the orchestrator and the make targets send it, and an api started
with none refuses every write. It is not a login: the secret is shared, so
the api's binding to `127.0.0.1` is a requirement of the deployment, not a
default to relax. An existing `.env` needs the line added (run `make setup`
again, which fills only the placeholders), and the stack recreated. With it,
`EMBEDDING_MODEL`, `NLI_MODEL`, `QA_MODEL` and `DOCLING_ARTIFACTS_PATH` are
fixed: a value stored for one of them through the UI, the API or
`make settings-set` stops applying, and the environment files' value is read.
Set them in `configs/env/backend.env` before upgrading if a stored one was meant.

`make services` and the System health page both ask `GET /services`, which
probes the catalogue in
[`backend/api/services.py`](../backend/api/services.py) live. Use that for
what is actually up.

Credentials are `PHOENIX_DEFAULT_ADMIN_INITIAL_PASSWORD` for Phoenix (sign in
as `admin@localhost`), `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`, and
`ARGILLA_USERNAME` / `ARGILLA_PASSWORD`.

## Memory

The memory limits in [`compose.yaml`](../compose.yaml) add up to about
33 GiB at the shipped sizes: PostgreSQL may take 4 ([sized below](#sizing-postgres)),
the question worker 6, the parse and extract workers 4
each, the chunk and topic workers 3 each, Elasticsearch 2, and every other
service 1 or less. They are ceilings rather than reservations, and a
container that reaches its own is killed.

On macOS and Windows the containers run inside Podman's virtual machine,
which has a memory size of its own, whatever the host has.
`podman machine inspect` shows it (`Resources.Memory`, in MiB), and the
machine has to be stopped to change it:

```bash
podman machine stop
podman machine set --memory 16384
podman machine start
```

A machine smaller than the workers you run at once is what the smaller
stack below is for: its services with the parse or the chunk worker have run
in a machine of 8 GiB. The question worker's limit alone is 6 GiB.

### Sizing Postgres

One server holds five databases and three vector indexes (passages, facts and
questions, 1024 dimensions each). Its size follows the corpus, and
[`configs/env/deployment.env`](../configs/env/deployment.env) holds the values:
`POSTGRES_CPUS` and `POSTGRES_MEMORY` are the container's limits,
`POSTGRES_SHM_SIZE` its `/dev/shm`, and `POSTGRES_SHARED_BUFFERS`,
`POSTGRES_MAINTENANCE_WORK_MEM`, `POSTGRES_EFFECTIVE_CACHE_SIZE` and
`POSTGRES_MAX_CONNECTIONS` reach the server as `-c` options.

A vector is 4 KB, and an HNSW index over it is about the same size again. The
facts are the largest of the three: 137,000 vectors are about 0.55 GB of
vectors and 1.1 GB with the index, and the passages and the questions add a
fifth. The working set is that, and the memory is three times it, so the index
stays cached while a second one is built. The defaults are the go-live corpus
(about 300 documents, 20,000 passages, 137,000 fact vectors), ten times the
build the review measured.

| Corpus | Passages | Fact vectors | `POSTGRES_CPUS` | `POSTGRES_MEMORY` | `POSTGRES_SHM_SIZE` | `POSTGRES_SHARED_BUFFERS` | `POSTGRES_MAINTENANCE_WORK_MEM` | `POSTGRES_EFFECTIVE_CACHE_SIZE` |
|---|---|---|---|---|---|---|---|---|
| The reviewed build | 2,000 | 14,000 | 1.0 | 1G | 256m | 256MB | 256MB | 640MB |
| Five times | 10,000 | 70,000 | 2.0 | 2G | 512m | 512MB | 512MB | 1280MB |
| **Go-live (shipped)** | 20,000 | 137,000 | 4.0 | 4G | 1g | 1GB | 1GB | 2560MB |
| Twenty times | 40,000 | 274,000 | 4.0 | 8G | 2g | 2GB | 2GB | 5GB |

- **`POSTGRES_SHM_SIZE`** at least `POSTGRES_MAINTENANCE_WORK_MEM`. A parallel
  index build takes its memory from `/dev/shm`, which a container gets 64 MB of
  by default. A restore of the review's dump failed there with `could not
  resize shared memory segment` while an HNSW index was built in parallel.
- **`POSTGRES_MAINTENANCE_WORK_MEM`** is what one index build holds before it
  spills to disk, where pgvector warns that the graph no longer fits. The
  biggest index is the facts', so it is the size of that index.
- **`POSTGRES_MAX_CONNECTIONS`** does not follow the corpus, it follows the
  processes. The api and the six workers each hold `DATABASE_POOL_SIZE` plus
  `DATABASE_POOL_OVERFLOW` connections (70), the object store's filer holds up
  to `WEED_POSTGRES_CONNECTION_MAX_OPEN` (50), and Phoenix, Dagster, Argilla,
  Grafana, Adminer and a person with `psql` need the rest of the 250. A worker
  scaled to more replicas, or a larger pool, adds its own share: keep the
  total under 80% of this. `tests/static/test_env_files.py` refuses a pool
  that no longer fits.
- A changed value needs `podman compose up -d postgres`, which recreates the
  container on its volume, and no migration.

### A smaller stack

`make dev` starts every service. A run needs fewer: the database, the object
store, the api and the stage workers it uses. Logs and dashboards
(Elasticsearch, Filebeat, Grafana), review (Argilla and Redis), Adminer and
Dagster are for watching and driving a run, and the `-start` targets and the
host drains need none of them.

```bash
make certs logs-dir
export COMPOSE_ENV_FILES=configs/env/deployment.env,.env
podman compose up -d api phoenix seaweedfs-volume seaweedfs-volume2
make schema
```

`up` starts what these depend on as well: PostgreSQL and the SeaweedFS
master, filer and S3 gateway. The two volume servers are named because no
service depends on them, and the object store cannot write without them.
Phoenix is where the host commands send their traces. Add `streamlit` for the
pages.

Then bring up one stage worker at a time, queue its stage, and stop it once
its queue is drained:

```bash
podman compose up -d parse-worker
make parse-start                 # make parse-status says when it is done
podman compose stop parse-worker
```

`make pipeline` and `make all` need Dagster, so a run on this stack is driven
with the `-start` targets, or with the host drains while a stage's worker is
stopped.

## A second stack beside the first

Two checkouts on one machine each run a stack of their own once the second
has its own project name and its own published ports. Compose names every
container, volume, network and built image for the project, which is
`qa_generator` unless something sets another, so a second project has its own
database, object store and images. The database names in
`configs/env/deployment.env` can stay as they are.

Set the name and the ten ports in the second checkout's `.env`. Compose and
the Makefile read it after `configs/env/deployment.env`, so a value there
wins, and `make doctor` lists each name it moves:

```ini
COMPOSE_PROJECT_NAME=qa_second
POSTGRES_PORT=25432
S3_PORT=28333
PHOENIX_PORT=26006
PHOENIX_GRPC_PORT=24317
BACKEND_PORT=28000
STREAMLIT_PORT=28501
DAGSTER_WEBSERVER_PORT=23000
GRAFANA_PORT=23001
ARGILLA_PORT=26900
ADMINER_PORT=29001
```

Every address a host command or a page uses is derived from these ports, so
nothing else moves: the URLs in the table above answer on the new ports, and
`make services` lists them. The smoke layer reads its image tags' project
name and the Dagster port from the shell rather than from `.env`, so give
`make test-smoke` both:

```bash
COMPOSE_PROJECT_NAME=qa_second DAGSTER_WEBSERVER_PORT=23000 make test-smoke
```

## Scaling

`parse-worker` and `chunk-worker` scale horizontally — each claims one row at
a time with `FOR UPDATE SKIP LOCKED`. `extract-worker` does too, **to two
replicas at most**, or one drain on the host beside one. Extract workers
running side by side judge a passage's facts again inside the store, under a
lock per language and kind, so two passages read at once do not both keep one
restated claim; see the `duplicate` refusal in
[the extraction README](../backend/extraction/README.md). Two drains were
measured on copies of the reviewed build and of the shop calibration corpus:
over the same 257 passages two drains took 0.57 of one drain's time, and over
168 shop passages 0.54, and neither kept a claim twice. More than two are not
measured, so a deployment runs no more ([Go-live deployment](#go-live-deployment)).
Keep the drains within the database's connections
([Sizing Postgres](#sizing-postgres)) and the provider's rate limit.

```bash
export COMPOSE_ENV_FILES=configs/env/deployment.env,.env
podman compose up -d --scale extract-worker=2
```

**How many drains one database takes is bounded by the provider's quota, not
by the database.** On the Azure quota this build ran on, two drains of the
model stages ran side by side without a failed row, and six lost 3 of 10 topics
to rate limits. A drain waits out a rate limit (`Retry-After`, two minutes at
most, ten minutes in all per call) without using up `LLM_MAX_ATTEMPTS`, and
five rows in a row that the model could not be reached for stop it with exit
75 and the rows back in the queue, so too many drains cost time and not rows.
Run at most two model drains against one database on that quota, and measure
before raising it.

`question-worker` scales the same way but has less to divide: its queue is
one row per topic. `topic-worker` can be scaled and there is no point — a fit
is one request row.

`question-worker` loads `EMBEDDING_MODEL`, 2.2 GB, before it claims anything,
and downloads it into the `models` volume if extract-worker has not. The
topics sit `pending` until it finishes and `make logs` says so. The container is given 6 GB for it and
`NLI_MODEL`'s weights, and the weights are per container, not per lane.

`assess-worker` is the cheapest of the six to scale and, with `topic-worker`,
which fits its NMF from scratch, one of two that load **no** pretrained
weights: it asks a served model two to six questions about text it already
has. 1 GB and one CPU. It also does nothing until
`ASSESSMENT_ENABLED` is true, so a deployment that never turns the
evaluation phase on pays for one idle container. It reads the flag every
`WORKER_POLL_SECONDS`, so switching it on from the Assessment page needs no
restart; a change to `.env` reaches it with `make up`.

## Sizing a corpus

`make estimate` prints, for the rows still to do, the time, the model calls and
the spend of each stage, before anything is queued. It multiplies them by what
one row of the stage took in the reviewed build: 30 documents, 1,973 passages
and 41 topics, Azure models, 5 h 41 min and USD 75.53 end to end. Those rates
are the table below. A corpus on another provider, or with another model split,
has other rates, and `make spend LOG=run.log` reads yours off a run.

| Stage | Row | Seconds of one drain | USD | Calls | Divided by drains |
|---|---|---|---|---|---|
| parse | document | 6.6 | 0 | 0 | yes |
| chunk | document | 2.6 | 0 | 0 | yes |
| extract | passage | 3.69 | 0.00664 | 1.29 | yes |
| topics | passage | 0.033 | 0.00002 | 0.001 | no |
| bridges | topic | 17.6 | 0.0522 | 12 | no |
| questions | topic | 489 | 1.35 | 320 | yes |
| release | accepted question | 0.323 | 0.000676 | 0.54 | no |
| assess | sample of 441 | 1392 | 3.59 | 1862 | no |

How a row count follows from the corpus: a document is 66 passages, a passage
carrying a validated fact belongs to a topic at 40 passages a topic
(`TOPIC_PASSAGES_PER_TOPIC`), up to the ceiling `TOPIC_NUM_TOPICS` a language,
and a topic leaves 53 accepted questions. A run writes `QUESTIONS_PER_TOPIC`
slots for each topic, so the questions grow with the topics and the topics with
the passages: slots are topics times `QUESTIONS_PER_TOPIC`. A stage whose
workers scale (`DRAINS=questions=2`) divides its time by the drains and keeps
its spend. Two is the most drains one database takes on the current Azure
quota; more need a larger quota, measured first (see below).

**The go-live corpus, ten times the reviewed one**: 300 PDFs, 20,000 passages,
410 topics, 21,750 accepted questions. One drain of each stage takes 81 hours
and costs USD 725:

| Stage | Rows | Time, one drain | Time, extract and questions at 2 drains | USD |
|---|---|---|---|---|
| parse and chunk | 300 documents | 46 min | 23 min at 2 | 0 |
| extract | 19,730 passages | 20.2 h | 10.1 h | 131 |
| topics | 19,730 passages | 11 min | 11 min | 0.39 |
| bridges | 410 topics | 2.0 h | 2.0 h | 21 |
| questions | 410 topics | 55.7 h | 27.9 h | 554 |
| release | 21,750 accepted | 1.9 h | 1.9 h | 15 |
| assess | a fixed sample | 23 min | 23 min | 3.59 |
| **total** | | **81 h** | **43 h** | **725** |

Two things in it are new since the review. The questions are 410 topics because
`TOPIC_NUM_TOPICS` is 300 a language and no longer 40: the review's go-live
estimate of USD 264 held the questions to the 9,600 slots two languages of 40
topics could write, a fifth of the coverage, and it is USD 725 for the whole.
Spending less is `QUESTIONS_PER_TOPIC`, which scales the questions down and the
coverage with them. And the release draw is no longer the quadratic that took
39 minutes a draw at this size: it steps down from the size the pool can place
and draws with no list rebuilt per question.

The example is worked at two drains because that is what the current Azure
quota carries: two drains of the model stages ran side by side without a
failed row, and six lost 3 of 10 topics to rate limits. A third drain, or a
fourth, shortens the time only on a larger quota, and the quota is to be
measured before the drains are raised, not assumed.

What to size besides time: [Postgres](#sizing-postgres) for the vectors, the
parse worker's memory for the longest document (`PARSING_MAX_PAGES`, 180 pages,
about 3.1 GB of the 4 GB it is given by the measured curve, to be measured
again in the worker's Linux image at the next build), and the topic worker's 3 GB, which holds the
passages by topics matrix of 10,000 by 300 for one language at a time.

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

The cost log is the spend of record. The figure Phoenix shows is indicative:
it prices a call on its own table of models, which may price a new model
differently from the runner's `make spend`. Reconcile the two per model after
setting a price in Phoenix, and trust `make spend` where they differ.

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
by `make up` and `make dev`, once Phoenix has made them. `make grafana-grants`
grants them on its own, for a stack started some other way.

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
make logs-wipe           # every line, emptying every file. What make wipe runs
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

## Backups

The archive (`make archive`) is a second chance after a deletion, and it lives
in the same database and the same object store it protects. A backup is a copy
of both somewhere else.

```bash
make backup DIR=/backups/$(date +%F)
```

writes, under `DIR`: `db/<name>.dump`, a `pg_dump -Fc` of each of four
databases (the application's, SeaweedFS's, Phoenix's and Dagster's), taken
through the postgres container; `s3/<bucket>/<key>`, every object of the
five buckets, read through the stack's S3 endpoint; and `manifest.json`, the
row count of every table of the application database and the key, size and
sha256 of every object and dump. It never copies `.env`, `provider.env` or a
certificate key: keep those where you keep secrets. `DIR` must hold no backup.

Argilla's database is left out. Its users table holds the owner's API key in
clear, so a dump of it is a secret, and a backup folder is copied off the
machine. `make backup DIR=... ARGILLA=1` adds it: store that `DIR` as you
store secrets, and rotate `ARGILLA_API_KEY` if it leaks. Without it, the review
datasets come back from the database with `make review-push-*`, and an answer
not yet pulled with `make review-pull-*` is not in the backup.

Stop the workers first (`podman compose ... stop parse-worker chunk-worker
extract-worker topic-worker question-worker assess-worker`, as step 2 of the
drill below does). `make backup` takes the dumps, then the objects, then the
row counts, and a worker still writing makes them three moments: the backup
then verifies with differences, and a row dumped before an object was deleted
has no object in it. It prints this before it starts and does not refuse,
which would need a force flag for a case the operator can see for themselves.

Copy `DIR` off the machine. A backup on the volume it protects is not one.

### The restore drill

Run it on a scratch stack before you need it, and again after any change to the
stores. It replaces the data of the stack it runs on.

1. Bring up a stack of the same version beside the first (see "A second stack
   beside the first"), or the same one after `make down-volumes CONFIRM=all-volumes`, then `make up`.
2. Stop everything but postgres and seaweedfs, so that no connection holds a
   database: `podman compose --env-file configs/env/deployment.env --env-file .env stop api frontend parse-worker chunk-worker extract-worker topic-worker question-worker assess-worker dagster-webserver dagster-daemon phoenix argilla grafana`
   (`docker compose` for docker; `ps` lists what else runs).
3. `make restore-backup DIR=/backups/<the directory> CONFIRM=<APP_DB_NAME>`.
   It refuses while a worker runs and unless `CONFIRM` names the database. It
   runs `pg_restore --clean --if-exists --single-transaction` as the superuser for the application database only, keeping the owners the dump carries (without them the application role could not read its tables),
   uploads the objects under that database's own prefix, and checks that
   dump, those objects and every row count against the manifest. It exits 1
   and names each difference. The buckets, the SeaweedFS filer, Phoenix,
   Dagster and Argilla are shared by every database on the stack, so it
   leaves them and every other database's objects as they are.

   To put the whole stack back (the five databases and every database's
   objects, Argilla's only if the backup took it), run
   `make restore-backup-stack DIR=... CONFIRM=stack`. It rolls
   every database's objects, the filer's entries, the traces and the Dagster
   runs back to the backup's, so it refuses while more than one application
   database exists on the server, unless `ALL_DATABASES=1`.
4. `make up`, then `make schema-status` (at the newest revision) and
   `make documents` (the documents the backup held). Open a document's page and
   a topic figure: the objects are read from the restored store.

A database upgraded to v0.5.2 holds its objects under bare keys until `make
s3-prefix` copies them under its prefix, and a backup taken then holds them
bare. `make restore-backup` puts back and verifies, besides the keys under the
database's prefix, the bare keys its rows name (its documents and archived
documents, and its `topics/<database>/` keys), so the drill after `make
down-volumes` gets its documents back; the other bare keys belong to the
databases they were written for and come back only with `make
restore-backup-stack`. `make s3-prefix` copies them under the prefix, never
over an object the prefix already holds. Bare objects are never deleted: they
stay after `make delete`, `make archive-purge` and `make wipe-all` until a
person removes them from the buckets, once every database has run `make
s3-prefix`.

### What Phoenix keeps

Every trace holds the prompts a run sent, and every prompt is a passage of a
customer's document. Phoenix keeps them for ever unless told otherwise, so
`make up` and `make dev` set its default trace retention policy to
`PHOENIX_TRACE_RETENTION_DAYS` (30 where unset; it is in
`configs/env/deployment.env`, with its reason). `make phoenix-retention` sets
it again after a change, and it needs the stack up. Phoenix applies the
policy on its own schedule, so spans a day past the limit may still be there
for a while. A failure to set it is printed and the stack still starts: read
it. A policy of zero is refused, because it is Phoenix's own "never delete".

The cost log is the spend of record, not what Phoenix holds, so shortening the
retention loses no figure `make spend` reports.

## Failure

A row a worker died holding is failed by the next run of that stage with the
reason recorded, and `retry` returns it to the queue. There is no state a row
can reach that nothing can move it out of.

A stage's failure is never an HTTP 500 — it is recorded against the row and
read back through `/{stage}/status`.

## Go-live host

Go-live reaches a hosted provider from the host, never from a container. The
model stages (extraction, topics, questions, assessment) run on the host
through `make corpus-hosted`; the containers keep parsing and chunking, which
call no model, and the model workers stay stopped. Development is unchanged:
without `HOST_RUNNER` the containers call Ollama, as the README says.

### The runbook

From a fresh clone, following only this page:

1. Clone outside any synced folder, and keep the secrets where only you can
   read them (see "Keeping the secrets out of the checkout" below).
2. `cp .env.example .env`, then `make setup` to fill the passwords. The file
   ships the go-live split: `HOST_RUNNER=1`, the seven role models and
   `LLM_REASONING_EFFORT=none`, described in
   [configuration](configuration.md#the-go-live-split). Put the provider's
   credentials in `configs/env/provider.env`, which is not in git.
   `APP_DB_PASSWORD` must be letters, digits, `-`, `_` and `.`: the connection
   string is built from it as written, so `@ / : # ? %` in it are refused by
   `make doctor` and by `make corpus-hosted`, naming the setting.
3. `make up`. With `HOST_RUNNER=1` it starts the services no profile names:
   postgres, the object store, the api, the parse and chunk workers, the web
   page and Phoenix. The parse and chunk workers drain their queues here, and
   `make corpus-hosted` waits for each to empty before the model stages. The
   model workers sit under the `local-models` profile
   and Dagster under `orchestrated`, and this `make up` stops none of them:
   one left up from development calls Ollama, so `make doctor` and
   `make corpus-hosted` refuse while any is, naming the `compose stop` that
   stops it. `make all`, `make pipeline` and
   `make auto` refuse, and so do the pipeline's routes, naming the host
   runner. A queue verb for a model stage still queues its rows, and its answer
   names the command that drains them.
4. `make doctor`. It checks the split, asks every model one question, and
   reads the Hugging Face cache the run reads with the Hub switched off,
   naming any encoder, at its pinned commit, or Docling weight that is missing
   or holds no weights; on this profile that fails, as it does with
   `HF_HUB_OFFLINE=1`, and `make corpus-hosted` checks it again before it
   detaches. Fill the host's cache once beforehand, where the Hub is
   reachable: `make docling-weights HOST=1` for Docling and the
   `poetry run hf download` line the doctor prints for a missing encoder, as
   [configuration](configuration.md#pinning-the-encoders) says.
5. Upload the documents on the Upload page, or with
   `curl -H "X-API-Token: $API_TOKEN" -F file=@x.pdf http://localhost:8000/documents`.
6. `make corpus-hosted SPEND_CAP=50`. It returns at once, and the run goes on
   detached: `logs/corpus-hosted.log` holds what it does and
   `logs/corpus-hosted.pid` its process group, database and leader's start time;
   `make corpus-hosted-stop` stops it. It names the database it acts on,
   gives every drain that name and `HF_HUB_OFFLINE=1`, and counts spend
   across the drains in `logs/corpus-spend-<database>.usd` (`SPEND_LEDGER`), one
   ledger a database, so `SPEND_CAP` is the cost of
   the whole run and not of each drain. The file holds the run's total and is
   rewritten after every priced call, so a drain killed outright leaves its
   spend counted. Every drain logs the split it resolved
   before its first row, and a role that resolves to an Ollama model stops
   the run before a model is asked.
7. When it ends, the two workbooks: `make questions-export OUT=release.xlsx
   FILTER="--released"` and `make questions-export OUT=all.xlsx`.

### What a queue verb says on this profile

The Start button and `POST /{stage}/start` still queue rows, `retry`,
`rerun` and `reclaim` return them, and `POST /assessment/enrol` enrols them. For
a model stage (extraction, topics, questions, assessment) the answer is 202 and
its detail names the command that drains them, `make corpus-hosted` or the stage's own target, because no worker
does on this profile. A release that adds a stage ends its upgrade section with
`make up`, so the worker or profile it brings is started.

### A stale image

Each image bakes the hash of the lock it installed (`requirements.lock` for the
backend and the page, `requirements.txt` for Dagster, which installs the
ranges), and every container compares it at its start with the checkout's own,
bind-mounted read-only. After a `git pull` or an edit that changed one,
`make up` starts nothing on the old packages: each affected container logs
`run compose build, then make up`, waits ten minutes and exits, and its restart
policy tries again; `make down` or a stop ends that wait at once. Rebuild with `podman compose --env-file
configs/env/deployment.env --env-file .env build`, then `make up`.

### Keeping the secrets out of the checkout

A checkout inside a synced folder (`~/Library/CloudStorage`, `OneDrive` or
`OneDrive - <organisation>`, `Dropbox` or `Dropbox (<team>)`, `Box Sync`,
iCloud Drive) is copied to a vendor's servers and to every device signed in,
`.env` and `provider.env` with it. Go-live runs from a clone elsewhere:

1. `git clone` into a folder no sync client watches, such as `~/srv/qa_generator`
   or `/srv/qa_generator`. `make doctor` warns when the checkout, or the secrets
   file, sits under one.
2. Move the secrets out of the checkout and name them: put `.env` where only
   you read it, for example `/etc/qa/secrets.env` with mode 600, and run every
   command with `ENV_FILE=/etc/qa/secrets.env`, or export it once. Host commands
   source that file and compose is handed it, so nothing else changes. Give it a
   path without spaces. `configs/env/provider.env` holds credentials too and
   stays out of git; keep it out of any folder you back up.
3. **Rotate every key after the move.** The old `.env` was in a synced folder, so
   its passwords, `PHOENIX_ADMIN_SECRET`, `GRAFANA_SECRET_KEY`, the Argilla key
   and the provider's credentials have been read by the sync service. Set new
   ones (`make setup` fills placeholders; rotate the provider's in its own
   console), and delete the old file and the synced folder's copy of the
   checkout.
4. A backup of a database or an object store holds none of this: leave `.env`,
   `ENV_FILE`, `provider.env` and the certificate keys under `certs/` out of
   it.

Moving a checkout is yours to do; nothing here moves it.

### Upgrading a deployment

`make upgrade` takes the stack to the code in the checkout, in the order that
works: it checks the container engine has the room (`UPGRADE_FREE_GB`, 20 by
default, read in the podman VM where there is one), builds, prunes the images
the build orphaned, stops the workers, runs `make schema` and starts the stack
with `make up`. It stops at the first step that fails, so a build that did not
finish never reaches the migration. Run it after `git pull` and before
`make corpus-hosted`; an upgrade section of this page that says to rebuild and
run `make up` is this.

### Profiles

With no profile named compose starts eleven services: the database, the object
store (master, two volumes, filer, S3 gateway), the api, the parse and chunk
workers, the page and Phoenix. The rest sit under a profile:

| Profile | Services | Started by |
|---|---|---|
| `local-models` | the extract, topic, question and assess workers | development `make up`; never on the go-live profile, where the host runner drains them |
| `orchestrated` | Dagster's webserver and daemon | development `make up`; never on the go-live profile |
| `review` | Argilla, Redis and Elasticsearch | `COMPOSE_PROFILES=review` in `.env` |
| `logs` | Filebeat and Grafana, which need `review` for the Elasticsearch they use | `COMPOSE_PROFILES=review,logs` |
| `tools` | Adminer | `COMPOSE_PROFILES=tools` |

`make up` enables every profile unless `HOST_RUNNER` is set; on the go-live
profile it enables what `COMPOSE_PROFILES` in `.env` names, bar the first two.
Every other `make` target sees all of them, so `make down` stops a service
whichever profile started it. `make wipe` skips the Argilla, Elasticsearch and
Dagster steps of a service that is not running and says so, and still empties
the log files; `make doctor` does not check the containers' model where the
workers are stopped.

### After a stop

A drain that stopped itself, because the model could not be reached or the cap
was reached, exits 75 and gives its rows back; a failed row exits 3. Either
stops the run before the next stage. A run that ends other than finished keeps
its pid file, so `make corpus-hosted` after a stop, a crash or a kill resumes
it: it finds the pid file nobody holds, returns every stage's failed
rows to the queue and runs the chain again on the database it records, and the
spend so far still counts against `SPEND_CAP`. Only a run that finished, or
`make corpus-hosted RESET=1`, makes the next one fresh, with its count started
again. A start that names another database than a stopped run's is refused,
since that run's failed rows and spend are not its own. A second
`make corpus-hosted` while the first
runs is refused: the pid file records the run's process group and when the make
leading it started, and that group, its leader alive with that start time or, the
leader killed, a drain of it left, is a run going on. A group number another
process has taken since (after a reboot or a wrap of the pid count) is not the
run: the stop signals nothing of it, and a start resumes. Each
database has its own ledger, so a run on another database never touches this
one's, and a `make corpus` on the same database refuses beside the hosted run:
while it goes, and, unless it resumes with `RESUME=1`, while a stopped one is
recorded, whose spend a fresh run would start again.

A resume returns every stage's failed rows to the queue first, so a row that
fails every time - a document parsing refuses for its language, an empty or
broken PDF - stops every resume at the same stage with 3. Read why before
starting it again: `logs/corpus-hosted.log` names each failed row and its
error, and the stage's page lists them. Then put the row right or take it out:
`make delete SHA=<sha256>` removes a document that cannot be processed, and
once the cause is fixed the stage's `-retry` target (`make parse-retry
SHA=<sha256>`, `make extract-retry PASSAGE=<id>`) returns that row alone.
`make corpus-hosted RESET=1` starts a fresh run, which retries no failed row
and starts the spend count again.

`make corpus-hosted-stop` stops a hosted run: it sends TERM to that whole
group, so the drain in hand finishes its row, or gives it back, and exits 75,
and kills what is left after 300 seconds, a model stage's grace and its
give-back. The spend ledger and the pid file are kept, so the next
`make corpus-hosted` resumes the run.

To have a supervisor restart it, run `scripts/corpus-hosted.sh`, the runner
`make corpus-hosted` detaches, in the foreground. It takes `make corpus`'s
command line, keeps the same pid file and ledger, and exits with the code of
the stage that ended the run rather than make's 2: 0 when the run finished, 75
when it stopped (at `SPEND_CAP`, on a model that cannot be reached, or on a
signal, which it passes to the whole run), 3 when rows failed or the start was
refused, and anything else for a crash. Only a crash is restarted: a stop at the
cap restarted would pay every model drain's preflight again for nothing, and
failed rows want reading first. The runner resumes a run that did not finish by
itself, so neither unit names `RESUME=1`, and every start proves what
`make corpus-hosted` proves (`make corpus-preflight`: the go-live profile, no
model worker or Dagster container up, the split, the password and the cache),
refusing with 3 where it does not. A database it is not given is resolved as
`make corpus` resolves it, and recorded. Its `PATH` must reach `make`,
`poetry` and the container engine; give `ENV_FILE` where the secrets live
outside the checkout.

```ini
# /etc/systemd/system/qa-corpus.service
[Unit]
Description=qa_generator corpus run
Wants=network-online.target
After=network-online.target

[Service]
User=qa
WorkingDirectory=/srv/qa_generator
Environment=PATH=/home/qa/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/srv/qa_generator/scripts/corpus-hosted.sh APP_DB_NAME=qa_generator SPEND_CAP=50
Restart=on-failure
RestartSec=60
RestartPreventExitStatus=3 75
KillMode=mixed
TimeoutStopSec=330

[Install]
WantedBy=multi-user.target
```

`KillMode=mixed` sends the stop to the runner alone, which passes it to the run
once; `TimeoutStopSec` outlasts its 300 seconds.

```xml
<!-- /Library/LaunchDaemons/qa.corpus.plist: the same on macOS. A daemon, so it
     runs without anybody logged in; launchd restarts on any code but 0, so the
     runner is told to turn a stop into 0. -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>qa.corpus</string>
  <key>UserName</key><string>you</string>
  <key>WorkingDirectory</key><string>/Users/you/srv/qa_generator</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/Users/you/.local/bin:/opt/podman/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/you/srv/qa_generator/scripts/corpus-hosted.sh</string>
    <string>--zero-on-stop</string>
    <string>APP_DB_NAME=qa_generator</string>
    <string>SPEND_CAP=50</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ThrottleInterval</key><integer>60</integer>
  <key>ExitTimeOut</key><integer>330</integer>
</dict>
</plist>
```

A restart by either resumes the run with its ledger, so the cap holds across
restarts. `make corpus-hosted RESET=1`, or a fresh `make corpus` without
`RESUME=1`, starts a run's count again. A unit enabled at boot starts a fresh
run after one that finished, which draws the release again at the verifier's
cost: disable it once the run is done.

## Upgrading the schema on a stack with data

`make schema` applies each revision in a transaction of its own, and a
revision that cannot get its lock within 5 seconds fails with the lock
timeout instead of waiting: a DDL statement queues behind any open transaction
on its table, and every query behind it queues in turn. A statement may run
10 minutes. When one fails, find what holds the table (a drain, a worker, a
long `make` command), stop it and run `make schema` again: the revisions
already applied stay applied. The order:

1. Stop the stage workers and the host drains.
2. Back up with `make backup` (see "Backups").
3. `make schema`.
4. Build the images, then `make up`.

A revision that adds a CHECK adds it `NOT VALID` and validates it in a
revision of its own, and a backfill of many rows runs in batches outside the
DDL transaction; `backend/database/README.md` has the rule.

## Go-live deployment

The final review of v0.5.1 (2026-10-22) set what a deployment running a
customer corpus has to hold, and the conditions under which its open items
stay out of the way. This is that list as it stands in v0.5.2. Each line names
its item by the review's number (`C-` and three digits, as `docs/bugs.md` gives
them) and what lifts it. A condition this release's fixes lift has left the
list and is named, with its fix, under
[Upgrading to v0.5.2](#upgrading-to-v052). The settings named here are in
[configuration](configuration.md#go-live-settings), and
[the runbook](#the-runbook) is how a fresh clone reaches the deployment.

The list covers about ten times the reviewed build: 300 PDFs and 20,000
passages, German and English. The review measured 30 PDFs and 1,973 passages.

### The model split

- **The measured split** (C-051). `.env.example` ships it and
  [configuration](configuration.md#the-go-live-split) gives the table: the
  writer `azure/gpt-5.6-sol` at `LLM_REASONING_EFFORT=none`, extraction and
  phrasing `azure/gpt-5.4`, digests and the judge `azure/gpt-4o`, the verifier
  and topic naming `azure/gpt-4.1`. Every drain logs the split it resolved
  before its first row, and with `HOST_RUNNER=1` a drain and `make doctor`
  refuse a role that resolves to an Ollama model (C-006, C-013).
- **One endpoint** for every role, below (C-366).

### Settings

- **The model stages run on the host** (C-006): `HOST_RUNNER=1`, `make
  corpus-hosted`, and the model workers stopped; a run refuses to start while
  a model worker or a Dagster container is up (`make corpus-preflight`). The orchestrated path is not
  part of this profile (C-073): `make all`, `make pipeline`, `make auto` and the
  pipeline's routes refuse, naming the host runner.
- **The judge and the provider are the host's** (C-006).
  `ASSESSMENT_JUDGE_MODEL` in `.env` and the provider's credentials in
  `configs/env/provider.env` are what the host runner reads, and `make doctor`
  refuses a judge left unset while `ASSESSMENT_ENABLED` is true. The Assessment
  page shows the containers' judge, `ASSESSMENT_JUDGE_CONTAINER_MODEL`, so on
  this profile it says the next run judges nothing: that line is about the
  stopped workers, not the host run.
- **A model cache filled once, and read offline** (C-072, C-117). Fill it where
  the Hub is reachable, as [Pinning the encoders](configuration.md#pinning-the-encoders)
  says; `make corpus-hosted` then runs every drain with `HF_HUB_OFFLINE=1` and
  refuses, before it detaches, a cache missing an encoder at its pinned commit
  or Docling's weights. Point `DOCLING_ARTIFACTS_PATH` at the prefetched parser
  weights where they are not in the cache.
- **A spend cap** (C-091): `make corpus-hosted SPEND_CAP=<USD>`, counted across
  the drains of the run. With it set, a drain refuses a model litellm cannot
  price (C-219).
- **Every published port on 127.0.0.1, and one operator** (C-085, below).
- **Entity and temporal questions stay off** (C-176, C-217). Both carry weight
  0 in `QUESTIONS_TYPE_MIX` and `QUESTIONS_RELEASE_TYPES`: entity with no
  defect measured, temporal because a corpus with no periods answers it with
  comparisons wearing the name. Calibrate each on the go-live corpus before
  giving it a weight; a corpus of releases, versions or reporting periods is
  the one where temporal may earn one.

### Resources

- **Postgres sized as shipped, its probe time watched** (C-011).
  `configs/env/deployment.env` ships the go-live row of
  [Sizing Postgres](#sizing-postgres). Its measure is the 10x load test
  `make test-perf` runs: a dedup probe and a fact write within twice their
  time at the reviewed build's size. On CI's runner, in two runs, the
  single-pass probe p95 went from 4.5 ms to 9.7 ms, 2.15x against the 2x the
  bar allows; the warm probe held at 1.00x and the write at 1.66x. The sizing
  ships with that limit by the user's decision: the database is about 2% of a
  drain's time at ten times the build. Watch the probe time as the corpus
  grows, and raise `POSTGRES_MEMORY` and `POSTGRES_SHARED_BUFFERS` by the
  table's next row if it climbs.
- **The podman VM's memory** at least what the limits of the services it runs
  add up to ([Memory](#memory)): the eleven the go-live profile starts come to
  about 15 GiB at the shipped sizes, PostgreSQL and the parse worker 4 each and
  the chunk worker 3. Every profile added on top adds its own.
- **Free disk before every build**: `make upgrade` refuses below
  `UPGRADE_FREE_GB` (20) in the engine and prunes what a build orphans. The
  margin is the review's, not a measured bound.
- **At most two drains of a model stage a database**, and at most two of
  extraction (C-082, C-026, below).
- **Time and spend**: `make estimate` says both for the rows still to do
  (C-084). [Sizing a corpus](#sizing-a-corpus) works the go-live corpus: 43
  hours and USD 725 at two drains of extraction and questions, the questions
  growing with `TOPIC_NUM_TOPICS`.

### Backups

- **`make backup` before every upgrade and every wipe** (C-003), copied off
  the machine, and [the restore drill](#the-restore-drill) on a scratch stack
  before it is needed. A backup leaves Argilla's database out unless
  `ARGILLA=1`, whose dump holds a key in clear.
- **The archive bucket is the only copy of a deleted row's objects.** Purge it
  per database on a cadence, after a backup ([Deleting things](#deleting-things)).

### Monitoring

- **Alert on a non-zero exit** (C-009, C-091). A drain exits 3 when a row
  failed and 75 when it stopped itself (an outage, `SPEND_CAP`, a model that
  finds nothing, a signal), and `scripts/corpus-hosted.sh` exits with the code
  of the stage that ended the run ([After a stop](#after-a-stop)).
- **The database on every log line** (C-005): each line carries `db`, and
  Phoenix projects, review datasets and Dagster runs carry the database's
  name.
- **A retention for Phoenix's traces** (C-103), which hold every passage a
  prompt sent: `PHOENIX_TRACE_RETENTION_DAYS` in
  `configs/env/deployment.env`, set at `make up`. Read `make up`'s output: a
  failure to set it is printed, and the stack starts anyway.
- **The release draw's time at scale** (C-089): a pool of the reviewed
  build's accepted questions ten times over, 21,750 rows, draws its release in
  10.6 s, where v0.5.1's scan took about 39 minutes.

### Before the first go-live release is used

- **Label a sample of it.** The quality figures so far are measured on
  football regulations and on the shop calibration corpus, and tables, the
  core of bank and shop material, read worst. Label 60 released rows per
  language blind under the rubric, with the table slice and the two-passage
  slice read apart, and use the release only if it meets the review's release
  bar: usable at least 0.723, invalid at most 3.4 per 60. About two hours of
  labelling and no model call.
- **Read the table slice apart** until C-097 and C-282 ship. A table continued
  on the next page joins its table since v0.5.2 (C-121), but a table's wrong
  section path (C-097) and a second tier joined to the row above (C-282) are
  open.

### The conditions that still hold

| Item | Condition | What lifts it |
|---|---|---|
| C-026 | At most two `extract-worker` replicas, or two extraction drains, a database: `--scale extract-worker=2`. The store's duplicate lock was measured with two drains side by side (0.57 and 0.54 of one drain's time, no claim kept twice), and more are not measured | A measurement of three or more drains on a copy |
| C-082 | At most two model drains a database on the current Azure quota: six drains lost 3 of 10 topics to the token rate limit and two lost none. A drain now waits out a rate limit without spending an attempt | A larger quota, measured before the drains are raised |
| C-085 | Every published port stays on 127.0.0.1, and one operator uses the host. `API_TOKEN` guards the API's writes but is shared, and the pages have no login: serving the stack to a team, or binding another interface, makes this a blocker | A login on the pages and the API |
| C-366 | Every role model on one endpoint, `LLM_BASE_URL`; a split across Azure resources needs a gateway in front of them that routes by model id | An address per role (deferred: the measured split fits one resource) |
| C-106 | Ingest only documents the customer authored or controls, no user reviews or third-party submissions: a document's text reaches every prompt as it is, so an instruction planted in it is read as one | Fencing the material in every prompt. It was tried in v0.5.2 and withdrawn: fenced extraction narrowed 10 of 60 facts against 7 unfenced, over the bar of 9 |
| C-054 | After a deletion through the pages or the API, run `make extract-dedup`: every deletion says how many duplicate refusals lost their twin, and on this profile no extraction worker runs to give them back. `make delete` and `make delete-derived` run it themselves | A replay the host runner makes after a deletion |
| C-066 | Export a large corpus with `make questions-export` on the host, never through the pages: the API builds the whole workbook in its 512 MB and fails past about 13,000 questions | The streaming export, deferred to v0.5.3 |
| C-029 | Report the difficulty band as retrieval spread, never as hardness, and leave `QUESTIONS_RELEASE_DIFFICULTY` unset: equal thirds drew nearly every multi-passage question, where the welds sit. The workbook titles the column Retrieval spread since v0.5.2 | A grading of how hard a question is to answer, not built |
| C-031 | Leave distant-from-document out of per-category reports: most of its released rows use the document's words | A per-question reading of how far a row's words are from its evidence, calibrated on two corpora (deferred) |
| C-052 | Before a release from price lists or fee schedules, read by hand its questions whose explanation states a space-grouped amount (`12 500 €`): a wrong total there can still pass the explanation check. Since v0.5.2 the figure reader takes such an amount as one figure with a marked currency, a price dash, a no-break space or any currency sign after it | The explanation half of the fix, which needs the arithmetic check's model call to tell a right total from a wrong one |
| C-056 | Before ingest, count the image-only PDFs: a scanned document is refused, and an image-only page is only warned about | OCR (C-083); the reworded page count of C-127 was withdrawn in v0.5.2 |
| C-083 | OCR stays off. Pillow 13.0.0, which v0.5.2 ships, fixes the advisories that were the other reason | A measured OCR pass on the go-live corpus |
| C-140 | Before go-live, measure the text nested in pictures on the shop calibration database (`qa_cal_shop`): banners and infographics in bank or shop material may carry statements, which reach no passage | A filter that tells a statement from a diagram label. The clause filter tried in v0.5.2 was withdrawn: 5 of 26 changed passages read worse |
| C-266 | Before go-live, measure on the shop calibration database the questions drawn from imprint, hotline and contact passages | A passage gate on contact shapes, with a threshold calibrated on the shop corpus (deferred) |
| C-186 | Before ingest, check the refusal count of a first batch: a PDF whose header follows a few leading bytes, as some document-management exports write them, is refused as unknown type | Reading the signature within the first kilobyte (deferred) |
| C-278 | Before ingest, compare the corpus's widest table rows with the chunk's token budget (`EMBEDDING_MAX_TOKENS` less the embedder's own tokens): a longer row is cut mid-cell and lands in no grid. Ship the fix first if any exceeds it | Keeping a row whole in one passage (deferred) |
| C-419 | Check any tracked-change export in the corpus before ingest: only a drawn horizontal strike is read as struck-through | A strike reading for tracked changes, with a fixture first (deferred) |
| C-245 | Leave `EXTRACTION_DUPLICATE_COSINE` at its shipped value: 0 also stops writing passage embeddings | Building the embedder whatever the threshold (deferred) |
| C-424 | Leave `QA_MODEL` empty, as it ships, until an encoder is calibrated: the first candidate the settings file names cannot load under transformers 5 | A calibration of one encoder |
| C-297 | Build the go-live images once, record their digests, and rebuild only on purpose: the Dagster image installs ranges, installs are not hash-checked and base images are named by tag. A container already refuses to start on a lock its image was not built from (C-010) | Locked and hash-checked installs, images by digest (deferred) |
| C-162 | No schema downgrade past v0.4.2: rolling back `733a3eadef7c` archives every rubric score, and a restore of that deletion fails | Skipping the archive in that downgrade (deferred) |
| C-200 | Leave the nightly schedule off: it ignores Stop and `INGESTION_OPEN`. The go-live profile runs no Dagster at all | A schedule that skips after a cancelled run (deferred) |

## Upgrading to v0.5.2

v0.5.2 is the fix release after the final review of v0.5.1: data safety, the hosted model path, drains that stop and say why, scale, and the parse, fact and question fixes that passed their bars. `docs/bugs.md` lists each fix with its measure, what was withdrawn and the known limits. A build made from scratch on a new database needs only steps 1 and 2 and none of the reruns.

### 1. Before the pull, then the code, the host environment and images

Before `git pull`, pull the verdicts of the review datasets (`make review-pull-facts`, `make review-pull-topics`, `make review-pull-questions`): their names gain the database in this release (step 6). If `configs/env/backend.env` holds edits of your own, set them aside first, since this release removes its role models and renames `TOPIC_MIN_WEIGHT` and the pull stops there: the role models go into `.env`, `TOPIC_MIN_WEIGHT` goes (step 3), and `SPEND_CAP` is given on the command line rather than in the file.

```bash
git pull
make setup        # once .env holds the new lines below
podman compose --env-file configs/env/deployment.env --env-file .env stop parse-worker chunk-worker extract-worker topic-worker question-worker assess-worker
make backup DIR=/backups/$(date +%F)
poetry install --with llm,nlp,data,storage,api,pipeline,viz,observability,dev
make upgrade
```

`.env` gains lines, and compose refuses to start without them: add those `.env.example` now carries that yours lacks, `HOST_RUNNER`, the seven role models with `LLM_REASONING_EFFORT`, and `API_TOKEN=change_me_api_token`, and `make setup` fills the placeholders and nothing else. `make backup` is new in this release ([Backups](#backups)); copy its `DIR` off the machine. On the go-live profile, fill the host's model cache once where the Hub is reachable: `make docling-weights HOST=1` for Docling's weights, and each encoder at its pinned commit, which `make doctor` names with the command that fetches it. `make upgrade` checks the engine has `UPGRADE_FREE_GB` (20) free, builds, prunes the images the build orphaned, stops the workers, runs `make schema` and `make up`, stopping at the first step that fails ([Upgrading a deployment](#upgrading-a-deployment)).

- **Docling** goes from 2.141.0 to 2.142.1, docling-core to 2.104.0, docling-parse to 7.23.0 and doclang to 0.8.0, on the host and in the API image. It needs no re-parse: on the 30 football and 50 shop PDFs it changed nothing but the parentheses of 9 shop passages' link URLs, which it now percent-encodes.
- **Pillow** goes from 12.3.0 to 13.0.0, which fixes the advisories accepted against 12.3.0. What `make audit` still accepts is in `configs/audit-accepted.txt`: filelock 3.32.7's three advisories, until **2026-11-30**, as litellm 1.106.2 requires filelock below 4.0 and the fix is 4.2.1. On that date the audit fails until the entry is read again.
- **A container refuses a stale image.** Each image bakes the hash of the lock it installed, and a container whose checkout's lock differs waits ten minutes and exits ([A stale image](#a-stale-image)): after a pull that moved a lock, build before `make up`, as `make upgrade` does.

Keep the secrets out of a synced folder from now on: `make doctor` warns when the checkout or `ENV_FILE` sits in one, and [Keeping the secrets out of the checkout](#keeping-the-secrets-out-of-the-checkout) says how to move them and why to rotate every key after.

### 2. Three migrations, in order

`make upgrade` runs `make schema`; `make schema-status` shows what it will do. Each revision now runs in a transaction of its own under a 5-second lock timeout, so one that waits on a table a drain holds fails instead of queueing every worker behind it: stop what holds the table and run `make schema` again. On top of v0.5.1's head `20e31b1656f7`, in this order:

| Revision | What it does |
|---|---|
| `860d56b11032` | Adds `facts.language`, filled from each fact's first citation, then analyses `facts` so the first dedup probe plans with the new column and uses the vector index (C-090) |
| `7a41c9d2e8b0` | Adds `facts.twin_id`, a foreign key set NULL when the twin goes, and its index. NULL on every stored refusal, so the first dedup replay after the upgrade reads each duplicate refusal once (C-068) |
| `4a7c2e91d3b8` | Adds `questions.source_digests` and two BEFORE DELETE triggers on `passages` and `facts` that stamp it, and turns the trigger that deleted a question whose last fact went into one that rejects it as `source_changed` and keeps it (C-001) |

Each comes off again with `make schema-down CONFIRM=<database>`, which drops what it added.

### 3. Settings whose meaning or home moved

- **`TOPIC_MIN_WEIGHT` is retired for `TOPIC_RELATIVE_WEIGHT`** (0.5): a membership is kept when it is at least that share of the passage's strongest, where the absolute floor it replaces kept weak memberships that bound unrelated passages, 3.7 topics a passage on the reviewed build. A value left in an environment file is no longer read. A row stored under the old name stops the topic stage's build and `make doctor`, naming the new one and the `DELETE` that removes the row: an absolute weight read as a share would be a floor of nearly nothing. Refit afterwards (step 5).
- **`TOPIC_NUM_TOPICS`** ships at 300 a language, where it was 40, and topics are named 25 to a call. A corpus past 40 topics a language fits more of them, and the questions, written per topic, grow with them: `make estimate` says by how much.
- **`PARSING_MAX_PAGES`** is new (180; 0 is no limit): a longer document is refused before conversion, naming its pages, where the parse worker ran out of its 4 GB and was killed holding its claim. `make parse-retry` returns it after a split.
- **`SPEND_CAP`** is new and the deployment's: a cap in USD, given on a drain's command line, `make corpus-hosted SPEND_CAP=` among them, that stops a drain, the bridge pass, the release draw and the rejudge with exit 75 before the next row past it. Under `make corpus-hosted` it counts the whole run, through a spend ledger kept for each database (`SPEND_LEDGER`). With it set, a drain refuses a model litellm cannot price.
- **`EMBEDDING_MODEL`, `NLI_MODEL` and `QA_MODEL` are fixed**, with their commits beside them in `backend.env` (`EMBEDDING_MODEL_REVISION`, `NLI_MODEL_REVISION`, `QA_MODEL_REVISION`, the build cache's commits): a model id and its commit change together, in the file. A row stored for one of the three ids stops every stage's build, naming its pin and the `DELETE` that removes it. `DOCLING_ARTIFACTS_PATH` is fixed as well, so a stored override of any of the four stops applying.
- **`API_TOKEN`** is new, in `.env`: every write to the API, and every read of its settings, carries it as `X-API-Token`. The pages, a Redo's confirmation and force included, the orchestrator and the make targets send it; a client of your own must too, and is refused with 401 without it.
- **`HOST_RUNNER`** is new, in `.env`: `1` is the go-live profile, the model stages run on the host through `make corpus-hosted` and the model workers and Dagster stay stopped, and a run refuses to start while one of them is up ([Go-live host](#go-live-host)). Unset, development runs as before.
- **`ENV_FILE`** is new: the secrets file every host command reads and compose is handed, `.env` unless it names another.
- **The role models** are `.env`'s alone: `backend.env` names none, and `.env.example` ships the go-live split. A role you leave unset follows `LLM_MODEL`.
- **`LITELLM_LOCAL_MODEL_COST_MAP=true`** is committed in `backend.env`, so prices and which models are sent no reasoning effort follow the installed litellm and move only with its lock.
- **`POSTGRES_*`** are new in `deployment.env` and size the server for the go-live corpus: 4 CPUs and 4 GB where it had 1 and 512 MB ([Sizing Postgres](#sizing-postgres)). The VM needs the room: the memory limits add up to about 33 GiB with every profile on.
- **`PHOENIX_TRACE_RETENTION_DAYS`** is new in `deployment.env` (30): `make up` sets Phoenix's default trace retention to it.

### 4. Prompts and model calls

- **Prompt versions.** The writer moves from 29 to 32: 32 tells every writer the reader never sees the passage, and an answerable writer to put the case that makes its key the only answer into the question (30 and 31 were never released). The verifier moves from 12 to 15, for the settles reading of a why-question over a bare rule. Phrasing moves from 4 to 5, for the self-contained judge's definite sets. Every other prompt keeps its released version: atomic extraction 12, repair-1, the digest 5, the bridge prompt 6, `verifier: stated` 1, the assessment template 4 and topic naming 3.
- **What that marks stale.** Stored rows keep the version they were written under, and only `make questions-rejudge` reads one: its first run after the upgrade asks again about every stored accepted unanswerable question, one `settles` reading each and a second where the cited passages are silent and the probe is on. No fact, bridge, digest, topic or judgement is stale by its prompt.
- **Calls added.** A derived question citing two passages gets the parts reading, one verifier call. Topics are named 25 to a call, so a language of more than 25 topics makes more naming calls, each smaller. The digest pass of step 5 is one digest call a passage, and only when run.

### 5. Reruns, in order

None of these is needed to start v0.5.2. Each brings stored data up to what v0.5.2 reads differently; run only the steps your corpus needs. A rerun without `SHA` refuses unless `CONFIRM` names the database, and a re-chunk or re-extraction over questions refuses, naming how many released, accepted and reviewed questions rest on what it would replace, unless `FORCE=1`: those are rejected as `source_changed` and kept, never deleted.

| Step | Command | Needed because of |
|---|---|---|
| Parse | `make parse-rerun CONFIRM=<database>` | The parse fixes: a document in a language no configured model names is refused, naming it (C-008); titles (C-096); hidden text dropped (C-107); low-confidence pages and interleaved columns named (C-109, C-426). Docling 2.142.1 alone needs none |
| Chunk | `make chunk-rerun CONFIRM=<database> FORCE=1` | The passage fixes: clauses a bookmark pass made headings (C-007), tables continued on the next page (C-121), running items, change boxes and letterheads (C-187, C-230, C-368). On the reviewed build it changes 108 passages of 9 documents and keeps every other with its facts and questions; on the shop corpus it changes none |
| Extract the new passages | `make extract-start`, then `make extract` | The passages the re-chunk made have no facts yet; only those reach the model |
| Judge facts again | `make extract-revalidate` | The fact checks (C-019, C-020, C-021, C-033, C-129, C-137, C-416). No model call. On a copy of the build the first run moved validated atomic facts from 10,468 to 10,761, bridges 189 to 203, outlines 559 to 593 and summaries 616 to 619, and writes only the facts whose verdict changed; a second run writes nothing |
| Digest | `make extract-digests` | v0.5.1's digest floor of 500 characters and the floor's count of list items (C-057, C-098): passages above it that hold no digest get one. On a copy of the build at 500 characters, before the list items were counted, it digested 255 passages for USD 1.04 and left every atomic fact and question as it was |
| Refit topics | `make topics-discover` | `TOPIC_RELATIVE_WEIGHT` (C-095): questions are dealt from memberships, which the old floor kept. A new topic that is an old generated one and gained no passage stays generated; the others are asked about by the next `make questions` |
| Questions already stored | `make questions-reverify` | Holds every stored question to its facts after the steps above, and rejects one whose facts went or no longer hold. It never gives a rejected one back, so the gates this release loosens (C-144, C-188) keep only what is written from now on; `make questions-rerun` writes every topic again, at the writer's cost |
| Ask unanswerables again | `make questions-rejudge` | Verifier 15 (C-022), as step 4 says |
| Redraw the release | `make questions-balance` | The rows rejected above leave it. The draw is the same on the reviewed build, now in seconds at ten times its size (C-089) |
| Export again | `make questions-export` | The workbook titles the band Retrieval spread, gives each row its earlier turns and its source, and its Summary names the judge and counts the documents and passages no accepted question of the export reaches (C-023, C-029, C-102, C-135). A large corpus still exports through this command and never through the pages: the streaming export is deferred to v0.5.3 (C-066) |
| Copy objects under the database's name | `make s3-prefix` | Object keys now carry the database (C-004). A bare key from before is still read, but only a copy under this database's prefix is out of reach of another database's delete or purge. Once per database that used the store |

### 6. What else changes for you

- **Phoenix, Argilla, logs and Dagster carry the database.** Projects are named `<name>__<database>`, every log line carries `db`, the corpus job tags its Dagster runs, and a wipe takes only its own database's. What was filed before belongs to none and is taken only with `ALL_DATABASES=1`.
- **The golden sets** are named `<name>__<database>` too. Upload them again under their database's name with `make eval-upload` and `make eval-phrasing`; the old ones are deleted only with `ALL_DATABASES=1` (`make phoenix-purge ALL_DATABASES=1`, which takes every database's projects with them).
- **The review datasets** carry the database in Argilla, and a dataset pushed under the bare name is left where it is: with its verdicts pulled before the upgrade (step 1), push again (`make review-push-*`).
- **Destructive targets ask for the database.** `schema-down`, `schema-reset`, `wipe`, `delete`, `delete-derived`, `topics-delete`, an unnarrowed `*-rerun` and `archive-purge` with `TABLE`, `ALL` or `DAYS` refuse unless `CONFIRM=<database>` is given on the command line: one exported in the shell does not count. `make down-volumes`, which deletes every database's volumes, wants `CONFIRM=all-volumes`, and `make restore-backup-stack` `CONFIRM=stack`, both on the command line. A restore is `make restore-documents AT=`, which puts back only the deletions it names.
- **A deletion takes the questions on what it removes.** A question on a fact the deletion removes goes, one written from two documents with either; a fact another document also cites stays, with its question. A question a rerun left with no fact is found by the documents stamped on it (`questions.source_digests`). Every deletion ends saying how many duplicate refusals lost their twin, which the extraction worker gives back when its queue is empty, or `make extract-dedup` where none runs.
- **Drains exit with a reason**: 0 done, 3 a row failed, 75 stopped (an outage, `SPEND_CAP`, a model that finds nothing, a signal). `make corpus` stops at the first non-zero exit, waits only for the parse and chunk workers, and refuses beside a model worker or a hosted run of its database. On the go-live profile it runs as `make corpus-hosted`, which a systemd unit or a launchd daemon can supervise; `RESET=1` starts a stopped run afresh, and `RESET=0` or none resumes it ([After a stop](#after-a-stop)).
- **Two extraction drains** may run side by side, and no more ([Scaling](#scaling)).
- **The go-live conditions** that still hold are in [Go-live deployment](#go-live-deployment), and those this release lifts are below.

### 7. Deployment conditions this release lifts

The final review's go-live gate made these conditions of a deployment. Each
one's fix ships in v0.5.2, so it has left [Go-live deployment](#go-live-deployment).

| Item | The condition was | What lifts it |
|---|---|---|
| C-001 | Do not apply v0.5.1's lower digest floor to stored data | A re-chunk or re-extraction keeps the facts and passages that come back identical and rejects the questions on a changed one as `source_changed` instead of deleting them. On a copy of the reviewed build, `make extract-digests` at 500 characters digested 255 passages and left every atomic fact and every question's id and status as they were |
| C-024 | `TOPIC_NUM_TOPICS=40` caps the topics, and with them the questions a run can write | The ceiling ships at 300 a language and topics are named 25 to a call; a synthetic language of 10,000 passages fits 250 topics, every one named |
| C-058 | No refit or topic delete while a question drain runs | A fit request, `DELETE /topics` and `make topics-delete` refuse while a topic holds a live question claim (409 `questions_running`, or exit 1) |
| C-059 | The workbook says that the judge's figures are not a quality estimate | The judged sample is drawn from each stratum in proportion to its size, from the released questions once a release exists, and the Summary says its counts are not a quality estimate |
| C-072 | `HF_HUB_OFFLINE=1` with a filled model cache | `make corpus-hosted` runs with `HF_HUB_OFFLINE=1` and refuses, before it detaches, a cache missing an encoder at its pinned commit or Docling's weights |
| C-075 | Stop the workers and drains before `make schema` | Each migration runs in its own transaction under a 5-second lock timeout and a 10-minute statement timeout, so a busy table fails the migration rather than queueing every worker behind it, and `make upgrade` stops the workers first |
| C-076 | Before ingest, list the page counts and split or try first any document far above 139 pages | `PARSING_MAX_PAGES` (180) refuses a longer document before conversion, naming its pages; `make parse-retry` returns it |
| C-078 | Run `make confidence-recalibrate` only with the question drains stopped | It reads without a lock and writes back in batches of 300, each row guarded by the scores it read; a row changed meanwhile is left for the next run |
| C-079 | No `make up` or reboot during a drain, and the `*-retry` targets after any restart | A worker told to stop finishes its row, or gives it back at a second signal or at its stage's grace, and exits 75; compose waits longer than that grace. `make corpus-hosted` resumes a stopped run and returns its failed rows |
| C-080 | Give the VM at least the compose limits, or stop the unused services | Argilla, Redis, Elasticsearch, Filebeat, Grafana and Adminer sit under profiles, and the go-live `make up` starts eleven services ([Profiles](#profiles)) |
| C-086 | Check free space and prune dangling images before every rebuild | `make upgrade` checks `UPGRADE_FREE_GB` (20) in the engine, builds, and prunes what the build orphaned before it migrates |
| C-088 | `LITELLM_LOCAL_MODEL_COST_MAP=true` in the deployment's environment | Committed in `backend.env` |
| C-102 | Before the first customer workbook, say that a follow-up's earlier turns and a row's location must be looked up | The Questions sheet gives each row its earlier turns and its source. Read blind, 35 of 40 released rows stand on their own (bar 34) |
| C-103 | Set a trace retention at `make up` for a customer corpus | `make up` sets Phoenix's default trace retention to `PHOENIX_TRACE_RETENTION_DAYS`. It was not checked against a running Phoenix: read what `make up` prints |
| C-107 | Ingest only documents the customer controls, as for C-106, until hidden text is flagged | Text no reader sees (render mode 3, fully transparent, under 2 points, white on bare paper) is dropped from a page whose other text paints ink: 2 of 80 PDFs change, both by diagram labels under 2 points |
| C-110 | Pin the parse dependencies and replay a sample after any bump | `make test-golden` converts and chunks pages of the shop corpus, German and English, and a price list made in the test, against stored snapshots |
| C-112 | Pin the embedding libraries for the go-live corpus | Every Hugging Face load names its pinned commit, and a nightly job fetches the weights at those commits and runs the real-model tests offline, failing where they skipped |
| C-114 | Bulk loads go through the host, not the Upload page | `make ingest DIR=` loads a folder from the host, and the Upload page refuses more than 20 files or 200 MB at once, naming it |
| C-117 | Fill the model cache once, keep `HF_HUB_OFFLINE=1`, and record the revisions | `EMBEDDING_MODEL_REVISION`, `NLI_MODEL_REVISION` and `QA_MODEL_REVISION` pin each encoder, fixed beside its model id, and every load passes them |
| C-118 | A purge cadence in the runbook, run per database | `make archive-purge` deletes in committed batches of 10,000 rows, only this database's, and `make doctor` prints the archive's size ([Deleting things](#deleting-things)) |
| C-119 | No stored overrides on the go-live database, or check `make settings` after every upgrade | Every stage checks the stored rows against the catalogue when it builds: a row the catalogue refuses, or a retired name, stops that stage naming it, and an override is warned about |
| C-123 | Read the audit's output by hand before go-live and at each upgrade | `configs/audit-accepted.txt` lists each accepted advisory with its reason and a review-by date, and `make audit` fails on any other and on a passed date |
| C-201 | A database password without URL-reserved characters | `make doctor` and `make corpus-hosted` refuse an `APP_DB_PASSWORD` holding `@ / : # ? %`, naming it |
| C-219 | After any model change, a preflight log must show a price for each role | A drain with `SPEND_CAP` set refuses a model litellm cannot price, naming it, and an unpriced call is logged as one |
| C-253 | Build images locally only and never push them | `.dockerignore` lets in only what the three Dockerfiles copy: no workbook, document, `.env` or key reaches a build |
| C-295 | Choose the embedding model before go-live and change it only through a migration and a full re-embed | `EMBEDDING_MODEL`, `NLI_MODEL` and `QA_MODEL` are fixed: set in `backend.env` beside their commits, and a stored row for one stops every stage naming the `DELETE` that removes it. A new embedding model still means a migration and a full re-embed |
| C-299 | Keep `MAX_FILE_SIZE_MB` at or below its shipped 100 | `MAX_FILE_SIZE_MB` is bounded at 150, what the API's 512 MB holds whole, and the API refuses a PDF of more than `PARSING_MAX_PAGES` pages or one read past `PARSING_TIMEOUT_SECONDS`, naming the setting |
| C-416 | Before ingest, list the currency codes in the corpus's tables, and ship the currency fix first beyond EUR, USD, GBP and CHF | A currency is any ISO 4217 code or currency sign beside a number, or the language's own word for one |

## Upgrading to v0.5.1

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no new setting. Two fixes and one default:

- **Dagster starts again.** v0.5.0 moved the orchestration image to SQLAlchemy 2.1, which reads a bare `postgresql://` URL as psycopg 3. The image installs only the psycopg2 that dagster-postgres brings, so the Dagster webserver and daemon failed at start, and so did `make dagster-wipe` and with it `make wipe`. `configs/dagster/dagster.yaml` now names `postgresql+psycopg2` as the scheme of the storage URL. Rebuild the orchestration image and recreate both containers, which the commands above do.
- **One reasoning effort serves a mixed model split.** `LLM_REASONING_EFFORT` is no longer sent to a hosted model that litellm knows does not reason, such as gpt-4.1 or gpt-4o, which refuses the parameter. A reasoning writer that must be told `none` to answer at temperature 0, such as gpt-5.6-sol, can now sit beside a verifier, a judge or a phrasing model that does not reason. A model litellm does not know, such as a deployment of your own name, is still sent the effort.
- **More passages are digested.** `EXTRACTION_DIGEST_MIN_CHARS` ships at 500, where it was 800, so the next extraction gives passages of 500 to 800 characters a summary and an outline. The measurement that set 800 predicts about half of those digest calls refused as `not_condensed`, at one digest call each. Stored facts keep what they were extracted with; set it back to 800 in `configs/env/backend.env` to ask only where most digests pass.

## Upgrading to v0.5.0

This section gives two paths. The first is for a stack on v0.4.5. The second is for a stack that still runs v0.3.12, as production does. Either way, a build made from scratch on a new database needs only the code, the host environment and the images below, `make up` and `make schema`, and none of the reruns.

### From v0.4.5

```bash
poetry install --with llm,nlp,data,storage,api,pipeline,viz,observability,dev
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

**Dependencies.** Every dependency moves to the newest release its range allows. That is 139 packages of `poetry.lock` moved, added or removed, with `backend/api/requirements.lock`, `frontend/requirements.lock` and the pins in `orchestration/requirements.txt` beside them. Run the `poetry install` above on a host checkout before anything else; `make install-python` runs the same command and then fetches the spaCy pipelines. Then rebuild the images, so the host and the images run the same versions.

The moves that matter to a stack:

- **SQLAlchemy** goes from 2.0.52 to 2.1.6, and 2.1.6 is now the floor in `pyproject.toml` and `backend/api/requirements.txt`. Two queries ask for DISTINCT ON through `sqlalchemy.dialects.postgresql.distinct_on`, which 2.0 lacks. A virtualenv left at 2.0.52 fails at import with `cannot import name 'distinct_on'`.
- **pandas** goes from 2.3.3 to 3.0.6 on the host and in both images. The workbook export and `make diversity` read through it.
- **Docling** goes from 2.137.0 to 2.141.0, and docling-core from 2.101.1 to 2.103.1, on the host and in the API image, where the parse worker runs. A document parsed now can come out differently from one parsed under 2.137.0. Stored parses keep what they were parsed with until `make parse-rerun`.
- **Dagster** goes from 1.13.24 to 1.13.26, and dagster-postgres from 0.29.24 to 0.29.26, in the orchestration image and on the host. Both use the one `dagster` database, so rebuild the image whenever the host moves.
- **The rest.** litellm goes from 1.100.1 to 1.106.2, transformers from 5.17.0 to 5.20.2, fastapi from 0.141.1 to 0.159.1 and pydantic from 2.13.5 to 2.14.1. The warning pydantic 2.14 raises over one of litellm's response types is ignored by name in the test configuration.
- **Pillow** stays at 12.3.0, with its advisories accepted as *Upgrading to v0.4.4* says.

**No migration.** `make schema` has nothing new to apply, and the head stays at `20e31b1656f7`. Nothing in `backend/database` changed but one of those two queries, the one that picks each passage's dominant topic.

**Settings.** No setting is new and none is gone. One default moves: `QUESTIONS_RELEASE_UNANSWERABLE` ships at 0.10, where it was 0, so a release made now holds up to a tenth unanswerable questions. The settles reading still keeps answerable ones: on link U, 19 of 60 kept out-of-corpus rows and 20 of 60 base rows were answered by the corpus after all. Up to about a third of the released unanswerable rows therefore test a chatbot for saying no to a question it should answer. This is a known defect, recorded in `docs/bugs.md`. Set the value to 0 in `configs/env/backend.env` to release none.

A category of `QUESTIONS_CATEGORIZATIONS` takes two new keys:

- `settles`: the verdict the passages its question cites must give, `answers`, `refutes` or `silent`;
- `behaviour`: what a good reply to its question does.

A categorization whose categories all carry both is the unanswerable one. Its categories are told only to the unanswerable writer, and at most one categorization may carry them. A value is refused in five more cases, listed in the [configuration guide](configuration.md):
- `settles` is none of the three verdicts;
- a category has one of the two keys without the other;
- a behaviour is empty;
- only some categories of a categorization carry `settles`;
- two categorizations carry it.

Unset, the default keeps Phrasing × Premise × Linguistic variation and adds a fourth categorization, `Unanswerable`, which deals every unanswerable slot the out-of-corpus kind alone. That kind is the perturbation unanswerable slots were always written as, and the one kind link U passed.

The kinds of UAEval4RAG (Peng et al., [*Unanswerability Evaluation for Retrieval Augmented Generation*](https://aclanthology.org/2025.acl-long.415/), ACL 2025) are `out-of-corpus`, `false-presupposition`, `underspecified` and `nonsensical`, held as `UNANSWERABLE_CATEGORIZATION` in `backend/question_generation/config.py`. The other three are opt-in. To opt in, set `QUESTIONS_CATEGORIZATIONS` to a list holding the default's three answerable categorizations and `UNANSWERABLE_CATEGORIZATION`, in place of the default's own `Unanswerable` entry, because a value replaces the default whole. JSON cannot be written in `configs/env/backend.env`, so set it on the settings page, with `PATCH /settings/questions` or with `python -m settings.run`. The three opt-in kinds got writer-prompt fixes after link U that were not re-calibrated, so link U's figures describe their prompts before those fixes.

**Prompts.** The writer's version moves from 28 to 29. Only the unanswerable writer's text changed. Every other writer prompt is the same text as under 28, as its digest in `tests/static/test_prompts_pinned.py` shows.

Told no kind, the unanswerable writer takes the same steps and checks as before, with its wording rearranged:
- its opening says the questions test whether a chatbot handles a question it should not simply answer;
- the rule against an absurd question moves into the step that says what to change;
- its reply field is described afresh.

Told a kind, it is sent that kind's variant. The catalogue records four writer variants beside `perturb`: `perturb (out-of-corpus)`, `perturb (false-presupposition)`, `perturb (underspecified)` and `perturb (nonsensical)`. An underspecified writer may decline a passage that gives no value differing by case, and the slot is then skipped. The verifier stays at 12, phrasing at 4 and the assessment template at 4, and extraction and topics are untouched. Stored questions keep the version they were written under.

**Model calls.** None is added. A draft written to a kind gets the settles readings every unanswerable draft already gets: one over the passages it cites, and, where those give its kind's verdict, one more beside the passage probe. A draft the reading refused is written again, as before, with a note for its verdict where there is one.

**Stored rows.** Nothing stored needs a rerun. `make questions-rejudge` reads each row's expected verdict off its stored category. A row written before v0.5.0 has none and reads `silent`, as it was written. The verifier's version did not move, so a rejudge asks nothing about a row already judged under verifier 12. `make questions` writes new rows under writer prompt 29, with the out-of-corpus kind by default. The next `make questions-balance` draws unanswerable rows into the release, up to the 0.10 ceiling.

**Commands, the workbook and the API.**
- `make diversity FILE=<workbook> LABELS=<file>` corrects each share reviewers labelled by the judge's verdict on all the questions, with prediction-powered inference (Angelopoulos et al., [*Prediction-powered inference*](https://doi.org/10.1126/science.adi6000), Science 2023) as ARES (Saad-Falcon et al., [*ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems*](https://aclanthology.org/2024.naacl-long.20/), NAACL 2024) does. The labels file and the report are in the [assessment README](../backend/assessment/README.md#labelled-shares-corrected-by-the-judge). It needs a workbook whose Judge column holds the judge of the DataMorgana paper (Filice et al., [*Generating Q&A Benchmarks for RAG Evaluation in Enterprise Settings*](https://aclanthology.org/2025.acl-industry.33/), ACL 2025 Industry Track).
- Every `make diversity` table but `AGAINST=`'s gains `held`, an easiness reading.
- Export a workbook again to get the new cells:
  - the Summary sheet counts the questions each model wrote, verified and phrase-judged;
  - an unanswerable row told a kind names it in its Categories cell (`Unanswerable=false-presupposition`);
  - its Answer cell reads `Expected behaviour: ` and what a good reply does.
- `GET /questions/quality` gains the maps `writer_model`, `verifier_model` and `phrasing_model`. A question in `GET /questions` gains `behaviour`, null except on an unanswerable question told a kind.
- No column, target or route is added.

### From v0.4.0 to v0.4.4

Follow the section of each release after yours first, in order, then *From v0.4.5* above. `make schema` reaches `20e31b1656f7` on the way: three revisions from v0.4.0 or v0.4.1 (v0.4.2's two and v0.4.4's), one from v0.4.2 or v0.4.3.

### From v0.3.12

This is for a stack that runs v0.3.12 and moves straight to v0.5.0. It replaces the sections for v0.3.13 to v0.4.5 and *From v0.4.5* above: follow it once, in the order given, and skip those. Each step names the release that needs it, and that release's section has the detail. Back up PostgreSQL and the `documents` bucket first (the wiki's Operations page describes the backups). One of the migrations below cannot be undone.

#### 1. Code, the host environment and images

```bash
poetry install --with llm,nlp,data,storage,api,pipeline,viz,observability,dev
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
podman compose --env-file configs/env/deployment.env --env-file .env up -d --remove-orphans
```

The last line removes, once, the `seaweedfs-ui` container that compose no longer defines (v0.4.5). The `poetry install` brings the host to v0.5.0's lock; a virtualenv left on v0.3.12's SQLAlchemy 2.0 fails at import. The images' locks have followed `poetry.lock`'s pins since v0.4.4. The API image now parses with Docling 2.141.0.

#### 2. Six migrations: `make schema`

Check what it will do with `make schema-status`. `make schema` then applies six revisions, one after the other, on top of v0.3.12's head `8f759a3a3848`:

| Revision | From | What it does |
|---|---|---|
| `a41c9e3d7b52` | v0.3.20 | Adds `questions.kind`, `NOT NULL`, backfilled from the passage scope |
| `c3a9e1470b5d` | v0.3.23 | Adds `facts.bridge`, empty on every stored bridge until `make extract-bridge FORCE=1` rewrites it |
| `d5b2f8a60c14` | v0.3.36 | A trigger takes a thread's follow-ups out of the release when its root leaves `accepted`, and a one-time repair clears the release of follow-ups already split from their root. **The repair cannot be undone by a downgrade**; *Upgrading to v0.4.0* gives the query that counts the rows it will touch |
| `733a3eadef7c` | v0.4.2 | Lets `assessment_metrics` hold the DataMorgana paper's six `rubric_*` scores |
| `626a5b07ae34` | v0.4.2 | Adds `questions.categories`, empty on stored questions |
| `20e31b1656f7` | v0.4.4 | Column comments only |

#### 3. Settings

None is required. These changed:

- **New defaults that change what a build writes.**
  - `QUESTIONS_KIND_MIX` defaults to `needs_both:5,compound:1` (v0.3.20 and v0.3.26). About one in six slots that span passages becomes a compound question; `needs_both:1` turns that off.
  - `QUESTIONS_CATEGORIZATIONS` is new (v0.4.2). Unset, it deals Phrasing × Premise × Linguistic variation (v0.4.3) and, from v0.5.0, the out-of-corpus kind to every unanswerable slot; `[]` turns categories off. The other three unanswerable kinds are opted into through it, as *From v0.4.5* says.
  - `QUESTIONS_RELEASE_UNANSWERABLE` ships at 0.10 (v0.5.0), where v0.3.12 had 0, so a release holds up to a tenth unanswerable questions, with the known defect *From v0.4.5* gives; 0 releases none.
- **Gone.** `TOPIC_LABEL_MIN_FACT_SHARE` (v0.4.4) and `REVIEW_REVIEWER` (v0.4.5) are deleted. A value left in an environment file is no longer read.
- **Held to tighter bounds** (v0.4.5). `EMBEDDING_MAX_TOKENS` must be at least 64. `ORCHESTRATION_DRAIN_TIMEOUT_SECONDS` and `ORCHESTRATION_POLL_SECONDS` must each be a finite number of seconds, at least 1, or the orchestrator's code location refuses to load: correct such a value before `make up`. `DATABASE_URL` must name a database (v0.4.4).
- **Read differently**, with no change to their values: `QUESTIONS_RELEASE_LANGUAGES` unset, `EXTRACTION_BRIDGES_PER_TOPIC`, `EXTRACTION_MIN_OTHER_SHARE`, and `TOPIC_NO_BELOW` and `TOPIC_NO_ABOVE` for a small language (v0.4.0, step 3 of its section).
- **Models.** `make doctor` asks every model a stage calls (v0.4.5). `configs/env/backend.env` puts `EXTRACTION_DIGEST_MODEL`, `TOPIC_MODEL` and `QUESTIONS_PHRASING_MODEL` on `ollama_chat/muse-glimmer:30b-mlx`. Pull that model, or point the three lines at one you have.

#### 4. Prompts and model calls

- **Prompt versions** from v0.3.12 to v0.5.0:
  - the writer, from 15 to 29;
  - the verifier, from 6 to 12, and `verifier: stated` 1 is new (v0.3.35);
  - the assessment template, from 2 to 4 (v0.4.2);
  - topic naming, from 2 to 3 (v0.4.4);
  - the bridge prompt, from 5 to 6;
  - unchanged: atomic extraction 12, repair-1, the digest 5 and phrasing 4.

  Stored rows keep the version they were written under.
- **Calls added since v0.3.12.**
  - An accepted answerable `needs_both` question citing two passages gets one more verifier read (v0.3.35).
  - A compound question costs two verifier reads (v0.3.26).
  - The DataMorgana paper's judge replaces question relevance in the assessment, one call for another, while `ASSESSMENT_ENABLED` is on (v0.4.2). A root question is judged in six calls.
  - A with-premise draft that names no asker is written once more (v0.4.3).
  - A short search query costs one more verifier read, and only while that opt-in category is configured (v0.4.3).
  - v0.5.0 adds none.

#### 5. Reruns, in order

None of these is needed to start v0.5.0. Each brings stored data up to what the releases since v0.3.12 read differently, and one pass under v0.5.0's code covers every release at once. Run only the steps your corpus needs. Each `make *-rerun` drains on the host and refuses while that stage's container worker runs. To rerun with the container workers, use the stage's page or `POST /{stage}/rerun?confirm=true` instead.

| Step | Command | Needed because of |
|---|---|---|
| Parse | `make parse-rerun` | v0.3.31, v0.4.0 and v0.4.4; and v0.5.0's Docling 2.141.0. It refuses while the parse worker runs |
| Chunk | `make chunk-rerun` | v0.3.31, v0.3.32, v0.4.0 and v0.4.4. A passage the new cut repeats exactly keeps its facts. Every other one is replaced, the facts and bridges resting on it go into the archive, and the questions resting on them are rejected as `source_changed` and kept. Without `SHA` it refuses unless `CONFIRM` names the database |
| Extract new passages | `make extract-start`, then `make extract` | The passages the re-chunk made have no facts yet. Only those reach the model |
| Give back repair pieces | `make extract-recap`, then `make extract-dedup` | v0.3.14; no model call for the recap |
| Judge facts again | `make extract-revalidate` | v0.3.15, v0.3.29, v0.3.33 and v0.4.4. No model call |
| Rewrite bridges | `make extract-bridge FORCE=1` | v0.3.16, v0.3.23 (fills `facts.bridge`), v0.3.28, v0.4.0 and v0.4.4 (records the passage that headed each link). The one rerun that calls the model for every bridge. `FORCE=1` is needed while an accepted question cites a bridge, and those questions are rejected as `source_changed` and kept |
| Refit topics | `make topics-discover` | v0.4.0 and v0.4.4. Figures and models move to `topics/<database>/<language>`, and until this runs the Topics page shows no figure. A name or coverage choice a person gave goes to the topic holding most of its passages |
| Questions already stored | `make questions-rescore`, then `make questions-reverify` | The stored kind and citations (v0.3.20, v0.3.25), the number and answer readings (v0.3.18, v0.3.19, v0.3.24 and v0.3.33), and v0.4.3's gates and reads. Reverify can reject a stored question and never gives a rejected one back |
| Ask unanswerables again | `make questions-rejudge` | v0.4.3 moved the verifier to 12. The first run costs one settles reading for each stored accepted unanswerable question, and a second where its cited passages are silent and the probe is on. Later runs ask nothing new |
| Redraw the release | `make questions-balance` | v0.3.27, v0.4.0 and v0.4.3 (a scarce kind no longer caps the release), and the thread trigger |

Two more are optional:
- Stored questions carry no categories, no compound kind and no unanswerable kind. Only a fresh `make questions` writes those.
- `make assess-rerun ONLY=--only\ kind=question` judges stored questions with the DataMorgana paper's judge (v0.4.2). It clears and replaces every stored question verdict, the old `relevance` rows included. `make diversity LABELS=` and the judge's means need it.

#### 6. What else changes for you

- **The workbook.** On its next export it gains a Kind column after Type (v0.3.34) and a Categories column (v0.4.2). The Summary sheet counts kinds, categories (v0.4.3) and the models that made the set (v0.5.0). An unanswerable row told a kind gives its expected behaviour in the Answer cell (v0.5.0).
- **Argilla.** Recreate a question dataset made before v0.4.3: it lacks `kind` (v0.3.28), the `thread` field and `turn` (v0.3.34), and the categories (v0.4.3). Recreate a facts dataset made before v0.4.5: it lacks each fact's `language`. The [review README](../review/README.md) says how.
- **The API.** *Upgrading to v0.4.0* and *Upgrading to v0.4.5* list what moved: assessment reruns answer 409 when the phase cannot run, `GET /pipeline/runs` refuses a `limit` outside 1 to 500, and NUL bytes and lone surrogates are refused at the edge.
- **Test runs** from a checkout no longer load its `.env` (v0.4.3).

## Upgrading to v0.4.5

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

Then, once, remove the old `seaweedfs-ui` container, which compose no longer defines:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env up -d --remove-orphans
```

There is no migration: `make schema` has nothing new to apply, and the head stays at v0.4.4's `20e31b1656f7`. `backend/database` gains only a check of the text PostgreSQL can store, which the API's refusals call.

One setting is gone and none is new, and three are held to tighter bounds:

- `REVIEW_REVIEWER` is deleted from `configs/env/review.env` and the review settings. It was read and never used, since no column records who reviewed a row. A value left in an environment file is no longer read.
- `EMBEDDING_MAX_TOKENS` below 64 is refused when written, where 1 was taken: the chunker cuts to it less the embedder's own tokens, and a window of 1 to 6 left every document failing chunking or cut into sub-word passages. The shipped 512 is unchanged.
- `ORCHESTRATION_DRAIN_TIMEOUT_SECONDS` and `ORCHESTRATION_POLL_SECONDS` must each be a finite number of seconds, at least 1. The orchestrator's code location refuses to load with `nan`, an infinity, a negative or anything under a second, so a value like that in `configs/env/orchestration.env` or `.env` has to be corrected before `make up`. The shipped 28800 and 15 load as before.

Any setting, topic label or upload filename holding a NUL byte or a lone surrogate is refused at the edge: `out_of_range` for a setting, 422 for a topic label and 400 `invalid_value` for a filename, where it reached the database and answered 500. A refused upload writes no object and no `ingest_events` row. A 422 body is now written ASCII-escaped, so it can echo such input back; a JSON reader gets the same text as before.

The API's orchestration routes: Stop asks Dagster for every unfinished run of the corpus job rather than the five newest. `GET /pipeline/runs` refuses a `limit` outside 1 to 500 with a 422, as every listing does. It and `PUT /pipeline/automation` answer 503 `orchestrator_refused` when Dagster answers with an error, where they answered `no_orchestrator`, so a client that branched on `no_orchestrator` for both should read the code. The `arrivals` sensor asks once more for a corpus run that failed, then skips, naming `make pipeline` and the Run button, until new documents arrive or the queue empties.

Models: a hosted `LLM_MODEL` is no longer sent the `OLLAMA_BASE_URL` address when `LLM_BASE_URL` still holds it, so it reaches its provider's own; a gateway address in `LLM_BASE_URL` is kept. `make doctor` asks every model a stage calls one question, `LLM_MODEL` and each stage's own, the judge only while `ASSESSMENT_ENABLED` is on, where it asked `LLM_MODEL` alone. `configs/env/backend.env` puts three judgements on `ollama_chat/muse-glimmer:30b-mlx` (`EXTRACTION_DIGEST_MODEL`, `TOPIC_MODEL` and `QUESTIONS_PHRASING_MODEL`), so a deployment that never pulled it now fails `make doctor` there rather than at its first digest: pull it, or point the three lines at a model you have.

No prompt moves, and no question, extraction or topic code changed, so nothing stored needs a rerun and no stage's model calls change.

Compose: the backend and orchestration images are named for the compose project, `qa_generator-backend` and `qa_generator-orchestration` as before unless `-p` or `COMPOSE_PROJECT_NAME` names another, so the default stack keeps its images. A stack now has 23 containers. A second stack beside the first sets `COMPOSE_PROJECT_NAME` and the ten published ports in its own `.env` (see [A second stack beside the first](#a-second-stack-beside-the-first)); `make test-smoke` reads the project name and `DAGSTER_WEBSERVER_PORT` from the shell, so export both there. A Podman machine smaller than the workers run at once is what [A smaller stack](#a-smaller-stack) is for.

What a person on the pages will notice:

- Every listing's search box holds at most 200 characters, the bound the listing routes hold a search to. A longer paste is cut to its first 200 characters, where it replaced the page below the search with `Failed to load: 422`.
- The Topics search looks in a topic's terms joined by commas, as the table shows them, and *Label and terms* looks in the label and the terms each alone.
- Saving only a topic's coverage choice no longer cuts a stored name longer than the 120 characters `PATCH /topics` takes: the page sends the name only when it was edited.
- A filename, an artefact's text and a stage's reason are drawn as written, never read as HTML or Markdown.
- A row that leaves a listing after it was picked is named, *Row 8036 is no longer in this list; anything pressed for it was not done.*, and nothing pressed for it is done.

Review: a fact push leaves out the facts answered in Argilla and not yet pulled, as a question push already did. A fact record now carries `language` metadata, the language of the passage at its own citation. A facts dataset created before v0.4.5 has no such term, and a push to it drops the term with a warning naming the steps: `make review-pull-facts`, then delete the dataset in Argilla and push again. A pull leaves a corrected topic name over 120 characters in Argilla, with its coverage answer, and logs the topic ids; shorten it there and pull again. The [review README](../review/README.md) lists both limits.

A build made from scratch needs none of the steps above beyond the build and `make up`.

## Upgrading to v0.4.4

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
make schema
```

`make schema` applies one revision on top of `626a5b07ae34`, the head since v0.4.2: `20e31b1656f7`, which changes column comments and nothing else. `questions.categories` now says it is NULL wherever no category was rendered, a compound question included; `topics.top_terms` says a label is carried across a refit by the passages a topic holds, not by its terms; `topics.embedding` says it is read to place each passage the fit left in no topic in the nearest one; and `facts.bridge` says it also holds the id of the passage that headed the link (`head`), and that a bridge older than prompt 6 reads as headed by the passage it shows first. No row changes, and a downgrade puts the old texts back. A revision written elsewhere on top of `626a5b07ae34` now takes `20e31b1656f7` as its parent.

Rebuild both images. Their locks are now resolved under the pins of `poetry.lock`, so every package an image shares with the host runs at the host's version, and a static test holds them equal. Of the 30 pins that had drifted, the ones that matter to a stack are Docling 2.137.0 in the API image (it held 2.132.0), pandas 2.3.3 in the API's workbook export (it ran pandas 3), protobuf 6, aiohttp 3.14.5 and litellm 1.100.1. The parse worker runs in the API image, so a document it parses now can come out differently from one it parsed under 2.132.0; the host already ran 2.137.0. On a host checkout nothing changes: `poetry.lock` and `pyproject.toml` are as they were. `make lock` now writes both image locks, `backend/api/requirements.lock` and `frontend/requirements.lock`, in a throwaway container under those pins; run it after changing a `requirements.txt`.

Pillow stays at 12.3.0 in `poetry.lock` and both image locks. GitHub's 9 open Dependabot alerts on it and the 21 advisories OSV lists are fixed only in Pillow 13.0.0, which no released Docling allows, so each is accepted with its exposure: none is reached by the parse of an uploaded PDF (`docs/bugs.md` says why). Once docling and docling-core release the lift, the upgrade is those releases with docling-parse 7.22.4, docling-ibm-models 4.0.4 and streamlit 1.66.1 or later, then `make lock` and an image rebuild. `make audit` reads OSV, which lists three Pillow advisories PyPI's service missed.

One setting is gone and none is new:

- `TOPIC_LABEL_MIN_FACT_SHARE` is deleted. It could never fire on a real fit, where every topic's share of fact-bearing passages is one. A topic is now left unnamed when it is no passage's strongest. A value left in an environment file is no longer read, and a value stored through the Settings page is ignored.
- `PARSING_OCR_CHAR_THRESHOLD` (100) also decides which pages of a digital PDF are named as image-only: a page holding no more characters than it, under pictures covering at least half of it, is named in the parse warning, the stored parse's metadata and `documents.parse_error`. The document is parsed for its other pages as before.
- `DATABASE_URL` must name a database: topic figures and models are keyed by it, and one with no database in its path is refused, naming the variable, when a figure or a model is stored or read.

Prompts: the topics naming prompt moves from version 2 to 3. The model flags a topic with no subject in a field of its answer instead of writing "Mixed", so a refusal in any language is left unnamed. Extraction stays at atomic prompt 12, repair-1 and digest 5, and the bridge prompt stays at version 6, byte for byte, though its list of relation names is now read off `llm/spans.py`. No question prompt moves: v0.4.4 changes no question code. `tests/static/test_prompts_pinned.py` pins the new topics version. Topics already named keep their names until the next fit names them again.

Model calls: none is added. A topic that is no passage's strongest is no longer sent to the naming model, so a fit may make a call or two fewer.

Topic figures and models move to new keys, `topics/<database>/<language>.html` in `export` and `.npz` in `models`, the database read from the path of `DATABASE_URL`, so a second database on the same object store no longer overwrites or archives this one's. The old keys `topics/<language>.*` are not read: until `make topics-discover` runs, the Topics page and `GET /topics/visualisation/{language}` show no figure and `make topics-render` finds no model. The old objects stay where they are, and nothing reads them.

Stored rows take the new readings only when you rerun them. In order, on an existing database (none of this is needed to start v0.4.4, and a build from scratch needs none of it). Each `make *-rerun` drains on the host and refuses while that stage's container worker runs; to rebuild with the container workers, rerun from the stage's page or `POST /{stage}/rerun?confirm=true` instead:

1. `make parse-rerun` parses every document again: the mend drops every format character and reads a C1 control as its cp1252 character, a table label wrapped over three lines is joined whole, and a stamped scanned page is named. It runs on the host and refuses while the parse worker runs.
2. `make chunk-rerun` cuts every document again. A passage the new cut repeats exactly keeps its facts; every other one is replaced, the facts and bridges resting on it go with it, into the archive, and the questions resting on them are rejected as `source_changed` and kept. What moves: sentences after an abbreviation (`incl. VAT`, `Art. 5`, `Mo.–Fr.`), after one inside a bracket or a quote (`(cf. Section 4)`) and after `p.a.` or `EUR/Mon.` before a lower-case word, a figure ending a sentence (`Die Gebühr beträgt EUR 5.`), which no longer opens the next, a lone integer beside its label, a sentence cut at a page break before a capital, a body line opening with the running foot's name, a chapter opening under a heading spelled unlike its running head, a list-item lead-in, a heading holding ` > ` (now written ` › `), a picture's footnote and a bilingual list. Without `SHA` it refuses unless `CONFIRM` names the database.
3. `make extract-start`, then `make extract`: the passages the re-chunk made arrive `new`, so the first queues them and the second drains the queue. Only those passages reach the model. (`make extract` alone drains only what is already queued.) A passage skipped before as a grid of identifiers, a fee table whose amounts carry a currency code (`EUR 5`), was marked read and is not queued again: `make extract-rerun SHA=` reads its document again, replacing that document's facts; the questions on them are rejected as `source_changed` and kept.
4. `make extract-revalidate` judges every stored fact again under the new checks, with no model call: a German *Sie* read against its passage, a fact opening on *such a card*, *the following fees*, *the above fees* or an inflected *Nachstehende Bedingungen*, *dies* after a free relative clause.
5. `make extract-bridge FORCE=1` writes every bridge again, each now recording the passage that headed its link, which is what a narrowed pass and `MISSING=1` read from now on, and a subsection reference (`Section 7(2)`) now links the section it cites. It is the one rerun that calls the model for every bridge. `FORCE=1` is needed while an accepted question cites a bridge, and those questions are rejected as `source_changed` and kept.
6. `make topics-discover` fits the topics again and names them, and writes the figure and the model under the new keys. A name or coverage choice a person gave goes to the new topic holding most of its passages; a model's name is given again. Identical passages now get identical memberships, so a few passages can change topic (5 of 1,150 on the calibration bases).
7. `make questions-reverify` holds every stored question to its facts and the gates again, and rejects one whose facts went or no longer hold; it never gives a rejected one back. If the refit changed the topics, run `make questions-rescore` after it, so a question's topic scope and difficulty band follow the new topics.

A restore from the archive now keeps a follow-up's release only under a turn still accepted and released in the same release; otherwise it comes back accepted but undrawn, and the next `make questions-balance` decides. The archive README lists what else a restore does.

Operations: `make audit` also audits the host `poetry.lock`, and it and `make lock` keep their scratch files in a temporary directory removed on any exit. `make dev` waits at most 60 seconds for Postgres and says so when it never answers. `make questions-export OUT=`, `make diversity FILE=` and `AGAINST=`, and the spend targets' `LOG=` take a path holding a space, and every target takes a command-line value holding `( )`, `&` or a quote whole; `QA_COMMAND_LINE` names only the variables given on the command line. `make spend` and `make spend-by-shape` refuse a `LOG` that names no readable file with exit status 2. `make audit` reads every lock against OSV and runs whole on Linux only, as the nightly job runs it: on a Mac the `poetry.lock` leg fails on CUDA wheels with no macOS build. The configuration guide lists `QUESTIONS_KIND_MIX` among the settings that read a default in code: its line in `backend.env` is a comment, so every deployment deals `needs_both:5,compound:1`. CI runs every job on `ubuntu-24.04` with poetry 2.3.2, the version that wrote `poetry.lock`.

## Upgrading to v0.4.3

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

There is no migration: `make schema` has nothing new to apply, and the head stays at `626a5b07ae34`. Nothing in `backend/database` changed.

No setting is new. Unset, `QUESTIONS_CATEGORIZATIONS` now deals three categorizations: Phrasing and Premise as before, and Linguistic variation, a question in the document's own terms (similar-to-document) or in other words that keep every term's meaning (distant-from-document), at even odds. To keep v0.4.2's two, set it to `DEFAULT_CATEGORIZATIONS` in `backend/question_generation/config.py` without its Linguistic variation entry. The setting accepts one more value, and two of its fields now do more than before:

- A category may be `"form": "premise"`, besides `question` and `query`. The default's with-premise category is of this form, and its description is reworded: the premise states a fact of the asker's own situation, something they have, did, bought or plan, never only the topic, the answer wanted or that they are reading or checking something. A premise is not told beside a category that caps the question's words, nor beside a search query; such a slot is written as no category of the premise's categorization.
- A category's `words` bound `max` now has two effects besides the report: a premise is not told beside it, and a search query carrying it is read once more against the passages it does not cite and is refused as not recoverable where one of them answers it differently. A `min` alone has neither effect.
- A search query is no longer told on a slot that spans two passages, nor on a `reason`, `comparison`, `implication` or `temporal` slot. Such a slot is written as no category of the query's categorization.
- The descriptions of distant-from-document, now in the default, and of expert and long-search-query, in the guide's opt-in JSON, are reworded. A value you set yourself is used as written, so copy the new JSON from the [configuration guide](configuration.md) if you want it.
- A value is refused, naming the categorization or category at fault, in nine cases, all listed in the guide, among them a categorization named twice, a line break in a name, a category with no description, probabilities given to some categories only and a probability outside 0 to 1.

The prompt versions move. The writer's goes from 19 to 28: 20 is the aggregation prompt's count rule, 21 the line on people and stories in the material and on contact boxes, 23 to 25 and 27 the premise, and 26 the search queries; 22 let a title name what a question asks about, and 28 takes that back, so the writer is told about titles what 19 told it. The verifier's goes from 6 to 12: the round trip's read also says whether the passages give a reason beyond the rule, and answers only where the passages answer the question as it is asked. No other module changed its version (phrasing stays at 4, the assessment template at 4, and extraction and topics are untouched), and `tests/static/test_prompts_pinned.py` pins both new versions. Questions already stored keep the version they were written under.

Model calls: the reason check rides on the round trip's read, which every answerable question already gets, so it adds no call. A short search query, one that has a `words` maximum, costs one passage probe (an index lookup, no model) and one more verifier read, and only while a category of that kind is configured and `QUESTIONS_ELSEWHERE_PASSAGES` is above 0 (the default is 20); long queries and every other question are unchanged. A with-premise question whose first draft holds no first- or second-person word is written once more, with a note. The default categories use no query, so a default run adds at most that rewrite. `make questions-rejudge` asks again about every accepted unanswerable question whose `settles` verdict was given under another verifier version. Because v0.4.3 moved that version, its first run on an upgraded database costs one `settles` reading for each stored accepted unanswerable question, and a second where the cited passages are silent and the passage probe is on. It is a one-time cost: later runs ask nothing.

Stored questions meet the new gates only when you rerun them:

- `make questions` writes new rows under writer prompt 28 and the new categories.
- `make questions-reverify` holds the stored rows to the new gates and reads.
- `make questions-balance` draws the release again. The draw now caps a kind the pool holds too few of at what a release can take of it and spreads its places over the other kinds, so a release grows where one scarce kind used to cap it. Draw it once after the other two.

The export command line refuses a `--question-type` or `--answer-form` that does not exist, as `GET /questions/export` does, where it wrote an empty workbook and exited 0. A review dataset made before v0.4.3 must be recreated to carry the categories field and the new guideline; the [review README](../review/README.md) says how.

Test runs from a checkout no longer load the checkout's `.env`: `LITELLM_MODE=PRODUCTION` is set when the model client is imported, so an xdist worker started from a worktree cannot pick up another checkout's model names and credentials. A process that imports the client does not read a `.env` above its working directory; the project's own settings loading (`LOADENV`, compose) is unchanged.

A build made from scratch writes everything under these versions and needs none of the reruns above.

## Upgrading to v0.4.2

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
make schema
```

`make schema` applies two revisions on top of v0.4.0's head `d5b2f8a60c14`. `733a3eadef7c` lets `assessment_metrics` hold the six `rubric_*` scores of the DataMorgana paper's judge; its downgrade deletes those rows before the old CHECK returns. `626a5b07ae34` adds `questions.categories`, the categories a question's writer was told; it stays empty on stored questions.

No setting is required. `QUESTIONS_CATEGORIZATIONS` is new and optional: unset, a fresh generation deals the paper's Phrasing (concise, verbose) and Premise (direct, with-premise) at even odds, and the [configuration guide](configuration.md) gives the JSON for the categories to opt into. The writer prompt moves from version 16 to 19. The assessment template moves from version 2 to 4: a root question is judged in six calls and eleven metrics and a follow-up in five, and phoenix-evals' question relevance is no longer asked (stored rows are kept and read as before). On a host checkout run `poetry install`: scipy is now declared, and it was already installed through gensim.

Stored questions keep what they were written with: a fresh `make questions` writes categories, and `make assess-rerun ONLY=--only\ kind=question` judges stored questions again with the paper's judge, which clears and replaces every stored question verdict. `make diversity FILE=<workbook>` measures an exported workbook (n-gram diversity, self-repetition, word and part-of-speech compression ratios, homogenization; `AGAINST=`, `BY=category`, `BY=kind`, `BY=document`) and changes nothing stored. A declined one-passage application slot is now written as a one-passage question instead of being told to span while labelled single.

## Upgrading to v0.4.1

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration, no setting, no prompt change and no model call. `make diversity FILE=<workbook>` is new: it measures how varied an exported workbook's questions are and changes nothing stored, so no stage needs rerunning.

## Upgrading to v0.4.0

This section is for a stack that runs v0.3.12 and moves straight to v0.4.0. It replaces the sections for v0.3.13 to v0.3.36: follow it once, in the order given, and skip those. Each step says which release needs it, so a stack that already holds some of them can leave those out. Back up PostgreSQL and the `documents` bucket first (the wiki's Operations page describes the backups); the migrations below cannot all be undone.

### 1. Code, images and the host environment

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

On a host checkout also run `poetry install` (it also picks up certifi 2026.10.19, past GHSA-6q48-6c7w-9gw2; the images' locks pin it too). The host `poetry.lock` now pins aiohttp 3.14.5 and yarl 1.25.1 (v0.3.28), which closes three advisories (CVE-2026-111063, CVE-2026-111064 and GHSA-2g87-pp6c-29x5); the images' own locks were fixed in v0.3.13. Nothing else in the lock was meant to move.

### 2. Three migrations: `make schema`

`make schema` applies three revisions, one after the other, on top of v0.3.12's head (`8f759a3a3848`). Check what it will do first with `make schema-status`.

| Revision | From | What it does |
|---|---|---|
| `a41c9e3d7b52` | v0.3.20 | Adds `questions.kind` (`single`, `needs_both`, `compound` or `false_premise`), `NOT NULL`. Existing rows are backfilled from the passage scope: `needs_both` where it is `multi_passage`, `single` otherwise (176 `needs_both` on the accepted answerable rows of the v0.3.12 build). The same rule backfills the question payloads held in wipe archives made before the column existed, so restoring an older archive no longer fails on an empty kind. Downgrading takes the key out of the payloads again |
| `c3a9e1470b5d` | v0.3.23 | Adds `facts.bridge`, a nullable JSON object `{relation, question, answer}` that only a bridge may carry. No backfill: it stays empty on every stored bridge until `make extract-bridge FORCE=1` rewrites that bridge |
| `d5b2f8a60c14` | v0.3.36 | Adds a trigger and its function, so that a question leaving `accepted` (by a person, by a re-check, or by the trigger that rejects a question that lost a fact) takes every follow-up below it out of the release in the same statement. It also repairs, once, the threads already split: it clears `release_id` on follow-ups that stay released under a root that is not accepted. That repair cannot be undone by a downgrade. To see how many rows it will touch on a stored corpus, run `SELECT count(*) FROM questions q WHERE q.release_id IS NOT NULL AND q.follows_id IS NOT NULL AND EXISTS (SELECT 1 FROM questions r WHERE r.id = q.follows_id AND r.status <> 'accepted');` beforehand (it counts direct follow-ups; deeper turns of the same threads are cleared too) |

No other release between v0.3.12 and v0.4.0 adds a migration.

### 3. Settings

No setting was removed and none is required. One default is new and changes what a build writes:

- **`QUESTIONS_KIND_MIX` defaults to `needs_both:5,compound:1`** (the setting arrived in v0.3.20 with `needs_both:1`, which is v0.3.12's plan; v0.3.26 changed the default). About one of every six slots that span passages is now dealt as a compound question, which asks two separate things, one answered by each of two passages, and costs two verifier reads. `QUESTIONS_KIND_MIX=needs_both:1` turns compound questions off.

Two existing settings read differently, with no change to their values:

- With `QUESTIONS_RELEASE_LANGUAGES` unset, a release weighs each language by the accepted questions a draw can take from it (answerable ones; unanswerable ones too only when `QUESTIONS_RELEASE_UNANSWERABLE` is above 0), not by all of them (v0.4.0). The ids of an existing release can move slightly when you rerun `make questions-balance`.
- `EXTRACTION_BRIDGES_PER_TOPIC` counts a pair on the passage that heads it, whichever topic its partner sits in; `EXTRACTION_MIN_OTHER_SHARE` no longer caps the facts a repair call splits out of a refused statement.

`TOPIC_NO_BELOW` and `TOPIC_NO_ABOVE` now scale with a language's passage count below six passages, so a small language keeps terms instead of failing silently (v0.4.0); values are unchanged.

### 4. A new model call

From v0.3.35 every accepted answerable `needs_both` question that cites two passages gets one more verifier call, under the new pinned prompt `verifier: stated` 1: it lists the parts of the answer and quotes every passage that states each part, the code finds the quotes, and the question stays two-passage only when each cited passage holds a part no other holds. This costs about USD 0.45 to 0.5 for a build the size of the Laws of the Game. If the model is unavailable or refuses the reading, the question is kept as cited, with a warning, and nothing is lost. Compound questions never reach it. Stored questions are not rejudged by it.

### 5. Reruns, in order

None of these is needed to start the new version; each brings stored data up to date with the reading the release changed. Run only the steps your corpus needs; the first column says what each is for.

| Step | Command | Needed because of |
|---|---|---|
| Parse | `make parse-rerun` | v0.3.31 (a font's U+00AD hyphen is kept, `3-5 Werktage` no longer reads `35`; a table's group row stays its own row; a wrapped label's tail joins its label); v0.4.0 (a document with an image-only page now names it in a warning and in the stored parse's `image-only-pages` metadata; it is not refused) |
| Chunk | `make chunk-rerun` | v0.3.31 (follows the parse), v0.3.32 (a table's footnote is written beneath the table; a colon-ended lead-in is kept with every piece of a table), v0.4.0 (a chunk ends where its prose changes language; a chapter opening mid-page starts at its own heading). A re-chunk keeps every passage whose text comes back unchanged, with its facts, so only changed passages are rebuilt |
| Extract new passages | `make extract-start`, then `make extract` | passages the chunk rerun changed have no facts yet; the stage queues what it has not been asked to do and drains the queue, so only those passages reach the model |
| Give back repair pieces | `make extract-recap`, then `make extract-dedup` | v0.3.14 (a repair piece no longer competes for the per-passage cap: on the v0.3.12 build all 65 `over_cap` refusals are freed, with no model call); the dedup decides the cross-passage repeats the freed facts may leave |
| Judge facts again | `make extract-revalidate` | v0.3.15 (a bridge's heading and title are read as an atomic fact's are), v0.3.29 (polite Sie, exceptive clauses, German "dies"), v0.3.33 (numbers read as values, spelled counts past twelve). No model call |
| Rewrite bridges | `make extract-bridge FORCE=1` | v0.3.16 (pairs follow the documents' own links across topics, under bridge prompt 6; adds about USD 0.25 to a build), v0.3.23 (fills `facts.bridge`), v0.3.28 (an earlier topic-scoped pass may have lost cross-topic bridges), v0.4.0 and v0.4.0 (links resolve in the right document; sibling pairs are dealt among passages that hold a validated fact). `FORCE=1` is needed while an accepted question cites a bridge. This is the one rerun that calls the model for every bridge |
| Refit topics | `make topics-discover` | v0.4.0 (a refit may rename topics whose names shared an ending that is a top term, and may add topics for a small language; a name or coverage choice a person gave stays). A language left without a model now ends the fit as failed, after the other languages are stored |
| Questions already stored | `make questions-rescore`, then `make questions-reverify` | the stored kind and citations (v0.3.20, v0.3.25: reverify holds a compound question to its kind), and the number and answer readings of v0.3.18, v0.3.19, v0.3.24 and v0.3.33. Reverify can reject a stored question; it never gives a rejected one back. A rule that frees questions takes effect only in a fresh generation (`make questions`) |
| Redraw the release | `make questions-balance` | v0.3.27 (sizes are scanned down and the first that fills is kept, instead of bisecting), v0.3.28 onward (v0.4.0: kinds and languages held only by unanswerable rows no longer shrink the release) and the new thread trigger |

Two upgrades need no rerun but a recreated dataset: the Argilla question datasets made before v0.3.28 lack the `kind` metadata term, and those made before v0.3.34 lack the `thread` field and `turn` metadata. The stale warning appears; recreate the dataset to get them.

### 6. What else changes for you

- The questions workbook gains a Kind column after Type on its next export (v0.3.34), and the Questions page tells Type (what a question asks) from Kind (what it was written as).
- `POST /assessment/rerun` and the Redo button answer 409 `assessment_cannot_run` before touching any stored verdict when the assessment cannot run (`ASSESSMENT_ENABLED` off, or no judge model set); before v0.4.0 they wiped every stored verdict and answered 202.
- Restoring an archive skips a row whose foreign-key parent is absent and prints what it left behind per table; a restored question keeps its `release_id` only when the live release holds it (v0.4.0).
- Speed: the release draw scans sizes downward and takes seconds at one or two thousand accepted rows (minutes at 10,000), and sibling linking over one flat parent is several times faster, 16 s instead of 132 s at 2,000 sections (v0.4.0).

## Upgrading to v0.3.36

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
make schema
```

`make schema` is needed: revision `d5b2f8a60c14` (on `c3a9e1470b5d`) adds a trigger and its function, and runs a one-time repair that clears `release_id` on released follow-ups whose root is not accepted; a downgrade cannot undo the repair. To see how many follow-ups the repair touches on a stored corpus first: `SELECT count(*) FROM questions q WHERE q.release_id IS NOT NULL AND q.follows_id IS NOT NULL AND EXISTS (SELECT 1 FROM questions r WHERE r.id = q.follows_id AND r.status <> 'accepted');` (it counts direct follow-ups; deeper turns of the same threads are cleared too). Rerun `make questions-balance` afterwards to redraw the release.

## Upgrading to v0.3.35

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. A new `make questions` run makes one more verifier call per accepted answerable needs_both question citing two passages (about USD 0.45 to 0.5 per build), under the new pinned prompt `verifier: stated` 1; stored questions are not rejudged.

## Upgrading to v0.3.34

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. The workbook gains a Kind column on its next export. Existing Argilla question datasets lack the `thread` field and the `turn` metadata term: the stale warning appears; recreate the dataset to get them.

## Upgrading to v0.3.33

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. Rerun `make extract-revalidate` to read stored facts with the new number readings, and `make questions-reverify` for stored questions. On the Laws of the Game one English fact (13216) is admitted and nothing else moves.

## Upgrading to v0.3.32

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. Run `make chunk-rerun` to bring a stored corpus up to date; a document with table footnotes or tables longer than one passage under a lead-in changes its passages. On the 30 football PDFs 0 passages change. The parse, its content hash and language are untouched.

## Upgrading to v0.3.31

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. `make parse-rerun` then `make chunk-rerun` brings a stored corpus up to date: a PDF whose font maps its hyphen to U+00AD (pymupdf and MuPDF Arial subsets) gets its hyphens back, and a document with group-row or wrapped-label fee tables reads them as rows. On the 30 football PDFs 1 element per language changes.

## Upgrading to v0.3.30

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. Stored questions stay as they are. A new `make questions` run deals compound samples from a passage's own claims and unanswerable slots from facts resting on one passage; a topic that held only bridges for such a slot writes fewer questions of it, and the log names each slot skipped.

## Upgrading to v0.3.29

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. Rerun `make extract-revalidate` to read stored facts with the new reference reading; on the Laws of the Game three German facts are admitted and no other verdict moves.

## Upgrading to v0.3.28

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. On a host checkout run `poetry install` to pick up the new `poetry.lock` (aiohttp 3.14.5, yarl 1.25.1). A narrowed `make extract-bridge` no longer deletes bridges opening outside the scope; run a whole-corpus `FORCE=1` pass to rebuild such bridges after a topic change. Existing Argilla question datasets lack the `kind` metadata term: the stale warning appears, recreate the dataset to get it. Stored data does not change.

## Upgrading to v0.3.27

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. Rerun `make questions-balance` to redraw the release; no extraction or question stage needs rerunning. A pool whose stored hash already filled (v0.3.12's did, at 395 rows) is released the same. The draw takes longer on a large pool, seconds at one or two thousand rows.

## Upgrading to v0.3.26

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. **Compound questions are now dealt**, in about one of every six spanning slots (the kind mix defaults to `needs_both:5,compound:1`); `QUESTIONS_KIND_MIX=needs_both:1` turns them off. Measured on pairs built by the calibration script, not through the deal: 28 of 48 accepted and, read blind, 28 of 28 compound, 0 false joins, 75% usable and keys right 68%, under the 80% and 75% the calibration asked. The real path through the deal is not calibrated yet; the corpus rebuild on this release measures it. A compound question costs two verifier reads and no round trip, and the weld rate counts only the `needs_both` kind. Stored questions stay as they are.

## Upgrading to v0.3.25

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. `make questions-reverify` now holds a stored question to its stored kind, so a compound question is no longer rejected for its two question words. It cannot re-check a compound question's two halves, which are not stored; only the two-question-word refusal is skipped for it.

## Upgrading to v0.3.24

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. Two readings of the answer checks are fixed: a numbered list's markers no longer count as figures in `answer_incomplete`, and a dash range's unit matches whatever part of speech the tagger gives it. Both only free refusals, and a rule frees questions only in a fresh question generation: `make questions-reverify` never gives back a rejected question.

## Upgrading to v0.3.23

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
make schema
```

`make schema` applies one migration: it adds `facts.bridge`, empty on every row, with no backfill, and constrains it to a bridge. Bridges written before it stay empty until `make extract-bridge FORCE=1` rewrites them. Nothing else changes: no prompt version moves and no stored verdict moves.

## Upgrading to v0.3.22

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. Writer prompt 16 (it was 15): the prompt text of each type gains a compound variant, and no stored question moves. **Compound questions are off by default**; `QUESTIONS_KIND_MIX=needs_both:5,compound:1` deals one spanning slot in six as compound. They were calibrated on pairs built by the calibration script, not through the deal, so the real path is not calibrated, and the blind read missed its quality bars (75% usable, keys right 68%): turn it on to measure it, not for a release. A compound question costs two verifier reads and no round trip. The weld rate counts only the `needs_both` kind; a compound question is never a weld.

## Upgrading to v0.3.21

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. No kind fixes a band yet, so no stored band moves and `make questions-rescore` is not needed; it is needed after a kind that fixes one ships.

## Upgrading to v0.3.20

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
make schema
```

`make schema` applies one migration: `questions.kind`, `NOT NULL` and one of `single`, `needs_both`, `compound`, `false_premise`, backfilled `needs_both` where the passage scope is `multi_passage` and `single` otherwise (176 `needs_both` on the accepted answerable rows of the v0.3.12 build). Nothing else changes: no prompt version moves, no stored verdict moves, and `QUESTIONS_KIND_MIX` is optional and defaults to `needs_both:1`, which is today's plan. The questions page shows the kind.

## Upgrading to v0.3.19

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. The `answer_incomplete` gate refuses fewer list keys, so a build refuses fewer questions and keeps more. The rule frees questions only in a fresh question generation: `make questions-reverify` never gives back a rejected question.

## Upgrading to v0.3.18

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. A key holding a range written with a dash is no longer refused as `not_recoverable` when the recovery gives each end in its own words. The rule frees questions only in a fresh question generation: `make questions-reverify` never gives back a rejected question.

## Upgrading to v0.3.17

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. Only the plan of the question stage changes: a build that writes unanswerable questions plans them as factoid, entity and reason questions. Stored questions stay as they are and no prompt version moves. `QUESTIONS_RELEASE_UNANSWERABLE` stays 0.

## Upgrading to v0.3.16

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting.

**Bridges.** `make extract-bridge` writes the bridges again from the new pairs under bridge prompt 6, which records `prompt_version` 6 (`FORCE=1` while an accepted question cites a bridge). A pass narrowed with `--only` deletes the bridges of its topics, including the cross-topic ones, and rewrites only the links whose head it reads. The pass now parses every readable passage once, about 20 seconds per 700 passages, and a pair whose passage holds no validated atomic fact is not read. It costs about USD 0.25 more a build in input tokens. A heading numbered before its word ("1.2 Returns") gives no reference link, only sibling and term links.

## Upgrading to v0.3.15

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. `make extract-revalidate` judges the stored bridges again under the new rule, with no model call: on the v0.3.12 build 6 become validated and 5 change their refusal to `not_bridging`; none validated is refused.

## Upgrading to v0.3.14

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting.

**The cap and the repair pieces.** A fact the repair call wrote for a
statement refused as `not_atomic` no longer competes for its passage's atomic
cap. `make extract-recap` gives back the repair pieces an earlier cap refused,
with no model call; on the v0.3.12 build it frees all 65 `over_cap` refusals
(none newly refused). Run `make extract-dedup` after it, which re-decides the
cross-passage repeats the freed facts may leave. Facts, bridges, topics and
questions already built on the stored facts stay as they are until the stages
that read them are run again. A full re-extraction gives the same result for
new rows, because the cap is applied in flight, but it asks the model again
for every passage, which `make extract-recap` does not, so recap is the way
to carry the change into a stored build.

## Upgrading to v0.3.13

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting. The rebuild installs aiohttp 3.14.4 in the API
image and the workers, which fixes three advisories published against 3.14.3.
Nothing else changes and no stored data moves.

## Upgrading to v0.3.12

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting.

**Verifier prompt 6.** Every verifier prompt is now version 6 and only the
settles prompt changed. `make questions-rejudge` asks every accepted
unanswerable question again under it, about two model calls each; some will
be refused. `QUESTIONS_RELEASE_UNANSWERABLE` stays 0.

## Upgrading to v0.3.11

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting.

**The topic fit.** A fit now makes eight seeded draws and keeps the most
cohesive, so it takes about eight times as long, a few seconds per language
on a corpus of a few hundred passages. Stored topics stay until the next
`make topics-discover`, which names the new topics and carries a person's
decisions as v0.3.7 does; bridges and questions follow the topics.

## Upgrading to v0.3.10

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting.

**A repair prompt (`repair-1`).** A passage whose model-written statements are
refused as `not_atomic` costs one more model call, which writes the split
facts. It runs only when a passage is extracted, so stored facts gain nothing
until the corpus is extracted again.

**The claim counter.** `make extract-revalidate` judges stored facts again
without a model call; on the reviewed build it validates 8 refused facts.

## Upgrading to v0.3.9

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting.

**Bridge prompt 5.** Stored bridges stay as they are and are marked as written
by an older prompt. `make extract-bridge FORCE=1` writes them again, replacing
the ones accepted questions cite, which rejects those questions; questions and
the release then follow.

**The deal.** A bridge is offered to the writer alone, so the next questions
pass writes one question per bridge where it wrote a bridge beside a claim.
Questions already stored are untouched.

## Upgrading to v0.3.8

Check that `.env` sets every secret compose now requires, then rebuild:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env config -q
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no prompt change.

**Secrets.** Every password and key compose passes is now required, and
compose stops naming the first one missing. `.env.example` names every one;
an `.env` written before this release may lack a line, which must be added by
hand, since `make setup` writes `.env` only when there is none.

**Settings refused that were accepted.** A number that is `nan` or infinite,
a flag spelled other than as true or false, `TOPIC_NUM_TOPICS` below 2,
`TOPIC_RANDOM_STATE` outside 0 to 2^32 - 1 and a `TOPIC_NO_ABOVE` of 0 are
refused when written. One already stored keeps working where it did; the
settings page shows it with a warning so it can be corrected.

**What else an operator will notice.**

- The frontend answers only at `localhost` and `127.0.0.1`.
- `PAGE_SIZE` outside 1 to 500 stops the frontend at start-up.
- `/redoc` is gone; `/docs` stays.
- Stop stops every queued or started run, not only the newest, and says
  which were already stopping.
- A topic `PATCH` changes only the fields its body names.
- The Argilla topics dataset makes the corrected label optional for a newly
  created dataset; recreate an existing one to take the change.
- `make eval-score` figures are not comparable with earlier ones: it now
  scores the reader production runs.

## Upgrading to v0.3.7

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no setting.

**Two prompts changed: atomic extraction 12 and the digest 5.** Every stored
fact is now marked as written by an older prompt, and nothing is re-run on
its own. The new prompts reach stored facts only through a re-extraction of
the corpus (`make extract-start` with the stack up), which replaces every
passage's facts and so the questions resting on them: topics, bridges,
questions and the release then follow, as in the v0.3.0 rebuild. On a corpus
the size of the reviewed rulebook that is about 1,640 model calls for the
extraction alone.

**Topic names.** The next `POST /topics/discover` carries a person's name and
coverage choice only to the new topic holding most of the same passages. A
decision with no such topic is dropped and logged, and the run's span counts
it; check the log after a refit and name those topics again in the topic
review.

## Upgrading to v0.3.6

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
make schema
```

`make schema` applies one migration, which only corrects the passages
table's comment; its downgrade restores the old wording.

**A re-chunk now keeps what it does not change.** A passage whose text,
section path, sentences and table cells come out the same keeps its id, its
facts and its topics, so a parsing fix rebuilds only the passages it
changed.

**Carrying the fixes into stored data.** The parsing and chunking fixes reach
stored passages through a re-parse and a re-chunk (`POST /parsing/rerun?confirm=true`,
then `POST /chunking/rerun?confirm=true`, with the stack up); neither calls a model. The
passages they change lose their facts and questions, so run extraction,
topics and questions again after them, as the v0.3.0 upgrade describes. On
the reviewed rulebook that is 30 passages carrying 237 facts and 86
questions.

## Upgrading to v0.3.5

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration, no setting and no prompt change.

**`make questions-balance` now leaves a record.** Its trace reaches Phoenix
under the run, and its log names every pair of released questions it put to
the twin judge, with the round and the verdict, and how far each kind, band
and language came from its quota.

**Unanswerable questions.** The check that a verifier's quote sits in the
passages now reads a quote stitched from bullets, cells or a passage's
continuation piece by piece. It applies to every `settles` judgement made
from now on: in a question generation and in `make questions-rejudge`, which
asks again only a row whose stored verdict is from an older prompt version.
`QUESTIONS_RELEASE_UNANSWERABLE` stays 0.

## Upgrading to v0.3.4

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration, no setting and no prompt change.

The round-trip and typing gates change how a question being written is
judged, so they apply to the questions written from now on. Stored questions
keep their verdicts: `make questions-reverify` runs only the gates that need
no model, and these need the verifier's reading. A topic generated again
(`make questions-start TOPIC=…`, then the worker) is judged the new way.

## Upgrading to v0.3.3

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration, no setting and no prompt change.

**Carrying the fixes into stored facts.** With `extract-worker` stopped, run
`make extract-revalidate`. It judges every stored fact again with this
release's checks, without calling a model and without changing a statement,
and now also puts what it validates through the duplicate gate and the
per-passage cap. Facts it newly validates are offered to the next question
generation; no stored question changes.

**What the extract worker now does by itself.** After a run that replaced
facts - a re-extraction of a document or of the corpus - the worker replays
the dedup gate over the corpus once its queue is empty, so a fact refused as
the twin of one that run deleted is given back. Two workers never replay at
once. A deletion through the API or the UI still needs `make extract-dedup`
afterwards.

## Upgrading to v0.3.2

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration, no setting and no prompt change.

The fixes change how text and numbers are read: where sentences end, which
figure-only paragraphs are page numbers, how a hyphen broken across a table
cell or a page is mended, and how a German decimal, a time or a total is
compared. Everything the stages produce from now on reads them the new way.
What is already stored keeps its old reading until it is built again: the
sentence and hyphen fixes reach stored passages and facts through a re-parse
and a re-chunk and the stages after them (see [Upgrading to
v0.3.0](#upgrading-to-v030) for the order), and the number readings reach a
stored question only when it is written again. Parsing and chunking call no
model.

## Upgrading to v0.3.1

Rebuild the images, since the code they run has changed, and let `make doctor`
confirm the API serves this build:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
make doctor
```

`make doctor` now compares the settings the API serves with the settings the
checkout defines, and names any the API lacks: an API still serving an older
build is the usual cause, and the rebuild above the cure.

No migration and no prompt change, so nothing needs re-running: v0.3.1
produces the same passages, facts and questions from the same input.

| Setting | v0.3.0 | v0.3.1 |
|---|---|---|
| `LLM_STRUCTURED_MODE` | any instructor mode | one of `FUNCTIONS`, `PARALLEL_TOOLS`, `TOOLS`, `TOOLS_STRICT`, `JSON`, `JSON_O1`, `MD_JSON`, `JSON_SCHEMA`, the modes litellm's client takes; anything else is refused at start-up |
| `QUESTIONS_MEETS_SHARE` | required | absent reads 0.02 |

What an operator will notice:

- **A model call is billed at most `LLM_MAX_ATTEMPTS` times.** instructor's
  own re-asks are off, a 429 waits what its `Retry-After` asks (two minutes
  at most), and a provider's content filter is a refusal after one call
  that skips one question slot rather than failing its topic.
- **`make spend` counts failed calls**, which are billed too, and prints cost
  to four decimals; `make spend-by-shape` reads the same log the same way.
- **`make delete` and `make delete-derived` refuse while `extract-worker`
  runs**, before they delete anything. Stop the worker first, or delete
  through the API and run `make extract-dedup` once the worker is stopped.
- **`make audit` fails when it finds an advisory.**
- **`ARGILLA_API_KEY` reaches Argilla**, on a fresh `argilla_data` volume
  only: an owner Argilla already created keeps its key.

## Upgrading to v0.3.0

Rebuild the image, since the code it runs has changed:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build api
make up
```

No migration: no table, column or constraint changes.

These settings changed in `configs/env/backend.env`. A deployment that copied
the file keeps its old values until it takes the new ones:

| Setting | v0.2.2 | v0.3.0 |
|---|---|---|
| `QUESTIONS_RELEASE_DIFFICULTY` | `easy:1,medium:1,hard:1` | unset, which follows the answerable pool's own band split |
| `QUESTIONS_RELEASE_UNANSWERABLE` | 0.10 | 0, until the `settles` judgement can be trusted with them |
| `QUESTIONS_ELSEWHERE_PASSAGES` | 10 | 20 |
| `QUESTIONS_FOLLOWUP_TYPES` | `condition,reason,comparison` | `condition,reason` |
| `QUESTIONS_MEETS_SHARE` | — | 0.02, new; required until v0.3.1 |
| `QUESTIONS_RELEASE_TYPES` | `aggregation:4` | `aggregation:1`, the other kinds unchanged |

Six prompts changed, so the runs after the upgrade record new prompt
versions: atomic extraction 11, the digest 4, question writing 15, the
verifier 5, the phrasing judge 4 and topic naming 2.

**`make questions-balance` now calls the verifier**, about once per released
question, to judge which released questions want one answer. It proves the
verifier model before it asks anything.

On v0.3.0 `QUESTIONS_MEETS_SHARE` is required: a `backend.env` copied from
v0.2.2 must gain the line `QUESTIONS_MEETS_SHARE=0.02`, or `make questions`
and `make questions-balance` stop on the missing name and `question-worker`
logs that it refuses to claim work. From v0.3.1 an absent line reads 0.02.

**What the stored data needs.** Most of the fixes change the passages, the
facts or the topics themselves, so stored rows improve only through a
rebuild, and the container workers build it. With the stack up (`make up`),
queue each stage once the one before it has finished: `POST /parsing/rerun?confirm=true`,
then `POST /chunking/rerun?confirm=true`, then `make extract-start`, then
`POST /topics/discover`, then `make extract-bridge MISSING=1`, then
`make questions-start`, and last `make questions-rejudge` and
`make questions-balance`. The bridge pass has no worker yet, so it runs on
the host. The host drains - `make parse-rerun`, `make chunk-rerun`,
`make extract`, `make topics-discover`, `make questions` - refuse while their
stage's worker runs, and are for developing a stage. Parsing and chunking
call no model; every step from extraction on does.

`make topics-discover` carries a name a person gave to the new topic holding
most of the passages it was given for, and no name a model gave, so every
topic it names is named the v0.3.0 way: in one call per language, in the
corpus's own spelling, without the domain every name shares. A name can be
changed in the topic review: `make review-push-topics`, then
`make review-pull-topics`.

## Upgrading to v0.2.2

Rebuild the image, since the code it runs has changed, then bring the schema
up:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build api
make up
make schema
```

The three new revisions change column comments only. No table, column or
constraint moves, and each downgrades cleanly.

These settings changed in `configs/env/backend.env`. A deployment that copied
the file keeps its old values until it takes the new ones:

| Setting | v0.2.1 | v0.2.2 |
|---|---|---|
| `EXTRACTION_DUPLICATE_COSINE` | 0.95 | 0.985 |
| `QUESTIONS_OFF_TOPIC_OVERLAP` | 0.3 | 0, which turns the gate off |
| `QUESTIONS_ELSEWHERE_PASSAGES` | 4 | 10 |
| `QUESTIONS_DUPLICATE_SHARED_COSINE` | — | 0.88, new; optional, and unset holds a shared fact to `QUESTIONS_DUPLICATE_COSINE` |
| `QUESTIONS_RELEASE_LANGUAGES` | — | optional, new; unset follows the pool's own language split |

Three prompts changed, so the runs after the upgrade record new prompt
versions: question writing 12, the verifier 3 and atomic extraction 10.

**What the stored data needs.** The fixes change what the next run writes.
Rows already stored improve only through a re-run. In this order, the
commands that call no model come first:

| Command | Calls a model | What it carries into stored rows |
|---|---|---|
| `make extract-dedup` | no | Duplicate refusals the new rule would not make are given back, with their passages re-judged and re-capped, and fold citations come off the facts they were written onto |
| `make extract-revalidate` | no | Facts refused for a pronoun their own statement resolves are validated |
| `make extract-recap` | no | The atomic cap, now never below a passage's sentences plus list items, and the repair pieces an earlier cap refused given back |
| `make questions-rescore` | no | Each question's scope and difficulty, from the facts it cites now. Run it after `extract-dedup` and before re-verify, and not after any other re-run: there it would hide a question that lost a fact |
| `make questions-reverify` | no | The new gates, on every accepted question. It only rejects |
| `make questions-rejudge` | yes, the verifier | The `settles` judgement, on every accepted unanswerable question |
| `make questions-balance` | yes, the verifier | A release with the language share, hash order and twin check, the twins judged by the verifier |

Struck-through text, list lead-ins and chapter-aware section paths change
the passages themselves. They reach stored rows only through a rebuild by the container workers:
`POST /parsing/rerun?confirm=true`, then `POST /chunking/rerun?confirm=true`, then extraction, topics,
the bridge pass (`make extract-bridge MISSING=1`) and questions again, all of which
from extraction on call models. A fresh question generation also carries
the fixes that live in how questions are written: the widen retry, the deal,
the reason and application slots, the perturbation prompt, and the gates that
only ever rejected. `make questions-reverify` never gives back a rejected
question.

## Things that go wrong

| Symptom | Usually |
|---|---|
| Topics sit `pending`, nothing in the logs | `question-worker` is downloading 2.2 GB of embedding weights |
| `make assess` prints one line and stops | `ASSESSMENT_ENABLED` is not true, in `.env` or in the override the Assessment page stores, which wins; `make settings SERVICE=assessment` shows the value in force |
| `make assess` refuses before it claims anything | `ASSESSMENT_JUDGE_MODEL` names a model that is not served |
| A queue fills and nothing drains it | That stage has no container. `make up` |
| Grafana panels are empty | The shipper. `make logs-shipper` |
| A panel that groups by `stage` finds nothing | A field missing from `append_fields` in `filebeat.yml` |
| An edit to `filebeat.yml` changed nothing | The filebeat container still runs the file it started with: `podman compose restart filebeat` |
| Grafana cannot read the database | `init.sh` has not run on this volume |
| The run dashboard's Phoenix panels cannot read their tables | The grants `make up` and `make dev` make have not run. `make grafana-grants` |
| Streamlit refuses a file the API would accept | `server.maxUploadSize` is below `MAX_FILE_SIZE_MB` |
| The frontend will not start, naming a variable | It is declared but not in the `streamlit` service's `environment` |
| Argilla refuses the key | Its owner was made before compose passed it `ARGILLA_API_KEY`, and keeps the key Argilla made. That one is under "My settings": copy it into `ARGILLA_API_KEY`. It is not `ARGILLA_PASSWORD` |
| Argilla restarts, logging that Elasticsearch is not available | `certs/` was generated by macOS's LibreSSL before v0.2.1 and lacks key identifiers. Delete `certs/`, then `make down && make dev` |
| A p99 climbing towards `LLM_TIMEOUT_SECONDS` | Calls about to time out, be tried again and fail their rows. Raise the timeout |
| A scanned PDF is refused rather than parsed | OCR is not enabled |
| `make questions-reverify` rejects many questions as `source_changed` after `make extract-dedup` | Their stored scope still counts the fold citations the dedup removed. Run `make questions-rescore` first |
| The release report warns that a language in the pool has no weight | `QUESTIONS_RELEASE_LANGUAGES` leaves it out, so none of it is drawn. Name it, or unset the setting to follow the pool's own language split |

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
make restore-documents SINCE=<time>  # list the deletions from then on
make restore-documents AT=<archived_at>  # put those deletions back
make archive-purge DAYS=30        # the second deletion. This one is final
```

Nothing purges itself, so the archive grows on ordinary runs too — a
re-extraction and a re-chunk delete the facts they replace (the questions on them are kept, rejected). `make doctor` prints the archive's rows and
size, read from the planner's statistics so it costs nothing however large the
archive is. Purge on a cadence per database, after `make backup`: `make
archive-purge DAYS=<n>` deletes in committed batches of 10,000 rows, so a large
archive never holds one lock or one transaction, and it takes only this
database's rows and objects. See [`backend/archive/`](../backend/archive/README.md).

These two archive nothing, because `TRUNCATE` and a dropped volume fire no
row trigger:

```bash
make down-volumes CONFIRM=all-volumes  # the containers' data, all of it
make schema-reset                 # every table, rebuilt from the revisions
```

Deleting a document takes everything derived from it. What it does **not**
take is `topics`: a fit is over the corpus rather than over a file, so
`make wipe` is one command that runs both.

A claim two documents in the same language share, as the same kind of fact, rests on one of them only; a translation's claim is its own language's fact and is never a duplicate. The second copy is
stored as a `duplicate` refusal that names the first and cites only its own
passage. Deleting the first document therefore takes the claim with it,
and leaves the second copy refused. `make delete` and `make delete-derived`
then run `make extract-dedup` over the whole corpus. It calls no model,
gives that copy back, and re-judges and re-caps the passages of what it gave
back, and no others. Every deletion, `make delete`, `make delete-derived`,
either `DELETE` route or the Documents page, ends with one line saying how
many duplicate refusals lost the fact they repeated. The extraction worker
re-decides them when its queue is empty: it asks for a refusal pointing at no
twin, which a deletion leaves however it was made, while the worker ran, before
it started or across a rebuild for changed settings. Where no extraction worker
runs, as in the go-live profile, run `make extract-dedup`. No `make questions-rescore` follows
a deletion: the questions that rested on the deleted facts went with them.

The deletion and the replay are two steps. Both refuse beside a running
`extract-worker` container, and `make delete` asks before it deletes, so that
refusal leaves the document where it was. If the replay fails after the
deletion, the document is already gone, and running `make delete SHA=…`
again finds nothing to delete. The recovery is `make extract-dedup`, once
whatever stopped it is out of the way.
