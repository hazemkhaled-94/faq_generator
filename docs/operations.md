# Operations

How to run, size, back up, upgrade and troubleshoot the stack.

## The services

After `make dev` reports ready, these services answer at the default ports
from `configs/env/deployment.env`. A [second
stack](#a-second-stack-beside-the-first) moves them.

| Service | URL | Purpose |
|---|---|---|
| Frontend | <http://localhost:8501> | Run each stage, browse what it produced |
| API | <http://localhost:8000/docs> | OpenAPI documentation |
| Phoenix | <http://localhost:6006> | Traces, gate verdicts, judgements, prompts, experiments, the playground |
| Grafana | <http://localhost:3001> | Logs and pipeline dashboards |
| Argilla | <http://localhost:6900> | Review what the models decided |
| Adminer | <http://localhost:9001> | Database browser |
| Dagster | <http://localhost:3000> | The asset graph and run history |

PostgreSQL, SeaweedFS, Elasticsearch, Redis, Filebeat, the Dagster daemon and
the six stage workers run behind them: 23 containers in all.

Credentials:

| Service | Setting |
|---|---|
| Phoenix | `PHOENIX_DEFAULT_ADMIN_INITIAL_PASSWORD`, user `admin@localhost` |
| Grafana | `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD` |
| Argilla | `ARGILLA_USERNAME`, `ARGILLA_PASSWORD` |

`make services` and the System health page query `GET /services`, which probes
the catalogue in [`backend/api/services.py`](../backend/api/services.py) live.
Use it to see what is up.

### Access

Every published port binds to 127.0.0.1. PostgreSQL and the SeaweedFS S3
gateway publish a port for host commands. The SeaweedFS master, filer and
volume servers publish none. The API answers only the host names in
`API_ALLOWED_HOSTS` and refuses with 403 a browser request from another site
and a write from another origin.

Every write to the API and every read of `/settings` must carry the shared
secret `API_TOKEN` in the `X-API-Token` header. Without it the API answers 401
`unauthorized`. `make setup` generates the secret into `.env`, and the
frontend, the orchestrator and the make targets send it. An API started
without one refuses every write.

The secret is shared and is not a login, so the binding to 127.0.0.1 is a
requirement of the deployment. An existing `.env` needs the line added: run
`make setup` again, which fills only placeholders, and recreate the stack.

`EMBEDDING_MODEL`, `NLI_MODEL`, `QA_MODEL` and `DOCLING_ARTIFACTS_PATH` are
fixed. A value stored for one of them through the UI, the API or `make
settings-set` stops applying, and the value in the environment files is read.
Set an intended value in `configs/env/backend.env` before upgrading.

## Memory

The memory limits in [`compose.yaml`](../compose.yaml) add up to about 33 GiB
at the shipped sizes.

| Service | Limit |
|---|---|
| PostgreSQL ([sized below](#sizing-postgres)) | 4 GiB |
| Question worker | 6 GiB |
| Parse and extract workers | 4 GiB each |
| Chunk and topic workers | 3 GiB each |
| Elasticsearch | 2 GiB |
| Every other service | 1 GiB or less |

The limits are ceilings, not reservations. A container that reaches its limit
is killed.

On macOS and Windows the containers run inside Podman's virtual machine, which
has its own memory size. `podman machine inspect` shows it
(`Resources.Memory`, in MiB). Stop the machine to change it:

```bash
podman machine stop
podman machine set --memory 16384
podman machine start
```

A machine smaller than the workers run at once needs [the smaller
stack](#a-smaller-stack). That stack with the parse or the chunk worker has
run in a machine of 8 GiB. The question worker's limit alone is 6 GiB.

### Sizing Postgres

One server holds five databases and three vector indexes (passages, facts and
questions, 1024 dimensions each). Its size follows the corpus.
[`configs/env/deployment.env`](../configs/env/deployment.env) holds the
values:

| Setting | Effect |
|---|---|
| `POSTGRES_CPUS`, `POSTGRES_MEMORY` | The container's limits |
| `POSTGRES_SHM_SIZE` | The container's `/dev/shm` |
| `POSTGRES_SHARED_BUFFERS`, `POSTGRES_MAINTENANCE_WORK_MEM`, `POSTGRES_EFFECTIVE_CACHE_SIZE`, `POSTGRES_MAX_CONNECTIONS` | Passed to the server as `-c` options |

A vector is 4 KB, and an HNSW index over it is about the same size again. The
facts are the largest of the three: 137,000 vectors are about 0.55 GB of
vectors and 1.1 GB with the index, and the passages and the questions add a
fifth. The working set is that total, and the memory is three times it, so the
index stays cached while a second one is built.

The shipped values fit the production corpus: about 300 documents, 20,000
passages and 137,000 fact vectors, ten times the reviewed build.

| Corpus | Passages | Fact vectors | `POSTGRES_CPUS` | `POSTGRES_MEMORY` | `POSTGRES_SHM_SIZE` | `POSTGRES_SHARED_BUFFERS` | `POSTGRES_MAINTENANCE_WORK_MEM` | `POSTGRES_EFFECTIVE_CACHE_SIZE` |
|---|---|---|---|---|---|---|---|---|
| The reviewed build | 2,000 | 14,000 | 1.0 | 1G | 256m | 256MB | 256MB | 640MB |
| Five times | 10,000 | 70,000 | 2.0 | 2G | 512m | 512MB | 512MB | 1280MB |
| Production (shipped) | 20,000 | 137,000 | 4.0 | 4G | 1g | 1GB | 1GB | 2560MB |
| Twenty times | 40,000 | 274,000 | 4.0 | 8G | 2g | 2GB | 2GB | 5GB |

- `POSTGRES_SHM_SIZE` is at least `POSTGRES_MAINTENANCE_WORK_MEM`. A parallel
  index build takes its memory from `/dev/shm`, and a container gets 64 MB by
  default. A restore of the reviewed dump failed there with `could not resize
  shared memory segment` during a parallel HNSW build.
- `POSTGRES_MAINTENANCE_WORK_MEM` is what one index build holds before it
  spills to disk, where pgvector warns that the graph does not fit. Set it to
  the size of the largest index, the facts' index.
- `POSTGRES_MAX_CONNECTIONS` follows the processes, not the corpus. The API
  and the six workers each hold `DATABASE_POOL_SIZE` plus
  `DATABASE_POOL_OVERFLOW` connections (70 in all). The object store's filer
  holds up to `WEED_POSTGRES_CONNECTION_MAX_OPEN` (50). Phoenix, Dagster,
  Argilla, Grafana, Adminer and a person with `psql` use the rest of the 250.
  A worker scaled to more replicas, or a larger pool, adds its own share. Keep
  the total under 80% of the limit. `tests/static/test_env_files.py` refuses a
  pool that does not fit.
- A changed value needs `podman compose up -d postgres`, which recreates the
  container on its volume. No migration is needed.

### A smaller stack

`make dev` starts every service. A run needs fewer: the database, the object
store, the API and the stage workers it uses. Logs and dashboards
(Elasticsearch, Filebeat, Grafana), review (Argilla and Redis), Adminer and
Dagster only watch and drive a run. The `-start` targets and the host drains
need none of them.

```bash
make certs logs-dir
export COMPOSE_ENV_FILES=configs/env/deployment.env,.env
podman compose up -d api phoenix seaweedfs-volume seaweedfs-volume2
make schema
```

`up` also starts what these depend on: PostgreSQL and the SeaweedFS master,
filer and S3 gateway. The two volume servers are named because no service
depends on them and the object store cannot write without them. Phoenix
receives the traces of host commands. Add `streamlit` for the pages.

Then bring up one stage worker at a time, queue its stage and stop the worker
once its queue is drained:

```bash
podman compose up -d parse-worker
make parse-start                 # make parse-status says when it is done
podman compose stop parse-worker
```

`make pipeline` and `make all` need Dagster. On this stack, drive a run with
the `-start` targets, or with the host drains while the stage's worker is
stopped.

## A second stack beside the first

Two checkouts on one machine each run a stack once the second has its own
project name and its own published ports. Compose names every container,
volume, network and built image for the project (`qa_generator` unless another
name is set), so a second project has its own database, object store and
images. The database names in `configs/env/deployment.env` can stay.

Set the name and the ten ports in the second checkout's `.env`. Compose and
the Makefile read it after `configs/env/deployment.env`, so its values win.
`make doctor` lists each name it moves.

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

Every address a host command or a page uses derives from these ports, so
nothing else moves. The URLs in the services table answer on the new ports,
and `make services` lists them. The smoke layer reads the project name and the
Dagster port from the shell, not from `.env`, so give `make test-smoke` both:

```bash
COMPOSE_PROJECT_NAME=qa_second DAGSTER_WEBSERVER_PORT=23000 make test-smoke
```

## Scaling

`parse-worker` and `chunk-worker` scale horizontally. Each claims one row at a
time with `FOR UPDATE SKIP LOCKED`.

`extract-worker` scales to two replicas at most, or to one host drain beside
one replica. Workers running side by side judge a passage's facts again inside
the store, under a lock per language and kind, so two passages read at once do
not both keep one restated claim. See the `duplicate` refusal in [the
extraction README](../backend/extraction/README.md). Two drains were measured
on copies of the reviewed build and of the shop calibration corpus. Over the
same 257 passages two drains took 0.57 of one drain's time, and over 168 shop
passages 0.54. Neither kept a claim twice. More than two are not measured, so
a deployment runs no more ([Production deployment](#production-deployment)).

```bash
export COMPOSE_ENV_FILES=configs/env/deployment.env,.env
podman compose up -d --scale extract-worker=2
```

Keep the drains within the database's connections ([Sizing
Postgres](#sizing-postgres)) and the provider's rate limit.

The provider's quota bounds the number of drains, not the database. On the
Azure quota this build ran on, two drains of the model stages ran side by side
without a failed row. Six lost 3 of 10 topics to rate limits. A drain waits
out a rate limit (`Retry-After`, two minutes at most, ten minutes in all per
call) without using up `LLM_MAX_ATTEMPTS`. Five rows in a row that the model
could not be reached for stop the drain with exit 75 and the rows back in the
queue. Too many drains therefore cost time, not rows. Run at most two model
drains against one database on that quota, and measure before raising the
number.

| Worker | Scaling |
|---|---|
| `question-worker` | Scales the same way, with less to divide: its queue is one row per topic |
| `topic-worker` | Can be scaled, with no gain: a fit is one request row |
| `assess-worker` | Cheapest to scale. It loads no pretrained weights, uses 1 GB and one CPU, and asks a served model two to six questions about text it already has |

`question-worker` loads `EMBEDDING_MODEL` (2.2 GB) before it claims anything,
and downloads it into the `models` volume if the extract worker has not. The
topics stay `pending` until it finishes, and `make logs` says so. Its 6 GB
limit covers the embedding model and the `NLI_MODEL` weights. The weights are
per container, not per lane.

`assess-worker` does nothing until `ASSESSMENT_ENABLED` is true, so a
deployment that never turns the evaluation phase on pays for one idle
container. It reads the flag every `WORKER_POLL_SECONDS`. Switching it on from
the Assessment page needs no restart. A change to `.env` reaches it with `make
up`.

## Sizing a corpus

`make estimate` prints, for the rows still to do, the time, the model calls
and the spend of each stage, before anything is queued. It multiplies them by
what one row of the stage took in the reviewed build: 30 documents, 1,973
passages and 41 topics, Azure models, 5 h 41 min and USD 75.53 end to end.
Those rates are the table below. Another provider or another model split has
other rates, and `make spend LOG=run.log` reads them off a run.

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

Row counts follow from the corpus:

- A document is 66 passages.
- A passage carrying a validated fact belongs to a topic at 40 passages a
  topic (`TOPIC_PASSAGES_PER_TOPIC`), up to the ceiling `TOPIC_NUM_TOPICS` a
  language.
- A topic leaves 53 accepted questions. A run writes `QUESTIONS_PER_TOPIC`
  slots for each topic, so questions grow with the topics and the topics with
  the passages.
- A stage whose workers scale (`DRAINS=questions=2`) divides its time by the
  drains and keeps its spend.

The production corpus is ten times the reviewed one: 300 PDFs and 20,000
passages, which give 410 topics and 21,750 accepted questions. One drain of
each stage takes 81 hours and costs USD 725. The 410 topics follow from
`TOPIC_NUM_TOPICS` at 300 a language. Spending less means lowering
`QUESTIONS_PER_TOPIC`, which scales the questions and the coverage down
together.

| Stage | Rows | Time, one drain | Time, extract and questions at 2 drains | USD |
|---|---|---|---|---|
| parse and chunk | 300 documents | 46 min | 23 min at 2 | 0 |
| extract | 19,730 passages | 20.2 h | 10.1 h | 131 |
| topics | 19,730 passages | 11 min | 11 min | 0.39 |
| bridges | 410 topics | 2.0 h | 2.0 h | 21 |
| questions | 410 topics | 55.7 h | 27.9 h | 554 |
| release | 21,750 accepted | 1.9 h | 1.9 h | 15 |
| assess | a fixed sample | 23 min | 23 min | 3.59 |
| total | | 81 h | 43 h | 725 |

The example uses two drains because the current Azure quota carries two. A
third drain shortens the time only on a larger quota. Measure the quota before
raising the number of drains.

Size besides time:

- [Postgres](#sizing-postgres) for the vectors.
- The parse worker's memory for the longest document. `PARSING_MAX_PAGES` is
  180 pages, about 3.1 GB of the worker's 4 GB by the measured curve. The
  curve is measured on the host and still to be measured in the worker's Linux
  image.
- The topic worker's 3 GB, which holds the passages-by-topics matrix of 10,000
  by 300 for one language at a time.

## What the model costs

[measurements.md](measurements.md) has the per-call latency and the per-stage
spend of the last run. A passage whose sentences carry no finite verb is
skipped before the call.

Live, use the **2 · What each stage is doing** dashboard and Phoenix. For a
finished run, read a captured log:

```bash
make spend LOG=run.log
make spend LOG=run.log SINCE=2026-09-19
```

`LOG` is required. It names the text log a terminal saw, not the shipped JSON.

The cost log is the spend of record. The figure Phoenix shows is indicative:
Phoenix prices a call on its own table of models, which may price a new model
differently from `make spend`. After setting a price in Phoenix, reconcile the
two per model. Where they differ, trust `make spend`.

## Replaying a call in the Phoenix playground

Open any `completion` span in Phoenix and replay it against a chosen model
with the prompt as it was sent.

The playground works against Ollama only, because every other provider Phoenix
offers needs an API key. Two lines on the `phoenix` service wire it:
`OLLAMA_BASE_URL` set to `OLLAMA_CONTAINER_URL`, and an `extra_hosts` entry so
`host.docker.internal` resolves. With `OLLAMA_CONTAINER_URL` unset, Phoenix
falls back to `localhost:11434`, which inside its container is Phoenix itself.

Prompts are selectable in the playground. A stage publishes what it records
when it starts, and `make prompts-publish` republishes all of them.

## Dashboards

Grafana provisions four dashboards from `configs/grafana/` over three
datasources. They are numbered in reading order, and each opens with what it
answers and which tool answers the rest.

| Dashboard | Reads | Shows |
|---|---|---|
| 1 · Where the corpus is now | PostgreSQL | Queue depth per stage, failures with reasons, fact and question acceptance, topic coverage |
| 2 · What each stage is doing | Elasticsearch | Units finished per interval, model latency at p50/p95/p99, facts and questions accepted against refused |
| 3 · One run, end to end | all three | One run on one page: what it produced, what it cost, its Phoenix projects, the gate verdicts, every line it wrote |
| 4 · Every line every process wrote | Elasticsearch | Lines per level, what failed and where |

Logs say what happened once. The tables say what is true now. A row that a
worker died holding logged nothing and is still counted in **1 · Where the
corpus is now**.

Dashboard 3 joins both sides through a run: `questions.run_id` on one side and
a Phoenix project named `<position>-<stage>-<RUN_ID>` on the other. Only a run
named with `RUN_ID` gets a project of its own. The spans of an unnamed run sit
in its stage's shared project, and the Phoenix panels show nothing for it. The
`Phoenix` datasource is the same PostgreSQL server and a different database,
read by the same `grafana_reader`.

Grafana holds state and logs only. To see how one artefact was produced, open
it on its page in the application and read the **How this was produced** fold.
Phoenix shows the calls behind a step, and Dagster shows which run produced
it.

Watch **model latency p99** during a long run. A call that runs past
`LLM_TIMEOUT_SECONDS` is tried again up to `LLM_MAX_ATTEMPTS` times and then
fails its row. A p99 climbing towards the timeout means a stage is about to
fail rows.

`grafana_reader` holds `SELECT` and nothing else. `configs/postgres/init.sh`
creates it, and that script runs only on the first boot of an empty volume. On
a stack that already has a volume, run it:

```bash
export COMPOSE_ENV_FILES=configs/env/deployment.env,.env
podman compose exec postgres bash /docker-entrypoint-initdb.d/init.sh
```

`make up` and `make dev` grant `SELECT` on the five Phoenix tables the run
dashboard queries, once Phoenix has made them. `make grafana-grants` grants
them on its own, for a stack started another way.

### Rotating `GRAFANA_SECRET_KEY`

Grafana encrypts the secrets in its database with `GRAFANA_SECRET_KEY`, so a
new key has to reach them in order:

1. Snapshot the `grafana_data` volume.
2. With Grafana still running under the old key, rotate its data keys: `POST
   /api/admin/encryption/rotate-data-keys` as `GRAFANA_ADMIN_USER`. It answers
   204.
3. Remove the signing keys Grafana stored encrypted under the old key, so it
   mints its own. Left in place, `/api/signing-keys/keys` answers 500. The
   repository has no command for this step.
4. Put the new `GRAFANA_SECRET_KEY` in `.env` and recreate the `grafana`
   container, which `make up` does once the value has changed. Compose passes
   it as `GF_SECURITY_SECRET_KEY` and refuses to start Grafana without it.
5. Check that the three provisioned datasources report healthy and that
   alerting, the dashboards and search load.

## Logs

```bash
make logs                          # everything, from the container engine
make logs-api
make logs-shipper                  # why nothing is arriving
make logs-retention                # how long Elasticsearch keeps them. Run once
make logs-prune                    # delete the files on the volume
make logs-wipe CONFIRM=<database>  # this database's lines; ALL_DATABASES=1 every stream and file. What make wipe runs
```

Filebeat ships this project's processes to Elasticsearch, wherever they ran. A
container writes to the `logs` volume and a host command to `./logs`, and
Filebeat reads both into one data stream. `host.name` tells them apart.

The other containers (PostgreSQL, SeaweedFS, Redis, Elasticsearch, Phoenix,
Argilla, Grafana, Adminer and Filebeat) keep the `json-file` driver. Read them
with `make logs`.

Retention has two halves. `make logs-retention` ages what Elasticsearch holds.
`make logs-prune` ages the files. Nothing is deleted until the first has run.
Each process writes `{service}-{host}-{pid}.log`, so nothing else removes a
file.

[`telemetry/`](../telemetry/README.md) lists the field names.

## Backups

The archive (`make archive`) is a second chance after a deletion. It lives in
the same database and object store it protects. A backup is a copy of both
somewhere else.

```bash
make backup DIR=/backups/$(date +%F)
```

The command writes under `DIR`:

| Path | Content |
|---|---|
| `db/<name>.dump` | A `pg_dump -Fc` of each of four databases (the application's, SeaweedFS's, Phoenix's and Dagster's), taken through the postgres container |
| `s3/<bucket>/<key>` | Every object of the five buckets, read through the stack's S3 endpoint |
| `manifest.json` | The row count of every table of the application database, and the key, size and sha256 of every object and dump |

`make backup` never copies `.env`, `provider.env` or a certificate key. Store
those with the other secrets. `DIR` must hold no backup. Every folder and file
it writes, `DIR` included, is readable by its owner alone (700 and 600),
whatever the shell's umask, because the objects are every source document.

Argilla's database is left out, because its users table holds the owner's API
key in clear. `make backup DIR=... ARGILLA=1` adds it. Store that `DIR` as a
secret, and rotate `ARGILLA_API_KEY` if it leaks. Without it, the review
datasets come back from the database with `make review-push-*`. An answer not
yet pulled with `make review-pull-*` is not in the backup.

Stop the workers first (`podman compose ... stop parse-worker chunk-worker
extract-worker topic-worker question-worker assess-worker`, as step 2 of the
drill below does). `make backup` takes the dumps, then the objects, then the
row counts. A worker still writing makes them three moments, and the backup
then verifies with differences. A row dumped before an object was deleted has
no object in the backup. The command prints this warning before it starts and
does not refuse.

Copy `DIR` off the machine. A backup on the volume it protects is not a
backup.

### The restore drill

Run the drill on a scratch stack before it is needed, and again after any
change to the stores. It replaces the data of the stack it runs on.

1. Bring up a stack of the same version beside the first (see [A second stack
   beside the first](#a-second-stack-beside-the-first)), or reuse the same
   stack after `make down-volumes CONFIRM=all-volumes`, then `make up`.
2. Stop everything but postgres and seaweedfs, so that no connection holds a
   database. Use `docker compose` for docker. `ps` lists what else runs.

   ```bash
   podman compose --env-file configs/env/deployment.env --env-file .env stop api frontend parse-worker chunk-worker extract-worker topic-worker question-worker assess-worker dagster-webserver dagster-daemon phoenix argilla grafana
   ```

3. Restore one database: `make restore-backup DIR=/backups/<the directory>
   CONFIRM=<APP_DB_NAME>`. It refuses while a worker runs and unless `CONFIRM`
   names the database. It runs `pg_restore --clean --if-exists
   --single-transaction` as the superuser, for the application database only,
   and keeps the owners the dump carries (without them the application role
   cannot read its tables). It uploads the objects under that database's own
   prefix and checks the dump, the objects and every row count against the
   manifest. It exits 1 and names each difference. The buckets, the SeaweedFS
   filer, Phoenix, Dagster and Argilla are shared by every database on the
   stack, so the command leaves them, and every other database's objects, as
   they are.

   To put the whole stack back (the five databases and every database's
   objects, Argilla's only if the backup took it), run `make
   restore-backup-stack DIR=... CONFIRM=stack`. It rolls every database's
   objects, the filer's entries, the traces and the Dagster runs back to the
   backup's. It refuses while more than one application database exists on the
   server, unless `ALL_DATABASES=1`.
4. Run `make up`, then `make schema-status` (at the newest revision) and `make
   documents` (the documents the backup held). Open a document's page and a
   topic figure: the objects are read from the restored store.

A database upgraded to v0.5.2 holds its objects under bare keys until `make
s3-prefix` copies them under its prefix, and a backup taken before that holds
them bare. `make restore-backup` puts back and verifies the keys under the
database's prefix and the bare keys its rows name (its documents, its archived
documents and its `topics/<database>/` keys). Other bare keys belong to the
databases they were written for and come back only with `make
restore-backup-stack`. `make s3-prefix` never copies over an object the prefix
already holds. Bare objects are never deleted. They stay after `make delete`,
`make archive-purge` and `make wipe-all` until a person removes them from the
buckets, once every database has run `make s3-prefix`.

### What Phoenix keeps

Every trace holds the prompts a run sent, and every prompt contains a passage
of a source document. Phoenix keeps traces for ever unless told otherwise.
`make up` and `make dev` set its default trace retention policy to
`PHOENIX_TRACE_RETENTION_DAYS` (30 where unset, in
`configs/env/deployment.env`). `make phoenix-retention` sets it again after a
change and needs the stack up.

Phoenix applies the policy weekly, at 00:00 UTC on Sundays as Phoenix 20.3.0
ships it, so a trace can stay up to seven days past the limit. A failure to
set the policy is printed and the stack still starts, so read the output. A
policy of zero is refused, because Phoenix reads it as "never delete".

The cost log is the spend of record, so shortening the retention loses no
figure `make spend` reports.

## Failure

The next run of a stage fails a row that a worker died holding, and records
the reason. `retry` returns the row to the queue. No row can reach a state
that nothing can move it out of.

A stage's failure is never an HTTP 500. It is recorded against the row and
read back through `/{stage}/status`.

## Production host

On the production profile the host reaches a hosted provider, never a
container. The model stages (extraction, topics, questions, assessment) run on
the host through `make corpus-hosted`. The containers keep parsing and
chunking, which call no model, and the model workers stay stopped. Without
`HOST_RUNNER`, containers call Ollama, as the README says.

### The runbook

From a fresh clone:

1. Clone outside any synced folder, and keep the secrets where only the
   operator can read them (see [Keeping the secrets out of the
   checkout](#keeping-the-secrets-out-of-the-checkout)).
2. `cp .env.example .env`, then `make setup` to fill the passwords. The file
   ships the production split: `HOST_RUNNER=1`, the seven role models and
   `LLM_REASONING_EFFORT=none`, described in
   [configuration](configuration.md#the-production-split). Put the provider's
   credentials in `configs/env/provider.env`, which is not in git.
   `APP_DB_PASSWORD` must use only letters, digits, `-`, `_` and `.`, because
   the connection string is built from it as written. `make doctor` and `make
   corpus-hosted` refuse `@ / : # ? %` and name the setting.
3. `make install`, then `make docling-weights HOST=1`. `make install` sets up
   the host's virtualenv and the spaCy pipelines, which every host command and
   the model stages run in. It also fetches Docling's weights into the
   `models` volume that the parse worker reads. The worker has the Hub off and
   no route out, so a fresh volume fails every document. This needs the
   container engine and builds the image the first time. `make docling-weights
   HOST=1` fetches the same weights into the host's Hugging Face cache, which
   `make doctor`, the hosted run's preflight and a host drain read with the
   Hub off.
4. `make up`. With `HOST_RUNNER=1` it starts the services that no profile
   names: postgres, the object store, the API, the parse and chunk workers,
   the web page and Phoenix. The parse and chunk workers drain their queues,
   and `make corpus-hosted` waits for each to empty before the model stages.
   The model workers sit under the `local-models` profile and Dagster under
   `orchestrated`. This `make up` stops none of them. A worker left up from
   development calls Ollama, so `make doctor` and `make corpus-hosted` refuse
   while one runs and name the `compose stop` command that stops it. `make
   all`, `make pipeline`, `make auto` and the pipeline's routes refuse and
   name the host runner. A queue verb for a model stage still queues its rows,
   and its answer names the command that drains them.
5. `make schema`, which creates the tables. `make up` migrates nothing, and
   the first upload to an empty database fails without it.
6. `make doctor`. It checks the split and asks every model one question. It
   reads the Hugging Face cache with the Hub switched off and names any
   encoder (at its pinned commit) or Docling weight that is missing or holds
   no weights. On this profile that fails, as it does with `HF_HUB_OFFLINE=1`.
   `make corpus-hosted` checks it again before it detaches. Run the `poetry
   run hf download` line the doctor prints for a missing encoder where the Hub
   is reachable, as [configuration](configuration.md#pinning-the-encoders)
   says, then run `make doctor` again.
7. `make ingest DIR=<folder of PDFs>` loads a corpus from the host, one line a
   file, under the limits the Upload page has stored. The Upload page is for a
   few files: it refuses more than 20 files or 200 MB at once, and holds the
   selection in memory before it checks. One file with curl: `curl -H
   "X-API-Token: $API_TOKEN" -F file=@x.pdf http://localhost:8000/documents`.
8. `make corpus-hosted SPEND_CAP=50`. The command returns at once and the run
   continues detached. `logs/corpus-hosted.log` holds its output, and
   `state/corpus-hosted.pid` holds its process group, database and the
   leader's start time. `make corpus-hosted-stop` stops it. The run names the
   database it acts on and gives every drain that name and `HF_HUB_OFFLINE=1`.
   It counts spend across the drains in `state/corpus-spend-<database>.usd`
   (`SPEND_LEDGER`), one ledger a database, so `SPEND_CAP` is the cost of the
   whole run, not of each drain. The ledger holds the run's total and is
   rewritten after every priced call, so a drain killed outright leaves its
   spend counted. Every drain logs the split it resolved before its first row,
   and a role that resolves to an Ollama model stops the run before a model is
   asked.

   `state/` belongs to the run and is not a log folder. `make wipe
   CONFIRM=<database> ALL_DATABASES=1` and `make logs-prune` empty and delete
   files under `logs/` and leave `state/`, so a stopped run still resumes with
   its spend and a live one can still be stopped. Keep `state/` out of any
   clean-up while a run is recorded.
9. `make questions-export OUT=release.xlsx FILTER="--released"` and `make
   questions-export OUT=all.xlsx` when the run ends: the two workbooks.

### What a queue verb says on this profile

The Start button and `POST /{stage}/start` still queue rows. `retry`, `rerun`
and `reclaim` return rows, and `POST /assessment/enrol` enrols them. For a
model stage (extraction, topics, questions, assessment) the answer is 202 and
its detail names the command that drains the rows, `make corpus-hosted` or the
stage's own target, because no worker drains them on this profile. A release
that adds a stage ends its upgrade section with `make up`, which starts the
new worker or profile.

### A stale image

Each image bakes the hash of the lock it installed: `requirements.lock` for
the backend and the page, `requirements.txt` for Dagster, which installs the
ranges. Every container compares the hash at start with the checkout's own,
bind-mounted read-only. After a `git pull` or an edit that changed a lock,
`make up` starts nothing on the old packages. Each affected container logs
`run compose build, then make up`, waits ten minutes and exits, and its
restart policy tries again. `make down` or a stop ends the wait at once.
Rebuild, then `make up`:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
```

### Keeping the secrets out of the checkout

A checkout inside a synced folder (`~/Library/CloudStorage`, `OneDrive` or
`OneDrive - <organisation>`, `Dropbox` or `Dropbox (<team>)`, `Box Sync`,
iCloud Drive) is copied to the sync provider's servers and to every signed-in
device, `.env` and `provider.env` with it. Run the production profile from a
clone elsewhere:

1. `git clone` into a folder that no sync client watches, such as
   `~/srv/qa_generator` or `/srv/qa_generator`. `make doctor` warns when the
   checkout or the secrets file sits under a synced folder.
2. Move the secrets out of the checkout and name them. Put `.env` where only
   the operator can read it, for example `/etc/qa/secrets.env` with mode 600,
   and run every command with `ENV_FILE=/etc/qa/secrets.env` or export it
   once. Host commands source that file and compose is handed it, so nothing
   else changes. The path must not contain spaces. `configs/env/provider.env`
   also holds credentials and stays out of git. Keep it out of any folder that
   is backed up.
3. Rotate every key after the move. The old `.env` sat in a synced folder, so
   the sync service has read its passwords, `PHOENIX_ADMIN_SECRET`,
   `GRAFANA_SECRET_KEY`, the Argilla key and the provider's credentials. Set
   new ones (`make setup` fills placeholders, and the provider's key is
   rotated in its own console), then delete the old file and the synced
   folder's copy of the checkout.
4. A backup of a database or an object store holds none of these. Leave
   `.env`, `ENV_FILE`, `provider.env` and the certificate keys under `certs/`
   out of it.

Nothing in the repository moves a checkout.

### Upgrading a deployment

`make upgrade` takes the stack to the code in the checkout, in the order that
works:

1. Check that the container engine has the room (`UPGRADE_FREE_GB`, 20 by
   default, read in the podman VM where there is one).
2. Build.
3. Prune the images the build orphaned.
4. Stop the workers.
5. Run `make schema`.
6. Start the stack with `make up`.

It stops at the first step that fails, so a build that did not finish never
reaches the migration. Run it after `git pull` and before `make
corpus-hosted`. An upgrade section below that says to rebuild and run `make
up` means this command.

### Profiles

With no profile named, compose starts eleven services: the database, the
object store (master, two volumes, filer, S3 gateway), the API, the parse and
chunk workers, the page and Phoenix. The rest sit under a profile.

| Profile | Services | Started by |
|---|---|---|
| `local-models` | the extract, topic, question and assess workers | development `make up`; never on the production profile, where the host runner drains them |
| `orchestrated` | Dagster's webserver and daemon | development `make up`; never on the production profile |
| `review` | Argilla, Redis and Elasticsearch | `COMPOSE_PROFILES=review` in `.env` |
| `logs` | Filebeat and Grafana, which need `review` for the Elasticsearch they use | `COMPOSE_PROFILES=review,logs` |
| `tools` | Adminer | `COMPOSE_PROFILES=tools` |

`make up` enables every profile unless `HOST_RUNNER` is set. On the production
profile it enables what `COMPOSE_PROFILES` in `.env` names, except the first
two. Every other `make` target sees all profiles, so `make down` stops a
service whichever profile started it. `make wipe` skips the Argilla,
Elasticsearch and Dagster steps of a service that is not running, says so, and
still empties the log files. `make doctor` does not check the containers'
model where the workers are stopped.

### After a stop

A drain that stopped itself, because the model could not be reached or the cap
was reached, exits 75 and gives its rows back. A failed row exits 3. Either
exit stops the run before the next stage.

| Exit | Meaning |
|---|---|
| 0 | The run finished |
| 3 | A row failed, or the start was refused |
| 75 | The drain stopped: `SPEND_CAP`, a model that cannot be reached, or a signal |

A run that ends without finishing keeps its pid file. `make corpus-hosted`
after a stop, a crash or a kill resumes it: it finds the pid file that nobody
holds, returns every stage's failed rows to the queue and runs the chain again
on the database the file records. The spend so far still counts against
`SPEND_CAP`. Only a run that finished, or `make corpus-hosted RESET=1`, makes
the next run fresh with its count started again. A start that names another
database than a stopped run's is refused, because that run's failed rows and
spend belong to its own database.

A second `make corpus-hosted` while the first runs is refused. The pid file
records the run's process group and the start time of the make leading it (in
C locale and UTC, so a stop from a shell in another locale or zone finds it).
A run is going on while that group's leader is alive with that start time, or,
with the leader killed, while a drain of it is left. A group number that
another process took since (after a reboot or a wrap of the pid count) is not
the run: the stop signals nothing of it and a start resumes. Each database has
its own ledger, so a run on another database never touches this one's. A `make
corpus` on the same database refuses beside the hosted run, and refuses while
a stopped run is recorded unless it resumes with `RESUME=1`, because a fresh
run would start the spend again.

A resume returns every stage's failed rows to the queue first. A row that
fails every time (a document that parsing refuses for its language, an empty
or broken PDF) therefore stops every resume at the same stage with exit 3.
Read why before starting again: `logs/corpus-hosted.log` names each failed row
and its error, and the stage's page lists them. Then fix the row or remove it:

- `make delete SHA=<sha256> CONFIRM=<database>` removes a document that cannot
  be processed.
- Once the cause is fixed, the stage's `-retry` target returns that row alone:
  `make parse-retry SHA=<sha256>`, `make extract-retry PASSAGE=<id>`.
- `make corpus-hosted RESET=1` starts a fresh run. It retries no failed row
  and starts the spend count again.

`make corpus-hosted-stop` sends TERM to the whole group. The drain in hand
finishes its row, or gives it back, and exits 75. Whatever is left is killed
after 300 seconds, a model stage's grace plus its give-back. The spend ledger
and the pid file are kept, so the next `make corpus-hosted` resumes the run.

To have a supervisor restart the run, run `scripts/corpus-hosted.sh`, the
runner that `make corpus-hosted` detaches, in the foreground. It takes `make
corpus`'s command line and keeps the same pid file and ledger. It exits with
the code of the stage that ended the run, not make's 2: 0 when the run
finished, 75 when it stopped (at `SPEND_CAP`, on a model that cannot be
reached, or on a signal, which it passes to the whole run), 3 when rows failed
or the start was refused, and anything else for a crash. Only a crash is
restarted. A stop at the cap, restarted, would pay every model drain's
preflight again for nothing, and failed rows need reading first.

The runner resumes an unfinished run by itself, so neither unit below names
`RESUME=1`. Every start proves what `make corpus-hosted` proves (`make
corpus-preflight`: the production profile, no model worker or Dagster
container up, the split, the password and the cache) and refuses with 3 where
it fails. A database that is not given is resolved as `make corpus` resolves
it, and recorded. The runner's `PATH` must reach `make`, `poetry` and the
container engine. Give `ENV_FILE` where the secrets live outside the checkout.

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

`KillMode=mixed` sends the stop to the runner alone, which passes it to the
run once. `TimeoutStopSec` outlasts the runner's 300 seconds.

```xml
<!-- /Library/LaunchDaemons/qa.corpus.plist: the same on macOS. A daemon runs
     without anybody logged in. launchd restarts on any code but 0, so the
     runner is told to turn a stop into 0. -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>qa.corpus</string>
  <key>UserName</key><string>qa</string>
  <key>WorkingDirectory</key><string>/Users/qa/srv/qa_generator</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/Users/qa/.local/bin:/opt/podman/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/qa/srv/qa_generator/scripts/corpus-hosted.sh</string>
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

A restart by either unit resumes the run with its ledger, so the cap holds
across restarts. `make corpus-hosted RESET=1`, or a fresh `make corpus`
without `RESUME=1`, starts a run's count again. A unit enabled at boot starts
a fresh run after one that finished, which draws the release again at the
verifier's cost. Disable the unit once the run is done.

## Upgrading the schema on a stack with data

`make schema` applies each revision in a transaction of its own. A revision
that cannot get its lock within 5 seconds fails with the lock timeout instead
of waiting, because a DDL statement queues behind any open transaction on its
table and every query behind it queues in turn. A statement may run 10
minutes. When one fails, find what holds the table (a drain, a worker, a long
`make` command), stop it and run `make schema` again. The revisions already
applied stay applied.

Order:

1. Stop the stage workers and the host drains.
2. Back up with `make backup` (see [Backups](#backups)).
3. `make schema`.
4. Build the images, then `make up`.

A revision that adds a CHECK adds it `NOT VALID` and validates it in a
revision of its own. A backfill of many rows runs in batches outside the DDL
transaction. `backend/database/README.md` has the rule.

## Production deployment

This section lists what a production deployment holds, and the conditions
under which known open items stay out of the way. It covers about ten times
the reviewed build: 300 PDFs and 20,000 passages, German and English. The
review measured 30 PDFs and 1,973 passages.

Each line names its item by the review's number (`C-` and three digits, as
`docs/bugs.md` gives them). A condition that a release fixes leaves the list
and appears, with its fix, in that release's upgrade notes ([Upgrading to
v0.5.2](#upgrading-to-v052) lists the latest). The settings are in
[configuration](configuration.md#production-settings). [The
runbook](#the-runbook) is how a fresh clone reaches the deployment.

### The model split

- The measured split (C-051) ships in `.env.example`, and
  [configuration](configuration.md#the-production-split) has the table. The
  writer is `azure/gpt-5.6-sol` at `LLM_REASONING_EFFORT=none`. Extraction and
  phrasing use `azure/gpt-5.4`, digests and the judge use `azure/gpt-4o`, and
  the verifier and topic naming use `azure/gpt-4.1`.
- Every drain logs the split it resolved before its first row. With
  `HOST_RUNNER=1`, a drain and `make doctor` refuse a role that resolves to an
  Ollama model (C-006, C-013).
- Every role uses one endpoint (C-366, see the table below).

### Settings

- The model stages run on the host (C-006): `HOST_RUNNER=1`, `make
  corpus-hosted` and the model workers stopped. A run refuses to start while a
  model worker or a Dagster container is up (`make corpus-preflight`). The
  orchestrated path is not part of this profile (C-073): `make all`, `make
  pipeline`, `make auto` and the pipeline's routes refuse and name the host
  runner.
- The judge and the provider belong to the host (C-006). The host runner reads
  `ASSESSMENT_JUDGE_MODEL` from `.env` and the provider's credentials from
  `configs/env/provider.env`. `make doctor` refuses an unset judge while
  `ASSESSMENT_ENABLED` is true. The Assessment page shows the containers'
  judge, `ASSESSMENT_JUDGE_CONTAINER_MODEL`, so on this profile it says the
  next run judges nothing. That line describes the stopped workers, not the
  host run.
- The model cache is filled once and read offline (C-072, C-117). Fill it
  where the Hub is reachable, as [Pinning the
  encoders](configuration.md#pinning-the-encoders) says. `make corpus-hosted`
  then runs every drain with `HF_HUB_OFFLINE=1` and, before it detaches,
  refuses a cache that lacks an encoder at its pinned commit or Docling's
  weights. Point `DOCLING_ARTIFACTS_PATH` at the prefetched parser weights
  where they are not in the cache.
- A spend cap (C-091): `make corpus-hosted SPEND_CAP=<USD>`, counted across
  the drains of the run. With a cap set, a drain refuses a model that litellm
  cannot price (C-219).
- Every published port stays on 127.0.0.1, and one operator uses the host
  (C-085, see the table below).
- Entity and temporal questions stay off (C-176, C-217). Both carry weight 0
  in `QUESTIONS_TYPE_MIX` and `QUESTIONS_RELEASE_TYPES`. No defect was
  measured for entity questions. A corpus with no periods answers temporal
  questions with comparisons that wear the name. Calibrate each on the
  production corpus before giving it a weight. A corpus of releases, versions
  or reporting periods is where temporal questions may earn one.

### Resources

- Postgres is sized as shipped, and its probe time is watched (C-011).
  `configs/env/deployment.env` ships the production row of [Sizing
  Postgres](#sizing-postgres). The measure is the 10x load test that `make
  test-perf` runs: a dedup probe and a fact write within twice their time at
  the reviewed build's size. On the CI runner the single-pass probe p95 ran
  2.15x in the first two runs (4.4 to 9.5 ms and 4.5 to 9.7 ms) and 5.47x to
  7.80x in the last three (up to 32.8 ms), against the 2x bar. All five read
  the same plan and a single-pass median of 6.0 to 6.9 ms at 10x: the slowest
  probe in twenty moved. The warm probe held at 1.00x to 1.29x and the write
  at 1.21x to 1.66x. The sizing ships with that limit by decision, because the
  database is about 2% of a drain's time at ten times the build: about 0.13 s
  a passage at the medians and about 0.5 s with every probe and write at the
  slowest run's p95. Watch the probe time as the corpus grows. If it climbs,
  raise `POSTGRES_MEMORY` and `POSTGRES_SHARED_BUFFERS` to the table's next
  row.
- The podman VM's memory is at least the sum of the limits of the services it
  runs ([Memory](#memory)). The eleven services of the production profile come
  to about 15 GiB at the shipped sizes: PostgreSQL and the parse worker 4 each
  and the chunk worker 3. Every added profile adds its own.
- Free disk before every build: `make upgrade` refuses below `UPGRADE_FREE_GB`
  (20) in the engine and prunes what a build orphans. The margin comes from
  the review and is not a measured bound.
- At most two drains of a model stage a database, and at most two of
  extraction (C-082, C-026, see the table below).
- Time and spend (C-084): `make estimate` gives both for the rows still to do.
  [Sizing a corpus](#sizing-a-corpus) works the production corpus: USD 725 and
  81 hours under `make corpus-hosted`, which runs one drain a stage. Two
  drains of extraction and of questions would make it 43 hours, but no
  documented path runs a second drain beside a hosted run, and a drain started
  by hand does not count against the run's `SPEND_CAP`. The questions grow
  with `TOPIC_NUM_TOPICS`.

### Backups

- Run `make backup` before every upgrade and every wipe (C-003), copy it off
  the machine, and run [the restore drill](#the-restore-drill) on a scratch
  stack before it is needed. A backup leaves Argilla's database out unless
  `ARGILLA=1`, because that dump holds a key in clear.
- The archive bucket is the only copy of a deleted row's objects. Purge it per
  database on a cadence, after a backup ([Deleting things](#deleting-things)).

### Monitoring

- Alert on a non-zero exit (C-009, C-091). A drain exits 3 when a row failed
  and 75 when it stopped itself (an outage, `SPEND_CAP`, a model that finds
  nothing, a signal). `scripts/corpus-hosted.sh` exits with the code of the
  stage that ended the run ([After a stop](#after-a-stop)).
- Every log line carries `db` (C-005). Phoenix projects, review datasets and
  Dagster runs carry the database's name.
- Phoenix traces hold every passage a prompt sent, so set a retention (C-103):
  `PHOENIX_TRACE_RETENTION_DAYS` in `configs/env/deployment.env`, applied by
  `make up`. Read `make up`'s output: a failure to set it is printed and the
  stack starts anyway.
- The release draw takes 10.6 s at 21,750 accepted questions (C-089), the
  reviewed build's pool ten times over.

### Before the first production release

- Label a sample. The quality figures were measured on football regulations
  and on the shop calibration corpus, and tables, the core of bank and shop
  material, read worst. Label 60 released rows per language blind under the
  rubric, with the table slice and the two-passage slice read apart. Use the
  release only if it meets the review's bar: usable at least 0.723, invalid at
  most 3.4 per 60. This takes about two hours of labelling and no model call.
- Read the table slice apart until C-097 and C-282 ship. A table continued on
  the next page joins its table (C-121), but a wrong section path (C-097) and
  a second tier joined to the row above (C-282) are open.
- Report what the reviewed build measured, and report the release as a whole
  or each slice with its own share:
  - Released two-passage questions were 0.548 usable (n 126) and accepted hard
    questions 0.514 (n 70), against 0.841 for the release. Never report either
    slice alone as the system's quality.
  - 13 of the 128 released unanswerable questions are answered by the corpus
    and 11 are invalid, mostly the same rows. A refusal evaluation built on
    them drops or rechecks those rows, or about one expected refusal in ten is
    wrong.
  - The automatic judge agrees with the labels at kappa 0.18, close to chance.
    Quality figures need labels, not the judge.

### The conditions that still hold

| Item | Condition | What lifts it |
|---|---|---|
| C-026 | At most two `extract-worker` replicas, or two extraction drains, a database: `--scale extract-worker=2`. The store's duplicate lock was measured with two drains side by side (0.57 and 0.54 of one drain's time, no claim kept twice), and more are not measured | A measurement of three or more drains on a copy |
| C-082 | At most two model drains a database on the current Azure quota: six drains lost 3 of 10 topics to the token rate limit and two lost none. A drain waits out a rate limit without spending an attempt | A larger quota, measured before the drains are raised |
| C-085 | Every published port stays on 127.0.0.1, and one operator uses the host. `API_TOKEN` guards the API's writes but is shared, and the pages have no login. Serving the stack to a team, or binding another interface, makes this a blocker | A login on the pages and the API |
| C-366 | Every role model on one endpoint, `LLM_BASE_URL`. A split across Azure resources needs a gateway in front of them that routes by model id | An address per role (deferred: the measured split fits one resource) |
| C-106 | Ingest only documents the corpus owner authored or controls, with no user reviews or third-party submissions. A document's text reaches every prompt as it is, so an instruction planted in it is read as one | Fencing the material in every prompt. It was tried in v0.5.2 and withdrawn: fenced extraction narrowed 10 of 60 facts against 7 unfenced, over the bar of 9 |
| C-114 | Load bulk corpora through the host with `make ingest DIR=`. The Upload page takes a few files at a time: it refuses more than 20 files or 200 MB, but Streamlit uploads every picked file into its 1 GB process before that check, so a large selection can kill it. The page says so above its picker | A check before the upload, which Streamlit's uploader cannot make |
| C-054 | After a deletion through the pages or the API, run `make extract-dedup`. Every deletion says how many duplicate refusals lost their twin, and on this profile no extraction worker runs to give them back. `make delete` and `make delete-derived` run it themselves | A replay that the host runner makes after a deletion |
| C-066 | Export a large corpus with `make questions-export` on the host, never through the pages. The API builds the whole workbook in its 512 MB, which failed past about 13,000 questions in v0.5.1. The workbook has more columns since, and the bound is not measured again | The streaming export, deferred to v0.5.3 |
| C-029 | Report the difficulty band as retrieval spread, never as hardness, and leave `QUESTIONS_RELEASE_DIFFICULTY` unset: equal thirds drew nearly every multi-passage question, where the welds sit. The workbook titles the column Retrieval spread | A grading of how hard a question is to answer, not built |
| C-031 | Leave distant-from-document out of per-category reports: most of its released rows use the document's words | A per-question reading of how far a row's words are from its evidence, calibrated on two corpora (deferred) |
| C-052 | Before a release from price lists or fee schedules, read by hand the questions whose explanation states a space-grouped amount (`12 500 €`): a wrong total there can still pass the explanation check. The figure reader takes such an amount as one figure with a marked currency, a price dash, a no-break space or any currency sign after it | The explanation half of the fix, which needs the arithmetic check's model call to tell a right total from a wrong one |
| C-056 | Before ingest, count the image-only PDFs: a scanned document is refused, and an image-only page only draws a warning | OCR (C-083). The reworded page count of C-127 was withdrawn in v0.5.2 |
| C-083 | OCR stays off. Pillow 13.0.0 fixes the advisories that were the other reason | A measured OCR pass on the production corpus |
| C-140 | Before production, measure the text nested in pictures on the shop calibration database (`qa_cal_shop`): banners and infographics in bank or shop material may carry statements, which reach no passage | A filter that tells a statement from a diagram label. The clause filter tried in v0.5.2 was withdrawn: 5 of 26 changed passages read worse |
| C-266 | Before production, measure on the shop calibration database the questions drawn from imprint, hotline and contact passages | A passage gate on contact shapes, with a threshold calibrated on the shop corpus (deferred) |
| C-186 | Before ingest, check the refusal count of a first batch: a PDF whose header follows a few leading bytes, as some document-management exports write them, is refused as unknown type | Reading the signature within the first kilobyte (deferred) |
| C-278 | Before ingest, compare the corpus's widest table rows with the chunk's token budget (`EMBEDDING_MAX_TOKENS` less the embedder's own tokens). A longer row is cut mid-cell and lands in no grid. Ship the fix first if any row exceeds the budget | Keeping a row whole in one passage (deferred) |
| C-295 | Choose the embedding model before production, and change it only through a migration and a full re-embed. `EMBEDDING_MODEL` and its commit are fixed, so no page or stored row moves them, but an edit of `backend.env` and a restart would mix two models' vectors, which nothing checks | A guard that refuses vectors of another model, with the migration and re-embed written down |
| C-419 | Check any tracked-change export in the corpus before ingest: only a drawn horizontal strike is read as struck-through | A strike reading for tracked changes, with a fixture first (deferred) |
| C-245 | Leave `EXTRACTION_DUPLICATE_COSINE` at its shipped value: 0 also stops writing passage embeddings | Building the embedder whatever the threshold (deferred) |
| C-424 | Leave `QA_MODEL` empty, as it ships, until an encoder is calibrated: the first candidate the settings file names cannot load under transformers 5 | A calibration of one encoder |
| C-297 | Build the production images once, record their digests, and rebuild only on purpose: the Dagster image installs ranges, installs are not hash-checked and base images are named by tag. A container already refuses to start on a lock its image was not built from (C-010) | Locked and hash-checked installs, images by digest (deferred) |
| C-162 | No schema downgrade past v0.4.2: rolling back `733a3eadef7c` archives every rubric score, and a restore of that deletion fails | Skipping the archive in that downgrade (deferred) |
| C-200 | Leave the nightly schedule off: it ignores Stop and `INGESTION_OPEN`. The production profile runs no Dagster at all | A schedule that skips after a cancelled run (deferred) |

## Upgrading

Each section below lists the steps from the release before it, newest first.
Unless a section says otherwise, an upgrade is `make upgrade` (see [Upgrading
a deployment](#upgrading-a-deployment)): rebuild the images and run `make up`,
which `make upgrade` does in order. On a host checkout, run `poetry install`
when `poetry.lock` changed. A build made from scratch on a new database needs
none of the reruns. A stack on v0.3.12 follows the v0.4.0 or v0.5.0 section
instead of the v0.3.13 to v0.3.36 sections.

A rerun brings stored data up to what a release reads differently. Run only
the reruns the corpus needs. Each `make *-rerun` drains on the host and
refuses while the stage's container worker runs. To rerun with the container
workers, use the stage's page or `POST /{stage}/rerun?confirm=true`.

## Upgrading to v0.5.2

v0.5.2 is the fix release after the final review of v0.5.1. It covers data
safety, the hosted model path, drains that stop and say why, scale, and the
parse, fact and question fixes that passed their bars. `docs/bugs.md` lists
each fix with its measure, what was withdrawn and the known limits. A build
made from scratch needs only steps 1 and 2.

### 1. Pull, code, host environment and images

Before `git pull`, pull the verdicts of the review datasets, because their
names gain the database in this release (step 6): `make review-pull-facts`,
`make review-pull-topics`, `make review-pull-questions`.

If `configs/env/backend.env` holds local edits, set them aside first. This
release removes the role models from that file and renames `TOPIC_MIN_WEIGHT`.
The role models move into `.env`, `TOPIC_MIN_WEIGHT` goes (step 3), and
`SPEND_CAP` is given on the command line.

```bash
git pull
make setup        # once .env holds the new lines below
podman compose --env-file configs/env/deployment.env --env-file .env stop parse-worker chunk-worker extract-worker topic-worker question-worker assess-worker
make backup DIR=/backups/$(date +%F)
poetry install --with llm,nlp,data,storage,api,pipeline,viz,observability,dev
make upgrade
```

`.env` needs the lines that `.env.example` carries and `.env` lacks. `make
setup` fills placeholders and nothing else.

- `API_TOKEN=change_me_api_token` is required: compose refuses to start
  without it.
- `HOST_RUNNER` is optional and reads 0 (development) where unset.
- A role model left unset follows `LLM_MODEL`.
- With `LLM_REASONING_EFFORT` unset, each model keeps its own default effort.
  The shipped reasoning writer then thinks.

`make backup` is new in this release ([Backups](#backups)). Copy its `DIR` off
the machine. On the production profile, fill the host's model cache once where
the Hub is reachable: `make docling-weights HOST=1` for Docling's weights, and
each encoder at its pinned commit, which `make doctor` names with the command
that fetches it.

- Docling goes from 2.141.0 to 2.142.1 (docling-core 2.104.0, docling-parse
  7.23.0, doclang 0.8.0), on the host and in the API image. No re-parse is
  needed. On the 30 football and 50 shop PDFs it changed only the parentheses
  of the link URLs in 9 shop passages, which it percent-encodes.
- Pillow goes from 12.3.0 to 13.0.0, which fixes the advisories accepted
  against 12.3.0. `configs/audit-accepted.txt` lists what `make audit` still
  accepts: filelock 3.32.7's three advisories until 2026-11-30, because
  litellm 1.106.2 requires filelock below 4.0 and the fix is 4.2.1. On that
  date the audit fails until the entry is read again.
- A container refuses a stale image ([A stale image](#a-stale-image)). After a
  pull that moved a lock, build before `make up`, as `make upgrade` does.
- Keep the secrets out of a synced folder. `make doctor` warns when the
  checkout or `ENV_FILE` sits in one. [Keeping the secrets out of the
  checkout](#keeping-the-secrets-out-of-the-checkout) says how to move them
  and why to rotate every key.

### 2. Three migrations, in order

`make upgrade` runs `make schema`, and `make schema-status` shows what it will
do. Each revision runs in a transaction of its own under a 5-second lock
timeout. A revision that waits on a table a drain holds fails instead of
queueing every worker behind it: stop what holds the table and run `make
schema` again. The head before this release is `20e31b1656f7`.

| Revision | What it does |
|---|---|
| `860d56b11032` | Adds `facts.language`, filled from each fact's first citation, then analyses `facts` so the first dedup probe uses the vector index (C-090) |
| `7a41c9d2e8b0` | Adds `facts.twin_id`, a foreign key set NULL when the twin goes, and its index. It is NULL on every stored refusal, so the first dedup replay reads each duplicate refusal once (C-068) |
| `4a7c2e91d3b8` | Adds `questions.source_digests` and three BEFORE DELETE triggers (on `passages`, `facts` and `fact_passages`) that stamp it. The trigger that deleted a question whose last fact went now rejects it as `source_changed` and keeps it (C-001) |

`make schema-down CONFIRM=<database>` removes each revision again and drops
what it added.

### 3. Settings

- `TOPIC_MIN_WEIGHT` is replaced by `TOPIC_RELATIVE_WEIGHT` (0.5). A
  membership is kept when it is at least that share of the passage's
  strongest. The old absolute floor kept weak memberships that bound unrelated
  passages (3.7 topics a passage on the reviewed build). A value left in an
  environment file is ignored. A row stored under the old name stops the topic
  stage's build and `make doctor`, naming the new setting and the `DELETE`
  that removes the row. Refit afterwards (step 5).
- `TOPIC_NUM_TOPICS` ships at 300 a language (was 40), and topics are named 25
  to a call. A corpus past 40 topics a language fits more topics, and the
  questions grow with them. `make estimate` says by how much.
- `MAX_FILE_SIZE_MB` is bounded at 150, meant as what the API's 512 MB holds
  whole (not measured). A larger stored value is refused: an upload answers
  503 `stored_setting_refused`, `make ingest` exits 3 and `make doctor` fails,
  each naming the setting. Store 150 or less, or delete the row.
- `PARSING_MAX_PAGES` is new (180; 0 is no limit). A longer document is
  refused before conversion, naming its pages. Before this setting the parse
  worker ran out of its 4 GB and was killed holding its claim. `make
  parse-retry` returns the document after a split.
- `SPEND_CAP` is new, in USD, and is given on a drain's command line (`make
  corpus-hosted SPEND_CAP=` among them). It stops a drain, the bridge pass,
  the release draw and the rejudge with exit 75 before the next row past it.
  Under `make corpus-hosted` it counts the whole run through a spend ledger
  per database (`SPEND_LEDGER`). With it set, a drain refuses a model that
  litellm cannot price.
- `EMBEDDING_MODEL`, `NLI_MODEL` and `QA_MODEL` are fixed, with their commits
  beside them in `backend.env` (`EMBEDDING_MODEL_REVISION`,
  `NLI_MODEL_REVISION`, `QA_MODEL_REVISION`). A model id and its commit change
  together, in the file. A row stored for one of the three ids stops every
  stage's build, naming its pin and the `DELETE` that removes it.
  `DOCLING_ARTIFACTS_PATH` is fixed as well, so a stored override of any of
  the four stops applying.
- `API_TOKEN` is new, in `.env`. Every write to the API and every read of its
  settings carries it as `X-API-Token`. The pages, a Redo's confirmation and
  force, the orchestrator and the make targets send it. A client written
  separately must send it too, or the API answers 401.
- `HOST_RUNNER` is new, in `.env`. `1` selects the production profile: the
  model stages run on the host through `make corpus-hosted`, the model workers
  and Dagster stay stopped, and a run refuses to start while one of them is up
  ([Production host](#production-host)). Unset, development runs as before.
- `ENV_FILE` is new. It names the secrets file that every host command reads
  and compose is handed, `.env` unless set.
- The role models are in `.env` only. `backend.env` names none, and
  `.env.example` ships the production split.
- `LITELLM_LOCAL_MODEL_COST_MAP=true` is committed in `backend.env`, so prices
  and the list of models sent no reasoning effort follow the installed litellm
  and move only with its lock.
- `POSTGRES_*` are new in `deployment.env` and size the server for the
  production corpus: 4 CPUs and 4 GB (was 1 CPU and 512 MB). See [Sizing
  Postgres](#sizing-postgres). The VM needs the room, because the memory
  limits add up to about 33 GiB with every profile on.
- `PHOENIX_TRACE_RETENTION_DAYS` is new in `deployment.env` (30). `make up`
  sets Phoenix's default trace retention to it.

### 4. Prompts and model calls

- Writer prompt 29 becomes 32. Version 32 tells every writer that the reader
  never sees the passage, and tells an answerable writer to put the case that
  makes its key the only answer into the question. Versions 30 and 31 were
  never released.
- Verifier 12 becomes 15, for the settles reading of a why-question over a
  bare rule. Phrasing 4 becomes 5, for the self-contained judge's definite
  sets.
- Unchanged: atomic extraction 12, repair-1, digest 5, bridge prompt 6,
  `verifier: stated` 1, assessment template 4, topic naming 3.
- Stored rows keep the version they were written under. Only `make
  questions-rejudge` reads one. Its first run after the upgrade asks again
  about every stored accepted unanswerable question: one `settles` reading
  each, and a second where the cited passages are silent and the probe is on.
- Added calls: a derived question citing two passages gets the parts reading
  (one verifier call). Topics are named 25 to a call, so a language of more
  than 25 topics makes more, smaller naming calls. The digest pass of step 5
  makes one digest call a passage, when run.

### 5. Reruns, in order

None of these is needed to start v0.5.2. A rerun without `SHA` refuses unless
`CONFIRM` names the database. A re-chunk or re-extraction over questions
refuses unless `FORCE=1`, naming how many released, accepted and reviewed
questions rest on what it would replace. Those questions are rejected as
`source_changed` and kept, never deleted.

| Step | Command | Needed because of |
|---|---|---|
| Parse | `make parse-rerun CONFIRM=<database>` | The parse fixes: a document in a language no configured model names is refused, naming it (C-008); titles (C-096); hidden text dropped (C-107); low-confidence pages and interleaved columns named (C-109, C-426). Docling 2.142.1 alone needs no rerun |
| Chunk | `make chunk-rerun CONFIRM=<database> FORCE=1` | The passage fixes: clauses a bookmark pass made headings (C-007), tables continued on the next page (C-121), running items, change boxes and letterheads (C-187, C-230, C-368). On the reviewed build it changes 108 passages of 9 documents. On the shop corpus it changes none |
| Extract the new passages | `make extract-start`, then `make extract` | The passages the re-chunk made have no facts yet. Only those reach the model |
| Judge facts again | `make extract-revalidate` | The fact checks (C-019, C-020, C-021, C-033, C-129, C-416). No model call. It writes only the facts whose verdict changed, and a second run writes nothing |
| Digest | `make extract-digests` | The digest floor of 500 characters and the floor's count of list items (C-057, C-098): passages above the floor that hold no digest get one. |
| Refit topics | `make topics-discover` | `TOPIC_RELATIVE_WEIGHT` (C-095). Questions are dealt from memberships, which the old floor kept. A new topic that is an old generated one and gained no passage stays generated. The next `make questions` asks about the others |
| Questions already stored | `make questions-reverify` | Holds every stored question to its facts after the steps above, and rejects one whose facts went or do not hold. It never gives a rejected question back, so the gates this release loosens (C-144, C-188) keep only what is written from now on. `make questions-rerun` writes every topic again, at the writer's cost |
| Ask unanswerables again | `make questions-rejudge` | Verifier 15 (C-022), as step 4 says |
| Redraw the release | `make questions-balance` | The rows rejected above leave the release. The draw is the same on the reviewed build and takes seconds at ten times its size (C-089) |
| Export again | `make questions-export` | The workbook titles the band Retrieval spread and gives each row its earlier turns and its source. Its Summary names the judge and counts the documents and passages that no accepted question of the export reaches (C-023, C-029, C-102, C-135). Export a large corpus with this command, never through the pages (C-066) |
| Copy objects under the database's name | `make s3-prefix` | Object keys carry the database (C-004). A bare key from before is still read, but only a copy under the database's prefix is safe from another database's delete or purge. Run it once per database that used the store |

### 6. What else changes

- Phoenix, Argilla, logs and Dagster carry the database: projects are named
  `<name>__<database>`, every log line carries `db`, and a wipe takes only its
  own database's. Items filed before belong to no database and are taken only
  with `ALL_DATABASES=1`.
- The golden sets are named `<name>__<database>` too. Upload them again under
  their database's name with `make eval-upload` and `make eval-phrasing`. The
  old ones are deleted only with `make phoenix-purge ALL_DATABASES=1
  CONFIRM=<database>`, which takes every database's projects with them.
- The review datasets carry the database in Argilla. A dataset pushed under
  the bare name stays where it is. With the verdicts pulled before the upgrade
  (step 1), push again with `make review-push-*`.
- Destructive targets ask for the database. `schema-down`, `schema-reset`,
  `wipe`, `delete`, `delete-derived`, `topics-delete`, an unnarrowed
  `*-rerun`, and `archive-purge` with `TABLE`, `ALL` or `DAYS` refuse unless
  `CONFIRM=<database>` is on the command line. A value exported in the shell
  does not count. `make down-volumes`, which deletes every database's volumes,
  needs `CONFIRM=all-volumes`, and `make restore-backup-stack` needs
  `CONFIRM=stack`. `make restore-documents AT=` restores a deletion and puts
  back only the deletions it names.
- A deletion takes the questions on what it removes. A question on a fact the
  deletion removes goes, and so does a question written from two documents
  when either is deleted. A fact that another document also cites stays, with
  its question. The documents stamped on a question
  (`questions.source_digests`) find a question that a rerun left with no fact.
  Every deletion ends by saying how many duplicate refusals lost their twin.
  The extraction worker gives them back when its queue is empty, or `make
  extract-dedup` does where no worker runs.
- The first empty extraction queue replays every duplicate refusal, once.
  `facts.twin_id` is NULL on every refusal stored before the upgrade (step 2),
  and NULL marks a refusal whose twin went. The first time an extraction drain
  finds its queue empty (a worker's poll or the end of a host `make extract`),
  it re-decides each of them against the facts stored now. A refusal that
  repeats no stored fact any more is given back, an outline refused as a twin
  of its own passage's summary among them (C-137), and its passage's facts are
  judged and capped again. No model is called. Later replays read only the
  refusals that a deletion or a rerun leaves without a twin.
- The first `make up` sets a trace retention for every database on the stack.
  Phoenix's default policy becomes `PHOENIX_TRACE_RETENTION_DAYS` (30) days
  for every project, and its next run deletes the older spans, among them
  those that a reconciliation of Phoenix's cost against `make spend` reads
  ([What the model costs](#what-the-model-costs)). Reconcile first, or raise
  the value in `deployment.env` before that `make up`.
- Drains exit with a reason: 0 done, 3 a row failed, 75 stopped (an outage,
  `SPEND_CAP`, a model that finds nothing, a signal). `make corpus` stops at
  the first non-zero exit, waits only for the parse and chunk workers, and
  refuses beside a model worker or a hosted run of its database. On the
  production profile it runs as `make corpus-hosted`, which a systemd unit or
  a launchd daemon can supervise. `RESET=1` starts a stopped run afresh, and
  `RESET=0` or nothing resumes it ([After a stop](#after-a-stop)).
- Two extraction drains may run side by side, and no more
  ([Scaling](#scaling)).
- The conditions that still hold are in [Production
  deployment](#production-deployment). The table below lists those this
  release lifts.

### 7. Deployment conditions this release lifts

Each fix ships in v0.5.2, so each condition has left [Production
deployment](#production-deployment).

| Item | The condition was | What lifts it |
|---|---|---|
| C-001 | Do not apply v0.5.1's lower digest floor to stored data | A re-chunk or re-extraction keeps the facts and passages that come back identical and rejects the questions on a changed one as `source_changed` instead of deleting them. |
| C-024 | `TOPIC_NUM_TOPICS=40` caps the topics, and with them the questions a run can write | The ceiling ships at 300 a language and topics are named 25 to a call. A synthetic language of 10,000 passages fits 250 topics, every one named |
| C-058 | No refit or topic delete while a question drain runs | A fit request, `DELETE /topics` and `make topics-delete` refuse while a topic holds a live question claim (409 `questions_running`, or exit 1) |
| C-059 | The workbook says that the judge's figures are not a quality estimate | The judged sample is drawn from each stratum in proportion to its size, from the released questions once a release exists, and the Summary says its counts are not a quality estimate |
| C-072 | `HF_HUB_OFFLINE=1` with a filled model cache | `make corpus-hosted` runs with `HF_HUB_OFFLINE=1` and, before it detaches, refuses a cache that lacks an encoder at its pinned commit or Docling's weights |
| C-075 | Stop the workers and drains before `make schema` | Each migration runs in its own transaction under a 5-second lock timeout and a 10-minute statement timeout, so a busy table fails the migration rather than queueing every worker behind it. `make upgrade` stops the workers first |
| C-076 | Before ingest, list the page counts and split or try first any document far above 139 pages | `PARSING_MAX_PAGES` (180) refuses a longer document before conversion, naming its pages. `make parse-retry` returns it |
| C-078 | Run `make confidence-recalibrate` only with the question drains stopped | It reads without a lock and writes back in batches of 300, each row guarded by the scores it read. A row changed meanwhile is left for the next run |
| C-079 | No `make up` or reboot during a drain, and the `*-retry` targets after any restart | A worker told to stop finishes its row, or gives it back at a second signal or at its stage's grace, and exits 75. Compose waits longer than that grace. `make corpus-hosted` resumes a stopped run and returns its failed rows |
| C-080 | Give the VM at least the compose limits, or stop the unused services | Argilla, Redis, Elasticsearch, Filebeat, Grafana and Adminer sit under profiles, and the production `make up` starts eleven services ([Profiles](#profiles)) |
| C-086 | Check free space and prune dangling images before every rebuild | `make upgrade` checks `UPGRADE_FREE_GB` (20) in the engine, builds, and prunes what the build orphaned before it migrates |
| C-088 | `LITELLM_LOCAL_MODEL_COST_MAP=true` in the deployment's environment | Committed in `backend.env` |
| C-102 | Before the first workbook is delivered, say that a follow-up's earlier turns and a row's location must be looked up | The Questions sheet gives each row its earlier turns and its source. Read blind, 35 of 40 released rows stand on their own (bar 34) |
| C-103 | Set a trace retention at `make up` | `make up` sets Phoenix's default trace retention to `PHOENIX_TRACE_RETENTION_DAYS`. It was not checked against a running Phoenix, so read what `make up` prints |
| C-107 | Ingest only documents the corpus owner controls, as for C-106, until hidden text is flagged | Text that no reader sees (render mode 3, fully transparent, under 2 points, white on bare paper) is dropped from a page whose other text paints ink. 2 of 80 PDFs change, both by diagram labels under 2 points |
| C-110 | Pin the parse dependencies and replay a sample after any bump | `make test-golden` converts and chunks pages of the shop corpus (German and English) and a price list made in the test, against stored snapshots |
| C-112 | Pin the embedding libraries for the production corpus | Every Hugging Face load names its pinned commit. A nightly job fetches the weights at those commits and runs the real-model tests offline, failing where they skipped |
| C-117 | Fill the model cache once, keep `HF_HUB_OFFLINE=1`, and record the revisions | `EMBEDDING_MODEL_REVISION`, `NLI_MODEL_REVISION` and `QA_MODEL_REVISION` pin each encoder, fixed beside its model id, and every load passes them |
| C-118 | A purge cadence in the runbook, run per database | `make archive-purge` deletes in committed batches of 10,000 rows, only this database's, and `make doctor` prints the archive's size ([Deleting things](#deleting-things)) |
| C-119 | No stored overrides on the production database, or check `make settings` after every upgrade | Every stage checks the stored rows against the catalogue when it builds. A row the catalogue refuses, or a retired name, stops that stage naming it, and an override draws a warning |
| C-123 | Read the audit's output by hand before production and at each upgrade | `configs/audit-accepted.txt` lists each accepted advisory with its reason and a review-by date. `make audit` fails on any other advisory and on a passed date |
| C-201 | A database password without URL-reserved characters | `make doctor` and `make corpus-hosted` refuse an `APP_DB_PASSWORD` holding `@ / : # ? %`, naming it |
| C-219 | After any model change, a preflight log must show a price for each role | A drain with `SPEND_CAP` set refuses a model that litellm cannot price, naming it, and an unpriced call is logged as one |
| C-253 | Build images locally only and never push them | `.dockerignore` lets in only what the three Dockerfiles copy: no workbook, document, `.env` or key reaches a build |
| C-299 | Keep `MAX_FILE_SIZE_MB` at or below its shipped 100 | `MAX_FILE_SIZE_MB` is bounded at 150, meant as what the API's 512 MB holds whole (not measured). The API refuses a PDF of more than `PARSING_MAX_PAGES` pages or one read past `PARSING_TIMEOUT_SECONDS`, naming the setting |
| C-416 | Before ingest, list the currency codes in the corpus's tables, and ship the currency fix first beyond EUR, USD, GBP and CHF | A currency is any ISO 4217 code or currency sign beside a number, or the language's own word for one |

## Upgrading to v0.5.1

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration and no new setting.

- Dagster starts again. v0.5.0 moved the orchestration image to SQLAlchemy
  2.1, which reads a bare `postgresql://` URL as psycopg 3. The image installs
  only the psycopg2 that dagster-postgres brings, so the Dagster webserver,
  the daemon and `make dagster-wipe` (and with it `make wipe`) failed at
  start. `configs/dagster/dagster.yaml` now names `postgresql+psycopg2` in the
  storage URL. The commands above rebuild the image and recreate both
  containers.
- One reasoning effort serves a mixed model split. `LLM_REASONING_EFFORT` is
  not sent to a hosted model that litellm knows does not reason (gpt-4.1,
  gpt-4o), which refuses the parameter. A reasoning writer that must be told
  `none` to answer at temperature 0 (gpt-5.6-sol) can sit beside a verifier,
  judge or phrasing model that does not reason. A model that litellm does not
  know, such as a deployment with its own name, is still sent the effort.
- `EXTRACTION_DIGEST_MIN_CHARS` ships at 500 (was 800). The next extraction
  gives passages of 500 to 800 characters a summary and an outline. The
  measurement that set 800 predicts about half of those digest calls refused
  as `not_condensed`, at one digest call each. Stored facts keep what they
  were extracted with. Set it back to 800 in `configs/env/backend.env` to ask
  only where most digests pass.

## Upgrading to v0.5.0

Two paths: from v0.4.5, and from v0.3.12.

### From v0.4.5

```bash
poetry install --with llm,nlp,data,storage,api,pipeline,viz,observability,dev
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

Every dependency moves to the newest release its range allows (139 packages of
`poetry.lock`, with the image locks and `orchestration/requirements.txt`). Run
`poetry install` first (`make install-python` runs it and fetches the spaCy
pipelines), then rebuild the images so the host and the images match.

- SQLAlchemy 2.0.52 becomes 2.1.6, now the floor. A virtualenv left at 2.0.52
  fails at import with `cannot import name 'distinct_on'`.
- pandas 2.3.3 becomes 3.0.6 on the host and in both images.
- Docling 2.137.0 becomes 2.141.0 (docling-core 2.103.1). A document parsed
  now can differ from one parsed under 2.137.0. Stored parses keep what they
  were parsed with until `make parse-rerun`.
- Dagster 1.13.26 and dagster-postgres 0.29.26 in the orchestration image and
  on the host. Both use the one `dagster` database, so rebuild the image
  whenever the host moves.
- litellm 1.106.2, transformers 5.20.2, fastapi 0.159.1, pydantic 2.14.1.
  Pillow stays at 12.3.0 (see v0.4.4).

No migration: the head stays at `20e31b1656f7`. No setting is new or gone.

`QUESTIONS_RELEASE_UNANSWERABLE` ships at 0.10 (was 0), so a release holds up
to a tenth unanswerable questions. The settles reading still keeps answerable
ones: on link U, 19 of 60 kept out-of-corpus rows and 20 of 60 base rows were
answered by the corpus after all. Up to about a third of the released
unanswerable rows therefore test a chatbot for saying no to a question it
should answer. This known defect is recorded in `docs/bugs.md`. Set the value
to 0 in `configs/env/backend.env` to release none.

A category of `QUESTIONS_CATEGORIZATIONS` takes two new keys, `settles` (the
verdict the cited passages must give: `answers`, `refutes` or `silent`) and
`behaviour` (what a good reply does). A categorization whose categories all
carry both is the unanswerable one, and at most one categorization may be. The
[configuration guide](configuration.md) lists when a value is refused.

Unset, the default keeps Phrasing × Premise × Linguistic variation and adds
`Unanswerable`, which deals every unanswerable slot the out-of-corpus kind
alone. The kinds of UAEval4RAG (Peng et al., [*Unanswerability Evaluation for
Retrieval Augmented Generation*](https://aclanthology.org/2025.acl-long.415/),
ACL 2025) are `out-of-corpus`, `false-presupposition`, `underspecified` and
`nonsensical`, held as `UNANSWERABLE_CATEGORIZATION` in
`backend/question_generation/config.py`. The other three are opt-in. To opt
in, set `QUESTIONS_CATEGORIZATIONS` to a list holding the default's three
answerable categorizations and `UNANSWERABLE_CATEGORIZATION` in place of
`Unanswerable`, because a value replaces the default whole. `backend.env`
cannot hold JSON, so use the settings page, `PATCH /settings/questions` or
`python -m settings.run`. The three opt-in kinds got writer-prompt fixes after
link U that were not re-calibrated.

Prompts: writer 28 becomes 29 (only the unanswerable writer changed, with a
variant per kind: `perturb (out-of-corpus)`, `perturb (false-presupposition)`,
`perturb (underspecified)`, `perturb (nonsensical)`). An underspecified writer
may decline a passage that gives no value differing by case, and the slot is
skipped. Verifier 12, phrasing 4 and assessment 4 stay. No model call is
added. Stored rows need no rerun: `make questions-rejudge` reads a row's
expected verdict off its stored category, and a row written before v0.5.0
reads `silent`. The next `make questions-balance` draws unanswerable rows into
the release up to the 0.10 ceiling.

Commands, workbook and API:

- `make diversity FILE=<workbook> LABELS=<file>` corrects each share that
  reviewers labelled by the judge's verdict on all the questions, with
  prediction-powered inference (Angelopoulos et al., [*Prediction-powered
  inference*](https://doi.org/10.1126/science.adi6000), Science 2023), as ARES
  (Saad-Falcon et al., [*ARES: An Automated Evaluation Framework for
  Retrieval-Augmented Generation
  Systems*](https://aclanthology.org/2024.naacl-long.20/), NAACL 2024) does.
  The [assessment
  README](../backend/assessment/README.md#labelled-shares-corrected-by-the-judge)
  describes the labels file and the report. The workbook's Judge column must
  hold the judge of the DataMorgana paper (Filice et al., [*Generating Q&A
  Benchmarks for RAG Evaluation in Enterprise
  Settings*](https://aclanthology.org/2025.acl-industry.33/), ACL 2025
  Industry Track).
- Every `make diversity` table except `AGAINST=`'s gains `held`, an easiness
  reading.
- Export again for the new cells: the Summary counts the questions each model
  wrote, verified and phrase-judged, and an unanswerable row told a kind names
  it in Categories (`Unanswerable=false-presupposition`) and gives `Expected
  behaviour: ` in Answer.
- `GET /questions/quality` gains `writer_model`, `verifier_model` and
  `phrasing_model`. A question in `GET /questions` gains `behaviour`.

### From v0.4.0 to v0.4.4

Follow the section of each later release first, in order, then From v0.4.5.
`make schema` reaches `20e31b1656f7` on the way.

### From v0.3.12

This path replaces the sections for v0.3.13 to v0.4.5 and From v0.4.5. Back up
PostgreSQL and the `documents` bucket first ([Backups](#backups)). One
migration below cannot be undone.

#### 1. Code, host environment and images

```bash
poetry install --with llm,nlp,data,storage,api,pipeline,viz,observability,dev
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
podman compose --env-file configs/env/deployment.env --env-file .env up -d --remove-orphans
```

The last command removes, once, the `seaweedfs-ui` container that compose no
longer defines (v0.4.5). A virtualenv left on v0.3.12's SQLAlchemy 2.0 fails
at import.

#### 2. Six migrations: `make schema`

Check with `make schema-status`. The revisions apply in order on top of
v0.3.12's head `8f759a3a3848`:

| Revision | From | What it does |
|---|---|---|
| `a41c9e3d7b52` | v0.3.20 | Adds `questions.kind`, `NOT NULL`, backfilled from the passage scope |
| `c3a9e1470b5d` | v0.3.23 | Adds `facts.bridge`, empty until `make extract-bridge FORCE=1` rewrites each bridge |
| `d5b2f8a60c14` | v0.3.36 | A trigger takes a thread's follow-ups out of the release when its root leaves `accepted`, and a one-time repair clears the release of follow-ups already split from their root. A downgrade cannot undo the repair. The v0.4.0 notes give the count query |
| `733a3eadef7c` | v0.4.2 | Lets `assessment_metrics` hold the six `rubric_*` scores of the DataMorgana paper's judge |
| `626a5b07ae34` | v0.4.2 | Adds `questions.categories`, empty on stored questions |
| `20e31b1656f7` | v0.4.4 | Column comments only |

#### 3. Settings

None is required. Changed:

- `QUESTIONS_KIND_MIX` defaults to `needs_both:5,compound:1`. About one in six
  slots that span passages becomes a compound question. `needs_both:1` turns
  that off.
- `QUESTIONS_CATEGORIZATIONS` is new. Unset, it deals Phrasing × Premise ×
  Linguistic variation and the out-of-corpus kind to every unanswerable slot.
  `[]` turns categories off.
- `QUESTIONS_RELEASE_UNANSWERABLE` ships at 0.10 (was 0), with the known
  defect that From v0.4.5 gives. 0 releases none.
- Deleted: `TOPIC_LABEL_MIN_FACT_SHARE` and `REVIEW_REVIEWER`. A value left in
  an environment file is ignored.
- Tighter bounds: `EMBEDDING_MAX_TOKENS` at least 64.
  `ORCHESTRATION_DRAIN_TIMEOUT_SECONDS` and `ORCHESTRATION_POLL_SECONDS` each
  a finite number of seconds, at least 1, or the orchestrator's code location
  refuses to load. `DATABASE_URL` must name a database.
- Read differently, values unchanged: `QUESTIONS_RELEASE_LANGUAGES` unset,
  `EXTRACTION_BRIDGES_PER_TOPIC`, `EXTRACTION_MIN_OTHER_SHARE`, and
  `TOPIC_NO_BELOW` and `TOPIC_NO_ABOVE` for a small language.
- `make doctor` asks every model a stage calls. `configs/env/backend.env` puts
  `EXTRACTION_DIGEST_MODEL`, `TOPIC_MODEL` and `QUESTIONS_PHRASING_MODEL` on
  `ollama_chat/muse-glimmer:30b-mlx`. Pull that model, or point the three
  lines at an available one.

#### 4. Prompts and model calls

- Writer 15 to 29. Verifier 6 to 12, with `verifier: stated` 1 new. Assessment
  template 2 to 4. Topic naming 2 to 3. Bridge prompt 5 to 6. Unchanged:
  atomic extraction 12, repair-1, digest 5, phrasing 4. Stored rows keep their
  version.
- Calls added: one verifier read for an accepted answerable `needs_both`
  question citing two passages (v0.3.35), two for a compound question
  (v0.3.26), the DataMorgana judge in place of question relevance while
  `ASSESSMENT_ENABLED` is on (six calls for a root question), one rewrite of a
  with-premise draft that names no asker, and one verifier read for a short
  search query when that opt-in category is configured.

#### 5. Reruns, in order

None is needed to start v0.5.0. One pass under v0.5.0's code covers every
release since v0.3.12.

| Step | Command | Notes |
|---|---|---|
| Parse | `make parse-rerun CONFIRM=<database>` | Parse fixes of v0.3.31, v0.4.0, v0.4.4 and Docling 2.141.0 |
| Chunk | `make chunk-rerun CONFIRM=<database>` | A passage that the new cut repeats exactly keeps its facts. Every other one is replaced, the facts and bridges on it go to the archive, and the questions on them are rejected as `source_changed` and kept |
| Extract new passages | `make extract-start`, then `make extract` | Only passages the re-chunk made reach the model |
| Give back repair pieces | `make extract-recap`, then `make extract-dedup` | No model call for the recap |
| Judge facts again | `make extract-revalidate` | No model call |
| Rewrite bridges | `make extract-bridge FORCE=1` | The one rerun that calls the model for every bridge. `FORCE=1` is needed while an accepted question cites a bridge, and those questions are rejected as `source_changed` and kept |
| Refit topics | `make topics-discover` | Figures and models move to `topics/<database>/<language>`, and the Topics page shows no figure until this runs. A person's name or coverage choice goes to the topic holding most of its passages |
| Questions already stored | `make questions-rescore`, then `make questions-reverify` | Reverify can reject a stored question and never gives a rejected one back |
| Ask unanswerables again | `make questions-rejudge` | One settles reading for each stored accepted unanswerable question, and a second where its cited passages are silent and the probe is on. Later runs ask nothing new |
| Redraw the release | `make questions-balance` | |

Optional:

- Stored questions carry no categories, no compound kind and no unanswerable
  kind. Only a fresh `make questions` writes those.
- `make assess-rerun ONLY=--only\ kind=question` judges stored questions with
  the DataMorgana paper's judge. It clears and replaces every stored question
  verdict, the old `relevance` rows included. `make diversity LABELS=` and the
  judge's means need it.

#### 6. What else changes

- The workbook gains a Kind column after Type and a Categories column, and its
  Summary counts kinds, categories and models, on the next export.
- Argilla: recreate a question dataset made before v0.4.3 (it lacks `kind`,
  `thread`, `turn` and the categories) and a facts dataset made before v0.4.5
  (it lacks each fact's `language`). The [review README](../review/README.md)
  says how.
- API: assessment reruns answer 409 when the phase cannot run, `GET
  /pipeline/runs` refuses a `limit` outside 1 to 500, and NUL bytes and lone
  surrogates are refused at the edge.

## Upgrading to v0.4.5

Rebuild and `make up`. Then, once, remove the old `seaweedfs-ui` container,
which compose does not define:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env up -d --remove-orphans
```

No migration (the head stays at `20e31b1656f7`), no prompt change, no rerun.

- `REVIEW_REVIEWER` is deleted. A value left in an environment file is
  ignored.
- `EMBEDDING_MAX_TOKENS` below 64 is refused when written (1 was accepted). A
  window of 1 to 6 left every document failing chunking or cut into sub-word
  passages. The shipped 512 is unchanged.
- `ORCHESTRATION_DRAIN_TIMEOUT_SECONDS` and `ORCHESTRATION_POLL_SECONDS` must
  each be a finite number of seconds, at least 1. The orchestrator's code
  location refuses to load otherwise. Correct such a value in
  `configs/env/orchestration.env` or `.env` before `make up`. The shipped
  28800 and 15 load as before.
- A setting, topic label or upload filename holding a NUL byte or a lone
  surrogate is refused at the edge: `out_of_range` for a setting, 422 for a
  topic label, 400 `invalid_value` for a filename.
- Orchestration routes: Stop asks Dagster for every unfinished run of the
  corpus job. `GET /pipeline/runs` refuses a `limit` outside 1 to 500 with
  422. It and `PUT /pipeline/automation` answer 503 `orchestrator_refused`
       when Dagster answers with an error (they answered `no_orchestrator`).
- A hosted `LLM_MODEL` is not sent the `OLLAMA_BASE_URL` address when
  `LLM_BASE_URL` still holds it. A gateway address in `LLM_BASE_URL` is kept.
  `make doctor` asks every model a stage calls one question. `backend.env`
  puts `EXTRACTION_DIGEST_MODEL`, `TOPIC_MODEL` and `QUESTIONS_PHRASING_MODEL`
  on `ollama_chat/muse-glimmer:30b-mlx`: pull it, or point the three lines at
  an available model.
- Images are named for the compose project (`qa_generator-backend`,
  `qa_generator-orchestration` by default). A stack has 23 containers. See [A
  second stack beside the first](#a-second-stack-beside-the-first) and [A
  smaller stack](#a-smaller-stack).
- Review: a fact push leaves out facts answered in Argilla and not yet pulled.
  A fact record carries `language` metadata. A facts dataset created before
  v0.4.5 lacks it: run `make review-pull-facts`, delete the dataset in Argilla
  and push again. A corrected topic name over 120 characters stays in Argilla
  with its coverage answer: shorten it there and pull again.

## Upgrading to v0.4.4

Rebuild, `make up`, `make schema`.

- `make schema` applies `20e31b1656f7` on top of `626a5b07ae34`: column
  comments only.
- Both image locks resolve under the pins of `poetry.lock`, so images and host
  run the same versions. The parse worker runs in the API image (Docling
  2.137.0, was 2.132.0), so a document it parses can differ from an earlier
  parse. `make lock` writes both image locks in a throwaway container. Run it
  after changing a `requirements.txt`.
- Pillow stays at 12.3.0. Its advisories are fixed only in Pillow 13.0.0,
  which no released Docling allows, and none is reached by the parse of an
  uploaded PDF (`docs/bugs.md` says why). `make audit` reads OSV, which lists
  three Pillow advisories that PyPI's service missed.
- `TOPIC_LABEL_MIN_FACT_SHARE` is deleted. A topic is left unnamed when it is
  no passage's strongest.
- `PARSING_OCR_CHAR_THRESHOLD` (100) also decides which pages of a digital PDF
  are named as image-only: a page with no more characters than it, under
  pictures covering at least half of it. The parse warning, the stored parse's
  metadata and `documents.parse_error` name it.
- `DATABASE_URL` must name a database, because topic figures and models are
  keyed by it.
- Topic naming prompt 2 becomes 3: the model flags a topic with no subject
  instead of writing "Mixed". No model call is added.
- Topic figures and models move to `topics/<database>/<language>.html` in
  `export` and `.npz` in `models`. The old keys are not read. Until `make
  topics-discover` runs, the Topics page and `GET
  /topics/visualisation/{language}` show no figure and `make topics-render`
  finds no model.
- A restore from the archive keeps a follow-up's release only under a turn
  still accepted and released in the same release. Otherwise it comes back
  accepted but undrawn, and `make questions-balance` decides.
- `make audit` also audits the host `poetry.lock` and runs whole on Linux
  only. `make dev` waits at most 60 seconds for Postgres. `make spend` and
  `make spend-by-shape` refuse a `LOG` that names no readable file with exit
  status 2.

Reruns, in order (none is needed to start v0.4.4):

1. `make parse-rerun CONFIRM=<database>`
2. `make chunk-rerun CONFIRM=<database>`: a passage that the new cut repeats
   exactly keeps its facts. Every other one is replaced, and the questions on
   its facts are rejected as `source_changed` and kept.
3. `make extract-start`, then `make extract`. A passage skipped before as a
   grid of identifiers (a fee table whose amounts carry a currency code such
   as `EUR 5`) is not queued again: `make extract-rerun SHA=` reads its
   document again.
4. `make extract-revalidate`, no model call.
5. `make extract-bridge FORCE=1`, the one rerun that calls the model for every
   bridge.
6. `make topics-discover`.
7. `make questions-reverify`, then `make questions-rescore` if the refit
   changed the topics.

## Upgrading to v0.4.3

Rebuild and `make up`. No migration (the head stays at `626a5b07ae34`) and no
new setting.

- Unset, `QUESTIONS_CATEGORIZATIONS` deals Phrasing, Premise and Linguistic
  variation (similar-to-document or distant-from-document) at even odds. To
  keep v0.4.2's two, set it to `DEFAULT_CATEGORIZATIONS` in
  `backend/question_generation/config.py` without the Linguistic variation
  entry.
- A category may be `"form": "premise"`. A premise is not told beside a
  category that caps the question's words, nor beside a search query.
- A category's `words` bound `max` also stops a premise beside it and makes a
  search query carrying it be read once more against the passages it does not
  cite. A `min` alone has neither effect.
- A search query is not told on a slot that spans two passages, nor on a
  `reason`, `comparison`, `implication` or `temporal` slot.
- A value set locally is used as written. Copy the new JSON from the
  [configuration guide](configuration.md) to take the reworded descriptions.
  The guide lists the nine cases where a value is refused.
- Writer prompt 19 becomes 28 and verifier 6 becomes 12. Stored questions keep
  their version.
- Model calls: a short search query (one with a `words` maximum) costs one
  passage probe and one more verifier read, only while such a category is
  configured and `QUESTIONS_ELSEWHERE_PASSAGES` is above 0 (default 20). A
  with-premise draft with no first- or second-person word is written once
  more. The first `make questions-rejudge` costs one `settles` reading for
  each stored accepted unanswerable question, and a second where the cited
  passages are silent and the probe is on.
- The export command line refuses a `--question-type` or `--answer-form` that
  does not exist, as `GET /questions/export` does.
- Recreate a review dataset made before v0.4.3 to carry the categories field.
  The [review README](../review/README.md) says how.

Stored questions meet the new gates only when rerun: `make questions` (new
rows under writer 28), `make questions-reverify`, then `make
questions-balance` once, after the other two.

## Upgrading to v0.4.2

Rebuild, `make up`, `make schema`. On a host checkout, run `poetry install`.

- `make schema` applies two revisions on top of `d5b2f8a60c14`: `733a3eadef7c`
  lets `assessment_metrics` hold the six `rubric_*` scores of the DataMorgana
  paper's judge (its downgrade deletes those rows), and `626a5b07ae34` adds
  `questions.categories`, empty on stored questions.
- `QUESTIONS_CATEGORIZATIONS` is new and optional. Unset, a fresh generation
  deals the paper's Phrasing and Premise at even odds. The [configuration
  guide](configuration.md) gives the JSON to opt into more.
- Writer prompt 16 becomes 19. Assessment template 2 becomes 4: a root
  question is judged in six calls and eleven metrics and a follow-up in five,
  and question relevance is not asked (stored rows are kept).
- `make assess-rerun ONLY=--only\ kind=question` judges stored questions again
  with the paper's judge and replaces every stored question verdict. `make
  diversity FILE=<workbook>` measures an exported workbook and changes nothing
  stored.

## Upgrading to v0.4.1

Rebuild and `make up`. No migration, setting, prompt change or model call.
`make diversity FILE=<workbook>` is new: it measures how varied an exported
workbook's questions are and changes nothing stored.

## Upgrading to v0.4.0

This section is for a stack on v0.3.12 moving straight to v0.4.0. It replaces
the sections for v0.3.13 to v0.3.36. Back up PostgreSQL and the `documents`
bucket first ([Backups](#backups)), because the migrations cannot all be
undone.

1. Rebuild and `make up`. On a host checkout, run `poetry install`. The host
   `poetry.lock` pins aiohttp 3.14.5 and yarl 1.25.1, which close three
   advisories (CVE-2026-111063, CVE-2026-111064, GHSA-2g87-pp6c-29x5), and
   certifi 2026.10.19 (GHSA-6q48-6c7w-9gw2).
2. `make schema-status`, then `make schema`. Three revisions apply on top of
   `8f759a3a3848`:

   | Revision | From | What it does |
   |---|---|---|
   | `a41c9e3d7b52` | v0.3.20 | Adds `questions.kind` (`single`, `needs_both`, `compound` or `false_premise`), `NOT NULL`, backfilled from the passage scope (`needs_both` where it is `multi_passage`). The same rule backfills the question payloads in older wipe archives |
   | `c3a9e1470b5d` | v0.3.23 | Adds `facts.bridge`, a nullable JSON object `{relation, question, answer}`, empty until `make extract-bridge FORCE=1` rewrites the bridge |
   | `d5b2f8a60c14` | v0.3.36 | A question leaving `accepted` takes every follow-up below it out of the release in the same statement. A one-time repair clears `release_id` on follow-ups that stay released under a root that is not accepted. A downgrade cannot undo the repair |

   To count the rows the repair touches first (direct follow-ups; deeper turns
   of the same threads are cleared too):

   ```sql
   SELECT count(*) FROM questions q WHERE q.release_id IS NOT NULL AND q.follows_id IS NOT NULL AND EXISTS (SELECT 1 FROM questions r WHERE r.id = q.follows_id AND r.status <> 'accepted');
   ```
3. Settings: none is removed or required. `QUESTIONS_KIND_MIX` defaults to
   `needs_both:5,compound:1`: about one in six slots that span passages is
   dealt as a compound question (two questions, one answered by each of two
   passages, at two verifier reads). `needs_both:1` turns that off. With
   `QUESTIONS_RELEASE_LANGUAGES` unset, a release weighs each language by the
   accepted questions a draw can take from it, so the ids of an existing
   release can move when `make questions-balance` runs again.
   `EXTRACTION_BRIDGES_PER_TOPIC` counts a pair on the passage that heads it.
   `TOPIC_NO_BELOW` and `TOPIC_NO_ABOVE` scale with passage count below six
   passages.
4. A new model call: every accepted answerable `needs_both` question citing
   two passages gets one more verifier call under the pinned prompt `verifier:
   stated` 1 (about USD 0.45 to 0.5 for a build the size of the *Laws of the
   Game*, the football rules). If the model is unavailable, the question is
   kept as cited with a warning. Stored questions are not rejudged.
5. Reruns, in order. None is needed to start v0.4.0.

   | Step | Command | Needed because of |
   |---|---|---|
   | Parse | `make parse-rerun CONFIRM=<database>` | v0.3.31 (U+00AD hyphens kept, group rows, wrapped labels), v0.4.0 (an image-only page is named, not refused) |
   | Chunk | `make chunk-rerun CONFIRM=<database>` | v0.3.31, v0.3.32 (table footnotes and lead-ins), v0.4.0 (a chunk ends where its prose changes language). A passage whose text comes back unchanged keeps its facts |
   | Extract new passages | `make extract-start`, then `make extract` | Only changed passages reach the model |
   | Give back repair pieces | `make extract-recap`, then `make extract-dedup` | v0.3.14. On the v0.3.12 build all 65 `over_cap` refusals are freed, with no model call |
   | Judge facts again | `make extract-revalidate` | v0.3.15, v0.3.29, v0.3.33. No model call |
   | Rewrite bridges | `make extract-bridge FORCE=1` | v0.3.16 (about USD 0.25 more a build), v0.3.23, v0.3.28, v0.4.0. `FORCE=1` is needed while an accepted question cites a bridge |
   | Refit topics | `make topics-discover` | v0.4.0. A language left without a model ends the fit as failed, after the other languages are stored |
   | Questions already stored | `make questions-rescore`, then `make questions-reverify` | Stored kind and citations, number and answer readings. Reverify never gives a rejected question back |
   | Redraw the release | `make questions-balance` | v0.3.27, v0.4.0 and the thread trigger |

6. Recreate the Argilla question datasets made before v0.3.28 (no `kind`) or
   before v0.3.34 (no `thread` field and `turn`).

Other changes:

- The workbook gains a Kind column after Type.
- `POST /assessment/rerun` and the Redo button answer 409
  `assessment_cannot_run` before touching any stored verdict when the
  assessment cannot run (`ASSESSMENT_ENABLED` off, or no judge model set).
  Before v0.4.0 they wiped every stored verdict and answered 202.
- Restoring an archive skips a row whose foreign-key parent is absent and
  prints what it left behind per table.
- The release draw takes seconds at one or two thousand accepted rows (minutes
  at 10,000).

## Upgrading to v0.3.36

Rebuild, `make up`, `make schema`. Revision `d5b2f8a60c14` (on `c3a9e1470b5d`)
adds a trigger and its function and runs a one-time repair that clears
`release_id` on released follow-ups whose root is not accepted. A downgrade
cannot undo the repair. The v0.4.0 notes give the query that counts the rows
it touches. Run `make questions-balance` afterwards to redraw the release.

## Upgrading to v0.3.35

No migration or setting. A new `make questions` run makes one more verifier
call per accepted answerable `needs_both` question citing two passages (about
USD 0.45 to 0.5 per build) under the pinned prompt `verifier: stated` 1.
Stored questions are not rejudged.

## Upgrading to v0.3.34

No migration or setting. The workbook gains a Kind column on its next export.
Existing Argilla question datasets lack the `thread` field and the `turn`
metadata term: recreate the dataset.

## Upgrading to v0.3.33

No migration or setting. Run `make extract-revalidate` to read stored facts
with the new number readings, then `make questions-reverify` for stored
questions.

## Upgrading to v0.3.32

No migration or setting. Run `make chunk-rerun CONFIRM=<database>` to bring a
stored corpus up to date. A document with table footnotes, or tables longer
than one passage under a lead-in, changes its passages. The parse, its content
hash and language are untouched.

## Upgrading to v0.3.31

No migration or setting. `make parse-rerun CONFIRM=<database>` then `make
chunk-rerun CONFIRM=<database>` brings a stored corpus up to date. A PDF whose
font maps its hyphen to U+00AD (pymupdf and MuPDF Arial subsets) gets its
hyphens back, and a document with group-row or wrapped-label fee tables reads
them as rows.

## Upgrading to v0.3.30

No migration or setting. Stored questions stay as they are. A new `make
questions` run deals compound samples from a passage's own claims and
unanswerable slots from facts resting on one passage. A topic that held only
bridges for such a slot writes fewer questions of it, and the log names each
slot skipped.

## Upgrading to v0.3.29

No migration or setting. Run `make extract-revalidate` to read stored facts
with the new reference reading.

## Upgrading to v0.3.28

No migration or setting. On a host checkout run `poetry install` to pick up
the new `poetry.lock` (aiohttp 3.14.5, yarl 1.25.1). A narrowed `make
extract-bridge` does not delete bridges opening outside the scope. Run a
whole-corpus `make extract-bridge FORCE=1` to rebuild such bridges after a
topic change. Existing Argilla question datasets lack the `kind` metadata
term: recreate the dataset.

## Upgrading to v0.3.27

No migration or setting. Run `make questions-balance` to redraw the release.
The draw takes longer on a large pool (seconds at one or two thousand rows).

## Upgrading to v0.3.26

No migration or setting. Compound questions are dealt in about one of every
six spanning slots (the kind mix defaults to `needs_both:5,compound:1`).
`QUESTIONS_KIND_MIX=needs_both:1` turns them off. Measured on pairs built by
the calibration script, not through the deal: 28 of 48 accepted and, read
blind, 28 of 28 compound, 0 false joins, 75% usable and keys right 68%, under
the 80% and 75% the calibration asked. The real path through the deal is not
calibrated. A compound question costs two verifier reads and no round trip,
and the weld rate counts only the `needs_both` kind. Stored questions stay as
they are.

## Upgrading to v0.3.25

No migration or setting. `make questions-reverify` holds a stored question to
its stored kind, so a compound question is not rejected for its two question
words. It cannot re-check a compound question's two halves, which are not
stored.

## Upgrading to v0.3.24

No migration or setting. A numbered list's markers do not count as figures in
`answer_incomplete`, and a dash range's unit matches whatever part of speech
the tagger gives it. Both only free refusals, and a rule frees questions only
in a fresh question generation, because `make questions-reverify` never gives
back a rejected question.

## Upgrading to v0.3.23

Rebuild, `make up`, `make schema`. The migration adds `facts.bridge`, empty on
every row, with no backfill, and constrains it to a bridge. Bridges written
before it stay empty until `make extract-bridge FORCE=1` rewrites them. No
prompt version or stored verdict moves.

## Upgrading to v0.3.22

No migration or setting. Writer prompt 15 becomes 16: the prompt text of each
type gains a compound variant. Compound questions are off by default in this
release (`QUESTIONS_KIND_MIX=needs_both:5,compound:1` turns them on). The real
path is not calibrated, and the blind read missed its quality bars (75%
usable, keys right 68%). Turn them on to measure, not for a release. A
compound question costs two verifier reads and no round trip. A compound
question is never a weld.

## Upgrading to v0.3.21

No migration or setting. No kind fixes a band yet, so no stored band moves and
`make questions-rescore` is not needed.

## Upgrading to v0.3.20

Rebuild, `make up`, `make schema`. The migration adds `questions.kind` (`NOT
NULL`; `single`, `needs_both`, `compound` or `false_premise`), backfilled
`needs_both` where the passage scope is `multi_passage` and `single`
otherwise. `QUESTIONS_KIND_MIX` is optional and defaults to `needs_both:1`.
The questions page shows the kind. No prompt version or stored verdict moves.

## Upgrading to v0.3.19

No migration or setting. The `answer_incomplete` gate refuses fewer list keys,
so a build keeps more questions. The rule frees questions only in a fresh
question generation.

## Upgrading to v0.3.18

No migration or setting. A key holding a range written with a dash is not
refused as `not_recoverable` when the recovery gives each end in its own
words. The rule frees questions only in a fresh question generation.

## Upgrading to v0.3.17

No migration or setting. Only the plan of the question stage changes: a build
that writes unanswerable questions plans them as factoid, entity and reason
questions. Stored questions stay. `QUESTIONS_RELEASE_UNANSWERABLE` stays 0.

## Upgrading to v0.3.16

No migration or setting. `make extract-bridge` writes the bridges again from
the new pairs under bridge prompt 6 (`FORCE=1` while an accepted question
cites a bridge). A pass narrowed with `--only` deletes the bridges of its
topics, including the cross-topic ones, and rewrites only the links whose head
it reads. The pass parses every readable passage once (about 20 seconds per
700 passages), and a pair whose passage holds no validated atomic fact is not
read. It costs about USD 0.25 more a build in input tokens. A heading numbered
before its word ("1.2 Returns") gives no reference link, only sibling and term
links.

## Upgrading to v0.3.15

No migration or setting. `make extract-revalidate` judges the stored bridges
again under the new rule, with no model call.

## Upgrading to v0.3.14

No migration or setting. A fact that the repair call wrote for a statement
refused as `not_atomic` does not compete for its passage's atomic cap. `make
extract-recap` gives back the repair pieces an earlier cap refused, with no
model call (on the v0.3.12 build it frees all 65 `over_cap` refusals). Run
`make extract-dedup` after it, which re-decides the cross-passage repeats the
freed facts may leave. Facts, bridges, topics and questions built on the
stored facts stay until the stages that read them run again. A full
re-extraction gives the same result but asks the model again for every
passage, which recap does not.

## Upgrading to v0.3.13

No migration or setting. The rebuild installs aiohttp 3.14.4 in the API image
and the workers, which fixes three advisories published against 3.14.3. No
stored data moves.

## Upgrading to v0.3.12

No migration or setting. Every verifier prompt is version 6, and only the
settles prompt changed. `make questions-rejudge` asks every accepted
unanswerable question again under it, about two model calls each. Some will be
refused. `QUESTIONS_RELEASE_UNANSWERABLE` stays 0.

## Upgrading to v0.3.11

No migration or setting. A topic fit makes eight seeded draws and keeps the
most cohesive, so it takes about eight times as long (a few seconds per
language on a corpus of a few hundred passages). Stored topics stay until the
next `make topics-discover`, which names the new topics and carries a person's
decisions as v0.3.7 does. Bridges and questions follow the topics.

## Upgrading to v0.3.10

No migration or setting. A passage whose model-written statements are refused
as `not_atomic` costs one more model call (prompt `repair-1`), which writes
the split facts. It runs only when a passage is extracted, so stored facts
gain nothing until the corpus is extracted again. `make extract-revalidate`
judges stored facts again with the claim counter and no model call. On the
reviewed build it validates 8 refused facts.

## Upgrading to v0.3.9

No migration or setting. Bridge prompt 5: stored bridges stay and are marked
as written by an older prompt. `make extract-bridge FORCE=1` writes them
again, replacing the ones accepted questions cite, which rejects those
questions. Questions and the release then follow. A bridge is offered to the
writer alone, so the next questions pass writes one question per bridge, where
it wrote a bridge beside a claim. Stored questions are untouched.

## Upgrading to v0.3.8

Check that `.env` sets every secret compose requires, then rebuild:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env config -q
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

No migration or prompt change.

- Every password and key compose passes is required, and compose stops naming
  the first one missing. `.env.example` names every one. An `.env` written
  before this release may lack a line, which must be added by hand, because
  `make setup` writes `.env` only when there is none.
- Settings refused when written: a number that is `nan` or infinite, a flag
  spelled other than true or false, `TOPIC_NUM_TOPICS` below 2,
  `TOPIC_RANDOM_STATE` outside 0 to 2^32 - 1, and a `TOPIC_NO_ABOVE` of 0. A
  stored value keeps working where it did, and the settings page shows it with
  a warning.
- The frontend answers only at `localhost` and `127.0.0.1`. `PAGE_SIZE`
  outside 1 to 500 stops the frontend at start-up.
- `/redoc` is removed. `/docs` stays.
- Stop stops every queued or started run, not only the newest, and says which
  were already stopping.
- A topic `PATCH` changes only the fields its body names.
- The Argilla topics dataset makes the corrected label optional for a newly
  created dataset. Recreate an existing one to take the change.
- `make eval-score` figures are not comparable with earlier ones: it scores
  the reader that production runs.

## Upgrading to v0.3.7

No migration or setting. Atomic extraction 11 becomes 12 and the digest 4
becomes 5. Every stored fact is marked as written by an older prompt, and
nothing is re-run on its own. The new prompts reach stored facts only through
a re-extraction of the corpus (`make extract-start` with the stack up), which
replaces every passage's facts and so the questions resting on them. Topics,
bridges, questions and the release then follow. On a corpus the size of the
reviewed rulebook, extraction alone is about 1,640 model calls.

The next `POST /topics/discover` carries a person's name and coverage choice
only to the new topic holding most of the same passages. A decision with no
such topic is dropped and logged, and the run's span counts it. Check the log
after a refit and name those topics again in the topic review.

## Upgrading to v0.3.6

Rebuild, `make up`, `make schema`. The migration corrects the passages table's
comment, and its downgrade restores the old wording.

A re-chunk keeps what it does not change. A passage whose text, section path,
sentences and table cells come out the same keeps its id, its facts and its
topics, so a parsing fix rebuilds only the passages it changed.

The parsing and chunking fixes reach stored passages through a re-parse and a
re-chunk (`POST /parsing/rerun?confirm=true`, then `POST
/chunking/rerun?confirm=true`, with the stack up). Neither calls a model. The
passages they change lose their facts and questions, so run extraction, topics
and questions again after them, as the v0.3.0 notes describe. On the reviewed
rulebook that is 30 passages carrying 237 facts and 86 questions.

## Upgrading to v0.3.5

No migration, setting or prompt change.

- `make questions-balance` leaves a record. Its trace reaches Phoenix under
  the run, and its log names every pair of released questions it put to the
  twin judge, with the round and the verdict, and how far each kind, band and
  language came from its quota.
- The check that a verifier's quote sits in the passages reads a quote
  stitched from bullets, cells or a passage's continuation piece by piece. It
  applies to every `settles` judgement made from now on, in a question
  generation and in `make questions-rejudge`, which asks again only a row
  whose stored verdict is from an older prompt version.
  `QUESTIONS_RELEASE_UNANSWERABLE` stays 0.

## Upgrading to v0.3.4

No migration, setting or prompt change. The round-trip and typing gates change
how a question being written is judged, so they apply to questions written
from now on. Stored questions keep their verdicts: `make questions-reverify`
runs only the gates that need no model, and these need the verifier's reading.
A topic generated again (`make questions-start TOPIC=…`, then the worker) is
judged the new way.

## Upgrading to v0.3.3

No migration, setting or prompt change.

- With `extract-worker` stopped, run `make extract-revalidate`. It judges
  every stored fact again with this release's checks, without a model call and
  without changing a statement, and puts what it validates through the
  duplicate gate and the per-passage cap. Facts it newly validates are offered
  to the next question generation. No stored question changes.
- After a run that replaced facts (a re-extraction of a document or of the
  corpus), the extract worker replays the dedup gate over the corpus once its
  queue is empty, so a fact refused as the twin of one that run deleted is
  given back. Two workers never replay at once. A deletion through the API or
  the UI still needs `make extract-dedup` afterwards.

## Upgrading to v0.3.2

No migration, setting or prompt change. The fixes change how text and numbers
are read: where sentences end, which figure-only paragraphs are page numbers,
how a hyphen broken across a table cell or a page is mended, and how a German
decimal, a time or a total is compared. What the stages produce from now on
reads them the new way. Stored data keeps its old reading until built again.
The sentence and hyphen fixes reach stored passages and facts through a
re-parse, a re-chunk and the stages after them (see [Upgrading to
v0.3.0](#upgrading-to-v030) for the order). The number readings reach a stored
question only when it is written again. Parsing and chunking call no model.

## Upgrading to v0.3.1

Rebuild, `make up`, then `make doctor`:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
make doctor
```

`make doctor` compares the settings the API serves with the settings the
checkout defines and names any the API lacks. An API still serving an older
build is the usual cause, and the rebuild is the cure. No migration or prompt
change, so nothing needs re-running.

| Setting | v0.3.0 | v0.3.1 |
|---|---|---|
| `LLM_STRUCTURED_MODE` | any instructor mode | one of `FUNCTIONS`, `PARALLEL_TOOLS`, `TOOLS`, `TOOLS_STRICT`, `JSON`, `JSON_O1`, `MD_JSON`, `JSON_SCHEMA`, the modes litellm's client takes; anything else is refused at start-up |
| `QUESTIONS_MEETS_SHARE` | required | absent reads 0.02 |

- A model call is billed at most `LLM_MAX_ATTEMPTS` times. instructor's own
  re-asks are off, a 429 waits what its `Retry-After` asks (two minutes at
  most), and a provider's content filter is a refusal after one call that
  skips one question slot instead of failing its topic.
- `make spend` counts failed calls, which are billed too, and prints cost to
  four decimals. `make spend-by-shape` reads the same log the same way.
- `make delete` and `make delete-derived` refuse while `extract-worker` runs,
  before they delete anything. Stop the worker first, or delete through the
  API and run `make extract-dedup` once the worker is stopped.
- `make audit` fails when it finds an advisory.
- `ARGILLA_API_KEY` reaches Argilla on a fresh `argilla_data` volume only. An
  owner that Argilla already created keeps its key.

## Upgrading to v0.3.0

Rebuild the API image, then `make up`:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build api
make up
```

No migration. These settings changed in `configs/env/backend.env`. A
deployment that copied the file keeps its old values until it takes the new
ones.

| Setting | v0.2.2 | v0.3.0 |
|---|---|---|
| `QUESTIONS_RELEASE_DIFFICULTY` | `easy:1,medium:1,hard:1` | unset, which follows the answerable pool's own band split |
| `QUESTIONS_RELEASE_UNANSWERABLE` | 0.10 | 0, until the `settles` judgement can be trusted with them |
| `QUESTIONS_ELSEWHERE_PASSAGES` | 10 | 20 |
| `QUESTIONS_FOLLOWUP_TYPES` | `condition,reason,comparison` | `condition,reason` |
| `QUESTIONS_MEETS_SHARE` | none | 0.02, new; required until v0.3.1 |
| `QUESTIONS_RELEASE_TYPES` | `aggregation:4` | `aggregation:1`, the other kinds unchanged |

Six prompts changed: atomic extraction 11, the digest 4, question writing 15,
the verifier 5, the phrasing judge 4 and topic naming 2.

`make questions-balance` calls the verifier about once per released question,
to judge which released questions want one answer. It proves the verifier
model before it asks anything.

On v0.3.0, `QUESTIONS_MEETS_SHARE` is required. A `backend.env` copied from
v0.2.2 must gain the line `QUESTIONS_MEETS_SHARE=0.02`, or `make questions`
and `make questions-balance` stop on the missing name and `question-worker`
logs that it refuses to claim work. From v0.3.1 an absent line reads 0.02.

Most fixes change the passages, the facts or the topics themselves, so stored
rows improve only through a rebuild, and the container workers build it. With
the stack up (`make up`), queue each stage once the one before it has
finished: `POST /parsing/rerun?confirm=true`, then `POST
/chunking/rerun?confirm=true`, then `make extract-start`, then `POST
/topics/discover`, then `make extract-bridge MISSING=1`, then `make
questions-start`, and last `make questions-rejudge` and `make
questions-balance`.

The bridge pass has no worker, so it runs on the host. The host drains (`make
parse-rerun`, `make chunk-rerun`, `make extract`, `make topics-discover`,
`make questions`) refuse while their stage's worker runs and are for
developing a stage. Parsing and chunking call no model. Every step from
extraction on does.

`make topics-discover` carries a name that a person gave to the new topic
holding most of the passages it was given for, and no name a model gave. Every
topic it names is named the v0.3.0 way: in one call per language, in the
corpus's own spelling, without the domain every name shares. Change a name in
the topic review with `make review-push-topics`, then `make
review-pull-topics`.

## Upgrading to v0.2.2

Rebuild the API image, then bring the schema up:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build api
make up
make schema
```

The three new revisions change column comments only. No table, column or
constraint moves, and each downgrades cleanly.

These settings changed in `configs/env/backend.env`. A deployment that copied
the file keeps its old values until it takes the new ones.

| Setting | v0.2.1 | v0.2.2 |
|---|---|---|
| `EXTRACTION_DUPLICATE_COSINE` | 0.95 | 0.985 |
| `QUESTIONS_OFF_TOPIC_OVERLAP` | 0.3 | 0, which turns the gate off |
| `QUESTIONS_ELSEWHERE_PASSAGES` | 4 | 10 |
| `QUESTIONS_DUPLICATE_SHARED_COSINE` | none | 0.88, new; optional, and unset holds a shared fact to `QUESTIONS_DUPLICATE_COSINE` |
| `QUESTIONS_RELEASE_LANGUAGES` | none | optional, new; unset follows the pool's own language split |

Three prompts changed: question writing 12, the verifier 3 and atomic
extraction 10.

The fixes change what the next run writes. Rows already stored improve only
through a rerun. Run these in order, with the commands that call no model
first:

| Command | Calls a model | What it carries into stored rows |
|---|---|---|
| `make extract-dedup` | no | Duplicate refusals the new rule would not make are given back, with their passages re-judged and re-capped, and fold citations come off the facts they were written onto |
| `make extract-revalidate` | no | Facts refused for a pronoun their own statement resolves are validated |
| `make extract-recap` | no | The atomic cap, never below a passage's sentences plus list items, and the repair pieces an earlier cap refused given back |
| `make questions-rescore` | no | Each question's scope and difficulty, from the facts it cites now. Run it after `extract-dedup` and before re-verify, and after no other rerun: there it would hide a question that lost a fact |
| `make questions-reverify` | no | The new gates, on every accepted question. It only rejects |
| `make questions-rejudge` | yes, the verifier | The `settles` judgement, on every accepted unanswerable question |
| `make questions-balance` | yes, the verifier | A release with the language share, hash order and twin check, the twins judged by the verifier |

Struck-through text, list lead-ins and chapter-aware section paths change the
passages themselves. They reach stored rows only through a rebuild by the
container workers: `POST /parsing/rerun?confirm=true`, then `POST
/chunking/rerun?confirm=true`, then extraction, topics, the bridge pass (`make
extract-bridge MISSING=1`) and questions again. Every step from extraction on
calls models. A fresh question generation also carries the fixes in how
questions are written: the widen retry, the deal, the reason and application
slots, the perturbation prompt and the gates that only ever rejected. `make
questions-reverify` never gives back a rejected question.

## Things that go wrong

| Symptom | Usually |
|---|---|
| Topics sit `pending`, nothing in the logs | `question-worker` is downloading 2.2 GB of embedding weights |
| `make assess` prints one line and stops | `ASSESSMENT_ENABLED` is not true, in `.env` or in the override the Assessment page stores, which wins. `make settings SERVICE=assessment` shows the value in force |
| `make assess` refuses before it claims anything | `ASSESSMENT_JUDGE_MODEL` names a model that is not served |
| A queue fills and nothing drains it | That stage has no container. Run `make up` |
| Grafana panels are empty | The shipper. Run `make logs-shipper` |
| A panel that groups by `stage` finds nothing | A field missing from `append_fields` in `filebeat.yml` |
| An edit to `filebeat.yml` changed nothing | The Filebeat container still runs the file it started with. Run `podman compose restart filebeat` |
| Grafana cannot read the database | `init.sh` has not run on this volume |
| The run dashboard's Phoenix panels cannot read their tables | The grants that `make up` and `make dev` make have not run. Run `make grafana-grants` |
| Streamlit refuses a file the API would accept | `server.maxUploadSize` is below `MAX_FILE_SIZE_MB` |
| The frontend will not start, naming a variable | The variable is declared but not in the `streamlit` service's `environment` |
| Argilla refuses the key | Its owner was made before compose passed it `ARGILLA_API_KEY`, and keeps the key Argilla made. That key is under "My settings": copy it into `ARGILLA_API_KEY`. It is not `ARGILLA_PASSWORD` |
| Argilla restarts, logging that Elasticsearch is not available | `certs/` was generated by macOS's LibreSSL before v0.2.1 and lacks key identifiers. Delete `certs/`, then run `make down && make dev` |
| A p99 climbing towards `LLM_TIMEOUT_SECONDS` | Calls about to time out, be tried again and fail their rows. Raise the timeout |
| A scanned PDF is refused rather than parsed | OCR is not enabled |
| `make questions-reverify` rejects many questions as `source_changed` after `make extract-dedup` | Their stored scope still counts the fold citations the dedup removed. Run `make questions-rescore` first |
| The release report warns that a language in the pool has no weight | `QUESTIONS_RELEASE_LANGUAGES` leaves it out, so none of it is drawn. Name it, or unset the setting to follow the pool's own language split |

## Deleting things

```bash
make delete SHA=<sha256> CONFIRM=<database>          # a document and everything from it
make delete-derived SHA=<sha256> CONFIRM=<database>  # only its passages and facts
make wipe CONFIRM=<database>                         # every document, then the topics
make topics-delete CONFIRM=<database>                # every topic, membership, model and figure
```

Each is the first of two deletions. An AFTER DELETE trigger copies the row
into `archived_rows`, and the removal paths move objects into the `archive`
bucket:

```bash
make archive                                   # what is held, by table, with its age
make restore-documents SINCE=<time>            # list the deletions from then on
make restore-documents AT=<archived_at>        # put those deletions back
make archive-purge DAYS=30 CONFIRM=<database>  # the second deletion. This one is final
```

Nothing purges itself, so the archive grows on ordinary runs too: a
re-extraction and a re-chunk delete the facts they replace, and the questions
on them are kept, rejected. `make doctor` prints the archive's rows and size,
read from the planner's statistics so it costs nothing however large the
archive is. Purge on a cadence per database, after `make backup`. `make
archive-purge DAYS=<n>` deletes in committed batches of 10,000 rows, so a
large archive never holds one lock or one transaction, and it takes only this
database's rows and objects. See
[`backend/archive/`](../backend/archive/README.md).

These two archive nothing, because `TRUNCATE` and a dropped volume fire no row
trigger:

```bash
make down-volumes CONFIRM=all-volumes  # the containers' data, all of it
make schema-reset CONFIRM=<database>   # every table, rebuilt from the revisions
```

Deleting a document takes everything derived from it. It does not take
`topics`, because a fit is over the corpus and not over a file. `make wipe`
runs both.

A claim that two documents in the same language share, as the same kind of
fact, rests on one of them only. A translation's claim is its own language's
fact and is never a duplicate. The second copy is stored as a `duplicate`
refusal that names the first and cites only its own passage. Deleting the
first document takes the claim with it and leaves the second copy refused.

`make delete` and `make delete-derived` then run `make extract-dedup` over the
whole corpus. It calls no model, gives that copy back, and re-judges and
re-caps the passages of what it gave back, and no others. Every deletion
(`make delete`, `make delete-derived`, either `DELETE` route or the Documents
page) ends with one line saying how many duplicate refusals lost the fact they
repeated.

The extraction worker re-decides them when its queue is empty. It asks for a
refusal pointing at no twin, which a deletion leaves however it was made.
Where no extraction worker runs, as on the production profile, run `make
extract-dedup`. No `make questions-rescore` follows a deletion, because the
questions that rested on the deleted facts went with them.

The deletion and the replay are two steps. Both refuse beside a running
`extract-worker` container, and `make delete` asks before it deletes, so that
refusal leaves the document in place. If the replay fails after the deletion,
the document is already gone, and running `make delete SHA=…
CONFIRM=<database>` again finds nothing to delete. The recovery is `make
extract-dedup`, once whatever stopped it is out of the way.
