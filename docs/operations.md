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

Credentials: `PHOENIX_DEFAULT_ADMIN_INITIAL_PASSWORD` for Phoenix (user
`admin@localhost`), `GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD`,
`ARGILLA_USERNAME` and `ARGILLA_PASSWORD`.

`make services` and the System health page query `GET /services`, which probes
the catalogue in [`backend/api/services.py`](../backend/api/services.py) live.

### Access

Every published port binds to 127.0.0.1. PostgreSQL and the SeaweedFS S3
gateway publish a port for host commands. The SeaweedFS master, filer and
volume servers publish none. The API answers only the host names in
`API_ALLOWED_HOSTS` and refuses with 403 a browser request from another site
and a write from another origin.

Every write to the API and every read of `/settings` must carry the shared
secret `API_TOKEN` in the `X-API-Token` header, or the API answers 401
`unauthorized`. `make setup` generates the secret into `.env`, and the
frontend, the orchestrator and the make targets send it. The secret is shared
and is not a login, so binding to 127.0.0.1 is a requirement. An existing
`.env` needs the line added: run `make setup` again (it fills only
placeholders) and recreate the stack.

`EMBEDDING_MODEL`, `NLI_MODEL`, `QA_MODEL` and `DOCLING_ARTIFACTS_PATH` are
fixed. A value stored for one of them through the UI, the API or `make
settings-set` stops applying, and the environment files' value is read. Set an
intended value in `configs/env/backend.env` before upgrading.

## Memory

The memory limits in [`compose.yaml`](../compose.yaml) add up to about 33 GiB:
PostgreSQL 4 ([sized below](#sizing-postgres)), the question worker 6, the
parse and extract workers 4 each, the chunk and topic workers 3 each,
Elasticsearch 2, every other service 1 or less. A container that reaches its
limit is killed.

On macOS and Windows the containers run inside Podman's virtual machine, which
has its own memory size. `podman machine inspect` shows it
(`Resources.Memory`, in MiB). Stop the machine to change it:

```bash
podman machine stop
podman machine set --memory 16384
podman machine start
```

A machine smaller than the workers run at once needs [the smaller
stack](#a-smaller-stack), which has run with the parse or chunk worker in 8
GiB.

### Sizing Postgres

One server holds five databases and three vector indexes (passages, facts and
questions, 1024 dimensions each).
[`configs/env/deployment.env`](../configs/env/deployment.env) holds the
values: `POSTGRES_CPUS` and `POSTGRES_MEMORY` (container limits),
`POSTGRES_SHM_SIZE` (`/dev/shm`), and `POSTGRES_SHARED_BUFFERS`,
`POSTGRES_MAINTENANCE_WORK_MEM`, `POSTGRES_EFFECTIVE_CACHE_SIZE` and
`POSTGRES_MAX_CONNECTIONS` (passed as `-c` options).

A vector is 4 KB and its HNSW index about the same again: 137,000 fact vectors
are about 1.1 GB with the index, and memory is three times the working set.
The shipped values fit the production corpus (about 300 documents, 20,000
passages, 137,000 fact vectors), ten times the reviewed build.

| Corpus | Passages | Fact vectors | `POSTGRES_CPUS` | `POSTGRES_MEMORY` | `POSTGRES_SHM_SIZE` | `POSTGRES_SHARED_BUFFERS` | `POSTGRES_MAINTENANCE_WORK_MEM` | `POSTGRES_EFFECTIVE_CACHE_SIZE` |
|---|---|---|---|---|---|---|---|---|
| The reviewed build | 2,000 | 14,000 | 1.0 | 1G | 256m | 256MB | 256MB | 640MB |
| Five times | 10,000 | 70,000 | 2.0 | 2G | 512m | 512MB | 512MB | 1280MB |
| Production (shipped) | 20,000 | 137,000 | 4.0 | 4G | 1g | 1GB | 1GB | 2560MB |
| Twenty times | 40,000 | 274,000 | 4.0 | 8G | 2g | 2GB | 2GB | 5GB |

- `POSTGRES_SHM_SIZE` is at least `POSTGRES_MAINTENANCE_WORK_MEM`. A container
  gets 64 MB of `/dev/shm` by default, and a parallel index build fails there
  with `could not resize shared memory segment`.
- `POSTGRES_MAINTENANCE_WORK_MEM` is the size of the largest index (the
  facts'). A smaller value spills to disk, and pgvector warns that the graph
  does not fit.
- `POSTGRES_MAX_CONNECTIONS` follows the processes: the API and each worker
  hold `DATABASE_POOL_SIZE` plus `DATABASE_POOL_OVERFLOW` connections (70 in
  all), the filer up to `WEED_POSTGRES_CONNECTION_MAX_OPEN` (50), and the
  other services and `psql` use the rest of the 250. Scaled workers add their
  share. Keep the total under 80% of the limit
  (`tests/static/test_env_files.py` checks the pool).
- A changed value needs `podman compose up -d postgres`, which recreates the
  container on its volume. No migration is needed.

### A smaller stack

A run needs only the database, the object store, the API and the stage workers
it uses. Logs, dashboards, review, Adminer and Dagster are optional, and the
`-start` targets and host drains need none of them.

```bash
make certs logs-dir
export COMPOSE_ENV_FILES=configs/env/deployment.env,.env
export COMPOSE_FILE=compose.yaml:compose.dev.yaml   # the development stack only; leave it out with HOST_RUNNER=1
podman compose up -d api phoenix seaweedfs-volume seaweedfs-volume2
make schema
```

`up` also starts PostgreSQL and the SeaweedFS master, filer and S3 gateway.
The volume servers are named because nothing depends on them. Add `streamlit`
for the pages. Then bring up one stage worker at a time, queue its stage and
stop the worker once the queue is drained:

```bash
export COMPOSE_FILE=compose.yaml:compose.dev.yaml   # the development stack only; leave it out with HOST_RUNNER=1
podman compose up -d parse-worker
make parse-start                 # make parse-status says when it is done
podman compose stop parse-worker
```

`make pipeline` and `make all` need Dagster. On this stack, use the `-start`
targets, or host drains while the stage's worker is stopped.

## A second stack beside the first

A second checkout needs its own project name and published ports. Compose
names containers, volumes, networks and images for the project (`qa_generator`
unless set), so the second stack has its own database, object store and
images. Set the name and the ten ports in the second checkout's `.env`, which
wins over `configs/env/deployment.env`. `make doctor` lists each name it
moves.

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

Every address derives from these ports, and `make services` lists them. The
smoke layer reads the project name and the Dagster port from the shell, not
`.env`:

```bash
COMPOSE_PROJECT_NAME=qa_second DAGSTER_WEBSERVER_PORT=23000 make test-smoke
```

## Scaling

`parse-worker` and `chunk-worker` scale horizontally (each claims one row at a
time with `FOR UPDATE SKIP LOCKED`).

`extract-worker` scales to two replicas at most, or one host drain beside one
replica. Two drains were measured on copies of the reviewed build and the shop
calibration corpus: 0.57 of one drain's time over 257 passages, 0.54 over 168
shop passages, and no claim kept twice. The store judges facts again under a
lock per language and kind (see the `duplicate` refusal in [the extraction
README](../backend/extraction/README.md)). More than two are not measured, so
a deployment runs no more ([Production deployment](#production-deployment)).

```bash
export COMPOSE_ENV_FILES=configs/env/deployment.env,.env
export COMPOSE_FILE=compose.yaml:compose.dev.yaml   # the development stack only; leave it out with HOST_RUNNER=1
podman compose up -d --scale extract-worker=2
```

Keep the drains within the database's connections ([Sizing
Postgres](#sizing-postgres)) and the provider's rate limit. On the Azure quota
this build ran on, two model drains ran without a failed row and six lost 3 of
10 topics to rate limits. A drain waits out a rate limit (`Retry-After`, ten
minutes at most per call) without using up `LLM_MAX_ATTEMPTS`, and five rows
in a row that the model could not be reached for stop it with exit 75. Run at
most two model drains against one database on that quota, and measure before
raising it.

- `question-worker` scales the same way, with one row per topic. It loads
  `EMBEDDING_MODEL` (2.2 GB) before it claims anything, and downloads it into
  the `models` volume if the extract worker has not. Topics stay `pending`
  until it finishes, and `make logs` says so. Its 6 GB limit covers that model
  and the `NLI_MODEL` weights, per container.
- `topic-worker` can be scaled with no gain: a fit is one request row.
- `assess-worker` is the cheapest to scale (no pretrained weights, 1 GB, one
  CPU). It does nothing until `ASSESSMENT_ENABLED` is true and reads the flag
  every `WORKER_POLL_SECONDS`, so switching it on from the Assessment page
  needs no restart. A change to `.env` reaches it with `make up`.

## Sizing a corpus

`make estimate` prints, for the rows still to do, the time, model calls and
spend of each stage before anything is queued. It multiplies them by what one
row took in the reviewed build (30 documents, 1,973 passages, 41 topics, Azure
models, 5 h 41 min and USD 75.53 end to end). Another provider or model split
has other rates: `make spend LOG=run.log` reads them off a run.

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

Row counts: a document is 66 passages, a topic holds 40 passages
(`TOPIC_PASSAGES_PER_TOPIC`, up to `TOPIC_NUM_TOPICS` a language) and leaves
53 accepted questions, and a run writes `QUESTIONS_PER_TOPIC` slots for each
topic. A stage whose workers scale (`DRAINS=questions=2`) divides its time by
the drains and keeps its spend.

The production corpus has 300 PDFs and 20,000 passages (ten times the reviewed
one), which give 410 topics and 21,750 accepted questions. One drain of each
stage takes 81 hours and costs USD 725. Lowering `QUESTIONS_PER_TOPIC` spends
less and scales the coverage down with it.

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

Two drains is what the current Azure quota carries. Measure a larger quota
before raising the number.

Also size [Postgres](#sizing-postgres), the parse worker's memory for the
longest document (`PARSING_MAX_PAGES`, 180 pages, about 3.1 GB of its 4 GB by
a curve measured on the host, not in the worker's Linux image) and the topic
worker's 3 GB (a 10,000 by 300 matrix for one language).

## What the model costs

[measurements.md](measurements.md) has per-call latency and per-stage spend of
the last run. Live, use the **2 · What each stage is doing** dashboard and
Phoenix. For a finished run, read a captured text log (not the shipped JSON):

```bash
make spend LOG=run.log
make spend LOG=run.log SINCE=2026-09-19
```

The cost log is the spend of record. The figure Phoenix shows is indicative,
because Phoenix prices a call on its own table of models. Where the two
differ, trust `make spend`.

## Replaying a call in the Phoenix playground

Open a `completion` span in Phoenix and replay it against a chosen model with
the prompt as sent. The playground works against Ollama only
(`OLLAMA_BASE_URL` is set to `OLLAMA_CONTAINER_URL`, and an `extra_hosts`
entry resolves `host.docker.internal`). With `OLLAMA_CONTAINER_URL` unset,
Phoenix falls back to `localhost:11434`, which inside its container is
Phoenix. `make prompts-publish` republishes all prompts.

## Dashboards

Grafana provisions four dashboards from `configs/grafana/` over three
datasources.

| Dashboard | Reads | Shows |
|---|---|---|
| 1 · Where the corpus is now | PostgreSQL | Queue depth per stage, failures with reasons, fact and question acceptance, topic coverage |
| 2 · What each stage is doing | Elasticsearch | Units finished per interval, model latency at p50/p95/p99, facts and questions accepted against refused |
| 3 · One run, end to end | all three | What one run produced, what it cost, its Phoenix projects, the gate verdicts, every line it wrote |
| 4 · Every line every process wrote | Elasticsearch | Lines per level, what failed and where |

Dashboard 3 joins `questions.run_id` to a Phoenix project named
`<position>-<stage>-<RUN_ID>`. Only a run named with `RUN_ID` gets a project
of its own. For how one artefact was produced, read the **How this was
produced** fold on its page. A model latency p99 climbing towards
`LLM_TIMEOUT_SECONDS` means a stage is about to fail rows: a slower call is
tried again up to `LLM_MAX_ATTEMPTS` times and then fails its row.

`grafana_reader` holds `SELECT` only. `configs/postgres/init.sh` creates it on
the first boot of an empty volume. On an existing volume, run it:

```bash
export COMPOSE_ENV_FILES=configs/env/deployment.env,.env
export COMPOSE_FILE=compose.yaml:compose.dev.yaml   # the development stack only; leave it out with HOST_RUNNER=1
podman compose exec postgres bash /docker-entrypoint-initdb.d/init.sh
```

`make up` and `make dev` grant `SELECT` on the five Phoenix tables the run
dashboard queries. `make grafana-grants` does it for a stack started another
way.

### Rotating `GRAFANA_SECRET_KEY`

1. Snapshot the `grafana_data` volume.
2. With Grafana running under the old key, `POST
   /api/admin/encryption/rotate-data-keys` as `GRAFANA_ADMIN_USER` (answers
   204).
3. Remove the signing keys Grafana stored under the old key, so it mints its
   own. Left in place, `/api/signing-keys/keys` answers 500. The repository
   has no command for this.
4. Put the new `GRAFANA_SECRET_KEY` in `.env` and recreate the `grafana`
   container (`make up` does so once the value changed).
5. Check that the three datasources report healthy and that alerting,
   dashboards and search load.

## Logs

```bash
make logs                          # everything, from the container engine
make logs-api
make logs-shipper                  # why nothing is arriving
make logs-retention                # how long Elasticsearch keeps them. Run once
make logs-prune                    # delete the files on the volume
make logs-wipe CONFIRM=<database>  # this database's lines; ALL_DATABASES=1 every stream and file. What make wipe runs
```

Filebeat ships this project's processes to Elasticsearch (containers write to
the `logs` volume, host commands to `./logs`; `host.name` tells them apart).
Other containers keep the `json-file` driver: read them with `make logs`.
`make logs-retention` ages what Elasticsearch holds and `make logs-prune` ages
the files. Nothing is deleted until the first has run.
[`telemetry/`](../telemetry/README.md) lists the field names.

## Backups

The archive (`make archive`) lives in the database and object store it
protects. A backup copies both elsewhere.

```bash
make backup DIR=/backups/$(date +%F)
```

`make backup`, `make restore-backup` and `make restore-backup-stack` dump and restore through the stack's postgres container, so they refuse a `DATABASE_URL` that names another host than `localhost` or `127.0.0.1` at `POSTGRES_PORT`. A managed database is backed up by its provider.

| Path under `DIR` | Content |
|---|---|
| `db/<name>.dump` | `pg_dump -Fc` of the application, SeaweedFS, Phoenix and Dagster databases |
| `s3/<bucket>/<key>` | Every object of the five buckets |
| `manifest.json` | Row counts of the application database's tables, and key, size and sha256 of every object and dump |

`make backup` never copies `.env`, `provider.env` or a certificate key. `DIR`
must hold no backup. Everything it writes is readable by its owner alone (700
and 600). Argilla's database is left out because its users table holds the
owner's API key in clear. `make backup DIR=... ARGILLA=1` adds it: store that
`DIR` as a secret and rotate `ARGILLA_API_KEY` if it leaks. Without it,
restore review datasets with `make review-push-*`. An answer not yet pulled
with `make review-pull-*` is not in the backup.

Stop the workers first (`podman compose ... stop parse-worker chunk-worker
extract-worker topic-worker question-worker assess-worker`): a worker still
writing makes the backup verify with differences. The command warns and does
not refuse. Copy `DIR` off the machine.

### The restore drill

Run it on a scratch stack before it is needed, and after any change to the
stores. It replaces the data of the stack it runs on.

1. Bring up a stack of the same version beside the first (see [A second stack
   beside the first](#a-second-stack-beside-the-first)), or reuse the same
   stack after `make down-volumes CONFIRM=all-volumes`, then `make up`.
2. Stop everything but postgres and seaweedfs (`docker compose` for docker;
   `ps` lists what else runs):

   ```bash
   podman compose --env-file configs/env/deployment.env --env-file .env stop api frontend parse-worker chunk-worker extract-worker topic-worker question-worker assess-worker dagster-webserver dagster-daemon phoenix argilla grafana
   ```

3. `make restore-backup DIR=/backups/<the directory> CONFIRM=<APP_DB_NAME>`.
   It refuses while a worker runs and unless `CONFIRM` names the database. It
   runs `pg_restore --clean --if-exists --single-transaction` as the superuser
   for the application database only, keeping the dump's owners, uploads the
   objects under the database's own prefix, and checks the dump, objects and
   every row count against the manifest. It exits 1 and names each difference.
   Shared stores (buckets, filer, Phoenix, Dagster, Argilla) and other
   databases' objects stay as they are.

   To restore the whole stack (five databases and every database's objects,
   Argilla's only if backed up), run `make restore-backup-stack DIR=...
   CONFIRM=stack`. It refuses while more than one application database exists,
   unless `ALL_DATABASES=1`.
4. `make up`, then `make schema-status` (newest revision) and `make
   documents`. Open a document's page and a topic figure.

A database upgraded to v0.5.2 holds its objects under bare keys until `make
s3-prefix` copies them under its prefix, and an earlier backup holds them
bare. `make restore-backup` restores the keys under the database's prefix and
the bare keys its rows name (documents, archived documents,
`topics/<database>/`). Other bare keys come back only with `make
restore-backup-stack`. `make s3-prefix` never overwrites. Bare objects are
never deleted: they stay after `make delete`, `make archive-purge` and `make
wipe-all` until a person removes them once every database has run `make
s3-prefix`.

### What Phoenix keeps

Traces hold the prompts a run sent, which contain source passages. `make up`
and `make dev` set Phoenix's default trace retention to
`PHOENIX_TRACE_RETENTION_DAYS` (30 where unset, in
`configs/env/deployment.env`). `make phoenix-retention` sets it again and
needs the stack up. Phoenix applies the policy weekly (Sundays 00:00 UTC), so
a trace can outlive the limit by up to seven days. A failure to set it is
printed and the stack still starts. A policy of zero is refused.

## Failure

The next run of a stage fails a row that a worker died holding and records the
reason. `retry` returns it to the queue. A stage's failure is never an HTTP
500: it is recorded against the row and read through `/{stage}/status`.

## Production host

On the production profile the host reaches a hosted provider, never a
container. The model stages (extraction, topics, questions, assessment) run on
the host through `make corpus-hosted`. The containers keep parsing and
chunking, which call no model, and the model workers stay stopped. Without
`HOST_RUNNER`, containers call Ollama.

### The runbook

From a fresh clone:

1. Clone outside any synced folder, and keep the secrets where only the
   operator can read them (see [Keeping the secrets out of the
   checkout](#keeping-the-secrets-out-of-the-checkout)).
2. `cp .env.example .env` and `chmod 600 .env`, because `cp` keeps the
   example's mode 644 and `make setup` sets 600 only on a file it creates.
   Then `make setup` to fill the passwords. The file ships the production
   split: `HOST_RUNNER=1`, the seven role models and
   `LLM_REASONING_EFFORT=none`
   ([configuration](configuration.md#the-production-split)). Put the
   provider's credentials in `configs/env/provider.env`, which is not in git,
   with the Azure resource's address:
   `AZURE_API_BASE=https://<resource>.openai.azure.com`, or `LLM_BASE_URL` in
   `.env`, which every role then uses. Without it every model call fails. Give
   `AZURE_API_KEY` there, or, with no key, run `az login` on the host: Entra
   ID takes its token from that login. `APP_DB_PASSWORD` may use only letters, digits, `-`, `_` and `.`: `make
   doctor` and `make corpus-hosted` refuse `@ / : # ? %` and name the setting.
3. `make install`, then `make docling-weights HOST=1`. `make install` sets up
   the host's virtualenv and spaCy pipelines and fetches Docling's weights
   into the `models` volume that the parse worker reads (the worker has the
   Hub off, so a fresh volume fails every document; this needs the container
   engine). `make docling-weights HOST=1` fetches the same weights into the
   host's Hugging Face cache, which `make doctor` and host drains read with
   the Hub off.
4. `make up`. With `HOST_RUNNER=1` the containers run the images as built, with no source mounted: a `git pull` changes nothing in them until `make upgrade` rebuilds the images and restarts the containers, so code changes reach the go-live stack only through `make upgrade`, while the host runner already runs the checkout. With `HOST_RUNNER=1` it starts postgres, the object store, the
   API, the parse and chunk workers, the web page and Phoenix. `make
   corpus-hosted` waits for the parse and chunk queues to empty before the
   model stages. This `make up` does not stop model workers (`local-models`)
   or Dagster (`orchestrated`) left up from development: `make doctor` and
   `make corpus-hosted` refuse while one runs and name the `compose stop`
   command. `make all`, `make pipeline`, `make auto` and the pipeline's routes
   refuse and name the host runner. A queue verb for a model stage (Start,
   `retry`, `rerun`, `reclaim`) still queues rows and answers 202, naming the
   command that drains them.
5. `make schema`, which creates the tables. The first upload to an empty
   database fails without it.
6. `make doctor`. It checks the split, asks every model one question, and
   reads the Hugging Face cache with the Hub off. It names any encoder (at its
   pinned commit) or Docling weight that is missing, which fails on this
   profile. Run the `poetry run hf download` line it prints where the Hub is
   reachable ([configuration](configuration.md#pinning-the-encoders)), then
   `make doctor` again.
7. `make ingest DIR=<folder of PDFs>` loads a corpus from the host, one line a
   file, under the limits the Upload page has stored. The Upload page is for a
   few files: it refuses more than 20 files or 200 MB at once. One file with
   curl: `curl -H "X-API-Token: $API_TOKEN" -F file=@x.pdf
   http://localhost:8000/documents`.
8. `make corpus-hosted SPEND_CAP=50`. It returns at once and the run continues
   detached. `logs/corpus-hosted.log` holds its output and
   `state/corpus-hosted.pid` the process group, database and leader's start
   time. `make corpus-hosted-stop` stops it. Every drain gets the database
   name and `HF_HUB_OFFLINE=1`, and a role that resolves to an Ollama model
   stops the run. Spend is counted across drains in
   `state/corpus-spend-<database>.usd` (`SPEND_LEDGER`), one ledger a
   database, so `SPEND_CAP` is the cost of the whole run. `make wipe
   CONFIRM=<database> ALL_DATABASES=1` and `make logs-prune` leave `state/`:
   keep it out of any clean-up while a run is recorded.
9. `make questions-export OUT=release.xlsx FILTER="--released"` and `make
   questions-export OUT=all.xlsx` when the run ends.

### A stale image

Each image bakes the hash of the lock it installed (`requirements.lock` for
the backend and page, `requirements.txt` for Dagster). Every container
compares it at start with the checkout's own where the development override
mounts it, and with the image's own copy where nothing is mounted (the go-live
profile), which passes by construction. After a lock changed, a
container logs `run compose build, then make up`, waits ten minutes and exits.
Rebuild, then `make up`:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build
```

### Keeping the secrets out of the checkout

A checkout inside a synced folder (`~/Library/CloudStorage`, `OneDrive`,
`Dropbox`, `Box Sync`, iCloud Drive) is copied to the sync provider and to
every signed-in device, `.env` and `provider.env` with it.

1. `git clone` into a folder that no sync client watches, such as
   `~/srv/qa_generator` or `/srv/qa_generator`. `make doctor` warns when the
   checkout or the secrets file sits in a synced folder.
2. Put `.env` where only the operator can read it, for example
   `/etc/qa/secrets.env` with mode 600 (no spaces in the path), and run every
   command with `ENV_FILE=/etc/qa/secrets.env` or export it once. Host
   commands source that file and compose is handed it.
   `configs/env/provider.env` also holds credentials: keep it out of git and
   out of any backed-up folder.
3. Rotate every key after the move. The sync service has read the old `.env`:
   passwords, `PHOENIX_ADMIN_SECRET`, `GRAFANA_SECRET_KEY`, the Argilla key
   and the provider's credentials. `make setup` fills placeholders, and the
   provider's key is rotated in its own console. Delete the old file and the
   synced copy of the checkout.
4. Leave `.env`, `ENV_FILE`, `provider.env` and the keys under `certs/` out of
   backups.

### Upgrading a deployment

`make upgrade` takes the stack to the code in the checkout: it checks the
engine has `UPGRADE_FREE_GB` free (20 by default, read in the podman VM),
builds, prunes the images the build orphaned, stops the workers, runs `make
schema` and runs `make up`. It stops at the first step that fails. Run it
after `git pull` and before `make corpus-hosted`. An upgrade section below
that says to rebuild and run `make up` means this command.

### Profiles

With no profile named, compose starts eleven services: the database, the
object store (master, two volumes, filer, S3 gateway), the API, the parse and
chunk workers, the page and Phoenix.

| Profile | Services | Started by |
|---|---|---|
| `local-models` | the extract, topic, question and assess workers | development `make up`; never on the production profile |
| `orchestrated` | Dagster's webserver and daemon | development `make up`; never on the production profile |
| `review` | Argilla, Redis and Elasticsearch | `COMPOSE_PROFILES=review` in `.env` |
| `logs` | Filebeat and Grafana (need `review`) | `COMPOSE_PROFILES=review,logs` |
| `tools` | Adminer | `COMPOSE_PROFILES=tools` |

`make up` enables every profile unless `HOST_RUNNER` is set, in which case it
enables what `COMPOSE_PROFILES` names, except the first two. Other `make`
targets see all profiles, so `make down` stops any service. `make wipe` skips
the Argilla, Elasticsearch and Dagster steps of a service that is not running,
says so, and still empties the log files.

### After a stop

A drain that stopped itself (the model could not be reached, or the cap was
reached) exits 75 and gives its rows back. A failed row exits 3. Either stops
the run before the next stage.

| Exit | Meaning |
|---|---|
| 0 | The run finished |
| 3 | A row failed, or the start was refused |
| 75 | The drain stopped: `SPEND_CAP`, a model that cannot be reached, or a signal |

A run that ends without finishing keeps its pid file. `make corpus-hosted`
after a stop, a crash or a kill resumes it: it returns every stage's failed
rows to the queue and runs the chain again on the recorded database, and the
spend so far still counts against `SPEND_CAP`. Only a finished run, or `make
corpus-hosted RESET=1`, makes the next run fresh with the count started again.
A start that names another database than a stopped run's is refused.

A second `make corpus-hosted` while the first runs is refused. Each database
has its own ledger. A `make corpus` on the same database refuses beside a
hosted run, and while a stopped run is recorded unless it uses `RESUME=1`.

A resume returns every stage's failed rows to the queue first, so a row that
fails every time (a document parsing refuses for its language, an empty or
broken PDF) stops every resume at the same stage with exit 3.
`logs/corpus-hosted.log` names each failed row and its error. Then:

- `make delete SHA=<sha256> CONFIRM=<database>` removes a document that cannot
  be processed.
- Once the cause is fixed, the stage's `-retry` target returns that row alone:
  `make parse-retry SHA=<sha256>`, `make extract-retry PASSAGE=<id>`.
- `make corpus-hosted RESET=1` starts a fresh run. It retries no failed row
  and starts the spend count again.

`make corpus-hosted-stop` sends TERM to the whole group. The drain in hand
finishes or gives back its row and exits 75, and anything left is killed after
300 seconds. The ledger and pid file are kept, so the next `make
corpus-hosted` resumes.

A supervisor runs `scripts/corpus-hosted.sh`, the detached runner, in the
foreground. It takes `make corpus`'s command line, keeps the same pid file and
ledger, resumes an unfinished run by itself (so no `RESUME=1`), and exits with
the code of the stage that ended the run (0, 3, 75, or anything else for a
crash). Only a crash is restarted. Every start runs `make corpus-preflight`
(production profile, no model worker or Dagster up, the split, the password
and the cache) and refuses with 3 where it fails. Its `PATH` must reach
`make`, `poetry` and the container engine, and `ENV_FILE` is given where the
secrets live outside the checkout.

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

`KillMode=mixed` sends the stop to the runner alone, which passes it on once.
`TimeoutStopSec` outlasts the runner's 300 seconds.

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
across restarts. A unit enabled at boot starts a fresh run after one that
finished, which draws the release again at the verifier's cost: disable the
unit once the run is done.

## Upgrading the schema on a stack with data

`make schema` applies each revision in its own transaction. A revision that
cannot get its lock within 5 seconds fails instead of waiting (a statement may
run 10 minutes). Find what holds the table (a drain, a worker, a long `make`
command), stop it and run `make schema` again: applied revisions stay applied.
Order: stop the stage workers and host drains, `make backup`, `make schema`,
build the images, `make up`. `backend/database/README.md` describes the CHECK
and backfill rules.

## Production deployment

This section lists what a production deployment holds and the conditions under
which known open items stay out of the way. It covers about ten times the
reviewed build (300 PDFs, 20,000 passages, German and English). Items carry
the review's number (`C-` and three digits, as `docs/bugs.md` and
`docs/changelog.md` give them). A
condition that a release fixes moves to that release's upgrade notes
([Upgrading to v0.5.3](#upgrading-to-v053) lists the latest). Settings are in
[configuration](configuration.md#production-settings), and [the
runbook](#the-runbook) reaches the deployment from a fresh clone.

### The model split

- The measured split (C-051) ships in `.env.example`
  ([configuration](configuration.md#the-production-split)): writer
  `azure/gpt-5.6-sol` at `LLM_REASONING_EFFORT=none`, extraction and phrasing
  `azure/gpt-5.4`, digests and judge `azure/gpt-4o`, verifier and topic naming
  `azure/gpt-4.1`.
- With `HOST_RUNNER=1`, a drain and `make doctor` refuse a role that resolves
  to an Ollama model (C-006, C-013). Every role uses `LLM_BASE_URL` unless `LLM_BASE_URLS` names its own (C-366).

### Settings

- Model stages run on the host (C-006): `HOST_RUNNER=1`, `make corpus-hosted`,
  model workers stopped. A run refuses to start while a model worker or
  Dagster container is up (`make corpus-preflight`). `make all`, `make
  pipeline`, `make auto` and the pipeline's routes refuse (C-073).
- The host runner reads `ASSESSMENT_JUDGE_MODEL` from `.env` and credentials
  from `configs/env/provider.env` (C-006). `make doctor` refuses an unset
  judge while `ASSESSMENT_ENABLED` is true. The Assessment page shows the
  containers' judge, so on this profile it says the next run judges nothing:
  it describes the stopped workers.
- The model cache is filled once and read offline (C-072, C-117; [Pinning the
  encoders](configuration.md#pinning-the-encoders)). `make corpus-hosted`
  refuses an incomplete cache before it detaches. Point
  `DOCLING_ARTIFACTS_PATH` at prefetched parser weights where they are not in
  the cache.
- Spend cap (C-091): `make corpus-hosted SPEND_CAP=<USD>`, counted across the
  run's drains. A drain refuses a model litellm cannot price (C-219).
- Entity and temporal questions stay off (C-176, C-217): weight 0 in
  `QUESTIONS_TYPE_MIX` and `QUESTIONS_RELEASE_TYPES`. Calibrate each on the
  production corpus before giving it a weight.

### Resources

- Postgres as shipped (C-011): `configs/env/deployment.env` ships the
  production row of [Sizing Postgres](#sizing-postgres). `make test-perf` runs
  the 10x load test, which asks a dedup probe and a fact write to stay within
  twice their time at the reviewed build's size. On the CI runner the
  single-pass probe p95 swung from 1.99x to 16.61x on one unchanged commit,
  so its 2x bar measures the runner (N-035 in [bugs.md](bugs.md#failed-bar)).
  The sizing ships with that limit by decision: the database is about 2% of a
  drain's time at ten times the build.
  If the probe time climbs, raise `POSTGRES_MEMORY` and
  `POSTGRES_SHARED_BUFFERS` to the table's next row.
- The podman VM's memory is at least the sum of its services' limits
  ([Memory](#memory)): about 15 GiB for the eleven production services.
- `make upgrade` refuses below `UPGRADE_FREE_GB` (20) free in the engine.
- At most two drains of a model stage a database, and at most two of
  extraction (C-082, C-026).
- Time and spend (C-084): `make estimate`. [Sizing a corpus](#sizing-a-corpus)
  gives USD 725 and 81 hours under `make corpus-hosted`, which runs one drain
  a stage. A second drain started by hand does not count against `SPEND_CAP`.

### Backups

- `make backup` before every upgrade and every wipe (C-003), copied off the
  machine, plus [the restore drill](#the-restore-drill) on a scratch stack.
- The archive bucket is the only copy of a deleted row's objects. Purge it per
  database on a cadence, after a backup ([Deleting things](#deleting-things)).

### Monitoring

- Alert on a non-zero exit (C-009, C-091): 3 a row failed, 75 the drain
  stopped itself ([After a stop](#after-a-stop)).
- Every log line carries `db` (C-005). Set `PHOENIX_TRACE_RETENTION_DAYS`
  (C-103), applied by `make up`: read its output, because a failure is printed
  and the stack starts anyway.
- The release draw takes 10.6 s at 21,750 accepted questions (C-089).
- The nightly's Model quality job is skipped until the repository owner sets
  the variable `LLM_MODEL` and the secrets `AZURE_API_KEY`, `AZURE_API_BASE`
  and `AZURE_API_VERSION` in the GitHub repository settings. Until then the
  run shows it skipped, not green; once set, a model that does not answer
  fails it.

### Before the first production release

- Label a sample. Quality figures were measured on football regulations and
  the shop calibration corpus, and tables read worst. Label 60 released rows
  per language blind under the rubric, reading the table slice and the
  two-passage slice apart. Use the release only if it meets the review's bar:
  usable at least 0.723, invalid at most 3.4 per 60 (about two hours, no model
  call).
- Read the table slice apart until C-097 (a wrong section path) and C-282 (a
  second tier joined to the row above) ship.
- Report the release as a whole or each slice with its own share. Released
  two-passage questions were 0.548 usable (n 126) and accepted hard questions
  0.514 (n 70), against 0.841 for the release. 13 of the 128 released
  unanswerable questions are answered by the corpus and 11 are invalid, so a
  refusal evaluation drops or rechecks them. The automatic judge agrees with
  the labels at kappa 0.18, close to chance: quality figures need labels.

### The conditions that still hold

| Item | Condition | What lifts it |
|---|---|---|
| C-026 | At most two `extract-worker` replicas, or two extraction drains, a database: `--scale extract-worker=2` | Measuring three or more drains on a copy |
| C-082 | At most two model drains a database on the current Azure quota (six lost 3 of 10 topics to rate limits) | A larger quota, measured first |
| C-085 | Every published port stays on 127.0.0.1 and one operator uses the host: `API_TOKEN` is shared and the pages have no login | A login on the pages and the API |
| C-366 | A split across Azure resources names an address per role in `LLM_BASE_URLS`; every role left out is on `LLM_BASE_URL`, and credentials are one set per provider | One credential per resource |
| C-106 | Ingest only documents the corpus owner authored or controls: the writer, verifier, phrasing and judge prompts fence a document's text (v0.5.3), but the extraction, digest, bridge and topic-naming prompts send it as it is, so a planted instruction can still reach a fact | Fencing the extraction prompts (tried in v0.5.2 and withdrawn: fenced extraction narrowed 10 of 60 facts against 7 unfenced, over the bar of 9) |
| C-114 | Load bulk corpora with `make ingest DIR=`. The Upload page refuses more than 20 files or 200 MB, but Streamlit uploads every picked file into its 1 GB process first, so a large selection can kill it | A check before the upload, which Streamlit cannot make |
| C-066 | `make questions-export` and the pages write the same streamed workbook: the API holds a batch, not the corpus (it failed past about 13,000 questions in v0.5.1). Prefer `make questions-export` for more than 70,000 until it is measured on the go-live copy | A 70,000-question export measured through the API on that copy |
| C-029 | Report the difficulty band as retrieval spread, never as hardness, and leave `QUESTIONS_RELEASE_DIFFICULTY` unset | A grading of how hard a question is to answer, not built |
| C-031 | Leave distant-from-document out of per-category reports: most of its released rows use the document's words | A per-question word-distance reading (deferred) |
| C-052 | Before a release from price lists or fee schedules, read by hand the questions whose explanation states a space-grouped amount (`12 500 €`): a wrong total can pass the explanation check | The arithmetic check's model call |
| C-056 | Before ingest, count the image-only PDFs: a scanned document is refused, and an image-only page only draws a warning | OCR (C-083) |
| C-083 | OCR stays off | A measured OCR pass on the production corpus |
| C-140 | Before production, measure text nested in pictures on the shop calibration database (`qa_cal_shop`): banners and infographics may carry statements that reach no passage | A filter that tells a statement from a diagram label (the v0.5.2 clause filter was withdrawn) |
| C-266 | Before production, measure on the shop calibration database the questions drawn from imprint, hotline and contact passages | A passage gate on contact shapes (deferred) |
| C-278 | Before ingest, compare the widest table rows with the chunk's token budget (`EMBEDDING_MAX_TOKENS` less the embedder's own tokens): a longer row is cut mid-cell. Ship the fix first if any exceeds it | Keeping a row whole in one passage (deferred) |
| C-295 | Choose the embedding model before production and change it only through a migration and a full re-embed: editing `backend.env` would mix two models' vectors | A guard that refuses vectors of another model |
| C-419 | Check any tracked-change export before ingest: only a drawn horizontal strike is read as struck-through | A strike reading for tracked changes (deferred) |
| C-424 | Leave `QA_MODEL` empty, as it ships, until an encoder is calibrated | A calibration of one encoder |
| C-297 | Build the production images once, record their digests, and rebuild only on purpose: installs are not hash-checked and base images are named by tag | Locked installs, images by digest (deferred) |
| C-162 | Rolling back `733a3eadef7c`, past v0.4.2, drops every rubric score for good: they are not archived, since a restore would put back rows the narrower CHECK refuses | Archiving them in a form a restore can read |
| C-200 | Leave the nightly schedule off: it ignores Stop and `INGESTION_OPEN`. The production profile runs no Dagster | A schedule that skips after a cancelled run (deferred) |

## Upgrading

Each section lists the steps from the release before it, newest first. Unless
a section says otherwise, an upgrade is `make upgrade` (see [Upgrading a
deployment](#upgrading-a-deployment)): rebuild the images and `make up`. Run
`poetry install` on a host checkout when `poetry.lock` changed. A build made
from scratch needs none of the reruns. A stack on v0.3.12 follows the v0.4.0
or v0.5.0 section instead of the v0.3.13 to v0.3.36 sections.

Reruns bring stored data up to what a release reads differently. Run only
those the corpus needs. Each `make *-rerun` drains on the host and refuses
while the stage's container worker runs. To use the container workers, rerun
from the stage's page or `POST /{stage}/rerun?confirm=true`.

## Upgrading to v0.5.5

The deep QA release after v0.5.4, the last of this QA cycle. It adds one
migration, removes `make dagster-dev`, and refuses an `S3_BUCKETS` that gives
two roles one bucket, which a deployment may have to change before it pulls.
No lock, prompt or committed env file changes. `docs/changelog.md` lists each
fix and closed item under v0.5.5, and `docs/bugs.md` the accepted ones.

### 1. Before the pull: one bucket a role

`S3_BUCKETS` now refuses any two roles that resolve to one bucket, a default
name included (`documents=x,archive=x`, or `archive=documents`), with a
message naming both roles and the bucket. Under v0.5.4 an archive purge
deleted every live file that the archive's bucket shared with another role
(N-118). The backend reads the setting as its object-store code loads, so
with a shared bucket the api, the workers and every host command that reaches
the store fail. The shipped value, `documents,parsed,models,export,archive`
in `deployment.env`, names five buckets and needs nothing.

A deployment that gives two roles one bucket gives each role its own before
it pulls, moving the role's keys into the new bucket first, the archive's
above all, and only then changing `S3_BUCKETS`. Run no `make archive-purge`
before the move: the archive holds its keys under the database's prefix
beside the live ones, and the purge covers every key of the database in its
bucket, so it would delete live files. [The five
buckets](../backend/blob_store/README.md#the-five-buckets) gives each role's
key; an archived copy is `{database}/{origin}/{the key it had}@{UTC time}`.

### 2. Pull, code and images

```bash
git pull
podman compose --env-file configs/env/deployment.env --env-file .env stop parse-worker chunk-worker extract-worker topic-worker question-worker assess-worker
make backup DIR=/backups/$(date +%F)
make upgrade
```

- No dependency changes: `poetry.lock` and the image locks are v0.5.4's, so
  `poetry install` is not needed. The prompt versions and the committed env
  files are v0.5.4's too.
- `make upgrade` rebuilds the images with the new code and runs `make
  schema`, which applies step 3.

### 3. One migration

The head before this release is `9e3b61d4a2c7`.

| Revision | What it does |
|---|---|
| `c5a82e17d3f9` | Rewrites the comment of `questions.status`: a rejected question is kept, and so is one that lost its last citation (`source_changed`), and deleting a document, or what was derived from it, deletes its questions, rejected ones included. Comment only, and instant. The new head (N-117) |

`make schema-down CONFIRM=<database>` takes it back, once, before checking
out v0.5.4.

### 4. `make dagster-dev` is removed

`make dagster-dev` served Dagster's webserver on the host through plain
`dagster dev`, without `orchestration/serve.py`, so a web page open in the
operator's browser could launch or stop a run through a cross-site GET
(N-131). Use the compose webserver instead: `make up` on the development
profile mounts the checkout over the image, and the webserver refuses GraphQL
over GET and cross-site writes. A static test fails on any recipe, compose
command, image command, workflow or script that starts the webserver another
way.

### 5. Reruns, in order

None is needed to start v0.5.5. Each brings stored data up to what this
release reads differently, and most change nothing on the calibration
corpora. The counts are of the 30 football and 50 shop calibration PDFs and
their stored rows. A rerun without `SHA` refuses unless `CONFIRM` names the
database, and a re-chunk over questions refuses unless `FORCE=1`.

| Step | Command | Needed because of |
|---|---|---|
| Parse | `make parse-rerun CONFIRM=<database>` | Only for a corpus with a table that goes on onto the next page with footnotes or captions under its rest: the table now takes them, so they reach a passage (N-104). None of the 80 PDFs has such a rest |
| Chunk | `make chunk-rerun CONFIRM=<database> FORCE=1` | A list the converter splits at a page break keeps its depth, each page's indent read off its own edge (N-101, N-102, N-154): 37 football passages in 7 documents change, 0 shop, and no letter changes. The facts that cited the replaced passages go with them, and the questions resting on them are rejected as `source_changed` and kept |
| Extract new passages | `make extract-start`, then `make extract` | Re-chunked passages have no facts yet |
| A language added | `make chunk-revocabulary`, then `make extract-start` | Only after adding a language to `NLP_MODELS` on a chunked corpus: a passage stored as read for want of a pipeline goes back to `new` once it has a language, unless a fact cites it, and `extract-start` queues it (N-106). A `chunk-rerun` that keeps the passage's row does the same. No stored passage of the calibration corpora is affected |
| Dedup | `make extract-dedup` | Optional. It re-decides the stored `duplicate` refusals under the gate's new reading of units, months, weekdays and pairings (N-107). 0 of 753 stored refusals change |
| Judge facts again | `make extract-revalidate` | Optional. A list line cited beside a sentence is its own evidence, and a re-paired time or date is refused (N-108, N-109). 0 of 20,888 stored verdicts change |
| Stored questions | `make questions-reverify` | Optional. A German comparison answered *X ist schneller als Y* is no longer refused (N-133). 0 of 4,348 stored verdicts change |
| Refit, questions and release | `make topics-discover`, `make questions-rerun CONFIRM=<database>`, then `make questions-balance` | After a re-chunk, as in step 5 of [Upgrading to v0.5.3](#upgrading-to-v053): re-chunked passages belong to no topic yet, and reach questions only through the refit and a question run |

### 6. What else changes

- When the orchestrator refuses, the answer no longer carries Dagster's
  text, which named its database's host, address and role (N-130). The
  `orchestrator_refused` detail of `GET /pipeline/runs` and of the pipeline
  writes, and `orchestration.detail` of `GET /pipeline`, are a fixed
  sentence with the error's type and a trace id, such as `the orchestrator
  could not list its runs (PythonError); the api log holds why, trace <id>`.
  Dagster's words are in the api log under that id. A caller that
  matched Dagster's wording matches the type now.
- A row deleted, or claimed by another worker, while a drain fails or
  releases it is logged once as a warning naming the key and counted as no
  failure. Extraction's drain, `make extract` and `make corpus-hosted` take
  the next row instead of ending with a traceback (N-121).
- `make restore-documents AT=<archived_at>` puts back each object's archived
  copy stamped nearest the chosen deletion, the latest chosen one's where two
  took the same key. A rollback of a failed delete still takes the newest copy
  (N-119). An object the chosen deletion never archived still comes back as
  another deletion's copy (N-139 in `docs/bugs.md`).
- `make ingest DIR=` refuses a file past `MAX_FILE_SIZE_MB` unread and reads
  any other to at most the limit plus one byte, as `POST /documents` does
  (N-132).
- Two release writes at once no longer leave both draws released: the second
  waits for the first (N-114). The run comparison counts a restored question
  once (N-115).
- A quoted heading links to another document's section only where the
  quote's sentence names that document's full title (N-111). Links are not
  stored, so nothing needs a rerun. The bridges already written on a pair
  that is no longer linked stay until a bridge pass replaces them.

## Upgrading to v0.5.4

The follow-up release after v0.5.3. Nothing changes for a running
deployment: no migration, setting, prompt or lock change, and no rerun. The
backend image copies `pyproject.toml`, whose pytest options changed, so `make
upgrade` rebuilds it with the same code. `docs/changelog.md` lists what
changed under v0.5.4.

- `configs/audit-accepted.txt` accepts filelock 3.32.7's advisories until
  2026-12-31. After that date `make audit` fails until the entries are read
  again.
- CI and the Nightly stop a hung job after at most twice its longest recent
  run, and GitHub shows it as cancelled. A test that runs longer than ten
  minutes prints every thread's stack into the log first.
- A Nightly started by hand takes an optional seed. `gh workflow run
  nightly.yml -f seed=<n>` repeats the test order of a run whose log printed
  `Using --randomly-seed=<n>`.

## Upgrading to v0.5.3

The QA and fix release after v0.5.2. It also puts each infrastructure
component behind a port, chosen by a setting whose default is today's adapter,
so an Azure adapter can later replace one without touching its callers
([Swapping a component](architecture.md#swapping-a-component)). Nothing
changes by default. `docs/changelog.md` lists each fix and closed item under
v0.5.3, and `docs/bugs.md` the accepted ones. A build from scratch needs only
steps 1 and 2.

### 1. Pull, code and images

Before `git pull`, set aside local edits of the committed env files: this
release adds lines to `backend.env`, `deployment.env` and `review.env`.

```bash
git pull
make setup        # replaces any change_me_ value left in .env
chmod 600 .env configs/env/provider.env
podman compose --env-file configs/env/deployment.env --env-file .env stop parse-worker chunk-worker extract-worker topic-worker question-worker assess-worker
make backup DIR=/backups/$(date +%F)
make upgrade
```

- No dependency changes: `poetry.lock` and the image locks are v0.5.2's, so
  `poetry install` is not needed.
- `make up` and `make upgrade` refuse while `.env` (or `ENV_FILE`) holds a
  `change_me_` value, and the API treats a `change_me_` `API_TOKEN` as no
  secret: it refuses every write and settings read (N-076). `make
  placeholders` runs that check alone.
- `make setup` creates `.env` and `provider.env` readable by the owner alone,
  but leaves an existing file's mode as it is: hence the `chmod`. `make doctor`
  warns while either is readable by group or others (N-073).
- `compose.yaml` mounts no checkout path: every image runs from its own files.
  `make up` adds `compose.dev.yaml`, which mounts the source over the images,
  on the development profile only. On the go-live profile code reaches the
  containers only through `make upgrade`, which rebuilds the images before it
  restarts them. A bare `podman compose` command on a development stack needs
  `COMPOSE_FILE=compose.yaml:compose.dev.yaml`, or it recreates the
  containers without their mounts ([What compose
  reads](configuration.md#what-compose-reads)).
- Every service has a health check. A worker's tests that its first process
  is Python.

### 2. Two migrations, in order

The head before this release is `4a7c2e91d3b8`. Each revision runs under the
5-second lock timeout of [Upgrading the schema on a stack with
data](#upgrading-the-schema-on-a-stack-with-data).

| Revision | What it does |
|---|---|
| `5c1e8a3f7d20` | `archive_deleted_row()` skips the tables a transaction names in `qa.archive_skip`. A topic fit names `topics` and `passage_topics`, so a refit archives no topic rows. Every other deletion archives as before (C-420) |
| `9e3b61d4a2c7` | Adds `passages.nearest_foreign_cosine` and `passages.nearest_foreign_doc`, the cosine to the closest passage of another document in the same language and that document, and fills them for every embedded passage. The backfill commits 500 passages at a time, outside the revision's transaction. Each batch compares its passages with every embedded passage of their language, so time it on a copy of a large corpus first. A stopped backfill leaves the revision unstamped, and the next `make schema` resumes it (C-100). The new head |

`make schema-down CONFIRM=<database>` takes back one revision a run. Run it
twice to return to `4a7c2e91d3b8` before checking out v0.5.2: the first run
drops the two columns, the second puts the archive function back. A downgrade past `733a3eadef7c` (v0.4.2) now deletes every
rubric score without archiving it, so a later restore no longer fails on them,
and the scores are gone for good (C-162).

### 3. Settings

New. Each defaults to what the stack did before, so an env file without its
line still loads. Most choose the adapter of one port, and where the table
names one value it is the only adapter there is ([Which
adapter](configuration.md#which-adapter)):

| Setting | File | Default and values |
|---|---|---|
| `OBJECT_STORE` | `deployment.env` | `s3` |
| `DATABASE_AUTH` | `backend.env` | `url`: the password inside `DATABASE_URL`, asked each time a connection opens |
| `ORCHESTRATOR` | `deployment.env` | `dagster`, or `none`, which reads as no orchestrator whatever `DAGSTER_URL` is |
| `API_AUTH` | `backend.env` | `token`: the shared `API_TOKEN` |
| `LLM_CLIENT` | `backend.env` | `litellm` |
| `TRACE_STORE` | `deployment.env` | `phoenix`, or `none`: spans still go out over OTLP, annotations and published prompts stay in Postgres alone, and a golden-set upload or experiment is refused |
| `REVIEW_TOOL` | `review.env` | `argilla` |
| `LOG_FORMAT` | `deployment.env` | `text`, or `json`: stdout carries one JSON object a record, with the file's fields |
| `SERVICE_PROBES` | `deployment.env` | What the System health page probes, as `name=host:port` (`name=` for a process with no port). Ships the compose stack's list |
| `GRAFANA_DB_HOST`, `GRAFANA_DB_SSLMODE`, `GRAFANA_ELASTICSEARCH_URL` | `deployment.env` | `postgres:5432`, `disable` and `https://elasticsearch:9200`: where Grafana's datasources point |
| `LLM_BASE_URLS` | `.env` | Unset. An address of its own for a role, as `role=address` entries over writer, verifier, phrasing, extraction, digest, topics and judge (C-366) |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | none (the OpenTelemetry variable) | Unset reads `grpc`; `http/protobuf` for a collector behind an HTTPS ingress. Any other value is refused |

None is retired. Changed:

- `S3_BUCKETS` is read: the backend takes its five bucket names from it, where
  they were fixed in code, and an entry may be `role=bucket`
  (`documents=acme-docs`). Each bucket is checked by name, and the account's
  buckets are never listed, so a credential limited to its buckets works
  (N-063).
- `LLM_BASE_URL` serves every role that `LLM_BASE_URLS` leaves out. Credentials
  stay one set per provider.
- `DATABASE_URL`, `BACKEND_URL`, `S3_ENDPOINT`, `PHOENIX_BASE_URL`,
  `OTEL_EXPORTER_OTLP_ENDPOINT` and `ARGILLA_API_URL`: a host command keeps the
  value `ENV_FILE` or the environment gives, and builds it from `localhost`
  and the published port only when it is unset (N-064). A `DATABASE_URL`
  exported in a shell used to be overwritten and is now used. A given
  `DATABASE_URL` must name the database `APP_DB_NAME` names, or every target
  that loads the settings refuses, naming both. One that names no database is
  refused (N-070).
- `API_TOKEN`: a `change_me_` value counts as no secret (step 1).
- `PHOENIX_DB_PASSWORD`, `ARGILLA_DB_PASSWORD` and `ELASTICSEARCH_PASSWORD`:
  `make doctor` now refuses `@ / : # ? %` in them, as in `APP_DB_PASSWORD`,
  because compose writes each into a URL. A quote in a role password no longer
  breaks the first boot (N-072).
- `LOG_DIR`: an unwritable directory is reported as a record on stdout, where
  it was a bare line on stderr. With `LOG_FORMAT=json` it may be left empty,
  and no file is written (N-065).
- `EXTRACTION_DUPLICATE_COSINE` at 0 turns the duplicate refusal off and still
  writes the vectors (C-245).

### 4. Prompts and model calls

- Writer 32 becomes 35, verifier 15 becomes 17, `verifier: stated` 1 becomes
  3, phrasing 5 becomes 8, and the assessment judge 4 becomes 5. Unchanged:
  atomic extraction 12, repair-1, digest 5, bridge 6, topic naming 3. Stored
  rows keep their version.
- The writer, verifier, phrasing and judge prompts send a document's text
  between material tags, under a line saying it is never an instruction
  (C-106). Their worked examples come from libraries, permits, leases and
  catalogues (N-052). The extraction, digest, bridge and topic-naming prompts
  send the text as before.
- The first `make questions-rejudge` asks again about every stored accepted
  unanswerable question, because its verdicts were given under verifier 15:
  one `settles` reading each, and a second where the passages are silent and
  the probe is on.
- The two-passage readings stored under `verifier: stated` 1 keep that version,
  and the prompts table keeps the text they were read under, so they stay told
  apart from readings under 3. No command reads them again: only a question
  written from now on is read under 3.
- No model call is added or removed.

### 5. Reruns, in order

None is needed to start v0.5.3. Each brings stored data up to what this
release reads differently. A rerun without `SHA` refuses unless `CONFIRM`
names the database, and a re-chunk over questions refuses unless `FORCE=1`.
A re-chunk rejects the questions resting on a passage it replaces as
`source_changed` and keeps them. The new passages reach questions only through
the refit and the question run below.
The counts are of the 30 football and 50 shop calibration PDFs and their
stored rows.

| Step | Command | Needed because of |
|---|---|---|
| Ingest again | `make ingest DIR=<folder>` | A PDF refused `unsupported_type` because its header followed a few leading bytes (C-186), and a folder whose run stopped at a file name that is not UTF-8 (N-007). A file already stored is refused as `duplicate_bytes`, so the run is safe to repeat |
| Parse | `make parse-rerun CONFIRM=<database>` | A paragraph number printed in the left margin now opens its paragraph (N-057): 819 lines in three football documents |
| Chunk | `make chunk-rerun CONFIRM=<database> FORCE=1` | List markers the document does not print (N-003, 83 in 35 passages), a passage in an unconfigured language reads no language (N-004, none of the stored passages), one-page chapters (N-005, 6 passages) and heading fragments (N-006, 2 passages), all football |
| Extract new passages | `make extract-start`, then `make extract` | Re-chunked passages have no facts yet |
| Judge facts again | `make extract-revalidate` | The fact check's figure, unit, date, list-line and reference fixes (N-012, N-013, N-016, N-017, N-019, N-020, N-037, N-042, N-043, N-046, N-049, N-051, N-055, N-056, N-062). No model call. On the stored facts only N-037 moves a verdict: 17 stored refusals newly validated (15 usable) |
| Cap again | `make extract-recap` | Lettered, roman and en-dash list items count toward the cap (N-021): 7 stored passages count more items |
| Dedup | `make extract-dedup` | A refusal whose twin went in a deletion through the pages or the API before this release. `make corpus` now replays it itself (C-054) |
| Vectors | `make extract-embed` | Passages and facts a stage left without vectors at `EXTRACTION_DUPLICATE_COSINE=0` (C-245), and restored questions with none (C-331) |
| Refit topics | `make topics-discover` | Re-chunked passages belong to no topic yet |
| Questions on the new passages | `make questions-rerun CONFIRM=<database>` | Writes questions about the facts no accepted question rests on, the re-chunked passages' among them, at the writer's cost |
| Stored questions | `make questions-reverify`, then `make questions-rescore` after a refit | The structural and type gates: amounts, counts, periods, question words and marks, and the language check (N-022, N-023, N-029, N-039, N-040, N-045). No stored verdict changes. The `leaks_source` fixes (N-027, N-047, N-054) act on new questions only, since this re-check does not run that gate |
| Unanswerables | `make questions-rejudge` | Verifier 17 (step 4). Calls the verifier |
| Release | `make questions-balance` | Rejected rows leave it |
| Export | `make questions-export` | The workbook is streamed. Text opening with `=`, `+`, `-` or `@` is stored as text, long cells are cut and marked, Citations gives first and last page as integers, a sheet past Excel's row limit continues in a numbered one, and the Kind heading says what Kind means (C-066, C-071, C-175, C-239, C-240, C-241, N-025) |

### 6. What else changes

- `make doctor` fails where the API refuses this host's `API_TOKEN`: run `make
  up` after changing `.env` (N-074). `make services`, `make pipeline-status`,
  `make pipeline-stop` and `make pipeline-retry` exit non-zero when the API
  refuses them, and print its status and detail (N-068).
- `CONFIRM` is compared with the database `DATABASE_URL` names. `make backup`,
  `make restore-backup` and `make restore-backup-stack` refuse a
  `DATABASE_URL` that names another host than the stack's postgres. `make
  logs-wipe` takes every database's log stream only under `ALL_DATABASES=1`
  (N-070, N-071).
- The Dagster web UI answers only as `localhost`, `127.0.0.1` or
  `dagster-webserver`. It refuses a GraphQL request sent by GET, and a write
  from another site or origin, with 403 (N-067).
- `GET /pipeline` waits 3 seconds for Dagster, then reports the queues with
  orchestration unavailable (C-081). A supplied run name is 1 to 80 letters,
  digits or `._:-`, and any other answers 422 (C-257).
- A stage's unexpected failure stores the exception's type and a trace id on
  the row, and the traceback goes to the log under that id (N-069). Rows that
  failed before v0.5.3 still store the driver's text, which can name a
  database host and role or an object-store address, and an open GET serves
  it. `make pipeline-retry` returns every failed row to the queue and clears
  that text.
- A topic refit archives no topics or memberships (C-420), and reads its
  passages by document and position, so the same passages give the same fit
  in any insert order (C-221). Rows that earlier refits archived stay in
  `archived_rows`, and `make archive` counts them.
- The Filebeat template keeps no replica, so a single Elasticsearch node reads
  green. Indices made before stay yellow until they age out, or until the one
  call under [Logs](make.md#logs) (C-244).
- A worker that receives a second stop within 2 seconds of the first still
  finishes its row. `--wait` exits 75, naming the worker, when rows are
  pending and the worker has not moved them for the queue lease (C-006).
- `make corpus` (and `make corpus-hosted`) replays the dedup for orphaned
  refusals after the digests and before the bridge pass (C-054).
- The link pass reads a section number after a document label, as in `Ziffer
  4 und 5 AGB` (C-190). It changed no stored link, so no bridge pass is needed
  for it.
- The nightly's Model quality job is skipped until the repository variable
  `LLM_MODEL` and the secrets `AZURE_API_KEY`, `AZURE_API_BASE` and
  `AZURE_API_VERSION` are set (N-036).

### 7. Deployment conditions this release lifts

Each fix ships in v0.5.3, so each condition has left [Production
deployment](#production-deployment).

| Item | The condition was | What lifts it |
|---|---|---|
| C-054 | After a deletion through the pages or the API, run `make extract-dedup`: no extraction worker runs on this profile | `make corpus` replays the dedup before the bridge pass |
| C-186 | Check the refusal count of a first batch: a PDF whose header follows a few leading bytes is refused as unknown type | The header is looked for in the first kilobyte |
| C-245 | Leave `EXTRACTION_DUPLICATE_COSINE` at its shipped value: 0 also stops writing passage embeddings | 0 turns the refusal off and the vectors are still written |

Four conditions still hold in a narrower form. C-066: the pages write the same
streamed workbook as `make questions-export`, which stays the way past 70,000
questions. C-106: the question-side prompts fence the document's text, and the
extraction prompts do not. C-162: a downgrade past v0.4.2 drops the rubric
scores for good. C-366: `LLM_BASE_URLS` gives each role its own address, and
credentials stay one set per provider.

## Upgrading to v0.5.2

The fix release after the final review of v0.5.1: data safety, the hosted
model path, drains that stop and say why, scale, and parse, fact and question
fixes. `docs/changelog.md` lists each fix, and `docs/bugs.md` what stays
accepted, the withdrawn attempts among them.
A build from scratch needs only steps 1 and 2.

### 1. Pull, code and images

Before `git pull`, pull the review verdicts (dataset names gain the database,
step 6): `make review-pull-facts`, `make review-pull-topics`, `make
review-pull-questions`. Set aside local edits of `configs/env/backend.env`:
the role models move to `.env`, `TOPIC_MIN_WEIGHT` goes and `SPEND_CAP` is
given on the command line.

```bash
git pull
make setup        # once .env holds the new lines below
podman compose --env-file configs/env/deployment.env --env-file .env stop parse-worker chunk-worker extract-worker topic-worker question-worker assess-worker
make backup DIR=/backups/$(date +%F)
poetry install --with llm,nlp,data,storage,api,pipeline,viz,observability,dev
make upgrade
```

Add the lines `.env.example` carries that `.env` lacks (`make setup` fills
placeholders only). `API_TOKEN=change_me_api_token` is required. `HOST_RUNNER`
reads 0 where unset, a role model left unset follows `LLM_MODEL`, and with
`LLM_REASONING_EFFORT` unset the shipped reasoning writer thinks. Copy `make
backup`'s `DIR` off the machine ([Backups](#backups)). On the production
profile, fill the host's model cache once: `make docling-weights HOST=1`, and
each encoder at its pinned commit (`make doctor` prints the fetch command).

- Docling 2.142.1 (was 2.141.0) needs no re-parse. Pillow 13.0.0 (was 12.3.0).
  `configs/audit-accepted.txt` lists what `make audit` accepts: filelock
  3.32.7's advisories until 2026-11-30, after which the audit fails until the
  entry is read again.
- A container refuses a stale image ([A stale image](#a-stale-image)): build
  before `make up`, as `make upgrade` does.
- Keep the secrets out of a synced folder ([Keeping the secrets out of the
  checkout](#keeping-the-secrets-out-of-the-checkout)).

### 2. Three migrations, in order

`make schema-status` shows what `make upgrade` will run. The head before this
release is `20e31b1656f7`. Each revision runs in its own transaction under a
5-second lock timeout: if one fails, stop what holds the table and run `make
schema` again.

| Revision | What it does |
|---|---|
| `860d56b11032` | Adds `facts.language`, filled from each fact's first citation, then analyses `facts` (C-090) |
| `7a41c9d2e8b0` | Adds `facts.twin_id` (foreign key, set NULL when the twin goes) and its index. NULL on every stored refusal, so the first dedup replay reads each duplicate refusal once (C-068) |
| `4a7c2e91d3b8` | Adds `questions.source_digests` and three BEFORE DELETE triggers (on `passages`, `facts`, `fact_passages`) that stamp it. A question whose last fact went is rejected as `source_changed` and kept, not deleted (C-001) |

`make schema-down CONFIRM=<database>` removes each revision and drops what it
added.

### 3. Settings

- `TOPIC_MIN_WEIGHT` is replaced by `TOPIC_RELATIVE_WEIGHT` (0.5): a
  membership is kept when it is at least that share of the passage's
  strongest. A stored row under the old name stops the topic stage's build and
  `make doctor`, naming the new setting and the `DELETE` that removes it.
  Refit afterwards (step 5).
- `TOPIC_NUM_TOPICS` ships at 300 a language (was 40), and topics are named 25
  to a call. More topics mean more questions: `make estimate` says how many.
- `MAX_FILE_SIZE_MB` is bounded at 150. A larger stored value is refused
  (upload 503 `stored_setting_refused`, `make ingest` exit 3, `make doctor`
  fails): store 150 or less, or delete the row.
- `PARSING_MAX_PAGES` is new (180; 0 is no limit). A longer document is
  refused before conversion. `make parse-retry` returns it after a split.
- `SPEND_CAP` is new, in USD, given on a drain's command line. It stops a
  drain, the bridge pass, the release draw and the rejudge with exit 75 before
  the next row past it. Under `make corpus-hosted` it counts the whole run
  through a ledger per database (`SPEND_LEDGER`), and a drain refuses a model
  litellm cannot price.
- `EMBEDDING_MODEL`, `NLI_MODEL`, `QA_MODEL` and `DOCLING_ARTIFACTS_PATH` are
  fixed, with `EMBEDDING_MODEL_REVISION`, `NLI_MODEL_REVISION` and
  `QA_MODEL_REVISION` beside them in `backend.env`. A stored row for one of
  them stops every stage's build, naming its pin and the `DELETE` that removes
  it.
- `API_TOKEN` (`.env`): every API write and every read of settings carries it
  as `X-API-Token`, or the API answers 401.
- `HOST_RUNNER` (`.env`): `1` selects the production profile ([Production
  host](#production-host)). `ENV_FILE`: the secrets file every host command
  reads (`.env` unless set).
- The role models are in `.env` only, and `.env.example` ships the production
  split. `LITELLM_LOCAL_MODEL_COST_MAP=true` is committed in `backend.env`.
- `POSTGRES_*` (4 CPUs and 4 GB, were 1 CPU and 512 MB; [Sizing
  Postgres](#sizing-postgres)) and `PHOENIX_TRACE_RETENTION_DAYS` (30) are new
  in `deployment.env`. The VM needs about 33 GiB with every profile on.

### 4. Prompts and model calls

- Writer 29 becomes 32, verifier 12 becomes 15, phrasing 4 becomes 5.
  Unchanged: atomic extraction 12, repair-1, digest 5, bridge 6, `verifier:
  stated` 1, assessment 4, topic naming 3. Stored rows keep their version.
- The first `make questions-rejudge` asks again about every stored accepted
  unanswerable question (one `settles` reading each, and a second where the
  passages are silent and the probe is on).
- Added calls: one verifier call for a derived question citing two passages,
  more topic-naming calls for a language of more than 25 topics, and one
  digest call a passage in the digest pass of step 5.

### 5. Reruns, in order

None is needed to start v0.5.2. A rerun without `SHA` refuses unless `CONFIRM`
names the database. A re-chunk or re-extraction over questions refuses unless
`FORCE=1`, naming how many questions rest on what it replaces. Those questions
are rejected as `source_changed` and kept.

| Step | Command | Needed because of |
|---|---|---|
| Parse | `make parse-rerun CONFIRM=<database>` | Parse fixes: unsupported-language refusal (C-008), titles (C-096), hidden text (C-107), low-confidence pages and interleaved columns (C-109, C-426). Docling 2.142.1 alone needs none |
| Chunk | `make chunk-rerun CONFIRM=<database> FORCE=1` | Passage fixes (C-007, C-121, C-187, C-230, C-368). On the reviewed build it changes 108 passages of 9 documents |
| Extract new passages | `make extract-start`, then `make extract` | Re-chunked passages have no facts yet |
| Judge facts again | `make extract-revalidate` | Fact checks (C-019, C-020, C-021, C-033, C-129, C-416). No model call |
| Digest | `make extract-digests` | The 500-character digest floor and its list-item count (C-057, C-098) |
| Refit topics | `make topics-discover` | `TOPIC_RELATIVE_WEIGHT` (C-095) |
| Stored questions | `make questions-reverify` | Rejects a question whose facts went or do not hold, and never gives one back. `make questions-rerun` writes every topic again at the writer's cost |
| Unanswerables | `make questions-rejudge` | Verifier 15 (C-022) |
| Release | `make questions-balance` | Rejected rows leave it (C-089) |
| Export | `make questions-export` | Retrieval spread band, earlier turns and source per row, a fuller Summary (C-023, C-029, C-102, C-135) |
| Object keys | `make s3-prefix` | Keys carry the database (C-004). A bare key is still read, but only a copy under the prefix is safe from another database's delete or purge. Once per database |

### 6. What else changes

- Phoenix, Argilla, logs and Dagster carry the database (projects
  `<name>__<database>`, `db` on every log line). A wipe takes only its own
  database's. Items filed before belong to no database and go only with
  `ALL_DATABASES=1`.
- Upload golden sets again with `make eval-upload` and `make eval-phrasing`.
  Old ones go only with `make phoenix-purge ALL_DATABASES=1
  CONFIRM=<database>`. Push review datasets again with `make review-push-*`.
- Destructive targets need `CONFIRM=<database>` on the command line:
  `schema-down`, `schema-reset`, `wipe`, `delete`, `delete-derived`,
  `topics-delete`, an unnarrowed `*-rerun`, and `archive-purge` with `TABLE`,
  `ALL` or `DAYS`. `make down-volumes` needs `CONFIRM=all-volumes`, `make
  restore-backup-stack` needs `CONFIRM=stack`.
- A deletion takes the questions on what it removes (a two-document question
  goes when either document is deleted). A fact another document also cites
  stays. Run `make extract-dedup` where no extraction worker runs.
- The first empty extraction queue replays every duplicate refusal once
  (`facts.twin_id` is NULL on stored refusals). No model is called.
- The first `make up` sets the trace retention for every database, and Phoenix
  then deletes older spans. Reconcile Phoenix's cost against `make spend`
  first, or raise the value in `deployment.env`.
- Drains exit 0 done, 3 a row failed, 75 stopped. `make corpus` stops at the
  first non-zero exit. Use `make corpus-hosted` on the production profile
  ([After a stop](#after-a-stop)). Two extraction drains at most
  ([Scaling](#scaling)).

### 7. Deployment conditions this release lifts

Each fix ships in v0.5.2, so each condition has left [Production
deployment](#production-deployment).

| Item | The condition was | What lifts it |
|---|---|---|
| C-001 | Do not apply v0.5.1's lower digest floor to stored data | A re-chunk or re-extraction rejects questions on changed facts as `source_changed` instead of deleting them |
| C-024 | `TOPIC_NUM_TOPICS=40` caps topics and questions | The ceiling ships at 300 a language |
| C-058 | No refit or topic delete during a question drain | They refuse while a topic holds a live question claim (409 `questions_running`, or exit 1) |
| C-059 | The workbook says the judge's figures are not a quality estimate | The sample is proportional per stratum, and the Summary says so |
| C-072 | `HF_HUB_OFFLINE=1` with a filled model cache | `make corpus-hosted` runs offline and refuses an incomplete cache before it detaches |
| C-075 | Stop workers and drains before `make schema` | Lock timeout 5 seconds, statement timeout 10 minutes, and `make upgrade` stops the workers |
| C-076 | List page counts and split documents far above 139 pages | `PARSING_MAX_PAGES` (180) refuses a longer document before conversion |
| C-078 | Run `make confidence-recalibrate` only with question drains stopped | It writes back in batches of 300, each row guarded by the scores it read |
| C-079 | No `make up` or reboot during a drain | A worker told to stop finishes or gives back its row and exits 75, and `make corpus-hosted` resumes |
| C-080 | Give the VM at least the compose limits | Optional services sit under profiles ([Profiles](#profiles)) |
| C-086 | Check free space and prune images before every rebuild | `make upgrade` checks `UPGRADE_FREE_GB` (20) and prunes |
| C-088 | `LITELLM_LOCAL_MODEL_COST_MAP=true` | Committed in `backend.env` |
| C-102 | Say that earlier turns and a row's location must be looked up | The Questions sheet gives each row its earlier turns and source |
| C-103 | Set a trace retention at `make up` | `make up` sets `PHOENIX_TRACE_RETENTION_DAYS`. Read what it prints |
| C-107 | Ingest only documents the corpus owner controls until hidden text is flagged | Text no reader sees is dropped from a page whose other text paints ink |
| C-110 | Pin parse dependencies and replay a sample after any bump | `make test-golden` checks stored snapshots |
| C-112 | Pin the embedding libraries | Every Hugging Face load names its pinned commit |
| C-117 | Fill the model cache once, keep `HF_HUB_OFFLINE=1`, record revisions | `EMBEDDING_MODEL_REVISION`, `NLI_MODEL_REVISION`, `QA_MODEL_REVISION` |
| C-118 | A purge cadence, per database | `make archive-purge` runs in batches of 10,000 rows for this database only ([Deleting things](#deleting-things)) |
| C-119 | No stored overrides, or check `make settings` after every upgrade | Every stage checks stored rows against the catalogue |
| C-123 | Read the audit output by hand | `configs/audit-accepted.txt` lists accepted advisories with review-by dates, and `make audit` fails on any other |
| C-201 | A database password without URL-reserved characters | `make doctor` and `make corpus-hosted` refuse `@ / : # ? %` |
| C-219 | A preflight log must show a price per role | A drain with `SPEND_CAP` refuses a model litellm cannot price |
| C-253 | Build images locally only and never push them | `.dockerignore` admits only what the Dockerfiles copy |
| C-299 | Keep `MAX_FILE_SIZE_MB` at or below its shipped 100 | It is bounded at 150, and the API refuses a PDF over `PARSING_MAX_PAGES` pages |
| C-416 | List currency codes in tables, and ship the currency fix first beyond EUR, USD, GBP and CHF | A currency is any ISO 4217 code or sign beside a number, or the language's own word |

## Upgrading to v0.5.1

Rebuild and `make up`. No migration, no new setting.

- Dagster starts again. SQLAlchemy 2.1 reads a bare `postgresql://` URL as
  psycopg 3, but the orchestration image has only psycopg2, so the Dagster
  webserver, the daemon and `make dagster-wipe` (and `make wipe`) failed.
  `configs/dagster/dagster.yaml` now uses `postgresql+psycopg2`.
- `LLM_REASONING_EFFORT` is not sent to a hosted model that litellm knows does
  not reason (gpt-4.1, gpt-4o), so one effort serves a mixed split. A model
  litellm does not know is still sent it.
- `EXTRACTION_DIGEST_MIN_CHARS` ships at 500 (was 800): passages of 500 to 800
  characters get a summary and an outline, and about half of those digest
  calls are refused as `not_condensed`. Set it to 800 in
  `configs/env/backend.env` to revert.

## Upgrading to v0.5.0

### From v0.4.5

```bash
poetry install --with llm,nlp,data,storage,api,pipeline,viz,observability,dev
podman compose --env-file configs/env/deployment.env --env-file .env build
make up
```

Every dependency moves to the newest release its range allows. Run `poetry
install` first (`make install-python` also fetches the spaCy pipelines), then
rebuild the images. SQLAlchemy 2.1.6 is the floor: a virtualenv at 2.0.52
fails with `cannot import name 'distinct_on'`. Docling 2.141.0 can parse a
document differently from 2.137.0 (`make parse-rerun` updates stored parses).
No migration (head `20e31b1656f7`).

`QUESTIONS_RELEASE_UNANSWERABLE` ships at 0.10 (was 0). The settles reading
still keeps answerable questions: on link U, 19 of 60 kept out-of-corpus rows
and 20 of 60 base rows were answered by the corpus. Up to a third of released
unanswerable rows can test a chatbot for refusing a question it should answer
(a known defect in `docs/bugs.md`). Set 0 in `configs/env/backend.env` to
release none.

A category of `QUESTIONS_CATEGORIZATIONS` takes two keys, `settles`
(`answers`, `refutes` or `silent`) and `behaviour` (what a good reply does). A
categorization whose categories all carry both is the unanswerable one, and at
most one may be (the [configuration guide](configuration.md) lists when a
value is refused). Unset, the default adds `Unanswerable`, which deals every
unanswerable slot the out-of-corpus kind. The UAEval4RAG kinds (Peng et al.,
[*Unanswerability Evaluation for Retrieval Augmented
Generation*](https://aclanthology.org/2025.acl-long.415/), ACL 2025) are
`out-of-corpus`, `false-presupposition`, `underspecified` and `nonsensical`.
To opt into the other three, set `QUESTIONS_CATEGORIZATIONS` (settings page,
`PATCH /settings/questions` or `python -m settings.run`) to the default's
three answerable categorizations plus `UNANSWERABLE_CATEGORIZATION` from
`backend/question_generation/config.py`. Their writer prompts are not
re-calibrated. Writer 28 becomes 29. No model call is added, and stored rows
need no rerun.

`make diversity FILE=<workbook> LABELS=<file>` corrects labelled shares by the
judge's verdict with prediction-powered inference (Angelopoulos et al.,
[*Prediction-powered inference*](https://doi.org/10.1126/science.adi6000),
Science 2023), as ARES (Saad-Falcon et al., [*ARES: An Automated Evaluation
Framework for Retrieval-Augmented Generation
Systems*](https://aclanthology.org/2024.naacl-long.20/), NAACL 2024) does. It
needs a workbook whose Judge column holds the judge of the DataMorgana paper
(Filice et al., [*Generating Q&A Benchmarks for RAG Evaluation in Enterprise
Settings*](https://aclanthology.org/2025.acl-industry.33/), ACL 2025 Industry
Track). The [assessment
README](../backend/assessment/README.md#labelled-shares-corrected-by-the-judge)
describes the labels file. `GET /questions/quality` gains `writer_model`,
`verifier_model` and `phrasing_model`, and `GET /questions` gains `behaviour`.



Follow each later release's section in order, then From v0.4.5.

### From v0.3.12

This path replaces the sections for v0.3.13 to v0.4.5. Back up PostgreSQL and
the `documents` bucket first ([Backups](#backups)). One migration cannot be
undone.

1. Code and images:

   ```bash
   poetry install --with llm,nlp,data,storage,api,pipeline,viz,observability,dev
   podman compose --env-file configs/env/deployment.env --env-file .env build
   make up
   # development profile, as make up started it:
   podman compose --env-file configs/env/deployment.env --env-file .env -f compose.yaml -f compose.dev.yaml up -d --remove-orphans
   # go-live profile (HOST_RUNNER=1), compose.yaml alone:
   podman compose --env-file configs/env/deployment.env --env-file .env up -d --remove-orphans
   ```

   The last command removes the `seaweedfs-ui` container that compose no
   longer defines.
2. `make schema-status`, then `make schema`: six revisions on top of
   `8f759a3a3848`.

   | Revision | From | What it does |
   |---|---|---|
   | `a41c9e3d7b52` | v0.3.20 | Adds `questions.kind`, `NOT NULL`, backfilled from the passage scope |
   | `c3a9e1470b5d` | v0.3.23 | Adds `facts.bridge`, empty until `make extract-bridge FORCE=1` |
   | `d5b2f8a60c14` | v0.3.36 | A trigger takes follow-ups out of the release when their root leaves `accepted`, plus a one-time repair that a downgrade cannot undo |
   | `733a3eadef7c` | v0.4.2 | Lets `assessment_metrics` hold six `rubric_*` scores |
   | `626a5b07ae34` | v0.4.2 | Adds `questions.categories` |
   | `20e31b1656f7` | v0.4.4 | Column comments only |

3. Settings, none required. `QUESTIONS_KIND_MIX` defaults to
   `needs_both:5,compound:1` (`needs_both:1` turns compound questions off).
   `QUESTIONS_CATEGORIZATIONS` is new (`[]` turns categories off).
   `QUESTIONS_RELEASE_UNANSWERABLE` ships at 0.10 (was 0).
   `TOPIC_LABEL_MIN_FACT_SHARE` and `REVIEW_REVIEWER` are deleted.
   `EMBEDDING_MAX_TOKENS` must be at least 64,
   `ORCHESTRATION_DRAIN_TIMEOUT_SECONDS` and `ORCHESTRATION_POLL_SECONDS`
   finite and at least 1, and `DATABASE_URL` must name a database.
   `backend.env` puts `EXTRACTION_DIGEST_MODEL`, `TOPIC_MODEL` and
   `QUESTIONS_PHRASING_MODEL` on `ollama_chat/muse-glimmer:30b-mlx`: pull it
   or change the three lines.
4. Prompts: writer 15 to 29, verifier 6 to 12 (`verifier: stated` 1 is new),
   assessment 2 to 4, topic naming 2 to 3, bridge 5 to 6. New calls: a
   verifier read for a two-passage `needs_both` question, two for a compound
   question, six judge calls per root question while `ASSESSMENT_ENABLED` is
   on.
5. Reruns, in order (none needed to start; one pass covers every release since
   v0.3.12):

   | Step | Command | Notes |
   |---|---|---|
   | Parse | `make parse-rerun CONFIRM=<database>` | |
   | Chunk | `make chunk-rerun CONFIRM=<database>` | Unchanged passages keep their facts. Questions on replaced facts are rejected as `source_changed` and kept |
   | Extract new passages | `make extract-start`, then `make extract` | Only re-chunked passages reach the model |
   | Repair pieces | `make extract-recap`, then `make extract-dedup` | No model call for the recap |
   | Judge facts again | `make extract-revalidate` | No model call |
   | Rewrite bridges | `make extract-bridge FORCE=1` | Calls the model for every bridge. `FORCE=1` is needed while an accepted question cites one |
   | Refit topics | `make topics-discover` | The Topics page shows no figure until this runs |
   | Stored questions | `make questions-rescore`, then `make questions-reverify` | Reverify never gives a rejected question back |
   | Unanswerables | `make questions-rejudge` | One settles reading per stored accepted unanswerable question |
   | Release | `make questions-balance` | |

   Optional: `make assess-rerun ONLY=--only\ kind=question` judges stored
   questions with the DataMorgana paper's judge and replaces every stored
   question verdict (`make diversity LABELS=` needs it).
6. Recreate Argilla question datasets made before v0.4.3 and facts datasets
   made before v0.4.5 ([review README](../review/README.md)). The workbook
   gains Kind and Categories columns. Assessment reruns answer 409 when the
   phase cannot run, and `GET /pipeline/runs` refuses a `limit` outside 1 to
   500.

## Upgrading to v0.4.5

Rebuild and `make up`, then once remove the old `seaweedfs-ui` container:

```bash
# development profile, as make up started it:
podman compose --env-file configs/env/deployment.env --env-file .env -f compose.yaml -f compose.dev.yaml up -d --remove-orphans
# go-live profile (HOST_RUNNER=1), compose.yaml alone:
podman compose --env-file configs/env/deployment.env --env-file .env up -d --remove-orphans
```

No migration (head `20e31b1656f7`), no prompt change, no rerun.

- `REVIEW_REVIEWER` is deleted. `EMBEDDING_MAX_TOKENS` below 64 is refused.
  `ORCHESTRATION_DRAIN_TIMEOUT_SECONDS` and `ORCHESTRATION_POLL_SECONDS` must
  be finite and at least 1, or the orchestrator refuses to load (shipped 28800
  and 15 are fine).
- A NUL byte or lone surrogate is refused at the edge: `out_of_range` for a
  setting, 422 for a topic label, 400 `invalid_value` for a filename.
- `GET /pipeline/runs` refuses a `limit` outside 1 to 500 (422). It and `PUT
  /pipeline/automation` answer 503 `orchestrator_refused` (was
  `no_orchestrator`) when Dagster errors.
- `make doctor` asks every model a stage calls. `backend.env` puts
  `EXTRACTION_DIGEST_MODEL`, `TOPIC_MODEL` and `QUESTIONS_PHRASING_MODEL` on
  `ollama_chat/muse-glimmer:30b-mlx`: pull it or change the three lines.
- Images are named for the compose project, and a stack has 23 containers ([A
  second stack beside the first](#a-second-stack-beside-the-first)).
- A facts dataset created before v0.4.5 lacks `language` metadata: `make
  review-pull-facts`, delete the dataset in Argilla, push again.

## Upgrading to v0.4.4

Rebuild, `make up`, `make schema` (`20e31b1656f7`, column comments only).

- Image locks resolve under `poetry.lock`'s pins (parse worker Docling
  2.137.0, was 2.132.0). `make lock` writes both image locks: run it after
  changing a `requirements.txt`. Pillow stays at 12.3.0 (its fixes need Pillow
  13.0.0, which no released Docling allows; `docs/changelog.md`).
- `TOPIC_LABEL_MIN_FACT_SHARE` is deleted. `DATABASE_URL` must name a
  database. `PARSING_OCR_CHAR_THRESHOLD` (100) also names image-only pages of
  a digital PDF in the parse warning. Topic naming prompt 2 becomes 3.
- Topic figures and models move to `topics/<database>/<language>`: the Topics
  page shows no figure until `make topics-discover`.
- `make audit` also audits `poetry.lock`.
- Reruns, in order: `make parse-rerun CONFIRM=<database>`, `make chunk-rerun
  CONFIRM=<database>`, `make extract-start` and `make extract`, `make
  extract-revalidate`, `make extract-bridge FORCE=1`, `make topics-discover`,
  `make questions-reverify` (then `make questions-rescore` if topics changed).

## Upgrading to v0.4.3

Rebuild and `make up`. No migration (head `626a5b07ae34`), no new setting.

- Unset, `QUESTIONS_CATEGORIZATIONS` deals Phrasing, Premise and Linguistic
  variation. To keep v0.4.2's two, use `DEFAULT_CATEGORIZATIONS` from
  `backend/question_generation/config.py` without the Linguistic variation
  entry. A value set locally is used as written: copy the new JSON from the
  [configuration guide](configuration.md), which lists the nine cases where a
  value is refused.
- A category may be `"form": "premise"`. A `words` bound `max` stops a premise
  beside it. A search query is not told on a two-passage slot or on a
  `reason`, `comparison`, `implication` or `temporal` slot.
- Writer 19 becomes 28, verifier 6 becomes 12. A short search query costs one
  passage probe and one verifier read when that category is configured and
  `QUESTIONS_ELSEWHERE_PASSAGES` is above 0 (default 20). The first `make
  questions-rejudge` costs one settles reading per stored accepted
  unanswerable question, and a second where the passages are silent and the
  probe is on.
- The export command line refuses a `--question-type` or `--answer-form` that
  does not exist. Recreate review datasets made before v0.4.3 ([review
  README](../review/README.md)).
- Stored questions meet the new gates only through `make questions`, `make
  questions-reverify`, then `make questions-balance` once.

## Upgrading to v0.4.2

Rebuild, `make up`, `make schema`, and `poetry install` on a host checkout.
Two revisions on top of `d5b2f8a60c14`: `733a3eadef7c` (lets
`assessment_metrics` hold six `rubric_*` scores; its downgrade deletes those
rows) and `626a5b07ae34` (adds `questions.categories`).
`QUESTIONS_CATEGORIZATIONS` is new and optional. Writer 16 becomes 19,
assessment 2 becomes 4. `make assess-rerun ONLY=--only\ kind=question` judges
stored questions again and replaces every stored question verdict.

## Upgrading to v0.4.1

Rebuild and `make up`. No migration, setting, prompt change or model call.
`make diversity FILE=<workbook>` is new and changes nothing stored.

## Upgrading to v0.4.0

For a stack on v0.3.12 moving straight to v0.4.0. Back up PostgreSQL and the
`documents` bucket first ([Backups](#backups)): the migrations cannot all be
undone.

1. Rebuild and `make up`. On a host checkout run `poetry install` (aiohttp
   3.14.5, yarl 1.25.1 and certifi 2026.10.19 close advisories
   CVE-2026-111063, CVE-2026-111064, GHSA-2g87-pp6c-29x5 and
   GHSA-6q48-6c7w-9gw2).
2. `make schema-status`, then `make schema`: `a41c9e3d7b52`, `c3a9e1470b5d`
   and `d5b2f8a60c14` on top of `8f759a3a3848` (see the v0.3.12 path under
   v0.5.0). `d5b2f8a60c14` clears `release_id` on follow-ups under a root that
   is not accepted, and a downgrade cannot undo it. To count the rows first:

   ```sql
   SELECT count(*) FROM questions q WHERE q.release_id IS NOT NULL AND q.follows_id IS NOT NULL AND EXISTS (SELECT 1 FROM questions r WHERE r.id = q.follows_id AND r.status <> 'accepted');
   ```
3. `QUESTIONS_KIND_MIX` defaults to `needs_both:5,compound:1` (`needs_both:1`
   turns compound questions off). With `QUESTIONS_RELEASE_LANGUAGES` unset,
   the ids of an existing release can move.
4. Every accepted two-passage `needs_both` question gets one more verifier
   call (`verifier: stated` 1), about USD 0.45 to 0.5 for a build the size of
   the *Laws of the Game* (football rules).
5. Reruns, in order, as in the v0.3.12 path under v0.5.0 (each `-rerun` with
   `CONFIRM=<database>`).
6. Recreate Argilla question datasets made before v0.3.28 (no `kind`) or
   v0.3.34 (no `thread`, `turn`). `POST /assessment/rerun` answers 409
   `assessment_cannot_run` before touching any verdict when the assessment
   cannot run.

## Upgrading to v0.3.2 through v0.3.36

Each is rebuild and `make up` with no setting change, unless noted. A stack on
v0.3.12 uses the v0.4.0 section instead.

- v0.3.36: `make schema` (`d5b2f8a60c14`, see v0.4.0), then `make
  questions-balance`.
- v0.3.35: one more verifier call per two-passage `needs_both` question in a
  new `make questions` (about USD 0.45 to 0.5 a build).
- v0.3.34: the workbook gains a Kind column. Recreate Argilla question
  datasets (no `thread`, `turn`).
- v0.3.33, v0.3.29: `make extract-revalidate` (and `make questions-reverify`
  for v0.3.33).
- v0.3.32: `make chunk-rerun CONFIRM=<database>`. v0.3.31: `make parse-rerun
  CONFIRM=<database>`, then `make chunk-rerun CONFIRM=<database>`.
- v0.3.28: `poetry install`. Run `make extract-bridge FORCE=1` after a topic
  change. Recreate Argilla question datasets (no `kind`).
- v0.3.27: `make questions-balance`. v0.3.25: `make questions-reverify` holds
  a stored question to its stored kind.
- v0.3.26: compound questions are dealt in about one in six spanning slots
  (`QUESTIONS_KIND_MIX=needs_both:1` turns them off) and cost two verifier
  reads. They are not calibrated through the real deal.
- v0.3.24, v0.3.19, v0.3.18: answer-gate fixes free questions only in a fresh
  `make questions`.
- v0.3.23: `make schema` adds `facts.bridge`. v0.3.20: `make schema` adds
  `questions.kind`.
- v0.3.16: `make extract-bridge` under bridge prompt 6 (`FORCE=1` while an
  accepted question cites a bridge), about USD 0.25 more a build.
- v0.3.15: `make extract-revalidate`. v0.3.14: `make extract-recap`, then
  `make extract-dedup`.
- v0.3.12: verifier prompt 6: `make questions-rejudge` asks about every
  accepted unanswerable question again.
- v0.3.11: a topic fit is about eight times slower. v0.3.10: prompt `repair-1`
  costs one more call for a passage with `not_atomic` statements.
- v0.3.9: bridge prompt 5: `make extract-bridge FORCE=1` replaces bridges and
  rejects the questions citing them.
- v0.3.8: add any secret compose requires to `.env` by hand (`podman compose
  --env-file configs/env/deployment.env --env-file .env config -q` finds
  them). The frontend answers only at `localhost` and `127.0.0.1`, `PAGE_SIZE`
  outside 1 to 500 stops it, and `/redoc` is removed.
- v0.3.7: atomic extraction 12, digest 5: only a re-extraction replaces stored
  facts. v0.3.6: `make schema` corrects a column comment.
- v0.3.3: with `extract-worker` stopped, `make extract-revalidate`. A deletion
  through the API or UI still needs `make extract-dedup`.
- v0.3.2: text and number readings change. Re-parse and re-chunk stored data
  (see [Upgrading to v0.3.0](#upgrading-to-v030)).

## Upgrading to v0.3.1

Rebuild, `make up`, `make doctor` (it names settings the API lacks, which
means the API serves an older build). No migration or prompt change.

| Setting | v0.3.0 | v0.3.1 |
|---|---|---|
| `LLM_STRUCTURED_MODE` | any instructor mode | one of `FUNCTIONS`, `PARALLEL_TOOLS`, `TOOLS`, `TOOLS_STRICT`, `JSON`, `JSON_O1`, `MD_JSON`, `JSON_SCHEMA`; anything else is refused at start-up |
| `QUESTIONS_MEETS_SHARE` | required | absent reads 0.02 |

A model call is billed at most `LLM_MAX_ATTEMPTS` times (a 429 waits its
`Retry-After`, two minutes at most). `make spend` counts failed calls. `make
delete` and `make delete-derived` refuse while `extract-worker` runs. `make
audit` fails on an advisory. `ARGILLA_API_KEY` reaches Argilla on a fresh
`argilla_data` volume only.

## Upgrading to v0.3.0

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build api
make up
```

No migration. A copied `configs/env/backend.env` keeps its old values until it
takes the new ones.

| Setting | v0.2.2 | v0.3.0 |
|---|---|---|
| `QUESTIONS_RELEASE_DIFFICULTY` | `easy:1,medium:1,hard:1` | unset, which follows the answerable pool's own band split |
| `QUESTIONS_RELEASE_UNANSWERABLE` | 0.10 | 0, until the `settles` judgement can be trusted with them |
| `QUESTIONS_ELSEWHERE_PASSAGES` | 10 | 20 |
| `QUESTIONS_FOLLOWUP_TYPES` | `condition,reason,comparison` | `condition,reason` |
| `QUESTIONS_MEETS_SHARE` | none | 0.02, new; required until v0.3.1 |
| `QUESTIONS_RELEASE_TYPES` | `aggregation:4` | `aggregation:1`, the other kinds unchanged |

On v0.3.0, `QUESTIONS_MEETS_SHARE=0.02` must be in `backend.env`, or `make
questions` and `make questions-balance` stop on the missing name. `make
questions-balance` calls the verifier about once per released question.

Most fixes change passages, facts or topics, so stored rows improve only
through a rebuild by the container workers. With the stack up (`make up`),
queue each stage once the one before it has finished: `POST
/parsing/rerun?confirm=true`, then `POST /chunking/rerun?confirm=true`, then
`make extract-start`, then `POST /topics/discover`, then `make extract-bridge
MISSING=1`, then `make questions-start`, and last `make questions-rejudge` and
`make questions-balance`. The bridge pass has no worker and runs on the host.
A refit keeps a person's topic name, not a model's.

## Upgrading to v0.2.2

```bash
podman compose --env-file configs/env/deployment.env --env-file .env build api
make up
make schema
```

The three new revisions change column comments only.

| Setting | v0.2.1 | v0.2.2 |
|---|---|---|
| `EXTRACTION_DUPLICATE_COSINE` | 0.95 | 0.985 |
| `QUESTIONS_OFF_TOPIC_OVERLAP` | 0.3 | 0, which turns the gate off |
| `QUESTIONS_ELSEWHERE_PASSAGES` | 4 | 10 |
| `QUESTIONS_DUPLICATE_SHARED_COSINE` | none | 0.88, new; optional, and unset holds a shared fact to `QUESTIONS_DUPLICATE_COSINE` |
| `QUESTIONS_RELEASE_LANGUAGES` | none | optional, new; unset follows the pool's own language split |

Reruns for stored rows, in order (the first five call no model): `make
extract-dedup`, `make extract-revalidate`, `make extract-recap`, `make
questions-rescore` (after `extract-dedup`, before re-verify, and after no
other rerun), `make questions-reverify` (only rejects), then `make
questions-rejudge` and `make questions-balance` (verifier calls).
Struck-through text, list lead-ins and chapter-aware section paths change
passages and need a rebuild by the container workers (`POST
/parsing/rerun?confirm=true`, `POST /chunking/rerun?confirm=true`, then
extraction, topics, `make extract-bridge MISSING=1` and questions).

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
| The run dashboard's Phoenix panels cannot read their tables | Run `make grafana-grants` |
| Streamlit refuses a file the API would accept | `server.maxUploadSize` is below `MAX_FILE_SIZE_MB` |
| The frontend will not start, naming a variable | The variable is not in the `streamlit` service's `environment` |
| Argilla refuses the key | Its owner was made before compose passed it `ARGILLA_API_KEY`. Copy the key under "My settings" into `ARGILLA_API_KEY` (not `ARGILLA_PASSWORD`) |
| Argilla restarts, logging that Elasticsearch is not available | `certs/` was generated by macOS's LibreSSL before v0.2.1. Delete `certs/`, then run `make down && make dev` |
| A scanned PDF is refused rather than parsed | OCR is not enabled |
| `make questions-reverify` rejects many questions as `source_changed` after `make extract-dedup` | Their stored scope counts citations the dedup removed. Run `make questions-rescore` first |
| The release report warns that a language in the pool has no weight | `QUESTIONS_RELEASE_LANGUAGES` leaves it out. Name it, or unset the setting |

## Deleting things

```bash
make delete SHA=<sha256> CONFIRM=<database>          # a document and everything from it
make delete-derived SHA=<sha256> CONFIRM=<database>  # its passages and what rests on them: facts, questions, follow-ups, assessments
make wipe CONFIRM=<database>                         # every document, then the topics
make topics-delete CONFIRM=<database>                # every topic, membership, model and figure
```

Each is the first of two deletions. An AFTER DELETE trigger copies the row
into `archived_rows`, and removal paths move objects into the `archive`
bucket:

```bash
make archive                                   # what is held, by table, with its age
make restore-documents SINCE=<time>            # list the deletions from then on
make restore-documents AT=<archived_at>        # put those deletions back
make archive-purge DAYS=30 CONFIRM=<database>  # the second deletion. This one is final
```

Nothing purges itself, so the archive grows on ordinary runs too. `make
doctor` prints its rows and size. Purge per database on a cadence, after `make
backup`: `make archive-purge DAYS=<n>` deletes in committed batches of 10,000
rows and takes only this database's rows and objects. See
[`backend/archive/`](../backend/archive/README.md).

These two archive nothing, because `TRUNCATE` and a dropped volume fire no row
trigger:

```bash
make down-volumes CONFIRM=all-volumes  # the containers' data, all of it
make schema-reset CONFIRM=<database>   # every table, rebuilt from the revisions
```

Deleting a document takes everything derived from it but not `topics` (a fit
is over the corpus): `make wipe` runs both.

A claim that two documents in the same language share rests on one of them
only: the second copy is stored as a `duplicate` refusal citing only its own
passage. After a deletion, `make extract-dedup` (run by `make delete` and
`make delete-derived`) calls no model and gives that copy back, re-judging and
re-capping only the passages of what it gave back. Every deletion ends with a
line saying how many duplicate refusals lost their twin. The extraction worker
gives them back when its queue is empty. Where no extraction worker runs, as
on the production profile, the next `make corpus` or `make corpus-hosted`
replays it before the bridge pass; run `make extract-dedup` after a deletion
through the pages or the API to have it at once.

Both steps refuse beside a running `extract-worker`, and `make delete` asks
before it deletes, so a refusal leaves the document in place. If the replay
fails after the deletion, run `make extract-dedup` once the cause is gone:
running `make delete` again finds nothing.
