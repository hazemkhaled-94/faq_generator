# Make commands

Every target, grouped. A host target and the backend's containers read
`configs/env/backend.env`, so a tuning value set there reaches both. The
model does not: see
[Configuration and the container engine](#configuration-and-the-container-engine).

```bash
make help            # or just `make`
make help | grep -i topic
```

`help` reads the Makefile itself: a target's group is the section banner it
sits below and its description is the first sentence of the comment directly
above it. A target with no comment directly above it is not listed. This page
is the long form.

## First run

| Target | Does |
|---|---|
| `make setup` | Write `.env` and `configs/env/provider.env`, and fill in every placeholder |
| `make install` | The Python dependencies, the spaCy pipelines and Docling's weights |
| `make doctor` | Check the tools and the configuration, compare the settings the api serves with the checkout's (a warning when the api is down), the model split, the stored settings against the catalogue, and the pinned models and Docling's weights in the cache, failing on one missing or holding no weights with `HF_HUB_OFFLINE=1` or `HOST_RUNNER=1` and warning otherwise, then ask every model one question. Warns when the checkout or `ENV_FILE` sits in a synced folder, and fails on an `APP_DB_PASSWORD` a connection string cannot hold, and print the archive's estimated rows and size (`python -m archive.run --size`) |
| `make dev` | `make install` first, then certificates, every service, the schema and the Grafana grants |
| `make upgrade` | Take a deployment to this checkout's code: check the engine has `UPGRADE_FREE_GB` free (20), build, prune the images the build orphaned, stop the workers, `make schema`, `make up`; stops at the first step that fails |

`setup` is safe to run twice: it replaces `change_me_*` placeholders and
nothing else. It gives one secret per distinct placeholder and substitutes it
everywhere that placeholder appears.

`doctor` ends with a real call to `LLM_MODEL`, as the host calls it, so an
unknown model id, an unreachable address or a stale credential fails here
rather than on the first passage of a run:

```text
  ok       podman
  ok       poetry
  ok       configs/env/provider.env
  ok       .env
  ok       configs/env/deployment.env
  -        compose reads both: make passes them, a bare podman compose needs
             export COMPOSE_ENV_FILES=configs/env/deployment.env,.env
  ok       no placeholder passwords
  ok       PHOENIX_ADMIN_SECRET
  ok       containers call <LLM_CONTAINER_MODEL> at <OLLAMA_CONTAINER_URL>

Asking <LLM_MODEL> one question, as the host calls it...
```

The verifier, the judge and the containers' model are not called here: each
is first called at its own stage's preflight. A container may call only
Ollama: `doctor` fails when `OLLAMA_CONTAINER_URL` or `LLM_CONTAINER_MODEL`
is unset, or when `LLM_CONTAINER_MODEL` (or a set
`QUESTIONS_VERIFIER_CONTAINER_MODEL`) does not start with `ollama`.

## The short list

| Target | Does |
|---|---|
| `make all` | Bring the stack up, wait for Dagster to list the corpus job, and launch it. The container workers drain every stage but the topic fit, which Fit all on the Topics page asks for |
| `make corpus` | Every stage, drained on the host in order, stopping at the first drain that exits non-zero (3 a failed row, 75 a drain that stopped itself). Names the database first, the one `APP_DB_NAME=` on its command line gives or else the files', and gives every drain that name, `HF_HUB_OFFLINE=1` and one spend ledger, so `SPEND_CAP` holds for the whole run and not for each drain. The topics are fitted between extraction and the bridge pass only when a language holds passages and no topic or its topics no longer fit them, and the run stops if a language still has none; the bridge pass for the topics holding none follows, then the release draw and the judge. A stage whose container worker runs (`parse-worker`, `chunk-worker`, `extract-worker`, `question-worker`, `assess-worker`) is waited for until that worker has emptied its queue, not drained beside it, which is how the parse and chunk workers the go-live `make up` starts are met; the digest and bridge steps still refuse beside `extract-worker` and the topic fit beside `topic-worker`, so stop those two in development first. `RESUME=1` keeps the ledger and first returns every stage's failed rows to the queue, which is what a run killed mid-row left. Incremental up to the release: a stage already done queues and claims nothing, but the release draw runs again over every accepted question and asks the verifier about each released question and its nearest released neighbour, in up to three rounds that each draw again over the twins found, and a fourth that only drops the twins the last draw still holds, because those verdicts are not stored; it stops before the judge when the verifier does not answer |
| `make corpus-hosted` | `make corpus` on the host, detached and supervised: `scripts/corpus-hosted.sh` runs it in a process group of its own, recorded with its database in `logs/corpus-hosted.pid`, its log in `logs/corpus-hosted.log`; a second start is refused while a member of that group lives, and a start after a run that ended other than finished (a stop at `SPEND_CAP`, a signal, failed rows, a crash) resumes it on the database it records, keeping its spend; `RESET=1` starts a fresh run instead. The go-live profile's runner, and it needs `HOST_RUNNER=1`: it refuses without it, and a drain refuses a model role that is unset or resolves to Ollama. `make corpus-hosted SPEND_CAP=50` stops the whole run at USD 50. See [Go-live host](operations.md#go-live-host) |
| `make corpus-hosted-stop` | Stop the hosted run: TERM to its whole process group, so the drain in hand finishes its row or gives it back and exits 75, then KILL to what is left after 300 seconds, a model stage's grace and its give-back. The spend ledger and the pid file are kept, so the next `make corpus-hosted` resumes it |
| `make pipeline-status` | Where the corpus has got to, every stage in one call |
| `make services` | Every container, whether it is listening, and where to open it |
| `make open` | The same, and open the application |
| `make review` | Push a sample of facts and questions, and every topic label, to Argilla |
| `make pull` | Pull every decision made there back into the database |

`make auto` hands the whole thing to Dagster — see
[Orchestration](#orchestration).

## Configuration and the container engine

Targets read `configs/env/backend.env`, `configs/env/deployment.env`,
`configs/env/provider.env` then `.env`, and a later file wins; the review and
evaluation targets and `dagster-dev` also read `review.env`,
`evaluation.env` or `orchestration.env` after `deployment.env`. The api and
the six workers take only `backend.env` whole, and `provider.env` where they
call a model; compose reads `deployment.env` and `.env` only for the values
`compose.yaml` names.

`.env` is `ENV_FILE`, which is `.env` beside the Makefile unless you name
another: `make up ENV_FILE=/etc/qa/secrets.env`, or export it. A relative path
is read from the checkout. See [Go-live host](operations.md#go-live-host) for
why the secrets leave a synced checkout.

The model is named apart for the containers: a container calls
`LLM_CONTAINER_MODEL` at `OLLAMA_CONTAINER_URL`, its verifier is
`QUESTIONS_VERIFIER_CONTAINER_MODEL` and its judge
`ASSESSMENT_JUDGE_CONTAINER_MODEL`, never `.env`'s `LLM_MODEL`,
`QUESTIONS_VERIFIER_MODEL` or `ASSESSMENT_JUDGE_MODEL`.

A setting stored with `make settings-set` or a service's Configuration panel
beats every file, on the host and in the containers, until
`make settings-unset` removes it. A variable given on the command line beats
them all, the stored setting included:

```bash
make topics-discover TOPIC_PASSES=20
```

The Makefile re-applies command-line overrides after sourcing the files,
because sourcing would otherwise overwrite them, and before it builds the
addresses out of them, so `make schema POSTGRES_PORT=5433` connects to that
port.

The Makefile invokes `podman compose` and `podman`. For Docker, set both:

```bash
make CONTAINER=docker COMPOSE="docker compose" up
```

`CONTAINER` is the engine itself: `doctor` checks for it, `prune` (and so
`down`) runs it, and `lock` uses it for a build and a run compose has no
equivalent of.

## Starting and stopping

| Target | Does |
|---|---|
| `make dev` | `make install` first (poetry install, the spaCy downloads and Docling's weights, which need the network), then certificates, every service, wait for PostgreSQL, create the schema, then the grants `make up` makes. Use `make up` to start an installed stack |
| `make install` | `make install-python`, then `make docling-weights` |
| `make install-python` | Dependencies and the spaCy pipelines `NLP_MODELS` names, on the host alone. What CI's setup runs |
| `make docling-weights` | Download Docling's weights into the `models` volume parse-worker reads offline. Needs the container engine; fetches nothing already cached |
| `make up` | Start services, then grant Grafana's reader the five Phoenix tables the run dashboard queries. It waits up to 150 seconds for Phoenix to make them and then grants anyway, so a slow first boot fails here with the stack up; run `make grafana-grants` again |
| `make grafana-grants` | Those grants alone. Safe to run again |
| `make down` | Stop services, keep data, and remove dangling images |
| `make down-volumes` | Stop services and **delete all data** |
| `make certs` | Generate the TLS certificates Elasticsearch needs. Stops at a failed step, and skips only once `certs/elasticsearch.crt` is written |
| `make prune` | Remove dangling container images |

## Logs

| Target | Follows |
|---|---|
| `make logs` | All logs |
| `make logs-api` | The API |
| `make logs-frontend` | The frontend |
| `make logs-orchestration` | The Dagster webserver and daemon |
| `make logs-shipper` | The log shipper, when Grafana shows nothing |
| `make logs-retention` | Not a follow: how long Elasticsearch keeps them. **Run once** |
| `make logs-prune` | Not a follow: delete the log files nothing has written to for `LOGS_KEEP_DAYS`, on the `logs` volume and in `./logs`. Fails when the api, through which it reaches the volume, does not answer |
| `make logs-wipe` | Not a follow: delete this database's log lines (every line carries a `db` field), and leave the shared log files. `ALL_DATABASES=1` deletes every `qa-logs*` data stream and empties every log file, which the running services go on writing. Stops unless Elasticsearch acknowledges the delete or holds no stream. What `make wipe` runs |

```bash
make logs-retention LOGS_RETENTION_DAYS=90
make logs-prune LOGS_KEEP_DAYS=7
```

## The corpus as one thing

The same three verbs as below, over every stage at once, through the API.
After a model outage the failures are spread over five queues, and visiting
five of them is five chances to miss one.

| Target | Does |
|---|---|
| `make pipeline-status` | Every stage's queue, the run in flight, and what is set to start one |
| `make pipeline-stop` | Take back everything queued, in every stage, and stop the run behind it |
| `make pipeline-retry` | Return every stage's failures to the queue |

There is no `pipeline-start`: `make pipeline` is the better one for a
terminal, because it starts each stage **and waits for it to drain** before
the next, which is the whole difficulty. It and the Run button ask Dagster to
hold that wait while the container workers drain; `make corpus` holds it in
the shell and drains on the host, and a stage whose container worker runs is
waited for until that worker has emptied its queue instead (`WAIT=1`, which
`make corpus` gives every drain): the go-live `make up` starts the parse and
chunk workers. On the go-live profile (`HOST_RUNNER=1`) there is no
orchestrator: `make all`, `make pipeline` and `make auto` refuse, naming
`make corpus-hosted`, and so do `POST /pipeline/run`, `POST /pipeline/start`
and `PUT /pipeline/automation`, with a 409.

## The six verbs every stage answers

Each but the drain is the same operation as the stage's route of that name,
`make parse-start` as `POST /parsing/start`; no route drains. See
[`backend/stages/`](../backend/stages/README.md).

| | Parsing | Chunking | Extraction | Questions | Assessment |
|---|---|---|---|---|---|
| queue what was never asked for | `parse-start` | `chunk-start` | `extract-start` | `questions-start` | `assess-start` |
| drain here, in the foreground | `parse` | `chunk` | `extract` | `questions` | `assess` |
| show the queue | `parse-status` | `chunk-status` | `extract-status` | `questions-status` | `assess-status` |
| take back what has not begun | `parse-stop` | `chunk-stop` | `extract-stop` | `questions-stop` | `assess-stop` |
| return failures to the queue | `parse-retry` | `chunk-retry` | `extract-retry` | `questions-retry` | `assess-retry` |
| queue everything again | `parse-rerun` | `chunk-rerun` | `extract-rerun` | `questions-rerun` | `assess-rerun` |

A drain here — the bare target, every `-rerun` and `topics-discover` —
**refuses while that stage's container worker is running**, and prints the
`podman compose … stop <worker>` that stops it. `WAIT=1` on a bare drain
(`parse`, `chunk`, `extract`, `questions`, `assess`) waits for that worker to
empty the queue instead, polling its counts every `WORKER_POLL_SECONDS`, and
exits 3 if it failed rows meanwhile; `make corpus` runs its drains so. With no container engine
answering, or the stack down, it drains as before. `extract-dedup`,
`extract-revalidate` and `extract-recap`, which rewrite stored verdicts
across the corpus, refuse beside `extract-worker` the same way, and so do
`delete` and `delete-derived`, before they delete anything. `questions-reclaim`
and `assess-reclaim` refuse beside their worker when they are not narrowed.

`assess-start` also **enrols**: nothing upstream creates an assessment, so it
creates the rows as well as queuing them.

`chunk-start` and `chunk-rerun` queue **only the documents parsing has
finished**. A document exists from the moment it is uploaded, so without that
guard a start over a corpus half way through parsing queued the other half
and failed every row of it on a parsed form that was not there yet. It is the
only stage that needs it: a passage exists because chunking made it, and a
topic because a fit did.

Topic modelling has no `start` and no `rerun`: a fit is all-or-nothing over
one vocabulary.

| Target | Does |
|---|---|
| `make topics-discover` | Ask for a fit over the whole corpus, and run it. The corpus job does not; `make corpus` runs it as `make topics-discover ENSURE=1`, which fits only when a language holds passages and no topic or its topics are stale, and otherwise drains a fit already queued, as the `topics-retry` of `make corpus RESUME=1` leaves one, rather than leave it pending |
| `make topics` | Run any queued fit here, in the foreground |
| `make topics-status` | The topics held, any queued fit, and how many passages are in no topic |
| `make topics-stop` | Withdraw a queued fit |
| `make topics-retry` | Return a failed fit to the queue |
| `make topics-visualise` | Write each language's stored pyLDAvis page to `./topics/` |
| `make topics-render` | Redraw those pages from the stored models, without re-fitting. `CODE=de` for one |
| `make topics-name` | Name the topics a fit left unnamed, off the stored fit and without re-fitting. A topic with a name is left as it is |
| `make topics-delete` | Delete every topic and membership, any fit queued or running, and the judge's verdicts on the topics. The figures and models go to the archive. Refuses unless `CONFIRM` names the database |

### Narrowing to one item

Any verb but the bare drain narrows with `SHA`, `PASSAGE` or `TOPIC`, and
`SHA` wins over `PASSAGE` over `TOPIC`:

```bash
make parse-start SHA=<sha256>     # queue one document for parsing
make chunk-rerun SHA=<sha256>     # rebuild one document's passages
make extract-start SHA=<sha256>   # queue every passage of one document
make extract-retry PASSAGE=<id>   # return one failed passage to the queue
make questions-start TOPIC=<id>   # queue one topic for question generation
```

Parsing and chunking narrow to a document, extraction to a document or a
passage, question generation to a topic, assessment to a kind through
`ONLY=--only\ kind=<kind>`, topic modelling to nothing. `questions-balance`
always draws over every topic.

A bare drain is never narrowed: it takes the whole queue. So a narrowed
`-rerun` refuses while any row outside it is queued; take those back with
`make <stage>-stop` first.

## Replaying a stage without redoing it

Re-derive what a stage computed over rows already stored, without the
expensive part:

| Target | Does |
|---|---|
| `make extract-revalidate` | Judge every stored fact again. A refusal it validates meets the dedup gate and the cap, as one read in flight does. No model call |
| `make chunk-revocabulary` | Re-read language and vocabulary. `passages.language` and `passages.lemmas` change, and `facts.language` moves with the passage the fact opens on |
| `make questions-reverify` | Put every stored question through the gates that need no model |
| `make questions-rescore` | Rewrite every stored question's scopes and difficulty from what it cites now. For after the `extract-dedup` that takes out an earlier version's fold citations (the v0.2.2 upgrade), before `questions-reverify`; and after a topic refit that changed the topics, where it follows `questions-reverify`, which has first caught any `source_changed`. Not straight after a re-extraction or a deletion, where it would hide a question that lost a fact from the `source_changed` check |
| `make extract-recap` | Re-apply the atomic cap `EXTRACTION_MIN_OTHER_SHARE` works out to, never below a passage's own sentences and list items |
| `make extract-dedup` | Re-decide every `duplicate` refusal under today's rule, and take out the citations a refusal added to the fact it repeated. The passages of the refusals given back, and no others, are then re-judged and re-capped. No model call |
| `make extract-embed` | Write vectors onto passages and facts already stored. Does not apply the dedup gate |
| `make extract-digests` | Give a summary and an outline to the passages that finished without them because the digest model failed or its provider refused them, and to those above `EXTRACTION_DIGEST_MIN_CHARS` that hold none, which is how a lowered floor reaches stored passages. Calls the digest model once per such passage and writes nothing else; a passage that fails again keeps its note. `make corpus` runs it after `extract` |
| `make extract-bridge` | Read each topic's passage groups for claims spanning passages. Asks the model first and deletes nothing if it does not answer. Refuses while an accepted question cites a bridge it would replace; `FORCE=1` replaces them anyway; `MISSING=1` deletes nothing and reads only the topics holding no bridge yet, which is how `make corpus` runs it |
| `make confidence-recalibrate` | Take every stored margin again after a change to `QUESTIONS_DUPLICATE_FLOOR` or `EXTRACTION_DUPLICATE_FLOOR`. No model call, and no verdict moves. Written in batches of 300: a batch deadlocked with another writer is written once more, and deadlocked again fails the run naming its rows; run it again |

`chunk-revocabulary` takes `SHA`; `extract-revalidate`, `extract-recap`,
`extract-dedup`, `extract-embed` and `extract-bridge` take `SHA` or `PASSAGE`;
`questions-reverify`, `questions-rescore` and `questions-rejudge` take
`TOPIC`.

The alternative is destructive: `extract-rerun` calls the model again over
the whole corpus, and `chunk-rerun` replaces every passage of a document the
new cut changes, along with the facts drawn from them, keeping the passages
it cuts again unchanged. A fact `extract-rerun` reads again word for word
keeps its id, its embedding and its questions. A question resting on what a
rerun replaces is rejected as `source_changed` and kept, never deleted, and
its follow-ups leave the release. Both therefore refuse, naming how many
released, accepted and reviewed questions rest on what they would replace,
unless `FORCE=1` is given (the routes take `force=true`; they answer 409
`questions_rest_on_it` without it). Without `SHA`, or `PASSAGE` for
extraction, both also refuse unless `CONFIRM` names the database.

## Questions

| Target | Does |
|---|---|
| `make questions-balance` | Draw the balanced release out of what was accepted, with the verifier judging which released questions want one answer. **Calls the verifier model**, about once per released question |
| `make questions-export` | Write the questions a filter selects to an `.xlsx` |
| `make questions-reverify` | Re-check stored questions; no model call |
| `make questions-rejudge` | Ask the verifier whether the passages settle each accepted unanswerable question, and reject those they do. **Calls the verifier model**; takes `TOPIC` |
| `make questions-rescore` | Rewrite stored scopes and difficulty from current citations: after the upgrade's `extract-dedup`, and after a topic refit that changed the topics, once `questions-reverify` has run; no model call |
| `make questions-runs` | The 20 newest runs, newest first, and how many questions each wrote |
| `make questions-diff` | Two runs side by side, on the gate that stopped each |
| `make questions-reclaim` | Return a topic a dead worker still holds. **Narrow it** |

```bash
make questions RUN_ID=b-gemma4-12b
make questions-diff RUNS="a-gpt-4.1 b-gemma4-12b"
```

### Getting the dataset out

`OUT` names the file, `questions.xlsx` unless given, which it overwrites, and
`FILTER` takes the same narrowing the Questions page and `GET /questions` do.
**There is no default scope** — ask for nothing and you get everything,
rejected rows included.

```bash
make questions-export OUT=release.xlsx FILTER="--released"   # what questions-balance drew
make questions-export OUT=exam.xlsx FILTER="--status accepted --cognitive-level analyse"
make questions-export FILTER="--status accepted --unanswerable"
make questions-export FILTER="--no-citations"   # much faster, questions only

python -m question_generation.export --help     # every filter there is
```

Four sheets: the questions, the facts each cites — one row per fact per
passage — what an LLM judge made of each answer, and the counts. Argilla is
not this: it holds a disposable copy of a sample pushed for review.

A question's own row carries what it rests on, so it reads on its own: the
facts it cites and the evidence under them, its subjects, its documents **by
title**, the answer at length, and why the judge said what it did. The
Citations sheet is still the grain that carries the page number and the
passage ordinal, which is what checking an answer against the source needs.

The Assessment sheet and the three `Judge` columns are empty unless the
judge has run.

`questions-diff` reads live questions **and** archived ones. A rerun appends,
so two runs' questions stand side by side; the archive keeps the rows a
deletion or a re-chunk took since. A run listed `(deleted)` is being read out
of `archived_rows`.

```bash
make questions-reclaim TOPIC=473   # one topic, while a worker may be up
make questions-reclaim             # every one the stage holds
```

`reclaim` fills the gap between `retry`, which takes the failed, and `rerun`,
which skips what a worker holds. Narrow it while a worker may be up: nothing
can tell a dead claim from a live one. Not narrowed, it refuses while the
stage's worker runs.

It has routes now as well: `POST /{stage}/{scope}/{value}/reclaim` for one
scope, and `POST /{stage}/reclaim?confirm=true` for the whole stage, which
refuses without `confirm`. See
[`backend/stages/`](../backend/stages/README.md).

## The evaluation phase

An LLM judge over every fact, topic and question, run after the pipeline and
never during it. Off unless `ASSESSMENT_ENABLED` is true, in `.env` or as a
stored setting (`make settings-set SERVICE=assessment`, which wins over
`.env`), and every target says so and stops rather than quietly doing
nothing.

**It decides nothing.** The verdict goes in a column of its own beside the
checker's, and no stage reads it. See
[`backend/assessment/`](../backend/assessment/README.md) for why it cannot
be a gate.

| Target | Does |
|---|---|
| `make assess-enrol` | Create the rows without queuing any, and say how many it enrolled this time, so a second run over an unchanged corpus says 0. `make assess-status` shows the whole queue |
| `make assess-start` | Enrol and queue everything that has no verdict |
| `make assess` | Drain the judging queue here, in the foreground |
| `make assess-status` | The queue by state, and a warning when no judge is named. What the judge said is on the Assessment page, and for the questions in the Assessment sheet `make questions-export` writes |
| `make assess-stop` | Take back what has not begun |
| `make assess-retry` | Return the artefacts the judge could not be reached for |
| `make assess-rerun` | Judge everything again, under the current templates |
| `make assess-reclaim` | Return an artefact a dead worker holds. **Narrow it** |

```bash
make assess-enrol                              # enrol and count first; not a dry run
make assess-start ONLY=--only\ kind=question   # the deliverable only
make assess
```

A fact costs three model calls, a topic two and a question six, one of them
returning six scores (a follow-up five, without that one).
`ASSESSMENT_KINDS` and `ASSESSMENT_SAMPLE` in `configs/env/backend.env` are
the dials, and the default is a sample per kind rather than a corpus.

A failure here is the **model** being unreachable, not an artefact being bad:
a judgement that came back as a refusal is recorded as one and is not a
failed row.

### How varied the questions are

| Target | Does |
|---|---|
| `make diversity FILE=<workbook>` | N-gram diversity, self-repetition, the word and part-of-speech compression ratios and the homogenization score of an exported workbook's questions, one row per language, as the DataMorgana paper measures a benchmark, and `held`, how much of each question its cited evidence already holds, an easiness reading. `CODE=de` measures one language; `SIZE=200` draws that many from each, because the metrics move with a set's size. `AGAINST=<workbook>` compares with a second workbook: both drawn fifty times to 80% of the smaller set, each metric's mean and spread, the difference, and Welch's p, starred below 0.05. `BY=category` measures each category of each language on its own, then gives each category the share of its questions inside the word bounds configured today, which reads the stored settings, and the shares whose answer form is factoid and open-ended. `BY=kind` measures each kind (single, needs_both, compound) on its own and gives each kind's factoid and open-ended shares, with the questions that have no answer apart as `unanswerable`: the Kind column is the span of the answer's passages, which they do not have, so they all read `single` in the workbook. Where the workbook holds the paper's judge, its mean scores follow. `BY=document` draws the paper's few-documents curve (Figure 1) for a corpus of many documents. `LABELS=<file>` takes reviewers' yes/no labels of some of the questions (JSONL, an `id` and one field per label) and prints each labelled share corrected by the judge's verdict on all of them, with prediction-powered inference (Angelopoulos et al., [*Prediction-powered inference*](https://doi.org/10.1126/science.adi6000), Science 2023) as ARES (Saad-Falcon et al., [*ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems*](https://aclanthology.org/2024.naacl-long.20/), NAACL 2024) does: per language, per category or kind, and pooled, the corrected share, its 95% interval and the weight the judge was given, tuned as PPI++ (Angelopoulos, Duchi and Zrnic, [*PPI++: Efficient Prediction-Powered Inference*](https://arxiv.org/abs/2311.01453), 2023) tunes it. No LLM is asked, and the phase need not be on |

```bash
make questions-export OUT=set.xlsx FILTER="--status accepted --answerable --roots-only"
make diversity FILE=set.xlsx SIZE=200
```

See [`backend/assessment/`](../backend/assessment/README.md#how-varied-the-questions-are)
for what each metric is. They are the DataMorgana paper's:
Filice et al., [*Generating Q&A Benchmarks for RAG Evaluation in Enterprise
Settings*](https://aclanthology.org/2025.acl-industry.33/), ACL 2025 Industry Track.

## Documents

Every target that destroys data in a database (`schema-down`, `schema-reset`,
`wipe`, `wipe-all`, `delete`, `delete-derived`, `topics-delete`, an unnarrowed
`*-rerun`, `archive-purge` with `TABLE`, `ALL` or `DAYS`, and the four store
steps of the wipe run alone: `phoenix-purge`, `review-delete`, `logs-wipe` and
`dagster-wipe`) refuses unless
`CONFIRM=<database>`, typed on the command line (a `CONFIRM` exported in the
shell does not count), names the database the settings resolve to, and says
which database and port it would act on. An `APP_DB_NAME` exported in the
shell is honoured over `deployment.env`. Host drains print the database and
port they run against before they start.

Documents are ingestion's, not a stage's. A deletion here is the first of
two: its rows are archived and its objects moved to the `archive` bucket, so
`make restore-documents AT=<time>` puts them back until
`make archive-purge` empties the archive, which `make wipe-all` does too.
`make documents` only lists. What `wipe` takes from Phoenix, Argilla, the
logs and Dagster is final.

| Target | Does |
|---|---|
| `make s3-prefix` | Copy the objects a store holds from before keys carried the database's name under this database's prefix. Once per database that used the store. Copies only the objects this database's rows name, never over an object it already holds, never moves |
| `make documents` | List the newest 1000 documents with their parse state, and warn when the corpus holds more |
| `make ingest DIR=<directory>` | Ingest every PDF directly in a directory of the host through the service the Upload page uses, under its limits as stored there (`MAX_FILE_SIZE_MB`, `PARSING_MAX_PAGES`, `PARSING_TIMEOUT_SECONDS`), for a set too large for that page (it refuses more than 20 files or 200 MB at once). One line per file and a summary; a copy of a stored file is reported as a duplicate and stores nothing; a file the service refuses makes the run exit 1 |
| `make delete SHA=<sha256>` | Delete a document and everything derived from it. A question on a fact it removes goes, one written from two documents with either; a fact another document also cites stays, with its question. Refuses, deleting nothing, while `extract-worker` runs, which it does after `make up` or `make dev`: stop it first. Then `extract-dedup` over the whole corpus, which gives back a fact another document repeats and had refused as a duplicate of this one's. If that replay fails, the document is already gone: run `make extract-dedup`. The deletion ends with one line naming how many duplicate refusals lost the fact they repeated; after a deletion through the API or the UI the extraction worker re-decides them once its queue is empty, or `make extract-dedup` where none runs |
| `make delete-derived SHA=<sha256>` | Delete its passages, and with them their memberships, the facts and questions resting on them alone, follow-ups and assessments. Refuses while `extract-worker` runs, as `make delete` does, then runs the same replay |
| `make wipe-preflight` | Read only: authenticates to Phoenix, Argilla and Elasticsearch and asks the Dagster webserver, each only while its service runs (a store that is down is named, and `make wipe` skips its step with the same note), and names every store that refuses with the setting to check. What `make wipe` runs after the `CONFIRM` check and before it deletes anything |
| `make wipe` | Every document, the topics, then Phoenix, Argilla, the logs and Dagster, in that order, stopping at the first that fails: run it again once that service answers. Refuses unless `CONFIRM` names the database |
| `make wipe-all` | The same, then the archive. The one command for "leave nothing" |
| `make wipe KEEP=golden,runs` | Spare the Phoenix datasets and the Dagster run history |

`wipe` runs both deletions because deleting every document leaves the topics
standing. It also drops the upload history, which a single deletion keeps.

It then takes the Phoenix projects and datasets, the Argilla datasets, the
logs and the Dagster run history, for the reason the corpus went: a trace
of a run over documents that are gone, a reviewer asked about facts that no
longer exist and a log line about a passage nothing holds all describe a
corpus nobody can open. Leaving them is how a fresh run starts against four
services still full of the last one. Those four deletions are final:
nothing archives them, and an Argilla answer not yet pulled goes with its
dataset.

**The archive is kept.** The rows and objects it deletes are the first of
two deletions - the triggers copy each row into `archived_rows` and the
removal paths move each object into the `archive` bucket - so a wipe that
purged it would leave nothing to recover from.
[`make archive-purge`](#the-archive) is the second decision and stays one -
or `make wipe-all`, which is both in the only order they work in: `wipe`
fills the archive, so the purge has to come second or it takes nothing.

### What a wipe leaves

Nothing, by default. The command is called wipe, and a default that quietly
kept things would be the wrong way round: Phoenix keeps no project but
`default` and no dataset, Argilla no review dataset, Dagster no run, and
Grafana reads an empty log stream. Grafana holds nothing of the corpus - its
dashboards and datasources come from
[`configs/grafana/provisioning/`](../configs/grafana/provisioning/), and a
dashboard edited in the UI is kept until its file changes - so there is
nothing there a wipe could take.

`KEEP` spares the two things nothing upstream rebuilds:

| `KEEP=` | Leaves |
|---|---|
| `golden` | This database's Phoenix datasets and the experiments under them (every database's with `ALL_DATABASES=1`). Each is named `<name>__<database>`; `make eval-upload` puts `extraction-golden` back and `make eval-phrasing` `phrasing-golden`. A set uploaded before names carried the database is taken only with `ALL_DATABASES=1`; upload it again |
| `runs` | The Dagster run history |
| `golden,runs` | Both |

The rest of what a wipe takes outside the database and the buckets is gone
for good: every Phoenix project, every Argilla dataset with any answer not
yet pulled, and the logs. Any other `KEEP` name is refused.

## The archive

Every deletion of a row or an object above is the first of two.

| Target | Does |
|---|---|
| `make archive` | What is held, by table, with its age |
| `make backup DIR=<dir> [ARGILLA=1]` | Dump the application, SeaweedFS, Phoenix and Dagster databases (`pg_dump -Fc`), and Argilla's only with `ARGILLA=1` (its dump holds the owner's API key in clear: store it as a secret), copy every object of the five buckets and write a manifest of row counts and sha256 into `DIR`. Never `.env`, `provider.env` or a certificate key. `DIR` must hold no backup. See Backups in the operations guide |
| `make restore-backup DIR=<dir> CONFIRM=<database>` | Put one database back: `pg_restore` of the application database and its own objects (under its prefix), checked against the manifest. Leaves the shared stores (filer, Phoenix, Dagster, Argilla) and other databases' objects alone. Refuses while a worker runs and unless `CONFIRM` names the database. **Replaces the data** |
| `make restore-backup-stack DIR=<dir> CONFIRM=stack` | Put the whole stack back: the five databases and every database's objects. Rolls back every other database too, so it refuses while more than one application database exists unless `ALL_DATABASES=1`. **Replaces the data of the stack** |
| `make restore-documents` | Without `SINCE`, the 20 newest deleting transactions, and it exits 2, so make reports an error; an older start is read off `archived_rows`. With `SINCE=<time>`, list the deleting transactions from then on (exact `archived_at` each, tables and rows). With `AT=<archived_at>[,...]`, put back those deletions only; `service_settings` and `prompts` stay out unless `TABLES` names them. Run it before `archive-purge` |
| `make archive-purge` | The second deletion. **This one is final** |

```bash
make archive-purge TABLE=questions   # one table's rows
make archive-purge DAYS=30           # everything archived before then
make archive-purge ALL=1             # the whole thing, objects included
```

`TABLE` is about rows and leaves the bucket alone. `DAYS` and `ALL` take the
objects too. See [`backend/archive/`](../backend/archive/README.md).

## Settings

```bash
make settings SERVICE=topics
make settings-set SERVICE=topics SET="TOPIC_PASSES=20"
make settings-unset SERVICE=topics UNSET="TOPIC_PASSES"
```

The services are `ingestion`, `parsing`, `chunking`, `extraction`, `topics`,
`questions`, `assessment` and `platform`. See
[configuration.md](configuration.md).

## Schema

| Target | Does |
|---|---|
| `make migration m="add the dropped counts"` | Write a revision from the models |
| `make schema` | Apply everything outstanding |
| `make schema-status` | Where the database is |
| `make schema-down` | Take the newest revision back off. From the first revision that drops every table, `archived_rows` included. Refuses unless `CONFIRM` names the database |
| `make schema-reset` | Drop every table and rebuild. **Irreversible** |
| `make schema-stamp` | Adopt a database that already holds the tables |

**Read the generated revision before applying it.** Autogenerate does not see
a trigger, a data backfill, or anything ordered.

## Review and evaluation

| Target | Does |
|---|---|
| `make review-push-facts` / `review-pull-facts` | Send a sample of facts to Argilla; bring the verdicts back |
| `make review-push-topics` / `review-pull-topics` | The same, for topic labels, except that every topic is pushed rather than a sample |
| `make review-push-questions` / `review-pull-questions` | The same, for questions |
| `make review-status` | How much has been looked at |
| `make review-delete` | Delete this database's three review datasets: facts, topic labels and questions, each named with the database. A dataset under another name, another database's included, is left. **Irreversible** - pull first. What `make wipe` runs |
| `make review-all` | Every artefact of every kind, not a sample |
| `make eval-upload` | Put the golden cases in Phoenix |
| `make eval-score` | Score the served model against them, and record it |
| `make prompts-publish` | Republish every recorded prompt to Phoenix. A stage publishes what it records when it starts, so this is for a Phoenix wiped while the rows stayed |
| `make eval-phrasing` | Score the two phrasing judgements, each against its floor |

```bash
make eval-score EVAL_RUN_NAME=extraction-prompt-v7
make review-push-questions IDS=12,34,56
```

`IDS` is how the disagreements the Assessment page marks reach a reviewer.

## Phoenix's projects

| Target | Does |
|---|---|
| `make phoenix-projects` | What Phoenix holds, changing nothing |
| `make phoenix-retention` | Set Phoenix's default trace retention policy to `PHOENIX_TRACE_RETENTION_DAYS` days (30 where unset), so a prompt, which is a passage of a customer's document, is not kept for ever. Run by `make up` and `make dev` |
| `make phoenix-prune` | Delete this database's projects in which no work happened (`ALL_DATABASES=1`: every database's). **Irreversible**, and asks nothing first: it names at most 25 of the projects it takes, then deletes them |
| `make phoenix-purge` | Delete **every** project of this database (names end in `__<database>`; `ALL_DATABASES=1` takes every database's and those filed before) but `default`, whatever it holds, and every dataset of this database. What `make wipe` runs, and what `prune` will not do |
| `make phoenix-purge KEEP=golden` | The same, but leave the datasets and their experiments |
| `make dagster-wipe` | The runs this database launched (the corpus job tags each with it), and the event log under each; untagged history stays. `ALL_DATABASES=1` takes every run Dagster remembers |

A Phoenix project is created by whatever sends the first span to it and
removed by nothing. While a project meant a run somebody asked for that was
fine — but a `run_id` falling back to a uuid **per process**, a `--watch`
worker that is a process per restart, and an expired credential together
produce one project per minute, each holding the single call a preflight made
before giving up.

Two changes stop that — an unnamed run appends to its stage's own project,
and the exporter is not installed until the preflight passes — and `prune`
takes back whatever an older arrangement left.

`prune` takes a project only when **every span in it is a model call and it
could read every span**, and never `default`. A project too big to read in
one page is left alone, because the first fifty spans of a real run are model
calls too, and so is one whose spans Phoenix would not hand over.

## Tests and checks

| Target | Runs |
|---|---|
| `make test` | Everything that gates; starts containers of its own |
| `make check` | An alias for `make test` |
| `make test-fast` | Only the fast layers: no spaCy, no pyright, no containers |
| `make test-unit` | Everything but integration, smoke, eval and perf |
| `make test-integration` | The container layers, end to end aside, which is `make test-e2e` |
| `make test-e2e` | One document through every stage, in this process, and on through the bridge pass, the release draw, a stub-judged assessment and the workbook export |
| `make test-golden` | Real PDFs, two of the shop corpus and one made in the test, through the real converter and chunker, against the snapshots in `tests/golden/snapshots`: text, heading trail, pages and table size. Slow, offline from the weight cache, and fails rather than skips where a weight is missing. `make test` leaves it out |
| `make golden-refresh` | Rewrite those snapshots after a change to the parse or the chunker that is meant; read the diff before committing it |
| `make test-smoke` | Build both images and look inside them |
| `make test-eval` | Score the served model against the golden passages. Never gates |
| `make test-perf` | Time the ceilings the code names. Never gates |
| `make test-coverage` | The gating layers, with a coverage report |
| `make mutation` | Whether the tests would notice a gate changing. Hours |
| `make lint` | ruff check and format check |
| `make format` | Apply every fix ruff can make |
| `make typecheck` | pyright, at zero |
| `make audit` | Known advisories, read from OSV, against both image locks and the host `poetry.lock`, torch and torchvision left out. Fails on one, after reading all three, except an advisory listed in `configs/audit-accepted.txt` for that lock (`AUDIT_ACCEPTED=` names another file): each entry carries a reason and a review-by date, and a date that has come fails the audit before any lock is read. An accepted id that no lock it covers reports any more fails it too, named as no longer needed, so the list holds only what it hides. Its scratch files live in a temporary directory. Linux only, as the nightly job runs it: on a Mac the `poetry.lock` leg fails on CUDA wheels with no macOS build |
| `make lint-imports` | The two architecture rules, as import-linter contracts |
| `make deps` | A declared dependency nothing imports, and an import nothing declares |
| `make lock` | Rewrite `backend/api/requirements.lock` and `frontend/requirements.lock`, resolved under the pins of `poetry.lock` in a throwaway container |

`lint` and `format` cover `backend`, `frontend`, `telemetry`,
`orchestration`, `review`, `evaluation` and `tests`; `typecheck` covers the
same but `tests`.

`test-perf` and `mutation` run only in the nightly workflow, which also runs
`make audit`, every layer but eval, perf and slow, and the eval layer
`make test-eval` runs. The slow layer, the golden PDFs, runs in its weights
job alone, whose cache holds the embedding, NLI and Docling weights, keyed by
the Docling release; where a conversion differs from the snapshots it
converts them again and keeps them as the `golden-snapshots-linux` artifact,
from which a refresh recorded on Linux is taken. Which modules and layers mutation covers is
`[tool.mutmut]` in `pyproject.toml`; `mutmut browse` reads the survivors.

## Cost

```bash
make estimate                             # before a run: time, calls and USD of the rows still to do
make estimate DRAINS=questions=2,extract=2
make spend LOG=run.log                    # totals from a captured log
make spend LOG=run.log SINCE=2026-09-19   # one day of it
make spend-by-shape LOG=run.log           # split by model and judgement
```

`make estimate` multiplies the rows still to do by what a row of each stage
took in the reviewed build, and says so in
[Sizing a corpus](operations.md#sizing-a-corpus); `DRAINS` divides a stage's
time, not its spend, and more than two drains of the model stages need a
larger provider quota, measured first. `make spend` is for after a run.

`LOG` is **required** and names the text log a drain wrote to a terminal —
`make questions | tee run.log` — not the shipped JSON. For a run happening
now, use Grafana's **2 · What each stage is doing** dashboard or Phoenix.

`spend-by-shape` splits by the model that answered and the Pydantic class the
call had to return, which is what each judgement costs. Both read a log the
same way, so its totals agree, and both count a call that failed after it
was billed.

## Orchestration

The asset graph already chains the stages. These decide **when**.

| Target | Does |
|---|---|
| `make runs` | The sensor, the schedule and the last five runs |
| `make pipeline` | Every stage but the topic fit once, as a recorded Dagster run |
| `make auto` | Start the `arrivals` sensor: an upload starts a run on its own |
| `make manual` | Stop it again |
| `make dagster-dev` | Run the code location on the host |

`auto` is the unattended mode and ships stopped. `pipeline` runs the stages
of `make corpus` in the container workers rather than on the host, and
survives the terminal closing. It is not the same build: it skips the bridge
pass (`make extract-bridge MISSING=1`) and the release draw, and the workers
call `LLM_CONTAINER_MODEL` at `OLLAMA_CONTAINER_URL`, not `.env`'s
`LLM_MODEL`. `make questions-balance` draws the release once it ends.

All four have an equivalent through the api, for a deployment nobody drives
from a terminal: `POST /pipeline/run` is `make pipeline`, and
`PUT /pipeline/automation` is `auto` and `manual`. The Run button on the
Documents page is the first of those.
