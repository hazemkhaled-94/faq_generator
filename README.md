# FAQ Generator

FAQ Generator builds a question-and-answer dataset from a set of documents.
The dataset is a fixed benchmark for testing a retrieval-augmented chatbot.

The pipeline parses each document into passages, extracts facts that each
cite one source sentence, groups the passages into topics, and writes
questions with known answers. Every answer traces back to its facts, their
sentences and the page they sit on.

Some released questions have no answer in the corpus. They test whether a
chatbot declines to answer. `QUESTIONS_RELEASE_UNANSWERABLE` is 0.10, so up
to a tenth of the release is unanswerable. About a third of the questions
kept as unanswerable are in fact answered by the corpus, a known defect
listed in [docs/bugs.md](docs/bugs.md).

No prompt names a subject, and topics come from the corpus vocabulary.
German and English are configured in `NLP_MODELS`; [backend/nlp](backend/nlp/README.md)
lists the edits for another language. Every service runs on the operator's
own machines. Document text leaves only to the configured model provider.

## Output

An Excel workbook with four sheets. The API (`GET /questions`) and the
PostgreSQL database hold the same rows.

| Sheet | One row per |
|---|---|
| Questions | Question, with its answer, difficulty, type and sources |
| Citations | Question, fact and passage, with the page number and the evidence |
| Assessment | Judgement of a question by an independent model |
| Summary | Counts for the rows the filter selected |

The main columns of the Questions sheet:

| Column | Content |
|---|---|
| `question_text` | The question |
| `target_answer` | The answer a chatbot is scored against |
| `answer_explanation` | The same answer in full, for a human marker |
| `answerable` | `false` for questions the corpus does not answer |
| `difficulty` | `easy`, `medium` or `hard`, from how widely the answer is spread |
| `question_type` | One of thirteen question forms |

[docs/measurements.md](docs/measurements.md) shows what a full run produced.

## Requirements

| Tool | Version | Notes |
|---|---|---|
| [Python](https://www.python.org/downloads/) | 3.12 or 3.13 | 3.14 is not supported: gensim does not build there |
| [Poetry](https://python-poetry.org/docs/#installation) | 2.0 or later | |
| [Podman](https://podman.io/docs/installation) or [Docker](https://docs.docker.com/get-started/get-docker/) | with Compose | Runs 23 containers |
| [Ollama](https://ollama.com/download) | any recent | Development profile only |
| Disk | 15 GB | Images, model weights and volumes |
| RAM | 16 GB | 6 GB for the question worker. The Podman machine needs its own size: see [Memory](docs/operations.md#memory) |

## Installation

Clone outside any cloud-synced folder.

```bash
git clone https://github.com/hazemkhaled-94/qa_generator.git
cd qa_generator
make setup      # copies .env.example to .env and fills every placeholder secret
make install    # Python dependencies, spaCy pipelines and Docling's weights
```

`make setup` is safe to run again: it replaces only `change_me_*`
placeholders. `make install` needs the container engine running.

`.env` ships the production profile: `HOST_RUNNER=1`,
`LLM_MODEL=azure/gpt-5.4` and seven role models on Azure
([the production split](docs/configuration.md#the-production-split)). The
model stages run on the host. Put the provider credentials in
`configs/env/provider.env`.

`LLM_MODEL` is a [LiteLLM](https://docs.litellm.ai/docs/providers) model id.
Its prefix selects the provider:

```ini
LLM_MODEL=azure/<deployment>           # an API key, or Entra ID
LLM_MODEL=openai/gpt-4o                # OPENAI_API_KEY in provider.env
LLM_MODEL=anthropic/claude-sonnet-4-5  # ANTHROPIC_API_KEY
LLM_MODEL=ollama_chat/gemma4:31b       # local, no credentials
```

### Development profile

The development profile runs every stage in its container worker against a
local Ollama model. In `.env`, switch `LLM_MODEL` and `LLM_BASE_URL` to the
commented Ollama lines beside them, empty the role models that name Azure,
and remove `HOST_RUNNER=1`. Then pull the model:

```bash
ollama pull gemma4:31b
```

Pick a tag whose quantisation the runner can load: an `-mlx` build with
nvfp4 weights does not load under Ollama's MLX runner.

On both profiles `LLM_CONTAINER_MODEL` must name an Ollama model, and
compose refuses to start without it. A container never reads `LLM_MODEL`.

## Usage

### Production run

```bash
make docling-weights HOST=1             # Docling's weights into the host cache
make up                                 # database, object store, API, parse and chunk workers, frontend, Phoenix
make schema                             # creates the tables
make doctor                             # checks the config and sends one request to every model
make ingest DIR=<folder of PDFs>        # loads the corpus
make corpus-hosted SPEND_CAP=50         # runs every stage on the host, detached, up to USD 50
make questions-export OUT=release.xlsx FILTER="--released"
```

`make corpus-hosted` returns at once. Progress goes to
`logs/corpus-hosted.log`, and `make corpus-hosted-stop` stops the run. The
next `make corpus-hosted` resumes it. On this profile `make all`,
`make pipeline` and `make auto` refuse to run.
[The runbook](docs/operations.md#the-runbook) covers each step in detail.

### Development run

```bash
make dev        # certificates, every service, the schema
make doctor
```

The frontend is at <http://localhost:8501> and the API documentation at
<http://localhost:8000/docs>. The ports are set in
`configs/env/deployment.env`. `make services` lists the running containers
and their URLs, and `make help` lists every target.

Podman is the default container engine. To use Docker:

```bash
make CONTAINER=docker COMPOSE="docker compose" dev
```

Upload a PDF on the Upload page, or with curl. Every write to the API needs
`API_TOKEN` from `.env`:

```bash
curl -H "X-API-Token: $API_TOKEN" -F file=@guide.pdf http://localhost:8000/documents
```

The response gives the outcome (`stored` on the first upload) and the
file's `sha256`. Then run the pipeline in the container workers:

```bash
make all                                 # every stage except the topic fit
# when the run ends: Fit all on the Topics page, or POST /topics/discover
make pipeline                            # the stages again, now with questions for those topics
make questions-balance                   # draws the release
make questions-export OUT=exam.xlsx FILTER="--released"
```

The pipeline also starts from **Run the pipeline** on the Documents page,
from `POST /pipeline/run`, or on every upload with `make auto`. Follow it
with `make pipeline-status`, the Documents page or the Grafana pipeline
dashboard.

### Running stages on the host

`make corpus` runs every stage on the host, in order, for developing a
stage. A model stage refuses to run on the host while its container worker
runs. Host drains write to the same tables as the workers. Stage by stage:

```bash
make parse-start     && make parse       # a stored file becomes a structured document
make chunk-start     && make chunk       # the document becomes passages
make extract-start   && make extract     # passages become facts citing a sentence
make extract-digests                     # a digest for passages that finished without one
make topics-discover ENSURE=1            # fits topics when a language has none or they are stale
make topics-status                       # passages in no topic
make extract-bridge MISSING=1            # facts joining a topic's passages, for topics without any
make questions-start && make questions   # each topic's facts become questions
make questions-balance                   # draws the release
make assess-start    && make assess      # the judge, when ASSESSMENT_ENABLED is true
```

### Independent assessment

An optional second model judges each question. It changes no verdict: the
questions where the two models disagree form a queue for human review.

```ini
ASSESSMENT_ENABLED=true                           # .env
ASSESSMENT_JUDGE_CONTAINER_MODEL=azure/gpt-4.1    # the judge in assess-worker, not LLM_MODEL
```

```bash
make up                                  # assess-worker reads the new settings
make assess-enrol                        # enrols and counts before any spend; not a dry run
make assess-start                        # queues the enrolled rows for assess-worker
```

## Documentation

The [wiki](https://github.com/hazemkhaled-94/qa_generator/wiki) holds the
full documentation. Each service also documents itself in its own directory.

| Pipeline stage | |
|---|---|
| [backend/ingestion](backend/ingestion/README.md) | Upload validation, hashing and storage |
| [backend/preprocessing/parsing](backend/preprocessing/parsing/README.md) | Stored file to structured document |
| [backend/preprocessing/chunking](backend/preprocessing/chunking/README.md) | Document to passages |
| [backend/extraction](backend/extraction/README.md) | Passages to facts |
| [backend/topic_modelling](backend/topic_modelling/README.md) | Topics per language |
| [backend/question_generation](backend/question_generation/README.md) | Facts to questions |
| [backend/assessment](backend/assessment/README.md) | Independent judgement |

| Component | |
|---|---|
| [backend/api](backend/api/README.md) | HTTP API |
| [backend/stages](backend/stages/README.md) | Queue, worker and command line shared by every stage |
| [backend/database](backend/database/README.md) | Schema, migrations and triggers |
| [backend/blob_store](backend/blob_store/README.md) | Object storage buckets |
| [backend/archive](backend/archive/README.md) | Deleted documents and restore |
| [backend/nlp](backend/nlp/README.md) | Sentences, claims, vocabulary and language |
| [backend/llm](backend/llm/README.md) | Model calls |
| [backend/settings](backend/settings/README.md) | Runtime settings |
| [frontend](frontend/README.md) | Streamlit application |
| [orchestration](orchestration/README.md) | Dagster assets |
| [review](review/README.md) | Human review in Argilla |
| [evaluation](evaluation/README.md) | Model evaluation in Phoenix |
| [telemetry](telemetry/README.md) | Logging and tracing |
| [configs](configs/README.md) | Service configuration and init scripts |
| [tests](tests/README.md) | Test layers and what each needs |

| Guide | |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Module structure and dependency rules |
| [docs/configuration.md](docs/configuration.md) | Where each setting lives |
| [docs/make.md](docs/make.md) | Every `make` target |
| [docs/operations.md](docs/operations.md) | Deployment, scaling, monitoring and troubleshooting |
| [docs/measurements.md](docs/measurements.md) | Results of measured runs |
| [docs/bugs.md](docs/bugs.md) | Known defects and their fixes |

## Limitations

- Scanned documents are refused. OCR is off.
- Figures produce no passage of their own, and key-value form regions are
  not modelled.
- Changing `EMBEDDING_MODEL` requires a migration: `questions.embedding` is
  `vector(1024)`.
- Model calls dominate time and cost. A 30-document run took 5 h 41 min and
  USD 76. Question generation took USD 55 and 2 h 47 min on two drains;
  extraction took 2 h 01 min on one. `make estimate` and
  [Sizing a corpus](docs/operations.md#sizing-a-corpus) estimate a corpus.
  A local model is one to two orders of magnitude slower per call than a
  hosted one.

## Licence

[Apache 2.0](LICENSE).
