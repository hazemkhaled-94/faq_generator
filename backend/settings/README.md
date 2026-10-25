# Settings

Reading configuration: the environment, the overrides stored over it, what may
be configured, and what a change stales.

```
configs/env/*.env, .env   ──▶  the default, and required
        service_settings  ──▶  the override, if a row exists
```

A name is declared in **exactly one** of those files, so there is no
precedence between them to know — see
[docs/configuration.md](../../docs/configuration.md) for which file holds
what, and for the values that are derived rather than declared.

The files stay required. A variable missing from its file **stops the
service at start-up naming itself**, bar the few whose absence reads a value
of its own: a stage's own model, which falls back to `LLM_MODEL`; the two
pool sizes, which the engine falls back on; and `QUESTIONS_MEETS_SHARE`,
`QUESTIONS_KIND_MIX` and `QUESTIONS_CATEGORIZATIONS`, which read a default in
code.
`QUESTIONS_CATEGORIZATIONS` is only a comment in its file: its value is
JSON, and bash, which sources the files, cannot hold one.
[docs/configuration.md](../../docs/configuration.md#precedence) lists the
few. An override is a row in `service_settings`, and deleting that row
returns a setting to whatever the file says, or for those few to what their
absence reads.

`tests/static/test_settings_documented.py` moves that start-up failure to the
pull request.

## When a change takes effect

A watching worker picks a change up **once its queue is empty**. The check sits
between drains, where nothing is claimed, so a change made during a drain
waits for that drain to empty the queue and is never applied halfway through
an item. A one-off `make` drain reads the settings once, when it starts.

Nothing is requeued, and `make settings SERVICE=<name>` and `make doctor` say how
many stored rows of extraction, topics and questions were made before a
setting that stales that stage was changed, with the least destructive command
that brings them in line: the cheaper rebuild the catalogue names, and the
stage's rerun only where one of the changed settings names none. The change
must have gone through the store, which dates it. A file's change is dated by
nothing, and shows only as another version.
If the change means what a stage already produced was
made under the old value, whichever surface you used **says so and names the
stage**, and how to rebuild it: the cheaper command the catalogue names,
where every changed setting that stales something has one, and otherwise
that the stage be rerun — its `-rerun` target, or `make topics-discover` for
topics, which has none. Every fact, topic and question records the
configuration it was produced under.

That is what `invalidates` in the catalogue is for. It names the stages whose
stored output this setting produced — direct staleness only, since naming
`parsing` names the passages, facts and questions that cascade from it.

## The catalogue

[`catalog.py`](catalog.py) is the list of what may be configured: each
setting's service, its type, its bounds, the closed set of values where there
is one, one line of help, and what it stales.

One table rather than one per `config.py`, because the spaCy pipelines, the
worker poll and the pool sizes are read where they are used rather than by
one service.

Two directions are enforced by `tests/static/`:

| | |
|---|---|
| A setting the code reads and the catalogue does not describe | cannot be configured at all |
| A setting the catalogue describes and nothing reads | is a control that does nothing |

Neither is allowed to merge. That pair is why the Configuration panel on
every page holds no list of settings: adding one to `catalog.py` adds it to
the page.

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
never stored. They are the pool sizes, read before a service could ask a
database for anything; the addresses and host names (`LLM_BASE_URL`,
`OLLAMA_BASE_URL`, `SERVICE_URLS`, `API_ALLOWED_HOSTS`); the eight model
settings, `LLM_MODEL` and the ones a stage or a judgement names, which the
host and the containers each read from their own environment (compose gives
the containers their own `LLM_MODEL`, `QUESTIONS_VERIFIER_MODEL` and
`ASSESSMENT_JUDGE_MODEL`; the other five come from `backend.env` for both);
and the three spaCy pipeline settings and `WORKER_POLL_SECONDS`, of which
nothing reads a stored value. A row stored for a fixed or retired setting does
not apply and does not count toward the version.

## Stored rows are audited at every build

The catalogue moves under a stored row: a floor is raised, a choice dropped, a
name retired. Whenever a stage reads its settings (`store.snapshot(<stage>)`,
which every stage's build and command goes through, parsing and chunking
included, the upload route, which builds ingestion, the assessment enrolment
and `make confidence-recalibrate`; a route answers 503 `stored_setting_refused`
naming the row, and the recalibration exits 3) each row is checked against the catalogue as it stands. A row the
catalogue now refuses, or one stored under a name in `store.RETIRED`
(`TOPIC_MIN_WEIGHT`, which `TOPIC_RELATIVE_WEIGHT` replaces), stops the
build of a stage that reads it, a setting of that stage's or of the platform,
with the row, its value and when it was written, naming the replacement for a
retired name; every worker waits on it in place, as it does for any setting it
cannot build on, and a one-off command says so and exits 1. Another stage's
refused row is warned about and left for that stage. A row for a model id whose
commit is pinned (`EMBEDDING_MODEL`, `NLI_MODEL`, `QA_MODEL`) is refused the
same way: the id moves only with its `*_REVISION`, in the file. A row that overrides the file is one
warning naming the stored value, the file's and the date, once per name and
value in a process, where a worker reads its settings at every poll. A row for a name the
deployment now owns, or that nothing configures, is warned about and ignored: it
cannot be deleted with `make settings-unset`, so it must not stop a build.
`make doctor` reads through the same snapshot and fails on the same row, asks
every model with the stored values (and says which came from the store), and
falls back to the environment, saying so, where the store cannot be read.

## The three surfaces

All three go through the **same validation** — the stage's own
`Settings.load` — so what you are refused with is the message the worker
would have failed at start-up with. Every stage's, `assessment` included,
must still load after the change, and the catalogue's bounds and closed sets
are checked first: `LLM_STRUCTURED_MODE` takes only an instructor mode
litellm's client accepts. An empty value turns off an optional setting and is
refused for any other; a list of nothing but commas counts as empty.

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

A `null` value returns one setting to what the files say. **The whole request
is refused if any one value is**, so a PATCH never lands half applied. It is
written in one transaction that locks the table and checks the version the
page was drawn from, where it sent one, so a change made since is refused
with `version_moved`.

`GET /settings/{service}` answers, per setting: its value, what the files say
it would be, its type, its bounds, and whether somebody changed it.

## Precedence

Highest first:

1. A variable on a `make` command line — `make topics-discover TOPIC_PASSES=20`
2. A row in `service_settings`
3. The one file that declares it

There is no fourth rung, and that is the point: a name is in
`configs/env/backend.env` or `deployment.env` or `.env` or a tool's own
file, never in two, so "which file wins" is not a question a deployment has
to answer. `tests/static/test_env_files.py` keeps it that way.

The Makefile re-applies command-line overrides after sourcing the files,
because sourcing would otherwise overwrite them, and names them in
`QA_COMMAND_LINE`, so a stored row for one gives way too.

## A version is not a run

`settings_version` names a **configuration**: a digest of every catalogued
setting as resolved, bar the fixed platform settings no stage's output depends
on (`SPEND_CAP`, the poll interval, the pool sizes, the addresses and
`LLM_MODEL`), the files overlaid with the stored rows and a `make`
command line over both. It changes when any of them does. It answers "what
was this row produced under".

It cannot answer "which run produced it". Run a stage twice without touching
a setting and both sets of rows carry the same version.

So [`runs.py`](runs.py) names the run, and `facts`, `questions` and `topics`
each carry a `run_id` beside their `settings_version`:

```bash
make questions RUN_ID=b-gemma4-12b      # name it
make questions                          # or let it mint a uuid
make questions-runs                     # what there is
make questions-diff RUNS="a b"          # the two, gate by gate
```

Three things can name it, and the order is what matters:

| | |
|---|---|
| `RUN_ID` | Somebody named this run and means it. Always wins |
| The row's trigger | Whoever queued the row carried an id — a Dagster run, a Start button, a `make …-start` — and the worker adopts it for as long as it holds that row |
| A uuid | Nobody named it, and nobody asked by name. One per process |

The middle one is what joins a corpus to whatever set it going, and it is
the reason a run is no longer per **process**. A `--watch` worker is
long-lived and drains whatever arrives, so an id per process named the
container and not the work: a Dagster run, the Start button and
`make extract` all produced rows stamped with the same worker. `start`
writes its own id onto the rows it queues, `StageQueue._claim` reads it
back into a `ContextVar`, and `run_id` answers with it — so nothing had to
be threaded through the six services that write a row.

Unlike the version, it is not threaded through the factories. A version can
change while a process runs — that is what `reloading` in `stages/cli.py`
watches for — and a run cannot change under the row it belongs to.

## Configuration

This package configures nothing of its own. See
[docs/configuration.md](../../docs/configuration.md) for the files and the
settings most likely to need changing.

[`env.py`](env.py) holds the readers — `required`, `optional`, `integer`,
`decimal`, `boolean`, `csv`, `mapping` — and their names are what the static
tests scan for. A setting read through a variable rather than a literal is
invisible to that scan.

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

- **Changing a setting does not requeue anything.** It says what went stale
  and names the stage; the `-rerun` is yours to run.
- **A `fixed` setting is visible and unwritable.**
- **A PATCH is all-or-nothing.** One invalid value refuses the whole request.
- **A setting read through a variable is invisible to the static scan.** The
  pool sizes and `LOG_DIR` are read that way and checked by hand.
- **`make settings SERVICE=…` reads the same store the UI writes.**
