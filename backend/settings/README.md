# Settings

Reads configuration from the environment and from overrides stored over it.
Defines what may be configured and what a change stales.

```
configs/env/*.env, .env   ──▶  the default, and required
        service_settings  ──▶  the override, if a row exists
```

A name is declared in exactly one of those files, so no precedence between
them applies. [docs/configuration.md](../../docs/configuration.md) lists which
file holds what, and which values are derived rather than declared.

The files stay required. A variable missing from its file stops the service at
start-up and names itself, except for the few whose absence reads a value of
its own:

- a stage's own model, which falls back to `LLM_MODEL`;
- the two pool sizes, which the engine falls back on;
- `QUESTIONS_MEETS_SHARE`, `QUESTIONS_KIND_MIX` and
  `QUESTIONS_CATEGORIZATIONS`, which read a default in code.

`QUESTIONS_CATEGORIZATIONS` is only a comment in its file, because its value
is JSON and bash, which sources the files, cannot hold one.
[docs/configuration.md](../../docs/configuration.md#precedence) lists the
exceptions. An override is a row in `service_settings`. Deleting the row
returns a setting to what the file says, or for these settings to what their
absence reads.

`tests/static/test_settings_documented.py` moves the start-up failure to the
pull request.

## When a change takes effect

A watching worker picks a change up once its queue is empty. The check sits
between drains, where nothing is claimed. A change made during a drain waits
for the drain to empty the queue and is never applied halfway through an item.
A one-off `make` drain reads the settings once, when it starts.

Nothing is requeued. `make settings SERVICE=<name>` and `make doctor` say how
many stored rows of extraction, topics and questions were made before a change
to a setting that stales that stage. They print the least destructive command
that brings the rows in line: the cheaper rebuild the catalogue names, or the
stage's rerun where none of the changed settings names one. The change must
have gone through the store, which dates it. A change in a file is dated by
nothing and shows only as another version.

Whichever surface made the change says when what a stage already produced was
made under the old value. It names the stage and how to rebuild it:

- the cheaper command the catalogue names, where every changed setting that
  stales something has one;
- otherwise a rerun of the stage: its `-rerun` target, or `make
  topics-discover` for topics, which has none.

Every fact, topic and question records the configuration it was produced
under.

`invalidates` in the catalogue names the stages whose stored output a setting
produced. It records direct staleness only: naming `parsing` covers the
passages, facts and questions that cascade from it.

## The catalogue

[`catalog.py`](catalog.py) lists what may be configured: each setting's
service, type, bounds, the closed set of values where there is one, one line
of help, and what it stales. It is one table rather than one per `config.py`,
because the spaCy pipelines, the worker poll and the pool sizes are read where
they are used rather than by one service.

`tests/static/` enforces two directions, and neither may merge:

| Case | Result |
|---|---|
| A setting the code reads and the catalogue does not describe | cannot be configured at all |
| A setting the catalogue describes and nothing reads | is a control that does nothing |

The Configuration panel on every page holds no list of settings. Adding a
setting to `catalog.py` adds it to the page.

### The eight services

| Service | Configured on | Holds |
|---|---|---|
| `ingestion` | Upload | The size limit and the allowlist |
| `parsing` | Documents | The converter's thresholds and modes |
| `chunking` | Passages | How a passage is cut |
| `extraction` | Facts | What a fact may be, and the caps on each kind |
| `topics` | Topics | The fit: how many topics, how many passes, the vocabulary bounds |
| `questions` | Questions | The plan, the deal, the gates, the release |
| `assessment` | Assessment | Which artefacts the judge reads, and how many |
| `platform` | System health | The model, the tokenizer and the language pipelines the rest share |

Some settings are marked `fixed`: served read-only as the deployment's, and
never stored. They are:

- the pool sizes, read before a service could ask a database for anything;
- the addresses and host names (`LLM_BASE_URL`, `OLLAMA_BASE_URL`,
  `SERVICE_URLS`, `API_ALLOWED_HOSTS`);
- the eight model settings, `LLM_MODEL` and the ones a stage or a judgement
  names. The host and the containers each read them from their own
  environment: compose gives the containers their own `LLM_MODEL`,
  `QUESTIONS_VERIFIER_MODEL` and `ASSESSMENT_JUDGE_MODEL`; the other five come
  from `backend.env` for both;
- the three spaCy pipeline settings and `WORKER_POLL_SECONDS`, of which
  nothing reads a stored value.

A row stored for a fixed or retired setting does not apply and does not count
toward the version.

## Stored rows are audited at every build

The catalogue can move under a stored row: a floor is raised, a choice
dropped, a name retired. Whenever a stage reads its settings, each row is
checked against the catalogue as it stands. Every stage's build and command
reads settings through `store.snapshot(<stage>)`, including parsing and
chunking, the upload route (which builds ingestion), the assessment enrolment
and `make confidence-recalibrate`.

A row is refused when the catalogue now refuses it, or when it is stored under
a name in `store.RETIRED` (`TOPIC_MIN_WEIGHT`, which `TOPIC_RELATIVE_WEIGHT`
replaces). A row for a model id whose commit is pinned (`EMBEDDING_MODEL`,
`NLI_MODEL`, `QA_MODEL`) is refused the same way, because the id moves only
with its `*_REVISION`, in the file.

| Case | Result |
|---|---|
| A refused row in a setting of the stage or of the platform | The stage's build stops, with the row, its value and when it was written. A retired name also names its replacement |
| A worker meets it | The worker waits in place, as for any setting it cannot build on |
| A one-off command meets it | The command says so and exits 1 |
| A route meets it | The route answers 503 `stored_setting_refused`, naming the row |
| `make confidence-recalibrate` meets it | Exits 3 |
| A refused row of another stage | Warned about and left for that stage |
| A row that overrides the file | One warning naming the stored value, the file's and the date, once per name and value in a process (a worker reads its settings at every poll) |
| A row for a name the deployment now owns, or that nothing configures | Warned about and ignored. `make settings-unset` cannot delete it, so it must not stop a build |

`make doctor` reads through the same snapshot and fails on the same row. It
asks every model with the stored values and says which came from the store.
Where the store cannot be read, it falls back to the environment and says so.

## The three surfaces

All three go through the same validation, the stage's own `Settings.load`, so
a refusal is the message the worker would have failed at start-up with. Every
stage's settings, `assessment` included, must still load after the change. The
catalogue's bounds and closed sets are checked first: `LLM_STRUCTURED_MODE`
takes only an instructor mode that litellm's client accepts. An empty value
turns off an optional setting and is refused for any other. A list of nothing
but commas counts as empty.

```bash
# The page that runs the service, under Configuration.

# The API, one service per request, with API_TOKEN from .env:
curl -s -H "X-API-Token: $API_TOKEN" localhost:8000/settings/topics
curl -s -X PATCH localhost:8000/settings/topics \
  -H "X-API-Token: $API_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"values": {"TOPIC_PASSES": "20"}}'

# A terminal:
make settings SERVICE=topics
make settings-set SERVICE=topics SET="TOPIC_PASSES=20"
make settings-unset SERVICE=topics UNSET="TOPIC_PASSES"
```

A `null` value returns one setting to what the files say. The whole request is
refused if any one value is, so a PATCH never lands half applied. It is
written in one transaction that locks the table. Where the request sends the
version the page was drawn from, the transaction checks it, and a change made
since is refused with `version_moved`.

`GET /settings/{service}` answers, per setting: its value, what the files say
it would be, its type, its bounds, and whether somebody changed it.

## Precedence

Highest first:

1. A variable on a `make` command line, such as `make topics-discover
   TOPIC_PASSES=20`
2. A row in `service_settings`
3. The one file that declares it

No fourth level exists. A name is in `configs/env/backend.env` or
`deployment.env` or `.env` or a tool's own file, never in two.
`tests/static/test_env_files.py` keeps it that way.

The Makefile re-applies command-line overrides after sourcing the files,
because sourcing would otherwise overwrite them. It names them in
`QA_COMMAND_LINE`, so a stored row for one gives way too.

## A version is not a run

`settings_version` names a configuration: a digest of every catalogued setting
as resolved, with the files overlaid by the stored rows and a `make` command
line over both. It changes when any of them does. The digest leaves out the
fixed platform settings that no stage's output depends on: `SPEND_CAP`, the
poll interval, the pool sizes, the addresses and `LLM_MODEL`. The version
answers "what was this row produced under". It cannot answer "which run
produced it": a stage run twice with no setting touched writes two sets of
rows with the same version.

[`runs.py`](runs.py) names the run. `facts`, `questions` and `topics` each
carry a `run_id` beside their `settings_version`:

```bash
make questions RUN_ID=b-gemma4-12b      # name it
make questions                          # or let it mint a uuid
make questions-runs                     # what there is
make questions-diff RUNS="a b"          # the two, gate by gate
```

Three things can name the run, in this order:

| Source | Meaning |
|---|---|
| `RUN_ID` | Somebody named this run. Always wins |
| The row's trigger | Whoever queued the row carried an id (a Dagster run, a Start button, a `make …-start`), and the worker adopts it for as long as it holds that row |
| A uuid | Nobody named it. One per process |

The row's trigger joins a corpus to whatever set it going. A `--watch` worker
is long-lived and drains whatever arrives, so an id per process would name the
container and not the work. `start` writes its own id onto the rows it queues,
`StageQueue._claim` reads it back into a `ContextVar`, and `run_id` answers
with it. No change reaches the six services that write a row.

The run id is not threaded through the factories. A version can change while a
process runs, which `reloading` in `stages/cli.py` watches for. A run cannot
change under the row it belongs to.

## Configuration

This package configures nothing of its own.
[docs/configuration.md](../../docs/configuration.md) lists the files and the
settings most likely to need changing.

[`env.py`](env.py) holds the readers `required`, `optional`, `integer`,
`decimal`, `boolean`, `csv` and `mapping`. The static tests scan for their
names, so a setting read through a variable rather than a literal is invisible
to the scan.

## Tests

```sh
poetry run pytest tests/unit/settings tests/static/test_settings_catalogued.py
```

| File | Covers |
|---|---|
| [`test_env.py`](../../tests/unit/settings/test_env.py) | Reading configuration out of the environment, and every refusal |
| [`test_source.py`](../../tests/unit/settings/test_source.py) | Reading a setting from somewhere other than the process environment |
| [`test_configs.py`](../../tests/unit/settings/test_configs.py) | Each stage's settings, read out of the environment |
| [`test_changes.py`](../../tests/unit/settings/test_changes.py) | Which settings a change may name, and what it refuses |
| [`test_runs.py`](../../tests/unit/settings/test_runs.py) | Which of three things names the run a row belongs to |
| [`test_settings_documented.py`](../../tests/static/test_settings_documented.py) | Every setting the code reads is named in a file that declares it |
| [`test_settings_catalogued.py`](../../tests/static/test_settings_catalogued.py) | Every setting the code reads is described, and every description is read |
| [`test_service_settings.py`](../../tests/integration/database/test_service_settings.py) | The settings a deployment changed, and what a stage then reads |
| [`test_reloading.py`](../../tests/integration/database/test_reloading.py) | A worker picks up a changed setting without being restarted |
| [`test_settings.py`](../../tests/integration/api/test_settings.py), [`test_settings_cli.py`](../../tests/integration/api/test_settings_cli.py) | The same change, over HTTP and from a terminal |

## Limits

- Changing a setting does not requeue anything. The change says what went
  stale and names the stage. The operator runs the `-rerun`.
- A `fixed` setting is visible and unwritable.
- A PATCH is all-or-nothing. One invalid value refuses the whole request.
- A setting read through a variable is invisible to the static scan. The pool
  sizes and `LOG_DIR` are read that way and checked by hand.
- `make settings SERVICE=…` reads the same store the UI writes.
