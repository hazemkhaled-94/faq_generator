# Configuration

Settings come from files. A setting that `settings/catalog.py` does not mark
fixed can be overridden through the UI, the API or `make settings-set` without
a restart. A fixed setting changes in its file and takes a restart.
[`backend/settings/`](../backend/settings/README.md) describes the mechanics.

This page names no defaults: each file holds its values once.

## The files

| File | In git | Holds |
|---|---|---|
| `configs/env/backend.env` | yes | Pipeline behaviour: parsing, chunking, extraction, topic, question and assessment settings |
| `configs/env/deployment.env` | yes | Ports, container-side addresses, topology, role names |
| `configs/env/elasticsearch.env` | yes | The node's certificate paths, security flags and heap |
| `configs/env/seaweedfs-filer.env` | yes | Which metadata store the filer uses |
| `configs/env/orchestration.env` | yes | How long Dagster waits on a stage |
| `configs/env/review.env` | yes | How a review sample is drawn |
| `configs/env/evaluation.env` | yes | What a golden-set run is called in Phoenix |
| `configs/env/provider.env` | no | The env vars the model provider needs. `make setup` writes it from `provider.env.example` |
| `.env` | no | The credentials and the model the deployment calls |

A name appears in exactly one committed file, and `.env.example` sets no name
a committed file sets. `tests/static/test_env_files.py` refuses a second one.

`.env` is the one permitted exception: the Makefile and compose read it last,
so a name it sets again wins. A [second
stack](operations.md#a-second-stack-beside-the-first) uses this to move its
ports. `make doctor` lists every name `.env` (or `ENV_FILE`) sets over a
committed file.

compose hands each file to its services with `env_file`. The Makefile sources
`backend.env`, `deployment.env`, `provider.env` and `.env` for host commands.
`.env.example` stands in for `.env` in git, with a `change_me_*` placeholder
per secret, and `make setup` copies it and generates the passwords.

compose refuses to start while a password or key is missing or empty, and
names it. Only `S3_ACCESS_KEY` and `S3_SECRET_KEY` may be empty.

## What compose reads

compose interpolates `${...}` from two files, and the last wins:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env
```

The Makefile's compose commands go through `$(COMPOSE_CMD)`, which carries
both flags. A bare `podman compose` sees only `.env` and fails on the first
missing port. Export `COMPOSE_ENV_FILES` for it. It cannot be set inside
`.env`:

```bash
export COMPOSE_ENV_FILES=configs/env/deployment.env,.env
```

## What is derived, and so written nowhere

| Value | Built from | By |
|---|---|---|
| `DATABASE_URL` | `APP_DB_USER`, `APP_DB_PASSWORD`, `APP_DB_NAME`, `POSTGRES_PORT` | the Makefile (host), compose (containers) |
| `BACKEND_URL` | `BACKEND_PORT` | the Makefile |
| `S3_ENDPOINT` | `S3_PORT` | the Makefile |
| `PHOENIX_BASE_URL` | `PHOENIX_PORT` | the Makefile, and compose for the frontend's links |
| `OTEL_EXPORTER_OTLP_ENDPOINT`, `ARGILLA_API_URL` | `PHOENIX_GRPC_PORT`, `ARGILLA_PORT` | the Makefile |
| `SERVICE_URLS` | every published port | compose, for the System health page |
| `SPACY_MODELS` | `NLP_MODELS` | the Makefile |

### The host and the container see different addresses

The plain name is the host's. `*_CONTAINER_*` is what compose sets over it
inside the network.

| The host's | The container's |
|---|---|
| `BACKEND_URL` | `BACKEND_CONTAINER_URL` |
| `S3_ENDPOINT` | `S3_CONTAINER_ENDPOINT` |
| `PHOENIX_BASE_URL` | `PHOENIX_CONTAINER_BASE_URL` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `OTEL_CONTAINER_ENDPOINT` |
| `LLM_MODEL`, `LLM_BASE_URL`, `OLLAMA_BASE_URL` | `LLM_CONTAINER_MODEL`, and `OLLAMA_CONTAINER_URL` for both addresses |
| `QUESTIONS_VERIFIER_MODEL` | `QUESTIONS_VERIFIER_CONTAINER_MODEL` |
| `ASSESSMENT_JUDGE_MODEL` | `ASSESSMENT_JUDGE_CONTAINER_MODEL` |

The model pairs are the ones that do not fall back. `LLM_CONTAINER_MODEL` is
required, must name an Ollama model, is checked by `make doctor`, and does not
inherit `LLM_MODEL`. The verifier and judge do not inherit either: unset in
the containers, the writer marks its own work and nothing is judged. A
container given a hosted model it has no credential for waits in place and
logs every ten minutes that it cannot reach it.

## The production split

Production runs the model stages on the host through `make corpus-hosted`,
with `HOST_RUNNER=1` in `.env` and the model workers stopped. `.env.example`
ships the model split:

| Role | Setting | Model |
|---|---|---|
| Writer | `QUESTIONS_MODEL` | `azure/gpt-5.6-sol` |
| Passage reader | `EXTRACTION_MODEL` | `azure/gpt-5.4` |
| Phrasing judge | `QUESTIONS_PHRASING_MODEL` | `azure/gpt-5.4` |
| Digest reader | `EXTRACTION_DIGEST_MODEL` | `azure/gpt-4o` |
| Assessment judge | `ASSESSMENT_JUDGE_MODEL` | `azure/gpt-4o` |
| Verifier | `QUESTIONS_VERIFIER_MODEL` | `azure/gpt-4.1` |
| Topic namer | `TOPIC_MODEL` | `azure/gpt-4.1` |

- A role with no setting follows `LLM_MODEL`. The judge follows nothing.
  `backend.env` names no role model.
- `LLM_REASONING_EFFORT=none` is the one effort the split needs. A hosted
  model that does not reason is sent no effort.
- An assessment build warns when the judge is the writer's or verifier's
  model.
- The split has one address: every role model is reached through
  `LLM_BASE_URL`. A split across several Azure resources needs a gateway that
  routes by model id.

Every drain logs `split: writer=... effort=...` before it claims a row. With
`HOST_RUNNER=1`, a drain and `make doctor` refuse a role that resolves to an
Ollama model (including an OpenAI-compatible id served from an Ollama address,
such as `LLM_BASE_URL` on port 11434), and a judge left unset while
`ASSESSMENT_ENABLED` is true.

### Prices follow the installed litellm

`LITELLM_LOCAL_MODEL_COST_MAP=true` is committed, so litellm reads the
installed package's model list and prices change only with the litellm lock. A
model litellm does not list is unpriced, and a drain with `SPEND_CAP` set
refuses it.

## Pinning the encoders

`EMBEDDING_MODEL`, `NLI_MODEL` and `QA_MODEL` are Hugging Face repositories.
Each has a commit beside it (`EMBEDDING_MODEL_REVISION`, `NLI_MODEL_REVISION`,
`QA_MODEL_REVISION`) that every load passes, so a push to a repository's
default branch cannot change results.

- `backend.env` ships the commits. `QA_MODEL_REVISION` is empty while
  `QA_MODEL` is, and a `QA_MODEL` with no revision is refused at first load.
- The commits and model ids are fixed. A model and its commit change together,
  in the file. A stored row for a model id is refused at every stage's build,
  naming the `DELETE` that removes it.

With `HF_HUB_OFFLINE=1`, which `make corpus-hosted` sets, nothing is fetched.
`make doctor` names what the cache lacks: each encoder at its pinned commit
with its config and a weights file (`model.safetensors`, `pytorch_model.bin`
or a shard index), and Docling's weights (in `DOCLING_ARTIFACTS_PATH` where
that names a folder, else in the cache). A miss fails with `HF_HUB_OFFLINE=1`
or `HOST_RUNNER=1` and warns otherwise. `DOCLING_ARTIFACTS_PATH` set and empty
is refused.

Before a production run, fill the host's cache once, where the Hub is
reachable:

```bash
make docling-weights HOST=1
poetry run hf download <repo> --revision <commit>   # each encoder; make doctor prints the line for one it misses
```

Plain `make docling-weights` fills the containers' volume, which the host does
not read. With `DOCLING_ARTIFACTS_PATH` set, run `poetry run docling-tools
models download -o <that folder>`.

## Production settings

The settings that [Production deployment](operations.md#production-deployment)
relies on, with the review item each comes from. The production split above
covers `HOST_RUNNER` (C-006, C-073), the role models and effort (C-051),
`LLM_BASE_URL` (C-366), the judge (C-006), the revisions (C-117) and the cost
map (C-088).

| Setting | File | In production | Item |
|---|---|---|---|
| `APP_DB_PASSWORD` | `.env` | Letters, digits, `-`, `_`, `.` only: `@ / : # ? %` are refused | C-201 |
| `API_TOKEN` | `.env` | Generated by `make setup`. Keep the ports on 127.0.0.1 | C-085 |
| `HF_HUB_OFFLINE`, `DOCLING_ARTIFACTS_PATH` | `make corpus-hosted`, `backend.env` | `1` over a [filled cache](#pinning-the-encoders); the path never set and empty | C-072 |
| `SPEND_CAP` | command line | A cap in USD for the whole run | C-091, C-219 |
| `TOPIC_NUM_TOPICS` | `backend.env` | As shipped (300 a language). `make estimate` gives the cost | C-024 |
| `QUESTIONS_TYPE_MIX`, `QUESTIONS_RELEASE_TYPES` | `backend.env` | `entity` and `temporal` at 0 until calibrated on the production corpus | C-176, C-217 |
| `QUESTIONS_RELEASE_DIFFICULTY` | `backend.env` | Unset: the bands measure retrieval spread, not hardness | C-029 |
| `QA_MODEL` | `backend.env` | Empty, until an encoder is calibrated | C-424 |
| `EXTRACTION_DUPLICATE_COSINE` | `backend.env` | As shipped (0 also stops writing passage embeddings) | C-245 |
| `EMBEDDING_MAX_TOKENS` | `backend.env` | Above the corpus's widest table row, checked before ingest | C-278 |
| `POSTGRES_*` | `deployment.env` | The production row of [Sizing Postgres](operations.md#sizing-postgres) | C-011 |
| `PHOENIX_TRACE_RETENTION_DAYS` | `deployment.env` | Set: traces hold every passage a prompt sent | C-103 |

## Precedence

Highest first. A worker picks a change up when its queue next runs dry, and
nothing is requeued.

1. A variable on a `make` command line, for the host process that command
   runs. It never reaches a running container: `make extract-start
   EXTRACTION_DUPLICATE_COSINE=0.9` queues the passages, and `extract-worker`
   drains them under the stored or file value.
2. A row in `service_settings`, set through the UI, the API or `make
   settings-set`.
3. The file that declares the setting.

A variable missing from its file stops the service at start-up and names
itself, except:

| Setting | When absent |
|---|---|
| a stage's own model | follows `LLM_MODEL` |
| `LOG_LEVEL` | INFO |
| the two pool sizes | 5 |
| `QUESTIONS_MEETS_SHARE` | its shipped value |
| `QUESTIONS_KIND_MIX` | deals `needs_both:5,compound:1` |
| `QUESTIONS_CATEGORIZATIONS` | reads `DEFAULT_CATEGORIZATIONS` in [`question_generation/config.py`](../backend/question_generation/config.py), because no file here can hold JSON (see [A JSON value](#a-json-value)) |

Deleting an override row returns a setting to the file, or to what its absence
reads.

## Changing one

```bash
# On the page that runs the service, under Configuration.

# Or the API, one service per request, with API_TOKEN from .env:
curl -s -H "X-API-Token: $API_TOKEN" localhost:8000/settings/topics
curl -s -X PATCH localhost:8000/settings/topics \
  -H "X-API-Token: $API_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"values": {"TOPIC_PASSES": "20"}}'

# Or a terminal:
make settings SERVICE=topics
make settings-set SERVICE=topics SET="TOPIC_PASSES=20"
make settings-unset SERVICE=topics UNSET="TOPIC_PASSES"
```

`make settings SERVICE=<name>` and `make doctor` list how many stored rows of
extraction, topics and questions predate a change that stales that stage, with
the least destructive command. The page, the API and `make settings-set` name
the stale stage. Where every changed setting has a cheaper rebuild, such as
`make extract-revalidate` or `make questions-balance`, they name that command.
Otherwise they say to rerun the stage. A change in a file is not dated and
shows only after a restart.

### A JSON value

`QUESTIONS_CATEGORIZATIONS` holds the categorizations of the DataMorgana paper
(Filice et al., [*Generating Q&A Benchmarks for RAG Evaluation in Enterprise
Settings*](https://aclanthology.org/2025.acl-industry.33/), ACL 2025 Industry
Track) as JSON: one categorization object as the paper's Figure 2 prints it,
or a list of them. Each answerable question is written as one category of
each, and the question records which. A compound question and a follow-up are
told none. An unanswerable question is told only its kind.

Its line in `configs/env/backend.env` is a comment, because bash would split a
JSON value at its spaces. Unset, it reads `DEFAULT_CATEGORIZATIONS` in code.
`[]` turns categories off.

The default is three of the paper's Table 5 categorizations, each category at
even odds:

| Categorization | Categories |
|---|---|
| Phrasing | concise-and-natural, verbose-and-natural |
| Premise | direct, with-premise |
| Linguistic variation | similar-to-document, distant-from-document |

Two are reworded. distant-from-document keeps the meaning of every term it
rewords and coins no word, where the paper's "terms completely different"
swapped meaning-bearing terms. It passed calibration against
similar-to-document (keys 58 and 57 of 60, complete 57 and 54, invalid 4 and
11 per 60, conformance 0.80). with-premise asks the asker to state, in the
first person, a fact of their own situation (something they have, did, bought
or plan), because the paper's wording made the asker optional.

Table 5's Factuality is not used: factoid or open-ended is read off the answer
form of the type. User expertise is opt-in, because its conformance was 0.59
in calibration. Listed beside the default's three, it reads:

```json
[
  {
    "categorization_name": "User expertise",
    "role": "user",
    "categories": [
      {"name": "expert", "description": "The user asking the question knows the material and its terms, uses them exactly as the material writes them, and asks about a detail, an exception or a condition a newcomer would not know to ask about."},
      {"name": "novice", "description": "The user asking the question is a regular user with no understanding of specialized terms."}
    ]
  }
]
```

Set it on the Questions page, through the API, or with `settings.run`:

```bash
curl -s -X PATCH localhost:8000/settings/questions \
  -H "X-API-Token: $API_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"values": {"QUESTIONS_CATEGORIZATIONS": "[]"}}'

PYTHONPATH=backend poetry run python -m settings.run --service questions \
  --set 'QUESTIONS_CATEGORIZATIONS=[]'
```

`make settings-set` splits `SET` at spaces and breaks a JSON value. `make
settings-unset SERVICE=questions UNSET=QUESTIONS_CATEGORIZATIONS` returns to
the default in code.

A value is refused before anything is stored, naming the categorization or
category at fault, when:

- it is not JSON, or an item is not a categorization object;
- a categorization has no `categorization_name`, or one holding `=`, a comma
  or a line break, or shares a name with another;
- a categorization or category has a key the format lacks, or a
  categorization's role is not `question` or `user`, or it has no categories
  or names one twice;
- a category has no name or description, or a name that is empty or holds `=`,
  a comma or a line break;
- only some categories of a categorization have a probability, a probability
  is outside 0 to 1, or they do not sum to 1;
- `words` is not an object of `min` and `max`, a bound is not a whole number
  of at least 1, `min` exceeds `max`, or a form is not `question`, `query` or
  `premise`;
- `settles` is not `answers`, `refutes` or `silent`, only one of `settles` and
  `behaviour` is present, or `behaviour` is empty;
- only some categories of a categorization carry `settles`, or two
  categorizations carry it;
- a categorization carrying `settles` has a role other than `question`, or a
  category form other than `question`.

#### User categorizations

A categorization describes the question unless it says `"role": "user"`, which
describes the person asking. The answer must assume nothing about the asker
that the question does not say:

```json
[
  {
    "categorization_name": "Account experience",
    "role": "user",
    "categories": [
      {"name": "account-holder", "description": "an account holder who has held a current account for years and knows its terms."},
      {"name": "first-time", "description": "somebody opening their first account, who knows none of the bank's terms."}
    ]
  }
]
```

#### Premise

A category of `"form": "premise"` opens the question with what the asker says
about themselves, as the default's with-premise does. A value replaces the
default whole: list the default's categorizations beside it to keep them.

A premise is not told beside a category capping the question's words (such as
concise-and-natural) or beside a search query. A first draft is written once
more, with a note asking for the asker's own situation, when its premise holds
none of its language's first- or second-person pronouns (`_SPEAKING` in
`question_generation/generation.py`, German and English), or its verbs only
want, try, check or understand (`_ENQUIRING`; "I want to know" is noted, "I
want to return a jacket" is not). The second draft is kept.

#### Search queries

`"form": "query"` makes a category a search query: keywords typed into a box.

- The writer is told the question-mark rule does not apply. Every other rule
  holds.
- A query is not told on a slot that spans two passages, nor on a `reason`,
  `comparison`, `implication` or `temporal` slot. Such a slot is written as no
  category of the query's categorization.
- A query with a `max` in its `words` is also read against the
  `QUESTIONS_ELSEWHERE_PASSAGES` nearest passages it does not cite, and
  refused as not recoverable where one answers it differently.

Table 5's short and long search queries are of form `query` and neither is
dealt unset. In calibration the short one was accepted for 30% of its rows
(natural phrasings: 82 to 86%), and the long one reached 36 accepted rows,
under the 40 a category needs. A Phrasing that lists them beside the natural
phrasings, set in place of the default's, deals all four at even odds:

```json
[
  {
    "categorization_name": "Phrasing",
    "categories": [
      {"name": "concise-and-natural", "description": "phrased in the way people typically speak, reflecting everyday language use, without formal or artificial structure. It is a concise, direct question consisting of less than 10 words.", "words": {"max": 9}},
      {"name": "verbose-and-natural", "description": "phrased in the way people typically speak, reflecting everyday language use, without formal or artificial structure. It is a relatively long question consisting of more than 9 words.", "words": {"min": 10}},
      {"name": "short-search-query", "form": "query", "description": "phrased as a typed web query for search engines (only keywords, without punctuation and without a natural-sounding structure). It consists of less than 7 words.", "words": {"max": 6}},
      {"name": "long-search-query", "form": "query", "description": "phrased as a typed web query for search engines: keywords only, the nouns, names and figures of what is wanted, with no article, no auxiliary verb, no question word and nothing about the asker. It consists of more than 6 words.", "words": {"min": 7}}
    ]
  }
]
```

#### Word bounds

A category may carry `"words": {"min": 10}`, `{"max": 9}` or both. The writer
is not sent them and no question is refused for missing them. `make diversity
BY=category` reports the share of each category's questions inside them. The
default bounds are at most 9 words for concise-and-natural and at least 10 for
verbose-and-natural. A `max` also stops a premise being told beside the
category.

#### The unanswerable kinds

A categorization whose categories all carry `settles` and `behaviour` is the
unanswerable one. Its categories are kinds of question with no answer, told
only the unanswerable writer. At most one categorization may carry them, with
role `question` and every form `question`.

- `settles` is the verdict the settles reading must give over the cited
  passages for the question to be kept: `silent`, `refutes` or `answers` (the
  last two need words in the passages behind them). Any other verdict that
  answers the question refuses it as `answerable_after_all` or
  `answerable_elsewhere`. `silent` where the kind wants another refuses it as
  `wrong_type`.
- `behaviour` is what a good reply does, a criterion for a judge and not a
  reference answer. The export's Answer cell reads `Expected behaviour: ` and
  it, blank where none was stored.

The kinds follow UAEval4RAG (Peng et al., [*Unanswerability Evaluation for
Retrieval Augmented Generation*](https://aclanthology.org/2025.acl-long.415/),
ACL 2025), and the behaviours its Table 11's acceptable responses, modified
(code:
[SalesforceAIResearch/Unanswerability_RAGE](https://github.com/SalesforceAIResearch/Unanswerability_RAGE),
Apache-2.0).

The default deals unanswerable slots `out-of-corpus` alone, at probability 1:
the one kind that passed calibration
([measurements](measurements.md#unanswerable-kinds-v050)). The other three are
opt-in. `UNANSWERABLE_CATEGORIZATION` in
[`question_generation/config.py`](../backend/question_generation/config.py)
holds all four. List it in place of the default's own `Unanswerable` entry:

```json
{
  "categorization_name": "Unanswerable",
  "categories": [
    {"name": "out-of-corpus", "settles": "silent", "description": "one that moves the fact just out of reach with ONE change: a neighbouring thing the material does not cover, a detail of the same subject it does not state, or a different party, place or period that no list or rule in it reaches. It is still a plausible thing to ask of the material: never absurd, never about a thing that does not exist.", "behaviour": "says the material does not cover it, and does not invent an answer"},
    {"name": "false-presupposition", "settles": "refutes", "description": "one that takes for granted something the material says is not so - a party, a condition or an option it rules out - and asks about it as if it were so. It is still a plausible thing to ask of the material.", "behaviour": "points out that what the question takes for granted is not so, and may answer the corrected question, or declines to answer"},
    {"name": "underspecified", "settles": "answers", "description": "one that leaves out the detail the material needs to choose between its cases (which account, which product, which period), so that each case has its own answer. It is still a plausible thing to ask of the material.", "behaviour": "asks which case is meant, or gives the answer for each case the material distinguishes"},
    {"name": "nonsensical", "settles": "silent", "description": "one that joins things the material names in a way that makes no sense, so that no answer fits; it uses only words the material uses, and is not a typing error.", "behaviour": "says the question does not make sense as asked, asks what is meant, or declines to answer"}
  ]
}
```

#### Rerunning a stage

A stage's rerun is its `-rerun` target, bar topics, which have none: `make
topics-discover` fits them again and carries what a person decided about a
topic over to the matching new topic.

- Rerunning extraction leaves the bridges to `make extract-bridge`.
- Rerunning questions writes only about facts no accepted question rests on.
  `make questions-reverify` re-checks with the gates that need no model.
- `make questions-rejudge` asks again about every accepted unanswerable
  question whose `settles` verdict came from another verifier prompt version,
  at one `settles` reading per question (two where the cited passages are
  silent and the passage probe is on).

A fixed setting changes only in its file, with a restart, and no surface
reports what it left stale. After changing `NLP_MODELS`,
`NLP_DEFAULT_LANGUAGE` or `NLP_CAPITALISED_NOUNS`, rerun chunking and every
stage after it.

## The eight services

The services are `ingestion` (Upload page), `parsing` (Documents), `chunking`
(Passages), `extraction` (Facts), `topics` (Topics), `questions` (Questions),
`assessment` (Assessment) and `platform` (System health: model, tokenizer,
language pipelines).

`EXTRACTION_MODEL`, `TOPIC_MODEL` and `QUESTIONS_MODEL` name a stage's own
model, each meaning `LLM_MODEL` when absent. `EXTRACTION_DIGEST_MODEL`,
`QUESTIONS_PHRASING_MODEL`, `QUESTIONS_VERIFIER_MODEL` and
`ASSESSMENT_JUDGE_MODEL` name a model for one judgement. These eight model
settings, `LLM_MODEL` among them, are fixed: served read-only and never
stored. Three have a container value of their own, which compose sets over the
host's: `LLM_MODEL`, `QUESTIONS_VERIFIER_MODEL` and `ASSESSMENT_JUDGE_MODEL`,
in the table above. The other five come from `configs/env/backend.env` for
both.

Also fixed, and refused by a settings write: `NLP_MODELS`,
`NLP_DEFAULT_LANGUAGE`, `NLP_CAPITALISED_NOUNS`, `WORKER_POLL_SECONDS`,
`SPEND_CAP`, the pool sizes, `API_ALLOWED_HOSTS`, and the addresses
(`LLM_BASE_URL` among them).

## Where to look for a setting

| Looking for | Read |
|---|---|
| Which model, and where it is served | `.env` for `LLM_MODEL`, the verifier, the judge, their container values and the addresses. `.env.example` for the production split. A stage's own model (`EXTRACTION_MODEL`, `EXTRACTION_DIGEST_MODEL`, `TOPIC_MODEL`, `QUESTIONS_MODEL`, `QUESTIONS_PHRASING_MODEL`) is documented, unset, in `configs/env/backend.env` beside that stage's settings |
| How the model is called, and what a fact may be | `configs/env/backend.env`, "Extraction" |
| Encoders, tokenizer, spaCy pipelines | `configs/env/backend.env`, "Embedding", "Encoders that run in this process", "Language pipelines" |
| How many topics, and how they are fitted | `configs/env/backend.env`, "Topic modelling", and [`backend/topic_modelling/`](../backend/topic_modelling/README.md) |
| What a run costs, and what it writes | `configs/env/backend.env`, "Question generation", and [`backend/question_generation/`](../backend/question_generation/README.md) |
| What each question is written as | `QUESTIONS_CATEGORIZATIONS` ([A JSON value](#a-json-value)) |
| Which accepted questions ship | `configs/env/backend.env`, "The balanced release" |
| A port, an address, a role name | `configs/env/deployment.env` |
| A password or a key | `.env`, listed in `.env.example`. The provider's: `configs/env/provider.env` |

[measurements.md](measurements.md) says how defaults were measured.

## Five settings with constraints

- `PHOENIX_ADMIN_SECRET` needs at least 32 characters including a digit and a
  lower-case letter. `make doctor` checks all three.
- `PHOENIX_SECRET`, in `.env`, needs at least 32 characters. `make setup`
  generates one.
- `PHOENIX_DEFAULT_ADMIN_INITIAL_PASSWORD` applies only when Phoenix first
  creates its admin user. Changing it later means dropping the `phoenix`
  database.
- `GRAFANA_SECRET_KEY`, in `.env`, encrypts the secrets Grafana stores.
  compose refuses to start Grafana without it. Changing it is a rotation:
  [operations.md](operations.md) has the steps.
- `MAX_FILE_SIZE_MB` is written in two files, because Streamlit reads a static
  TOML: `server.maxUploadSize` in `frontend/.streamlit/config.toml` must match
  it, or the frontend rejects a file before the API sees it. A test pins the
  pair. The panel can change `MAX_FILE_SIZE_MB` without a restart, and nothing
  checks it against the TOML.

## What is enforced

- `tests/static/test_env_files.py`: one name, one file. Every `${...}` compose
  interpolates is declared, every password and key compose passes is required
  (`:?`, or `?` for the two S3 keys), and `.env.example` holds a placeholder
  for every secret.
- `tests/static/test_settings_documented.py`: every setting the code reads by
  literal name is named in a file that declares it. `TRACE_DATABASE` (a span
  per SQL statement, see [`telemetry/README.md`](../telemetry/README.md)),
  `RUN_ID` (see [`backend/settings/README.md`](../backend/settings/README.md))
  and the pool sizes are read another way and are not seen.
- `tests/static/test_settings_catalogued.py`: every setting read by literal
  name in `backend/`, `frontend/` and `telemetry/` is described in
  `settings/catalog.py`, bar the few the test lists. `orchestration/` is not
  scanned, so `INGESTION_OPEN` has no description and no panel.
- `tests/static/test_language_tables.py`: every word table keyed by language
  has a row for each language `NLP_MODELS` names.
- `tests/static/test_doc_links.py`: every relative link in a README resolves.
