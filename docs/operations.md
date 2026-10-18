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
claims one row at a time with `FOR UPDATE SKIP LOCKED`. Extract workers running
side by side do not see each other's uncommitted facts, so two passages read
at once can both keep one restated claim; see the `duplicate` refusal in
[the extraction README](../backend/extraction/README.md).

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

`assess-worker` is the cheapest of the six to scale and, with `topic-worker`,
which fits its NMF from scratch, one of two that load **no** pretrained
weights: it asks a served model two to six questions about text it already
has. 1 GB and one CPU. It also does nothing until
`ASSESSMENT_ENABLED` is true, so a deployment that never turns the
evaluation phase on pays for one idle container. It reads the flag every
`WORKER_POLL_SECONDS`, so switching it on from the Assessment page needs no
restart; a change to `.env` reaches it with `make up`.

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

## Failure

A row a worker died holding is failed by the next run of that stage with the
reason recorded, and `retry` returns it to the queue. There is no state a row
can reach that nothing can move it out of.

A stage's failure is never an HTTP 500 — it is recorded against the row and
read back through `/{stage}/status`.

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
queue each stage once the one before it has finished: `POST /parsing/rerun`,
then `POST /chunking/rerun`, then `make extract-start`, then
`POST /topics/discover`, then `make extract-bridge MISSING=1`, then
`make questions-start`, and last `make questions-rejudge` and
`make questions-balance`. The bridge pass has no worker yet, so it runs on
the host. The host drains - `make parse-rerun`, `make chunk-rerun`,
`make extract`, `make topics-discover`, `make questions` - refuse while their
stage's worker runs, and are for developing a stage. Parsing and chunking
call no model; every step from extraction on does.

`make topics-discover` carries a topic's name over wherever its top terms
still match, so such a topic keeps the name the last fit gave it. Only the
topics it names afresh are named the v0.3.0 way: in one call per language,
in the corpus's own spelling, without the domain every name shares. A
carried name can be changed in the topic review: `make review-push-topics`,
then `make review-pull-topics`.

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
| `make extract-recap` | no | The atomic cap, now never below a passage's sentences plus list items |
| `make questions-rescore` | no | Each question's scope and difficulty, from the facts it cites now. Run it after `extract-dedup` and before re-verify, and not after any other re-run: there it would hide a question that lost a fact |
| `make questions-reverify` | no | The new gates, on every accepted question. It only rejects |
| `make questions-rejudge` | yes, the verifier | The `settles` judgement, on every accepted unanswerable question |
| `make questions-balance` | yes, the verifier | A release with the language share, hash order and twin check, the twins judged by the verifier |

Struck-through text, list lead-ins and chapter-aware section paths change
the passages themselves. They reach stored rows only through a rebuild by the container workers:
`POST /parsing/rerun`, then `POST /chunking/rerun`, then extraction, topics,
the bridge pass (`make extract-bridge`) and questions again, all of which
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

A claim two documents in the same language share, as the same kind of fact, rests on one of them only; a translation's claim is its own language's fact and is never a duplicate. The second copy is
stored as a `duplicate` refusal that names the first and cites only its own
passage. Deleting the first document therefore takes the claim with it,
and leaves the second copy refused. `make delete` and `make delete-derived`
then run `make extract-dedup` over the whole corpus. It calls no model,
gives that copy back, and re-judges and re-caps the passages of what it gave
back, and no others. A deletion through the API or the UI does not run it,
so run `make extract-dedup` yourself afterwards. No `make questions-rescore` follows
a deletion: the questions that rested on the deleted facts went with them.

The deletion and the replay are two steps. Both refuse beside a running
`extract-worker` container, and `make delete` asks before it deletes, so that
refusal leaves the document where it was. If the replay fails after the
deletion, the document is already gone, and running `make delete SHA=…`
again finds nothing to delete. The recovery is `make extract-dedup`, once
whatever stopped it is out of the way.
