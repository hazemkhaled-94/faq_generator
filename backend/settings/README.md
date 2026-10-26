# Settings

Reads configuration from the environment and from overrides stored over it.
Defines what may be configured and what a change stales.

```
configs/env/*.env, .env   ──▶  the default, and required
        service_settings  ──▶  the override, if a row exists
```

A name is declared in exactly one of those files.
[docs/configuration.md](../../docs/configuration.md) lists which file holds
what.

The files stay required. A variable missing from its file stops the service at
start-up and names itself, except:

- a stage's own model, which falls back to `LLM_MODEL`;
- the two pool sizes, which the engine falls back on;
- `QUESTIONS_MEETS_SHARE`, `QUESTIONS_KIND_MIX` and
  `QUESTIONS_CATEGORIZATIONS`, which read a default in code.
  `QUESTIONS_CATEGORIZATIONS` is only a comment in its file, because its value
  is JSON and bash cannot hold one.

[docs/configuration.md](../../docs/configuration.md#precedence) lists the
exceptions. An override is a row in `service_settings`. Deleting the row
returns a setting to its file, or to what its absence reads.
`tests/static/test_settings_documented.py` fails the pull request when a
setting is missing.

## When a change takes effect

A watching worker picks a change up once its queue is empty, between drains. A
one-off `make` drain reads the settings once, when it starts.

Nothing is requeued. `make settings SERVICE=<name>` and `make doctor` say how
many stored rows of extraction, topics and questions predate a change to a
setting that stales that stage, and print the least destructive command that
fixes it: the cheaper rebuild the catalogue names, or a rerun of the stage
(its `-rerun` target, or `make topics-discover` for topics, which has none).
Every surface names the stale stage. A change made through the store is dated.
A change in a file is not, and shows only as another version. Every fact,
topic and question records the configuration it was produced under.

## The catalogue

[`catalog.py`](catalog.py) lists what may be configured: each setting's
service, type, bounds, closed set of values, one line of help, and what it
stales. `tests/static/` enforces both directions, and neither may merge:

| Case | Result |
|---|---|
| The code reads a setting the catalogue does not describe | It cannot be configured |
| The catalogue describes a setting nothing reads | It is a control that does nothing |

### The eight services

| Service | Configured on | Holds |
|---|---|---|
| `ingestion` | Upload | The size limit and the allowlist |
| `parsing` | Documents | The converter's thresholds and modes |
| `chunking` | Passages | How a passage is cut |
| `extraction` | Facts | What a fact may be, and the caps on each kind |
| `topics` | Topics | How many topics, how many passes, the vocabulary bounds |
| `questions` | Questions | The plan, the deal, the gates, the release |
| `assessment` | Assessment | Which artefacts the judge reads, and how many |
| `platform` | System health | The model, the tokenizer and the language pipelines |

Settings marked `fixed` are served read-only and never stored:

- the pool sizes;
- the addresses and host names (`LLM_BASE_URL`, `OLLAMA_BASE_URL`,
  `SERVICE_URLS`, `API_ALLOWED_HOSTS`);
- the eight model settings. The host and the containers read them from their
  own environment: compose gives the containers their own `LLM_MODEL`,
  `QUESTIONS_VERIFIER_MODEL` and `ASSESSMENT_JUDGE_MODEL`; the other five come
  from `backend.env` for both;
- the three spaCy pipeline settings and `WORKER_POLL_SECONDS`.

A row stored for a fixed or retired setting does not apply and does not count
toward the version.

## Stored rows are audited at every build

Whenever a stage reads its settings through `store.snapshot(<stage>)`, each
stored row is checked against the catalogue. Every stage's build and command
does this, as do the upload route, the assessment enrolment and `make
confidence-recalibrate`.

A row is refused when the catalogue now refuses it, when it is stored under a
name in `store.RETIRED` (`TOPIC_MIN_WEIGHT`, replaced by
`TOPIC_RELATIVE_WEIGHT`), or when it overrides a pinned model id
(`EMBEDDING_MODEL`, `NLI_MODEL`, `QA_MODEL`), which moves only with its
`*_REVISION` in the file.

| Case | Result |
|---|---|
| A refused row of the stage or the platform | The build stops, naming the row, its value, when it was written, and the replacement for a retired name |
| A worker meets it | It waits in place |
| A one-off command meets it | It exits 1 |
| A route meets it | It answers 503 `stored_setting_refused` |
| `make confidence-recalibrate` meets it | It exits 3 |
| A refused row of another stage | Warned about, left for that stage |
| A row that overrides the file | One warning per name and value in a process |
| A row for a name the deployment owns or nothing configures | Warned about and ignored, because `make settings-unset` cannot delete it |

`make doctor` reads the same snapshot and fails on the same row. If the store
cannot be read, it falls back to the environment and says so.

## The three surfaces

All three go through the stage's own `Settings.load`, so a refusal is the
message the worker would have failed at start-up with. The catalogue's bounds
and closed sets are checked first: `LLM_STRUCTURED_MODE` takes only an
instructor mode litellm's client accepts. An empty value turns off an optional
setting and is refused for any other.

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
refused if any one value is. It is written in one transaction. If the request
sends the version the page was drawn from, a change made since is refused with
`version_moved`.

`GET /settings/{service}` answers, per setting: its value, the file's value,
its type, its bounds, and whether it was changed.

## Precedence

Highest first:

1. A variable on a `make` command line, such as `make topics-discover
   TOPIC_PASSES=20`
2. A row in `service_settings`
3. The one file that declares it

The Makefile re-applies command-line overrides after sourcing the files, and
names them in `QA_COMMAND_LINE`, so a stored row for one gives way too.

## A version is not a run

`settings_version` names a configuration: a digest of every catalogued setting
as resolved (files, then stored rows, then a `make` command line). It leaves
out the fixed settings no stage's output depends on: `SPEND_CAP`, the poll
interval, the pool sizes, the addresses and `LLM_MODEL`. It says what a row
was produced under, not which run produced it.

[`runs.py`](runs.py) names the run. `facts`, `questions` and `topics` each
carry a `run_id` beside their `settings_version`:

```bash
make questions RUN_ID=b-gemma4-12b      # name it
make questions                          # or let it mint a uuid
make questions-runs                     # what there is
make questions-diff RUNS="a b"          # the two, gate by gate
```

The run is named by, in this order:

| Source | Meaning |
|---|---|
| `RUN_ID` | Somebody named this run. Always wins |
| The row's trigger | Whoever queued the row carried an id (a Dagster run, a Start button, a `make …-start`), and the worker adopts it while it holds that row |
| A uuid | Nobody named it. One per process |

`start` writes its id onto the rows it queues, `StageQueue._claim` reads it
into a `ContextVar`, and `run_id` answers with it.

## Configuration

This package configures nothing of its own. [`env.py`](env.py) holds the
readers `required`, `optional`, `integer`, `decimal`, `boolean`, `csv` and
`mapping`. A setting read through a variable rather than a literal is
invisible to the static scan. The pool sizes and `LOG_DIR` are read that way
and checked by hand.

## Tests

```sh
poetry run pytest tests/unit/settings tests/static/test_settings_catalogued.py
```

| File | Covers |
|---|---|
| [`test_env.py`](../../tests/unit/settings/test_env.py), [`test_source.py`](../../tests/unit/settings/test_source.py) | Reading configuration, and every refusal |
| [`test_configs.py`](../../tests/unit/settings/test_configs.py), [`test_changes.py`](../../tests/unit/settings/test_changes.py) | Each stage's settings, and what a change may name |
| [`test_runs.py`](../../tests/unit/settings/test_runs.py) | Which source names a row's run |
| [`test_settings_documented.py`](../../tests/static/test_settings_documented.py), [`test_settings_catalogued.py`](../../tests/static/test_settings_catalogued.py) | Every setting read is declared and described, and every description is read |
| [`test_service_settings.py`](../../tests/integration/database/test_service_settings.py), [`test_reloading.py`](../../tests/integration/database/test_reloading.py) | Stored overrides, and a worker picking up a change |
| [`test_settings.py`](../../tests/integration/api/test_settings.py), [`test_settings_cli.py`](../../tests/integration/api/test_settings_cli.py) | The same change over HTTP and from a terminal |

## Limits

- A change requeues nothing. The operator runs the `-rerun`.
- A `fixed` setting is visible and unwritable.
- A PATCH is all-or-nothing.
