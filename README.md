# FAQ Generator

Builds a verified question-and-answer dataset from a corpus of documents, so
a retrieval-augmented chatbot can be measured against a fixed benchmark
instead of against an opinion.

Documents are parsed into passages, read into atomic facts that each cite one
sentence of their source, grouped into topics, and turned into questions with
known answers. Every question carries the facts it was written from, and every
fact carries the sentence it came from, so any answer in the set can be traced
back to a page. A deliberate share of the questions written have no answer
in the corpus at all, which is what measures whether a chatbot recognises the
limits of its knowledge. As shipped, the release holds none of them:
`QUESTIONS_RELEASE_UNANSWERABLE` is 0 until the verifier's `settles`
judgement that keeps them can be trusted, so they stay in the accepted pool,
where `make questions-export FILTER="--status accepted --unanswerable"`
exports them and `FILTER="--released"` does not.

The pipeline is subject-agnostic: no prompt names a domain, and topics are
discovered from the corpus's own vocabulary rather than supplied. German and
English ship configured in `NLP_MODELS`; adding a third language is a short
list of edits in [`backend/nlp/`](backend/nlp/README.md).

Everything but a hosted model runs on infrastructure you control. **No
document content leaves the deployment**, except to whichever model provider
you configure — and with a locally served model, not even that. The
architecture supports local serving through Ollama; the measured run in
[docs/measurements.md](docs/measurements.md) used hosted models.

## What you get

An Excel workbook of four sheets, plus the same rows through the API and the
database:

| Sheet | One row per |
|---|---|
| Questions | Question, with its answer, difficulty, type, and what it rests on |
| Citations | Question × fact × passage, with the page number and the evidence |
| Assessment | Judgement of a question by an independent model |
| Summary | The counts for what the filter selected |

See [docs/measurements.md](docs/measurements.md) for what one run produced.

## Prerequisites

| | | |
|---|---|---|
| [Python](https://www.python.org/downloads/) | 3.12 or 3.13 | 3.14 is not supported: gensim does not build there |
| [Poetry](https://python-poetry.org/docs/#installation) | 2.0 or later | Dependency management |
| [Podman](https://podman.io/docs/installation) or [Docker](https://docs.docker.com/get-started/get-docker/) | with Compose | 23 containers |
| [Ollama](https://ollama.com/download) | any recent | **Required.** See below |
| Disk | ~15 GB | Images, model weights and volumes |
| RAM | 16 GB | 6 GB of it for the question worker. Podman's machine has a size of its own: see [Memory](docs/operations.md#memory) |

**Ollama is not optional.** `LLM_CONTAINER_MODEL` has to name a model Ollama
serves: compose refuses to start without it, `make doctor` refuses one that
is not an Ollama model, and a container never inherits the host's
`LLM_MODEL`. The host may call a hosted provider as well. Pull at least one
model before the first run:

```bash
ollama pull gemma4:31b
```

Pick a tag whose quantisation matches the runner serving it — an `-mlx` build
with nvfp4 weights will not load under Ollama's MLX runner.

## Install

```bash
git clone https://github.com/hazemkhaled-94/qa_generator.git && cd qa_generator
make setup      # writes .env and configs/env/provider.env, fills every placeholder
```

`setup` is safe to run twice: it replaces `change_me_*` placeholders and
nothing else.

Then name the model. `LLM_MODEL` in `.env` is a
[LiteLLM](https://docs.litellm.ai/docs/providers) identifier whose prefix
picks the provider:

```ini
LLM_MODEL=ollama_chat/gemma4:31b       # local, no credentials
LLM_MODEL=openai/gpt-4o                # OPENAI_API_KEY in provider.env
LLM_MODEL=anthropic/claude-sonnet-4-5  # ANTHROPIC_API_KEY
LLM_MODEL=azure/<deployment>           # a key, or Entra ID
```

`LLM_CONTAINER_MODEL` is what the containers call and compose refuses to start
without it. Set both to the same value if one model serves both.

Three judgements ship on a smaller model of their own, named in
`configs/env/backend.env`: `EXTRACTION_DIGEST_MODEL`, `TOPIC_MODEL` and
`QUESTIONS_PHRASING_MODEL` are `ollama_chat/muse-glimmer:30b-mlx`. Pull it
too, or point those three lines at a model you have. Blank, the digest
follows the passage reader, the topic names follow `LLM_MODEL`, and the
phrasing judge follows the verifier. The other three roles,
`EXTRACTION_MODEL`, `QUESTIONS_MODEL` and `QUESTIONS_VERIFIER_MODEL`, ship
unset and follow `LLM_MODEL`.

```bash
make install    # dependencies, the spaCy pipelines NLP_MODELS names, and Docling's weights
make doctor     # checks the tools and the config, then asks each model one question
```

`install` needs the container engine running. The parse worker has no
internet access, so `install` downloads Docling's weights into the `models`
volume from a container that has. After `make down-volumes`, run
`make docling-weights` again before parsing.

`doctor` ends with a real call to every model a stage calls, `LLM_MODEL` and
each of the six roles above, so a wrong model id, an unreachable address or a
stale credential fails there rather than on the first passage of a run.

## Run

```bash
make dev
```

Generates TLS certificates, starts every service, waits for PostgreSQL and
creates the schema. The frontend is then at <http://localhost:8501> and the
API documentation at <http://localhost:8000/docs>.

```bash
make services   # which containers are up, and where to open them
make help       # every target, grouped
```

### Choosing a setup

Four choices, independent of each other.

**Container engine.** Podman is the default; the Makefile calls
`podman compose`.

```bash
make CONTAINER=docker COMPOSE="docker compose" dev    # Docker instead
```

**Model provider.** Ollama alone is the simplest and needs no credentials.
A hosted provider is faster per call. The containerised workers call Ollama
for `LLM_CONTAINER_MODEL`; `ASSESSMENT_JUDGE_CONTAINER_MODEL` may point the
judge at a hosted one. Credentials go in `configs/env/provider.env`, which
compose gives to the four workers that call a model.

**Where the stages run.** The workers in their containers, or `make extract`
and friends on the host, never both for one stage: a host drain refuses while
that stage's worker is running, and prints the command that stops it. The
container workers build the dataset. A host drain is for developing a stage,
and nothing keeps its rows out of the dataset: it writes the same tables in
the same database as the workers, nothing but a `RUN_ID`, where one is set,
tells its rows apart, and the refusal checks only that the stage's worker is
stopped. Do not build the dataset with one.

**How the pipeline is driven.**

| | Start it with | Suits |
|---|---|---|
| Browser | **Run the pipeline** on the Documents page | Trying it out — the easiest |
| Terminal | `make all`, or `make pipeline` on a stack already up | A scripted or reproducible run |
| HTTP | `POST /pipeline/run` | A deployment nobody drives interactively |
| Unattended | `make auto` | An upload starting a run by itself |

`make corpus` and the bare stage targets drain on the host instead, for
developing a stage.

**The easiest path is `make setup` → `make install` → `make doctor` →
`make dev`, with Ollama for the model, Podman for the engine, and the
browser for the pipeline.** Nothing runs until asked; every stage is
incremental and skips what is already done.

## An example, end to end

Upload a PDF on the Upload page, then take it through:

```bash
make all                                 # every stage but the topic fit, in the workers
# once that run ends: Fit all on the Topics page, or POST /topics/discover
make pipeline                            # now with questions about those topics
make questions-balance                   # once that run ends: draw an evenly composed release
make questions-export OUT=exam.xlsx FILTER="--released"
```

`all` brings the stack up and launches Dagster's corpus job, which starts the
stages in order and waits for each to drain before starting the next; the
container workers do the draining. It never fits the topics: a fit replaces
the topics of every language it fits, so it is asked for on its own, and
`make topics-status` says how many passages are in no topic.

`make corpus` runs the same stages on the host, for developing a stage. It
stops at the first stage whose worker is running and prints the command that
stops it. Stage by stage, which is what it runs, plus the topic fit it never
asks for:

```bash
make parse-start     && make parse       # a stored file becomes a structured document
make chunk-start     && make chunk       # that document becomes passages
make extract-start   && make extract     # those passages become facts citing a sentence
make topics-status                       # how many passages are in no topic
make topics-discover                     # not in corpus: fit the topics, replacing the last fit
make extract-bridge MISSING=1            # facts joining a topic's passages, for topics holding none yet
make questions-start && make questions   # each topic's facts become questions
make questions-balance                   # draw the release again
make assess-start    && make assess      # the judge, when ASSESSMENT_ENABLED is true
```

Watch it with `make pipeline-status`, the Documents page, or Grafana's
pipeline dashboard.

The result is `exam.xlsx` — the four sheets above — and the same rows in
PostgreSQL behind `GET /questions`. A single row reads on its own:

| Column | Example |
|---|---|
| `question_text` | *Under what conditions may a test be re-run?* |
| `target_answer` | The key a chatbot is scored against |
| `answer_explanation` | The same answer at length, for a marker |
| `answerable` | `false` on the questions with no answer in the corpus |
| `difficulty` | `easy`, `medium` or `hard`, derived from how far the answer is spread |
| `question_type` | One of thirteen forms, never a subject |
| Citations | The facts it cites, their evidence, and the page each sits on |

Turning the evaluation phase on adds an independent model's opinion beside
each verdict — it decides nothing, and the pairs where the two disagree are a
queue for a person:

```ini
ASSESSMENT_ENABLED=true                           # .env
ASSESSMENT_JUDGE_CONTAINER_MODEL=azure/gpt-4.1    # who judges in assess-worker; not LLM_MODEL
```

```bash
make up                                  # assess-worker reads them
make assess-enrol                        # enrol and count, before paying; not a dry run
make assess-start                        # assess-worker judges what this queues
```

## Documentation

The [**project wiki**](https://github.com/hazemkhaled-94/qa_generator/wiki) is
the long form of everything below, on one site and cross-linked. In this
repository, each service documents itself beside its code.

**The pipeline, in the order a document moves:**

| | |
|---|---|
| [`backend/ingestion/`](backend/ingestion/README.md) | Upload validation, hashing and storage |
| [`backend/preprocessing/parsing/`](backend/preprocessing/parsing/README.md) | A stored file becomes a structured document |
| [`backend/preprocessing/chunking/`](backend/preprocessing/chunking/README.md) | That document becomes passages |
| [`backend/extraction/`](backend/extraction/README.md) | Those passages become facts citing a sentence |
| [`backend/topic_modelling/`](backend/topic_modelling/README.md) | Each language becomes topics over its own vocabulary |
| [`backend/question_generation/`](backend/question_generation/README.md) | Each topic's facts become questions with known answers |
| [`backend/assessment/`](backend/assessment/README.md) | An independent model reads it all back, and decides nothing |

**The surfaces:**

| | |
|---|---|
| [`backend/api/`](backend/api/README.md) | The HTTP surface |
| [`backend/stages/`](backend/stages/README.md) | The queue, the worker and the command line every stage shares |
| [`frontend/`](frontend/README.md) | The Streamlit application |
| [`docs/make.md`](docs/make.md) | Every `make` target |

**What they stand on:**

| | |
|---|---|
| [`backend/database/`](backend/database/README.md) | The schema, the migrations and the triggers |
| [`backend/blob_store/`](backend/blob_store/README.md) | The five buckets |
| [`backend/archive/`](backend/archive/README.md) | What a deletion leaves behind |
| [`backend/nlp/`](backend/nlp/README.md) | Sentences, claims, vocabulary and language |
| [`backend/llm/`](backend/llm/README.md) | The served model |
| [`backend/settings/`](backend/settings/README.md) | Configuration, and what a change stales |
| [`telemetry/`](telemetry/README.md) | Logging and tracing |

**Around the edges:**

| | |
|---|---|
| [`orchestration/`](orchestration/README.md) | Dagster: one asset per stage |
| [`review/`](review/README.md) | Argilla: where a person overrules a model |
| [`evaluation/`](evaluation/README.md) | Phoenix: scoring a served model against the golden cases |
| [`tests/`](tests/README.md) | The layers, and what each needs |
| [`configs/`](configs/README.md) | Service configuration and init scripts |
| [`docs/architecture.md`](docs/architecture.md) | The four graphs |
| [`docs/configuration.md`](docs/configuration.md) | Where every setting lives |
| [`docs/operations.md`](docs/operations.md) | Scaling, dashboards, and what goes wrong |
| [`docs/measurements.md`](docs/measurements.md) | What one run produced |
| [`docs/bugs.md`](docs/bugs.md) | What is wrong with what it produced, and the fix |

## How it is put together

No backend service imports another. Each owns a repository over the shared
models; `database/`, `blob_store/` and `llm/` build the connections, and
`nlp/` loads the language models, beside the two a stage loads itself:
parsing's Docling converter and chunking's tokenizer. Stages hand work to
each other through their own status column and share only what is in
`backend/stages/`.

A service package re-exports nothing, so a caller naming
`extraction.repository` pays for that submodule and no more — which is what
keeps LiteLLM, Docling, gensim and spaCy out of the API process.

They are independent modules, not independent services: one PostgreSQL schema,
one `Status` enum, one container image. The rules are enforced by
`make lint-imports`.

## Limitations

- **Scanned documents are refused rather than parsed.** OCR is not enabled.
- **Figures become no passage of their own**, and key-value form regions are
  not modelled.
- **`EMBEDDING_MODEL` cannot be changed without a migration.**
  `questions.embedding` is `vector(1024)`.
- **The model is the bottleneck, not the pipeline.** Question generation takes
  most of the wall clock and the spend ([measurements](docs/measurements.md)),
  and a locally served model is one to two orders slower per call than a hosted
  one.

## Licence

[Apache 2.0](LICENSE).
