# Make commands

Every target, grouped. A host target and the backend's containers read
`configs/env/backend.env`, so a tuning value set there reaches both. The model
does not: see [Configuration and the container
engine](#configuration-and-the-container-engine).

```bash
make help            # or just `make`
make help | grep -i topic
```

`help` reads the Makefile itself. A target's group is the section banner it
sits below, and its description is the first sentence of the comment directly
above it. A target with no comment directly above it is not listed. This page
is the long form.

## First run

| Target | Does |
|---|---|
| `make setup` | Write `.env` and `configs/env/provider.env` and fill in every placeholder. Safe to run twice: it replaces only `change_me_*` placeholders |
| `make install` | `make install-python`, then `make docling-weights` |
| `make doctor` | Check the tools, the configuration, the model split, the stored settings, and the pinned models and Docling's weights in the cache (a miss fails with `HF_HUB_OFFLINE=1` or `HOST_RUNNER=1`, else warns). Then ask every model one question. Also lists names `ENV_FILE` sets over a committed file, warns when the checkout or `ENV_FILE` sits in a synced folder, fails on an `APP_DB_PASSWORD` a connection string cannot hold, and prints the archive's estimated size |
| `make dev` | `make install` first, then certificates, every service, the schema and the Grafana grants |
| `make upgrade` | Check the engine has `UPGRADE_FREE_GB` free (20), build, prune orphaned images, stop the workers, `make schema`, `make up`. Stops at the first failing step |

`doctor` ends with a real call to `LLM_MODEL`, as the host calls it. A
container may call only Ollama: `doctor` fails when `OLLAMA_CONTAINER_URL` or
`LLM_CONTAINER_MODEL` is unset, or when `LLM_CONTAINER_MODEL` (or a set
`QUESTIONS_VERIFIER_CONTAINER_MODEL`) does not start with `ollama`.

## The short list
| Target | Does |
|---|---|
| `make all` | Bring the stack up, wait for Dagster to list the corpus job, and launch it. The container workers drain every stage but the topic fit, which Fit all on the Topics page asks for |
| `make corpus` | Drain every stage on the host in order, stopping at the first drain that exits non-zero (3 a failed row, 75 a drain that stopped itself). Waits for `parse-worker` and `chunk-worker` to empty their queues, and refuses beside `extract-worker`, `topic-worker`, `question-worker` and `assess-worker`: stop those first |
| `make corpus-hosted` | `make corpus` on the host, detached and supervised. Needs `HOST_RUNNER=1`. See [Production host](operations.md#production-host) |
| `make corpus-preflight` | What a hosted run proves before it starts: `HOST_RUNNER=1`, no model worker or Dagster up, the split, the database password and the Hugging Face cache |
| `make corpus-database` | Print the database a corpus run acts on: `APP_DB_NAME` given or exported, else the files' |
| `make corpus-hosted-stop` | TERM to the run's process group (the drain in hand finishes or gives back its row and exits 75), then KILL after 300 seconds. The ledger and pid file are kept |
| `make pipeline-status` | Where the corpus has got to, every stage in one call |
| `make services` | Every container, whether it is listening, and where to open it |
| `make open` | The same, and open the application |
| `make review` | Push a sample of facts and questions, and every topic label, to Argilla |
| `make pull` | Pull every decision made there back into the database |

`make auto` hands the whole run to Dagster (see
[Orchestration](#orchestration)).

`make corpus` gives every drain one database name (`APP_DB_NAME=` on the
command line, else the files'), `HF_HUB_OFFLINE=1` and one spend ledger, so
`SPEND_CAP` holds for the whole run. It is incremental up to the release,
whose draw runs each time and asks the verifier about each released question
and its nearest neighbour, in up to three rounds plus a fourth that only drops
twins. It stops before the judge when the verifier does not answer. `RESUME=1`
keeps the ledger and returns every stage's failed rows to the queue first.

`make corpus-hosted` runs `scripts/corpus-hosted.sh` in its own process group,
recorded in `state/corpus-hosted.pid` (log: `logs/corpus-hosted.log`). A
second start is refused while a member lives. After a run that ended
unfinished (a stop at `SPEND_CAP`, a signal, failed rows, a crash), a start
resumes on the recorded database and keeps its spend. `RESET=1` starts afresh.
`make corpus-hosted SPEND_CAP=50` stops at USD 50.

## Configuration and the container engine

Targets read `configs/env/backend.env`, `configs/env/deployment.env`,
`configs/env/provider.env` then `.env`, and a later file wins. The review and
evaluation targets and `dagster-dev` also read `review.env`, `evaluation.env`
or `orchestration.env`. The api and the workers take only `backend.env` whole,
plus `provider.env` where they call a model. compose reads `deployment.env`
and `.env` only for the values `compose.yaml` names.

`.env` is `ENV_FILE`: `make up ENV_FILE=/etc/qa/secrets.env`, or export it
([Production host](operations.md#production-host) says why).

A container calls `LLM_CONTAINER_MODEL` at `OLLAMA_CONTAINER_URL`. Its
verifier is `QUESTIONS_VERIFIER_CONTAINER_MODEL` and its judge
`ASSESSMENT_JUDGE_CONTAINER_MODEL`. It never reads `.env`'s `LLM_MODEL`,
`QUESTIONS_VERIFIER_MODEL` or `ASSESSMENT_JUDGE_MODEL`.

A setting stored with `make settings-set` or a Configuration panel beats every
file, on the host and in the containers, until `make settings-unset` removes
it. A variable given on the command line beats them all, the stored setting
included:

```bash
make topics-discover TOPIC_PASSES=20
```

The Makefile re-applies command-line overrides after sourcing the files and
before it builds the addresses, so `make schema POSTGRES_PORT=5433` connects
to that port.

The Makefile invokes `podman compose` and `podman`. For Docker, set both:

```bash
make CONTAINER=docker COMPOSE="docker compose" up
```

`CONTAINER` is the engine itself: `doctor`, `prune` (and so `down`) and `lock`
use it.

## Starting and stopping

| Target | Does |
|---|---|
| `make dev` | `make install` first (needs the network), then certificates, every service, the schema and the grants. Use `make up` for an installed stack |
| `make install-python` | Dependencies and the spaCy pipelines `NLP_MODELS` names, on the host alone. What CI's setup runs |
| `make docling-weights` | Download Docling's weights into the `models` volume that parse-worker reads. `HOST=1` fetches them into the host's Hugging Face cache instead, which `make doctor`, the hosted preflight and a host drain read |
| `make up` | Start services, then grant Grafana's reader the five Phoenix tables its run dashboard queries. On a slow first boot it fails after 150 seconds with the stack up: run `make grafana-grants` again |
| `make grafana-grants` | Those grants alone. Safe to repeat |
| `make down` | Stop services, keep data, and remove dangling images |
| `make down-volumes CONFIRM=all-volumes` | Stop services and **delete all data**: every database's volumes on the stack |
| `make certs` | Generate the TLS certificates Elasticsearch needs |
| `make prune` | Remove dangling container images |

## Logs

| Target | Does |
|---|---|
| `make logs` | Follow all logs |
| `make logs-api`, `make logs-frontend` | Follow the API, the frontend |
| `make logs-orchestration` | Follow the Dagster webserver and daemon |
| `make logs-shipper` | Follow the log shipper, when Grafana shows nothing |
| `make logs-retention` | Set how long Elasticsearch keeps logs. Run once |
| `make logs-prune` | Delete log files unwritten for `LOGS_KEEP_DAYS`, on the volume and in `./logs`. Fails when the api does not answer |
| `make logs-wipe` | Delete this database's log lines (each has a `db` field), keep the shared files. `ALL_DATABASES=1` deletes every `qa-logs*` stream and empties every file. What `make wipe` runs |

```bash
make logs-retention LOGS_RETENTION_DAYS=90
make logs-prune LOGS_KEEP_DAYS=7
```

## The corpus as one thing
| Target | Does |
|---|---|
| `make pipeline-stop` | Take back everything queued, in every stage, and stop the run behind it |
| `make pipeline-retry` | Return every stage's failures to the queue |

`make pipeline-status` (above) shows every stage's queue and the run in
flight. No `pipeline-start` exists: `make pipeline` starts each stage and
waits for it to drain before the next. With `WAIT=1`, which `make corpus`
gives every drain, a parse or chunk stage whose container worker runs is
waited for until that worker has emptied its queue. A model stage still
refuses beside its worker.

On the production profile (`HOST_RUNNER=1`) there is no orchestrator. `make
all`, `make pipeline` and `make auto` refuse, naming `make corpus-hosted`.
`POST /pipeline/run`, `POST /pipeline/start` and `PUT /pipeline/automation`
answer 409.

## The six verbs every stage answers

Each verb but the drain is the same operation as the stage's route: `make
parse-start` is `POST /parsing/start`. No route drains. See
[`backend/stages/`](../backend/stages/README.md).

| | Parsing | Chunking | Extraction | Questions | Assessment |
|---|---|---|---|---|---|
| queue what was never asked for | `parse-start` | `chunk-start` | `extract-start` | `questions-start` | `assess-start` |
| drain here, in the foreground | `parse` | `chunk` | `extract` | `questions` | `assess` |
| show the queue | `parse-status` | `chunk-status` | `extract-status` | `questions-status` | `assess-status` |
| take back what has not begun | `parse-stop` | `chunk-stop` | `extract-stop` | `questions-stop` | `assess-stop` |
| return failures to the queue | `parse-retry` | `chunk-retry` | `extract-retry` | `questions-retry` | `assess-retry` |
| queue everything again | `parse-rerun` | `chunk-rerun` | `extract-rerun` | `questions-rerun` | `assess-rerun` |

A drain here (the bare target, every `-rerun` and `topics-discover`) **refuses
while that stage's container worker is running** and prints the `podman
compose … stop <worker>` that stops it. `WAIT=1` on `parse` or `chunk` waits
for the worker to empty the queue instead (another database refuses with exit
3), polling every `WORKER_POLL_SECONDS`, and exits 3 if rows failed.

`extract-dedup`, `extract-revalidate`, `extract-recap`, `delete` and
`delete-derived` refuse beside `extract-worker` the same way.
`questions-reclaim` and `assess-reclaim` refuse beside their worker when not
narrowed.

`assess-start` also enrols: it creates the assessment rows as well as queuing
them. `chunk-start` and `chunk-rerun` queue only documents parsing has
finished. Topic modelling has no `start` and no `rerun`, because a fit is
all-or-nothing.

| Target | Does |
|---|---|
| `make topics-discover` | Ask for a fit over the whole corpus, and run it. `make corpus` runs it as `make topics-discover ENSURE=1`, which fits only when a language holds passages and no topic or its topics are stale, and otherwise drains a queued fit |
| `make topics` | Run any queued fit here, in the foreground |
| `make topics-status` | The topics held, any queued fit, and how many passages are in no topic |
| `make topics-stop` | Withdraw a queued fit |
| `make topics-retry` | Return a failed fit to the queue |
| `make topics-visualise` | Write each language's stored pyLDAvis page to `./topics/` |
| `make topics-render` | Redraw those pages from the stored models. `CODE=de` for one |
| `make topics-name` | Name the topics a fit left unnamed, without re-fitting |
| `make topics-delete` | Delete every topic and membership, any fit queued or running, and the judge's verdicts on topics. Figures and models go to the archive. Refuses unless `CONFIRM` names the database |

### Narrowing to one item
Any verb but the bare drain narrows with `SHA`, `PASSAGE` or `TOPIC` (`SHA`
wins over `PASSAGE` over `TOPIC`):

```bash
make parse-start SHA=<sha256>     # queue one document for parsing
make chunk-rerun SHA=<sha256>     # rebuild one document's passages
make extract-start SHA=<sha256>   # queue every passage of one document
make extract-retry PASSAGE=<id>   # return one failed passage to the queue
make extract-status SHA=<sha256>  # that document's passages by extract state
make questions-start TOPIC=<id>   # queue one topic for question generation
```

Parsing and chunking narrow to a document, extraction to a document or a
passage, question generation to a topic, assessment to a kind (`ONLY=--only\
kind=<kind>`), and topic modelling to nothing. `questions-balance` always
draws over every topic. A bare drain is never narrowed, so a narrowed `-rerun`
refuses while any row outside it is queued: run `make <stage>-stop` first.

## Replaying a stage without redoing it

These targets re-derive stored results without the expensive part:

| Target | Does |
|---|---|
| `make extract-revalidate` | Judge every stored fact again. No model call |
| `make chunk-revocabulary` | Re-read language and vocabulary: `passages.language`, `passages.lemmas`, and `facts.language` change |
| `make questions-reverify` | Put every stored question through the gates that need no model |
| `make questions-rescore` | Rewrite stored scopes and difficulty from what each question cites now. Run it after an `extract-dedup` that removes fold citations, before `questions-reverify`, and after a topic refit, following `questions-reverify`. Not after a re-extraction or deletion, where it would hide `source_changed` |
| `make extract-recap` | Re-apply the atomic cap `EXTRACTION_MIN_OTHER_SHARE` works out to, never below a passage's own sentences and list items |
| `make extract-dedup` | Re-decide every `duplicate` refusal under today's rule, remove the citations a refusal added, and re-judge and re-cap the passages of refusals given back. No model call |
| `make extract-embed` | Write vectors onto stored passages and facts. Does not apply the dedup gate |
| `make extract-digests` | Give a summary and an outline to passages that finished without them (the digest model failed or refused) or hold none above `EXTRACTION_DIGEST_MIN_CHARS`. One digest-model call per passage. `make corpus` runs it after `extract` |
| `make extract-bridge` | Read each topic's passage groups for claims spanning passages. Asks the model first. Refuses while an accepted question cites a bridge it would replace: `FORCE=1` replaces them anyway. `MISSING=1` reads only topics with no bridge and deletes nothing (how `make corpus` runs it) |
| `make confidence-recalibrate` | Take every stored margin again after a change to `QUESTIONS_DUPLICATE_FLOOR` or `EXTRACTION_DUPLICATE_FLOOR`. No model call, no verdict moves. A deadlocked batch is retried once; a second deadlock fails the run: run it again |

`chunk-revocabulary` takes `SHA`. `extract-revalidate`, `extract-recap`,
`extract-dedup`, `extract-embed` and `extract-bridge` take `SHA` or `PASSAGE`.
`questions-reverify`, `questions-rescore` and `questions-rejudge` take
`TOPIC`.

The destructive alternative: `extract-rerun` calls the model again over the
whole corpus, and `chunk-rerun` replaces every passage of a document the new
cut changes, with its facts. A question resting on what a rerun replaces is
rejected as `source_changed` and kept, and its follow-ups leave the release.
Both reruns refuse, naming how many released, accepted and reviewed questions
rest on what they would replace, unless `FORCE=1` is given (routes take
`force=true`, else answer 409 `questions_rest_on_it`). Without `SHA`, or
`PASSAGE` for extraction, both also refuse unless `CONFIRM` names the
database.

## Questions
| Target | Does |
|---|---|
| `make questions-balance` | Draw the balanced release from what was accepted, with the verifier judging which released questions want one answer. **Calls the verifier model**, about once per released question |
| `make questions-export` | Write the questions a filter selects to an `.xlsx` |
| `make questions-rejudge` | Ask the verifier whether the passages settle each accepted unanswerable question, and reject those they do. **Calls the verifier model**. Takes `TOPIC` |
| `make questions-runs` | The 20 newest runs, and how many questions each wrote |
| `make questions-diff` | Two runs side by side, on the gate that stopped each. A run listed `(deleted)` is read from `archived_rows` |
| `make questions-reclaim` | Return a topic a dead worker still holds. **Narrow it** |

`questions-reverify` and `questions-rescore` are under [Replaying a
stage](#replaying-a-stage-without-redoing-it).

```bash
make questions RUN_ID=b-gemma4-12b
make questions-diff RUNS="a-gpt-4.1 b-gemma4-12b"
make questions-reclaim TOPIC=473   # one topic, while a worker may be up
make questions-reclaim             # every one the stage holds
```

A rerun appends, so two runs' questions stand side by side. Nothing can tell a
dead claim from a live one, so narrow `reclaim` while a worker may be up. Not
narrowed, it refuses while the stage's worker runs. Routes: `POST
/{stage}/{scope}/{value}/reclaim`, and `POST /{stage}/reclaim?confirm=true`
for the whole stage.

### Getting the dataset out

`OUT` names the file (`questions.xlsx` unless given, overwritten). `FILTER`
takes the narrowing the Questions page and `GET /questions` do. With no
filter, the export holds everything, rejected rows included.

```bash
make questions-export OUT=release.xlsx FILTER="--released"   # what questions-balance drew
make questions-export OUT=exam.xlsx FILTER="--status accepted --cognitive-level analyse"
make questions-export FILTER="--status accepted --unanswerable"
make questions-export FILTER="--no-citations"   # much faster, questions only

python -m question_generation.export --help     # every filter there is
```

The workbook has four sheets: the questions, the facts each cites (one row per
fact per passage, with page and passage ordinal), the LLM judge's assessment
(empty unless the judge has run), and the counts.

## The evaluation phase

An LLM judge over every fact, topic and question, run after the pipeline. It
is off unless `ASSESSMENT_ENABLED` is true, and every target says so and
stops. No stage reads its verdict
([`backend/assessment/`](../backend/assessment/README.md)).

| Target | Does |
|---|---|
| `make assess-enrol` | Create the rows without queuing any, and say how many it enrolled (0 on a second run) |
| `make assess-start` | Enrol and queue everything that has no verdict |
| `make assess` | Drain the judging queue here, in the foreground |
| `make assess-status` | The queue by state, and a warning when no judge is named |
| `make assess-stop` | Take back what has not begun |
| `make assess-retry` | Return the artefacts the judge could not be reached for |
| `make assess-rerun` | Judge everything again, under the current templates |
| `make assess-reclaim` | Return an artefact a dead worker holds. **Narrow it** |

```bash
make assess-enrol                              # enrol and count first; not a dry run
make assess-start ONLY=--only\ kind=question   # the questions only
make assess
```

A fact costs three model calls, a topic two and a question six (a follow-up
five). `ASSESSMENT_KINDS` and `ASSESSMENT_SAMPLE` set the amount. A failure
means the model is unreachable: a refusal is recorded as one and is not a
failed row.

### How varied the questions are

`make diversity FILE=<workbook>` measures an exported workbook's questions,
one row per language, as the DataMorgana paper measures a benchmark: n-gram
diversity, self-repetition, compression ratios and the homogenization score,
plus `held` (how much of each question its cited evidence already holds). No
LLM is asked, and the phase need not be on.

| Variable | Effect |
|---|---|
| `CODE=de` | Measure one language |
| `SIZE=200` | Draw that many questions from each language, because the metrics move with set size |
| `AGAINST=<workbook>` | Compare with a second workbook (both drawn fifty times to 80% of the smaller set): each metric's mean, spread, difference and Welch's p, starred below 0.05 |
| `BY=category` | Measure each category of each language, with the share inside the configured word bounds and its factoid and open-ended shares |
| `BY=kind` | Measure each kind (single, needs_both, compound). Unanswerable questions appear apart; they read `single` in the Kind column |
| `BY=document` | Draw the paper's few-documents curve (Figure 1) |
| `LABELS=<file>` | Take reviewers' yes/no labels (JSONL: an `id` and one field per label) and print each labelled share corrected by the judge's verdict on all questions |

`LABELS` uses prediction-powered inference (Angelopoulos et al.,
[*Prediction-powered inference*](https://doi.org/10.1126/science.adi6000),
Science 2023; as in [*ARES*](https://aclanthology.org/2024.naacl-long.20/),
NAACL 2024). It reports the corrected share, its 95% interval and the judge's
weight, tuned as in [*PPI++*](https://arxiv.org/abs/2311.01453) (2023).

```bash
make questions-export OUT=set.xlsx FILTER="--status accepted --answerable --roots-only"
make diversity FILE=set.xlsx SIZE=200
```

[`backend/assessment/`](../backend/assessment/README.md#how-varied-the-questions-are)
says what each metric is. The metrics are from Filice et al., [*Generating Q&A
Benchmarks for RAG Evaluation in Enterprise
Settings*](https://aclanthology.org/2025.acl-industry.33/), ACL 2025 Industry
Track.

## Documents

Every target that destroys data in a database refuses unless
`CONFIRM=<database>`, typed on the command line (an exported `CONFIRM` does
not count), names the database the settings resolve to. The refusal says which
database and port it would act on. The targets are `schema-down`,
`schema-reset`, `wipe`, `wipe-all`, `delete`, `delete-derived`,
`topics-delete`, an unnarrowed `*-rerun`, `archive-purge` with `TABLE`, `ALL`
or `DAYS`, and the wipe's store steps `phoenix-purge`, `review-delete`,
`logs-wipe` and `dagster-wipe`. An `APP_DB_NAME` exported in the shell beats
`deployment.env`.

A deletion here is the first of two: rows are archived and objects moved to
the `archive` bucket. `make restore-documents AT=<time>` puts them back until
`make archive-purge` (or `make wipe-all`) empties the archive. What `wipe`
takes from Phoenix, Argilla, the logs and Dagster is final.

| Target | Does |
|---|---|
| `make s3-prefix` | Copy objects stored before keys carried the database's name under this database's prefix. Run once per database. Never overwrites, never moves |
| `make documents` | List the newest 1000 documents with their parse state |
| `make ingest DIR=<directory>` | Ingest every PDF in a host directory, for sets too large for the Upload page (20 files or 200 MB). Applies the stored `MAX_FILE_SIZE_MB`, `PARSING_MAX_PAGES` and `PARSING_TIMEOUT_SECONDS`. Exits 3 on a refused stored row, 1 on a refused file |
| `make delete SHA=<sha256> CONFIRM=<database>` | Delete a document and everything derived from it. A fact another document cites stays, with its question. Refuses while `extract-worker` runs. Ends by naming how many duplicate refusals lost the fact they repeated; the extraction worker re-decides them, or `make extract-dedup` where none runs |
| `make delete-derived SHA=<sha256> CONFIRM=<database>` | Delete its passages and what rests on them alone: memberships, facts, questions, follow-ups, assessments. Refuses while `extract-worker` runs |
| `make wipe-preflight` | Read only. Authenticates to Phoenix, Argilla and Elasticsearch and asks the Dagster webserver, each while it runs, and names every store that refuses |
| `make wipe` | Every document, the topics, then Phoenix, Argilla, the logs and Dagster, in that order, stopping at the first failure: run it again once that service answers. Refuses unless `CONFIRM` names the database |
| `make wipe-all` | The same, then the archive |
| `make wipe KEEP=golden,runs CONFIRM=<database>` | Spare the Phoenix datasets and the Dagster run history |

`wipe` also drops the upload history. Its four store deletions are final, and
an Argilla answer not yet pulled goes with its dataset. It keeps the archive;
`make wipe-all` purges it afterwards.

### What a wipe leaves

Nothing: Phoenix keeps no project but `default` and no dataset, Argilla no
review dataset, Dagster no run, and Grafana reads an empty log stream (its
dashboards come from
[`configs/grafana/provisioning/`](../configs/grafana/provisioning/)). `KEEP`
spares what nothing upstream rebuilds; any other name is refused:

| `KEEP=` | Leaves |
|---|---|
| `golden` | This database's Phoenix datasets and their experiments (every database's with `ALL_DATABASES=1`), each named `<name>__<database>`. `make eval-upload` puts `extraction-golden` back and `make eval-phrasing` `phrasing-golden`. A set uploaded before names carried the database needs `ALL_DATABASES=1`: upload it again |
| `runs` | The Dagster run history |
| `golden,runs` | Both |

## The archive

| Target | Does |
|---|---|
| `make archive` | What is held, by table, with its age |
| `make backup DIR=<dir> [ARGILLA=1]` | Dump the application, SeaweedFS, Phoenix and Dagster databases (`pg_dump -Fc`), copy the five buckets, and write a manifest of row counts and sha256 into `DIR`, which must hold no backup. `ARGILLA=1` adds Argilla's database, whose dump holds the owner's API key in clear: store it as a secret. Never includes `.env`, `provider.env` or a certificate key. See Backups in the operations guide |
| `make restore-backup DIR=<dir> CONFIRM=<database>` | Put one database back (`pg_restore` and its own objects), checked against the manifest. Leaves shared stores and other databases alone. Refuses while a worker runs. **Replaces the data** |
| `make restore-backup-stack DIR=<dir> CONFIRM=stack` | Put the whole stack back. Refuses while more than one application database exists unless `ALL_DATABASES=1`. **Replaces the data of the stack** |
| `make restore-documents` | Without `SINCE`, list the 20 newest deleting transactions and exit 2. `SINCE=<time>` lists them from then on. `AT=<archived_at>[,...]` puts those deletions back (not `service_settings` or `prompts`, unless `TABLES` names them). Run before `archive-purge` |
| `make archive-purge` | The second deletion. **This one is final** |

```bash
make archive-purge TABLE=questions CONFIRM=<database>  # one table's rows
make archive-purge DAYS=30 CONFIRM=<database>          # everything archived before then
make archive-purge ALL=1 CONFIRM=<database>            # the whole thing, objects included
```

`TABLE` takes rows and leaves the bucket alone. `DAYS` and `ALL` take the
objects too. See [`backend/archive/`](../backend/archive/README.md).

## Settings

```bash
make settings SERVICE=topics
make settings-set SERVICE=topics SET="TOPIC_PASSES=20"
make settings-unset SERVICE=topics UNSET="TOPIC_PASSES"
```

The services are `ingestion`, `parsing`, `chunking`, `extraction`, `topics`,
`questions`, `assessment` and `platform`
([configuration.md](configuration.md)).

## Schema

| Target | Does |
|---|---|
| `make migration m="add the dropped counts"` | Write a revision from the models. Read it before applying: autogenerate misses triggers, backfills and anything ordered |
| `make schema` | Apply everything outstanding |
| `make schema-status` | Where the database is |
| `make schema-down` | Take the newest revision back off (from the first revision, this drops every table, `archived_rows` included). Refuses unless `CONFIRM` names the database |
| `make schema-reset` | Drop every table and rebuild. **Irreversible** |
| `make schema-stamp` | Adopt a database that already holds the tables |

## Review and evaluation

| Target | Does |
|---|---|
| `make review-push-facts` / `review-pull-facts` | Send a sample of facts to Argilla. Bring the verdicts back |
| `make review-push-topics` / `review-pull-topics` | The same for topic labels (every topic is pushed) |
| `make review-push-questions` / `review-pull-questions` | The same for questions |
| `make review-status` | How much has been looked at |
| `make review-delete` | Delete this database's three review datasets. **Irreversible**: pull first. What `make wipe` runs |
| `make review-all` | Every artefact of every kind, not a sample |
| `make eval-upload` | Put the golden cases in Phoenix |
| `make eval-score` | Score the served model against them, and record it |
| `make prompts-publish` | Republish every recorded prompt to Phoenix |
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
| `make phoenix-retention` | Set Phoenix's trace retention to `PHOENIX_TRACE_RETENTION_DAYS` days (30 where unset), because a prompt holds a passage of a document. Run by `make up` and `make dev` |
| `make phoenix-prune` | Delete this database's projects in which no work happened (`ALL_DATABASES=1`: every database's). **Irreversible**, and asks nothing: it names at most 25 projects, then deletes them |
| `make phoenix-purge` | Delete every project of this database (names end in `__<database>`; `ALL_DATABASES=1` takes every database's) but `default`, and every dataset of this database. What `make wipe` runs |
| `make phoenix-purge KEEP=golden CONFIRM=<database>` | The same, but leave the datasets and their experiments |
| `make dagster-wipe` | The runs this database launched (the corpus job tags each) and their event logs. `ALL_DATABASES=1` takes every run |

`prune` takes a project only when every span in it is a model call and it
could read every span, and never `default`.

## Tests and checks

| Target | Runs |
|---|---|
| `make test` | Everything that gates. Starts containers of its own |
| `make check` | An alias for `make test` |
| `make test-fast` | Only the fast layers: no spaCy, no pyright, no containers |
| `make test-unit` | Everything but integration, smoke, eval and perf |
| `make test-integration` | The container layers, end to end aside |
| `make test-e2e` | One document through every stage to the workbook export |
| `make test-golden` | Real PDFs through the real converter and chunker, against the snapshots in `tests/golden/snapshots`. Slow, offline, fails where a weight is missing. `make test` leaves it out |
| `make golden-refresh` | Rewrite those snapshots after an intended change. Read the diff before committing |
| `make test-smoke` | Build both images and look inside them |
| `make test-eval` | Score the served model against the golden passages. Never gates |
| `make test-perf` | Time the ceilings the code names. Never gates |
| `make test-coverage` | The gating layers, with a coverage report |
| `make mutation` | Whether the tests would notice a gate changing. Takes hours |
| `make lint` | ruff check and format check |
| `make format` | Apply every fix ruff can make |
| `make typecheck` | pyright, at zero |
| `make audit` | Known advisories (OSV) against both image locks and the host `poetry.lock`. Fails on one, except an entry in `configs/audit-accepted.txt` (`AUDIT_ACCEPTED=` names another file) whose review-by date has not come. Linux only |
| `make lint-imports` | The two architecture rules, as import-linter contracts |
| `make deps` | A declared dependency nothing imports, and an import nothing declares |
| `make lock` | Rewrite `backend/api/requirements.lock` and `frontend/requirements.lock` under the pins of `poetry.lock` |

`lint` and `format` cover `backend`, `frontend`, `telemetry`, `orchestration`,
`review`, `evaluation` and `tests`. `typecheck` covers the same but `tests`.

The nightly workflow also runs `test-perf`, `mutation`, `make audit` and `make
test-eval`, and keeps differing golden conversions as the
`golden-snapshots-linux` artifact. `[tool.mutmut]` in `pyproject.toml` sets
what mutation covers.

## Cost
```bash
make estimate                             # before a run: time, calls and USD of the rows still to do
make estimate DRAINS=questions=2,extract=2
make spend LOG=run.log                    # totals from a captured log
make spend LOG=run.log SINCE=2026-09-19   # one day of it
make spend-by-shape LOG=run.log           # split by model and judgement
```

`make estimate` multiplies the rows still to do by what a row of each stage
took in the reviewed build ([Sizing a corpus](operations.md#sizing-a-corpus)).
`DRAINS` divides a stage's time, not its spend, and more than two drains of
the model stages need a larger provider quota. `LOG` is required and names the
text log a drain wrote to a terminal (`make questions | tee run.log`), not the
shipped JSON. For a run in progress, use Grafana's **2 · What each stage is
doing** dashboard or Phoenix.

## Orchestration
| Target | Does |
|---|---|
| `make runs` | The sensor, the schedule and the last five runs |
| `make pipeline` | Every stage but the topic fit once, as a recorded Dagster run |
| `make auto` | Start the `arrivals` sensor: an upload starts a run on its own. Ships stopped |
| `make manual` | Stop it again |
| `make dagster-dev` | Run the code location on the host |

`pipeline` runs the stages of `make corpus` in the container workers. It skips
the bridge pass (`make extract-bridge MISSING=1`) and the release draw, and
the workers call `LLM_CONTAINER_MODEL` at `OLLAMA_CONTAINER_URL`, not `.env`'s
`LLM_MODEL`. Run `make questions-balance` after it ends. `POST /pipeline/run`
is `make pipeline`, and `PUT /pipeline/automation` is `auto` and `manual`.
