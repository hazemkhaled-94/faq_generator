# Tests

Twelve layers and nine markers. `make test` runs every layer that gates a
merge except `smoke`, which CI runs as its own job. `eval` and `perf` never
gate.

```bash
make test           # everything that gates but smoke; starts its own containers
make test-fast      # no spaCy, no pyright, no containers
make test-unit      # all but integration, smoke, eval and perf
make test-integration
make test-e2e
make test-smoke     # build both images and look inside them
make test-eval      # score the served model on the golden passages
make test-perf      # time the ceilings named in the code
make test-coverage  # the gating layers, with a coverage report
make mutation       # change a gate and see whether a test notices. Hours
```

## The layers

| Directory | What it covers | Needs |
|---|---|---|
| [`static/`](static/) | The repository against itself: settings, migrations, locks, workflows, env files, compose, Makefile recipes, dashboards, prompt digests, import contracts, documentation links and pyright at zero | nothing |
| [`unit/`](unit/) | One module at a time, with no network or disk. Includes the Dagster code location | spaCy, for some |
| [`property/`](property/) | Invariants over generated input, with hypothesis | spaCy, for some |
| [`regression/`](regression/) | The verdicts the checks have always reached | spaCy |
| [`contract/`](contract/) | The OpenAPI surface, declared refusals, and calls generated from the OpenAPI document against every read route (`unsupported_method` is off, because `POST /questions/{action}` is a real route) | a container |
| [`integration/`](integration/) | The database, the object store and the HTTP surface | a container |
| [`e2e/`](e2e/) | One document through every stage in this process, then the bridge pass, release draw, assessment and workbook export, with models and converters stood in | a container |
| [`golden/`](golden/) | Real PDFs through the real converter and chunker, against stored snapshots (CC BY 4.0, see `pdfs/ATTRIBUTION.txt`). `make test-golden` runs it; `make golden-refresh` updates the snapshots | the cached Docling and tokenizer weights |
| [`frontend/`](frontend/) | Each Streamlit page, against a scripted backend | nothing |
| [`smoke/`](smoke/) | Both images built and inspected, and the compose file resolved | a container engine |
| [`eval/`](eval/) | A real served model reading the golden passages, judging phrasing and writing questions | a served model |
| [`perf/`](perf/) | The ceilings named in the code, as budgets of five times the measured mean | nothing |

## The markers

`--strict-markers` is on: a misspelled marker is an error.

| Marker | Means |
|---|---|
| `nlp` | Loads a spaCy pipeline or a sentence-transformer |
| `types` | Shells out to pyright |
| `integration` | Needs a container runtime |
| `frontend` | Runs a Streamlit view |
| `e2e` | Drives the whole pipeline in this process |
| `smoke` | Builds images and reads the compose file |
| `slow` | Converts real PDFs with Docling. `make test` leaves it out, `make test-golden` runs it |
| `eval` | Scores a real served model. Never gates |
| `perf` | Times the named ceilings. Never gates |

## A prompt is pinned, not just versioned

[`static/test_prompts_pinned.py`](static/test_prompts_pinned.py) pins the
digest of every stage prompt under its module's `PROMPT_VERSION`. After
changing a prompt, bump the version and write down the new digest.

## Import and dependency checks

`make lint-imports` runs import-linter over [`.importlinter`](../.importlinter):
a stage sits above what it shares, and no backend service imports another.
`make deps` runs deptry: an unused declared dependency, an undeclared import,
or a package reached only through another. `make test` runs import-linter;
CI runs `make deps` in the `static` job.

## What never gates

`tests/eval/` prints its numbers and asserts little, because a model's
answers vary between runs. It asserts only that each piece works: the
round-trip gate splits the golden questions, each phrasing judgement beats a
judge that always answers the same, and extraction and the writer produce
something.

`tests/perf/` runs nightly and by hand, not on pull requests: a wall-clock
budget on a shared runner measures the runner.

## Tests that skip rather than download 2.2 GB

[`unit/nlp/test_embedding.py`](unit/nlp/test_embedding.py) skips unless
`EMBEDDING_MODEL` is cached. A skip on a missing weight goes through
[`weights.unavailable`](weights.py), which fails instead when
`REQUIRE_MODELS=1`, as the nightly `weights` job sets.

## How the tests are written

[`conftest.py`](conftest.py) sets the environment, and
[`factories.py`](factories.py) and [`integration/seed.py`](integration/seed.py)
build rows. [`frontend/pages.py`](frontend/pages.py) is one page object over
every view. [`static/test_pages_are_the_only_way_in.py`](static/test_pages_are_the_only_way_in.py)
refuses a frontend test that reads `view.app.<widget>` past it, and
[`static/test_fake_backend_matches_the_api.py`](static/test_fake_backend_matches_the_api.py)
compares its fake responses with the API's dataclasses.

## Continuous integration

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs on every pull
request and push to `main`:

| Job | Runs |
|---|---|
| `setup` | Installs the dependencies |
| `static` | The `static/` layer, `make lint`, `make lint-imports` and `make deps` |
| `unit` | Everything that needs no container or served model |
| `integration` | The container layers, against pulled images |
| `smoke` | Builds and inspects both images |
| `coverage` | Combines the other jobs' coverage |
| `gate` | Waits for the rest. Require this job in branch protection |

[`.github/workflows/nightly.yml`](../.github/workflows/nightly.yml) runs at
03:00:

| Job | Runs |
|---|---|
| `audit` | Known advisories in both locks |
| `everything` | Every layer but `eval` and `perf` |
| `mutation` | `make mutation`, with survivors in the summary |
| `ceilings` | `make test-perf` |
| `weights` | Fetches the embedding, NLI and Docling weights, then runs the tests that need them with `REQUIRE_MODELS=1` |
| `evaluate` | The model evaluation. Skips unless `LLM_MODEL` is a repository variable |

## Limits

- The integration layers start their own PostgreSQL and SeaweedFS through
  testcontainers and never touch a running stack. With no container engine
  the whole layer skips, with a reason. A skip is not a pass.
- `filterwarnings = error`, with five ignores in
  [`pyproject.toml`](../pyproject.toml), each for one third-party module.
- `tests/contract/openapi.json` is a committed fixture: a new route fails the
  contract test until it is updated.
- The coverage figures in [docs/measurements.md](../docs/measurements.md) are
  a snapshot: `make test-coverage` re-measures.
