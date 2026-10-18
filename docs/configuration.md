# Configuration

Settings come from files. A deployment can override one that
`settings/catalog.py` describes and does not mark fixed through the UI, the
API or `make settings-set` without restarting anything; a fixed one changes
in its file and takes a restart. The mechanics are in
[`backend/settings/`](../backend/settings/README.md); this is the map.

**This page names no defaults.** The files below hold the values, each one
exactly once, and a table here repeating them would be a copy free to
disagree with the file — which is what it was, and did: it described
`QUESTIONS_TYPE_MIX` as "eleven kinds" long after the file had thirteen.
What a setting *is* is here; what it is *set to* is in the file named
beside it.

## The files

| File | In git | Holds |
|---|---|---|
| `configs/env/backend.env` | yes | How the pipeline behaves: the parsing, chunking, extraction, topic, question and assessment settings |
| `configs/env/deployment.env` | yes | Where this deployment put things: the ports, the container-side addresses, the topology, the role names |
| `configs/env/elasticsearch.env` | yes | The node's certificate paths, security flags and heap |
| `configs/env/seaweedfs-filer.env` | yes | Which metadata store the filer uses |
| `configs/env/orchestration.env` | yes | How long Dagster waits on a stage |
| `configs/env/review.env` | yes | How a review sample is drawn |
| `configs/env/evaluation.env` | yes | What a golden-set run is called in Phoenix |
| `configs/env/provider.env` | **no** | Whatever env vars the model provider needs. `make setup` writes it from `configs/env/provider.env.example`, which is in git |
| `.env` | **no** | The credentials, and which model this deployment calls |

**A name appears in exactly one of them.** There is no file that overrides
another, and no name to look up in two places to find out which value wins.
`tests/static/test_env_files.py` refuses a second live assignment of a name
across them, reading `.env.example` in place of `.env`;
`configs/env/provider.env` is not in git, so it does not read that one.

compose hands each file to the services that need it with `env_file`, and
the Makefile sources `backend.env`, `deployment.env`, `provider.env` and
`.env` for the host commands — so one value reaches both.

`.env` holds the deployment's secrets and `provider.env` the provider's.
`.env.example` stands in for `.env` in git, every secret a `change_me_*`
placeholder beside the model names. `make setup` copies one to the other and
generates the passwords.

compose refuses to start while any password or key it passes is missing
from `.env` or empty, naming the one it lacks, rather than handing a service
a blank and letting it fall back to its image's default. `S3_ACCESS_KEY` and
`S3_SECRET_KEY` alone may be empty, which lets boto3 find an instance role or
a profile, but their lines have to be there.

## What compose reads

compose interpolates `${...}` out of **two** files, in this order:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env
```

The last one wins, which is what lets a secret sit over a name. Every
compose command in the Makefile goes through `$(COMPOSE_CMD)`, which carries
both flags; `COMPOSE` stays the engine alone, so
`make COMPOSE="docker compose" up` still carries the files rather than
replacing them. A bare `podman compose` outside make sees only `.env` and
fails on the first missing port; export `COMPOSE_ENV_FILES` to it instead:

```bash
export COMPOSE_ENV_FILES=configs/env/deployment.env,.env
```

It cannot be set inside `.env` — compose has to resolve the file list before
it reads one.

## What is derived, and so written nowhere

A port copied into an address is a copy free to disagree with it, and a
password copied into a connection string is a secret in two places. These
are built from the names above rather than declared:

| Value | Built from | By |
|---|---|---|
| `DATABASE_URL` | `APP_DB_USER`, `APP_DB_PASSWORD`, `APP_DB_NAME`, `POSTGRES_PORT` | the Makefile for a host command, compose for a container |
| `BACKEND_URL` | `BACKEND_PORT` | the Makefile. The container's is `BACKEND_CONTAINER_URL` |
| `S3_ENDPOINT` | `S3_PORT` | the Makefile. The container's is `S3_CONTAINER_ENDPOINT` |
| `PHOENIX_BASE_URL` | `PHOENIX_PORT` | the Makefile, and compose for the frontend's browser links. The container's is `PHOENIX_CONTAINER_BASE_URL` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `PHOENIX_GRPC_PORT` | the Makefile. The container's is `OTEL_CONTAINER_ENDPOINT` |
| `ARGILLA_API_URL` | `ARGILLA_PORT` | the Makefile |
| `SERVICE_URLS` | every published port | compose, for the System health page |
| `SPACY_MODELS` | `NLP_MODELS` | the Makefile, which exports it so the image bakes what the workers load |

### The host and the container see different addresses

Seven things have two names, and the convention is the same for all of them:
the plain name is the **host's**, and `*_CONTAINER_*` is what compose sets
over it inside the network.

| The host's | The container's |
|---|---|
| `BACKEND_URL` | `BACKEND_CONTAINER_URL` |
| `S3_ENDPOINT` | `S3_CONTAINER_ENDPOINT` |
| `PHOENIX_BASE_URL` | `PHOENIX_CONTAINER_BASE_URL` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `OTEL_CONTAINER_ENDPOINT` |
| `LLM_MODEL`, `LLM_BASE_URL`, `OLLAMA_BASE_URL` | `LLM_CONTAINER_MODEL`, and `OLLAMA_CONTAINER_URL` for both addresses |
| `QUESTIONS_VERIFIER_MODEL` | `QUESTIONS_VERIFIER_CONTAINER_MODEL` |
| `ASSESSMENT_JUDGE_MODEL` | `ASSESSMENT_JUDGE_CONTAINER_MODEL` |

The model pairs are the ones that do **not** fall back. `LLM_CONTAINER_MODEL`
is required, must name an Ollama model, is checked by `make doctor`,
and does not inherit `LLM_MODEL`. The verifier and the judge do not inherit
either: unset in the containers, the writer marks its own work and nothing is
judged. A container given a hosted model it has no credential for does not
restart: its worker waits in place, claims nothing, and logs that it cannot
reach its model, again every ten minutes, until the model answers.

## Precedence

Highest first:

1. A variable given on a `make` command line, for the host process that
   command runs. It never reaches a running container:
   `make extract-start EXTRACTION_DUPLICATE_COSINE=0.9` queues the passages,
   and `extract-worker` drains them under the stored or the file value.
2. A row in `service_settings` — set through the UI, the API or `make settings-set`
3. The file that declares it

The files stay required. A variable missing from its file stops the service
at start-up naming itself, bar a few: a setting whose absence means
something, such as a stage's own model; `LOG_LEVEL`, which falls back to
INFO; the two pool sizes, which fall back to 5; `QUESTIONS_MEETS_SHARE`,
which reads its shipped value when absent; and `QUESTIONS_CATEGORIZATIONS`,
which reads `DEFAULT_CATEGORIZATIONS` in
[`question_generation/config.py`](../backend/question_generation/config.py)
when absent, because its value is JSON and no file here can hold one (see
[A JSON value](#a-json-value)). Deleting an override row is what returns a
setting to the file, or for those few to what their absence reads.

## Changing one

Three surfaces, all going through the stage's own `Settings.load`:

```bash
# On the page that runs the service, under Configuration.

# Or the API, one service per request:
curl -s localhost:8000/settings/topics
curl -s -X PATCH localhost:8000/settings/topics \
  -H 'content-type: application/json' \
  -d '{"values": {"TOPIC_PASSES": "20"}}'

# Or a terminal:
make settings SERVICE=topics
make settings-set SERVICE=topics SET="TOPIC_PASSES=20"
make settings-unset SERVICE=topics UNSET="TOPIC_PASSES"
```

A worker picks a change up once its queue next runs dry: it reads its
settings again between drains, not per row. Nothing is requeued. If the
change stales what a stage already produced, the surface you used says so
and names the stage. Where every setting changed that stales something has a
cheaper rebuild in its catalogue entry, such as `make extract-revalidate` or
`make questions-balance`, the page and the API name that command; otherwise
they say to rerun the stage. `make settings-set` names the same command and
says to rerun the stage either way.

### A JSON value

`QUESTIONS_CATEGORIZATIONS` holds the DataMorgana paper's categorizations as
JSON: one categorization object as the paper's Figure 2 prints it, or a list
of them. Each answerable question is written as one category of each, and the
question records which. Its line in `configs/env/backend.env` is a comment,
because bash sources that file and would split a JSON value at its spaces and
strip its quotes. Unset, it reads `DEFAULT_CATEGORIZATIONS` in code; `[]`
turns categories off.

Set it on the Questions page's Configuration panel, through the API, or with
`settings.run` in the environment `make` loads, each of which stores the
value whole:

```bash
curl -s -X PATCH localhost:8000/settings/questions \
  -H 'content-type: application/json' \
  -d '{"values": {"QUESTIONS_CATEGORIZATIONS": "[]"}}'

PYTHONPATH=backend poetry run python -m settings.run --service questions \
  --set 'QUESTIONS_CATEGORIZATIONS=[]'
```

Not `make settings-set`: it splits `SET` at its spaces, so a JSON value
reaches the store in pieces. A value that is not JSON, misspells a key,
names a category twice, puts an `=` in a name or has probabilities that do
not sum to 1 is refused, naming the categorization at fault, before
anything is stored. `make settings-unset SERVICE=questions
UNSET=QUESTIONS_CATEGORIZATIONS` goes back to the default in code.

A stage's rerun is its `-rerun` target, bar topics, which have none:
`make topics-discover` fits them again and carries what a person decided
about a topic over to the new topic matching it. Rerunning extraction leaves
the bridges to `make extract-bridge`. Rerunning questions writes only about
the facts no accepted question rests on and judges no stored question again,
which `make questions-reverify` does for the gates that need no model.

A fixed setting is the exception: it changes only in its file, with a
restart, and no surface reports what the change left stale. After changing
`NLP_MODELS`, `NLP_DEFAULT_LANGUAGE` or `NLP_CAPITALISED_NOUNS`, rerun
chunking and every stage after it.

Every fact, topic and question records the configuration it was produced
under.

## The eight services

`ingestion` on Upload, `parsing` on Documents, `chunking` on Passages,
`extraction` on Facts, `topics` on Topics, `questions` on Questions,
`assessment` on Assessment, and `platform` — the model, the tokenizer and the
language pipelines — on System health. Each configures its own settings and
no others.

A stage may name a different model of its own: `EXTRACTION_MODEL`,
`TOPIC_MODEL`, `QUESTIONS_MODEL`, each meaning `LLM_MODEL` when absent. Four
more name a model for one judgement: `EXTRACTION_DIGEST_MODEL`,
`QUESTIONS_PHRASING_MODEL`, `QUESTIONS_VERIFIER_MODEL` and
`ASSESSMENT_JUDGE_MODEL`.

These eight model settings, `LLM_MODEL` among them, are fixed: the deployment
sets them, and they are served read-only and never stored. Three have a
container value of their own, which compose sets over the host's: `LLM_MODEL`,
`QUESTIONS_VERIFIER_MODEL` and `ASSESSMENT_JUDGE_MODEL`, in the table above.
The other five are read from `configs/env/backend.env`, so where one is set
the host and the containers call the same model for it, a hosted one included,
and `make doctor` checks none of them. The four language and poll settings
(`NLP_MODELS`, `NLP_DEFAULT_LANGUAGE`, `NLP_CAPITALISED_NOUNS`,
`WORKER_POLL_SECONDS`), the pool sizes, `API_ALLOWED_HOSTS` and the addresses,
`LLM_BASE_URL` among them, are fixed too. A settings write refuses every one
of them.

## Where to look for a setting

| Looking for | Read |
|---|---|
| Which model, and where it is served | `.env` for `LLM_MODEL`, the verifier, the judge, their container values and the addresses, and `.env.example` for the provider table; a stage's own model (`EXTRACTION_MODEL`, `EXTRACTION_DIGEST_MODEL`, `TOPIC_MODEL`, `QUESTIONS_MODEL`, `QUESTIONS_PHRASING_MODEL`) in `configs/env/backend.env`, beside that stage's settings, where the host and the containers both read it |
| How the model is called — mode, temperature, timeout, attempts, context window, reasoning | `configs/env/backend.env`, "Extraction" |
| The encoders, the tokenizer, the spaCy pipelines | `configs/env/backend.env`, "Embedding", "Encoders that run in this process" and "Language pipelines" |
| What a fact may be, and the caps on each kind | `configs/env/backend.env`, "Extraction" |
| How many topics, and how they are fitted | `configs/env/backend.env`, "Topic modelling", and [`backend/topic_modelling/`](../backend/topic_modelling/README.md) |
| What a run costs, and what it writes | `configs/env/backend.env`, "Question generation", and [`backend/question_generation/`](../backend/question_generation/README.md) |
| When two questions count as one | `configs/env/backend.env`, `QUESTIONS_DUPLICATE_COSINE` and `QUESTIONS_DUPLICATE_SHARED_COSINE` |
| What each question is written as: the paper's categories | `QUESTIONS_CATEGORIZATIONS`, stored rather than in a file; its default is `DEFAULT_CATEGORIZATIONS` in [`question_generation/config.py`](../backend/question_generation/config.py). See [A JSON value](#a-json-value) |
| Which of the accepted questions ship | `configs/env/backend.env`, "The balanced release" |
| Whether the judge runs, and who judges | `.env`; which artefacts and how many, `configs/env/backend.env` |
| A port, an address, a role name | `configs/env/deployment.env` |
| A password or a key | `.env`, listed in `.env.example`; the provider's in `configs/env/provider.env` |

Most settings in `configs/env/backend.env` carry the paragraphs explaining
what they do and how their value was arrived at;
[`settings/catalog.py`](../backend/settings/catalog.py) carries the one-line
version the UI draws its controls from. How a default was measured is in
[measurements.md](measurements.md).

## Five settings with constraints

`PHOENIX_ADMIN_SECRET` needs at least 32 characters including a digit and a
lower-case letter; `make doctor` checks all three. `PHOENIX_SECRET`, in
`.env`, needs at least 32 characters, as its placeholder says; `make setup`
generates one, and `make doctor` does not check its length.
`PHOENIX_DEFAULT_ADMIN_INITIAL_PASSWORD` is applied only when Phoenix first
creates its admin user; changing it afterwards means dropping the `phoenix`
database.

`GRAFANA_SECRET_KEY`, in `.env`, encrypts the secrets Grafana stores in its
database. compose refuses to start Grafana without it, and changing it is a
rotation: [operations.md](operations.md) has the steps.

`MAX_FILE_SIZE_MB` is the one setting written in two files, because
Streamlit reads a static TOML and no env var: `server.maxUploadSize` in
`frontend/.streamlit/config.toml` must match it, or the frontend rejects a
file before the API sees it and tells the person the wrong limit. A test
pins the pair as the two files hold them. The Configuration panel can still
change `MAX_FILE_SIZE_MB` without a restart, and nothing checks that value
against the TOML, so change it only together with `server.maxUploadSize`.

## What is enforced

| Test | Checks |
|---|---|
| `tests/static/test_env_files.py` | One name, one file. Every `${...}` compose interpolates is declared, and one with no fallback is actually set. Every password and key compose passes is required: `:?`, or `?` for the two S3 keys. `.env.example` holds a placeholder for every secret. The image bakes the pipelines `NLP_MODELS` loads |
| `tests/static/test_settings_documented.py` | Every setting the code reads by its literal name, through a settings reader or `os.environ[...]`, is named in a file that declares it, commented out or not. One read any other way, such as `TRACE_DATABASE`, `RUN_ID` or the pool sizes, is not seen |
| `tests/static/test_language_tables.py` | Every word table keyed by language holds a row for each language `NLP_MODELS` names |
| `tests/static/test_settings_catalogued.py` | Every setting the code in `backend/`, `frontend/` and `telemetry/` reads by its literal name is described in `settings/catalog.py`, bar the few the test lists as configured by no page, and every description is read. `orchestration/` is not scanned, so `INGESTION_OPEN` has no description and no panel |
| `tests/static/test_doc_links.py` | Every relative link in a README resolves |

Two settings a person may set are declared in no file, and neither test sees
them, because each is read through a constant: `TRACE_DATABASE`, which puts a
span on every SQL statement (see
[`telemetry/README.md`](../telemetry/README.md)), and `RUN_ID`, which names a
run (see the same page and
[`backend/settings/README.md`](../backend/settings/README.md)).