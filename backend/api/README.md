# API

The HTTP surface the frontend and the orchestrator call, and the only address
either of them holds.

It **reads back** what the stages produced and **moves rows on and off a
stage's queue**. It never runs a stage: no route here does a stage's work,
because a conversion running inside the process that serves JSON holds that
request until it finishes. The work happens in the stage's worker
container, off the queue this API writes to — see
[`backend/stages/`](../stages/README.md).

`POST /pipeline/run` is not an exception to that. It runs nothing either: it
asks the **orchestrator** for a run and answers at once with its id. That is
the one thing on this surface the backend cannot do alone, and
[`/pipeline`](#the-corpus-as-one-thing) says why.

## What it does

One FastAPI application, assembled in [`main.py`](main.py): the two request
guards are installed, then the refusal handler, and every router in
[`routes/`](routes/) is included. Wiring is built once in
[`dependencies.py`](dependencies.py) and injected; the one route module that
builds anything itself is `routes/settings.py`, which holds a settings store.

It exports no span and holds no Phoenix secret: telemetry is configured with
no run, so its log lines carry trace ids and nothing is sent to Phoenix.

The process **loads no model, no converter and no inference library**. It
imports a stage's catalogue for a read route and a stage's queue for a queue
route, plus the light modules beside them a route reads (a stage's
configuration, assessment's templates, ingestion's upload service); question
generation's export, which loads pandas, is imported inside the one route
that writes a workbook. Because a service package re-exports
nothing, importing `extraction.repository` does not drag litellm, Docling,
gensim or spaCy into this process.
`tests/static/test_api_stays_light.py` pins that.

### The two kinds of route

**Read routes** are a noun: `/documents`, `/passages`, `/facts`, `/topics`,
`/questions`, `/assessment`. **Queue routes** are a verb under a stage's name: `/parsing`,
`/chunking`, `/extraction`, `/questions`, `/topics`, `/assessment`. Five of
the six are built by one factory — [`stage_router`](routes/stage.py) — so a
verb cannot mean two things depending on which stage answered it.

`/questions`, `/topics` and `/assessment` are the paths that are both,
because in each case the stage and what it produces share the word. The
queue routes are declared first, which keeps `/questions/status` from being
read as a question with the id `status`.

### The queue surface every stage shares

```
GET  /{stage}/status                      how much work is waiting; ?digests=true adds a hash of the rows per status, which reads the whole queue
POST /{stage}/{action}                    start | stop | retry | rerun | reclaim
GET  /{stage}/{scope}/{value}/status      the same, for one item
POST /{stage}/{scope}/{value}/{action}    the same verb, against fewer rows
```

The narrowed form is a `WHERE` on the stage's own table and nothing more, so
a narrowed verb and a whole-queue one cannot disagree.

| Verb | Moves |
|---|---|
| `start` | `new` → `pending`, the only status a worker claims |
| `stop` | `pending` → `new` |
| `retry` | a failed row back to `pending`, clearing the reason |
| `rerun` | every row to `pending`, skipping what a worker holds right now |
| `reclaim` | an `in_progress` row back to `pending`, without waiting out its lease |

All five answer **202** and return at once. None does the work.

`reclaim` used to be on the command line and deliberately not here, on the
grounds that the API cannot know a worker is gone. Neither can the command
line — a person runs both — and what the absence actually cost was the one
stuck row none of the other verbs reaches: `retry` takes the failed, `rerun`
skips what is held, and `stop` takes back only what has not begun. So it is
here, and the danger is answered by the thing that actually addresses it:

```
POST /parsing/document/{sha256}/reclaim   one item, while a worker may be up
POST /parsing/reclaim?confirm=true        the whole stage, once it is stopped
POST /parsing/reclaim                     400 confirm_required
```

Nothing here can tell a dead claim from a live one, so the unnarrowed form
asks to be confirmed rather than being refused outright. See
[`backend/stages/`](../stages/README.md).

`rerun` on `chunking` and `extraction`, whole or narrowed, answers 409
`questions_rest_on_it` while released, accepted or reviewed questions rest on
what it would replace, naming how many; `?force=true` goes on. The rows it
replaces reject those questions as `source_changed`; none is deleted.

| Stage | Narrows to | Example |
|---|---|---|
| `parsing` | `document` | `POST /parsing/document/{sha256}/start` |
| `chunking` | `document` | `POST /chunking/document/{sha256}/rerun` |
| `extraction` | `document`, `passage` | `POST /extraction/passage/{id}/retry` |
| `questions` | `topic` | `POST /questions/topic/{id}/rerun` |
| `topics` | — | a fit is all-or-nothing over one vocabulary |
| `assessment` | `kind` | `POST /assessment/kind/question/start` |

Topic modelling's routes are written out in
[`routes/topics.py`](routes/topics.py) rather than built by the factory:
`POST /topics/discover` writes a request row, and `/topics/stop` and
`/topics/retry` are the only other verbs that mean anything.

The assessment phase has one more of its own, `POST /assessment/enrol`:
nothing upstream creates an assessment, so enrolling without queuing is how
"judge the corpus" becomes a number before any of it is paid for.

### The corpus as one thing

[`routes/pipeline.py`](routes/pipeline.py). Two controls no stage route can
have, because neither is about one stage.

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

**Why `run` needs somebody else.** Stages have to be sequenced — chunking
needs a parsed document — and sequencing means waiting for one to drain
before starting the next. A request cannot hold that wait: extraction over
a real corpus is hours. So `run` asks the orchestrator, which is the one
component whose whole job is deciding when a stage should run, and returns
the run's id at once. `GET /pipeline`, `stop`, `runs` and both `automation`
routes talk to the orchestrator too; `start` and `retry` never do.

**`start` is the same idea without the waiting.** It queues one wave — as
far as the corpus can go right now — and is what a deployment with no
orchestrator uses. Calling it again after the workers drain moves it the
next stretch. It leaves topic modelling and the assessment phase alone: a
fit replaces the topics of every language it fits and the judge costs model
calls `.env` opts into, so both are asked for rather than swept into a
fan-out.

**Everything degrades except `run`, the run list and the automation
switch.** `DAGSTER_URL` unset, or a webserver that is down, answers
`available: false` on `GET /pipeline` and `GET /pipeline/automation`, and
**503 `no_orchestrator`** on `run`, `GET /pipeline/runs` and
`PUT /pipeline/automation`, while `start`, `stop` and `retry` go on
working — those are queue verbs, and the queue is the backend's own. A
second run is refused with **409 `already_running`** rather than racing the
first through the same queues. That refusal is an affordance and not the
guarantee: it holds an advisory lock from reading the run list to the
launch, so two requests cannot both pass it, but `make pipeline` and
Dagster's own Materialize button never reach it. What actually caps the
corpus at one run is `max_concurrent_runs: 1` in
[`configs/dagster/dagster.yaml`](../../configs/dagster/dagster.yaml).

**Every verb that queues rows names a run.** A stage's `start`, `retry`,
`rerun` and `reclaim`, and `/topics/discover` and `/topics/retry`, answer
with `run`, write it onto the rows they queued, and the worker that claims
one adopts it — so what the rows record is the thing that asked rather than
the worker that happened to take them. Pass `?run=` to supply one (Dagster
passes its own run id); leave it out and one is minted. `stop` queues
nothing and so names nothing.

Under `/pipeline`, `start` and `retry` take no `?run=`: each mints one id for
every stage it reaches and answers it as `queued_as`. There `run` is the
Dagster run, set only by `stop` when it stopped one.

**`stop` stops every live run, newest first,** because a queued run left
behind is started the moment the one before it stops. Its `run` is the oldest
it stopped, the one that was doing the work, and its `detail` names every run
it stopped and every one Dagster would not stop, with the reason. Dagster
stops only a queued or a started run, so a run an earlier press left stopping
is named as already stopping rather than asked again. It asks Dagster for
every unfinished run of the corpus job, not the five newest `GET /pipeline`
shows, so the run at work is reached however many are queued behind it.

## The full surface

**Documents** — served by [ingestion](../ingestion/README.md).

| Route | Answers |
|---|---|
| `POST /documents` | Upload one file, and what became of it |
| `GET /documents` | The corpus, with each document's stage statuses |
| `GET /documents/names` | Digests and filenames, for a picker |
| `GET /documents/{sha256}/file` | The stored bytes back |
| `DELETE /documents/{sha256}` | The document and everything derived from it |
| `DELETE /documents/{sha256}/derived` | Only its passages and facts |

A fact another document repeats was refused as a duplicate of this one's, and
is given back by the dedup replay. Either `DELETE` answers how many such
refusals lost the fact they repeated (`twinless`), and leaves them to the
extraction worker, which finds a refusal pointing at no twin when its queue is
empty and runs the replay `make extract-dedup` runs; with no worker running,
run `make extract-dedup` after one.

**Passages** — served by [chunking](../preprocessing/chunking/README.md).

| Route | Answers |
|---|---|
| `GET /passages` | Passages, with their heading trail, pages and tables |
| `GET /passages/types` | The block types the corpus holds |
| `GET /passages/{id}` | One passage in full, its numbered sentences and cell grids |

**Facts** — served by [extraction](../extraction/README.md).

| Route | Answers |
|---|---|
| `GET /facts` | Facts, accepted and rejected alike, with what they cite |
| `GET /facts/quality` | How many hold up, and why the rest were rejected |
| `GET /facts/{fact_id}/passages` | The ids of the passages one fact rests on, in the order the model saw them |

**Topics** — served by [topic modelling](../topic_modelling/README.md).

| Route | Answers |
|---|---|
| `GET /topics` | Every topic, its terms, and how much of the corpus it holds |
| `PATCH /topics/{id}` | Name a topic, or take it out of coverage reporting. A field left out of the body is left as it is; `label: null` clears the name |
| `GET /topics/fit` | When the topics were fitted, over what, and whether they still describe the corpus |
| `GET /topics/visualisation/{language}` | One language's model as a pyLDAvis page |
| `DELETE /topics` | Every topic and membership |

**Questions** — served by
[question generation](../question_generation/README.md).

| Route | Answers |
|---|---|
| `GET /questions` | Questions, accepted and rejected alike |
| `GET /questions/{id}` | One question with the facts it was written from |
| `GET /questions/plan` | What generation is configured to write per topic: the type and band mix, the shares and the answer bounds |
| `GET /questions/quality` | How many hold up, which gate stopped the rest, and coverage |
| `GET /questions/export` | The questions a filter selects, as an `.xlsx`. No default scope |
| `PATCH /questions/{id}` | Accept or reject one question |

**Assessment** — served by [the evaluation phase](../assessment/README.md).

| Route | Answers |
|---|---|
| `GET /assessment` | What an LLM judge made of each fact, topic and question |
| `GET /assessment/plan` | Whether the phase is on, who judges, and what each kind is asked |
| `GET /assessment/quality` | How much was judged, how each metric did, and where the judge and the pipeline disagree |

There is no PATCH, deliberately. A judgement is a record of what a model
said; a person who disagrees has `reviewed_verdict`, through
[`review/`](../../review/README.md) or the Facts and Questions pages.

**Prompts** — served by [`backend/stages/`](../stages/README.md).

| Route | Answers |
|---|---|
| `GET /prompts` | Every recorded prompt, newest version first by number, narrowed by `service`, `version` and `name` |

`facts.prompt_version` and `questions.prompt_version` name a version, and
until this table nothing resolved one: the span carrying the prompt belongs
to a Phoenix project with a retention of its own, and the row outlives it.

Read-only, and there is no route that writes one. A prompt is changed in the
source and recorded by the stage that sends it. It serves the table rather
than asking the code, which is what keeps litellm out of this process. The
text comes with the listing rather than behind a second call.

**Settings** — served by [`backend/settings/`](../settings/README.md).

| Route | Answers |
|---|---|
| `GET /settings/{service}` | Each setting's value, what the files say, its type, its bounds, and whether somebody changed it |
| `PATCH /settings/{service}` | Change it. A null value returns one setting to the file. A `fixed` setting, `LLM_BASE_URL` and every model name among them, is refused |

**The platform.**

| Route | Answers |
|---|---|
| `GET /health` | That the process is up, for the container healthcheck |
| `GET /status` | Every component behind the API, and what each service holds |
| `GET /services` | Every container, whether it is listening, and where to open it |

`/status` reports what the pipeline **holds**, counted out of the database;
`/services` reports what is **up**. A page wanting both asks twice. The
database reads healthy on `/status` only when it is at the code's migration
head; otherwise the detail names both revisions.

What `/services` proves is that something accepted a TCP connection on the
port — one code path for a web UI, a database and a broker, with no auth and
no TLS. The alternative was nine health protocols, nine sets of credentials,
and a page reporting Argilla as failed because it answered 401. A worker
serves no port and is reported as neither up nor down. `SERVICE_URLS` is
where the links come from; a service nobody published gets no link.

FastAPI serves its schema beside these at `GET /openapi.json`, and
[`main.py`](main.py) serves `GET /docs` on it. That page loads Swagger UI from
the CDN by exact version, where FastAPI's own names only the major version
and so runs whatever was last published under it. There is no `/redoc`.

### How one artefact was produced

| Route | Answers |
|---|---|
| `GET /lineage/{kind}/{id}` | Everything one document, passage, fact, topic or question was produced from, in pipeline order |

The one route that crosses every service, and the only one whose query
lives here rather than in a stage's repository — [`lineage.py`](lineage.py)
reads the same models the service repositories read, and the api is
already the only layer above all seven.

It walks **upwards**: a question to its facts, a fact to its passages, a
passage to its document. What came of an artefact is the listing each page
already answers with a filter.

Each step is numbered by the stage that produced it, carries that stage's
verdict and what the judge made of it, and links each artefact to its own
span. A step is capped at twenty artefacts and reports its own total,
because one topic in a real corpus holds hundreds of passages.

For a question it also reports `gates` — every gate that read it, at
its fixed position. `gates_recorded` is false for a question written
before that column existed.

### Filtering and paging

`/documents`, `/passages`, `/facts` and `/questions` all take `q` for a
case-insensitive substring and `limit`/`offset` to page. The last three also
take `document`, and `/questions` takes `topic` as well. Each takes the
filters its page offers — `parse_status`, `block_type`, `kind` and `method`,
and on `/questions` every column a question is classified by and `released`,
whether it is in the release. `/questions/quality` and `/questions/export`
take the listing's filter.

Each but `block_type` is spelled as a `Literal` so the OpenAPI document lists
its values and the frontend's pickers cannot drift; `block_type` is free
text, and `/passages/types` lists what the corpus holds.
`tests/static/test_api_vocabularies.py` holds the question classifications,
the band, the assessment metric and the settings service equal to the
copies they mirror.

`/topics` takes none and returns every topic at once.

## Refusals

Every deliberate refusal answers with a stable `code` beside its message, so
a caller branches on the code rather than on English:

```json
{ "code": "unknown_document", "detail": "no document with that digest" }
```

| Code | Status | Raised when |
|---|---|---|
| `invalid_digest` | 400 | The path segment is not a SHA-256 |
| `invalid_language` | 400 | The language is not an ISO 639-1 code |
| `invalid_value` | 400 | A narrowed verb was given a value its column cannot hold, or an upload's filename holds a NUL byte or a lone surrogate |
| `confirm_required` | 400 | `rerun` or `reclaim` over a whole stage, or `DELETE /topics`, without `?confirm=true`; the answer names the stage's rows, with the released, accepted or reviewed questions a rerun of `chunking` or `extraction` would reject as `source_changed`, or the topics at stake |
| `questions_rest_on_it` | 409 | `rerun` on `chunking` or `extraction` while released, accepted or reviewed questions rest on what it replaces, without `?force=true` |
| `wrong_service` | 400 | A setting belongs to another service |
| `fixed_setting` | 400 | A setting is the deployment's: served read-only, never stored |
| `not_a_choice` | 400 | A value is not one the setting takes |
| `out_of_range` | 400 | A value is outside the setting's bounds, or holds a NUL byte or a lone surrogate |
| `would_not_load` | 400 | A stage that loads now would not with that value |
| `unknown_document` | 404 | No document with that digest |
| `unknown_passage` | 404 | No passage with that id |
| `unknown_fact` | 404 | No fact with that id, on `/lineage` |
| `unknown_question` | 404 | No question with that id |
| `unknown_topic` | 404 | No topic with that id |
| `unknown_scope` | 404 | A stage was narrowed to a scope it does not accept |
| `unknown_setting` | 404 | A service has no setting by that name |
| `no_visualisation` | 404 | No fit or render has drawn that language's figure |
| `unauthorized` | 401 | A write, or any request under `/settings`, without the deployment's `API_TOKEN` as `X-API-Token` |
| `internal_error` | 500 | Anything no route handled: a fixed sentence naming a trace id, with the error itself in the log under that id |
| `cross_site_write` | 403 | A request of any method carries `Sec-Fetch-Site: cross-site` or `same-site`, or a write carries an `Origin` that is not the API's own; `/docs` alone is exempt, so the health page's link opens |
| `already_running` | 409 | `POST /pipeline/run` while a run is going |
| `assessment_cannot_run` | 409 | `POST /assessment/rerun` (or the kind-narrowed one) while `ASSESSMENT_ENABLED` is off or `ASSESSMENT_JUDGE_MODEL` names no model; no verdict is cleared |
| `questions_running` | 409 | `POST /topics/discover` or `DELETE /topics` while a worker is writing questions from a topic, which the fit or the delete would take from under it |
| `version_moved` | 409 | A settings change was sent against a version that is no longer current |
| `length_required` | 411 | An upload declares no `Content-Length` |
| `too_large` | 413 | An upload is over the size limit |
| `unsupported_type` | 415 | An upload is not a readable document of an accepted type |
| `no_orchestrator` | 503 | `run`, `GET /pipeline/runs` or `PUT /pipeline/automation` with no orchestrator answering |
| `orchestrator_refused` | 503 | The orchestrator answered `run`, `GET /pipeline/runs` or `PUT /pipeline/automation` with an error |

A request whose `Host` is not in `API_ALLOWED_HOSTS` is answered 400 by
Starlette's `TrustedHostMiddleware` before any route reads it, as plain text
rather than a body with a code.

`unauthorized` is answered by the same middleware, after the origin test. The
secret is `API_TOKEN` from `.env`, generated by `make setup`; it is compared in
constant time, and an api with none set refuses every write. The frontend, the
orchestrator and the make targets send it. `QA_MODEL`, `NLI_MODEL`,
`EMBEDDING_MODEL` and `DOCLING_ARTIFACTS_PATH` are `fixed`, so a secret holder
cannot change what the workers load.

`cross_site_write` is answered by the middleware in [`main.py`](main.py),
also before any route. The frontend's server, the orchestrator, `curl` and
the tests send neither header and pass; so does the `/docs` page, whose
calls are same-origin. A read a browser sends from another site is refused
too, because the export and the quality report are expensive; the same page
could not read its answer, but it could make the api build it.

FastAPI's 422 for a malformed query is left alone, and **a stage's own
failures are not answered here at all** — they are recorded against the row
and read back through `/{stage}/status`.

Anything no route handled is answered 500 `internal_error` by one handler: a
fixed sentence naming a trace id, with the error, which may hold the
database's host, address and role, in the log under that id. `/status` reports
an unreachable component as such and nothing the driver said.

Each refusal is logged once, in the handler rather than at each `raise`, at
**warning**.

## Configuration

The API reads the same
[`configs/env/backend.env`](../../configs/env/backend.env) the workers do.
Its address and pool sizes are the deployment's: `DATABASE_POOL_SIZE` and
`DATABASE_POOL_OVERFLOW` are served read-only and marked `fixed`. So are the
two settings only the API reads: `API_ALLOWED_HOSTS`, the host names it
answers to, and `SERVICE_URLS`, where `/services` links each container.
Compose also hands it `DAGSTER_URL`, the orchestrator's address. The
pipeline version it stamps on a stored upload is read from the working tree's
`pyproject.toml`, which compose mounts read-only. See
[docs/configuration.md](../../docs/configuration.md).

## Tests

```sh
poetry run pytest tests/contract tests/integration/api
poetry run pytest tests/unit/api tests/static/test_api_stays_light.py
```

| File | Covers |
|---|---|
| [`tests/contract/test_openapi.py`](../../tests/contract/test_openapi.py) | The published surface against [`openapi.json`](../../tests/contract/openapi.json) |
| [`tests/contract/test_openapi_conformance.py`](../../tests/contract/test_openapi_conformance.py) | The document and the server, checked against each other by generated calls |
| [`tests/unit/api/test_errors.py`](../../tests/unit/api/test_errors.py) | The shape every deliberate refusal takes |
| [`tests/unit/api/test_request_guards.py`](../../tests/unit/api/test_request_guards.py) | What is answered before any route reads a request |
| [`tests/unit/api/test_params.py`](../../tests/unit/api/test_params.py) | Every free-text query parameter, bounded before it reaches the driver |
| [`tests/unit/api/test_question_filters.py`](../../tests/unit/api/test_question_filters.py) | The `released` filter, as the three question reads parse it |
| [`tests/unit/api/test_question_plan.py`](../../tests/unit/api/test_question_plan.py) | The plan the questions page draws, from stored settings that no longer load |
| [`tests/unit/api/test_orchestrator.py`](../../tests/unit/api/test_orchestrator.py) | Dagster as the API calls it, against replies a real webserver gave |
| [`tests/unit/api/test_services.py`](../../tests/unit/api/test_services.py) | The service catalogue, and what a probe of it reports |
| [`tests/unit/api/test_settings_reads.py`](../../tests/unit/api/test_settings_reads.py) | What the settings page is handed, read against a store that moves |
| [`tests/integration/api/test_stages.py`](../../tests/integration/api/test_stages.py) | The queue surface every stage shares, over HTTP |
| [`tests/integration/api/test_pipeline_routes.py`](../../tests/integration/api/test_pipeline_routes.py) | The corpus as one thing, over HTTP |
| [`tests/integration/api/test_catalogue.py`](../../tests/integration/api/test_catalogue.py) | Reading back what the stages produced, and the platform's routes |
| [`tests/integration/api/test_documents.py`](../../tests/integration/api/test_documents.py), [`test_facts.py`](../../tests/integration/api/test_facts.py), [`test_questions.py`](../../tests/integration/api/test_questions.py), [`test_topics.py`](../../tests/integration/api/test_topics.py), [`test_assessment.py`](../../tests/integration/api/test_assessment.py) | Each noun's routes against the database that answers them |
| [`tests/integration/api/test_lineage.py`](../../tests/integration/api/test_lineage.py) | How one artefact was produced, over HTTP |
| [`tests/integration/api/test_closed_sets.py`](../../tests/integration/api/test_closed_sets.py) | A value outside a closed set a route accepts, refused over HTTP |
| [`tests/integration/api/test_settings.py`](../../tests/integration/api/test_settings.py), [`test_settings_cli.py`](../../tests/integration/api/test_settings_cli.py) | Reading and changing what a service is configured to do, over HTTP and from a terminal |
| [`tests/static/test_api_stays_light.py`](../../tests/static/test_api_stays_light.py) | That this process loads no model, converter or inference library |
| [`tests/static/test_api_vocabularies.py`](../../tests/static/test_api_vocabularies.py) | The filters offered against the values the database holds |

`tests/contract/openapi.json` is a committed fixture: a route added without
updating it fails the contract test.

## Limits

- **A queue verb answering 202 has done nothing yet.** It moved rows between
  statuses; `/status` is the only thing that says whether a worker picked
  them up.
- **`POST /{stage}/{action}` accepts any of the five verbs as a path
  segment.** An unknown one is FastAPI's own 422, not an `ApiError`.
- **`rerun` skips what a worker holds right now.** It is not a way to
  interrupt a running conversion.
- **`rerun` on `/assessment` is refused 409 `assessment_cannot_run` while the
  phase is off or no judge is named.** It clears every stored verdict, and no
  worker would judge the rows again; the same check `make assess-rerun` makes.
- **`GET /topics/visualisation/{language}` 404s for a language no fit or
  render has drawn.** A fit draws the figure, and `make topics-render`
  redraws it from the stored model; the route itself never draws.
- **The API can be reached while no worker exists.** A stage added since the
  stack came up has no container until `make up` creates one.
