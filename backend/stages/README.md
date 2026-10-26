# Stages

Six stages run off one queue. A stage owns a status column, an error column
and the timestamp of its claim, and supplies only those columns and its work.
Claiming, failing, sweeping, requeueing, draining and the command line are
written here once.

The `make` targets (`make parse`, `make extract-start SHA=…`) wrap the
parser built here. See [docs/make.md](../../docs/make.md).

## The model

Nothing starts by itself. A row arrives `new`, which no worker looks at.
`start` moves it to `pending`, the only status a worker claims, and `stop`
moves it back. A stage never starts another stage.

A `make` target, the Start button, `POST /{stage}/start` or the orchestrator
starts a stage. Only the orchestrator runs the stages in order. See
[`orchestration/`](../../orchestration/README.md) and `POST /pipeline/run`.

A stage claims on its own status column and on nothing else, so two stages
can own different columns of the same `documents` row.

```
new  ──start──▶  pending  ──claimed──▶  in_progress  ──▶  done
 ▲                   ▲                   │  ▲│
 └──────stop─────────┤                   │  └┘ heartbeat, every 30s
                     │                   ├──▶  failed  ──retry──▶  pending
                     │                   └──beat missed for 5 min──▶ failed
                     └────────reclaim────┘
```

### Queueing and claiming

A row may enter the queue only when `RowQueue.ready` says so. Chunking is the
only stage that declares one, so that `start` skips documents still waiting
to be parsed:

```python
ready = Document.parse_status == Status.PARSED
```

`start` and `reset` use `ready`. It gates queueing, never claiming: a row
already `pending` is worked whatever `ready` says.

Claiming uses `SELECT … FOR UPDATE SKIP LOCKED`, one row at a time, so two
workers never take the same row. Extraction runs at most two drains side by
side ([Scaling](../../docs/operations.md#scaling)):

```bash
podman compose up -d --scale extract-worker=2
```

A queue claims nothing while the database is behind the code's migration
head.

### Leases and the heartbeat

A worker refreshes `claimed_at` every `HEARTBEAT_SECONDS` while it holds a
row. The lease is the number of beats that may be missed before another run
sweeps the claim: five minutes, for every stage.

The next drain fails a row whose worker died, recording `the worker did not
finish; the run was interrupted`. `retry` returns it to the queue. A worker
whose row was swept and claimed again cannot finish, fail or refresh it.

### Narrowing

Every queue operation takes an optional `within`. A stage declares the
narrowings it accepts as `scopes`.

| Stage | Accepts |
|---|---|
| Parsing | `document` |
| Chunking | `document` |
| Extraction | `document`, `passage` |
| Question generation | `topic` |
| Assessment | `kind` |
| Topic modelling | none |

A scope a stage does not accept, or a value its column cannot hold, raises
`Unnarrowable`, with a `code` for the API and a message for the command line.

## The command line

```
python -m <stage>.run [--status|--start|--stop|--retry|--reclaim|--rerun|--wait] [--only SCOPE=VALUE] [--watch]
```

The actions are mutually exclusive.

| Flag | Does | Has a route |
|---|---|---|
| `--status` | Report the queue depth | yes |
| `--start` | Queue the rows never asked for | yes |
| `--stop` | Take back what has not begun | yes |
| `--retry` | Return failed rows to the queue | yes |
| `--rerun` | Queue every row again, finished ones included, then drain. Runs the preflight first | yes |
| `--reclaim` | Return a row a dead worker still holds, without waiting out its lease. See [`reclaim`](#reclaim) | yes |
| `--wait` | Wait for the stage's container worker to empty the queue, logging counts. Exits 3 when rows failed meanwhile, 75 when told to stop. Not in topic modelling | no |
| `--only SCOPE=VALUE` | Narrow the action to one item. Refused on a bare drain, and on `--rerun` while rows outside it are queued. Topic modelling ignores it | no |
| `--watch` | Drain, and keep draining | no |
| no flag | Drain the queue once, in the foreground, and stop | no |

```bash
python -m preprocessing.parsing.run --status
python -m preprocessing.chunking.run --start --only document=<sha256>
python -m extraction.run --retry --only passage=42
python -m topic_modelling.run --status
python -m question_generation.run --rerun --only topic=7
```

Stages add flags for their own operations: `--revocabulary` (chunking), `--revalidate`, `--bridge`,
`--recap`, `--dedup` and `--embed` (extraction), `--reverify`, `--rescore`,
`--rejudge` and `--balance` (question generation), `--enrol` (assessment).

Topic modelling builds its parser from its own actions. It has no `start`,
`rerun` or `--reclaim`: a fit is one request row.

### What a drain exits with

| Exit | Means |
|---|---|
| 0 | Every row was worked |
| 3 | A row failed and the drain went on past it (`--retry` returns it). Or the start was refused before anything was claimed: a split the production profile cannot run, a stored row the catalogue refuses, or a model that does not answer |
| 75 | The drain stopped itself, left what it held in the queue, and wants starting again |

A drain stops itself, and exits 75, in three cases:

- The model could not be reached for five rows in a row (`STOP_AFTER`). The
  five go back to the queue, not to `failed`. An outage is a timeout, a
  refused connection, a 429 past its patience, a 5xx, or bad credentials,
  deployment name or permission. A request the provider rejects for that row
  (bad request, context too long, content filter) is not an outage: the row
  fails and the drain takes the next. One good row ends the count.
- Extraction's model answered nothing for half of the last 50 readable
  passages. Those passages and the one in hand go back to the queue. The stop
  lasts until the worker's settings change.
- `SPEND_CAP` is reached. The drain adds up litellm's price for each call and
  stops before claiming the row that would pass the cap. With a cap set, a
  model litellm cannot price is refused at the start.

The passes that call a model outside the drain loop obey the cap too. Each
keeps what it wrote and exits 75. `--bridge` stops between topics, and
`make extract-bridge MISSING=1` resumes. `--balance` stops between judged
pairs. A rerun pays for the twin pairs again, so the cap must exceed what one
balance costs. `--rejudge` stops between questions, and a rerun asks only for
what no run has done.

A one-off drain handles signals as [the worker](#the-worker) does. Before it
starts, it prints how many rows are queued and the estimated cost. A watching
worker does not exit after a stop: it waits the poll interval and tries
again.

### `reclaim`

`abandon` is the automatic sweep, on a lease. `reclaim` frees a row held by a
killed worker without waiting out the lease. `retry`, `rerun` and `stop` do
not reach such a row.

Narrow it. Nothing can tell a dead claim from a live one:

```bash
make questions-reclaim TOPIC=473   # one topic, while a worker may be up
make questions-reclaim             # every one the stage holds. Only when it is stopped
```

The route enforces the narrowing. Every write needs the API token:

```bash
curl -X POST -H "X-API-Token: $API_TOKEN" localhost:8000/questions/topic/473/reclaim   # one topic
curl -X POST -H "X-API-Token: $API_TOKEN" localhost:8000/questions/reclaim             # 400, confirm it
curl -X POST -H "X-API-Token: $API_TOKEN" 'localhost:8000/questions/reclaim?confirm=true'
```

### Before the first claim

`queue_main` takes two optional callables, both run before anything is
drained.

`preflight` proves the stage can work: for a stage that calls a model, that
the model answers. It raises, and the process stops with nothing taken.
`--rerun` runs it before queueing, so a failing model leaves every stored row
as it was. A watching worker retries instead, backing off from 5 seconds
towards 60. The first refusal is logged in full, repeats are counted every ten
minutes, and recovery gets a line.

`prompts` records what the stage sends, so the version stamped on each row
resolves to its text. It runs after the preflight and never fails a start. A
text rewritten under an unchanged version is warned about and stored. See
[`prompts.py`](prompts.py) and [`backend/database/`](../database/README.md).

What it wrote is also published to Phoenix. See [`publish.py`](publish.py).
`make prompts-publish` republishes everything, for a Phoenix wiped while the
rows stayed.

### The worker

`--watch` is what the worker containers run: drain, sleep
`WORKER_POLL_SECONDS`, drain again.

`SIGTERM` and `SIGINT` make the worker stop claiming and finish the item it
holds. A second signal, or the stage's grace after the first (`GRACE_SECONDS`:
90 s for parsing and chunking, 270 s for stages that call a model), returns
the held row to the queue as pending and exits 75. `compose.yaml` gives each
worker a `stop_grace_period` above its grace by `RELEASE_MARGIN` (30 s), and a
test holds the two together. A worker killed regardless is swept by the lease.

A watching worker rebuilds its service between drains when the settings
change, running its `preflight` and recording its prompts again. A failed
build claims nothing and is retried after five seconds, doubling to an hour.

A `make` target runs one drain on the host, in the foreground, against the
containers' database. It refuses while the stage's worker container is
running. Container workers build the dataset; a host drain is for developing a
stage. Nothing keeps a host run out of the
dataset: a host parse, chunk or extract drain writes the same tables in the
same database as the workers, and only `RUN_ID`, when set, tells its rows
apart. The refusal checks only that the stage's worker is stopped. Do not
build the dataset with a host drain.

## Recalibrating stored confidences

`make confidence-recalibrate` runs [`recalibrate.py`](recalibrate.py). After a
change to `QUESTIONS_DUPLICATE_FLOOR` or `EXTRACTION_DUPLICATE_FLOOR`, it
re-reads every stored margin, with the stored overrides applied, and rewrites
`gate_scores` and `confidence` on the questions and the facts.

It calls no model and moves no verdict: `status` and `rejected_reason` stay
as they are (`make questions-reverify` changes verdicts). A second run writes
nothing. It works in batches of 300 without a lock, and a row changed
meanwhile is left for the next run.

A row written before `gate_scores` recorded a direction takes it from
`_REFUSES_HIGH`: `near_duplicate` and `duplicate` refuse a high reading. An
entry marked `opinion`, such as `settles`, has no margin and never enters a
recalculated confidence.

## Configuration

| Setting | What it does |
|---|---|
| `WORKER_POLL_SECONDS` | How long a watching worker sleeps between drains. Fixed: served read-only, never stored |
| `SPEND_CAP` | The most, in USD, one drain spends on model calls. Unset: no cap. Fixed. See [What a drain exits with](#what-a-drain-exits-with) |

## Tests

```sh
poetry run pytest tests/unit/stages tests/integration/database/test_queue.py
```

Unit tests cover the command line and narrowing (`test_cli.py`,
`test_queue_narrowing.py`), the worker loop (`test_worker.py`), recalibration
(`test_recalibrate.py`) and prompt recording and publishing
(`test_prompt_recording.py`, `test_prompt_publishing.py`). Integration tests
run claiming, the lease sweep and the verbs on PostgreSQL (`test_queue.py`,
`test_question_queue.py`), prompt storage (`test_prompt_store.py`), settings
reloading (`test_reloading.py`) and the five verbs over HTTP
(`test_stages.py`).

## Limits

- `topics` carries two queues on one table. A row with a NULL `topic_index`
  is a request to refit. A row that is a topic belongs to question
  generation, and every operation on it carries `topic_index IS NOT NULL`.
- `rerun` skips what a worker holds right now. `reclaim` is the one verb that
  can hand a live worker's row to a second one.
- A `make` drain refuses only while compose reports the stage's worker
  running. With no engine answering, it drains.
- Scaling `topic-worker` past one achieves nothing.
- A stage's failure never reaches the API as a 500.
