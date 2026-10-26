# API

The HTTP surface the frontend and the orchestrator call. It reads back what
the stages produced and moves rows on and off a stage's queue. It never runs
a stage: workers do that off the queue (see
[`backend/stages/`](../stages/README.md)). `POST /pipeline/run` asks the
orchestrator for a run and answers at once with its id. Interactive docs are
at `http://localhost:8000/docs`.

## Structure

One FastAPI application ([`main.py`](main.py)) with a router per area in
[`routes/`](routes/). The process loads no model, converter or inference
library, and holds no Phoenix secret.

Read routes are nouns (`/documents`, `/passages`, `/facts`, `/topics`,
`/questions`, `/assessment`). Queue routes are verbs under a stage's name.
[`stage_router`](routes/stage.py) builds five of the six.

## The queue surface every stage shares

```
GET  /{stage}/status                      how much work is waiting; ?digests=true adds a hash of the rows per status, which reads the whole queue
POST /{stage}/{action}                    start | stop | retry | rerun | reclaim
GET  /{stage}/{scope}/{value}/status      the same, for one item
POST /{stage}/{scope}/{value}/{action}    the same verb, against fewer rows
```

| Verb | Moves |
|---|---|
| `start` | `new` to `pending`, the only status a worker claims |
| `stop` | `pending` to `new` |
| `retry` | A failed row back to `pending`, clearing the reason |
| `rerun` | Every row to `pending`, skipping what a worker holds right now |
| `reclaim` | An `in_progress` row back to `pending`, without waiting out its lease |

All five answer 202 at once and do no work: `/{stage}/status` shows whether a
worker took the rows. An unknown action is FastAPI's 422.

`reclaim` cannot tell a dead claim from a live one, so a whole stage needs
`?confirm=true`:

```
POST /parsing/document/{sha256}/reclaim   one item, while a worker may be up
POST /parsing/reclaim?confirm=true        the whole stage, once it is stopped
POST /parsing/reclaim                     400 confirm_required
```

`rerun` on `chunking` and `extraction` answers 409 `questions_rest_on_it`
while released, accepted or reviewed questions rest on the rows it replaces.
`?force=true` goes on and rejects them as `source_changed`; none is deleted.

| Stage | Narrows to | Example |
|---|---|---|
| `parsing` | `document` | `POST /parsing/document/{sha256}/start` |
| `chunking` | `document` | `POST /chunking/document/{sha256}/rerun` |
| `extraction` | `document`, `passage` | `POST /extraction/passage/{id}/retry` |
| `questions` | `topic` | `POST /questions/topic/{id}/rerun` |
| `topics` | none | A fit is all-or-nothing |
| `assessment` | `kind` | `POST /assessment/kind/question/start` |

[`routes/topics.py`](routes/topics.py) is written by hand: `POST /topics/discover`
writes a request row, and `/topics/stop` and `/topics/retry` are the only
other verbs. `POST /assessment/enrol` creates the assessment rows as `new`
without queuing them, so `/assessment/status` shows what `start` would cost.
It is not a dry run: the rows are written.

Every verb that queues rows answers with a `run` and writes it onto those
rows. Pass `?run=` to supply one (Dagster does); otherwise one is
minted. `stop` names no run.

## The corpus as one thing

[`routes/pipeline.py`](routes/pipeline.py) holds the controls that span stages.

```
GET  /pipeline              every stage's queue, the run in flight, what is automated
POST /pipeline/run          take the corpus through every stage but the topic fit, in order
POST /pipeline/start        queue everything ready to be worked: parsing, chunking, extraction, questions
POST /pipeline/stop         take back everything queued, and stop every run behind it
POST /pipeline/retry        return every stage's failures to the queue
GET  /pipeline/runs         the recent runs
GET  /pipeline/automation   whether anything starts a run by itself
PUT  /pipeline/automation   switch that on or off
```

`run` asks the orchestrator to launch its `corpus` job and returns the run's
id. `GET /pipeline`, `stop`, `runs` and both `automation` routes also call the
orchestrator. `start` and `retry` never do.

`start` queues one wave, as far as the corpus can go right now. A deployment
with no orchestrator calls it again after each drain. It leaves topic
modelling and assessment alone: a fit replaces every topic and the judge
costs model calls.

With `DAGSTER_URL` unset or the webserver down:

- `GET /pipeline` and `GET /pipeline/automation` say `available: false`.
- `run`, `GET /pipeline/runs` and `PUT /pipeline/automation` answer 503
  `no_orchestrator`.
- `start`, `stop` and `retry` keep working.

A second run is refused with 409 `already_running`. `make pipeline` and
Dagster's Materialize button bypass that check. The cap of one run is
`max_concurrent_runs: 1` in
[`configs/dagster/dagster.yaml`](../../configs/dagster/dagster.yaml).

Under `/pipeline`, `start` and `retry` take no `?run=`: each mints one id
for every stage it reaches and answers it as `queued_as`. `stop` stops every
unfinished run of the corpus job, newest first. Its `run` is the oldest run
stopped, and its `detail` names each run stopped or refused, with the reason.

## Routes

| Route | Answers |
|---|---|
| `POST /documents` | Uploads one file, and what became of it |
| `GET /documents` | The corpus, with stage statuses |
| `GET /documents/names` | Digests and filenames |
| `GET /documents/{sha256}/file` | The stored bytes |
| `DELETE /documents/{sha256}` | The document and everything derived from it |
| `DELETE /documents/{sha256}/derived` | Only its passages and facts |

[Ingestion](../ingestion/README.md) serves documents. Either `DELETE` answers
how many duplicate refusals lost the fact they repeated (`twinless`). The
extraction worker replays them when its queue is empty; with none running,
run `make extract-dedup`.

| Route | Answers |
|---|---|
| `GET /passages` | Passages, with heading trail, pages and tables |
| `GET /passages/types` | The block types present |
| `GET /passages/{id}` | One passage in full, with numbered sentences |
| `GET /facts` | Facts, accepted and rejected, with citations |
| `GET /facts/quality` | How many hold up, and why the rest were rejected |
| `GET /facts/{fact_id}/passages` | The passage ids one fact rests on, in the order the model saw them |

Passages are served by [chunking](../preprocessing/chunking/README.md), facts
by [extraction](../extraction/README.md).

| Route | Answers |
|---|---|
| `GET /topics` | Every topic, its terms, and its share of the corpus |
| `PATCH /topics/{id}` | Names a topic or takes it out of coverage reporting. A field left out is unchanged; `label: null` clears the name |
| `GET /topics/fit` | When the topics were fitted, over what, and whether they still fit the corpus |
| `GET /topics/visualisation/{language}` | One language's model as a pyLDAvis page. 404 until a fit or `make topics-render` draws it |
| `DELETE /topics` | Every topic and membership. Needs `?confirm=true` |

Topics are served by [topic modelling](../topic_modelling/README.md).

| Route | Answers |
|---|---|
| `GET /questions` | Questions, accepted and rejected |
| `GET /questions/{id}` | One question with the facts it was written from |
| `GET /questions/plan` | What generation is configured to write per topic |
| `GET /questions/quality` | How many hold up, which gate stopped the rest, and coverage |
| `GET /questions/export` | The questions a filter selects, as an `.xlsx`. With no filter it exports every question |
| `PATCH /questions/{id}` | Accepts or rejects one question |

Questions are served by [question generation](../question_generation/README.md).

| Route | Answers |
|---|---|
| `GET /assessment` | What an LLM judge made of each fact, topic and question |
| `GET /assessment/plan` | Whether the phase is on, who judges, and what each kind is asked |
| `GET /assessment/quality` | How much was judged, each metric, and where the judge and the pipeline disagree |
| `GET /prompts` | Recorded prompts with their text, newest first, narrowed by `service`, `version` and `name` |
| `GET /settings/{service}` | Each setting's value, file value, type, bounds, and whether it was changed |
| `PATCH /settings/{service}` | Changes a setting. A null value returns it to the file. A `fixed` setting (`LLM_BASE_URL`, every model name) is refused |
| `GET /health` | That the process is up, for the healthcheck |
| `GET /status` | Every component behind the API, and what each holds |
| `GET /services` | Every container, whether it listens, and its link |
| `GET /lineage/{kind}/{id}` | Everything one artefact was produced from, in pipeline order |

[The evaluation phase](../assessment/README.md) serves assessment, which has
no `PATCH`: a person who disagrees sets `reviewed_verdict` in
[`review/`](../../review/README.md). Prompts are read-only
([`backend/stages/`](../stages/README.md)). Settings are served by
[`backend/settings/`](../settings/README.md).

`/status` reports what the pipeline holds. `/services` reports what is up,
which proves only that something accepted a TCP connection. A worker serves
no port and is neither up nor down. Links come from `SERVICE_URLS`. The
database reads healthy on `/status` only at the code's migration head.

`GET /openapi.json` serves the schema, and [`main.py`](main.py) serves
`GET /docs` on it. There is no `/redoc`. The schema declares `X-API-Token` on
every write and every `/settings` read. The **Authorize** button takes the
deployment's `API_TOKEN`; without it those routes answer 401.

`GET /lineage` walks upwards only: a question to its facts, a fact to its
passages, a passage to its document. Each step carries its stage's verdict
and the judge's, capped at twenty artefacts. The
query lives in [`lineage.py`](lineage.py).

## Filtering and paging

`/documents`, `/passages`, `/facts` and `/questions` take `q` (a
case-insensitive substring), `limit` (1 to 500) and `offset`. The last three
also take `document`, and `/questions` takes `topic`. Each takes its own
filters: `parse_status`, `block_type`, `kind`, `method`, and on `/questions`
every classification column plus `released` (in the release or not).
`/questions/quality` and `/questions/export` take the listing's filter.
`/topics` takes none.

Each filter except `block_type` is a `Literal` listed in the OpenAPI
document. `block_type` is free text; `/passages/types` lists the values.

## Refusals

Every deliberate refusal answers with a stable `code` beside its message:

```json
{ "code": "unknown_document", "detail": "no document with that digest" }
```

| Code | Status | Raised when |
|---|---|---|
| `invalid_digest` | 400 | The path segment is not a SHA-256 |
| `invalid_language` | 400 | The language is not an ISO 639-1 code |
| `invalid_value` | 400 | A narrowed verb's value does not fit its column, or an upload's filename holds a NUL byte or a lone surrogate |
| `confirm_required` | 400 | `rerun` or `reclaim` over a whole stage, or `DELETE /topics`, without `?confirm=true` |
| `wrong_service` | 400 | A setting belongs to another service |
| `fixed_setting` | 400 | A setting is the deployment's: served read-only, never stored |
| `not_a_choice` | 400 | A value is not one the setting takes |
| `out_of_range` | 400 | A value is outside the setting's bounds, or holds a NUL byte or a lone surrogate |
| `would_not_load` | 400 | A stage that loads now would not with that value |
| `unauthorized` | 401 | A write, or any request under `/settings`, without the deployment's `API_TOKEN` as `X-API-Token` |
| `cross_site_write` | 403 | Any request carries `Sec-Fetch-Site: cross-site` or `same-site`, or a write carries a foreign `Origin`. `/docs` is exempt |
| `unknown_document`, `unknown_passage`, `unknown_question`, `unknown_topic` | 404 | No such document (by digest), passage, question or topic (by id) |
| `unknown_fact` | 404 | No fact with that id, on `/lineage` |
| `unknown_scope` | 404 | A stage was narrowed to a scope it does not accept |
| `unknown_setting` | 404 | A service has no setting by that name |
| `no_visualisation` | 404 | No fit or render has drawn that language's figure |
| `questions_rest_on_it` | 409 | `rerun` on `chunking` or `extraction` over questions that rest on it, without `?force=true` |
| `already_running` | 409 | `POST /pipeline/run` while a run is going |
| `assessment_cannot_run` | 409 | `POST /assessment/rerun` (or the kind-narrowed one) while `ASSESSMENT_ENABLED` is off or `ASSESSMENT_JUDGE_MODEL` names no model |
| `questions_running` | 409 | `POST /topics/discover` or `DELETE /topics` while a worker writes questions |
| `version_moved` | 409 | A settings change was sent against a version that is no longer current |
| `length_required` | 411 | An upload declares no `Content-Length` |
| `too_large` | 413 | An upload is over the size limit |
| `unsupported_type` | 415 | An upload is not a readable document of an accepted type |
| `internal_error` | 500 | Anything no route handled. The body names a trace id; the error is in the log under it |
| `no_orchestrator` | 503 | `run`, `GET /pipeline/runs` or `PUT /pipeline/automation` with no orchestrator |
| `orchestrator_refused` | 503 | The orchestrator answered the same three routes with an error |

Some answers have no `code`. A `Host` not in `API_ALLOWED_HOSTS` gets a
plain-text 400 from Starlette's `TrustedHostMiddleware`, and a malformed
query gets FastAPI's own 422. A stage's own failures are recorded against the
row and read through `/{stage}/status`.

Middleware answers `unauthorized` and `cross_site_write` before any route. The
secret is `API_TOKEN` from `.env`, generated by `make setup`. An API with none
set refuses every write. The frontend, orchestrator and make targets send it.
`QA_MODEL`, `NLI_MODEL`, `EMBEDDING_MODEL` and `DOCLING_ARTIFACTS_PATH` are
`fixed`, so a token holder cannot change what the workers load.

Callers that send neither `Sec-Fetch-Site` nor `Origin` (the frontend's
server, the orchestrator, `curl`) pass. Each refusal is logged once.

## Configuration

The API reads [`configs/env/backend.env`](../../configs/env/backend.env).
`DATABASE_POOL_SIZE` and `DATABASE_POOL_OVERFLOW` (the
connection pool), `API_ALLOWED_HOSTS` (the host names it answers to) and
`SERVICE_URLS` (where `/services` links each container) are served read-only
and marked `fixed`. Compose also sets `DAGSTER_URL`. See
[docs/configuration.md](../../docs/configuration.md).

## Tests

```sh
poetry run pytest tests/contract tests/integration/api
poetry run pytest tests/unit/api tests/static/test_api_stays_light.py
```

| Path | Covers |
|---|---|
| [`tests/contract/`](../../tests/contract) | The surface against [`openapi.json`](../../tests/contract/openapi.json), a committed fixture: a route added without updating it fails |
| `tests/unit/api/` | Refusals, request guards, query bounds, the orchestrator client, the service catalogue |
| `tests/integration/api/` | Every route group over HTTP, against the database |
| [`tests/static/test_api_stays_light.py`](../../tests/static/test_api_stays_light.py) | That the process loads no model, converter or inference library |
| [`tests/static/test_api_vocabularies.py`](../../tests/static/test_api_vocabularies.py) | The filters against the values the database holds |

## Limits

The API answers while no worker exists. A stage added since the stack came up
has no container until `make up`.
