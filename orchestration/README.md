# Orchestration

The Dagster code location: one asset per stage, a job, a schedule and two
sensors. It calls the API and nothing else.

Dagster decides when a stage runs and never runs one. It posts to the stage
routes and polls `/status` until nothing claimable is left, as the Start
button and the `make` targets do. Without this directory the pipeline runs
as before, with nobody deciding when.

## The call that comes the other way

`POST /pipeline/run` (the Run button on Documents, or the same call over
HTTP) asks the API to launch the `corpus` job here. The API therefore holds
this package's address, `DAGSTER_URL`.

- The API's call reaches the webserver's GraphQL and asks for a job by name.
- Without this directory, `DAGSTER_URL` points at nothing, `GET /pipeline`
  answers `available: false`, and the Run button is disabled with a line
  saying why. Every queue verb keeps working, including the corpus-wide
  `start`, `stop` and `retry`.
- What is lost is the wait between stages: the shell holds it for `make
  corpus`, and a Dagster run holds it for everything else.

The queries are pinned to Dagster 1.13 in
[`backend/api/orchestrator.py`](../backend/api/orchestrator.py).
`tests/smoke/test_orchestrator_queries.py` validates each against a live
webserver, using a job name that does not exist, so nothing is launched.

## The asset graph

```
parsed_documents → passages → facts → topics → questions → assessments
```

Materialising an asset starts that stage and waits for the workers to drain
it. Each asset has its own group, numbered by stage: `stage_2_parsing`
through `stage_7_assessment`, as in
[`telemetry/pipeline.py`](../telemetry/pipeline.py).

Failed rows are an asset check named `nothing_failed`, not an exception: the
reason is recorded against the row, and `retry` moves it. `questions` is the
slowest asset and the one most likely to reach
`ORCHESTRATION_DRAIN_TIMEOUT_SECONDS`.

## Triggers

| | |
|---|---|
| The `corpus` job | Every stage but the topic fit, in order. Run it from the Dagster UI, `make pipeline`, `make all`, the Run button or `POST /pipeline/run` |
| The `nightly_corpus` schedule | The `corpus` job at 02:00 UTC. Ships stopped |
| The `arrivals` sensor | Polls parsing every minute and requests a run when documents other than the last ones it asked about are `new` and `INGESTION_OPEN` is on. It requests none during a corpus run, while parsing has rows queued or in progress, or after a stopped run. A failed run is requested once more; after a second failure on the same documents it waits for `make pipeline` or the Run button. Ships stopped |
| The `progress` sensor | Polls every stage's `/status` every 30 seconds. It files an `AssetMaterialization` when a stage's worked count rose or its worked rows changed at the same count, and an `AssetCheckEvaluation` when its failed count moved. During a corpus run it files nothing and only moves its cursor. Ships running |

Switch the schedule and the `arrivals` sensor on from Dagster's UI or with
`PUT /pipeline/automation`. `make auto` and `make manual` switch the
`arrivals` sensor alone and fail unless Dagster reports it switched.

`progress` only watches, so it ships running. Without it, work started
outside a Dagster run (`make extract`, `POST /extraction/start`, the Start
button) leaves the asset graph saying "never materialised". The check files
on a move in either direction, so a `retry` turns the asset green again.

The cursor holds each stage's last worked and failed counts and the `/status`
digests of its worked rows. Only the sensor requests digests
(`/status?digests=true`), because the hash reads every row. The six `/status`
reads go out at once, one `Backend` per thread, to stay inside Dagster's
60-second tick limit.

`make up` starts the webserver and the daemon. The UI is at
<http://localhost:3000>.

## One corpus run at a time

[`configs/dagster/dagster.yaml`](../configs/dagster/dagster.yaml) sets
`max_concurrent_runs: 1` on a `QueuedRunCoordinator`. Two corpus runs would
interleave through the same queues.

`POST /pipeline/run` answers a second run with 409, holding an advisory lock
from the check through the launch. `make pipeline`, `dagster job launch` and
the Materialize button bypass that route, so the coordinator is the guarantee.

## Run ids on rows

Each asset passes its run's id to the stage route it starts (`?run=`). The
backend writes it onto the rows that verb queues, and the worker that claims
a row adopts it. A fact produced by a Dagster run carries that run's id, and
`GET /lineage` leads from the fact back to the run. When a caller names none,
the API mints an id and answers with it. `RUN_ID` overrides both, which keeps
the A/B in [`evaluation/README.md`](../evaluation/README.md) working.

## No database access

The orchestrator runs in its own image (372 MB, against 3.02 GB for the
backend), because it needs no torch, spaCy or model. It has no
`DATABASE_URL` and no object store credentials, and
`tests/smoke/test_compose.py` pins that.

## Running it

```bash
make logs-orchestration   # follow the webserver and the daemon
make dagster-dev          # the code location on the host, against the
                          #   containerised PostgreSQL and API
```

## Configuration

From [`configs/env/orchestration.env`](../configs/env/orchestration.env):

| Setting | What it does |
| --- | --- |
| `ORCHESTRATION_DRAIN_TIMEOUT_SECONDS` | How long an asset waits for a stage to drain. Giving up does not fail the rows |
| `ORCHESTRATION_POLL_SECONDS` | How often an asset polls the API |

Both are finite numbers of seconds, at least 1. The code location refuses
nan, inf and anything lower.

Also used: `BACKEND_URL`, the only address the assets and sensors call, and
`INGESTION_OPEN` from [`configs/env/backend.env`](../configs/env/backend.env),
which lets `arrivals` start a run at all. The instance and its code location
are configured in [`configs/dagster/`](../configs/dagster/).

## Tests

```sh
poetry run pytest tests/unit/orchestration
```

| File | Covers |
|---|---|
| [`test_definitions.py`](../tests/unit/orchestration/test_definitions.py) | The code location: the assets, the job without the fit, the stopped triggers, the one-run cap and the clearing of a dead run |
| [`test_assets.py`](../tests/unit/orchestration/test_assets.py) | What the asset and check bodies report, against a stand-in backend |
| [`test_orchestration_client.py`](../tests/unit/orchestration/test_orchestration_client.py) | The stage routes as the orchestrator reads them, and the run id it carries |
| [`test_sensor.py`](../tests/unit/orchestration/test_sensor.py) | When a run is requested, and what `progress` records |
| [`tests/smoke/test_compose.py`](../tests/smoke/test_compose.py) | That the orchestrator holds no credential for the application tables |

None of these reaches a network.

## Limits

- A timeout is not a failure. An asset that gives up leaves every row where
  it was, and the workers keep draining.
- The `corpus` job ends at `assessments` and draws no release. `make
  questions-balance` draws one, and `make corpus` runs it after `questions`.
- A materialisation does not mean Dagster ran the stage: `progress` files
  one for work any surface started. That work appears on the asset page and
  not in the run list. The run id on the rows joins it to its logs.
- A second corpus run queues instead of racing. Only `POST /pipeline/run`
  refuses it, with 409.
- A run whose process died holds the single slot until run monitoring clears
  it. The daemon marks a run still stopping after 180 seconds as stopped. A
  run left `STARTED` is failed after 48 hours, because the default launcher
  cannot tell whether its process is alive. Terminating it in Dagster's UI is
  quicker. Both limits are in
  [`configs/dagster/dagster.yaml`](../configs/dagster/dagster.yaml).
