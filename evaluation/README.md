# Evaluation

The golden cases, and scoring a served model against them in Phoenix.
`make test-eval` prints a model's scores on the cases in
[`cases.py`](cases.py). This package records each run in Phoenix instead.

## Using it

```bash
make eval-upload                                 # the cases become a Phoenix dataset, named with this database
make eval-score                                  # score the model, and record it
make eval-score EVAL_RUN_NAME=extraction-prompt-v7
make eval-phrasing                               # the two phrasing judgements, against their floor
make prompts-publish                             # the recorded prompts
```

The targets wrap three mutually exclusive options, one required:

```bash
python -m evaluation.run --upload extraction-golden
python -m evaluation.run --score extraction-golden
python -m evaluation.run --publish-prompts
```

Results are at <http://localhost:6006>.

## Publishing the prompts

`make prompts-publish` records each prompt in Phoenix, so the version a span
names in `llm.prompt_template.version` opens beside the trace and the
playground can select it. A version carries the whole call:

| What Phoenix shows | Where it comes from |
|---|---|
| System message | `prompts.text`, composed by the stage that sends it |
| User message | `prompts.user_text`, with `{{name}}` where a call substitutes |
| Invocation parameters | `llm.config.Settings`: the temperature, and `reasoning_effort` where Phoenix knows it. The timeout, `num_ctx` and Ollama's `off` go in the description |
| Response format | `prompts.response_schema`, the JSON schema of the Pydantic shape |

Versions are published oldest first, because Phoenix keeps the last created as
current. The version and digest go in the version's description.

A stage publishes the prompts it newly records at start-up, through
[`backend/stages/publish.py`](../backend/stages/publish.py). The make target is
the full republish, for a Phoenix wiped while the database rows stayed. The
code is the source of truth: the next publish overwrites a UI edit.

## Comparing two runs

```bash
make questions-runs                              # which runs there are
make questions-diff RUNS="a-gpt-4.1 b-gemma4-12b"
```

The diff reads live and archived rows (`archived_rows`), so `questions-rerun`
does not destroy the other run. Runs are told apart by `questions.run_id`
([`settings/runs.py`](../backend/settings/runs.py)). A run named with
`RUN_ID` sends its spans to a Phoenix project `<position>-<stage>-<name>`,
which holds calls, tokens, latency and spend.

## Comparing scores

Phoenix versions the dataset, so a new case keeps earlier experiments valid.
Each run records the model and temperature as metadata, plus the
structured mode (extraction) and prompt version and floors (phrasing). Unset,
`EVAL_RUN_NAME` names the experiment after the model. Set it when the model is
the same and something else changed.

## Scoring

The pipeline's own checker scores the cases, not an LLM judge, because the
checker decides which facts are kept. The reader is built as in a worker:
`EXTRACTION_MODEL` where set, and the atomic cap
`EXTRACTION_MIN_OTHER_SHARE` works out to. Both are read from the environment
alone, so a value stored through the settings page or `make settings-set` does
not reach a score.

The `extraction` and `phrasing` sets are scored, asserting nothing. The
`questions` set is only uploaded, for browsing, because it already asserts and
gates a pull request.

`make eval-phrasing` records `names_its_source` and `self_contained`, a
`_floor` for each (the score of a judge giving the same answer every time),
and `answered`, the count judged, so an unreachable model does not read as a
wrong judge.

## Never a gate

Model answers move between runs, so a threshold would fail without a
regression. `tests/eval/` asserts only that each piece is wired up: the
round-trip gate splits golden questions correctly, each phrasing judgement
beats its floor on every case (German included), extraction keeps something,
and the writer writes for every kind.

## Layout

[`cases.py`](cases.py) holds the golden cases, read by this package and by
`tests/eval/`. [`experiments.py`](experiments.py) scores them into Phoenix,
[`config.py`](config.py) says where Phoenix is, and [`run.py`](run.py) is the
command line. Nothing here runs in an image; the backend image carries
`arize-phoenix-client` for [`telemetry/evaluations.py`](../telemetry/evaluations.py).

## Configuration

| Setting | Where | What it does |
| --- | --- | --- |
| `EVAL_RUN_NAME` | [`configs/env/evaluation.env`](../configs/env/evaluation.env) | What a run is called. Unset names it after the model |
| `PHOENIX_BASE_URL` | derived by the Makefile from `PHOENIX_PORT` in `configs/env/deployment.env` | Phoenix's HTTP API, as the host reaches it |
| `PHOENIX_ADMIN_SECRET` | `.env` | At least 32 characters, including a digit and a lower-case letter |
| `LLM_MODEL`, `LLM_BASE_URL` | `.env` | The model being scored, unless `EXTRACTION_MODEL` names extraction's own |

`PHOENIX_DEFAULT_ADMIN_INITIAL_PASSWORD` applies only when Phoenix first
creates its admin user.

## Tests

```sh
poetry run pytest tests/unit/evaluation   # no network
poetry run pytest tests/eval              # needs a served model
```

[`tests/unit/evaluation/`](../tests/unit/evaluation) covers the recorded scores
and the flags. [`tests/eval/`](../tests/eval) covers a served model's
extraction, writing and judging. It is excluded from `make test` and run
nightly, and skips unless `LLM_MODEL` is a repository variable.

## Limits

- Nothing here gates a merge.
- `--score` needs the set uploaded first.
- A static `EVAL_RUN_NAME` makes two models look like one experiment.
- Rows from before `run_id` existed carry NULL and cannot be told apart.
