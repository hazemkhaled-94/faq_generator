# Configuration

Settings come from files. A setting that `settings/catalog.py` describes and does not mark fixed can be overridden through the UI, the API or `make settings-set` without a restart. A fixed setting changes in its file and takes a restart. The mechanics are in [`backend/settings/`](../backend/settings/README.md).

This page names no defaults. Each file holds its values once, and a copy here could disagree with it. The page says what a setting is. The file named beside it says what the setting is set to.

## The files

| File | In git | Holds |
|---|---|---|
| `configs/env/backend.env` | yes | How the pipeline behaves: the parsing, chunking, extraction, topic, question and assessment settings |
| `configs/env/deployment.env` | yes | Where the deployment puts things: the ports, the container-side addresses, the topology, the role names |
| `configs/env/elasticsearch.env` | yes | The node's certificate paths, security flags and heap |
| `configs/env/seaweedfs-filer.env` | yes | Which metadata store the filer uses |
| `configs/env/orchestration.env` | yes | How long Dagster waits on a stage |
| `configs/env/review.env` | yes | How a review sample is drawn |
| `configs/env/evaluation.env` | yes | What a golden-set run is called in Phoenix |
| `configs/env/provider.env` | no | The env vars the model provider needs. `make setup` writes it from `configs/env/provider.env.example`, which is in git |
| `.env` | no | The credentials and the model the deployment calls |

A name appears in exactly one committed file. `.env.example` sets no name that a committed file sets. `tests/static/test_env_files.py` refuses a second live assignment of a name, reading `.env.example` in place of `.env`. It does not read `configs/env/provider.env`, which is not in git.

`.env` is the one permitted exception. The Makefile and compose read it last, so a name it sets again wins over `backend.env` or `deployment.env`. A [second stack](operations.md#a-second-stack-beside-the-first) uses this to move its ports and project name. `make doctor` lists every name that `.env` (or `ENV_FILE`) sets over a committed file, with the file it wins over.

compose hands each file to the services that need it with `env_file`. The Makefile sources `backend.env`, `deployment.env`, `provider.env` and `.env` for host commands, so one value reaches both.

`.env` holds the deployment's secrets and `provider.env` the provider's. `.env.example` stands in for `.env` in git, with a `change_me_*` placeholder for every secret beside the model names. `make setup` copies it to `.env` and generates the passwords.

compose refuses to start while a password or key it passes is missing from `.env` or empty, and names the one it lacks. Only `S3_ACCESS_KEY` and `S3_SECRET_KEY` may be empty, which lets boto3 find an instance role or a profile. Their lines must still be present.

## What compose reads

compose interpolates `${...}` from two files. The last one wins, so a secret can sit over a name:

```bash
podman compose --env-file configs/env/deployment.env --env-file .env
```

Every compose command in the Makefile goes through `$(COMPOSE_CMD)`, which carries both flags. `COMPOSE` stays the engine alone, so `make COMPOSE="docker compose" up` keeps both files. A bare `podman compose` outside make sees only `.env` and fails on the first missing port. Export `COMPOSE_ENV_FILES` for it:

```bash
export COMPOSE_ENV_FILES=configs/env/deployment.env,.env
```

`COMPOSE_ENV_FILES` cannot be set inside `.env`, because compose resolves the file list before it reads one.

## What is derived, and so written nowhere

These values are built from other names, so no port or password is copied into a second place.

| Value | Built from | By |
|---|---|---|
| `DATABASE_URL` | `APP_DB_USER`, `APP_DB_PASSWORD`, `APP_DB_NAME`, `POSTGRES_PORT` | the Makefile for a host command, compose for a container |
| `BACKEND_URL` | `BACKEND_PORT` | the Makefile. The container's is `BACKEND_CONTAINER_URL` |
| `S3_ENDPOINT` | `S3_PORT` | the Makefile. The container's is `S3_CONTAINER_ENDPOINT` |
| `PHOENIX_BASE_URL` | `PHOENIX_PORT` | the Makefile, and compose for the frontend's browser links. The container's is `PHOENIX_CONTAINER_BASE_URL` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `PHOENIX_GRPC_PORT` | the Makefile. The container's is `OTEL_CONTAINER_ENDPOINT` |
| `ARGILLA_API_URL` | `ARGILLA_PORT` | the Makefile |
| `SERVICE_URLS` | every published port | compose, for the System health page |
| `SPACY_MODELS` | `NLP_MODELS` | the Makefile, which exports it so the image bakes the pipelines the workers load |

### The host and the container see different addresses

Seven things have two names. The plain name is the host's. `*_CONTAINER_*` is what compose sets over it inside the network.

| The host's | The container's |
|---|---|
| `BACKEND_URL` | `BACKEND_CONTAINER_URL` |
| `S3_ENDPOINT` | `S3_CONTAINER_ENDPOINT` |
| `PHOENIX_BASE_URL` | `PHOENIX_CONTAINER_BASE_URL` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `OTEL_CONTAINER_ENDPOINT` |
| `LLM_MODEL`, `LLM_BASE_URL`, `OLLAMA_BASE_URL` | `LLM_CONTAINER_MODEL`, and `OLLAMA_CONTAINER_URL` for both addresses |
| `QUESTIONS_VERIFIER_MODEL` | `QUESTIONS_VERIFIER_CONTAINER_MODEL` |
| `ASSESSMENT_JUDGE_MODEL` | `ASSESSMENT_JUDGE_CONTAINER_MODEL` |

The model pairs are the ones that do not fall back. `LLM_CONTAINER_MODEL` is required, must name an Ollama model, is checked by `make doctor`, and does not inherit `LLM_MODEL`. The verifier and the judge do not inherit either. Unset in the containers, the writer marks its own work and nothing is judged. A container given a hosted model it has no credential for does not restart. Its worker waits in place, claims nothing, and logs every ten minutes that it cannot reach its model, until the model answers.

## The production split

Production runs the model stages on the host through `make corpus-hosted`, with `HOST_RUNNER=1` in `.env` and the model workers stopped. `.env` also holds the model split, and `.env.example` ships it:

| Role | Setting | Model |
|---|---|---|
| Writer | `QUESTIONS_MODEL` | `azure/gpt-5.6-sol` |
| Passage reader | `EXTRACTION_MODEL` | `azure/gpt-5.4` |
| Phrasing judge | `QUESTIONS_PHRASING_MODEL` | `azure/gpt-5.4` |
| Digest reader | `EXTRACTION_DIGEST_MODEL` | `azure/gpt-4o` |
| Assessment judge | `ASSESSMENT_JUDGE_MODEL` | `azure/gpt-4o` |
| Verifier | `QUESTIONS_VERIFIER_MODEL` | `azure/gpt-4.1` |
| Topic namer | `TOPIC_MODEL` | `azure/gpt-4.1` |

- `LLM_MODEL` is the model a role follows when its own setting is unset. The judge follows nothing.
- `backend.env` names no role model, so an unset role follows `LLM_MODEL`, never a project default.
- `LLM_REASONING_EFFORT=none` is the one effort the split needs. A hosted model that does not reason is sent no effort.
- The judge shares `azure/gpt-4o` with the digest reader. An assessment build says so in an INFO line. It warns only when the judge is the writer's or the verifier's model, the roles that wrote and checked the questions it judges.
- The split has one address: every role model is reached through `LLM_BASE_URL`. A split across several Azure resources, each with its own endpoint and key, needs a gateway in front of them that routes by model id. litellm does not pick an endpoint per role.

Every drain logs the split it resolved as one line, `split: writer=... effort=...`, before it claims a row. `make doctor` checks the same split. With `HOST_RUNNER=1`, a drain and the doctor refuse:

- a role that resolves to an Ollama model, including an OpenAI-compatible id served from an Ollama address (`LLM_BASE_URL` on port 11434, or a host named `ollama`);
- a judge left unset while `ASSESSMENT_ENABLED` is true.

The refusal names the role and the setting that moves it. The containers keep calling Ollama: the role models in `.env` never reach them, and compose gives them `LLM_CONTAINER_MODEL`.

### Prices follow the installed litellm

`LITELLM_LOCAL_MODEL_COST_MAP=true` is committed in `backend.env`, so litellm reads the model list of the installed package and fetches none at import. The prices that `make spend` and `SPEND_CAP` count at change only with the litellm lock. The same list says which hosted models do not reason and so are sent no `LLM_REASONING_EFFORT`. A model litellm does not list is unpriced, and a drain with `SPEND_CAP` set refuses it.

## Pinning the encoders

`EMBEDDING_MODEL`, `NLI_MODEL` and `QA_MODEL` are Hugging Face repositories. A bare repository id is whatever its default branch holds when a worker first loads it, so a push there changes passages and scores under the same settings. Each model has a commit beside it: `EMBEDDING_MODEL_REVISION`, `NLI_MODEL_REVISION` and `QA_MODEL_REVISION`. Every load passes it: the embedder, the tokenizer that chunking sizes passages with, the NLI pipeline and the QA head.

- `backend.env` ships the commits that are in the build's cache.
- `QA_MODEL_REVISION` is empty while `QA_MODEL` is. A `QA_MODEL` with no revision is refused at its first load.
- The three commits and the three model ids are fixed. The Configuration page does not offer them, and a model and its commit change together, in the file.
- A stored row made for one of the model ids before pinning is refused at every stage's build. The refusal names its pin and the `DELETE` that removes it.

With `HF_HUB_OFFLINE=1`, which `make corpus-hosted` sets, nothing is fetched. `make doctor` then reads the cache and names what is missing:

- each encoder at its pinned commit, with its config and a weights file (`model.safetensors`, `pytorch_model.bin` or a shard index; a snapshot left by a tokenizer load holds neither);
- Docling's weights, in `DOCLING_ARTIFACTS_PATH` where that names a folder and in the cache otherwise.

The doctor fails on what is missing with `HF_HUB_OFFLINE=1` or `HOST_RUNNER=1`, and warns otherwise, since a first load fetches it. `make corpus-hosted` runs the check with the Hub off before it detaches. `DOCLING_ARTIFACTS_PATH` set and empty is refused, because Docling reads it as the working directory.

Fill the host's cache once, where the Hub is reachable, before a production run:

```bash
make docling-weights HOST=1
poetry run hf download <repo> --revision <commit>   # each encoder; make doctor prints the line for one it misses
```

Plain `make docling-weights` fills the containers' `models` volume, which the parse worker reads and the host does not. With `DOCLING_ARTIFACTS_PATH` set, `poetry run docling-tools models download -o <that folder>` fills the folder instead.

## Production settings

The settings that [Production deployment](operations.md#production-deployment) relies on, each with the review item it comes from. Most ship as they must be. The rest are the deployment's to set. Each value is in the file named, not here.

| Setting | File | In production | Item |
|---|---|---|---|
| `HOST_RUNNER` | `.env` | `1`: the model stages run on the host through `make corpus-hosted`, and the model workers and Dagster stay stopped | C-006, C-073 |
| The seven role models | `.env` | The split above, as `.env.example` ships it | C-051 |
| `LLM_REASONING_EFFORT` | `.env` | `none`, which the writer needs and a model that does not reason is never sent | C-051 |
| `LLM_BASE_URL` | `.env` | One address for every role: a split across Azure resources needs a gateway that routes by model id | C-366 |
| `ASSESSMENT_JUDGE_MODEL` | `.env` | The judge the host runner asks. `make doctor` refuses it unset while `ASSESSMENT_ENABLED` is true | C-006 |
| `APP_DB_PASSWORD` | `.env` | Letters, digits, `-`, `_` and `.`: `make doctor` and `make corpus-hosted` refuse `@ / : # ? %` | C-201 |
| `API_TOKEN` | `.env` | Generated by `make setup`. Every write to the API and every read of its settings carries it. It is shared, so the ports stay on 127.0.0.1 | C-085 |
| `HF_HUB_OFFLINE` | set by `make corpus-hosted` | `1`, over a cache filled once where the Hub is reachable ([above](#pinning-the-encoders)) | C-072 |
| `DOCLING_ARTIFACTS_PATH` | `backend.env` | The prefetched parser weights, where they are not in the cache. Never set and empty | C-072 |
| `EMBEDDING_MODEL_REVISION`, `NLI_MODEL_REVISION`, `QA_MODEL_REVISION` | `backend.env` | As shipped, beside the model ids they pin. Both are fixed | C-117 |
| `LITELLM_LOCAL_MODEL_COST_MAP` | `backend.env` | `true`, as committed | C-088 |
| `SPEND_CAP` | the `make corpus-hosted` command line | A cap in USD for the whole run. With it set, a drain refuses a model litellm cannot price | C-091, C-219 |
| `TOPIC_NUM_TOPICS` | `backend.env` | As shipped (300 a language). The questions grow with the topics: `make estimate` says what a corpus costs | C-024 |
| `QUESTIONS_TYPE_MIX`, `QUESTIONS_RELEASE_TYPES` | `backend.env` | `entity` and `temporal` at 0 until each is calibrated on the production corpus. Entity has no measured defect. Temporal is answered with comparisons where a corpus has no periods | C-176, C-217 |
| `QUESTIONS_RELEASE_DIFFICULTY` | `backend.env` | Unset: the bands measure retrieval spread, not hardness | C-029 |
| `QA_MODEL` | `backend.env` | Empty, until an encoder is calibrated | C-424 |
| `EXTRACTION_DUPLICATE_COSINE` | `backend.env` | As shipped: 0 also stops writing passage embeddings | C-245 |
| `EMBEDDING_MAX_TOKENS` | `backend.env` | Above the corpus's widest table row, checked before ingest | C-278 |
| `POSTGRES_MEMORY` and the other `POSTGRES_*` | `deployment.env` | The production row of [Sizing Postgres](operations.md#sizing-postgres), as shipped | C-011 |
| `PHOENIX_TRACE_RETENTION_DAYS` | `deployment.env` | A retention in days for the traces, which hold every passage a prompt sent | C-103 |

## Precedence

Highest first:

1. A variable given on a `make` command line, for the host process that command runs. It never reaches a running container. `make extract-start EXTRACTION_DUPLICATE_COSINE=0.9` queues the passages, and `extract-worker` drains them under the stored or the file value.
2. A row in `service_settings`, set through the UI, the API or `make settings-set`.
3. The file that declares the setting.

The files stay required. A variable missing from its file stops the service at start-up and names itself, except for these:

| Setting | When absent |
|---|---|
| a stage's own model | follows `LLM_MODEL` |
| `LOG_LEVEL` | falls back to INFO |
| the two pool sizes | fall back to 5 |
| `QUESTIONS_MEETS_SHARE` | reads its shipped value |
| `QUESTIONS_KIND_MIX` | deals `needs_both:5,compound:1` |
| `QUESTIONS_CATEGORIZATIONS` | reads `DEFAULT_CATEGORIZATIONS` in [`question_generation/config.py`](../backend/question_generation/config.py), because its value is JSON and no file here can hold one (see [A JSON value](#a-json-value)) |

Deleting an override row returns a setting to the file, or for these settings to what their absence reads.

## Changing one

Three surfaces change a setting, all through the stage's own `Settings.load`:

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

A worker picks a change up once its queue next runs dry. It reads its settings between drains, not per row, so a drain under way finishes its queue under the old values. A change reaches no stored row, and nothing is requeued.

`make settings SERVICE=<name>` and `make doctor` list, for extraction, topics and questions, how many stored rows were made before a change to a setting that stales that stage. They print the least destructive command that brings the rows in line: the cheaper rebuild the setting's catalogue entry names, or the stage's rerun where none of the changed settings names one.

- The page, the API and `make settings-set` each say when a change stales what a stage produced, and name the stage.
- Where every changed setting has a cheaper rebuild, such as `make extract-revalidate` or `make questions-balance`, the page and the API name that command. Otherwise they say to rerun the stage. `make settings-set` names the same command and says to rerun the stage either way.
- A change made in a file is not dated. It shows only after a restart, as another version.
- A setting that the deployment owns and no stage's output depends on, such as `SPEND_CAP`, is no part of the configuration and lists nothing.

### A JSON value

`QUESTIONS_CATEGORIZATIONS` holds the categorizations of the DataMorgana paper (Filice et al., [*Generating Q&A Benchmarks for RAG Evaluation in Enterprise Settings*](https://aclanthology.org/2025.acl-industry.33/), ACL 2025 Industry Track) as JSON: one categorization object as the paper's Figure 2 prints it, or a list of them. Each answerable question is written as one category of each, and the question records which. A compound question and a follow-up are told none, and their Categories cell in the export is blank. An unanswerable question is told only its kind, where the unanswerable categorization below is set.

A category that a question cannot hold beside the others it was dealt is not told either, and the question records no category of that categorization (see the premise below). Its line in `configs/env/backend.env` is a comment, because bash sources that file and would split a JSON value at its spaces and strip its quotes. Unset, it reads `DEFAULT_CATEGORIZATIONS` in code. `[]` turns categories off.

The default is three of the paper's Table 5 categorizations, in its descriptions without the examples, every category at even odds because the table gives no probabilities. Two are reworded:

- distant-from-document is told to keep the meaning of every term it rewords and coin no word. The paper's "terms completely different" swapped the terms that carry the meaning. As worded, it passed calibration against similar-to-document (keys 58 and 57 of 60, complete 57 and 54, invalid 4 and 11 per 60, conformance 0.80), and Linguistic variation entered the default.
- with-premise asks for a premise in which the asker states, in the first person, a fact of their own situation: something they have, did, bought or plan. It never accepts only the topic, the kind of answer wanted, that they are reading or checking something, or the answer. The paper's wording ("very short premise, where the user reveals their needs or some information") made the asker optional, and a quarter of accepted with-premise questions opened on a label naming a setting.

| Categorization | Categories |
|---|---|
| Phrasing | concise-and-natural, verbose-and-natural |
| Premise | direct, with-premise |
| Linguistic variation | similar-to-document, distant-from-document |

Table 5's Factuality is not among them: whether a question is factoid or open-ended is read off the answer form its type gives it. Its User expertise is opt-in. It describes the expert by what an expert asks, in the material's own terms, where the paper's "a specialized user" invented insider words. Even so worded, its conformance was 0.59 in calibration: it is told on slots whose fact is basic, and asks basic questions in an expert's voice. A categorization left with its one other category would rewrite every question. Listed beside the default's three answerable ones, it reads:

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

Set it on the Questions page's Configuration panel, through the API, or with `settings.run` in the environment `make` loads. Each stores the value whole:

```bash
curl -s -X PATCH localhost:8000/settings/questions \
  -H "X-API-Token: $API_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"values": {"QUESTIONS_CATEGORIZATIONS": "[]"}}'

PYTHONPATH=backend poetry run python -m settings.run --service questions \
  --set 'QUESTIONS_CATEGORIZATIONS=[]'
```

`make settings-set` does not work for a JSON value: it splits `SET` at its spaces, so the value reaches the store in pieces. `make settings-unset SERVICE=questions UNSET=QUESTIONS_CATEGORIZATIONS` goes back to the default in code.

A value is refused before anything is stored, naming the categorization or category at fault, when:

- it is not JSON, or an item of it is not a categorization object;
- a categorization has no `categorization_name`, or one holding an `=`, a comma or a line break;
- two categorizations have the same name;
- a categorization or a category has a key the format does not have;
- a categorization's role is not `question` or `user`;
- a categorization has no categories, or names one category twice;
- a category has no name, or one that is empty or holds an `=`, a comma or a line break, or has no description;
- some categories of a categorization have a probability and others do not, a probability is not between 0 and 1, or the probabilities do not sum to 1;
- a category's `words` is not an object of `min` and `max`, a bound is not a whole number of at least 1, or its minimum is above its maximum;
- a category's form is not `question`, `query` or `premise`;
- a category's `settles` is not `answers`, `refutes` or `silent`, it has one of `settles` and `behaviour` without the other, or a behaviour that is empty;
- some categories of a categorization carry `settles` and others do not, or two categorizations carry it;
- a categorization carrying `settles` has a role other than `question`, or one of its categories a form other than `question`.

#### User categorizations

A categorization describes the question unless it says `"role": "user"`, which makes it describe the person asking. The writer is told the asker in a block of its own, and is told the answer must assume nothing about the asker that the question does not say. A bank might ask in the words of two kinds of account holder, at even odds:

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

A category of `"form": "premise"` is a question that opens on what the asker says about themselves, as the default's with-premise does. A value that holds only a premise writes no phrasing category. List the default's categorizations beside it to keep both, because a value replaces the default whole.

A premise needs words of its own, so it is not told beside a category capping the question's words, such as concise-and-natural, or beside a search query. On concise slots the writer shrank the premise to a label naming a setting. Such a slot is written as no category of the premise's categorization.

A first draft is written once more, with a note asking for the asker's own situation, when its premise either:

- holds none of its language's first- or second-person pronouns and possessives (`_SPEAKING` in `question_generation/generation.py`, German and English); or
- has verbs that only want, try, check or understand (`_ENQUIRING` beside it, read through the infinitive such a verb takes, so "I want to know" is noted and "I want to return a jacket" is not).

The second draft is kept. Neither draft is refused for it. The premise ends where a comma, a colon, a full stop or a dash set off by spaces opens the question. A language with no row is never noted.

#### Search queries

A category is a question asked unless it says `"form": "query"`, which makes it a search query: keywords typed into a box.

- The writer is told the question-mark rule does not apply, and no gate refuses the query for ending without one, when it is written or re-checked. Every other rule holds.
- A search query is not told on a slot that spans two passages, whose keywords cannot say how the two meet. It is not told on a `reason`, `comparison`, `implication` or `temporal` slot either, whose question word is the ask. Such a slot is written as no category of the query's categorization.
- A query bounded to a few words, by a `max` in its `words`, is also read against the `QUESTIONS_ELSEWHERE_PASSAGES` passages nearest it that it does not cite. It is refused as not recoverable where one of them answers it differently.

Table 5's short and long search queries are of form `query`, and neither is dealt unset. The short one was accepted for 30% of its rows in calibration, against 82 to 86% for the natural phrasings on the same slots. The long one, described as keywords and nothing else, with no question word and nothing about the asker, reached 36 accepted rows, under the 40 a category is measured on. A Phrasing that lists them beside the two natural phrasings, set in place of the default's, deals all four at even odds:

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

A category may carry word bounds, `"words": {"min": 10}`, `{"max": 9}` or both, each a whole number of at least 1. The writer is not sent them, and no question is refused for missing them. `make diversity BY=category` reports the share of each category's questions inside them. The report reads the bounds configured when it runs, so a question written under other bounds is counted against the current ones.

The default bounds concise-and-natural to at most 9 words and verbose-and-natural to at least 10, the counts their descriptions name. The search queries above are bounded to at most 6 and at least 7. A `max` has two more effects, whatever `min` is beside it: a premise is not told beside a category carrying one, and a search query carrying one is read once more against the passages it does not cite.

#### Unanswerable kinds

A categorization whose categories all carry `settles` and `behaviour` is the unanswerable one. Its categories are kinds of question with no answer, told only the unanswerable writer. An answerable slot dealt one is told nothing of it. At most one categorization may carry them. A kind is asked as a question: its categorization's role is `question` and every category's form is `question`.

- `settles` is the verdict the settles reading must give over the passages the question cites for the question to be kept: `silent`, `refutes` or `answers`. A `refutes` or an `answers` needs words in those passages behind it.
- The verdict, or `silent`, keeps the question beside the probe, which looks for an answer elsewhere. Any other verdict that answers it refuses it as `answerable_after_all` or `answerable_elsewhere`. `silent` where the kind wants another verdict refuses it as `wrong_type`.
- `behaviour` is what a good reply does: a criterion for a judge or a person, not a reference answer to match. The export's Answer cell of an unanswerable question reads `Expected behaviour: ` and it, blank where none was stored.

The kinds follow UAEval4RAG (Peng et al., [*Unanswerability Evaluation for Retrieval Augmented Generation*](https://aclanthology.org/2025.acl-long.415/), ACL 2025). The behaviours are its Table 11's acceptable responses, modified, one line each (code: [SalesforceAIResearch/Unanswerability_RAGE](https://github.com/SalesforceAIResearch/Unanswerability_RAGE), Apache-2.0).

The default deals unanswerable slots `out-of-corpus` alone, at probability 1. It is the one kind that passed calibration ([measurements](measurements.md#unanswerable-kinds-v050)). The other three are opt-in. `UNANSWERABLE_CATEGORIZATION` in [`question_generation/config.py`](../backend/question_generation/config.py) holds all four. List it in place of the default's own `Unanswerable` entry to deal all four:

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

A value that names no kind is written as before kinds existed: one detail of its fact moved just out of reach, kept only where both readings are silent.

#### Rerunning a stage

A stage's rerun is its `-rerun` target, bar topics, which have none: `make topics-discover` fits them again and carries what a person decided about a topic over to the new topic matching it.

- Rerunning extraction leaves the bridges to `make extract-bridge`.
- Rerunning questions writes only about the facts no accepted question rests on, and judges no stored question again. `make questions-reverify` judges again with the gates that need no model.
- `make questions-rejudge` asks again about every accepted unanswerable question whose `settles` verdict was given under another verifier prompt version. Verifier prompt version 12 changed the round trip's read alone. On a database upgraded to it, the first run costs one `settles` reading per stored accepted unanswerable question, and a second where the cited passages are silent and the passage probe is on.

A fixed setting is the exception: it changes only in its file, with a restart, and no surface reports what the change left stale. After changing `NLP_MODELS`, `NLP_DEFAULT_LANGUAGE` or `NLP_CAPITALISED_NOUNS`, rerun chunking and every stage after it.

Every fact, topic and question records the configuration it was produced under.

## The eight services

Each service configures its own settings and no others.

| Service | Page |
|---|---|
| `ingestion` | Upload |
| `parsing` | Documents |
| `chunking` | Passages |
| `extraction` | Facts |
| `topics` | Topics |
| `questions` | Questions |
| `assessment` | Assessment |
| `platform` (the model, the tokenizer and the language pipelines) | System health |

A stage may name a model of its own: `EXTRACTION_MODEL`, `TOPIC_MODEL` and `QUESTIONS_MODEL`, each meaning `LLM_MODEL` when absent. Four more name a model for one judgement: `EXTRACTION_DIGEST_MODEL`, `QUESTIONS_PHRASING_MODEL`, `QUESTIONS_VERIFIER_MODEL` and `ASSESSMENT_JUDGE_MODEL`.

These eight model settings, `LLM_MODEL` among them, are fixed: the deployment sets them, and they are served read-only and never stored. Three have a container value of their own, which compose sets over the host's: `LLM_MODEL`, `QUESTIONS_VERIFIER_MODEL` and `ASSESSMENT_JUDGE_MODEL`, in the table above. The other five are read from `configs/env/backend.env`. Where one is set, the host and the containers call the same model for it, a hosted one included, and `make doctor` asks them only as the host calls them.

These settings are fixed too, and a settings write refuses every one of them:

- `NLP_MODELS`, `NLP_DEFAULT_LANGUAGE`, `NLP_CAPITALISED_NOUNS` and `WORKER_POLL_SECONDS`;
- `SPEND_CAP`, the pool sizes and `API_ALLOWED_HOSTS`;
- the addresses, `LLM_BASE_URL` among them.

## Where to look for a setting

| Looking for | Read |
|---|---|
| Which model, and where it is served | `.env` for `LLM_MODEL`, the verifier, the judge, their container values and the addresses, and `.env.example` for the provider table and the production split (above). A stage's own model (`EXTRACTION_MODEL`, `EXTRACTION_DIGEST_MODEL`, `TOPIC_MODEL`, `QUESTIONS_MODEL`, `QUESTIONS_PHRASING_MODEL`) is documented, unset, in `configs/env/backend.env` beside that stage's settings, where the host and the containers both read it |
| How the model is called: mode, temperature, timeout, attempts, context window, reasoning | `configs/env/backend.env`, "Extraction" |
| The encoders, the tokenizer, the spaCy pipelines | `configs/env/backend.env`, "Embedding", "Encoders that run in this process" and "Language pipelines" |
| What a fact may be, and the caps on each kind | `configs/env/backend.env`, "Extraction" |
| How many topics, and how they are fitted | `configs/env/backend.env`, "Topic modelling", and [`backend/topic_modelling/`](../backend/topic_modelling/README.md) |
| What a run costs, and what it writes | `configs/env/backend.env`, "Question generation", and [`backend/question_generation/`](../backend/question_generation/README.md) |
| When two questions count as one | `configs/env/backend.env`, `QUESTIONS_DUPLICATE_COSINE` and `QUESTIONS_DUPLICATE_SHARED_COSINE` |
| What each question is written as: the paper's categories | `QUESTIONS_CATEGORIZATIONS`, stored rather than in a file. Its default is `DEFAULT_CATEGORIZATIONS` in [`question_generation/config.py`](../backend/question_generation/config.py). See [A JSON value](#a-json-value) |
| Which of the accepted questions ship | `configs/env/backend.env`, "The balanced release". A question's `difficulty` band is its retrieval spread (how many passages, documents and subjects it rests on, a long answer and a follow-up a point each), not how hard it is to reason about. The workbook names the column "Retrieval spread". `QUESTIONS_RELEASE_DIFFICULTY` draws the release by that spread. It stays unset so that it follows the bands the answerable pool holds: equal thirds take nearly every multi-passage question the pool has |
| Whether the judge runs, and who judges | `.env`. Which artefacts and how many: `configs/env/backend.env` |
| A port, an address, a role name | `configs/env/deployment.env` |
| A password or a key | `.env`, listed in `.env.example`. The provider's: `configs/env/provider.env` |

Most settings in `configs/env/backend.env` carry paragraphs explaining what they do and how their value was chosen. [`settings/catalog.py`](../backend/settings/catalog.py) carries the one-line version that the UI draws its controls from. [measurements.md](measurements.md) says how a default was measured.

## Five settings with constraints

- `PHOENIX_ADMIN_SECRET` needs at least 32 characters including a digit and a lower-case letter. `make doctor` checks all three.
- `PHOENIX_SECRET`, in `.env`, needs at least 32 characters, as its placeholder says. `make setup` generates one. `make doctor` does not check its length.
- `PHOENIX_DEFAULT_ADMIN_INITIAL_PASSWORD` is applied only when Phoenix first creates its admin user. Changing it afterwards means dropping the `phoenix` database.
- `GRAFANA_SECRET_KEY`, in `.env`, encrypts the secrets Grafana stores in its database. compose refuses to start Grafana without it. Changing it is a rotation: [operations.md](operations.md) has the steps.
- `MAX_FILE_SIZE_MB` is the one setting written in two files, because Streamlit reads a static TOML and no env var. `server.maxUploadSize` in `frontend/.streamlit/config.toml` must match it, or the frontend rejects a file before the API sees it and tells the person the wrong limit. A test pins the pair as the two files hold them. The Configuration panel can change `MAX_FILE_SIZE_MB` without a restart, and nothing checks that value against the TOML, so change it only together with `server.maxUploadSize`.

## What is enforced

| Test | Checks |
|---|---|
| `tests/static/test_env_files.py` | One name, one file. Every `${...}` compose interpolates is declared, and one with no fallback is set. Every password and key compose passes is required: `:?`, or `?` for the two S3 keys. `.env.example` holds a placeholder for every secret. The image bakes the pipelines `NLP_MODELS` loads |
| `tests/static/test_settings_documented.py` | Every setting the code reads by its literal name, through a settings reader or `os.environ[...]`, is named in a file that declares it, commented out or not. A read any other way, such as `TRACE_DATABASE`, `RUN_ID` or the pool sizes, is not seen |
| `tests/static/test_language_tables.py` | Every word table keyed by language holds a row for each language `NLP_MODELS` names |
| `tests/static/test_settings_catalogued.py` | Every setting the code in `backend/`, `frontend/` and `telemetry/` reads by its literal name is described in `settings/catalog.py`, bar the few the test lists as configured by no page, and every description is read. `orchestration/` is not scanned, so `INGESTION_OPEN` has no description and no panel |
| `tests/static/test_doc_links.py` | Every relative link in a README resolves |

Two settings a person may set are declared in no file, and neither settings test sees them, because each is read through a constant. `TRACE_DATABASE` puts a span on every SQL statement (see [`telemetry/README.md`](../telemetry/README.md)). `RUN_ID` names a run (see the same page and [`backend/settings/README.md`](../backend/settings/README.md)).
