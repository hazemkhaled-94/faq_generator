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

## The go-live split

Go-live runs the model stages on the host, through `make corpus-hosted`, with
`HOST_RUNNER` set to `1` in `.env` and the model workers stopped. The split of models
is `.env`'s too, and `.env.example` ships it:

| Role | Setting | Model |
|---|---|---|
| Writer | `QUESTIONS_MODEL` | `azure/gpt-5.6-sol` |
| Passage reader | `EXTRACTION_MODEL` | `azure/gpt-5.4` |
| Phrasing judge | `QUESTIONS_PHRASING_MODEL` | `azure/gpt-5.4` |
| Digest reader | `EXTRACTION_DIGEST_MODEL` | `azure/gpt-4o` |
| Assessment judge | `ASSESSMENT_JUDGE_MODEL` | `azure/gpt-4o` |
| Verifier | `QUESTIONS_VERIFIER_MODEL` | `azure/gpt-4.1` |
| Topic namer | `TOPIC_MODEL` | `azure/gpt-4.1` |

`LLM_MODEL` is the model a role follows when its own setting is unset (the
judge follows nothing), and `LLM_REASONING_EFFORT=none` is the one effort the
split needs: a hosted model that does not reason is sent none of it.
`backend.env` names no role model, so a role you leave unset follows `LLM_MODEL`
and never the project's default.

The split has one address: every role model is reached through `LLM_BASE_URL`. A split
across more than one Azure resource, each with its own endpoint and key, needs
a gateway in front of them that routes by model id; litellm does not pick an
endpoint per role.

Every drain logs the split it resolved as one line, `split: writer=... effort=...`,
before it claims a row, and `make doctor` checks it. With `HOST_RUNNER=1` a
drain and the doctor refuse a role that resolves to an Ollama model, and a
judge left unset while `ASSESSMENT_ENABLED` is true, naming the role and the
setting that moves it. The containers keep calling Ollama by design: `.env`'s
role models never reach them, and compose gives them `LLM_CONTAINER_MODEL`.

### Prices follow the installed litellm

`LITELLM_LOCAL_MODEL_COST_MAP=true` is committed in `backend.env`, so litellm
reads the model list of the installed package and never fetches one at import.
The prices `make spend` and `SPEND_CAP` count at, and which hosted models are
known not to reason (and so are sent no `LLM_REASONING_EFFORT`), therefore
change only when the litellm lock does. A model litellm does not list is
unpriced: a drain with `SPEND_CAP` set refuses it.

## Pinning the encoders

`EMBEDDING_MODEL`, `NLI_MODEL` and `QA_MODEL` are Hugging Face repositories, and
a bare repository id is whatever its default branch holds the day a worker
first loads it: a push there changes passages and scores under the same
settings. Each has a commit beside it, `EMBEDDING_MODEL_REVISION`,
`NLI_MODEL_REVISION` and `QA_MODEL_REVISION`, and every load (the embedder, the
tokenizer chunking sizes a passage with, the NLI pipeline, the QA head) passes
it. `backend.env` ships the commits in the build's cache; `QA_MODEL_REVISION` is
empty while `QA_MODEL` is, and a `QA_MODEL` with none is refused at its first
load. The three commits are fixed, and so are the three model ids beside them:
neither is offered on the Configuration page, a model and its commit change
together, in the file, and a row stored for one of the model ids before this
release is refused at every stage's build, naming its pin and the `DELETE` that
removes it.

With `HF_HUB_OFFLINE=1`, which `make corpus-hosted` sets, nothing is fetched, so
`make doctor` reads the cache first and names what is missing: each encoder at
its pinned commit, with its config and a weights file (`model.safetensors`,
`pytorch_model.bin` or a shard index; a snapshot a tokenizer load left holds
neither), and Docling's weights, in `DOCLING_ARTIFACTS_PATH` where that names a
folder and in the cache otherwise. It fails on what is missing with
`HF_HUB_OFFLINE=1` or `HOST_RUNNER=1`, and warns otherwise, where a first load
fetches it; `make corpus-hosted` checks it with the Hub off before it detaches. `DOCLING_ARTIFACTS_PATH` set and
empty is refused, because Docling reads it as the working directory. Fill the
cache once, where the Hub is reachable, before go-live: `make docling-weights`
for the converter, and one run of the chunk and question stages (or the
`huggingface-cli download <repo> --revision <commit>` of each) for the encoders.

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
which reads its shipped value when absent; `QUESTIONS_KIND_MIX`, which deals
`needs_both:5,compound:1` when absent; and `QUESTIONS_CATEGORIZATIONS`,
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
settings again between drains, not per row, so a drain under way works the
rest of its queue under the old values. A change reaches no stored row:
nothing is requeued, and `make settings SERVICE=<name>` and `make doctor` list,
for extraction, topics and questions, how many stored rows were made before a
setting that stales that stage was changed, with the least destructive command
that brings them in line (the cheaper rebuild its catalogue entry names, and
the stage's rerun only where one of the changed settings names none). A
change made in a file is not dated, so it shows only after a restart as
another version; a setting the deployment owns and no stage's output depends
on, such as `SPEND_CAP`, is no part of the configuration and lists nothing. If the change stales what a stage already produced, the surface you used says so
and names the stage. Where every setting changed that stales something has a
cheaper rebuild in its catalogue entry, such as `make extract-revalidate` or
`make questions-balance`, the page and the API name that command; otherwise
they say to rerun the stage. `make settings-set` names the same command and
says to rerun the stage either way.

### A JSON value

`QUESTIONS_CATEGORIZATIONS` holds the categorizations of the DataMorgana paper
(Filice et al., [*Generating Q&A Benchmarks for RAG Evaluation in Enterprise
Settings*](https://aclanthology.org/2025.acl-industry.33/), ACL 2025 Industry Track)
as JSON: one categorization object as the paper's Figure 2 prints it, or a list
of them. Each answerable question is written as one category of each, and the
question records which; a compound question and a follow-up are told none,
and their Categories cell in the export is blank. An unanswerable question is
told only its kind, where the unanswerable categorization below is set, and
none otherwise. A
category a question cannot hold beside the others it was dealt is not told
either, and the question records no category of that categorization: see
the premise below. Its line in `configs/env/backend.env` is a comment,
because bash sources that file and would split a JSON value at its spaces and
strip its quotes. Unset, it reads `DEFAULT_CATEGORIZATIONS` in code; `[]`
turns categories off.

The default is three of the paper's Table 5 categorizations, in its
descriptions without the examples, every category at even odds because the
table gives no probabilities. Two are reworded. distant-from-document is
told to keep the meaning of every term it rewords and coin no word, where
the paper's "terms completely different" swapped the ones that carry the
meaning; so worded it passed calibration against similar-to-document
(keys 58 and 57 of 60, complete 57 and 54, invalid 4 and 11 per 60,
conformance 0.80), and Linguistic variation entered the default. And
with-premise is reworded: the paper's
"very short premise, where the user reveals their needs or some information"
made the asker optional, and a quarter of accepted with-premise questions
opened on a label naming a setting. It now asks for a premise in which the
asker states, in the first person, a fact of their own situation, something
they have, did, bought or plan, and never only the topic, the kind of answer
wanted or that they are reading or checking something, nor the answer:

| Categorization | Categories |
|---|---|
| Phrasing | concise-and-natural, verbose-and-natural |
| Premise | direct, with-premise |
| Linguistic variation | similar-to-document, distant-from-document |

Table 5's Factuality is not among them: whether a question is factoid or
open-ended is read off the answer form its type gives it. Its User expertise
is not either, and is there to opt into, the expert described by what an
expert asks, in the material's own terms, where the paper's "a specialized
user" invented insider words. Even so worded its conformance was 0.59 in
calibration: it is told on slots whose fact is basic, and asks basic
questions in an expert's voice. A categorization left with its one other
category would rewrite every question. Listed beside the default's three
answerable ones, it reads:

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
reaches the store in pieces. A value is refused before anything is stored,
naming the categorization or category at fault, when:

- it is not JSON, or an item of it is not a categorization object;
- a categorization has no `categorization_name`, or one holding an `=`, a
  comma or a line break;
- two categorizations have the same name;
- a categorization or a category has a key the format does not have;
- a categorization's role is not `question` or `user`;
- a categorization has no categories, or names one category twice;
- a category has no name, or one that is empty or holds an `=`, a comma or a
  line break, or has no description;
- some categories of a categorization have a probability and others do not,
  a probability is not between 0 and 1, or the probabilities do not sum to 1;
- a category's `words` is not an object of `min` and `max`, a bound is not a
  whole number of at least 1, or its minimum is above its maximum;
- a category's form is not `question`, `query` or `premise`.
- a category's `settles` is not `answers`, `refutes` or `silent`, it has
  one of `settles` and `behaviour` without the other, or a behaviour that
  is empty;
- some categories of a categorization carry `settles` and others do not, or
  two categorizations carry it;
- a categorization carrying `settles` has a role other than `question`, or
  one of its categories a form other than `question`.

`make settings-unset SERVICE=questions UNSET=QUESTIONS_CATEGORIZATIONS` goes
back to the default in code.

A categorization describes the question unless it says `"role": "user"`,
which makes it describe the person asking. The writer is told the asker in a
block of its own and is told the answer must assume nothing about them that
the question does not say. A bank might ask in the words of two kinds of
customer, at even odds:

```json
[
  {
    "categorization_name": "Customer",
    "role": "user",
    "categories": [
      {"name": "account-holder", "description": "a customer who has held a current account for years and knows its terms."},
      {"name": "first-time", "description": "somebody opening their first account, who knows none of the bank's terms."}
    ]
  }
]
```

A category of `"form": "premise"` is a question opening on what the asker
says about themselves, as the default's with-premise is. A premise needs
words of its own, so it is not told beside a category capping the question's
words, such as concise-and-natural, nor beside a search query: on concise
slots the writer shrank it to a label naming a setting. Such a slot is
written as no category of the premise's categorization. A first draft whose
premise holds none of its language's first- or second-person pronouns and
possessives (`_SPEAKING` in `question_generation/generation.py`, German and
English), or whose verbs only want, try, check or understand (`_ENQUIRING`
beside it, read through the infinitive such a verb takes, so "I want to
know" is noted and "I want to return a jacket" is not), is written once
more, with a note asking for the asker's own situation, and the second draft
is kept; neither is refused for it. The
premise ends where a comma, a colon, a full stop or a dash set off by spaces
opens the question, and a language with no row is never noted.

A value replaces the default whole, so a value holding only this one writes
no phrasing category: list the default's categorizations beside it to keep
both.

A category is a question asked unless it says `"form": "query"`, which
makes it a search query: keywords typed into a box. The writer is told the
question-mark rule does not apply to it, and no gate refuses it for ending
without one, when it is written or when it is re-checked; every other rule
holds. A search query is not told on a slot that spans two passages, whose
keywords cannot say how the two meet, nor on a `reason`, `comparison`,
`implication` or `temporal` slot, whose question word is the ask: such a slot
is written as no category of the query's categorization. A query bounded to
a few words, by a `max` in its `words`, is also read against the
`QUESTIONS_ELSEWHERE_PASSAGES` passages nearest it that it does not cite, and
is refused as not recoverable where one of them answers it differently. Table
5's short and long search queries are of form `query`, and neither is dealt
unset. The short one was accepted for 30% of its rows in calibration, against
82-86% for the natural phrasings on the same slots. The long one, described
as keywords and nothing else, with no question word and nothing about the
asker, reached 36 accepted rows, under the 40 a category is measured on. A Phrasing listing them
beside the two natural phrasings, set in place of the default's, deals all
four at even odds:

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

A category may also carry word bounds, `"words": {"min": 10}`, `{"max": 9}`
or both, each a whole number of at least 1. The writer is not sent them, no
question is refused for missing them, and `make diversity BY=category`
reports the share of each category's questions inside them.
The default bounds concise-and-natural to at most 9 words and
verbose-and-natural to at least 10, the counts their descriptions name; the
search queries above are bounded to at most 6 and at least 7 the same way. The
report reads the bounds configured when it runs, so a question written under
other bounds is counted against today's. A `max` does two things besides,
whatever the `min` beside it: a premise is not told beside a category
carrying one, and a search query carrying one is read once more against the
passages it does not cite and is refused as not recoverable where one of
them answers it differently.

A categorization whose categories all carry `settles` and `behaviour` is
the **unanswerable** one: its categories are kinds of question with no
answer, told only the unanswerable writer, and an answerable slot dealt one
is told nothing of it. At most one categorization may carry them. `settles`
is the verdict the settles reading must give over the passages the question
cites for the question to be kept, `silent`, `refutes` or `answers`, a
`refutes` or an `answers` only with words those passages hold behind it.
Beside the probe, which looks for an answer elsewhere, that verdict or
`silent` keeps it. Any other verdict that answers it refuses it as
`answerable_after_all` or `answerable_elsewhere`, as before; `silent` where
the kind wants another refuses it as `wrong_type`. A kind is asked as a
question: its categorization's role is `question` and every category's form
is `question`. `behaviour` is what a good
reply to it does, a criterion for a judge or a person and not a reference
answer to match; the export's Answer cell of an unanswerable question reads
`Expected behaviour: ` and it, blank where none was stored. The kinds follow UAEval4RAG (Peng et al., [*Unanswerability
Evaluation for Retrieval Augmented Generation*](https://aclanthology.org/2025.acl-long.415/),
ACL 2025), its behaviours its Table 11's acceptable responses, modified, one
line each (code: [SalesforceAIResearch/Unanswerability_RAGE](https://github.com/SalesforceAIResearch/Unanswerability_RAGE),
Apache-2.0). The default deals unanswerable slots `out-of-corpus` alone, at
probability 1: it is the perturbation every unanswerable slot was written as,
and the one kind that passed calibration ([measurements](measurements.md#unanswerable-kinds-v050)).
The other three are opt-in: `UNANSWERABLE_CATEGORIZATION` in
[`question_generation/config.py`](../backend/question_generation/config.py)
holds all four, listed in place of the default's own `Unanswerable` entry:

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

Unset, an unanswerable question is written as the out-of-corpus kind alone,
the one kind that passed calibration; list all four to opt into the other
three. Where a value names no kind, it is written as before kinds: one detail
of its fact moved just out of reach, kept only where both readings are silent.

A stage's rerun is its `-rerun` target, bar topics, which have none:
`make topics-discover` fits them again and carries what a person decided
about a topic over to the new topic matching it. Rerunning extraction leaves
the bridges to `make extract-bridge`. Rerunning questions writes only about
the facts no accepted question rests on and judges no stored question again,
which `make questions-reverify` does for the gates that need no model.
`make questions-rejudge` asks again about every accepted unanswerable
question whose `settles` verdict was given under another verifier prompt
version, and v0.4.3 moved that version from 6 to 12 for the round trip's
read alone: on a database upgraded to it, its first run costs one `settles`
reading per stored accepted unanswerable question, and a second where the
cited passages are silent and the passage probe is on.

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
and `make doctor` asks them only as the host calls them. The four language and poll settings
(`NLP_MODELS`, `NLP_DEFAULT_LANGUAGE`, `NLP_CAPITALISED_NOUNS`,
`WORKER_POLL_SECONDS`), `SPEND_CAP`, the pool sizes, `API_ALLOWED_HOSTS` and the addresses,
`LLM_BASE_URL` among them, are fixed too. A settings write refuses every one
of them.

## Where to look for a setting

| Looking for | Read |
|---|---|
| Which model, and where it is served | `.env` for `LLM_MODEL`, the verifier, the judge, their container values and the addresses, and `.env.example` for the provider table and the go-live split (above); a stage's own model (`EXTRACTION_MODEL`, `EXTRACTION_DIGEST_MODEL`, `TOPIC_MODEL`, `QUESTIONS_MODEL`, `QUESTIONS_PHRASING_MODEL`) is documented, unset, in `configs/env/backend.env`, beside that stage's settings, where the host and the containers both read it |
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