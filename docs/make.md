# Make commands

Every target, grouped. `make` sources the same configuration the containers
read, so one value reaches both.

```bash
make help            # or just `make`
make help | grep -i topic
```

`help` reads the Makefile itself — a target's group is the section banner it
sits below and its description is the comment above it — so it cannot fall
behind. This page is the long form.

## First run

| Target | Does |
|---|---|
| `make setup` | Write `.env` and `configs/env/provider.env`, and fill in every placeholder |
| `make install` | The Python dependencies, the spaCy pipelines and Docling's weights |
| `make doctor` | Check the tools and the configuration, then ask the model one question |
| `make dev` | Certificates, every service, the schema and the Grafana grants |

`setup` is safe to run twice: it replaces `change_me_*` placeholders and
nothing else. It gives one secret per distinct placeholder and substitutes it
everywhere that placeholder appears.

`doctor` ends with a real call to the configured model, so an unknown model
id, an unreachable address or a stale credential fails here rather than on
the first passage of a run:

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

## The short list

| Target | Does |
|---|---|
| `make all` | Bring the stack up, wait for Dagster to list the corpus job, and launch it. The container workers drain every stage but the topic fit, which Fit all on the Topics page asks for |
| `make corpus` | Every stage but the topic fit, drained on the host in order, then the release draw and the judge, stopping at the first failure. For developing a stage. Incremental. Says how many passages are in no topic; `make topics-discover` fits them |
| `make pipeline-status` | Where the corpus has got to, every stage in one call |
| `make services` | Every container, whether it is listening, and where to open it |
| `make open` | The same, and open the application |
| `make review` | Push a sample of facts, topic labels and questions to Argilla |
| `make pull` | Pull every decision made there back into the database |

`make auto` hands the whole thing to Dagster — see
[Orchestration](#orchestration).

## Configuration and the container engine

Targets read `configs/env/backend.env`, `configs/env/deployment.env`,
`configs/env/provider.env` then `.env`, in the order the containers do. A
variable given on the command line beats them all:

```bash
make topics-discover TOPIC_PASSES=20
```

The Makefile re-applies command-line overrides after sourcing the files,
because sourcing would otherwise overwrite them.

The Makefile invokes `podman compose`. For Docker:

```bash
make COMPOSE="docker compose" up
```

`CONTAINER` is the engine itself, used by `lock`, which needs a build and a
run compose has no equivalent of.

## Starting and stopping

| Target | Does |
|---|---|
| `make dev` | Certificates, every service, wait for PostgreSQL, create the schema, then the grants `make up` makes |
| `make install` | `make install-python`, then `make docling-weights` |
| `make install-python` | Dependencies and the spaCy pipelines `NLP_MODELS` names, on the host alone. What CI's setup runs |
| `make docling-weights` | Download Docling's weights into the `models` volume parse-worker reads offline. Needs the container engine; fetches nothing already cached |
| `make up` | Start services, then grant Grafana's reader the five Phoenix tables the run dashboard queries, once Phoenix has made them |
| `make grafana-grants` | Those grants alone. Safe to run again |
| `make down` | Stop services, keep data, and remove dangling images |
| `make down-volumes` | Stop services and **delete all data** |
| `make certs` | Generate the TLS certificates Elasticsearch needs |
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
| `make logs-prune` | Not a follow: delete the log files nothing has written to for `LOGS_KEEP_DAYS`, on the `logs` volume and in `./logs` |
| `make logs-wipe` | Not a follow: delete every `qa-logs*` data stream and every log file. Stops unless Elasticsearch acknowledges the delete or holds no stream. What `make wipe` runs |

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
the shell and drains on the host.

## The five verbs every stage answers

Each is the same operation as the route beside it.

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
`podman compose … stop <worker>` that stops it. With no container engine
answering, or the stack down, it drains as before.

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
| `make topics-discover` | Ask for a fit over the whole corpus, and run it. Neither `make corpus` nor the corpus job does |
| `make topics` | Run any queued fit here, in the foreground |
| `make topics-status` | The topics held, any queued fit, and how many passages are in no topic |
| `make topics-stop` | Withdraw a queued fit |
| `make topics-retry` | Return a failed fit to the queue |
| `make topics-visualise` | Write each language's stored pyLDAvis page to `./topics/` |
| `make topics-render` | Redraw those pages from the stored models, without re-fitting. `CODE=de` for one |
| `make topics-delete` | Delete every topic and membership, any queued fit and the judge's verdicts on the topics. The figures and models go to the archive. Waits 5 seconds first |

### Narrowing to one item

Any verb narrows with `SHA`, `PASSAGE` or `TOPIC`:

```bash
make parse-start SHA=<sha256>     # queue one document for parsing
make chunk-rerun SHA=<sha256>     # rebuild one document's passages
make extract-start SHA=<sha256>   # queue every passage of one document
make extract-retry PASSAGE=<id>   # return one failed passage to the queue
make questions-start TOPIC=<id>   # write the questions for one topic
```

Parsing and chunking narrow to a document, extraction to a document or a
passage, question generation to a topic, topic modelling to nothing.

## Replaying a stage without redoing it

Re-derive what a stage computed over rows already stored, without the
expensive part:

| Target | Does |
|---|---|
| `make extract-revalidate` | Judge every stored fact again. No model call |
| `make chunk-revocabulary` | Re-read language and vocabulary. Only `passages.language` and `passages.lemmas` change |
| `make questions-reverify` | Put every stored question through the gates that need no model |
| `make extract-recap` | Re-apply the atomic cap `EXTRACTION_MIN_OTHER_SHARE` works out to |
| `make extract-dedup` | Re-decide every `duplicate` refusal under today's rule, and take out the citations a refusal added to the fact it repeated. No model call |
| `make extract-embed` | Write vectors onto passages and facts already stored. Does not apply the dedup gate |
| `make extract-bridge` | Read each topic's passage groups for claims spanning passages. Asks the model first and deletes nothing if it does not answer. Refuses while an accepted question cites a bridge it would replace; `FORCE=1` replaces them anyway |
| `make confidence-recalibrate` | Take every stored margin again after a change to `QUESTIONS_DUPLICATE_FLOOR` or `EXTRACTION_DUPLICATE_FLOOR`. No model call, and no verdict moves |

`chunk-revocabulary` and `extract-revalidate` take `SHA`;
`extract-revalidate`, `extract-recap`, `extract-dedup` and `extract-embed` take
`PASSAGE`;
`questions-reverify` takes `TOPIC`.

The alternative is destructive: `extract-rerun` calls the model again over
the whole corpus, and `chunk-rerun` deletes every passage of a document along
with the facts drawn from them. Without `SHA`, or `PASSAGE` for extraction,
both warn and wait 5 seconds first.

## Questions

| Target | Does |
|---|---|
| `make questions-balance` | Draw the balanced release out of what was accepted |
| `make questions-export` | Write the questions a filter selects to an `.xlsx` |
| `make questions-reverify` | Re-check stored questions; no model call |
| `make questions-rejudge` | Ask the verifier whether the passages settle each accepted unanswerable question, and reject those they do. **Calls the verifier model**; takes `TOPIC` |
| `make questions-runs` | Which runs there are, newest first |
| `make questions-diff` | Two runs side by side, on the gate that stopped each |
| `make questions-reclaim` | Return a topic a dead worker still holds. **Narrow it** |

```bash
make questions RUN_ID=b-gemma4-12b
make questions-diff RUNS="a-gpt-4.1 b-gemma4-12b"
```

### Getting the dataset out

`OUT` names the file and `FILTER` takes the same narrowing the Questions page
and `GET /questions` do. **There is no default scope** — ask for nothing and
you get everything, rejected rows included.

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

`questions-diff` reads live questions **and** archived ones, so a run
`questions-rerun` replaced still answers. A run listed `(deleted)` is being
read out of `archived_rows`.

```bash
make questions-reclaim TOPIC=473   # one topic, while a worker may be up
make questions-reclaim             # every one the stage holds
```

`reclaim` fills the gap between `retry`, which takes the failed, and `rerun`,
which skips what a worker holds. Narrow it while a worker may be up: nothing
can tell a dead claim from a live one.

It has a route now as well — `POST /{stage}/{scope}/{value}/reclaim`, with
`?confirm=true` needed for the unnarrowed form. See
[`backend/stages/`](../backend/stages/README.md).

## The evaluation phase

An LLM judge over every fact, topic and question, run after the pipeline and
never during it. Off unless `ASSESSMENT_ENABLED` is true in `.env`, and every
target says so and stops rather than quietly doing nothing.

**It decides nothing.** The verdict goes in a column of its own beside the
checker's, and no stage reads it. See
[`backend/assessment/`](../backend/assessment/README.md) for why it cannot
be a gate.

| Target | Does |
|---|---|
| `make assess-enrol` | Create the rows without queuing any, and say how many there are |
| `make assess-start` | Enrol and queue everything that has no verdict |
| `make assess` | Drain the judging queue here, in the foreground |
| `make assess-status` | The queue, and what the judge has said so far |
| `make assess-stop` | Take back what has not begun |
| `make assess-retry` | Return the artefacts the judge could not be reached for |
| `make assess-rerun` | Judge everything again, under the current templates |
| `make assess-reclaim` | Return an artefact a dead worker holds. **Narrow it** |

```bash
make assess-enrol                              # count the cost first
make assess-start ONLY=--only\ kind=question   # the deliverable only
make assess
```

A fact costs three model calls, a topic two and a question six.
`ASSESSMENT_KINDS` and `ASSESSMENT_SAMPLE` in `configs/env/backend.env` are
the dials, and the default is a sample per kind rather than a corpus.

A failure here is the **model** being unreachable, not an artefact being bad:
a judgement that came back as a refusal is recorded as one and is not a
failed row.

## Documents

Documents are ingestion's, not a stage's. **All of these are irreversible.**

| Target | Does |
|---|---|
| `make documents` | List every document with its parse state |
| `make delete SHA=<sha256>` | Delete a document and everything derived from it. A question that also rests on another document stays, rejected as `source_changed` |
| `make delete-derived SHA=<sha256>` | Delete its passages, and with them their memberships, the facts and questions resting on them alone, follow-ups and assessments |
| `make wipe` | Every document, the topics, and the four services that describe them. Waits 5 seconds first |
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
| `golden` | The Phoenix datasets and the experiments under them. `make eval-upload` puts them back |
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
| `make restore-documents` | Without `SINCE`, when each deletion happened. With `SINCE=<time>`, put back every row and object archived from then on. Run it before `archive-purge` |
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
| `make schema-down` | Take the newest revision back off. From the first revision that drops every table, `archived_rows` included. Waits 5 seconds first |
| `make schema-reset` | Drop every table and rebuild. **Irreversible** |
| `make schema-stamp` | Adopt a database that already holds the tables |

**Read the generated revision before applying it.** Autogenerate does not see
a trigger, a data backfill, or anything ordered.

## Review and evaluation

| Target | Does |
|---|---|
| `make review-push-facts` / `review-pull-facts` | Send a sample of facts to Argilla; bring the verdicts back |
| `make review-push-topics` / `review-pull-topics` | The same, for topic labels |
| `make review-push-questions` / `review-pull-questions` | The same, for questions |
| `make review-status` | How much has been looked at |
| `make review-delete` | Delete the three review datasets: facts, topic labels and questions. A dataset under another name is left. **Irreversible** - pull first. What `make wipe` runs |
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
| `make phoenix-prune` | Delete the projects in which no work happened. **Irreversible**, and asks nothing first: it names at most 25 of the projects it takes, then deletes them |
| `make phoenix-purge` | Delete **every** project but `default`, whatever it holds, and every dataset. What `make wipe` runs, and what `prune` will not do |
| `make phoenix-purge KEEP=golden` | The same, but leave the datasets and their experiments |
| `make dagster-wipe` | Every run Dagster remembers, and the event log under each |

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
| `make test-integration` | The container layers |
| `make test-e2e` | One document through every stage, in this process |
| `make test-smoke` | Build both images and look inside them |
| `make test-eval` | Score the served model against the golden passages. Never gates |
| `make test-perf` | Time the ceilings the code names. Never gates |
| `make test-coverage` | The gating layers, with a coverage report |
| `make mutation` | Whether the tests would notice a gate changing. Hours |
| `make lint` | ruff check and format check |
| `make format` | Apply every fix ruff can make |
| `make typecheck` | pyright, at zero |
| `make audit` | Known advisories against the two locks |
| `make lint-imports` | The two architecture rules, as import-linter contracts |
| `make deps` | A declared dependency nothing imports, and an import nothing declares |
| `make lock` | Rewrite `backend/api/requirements.lock` |

`lint`, `format` and `typecheck` cover `backend`, `frontend`, `telemetry`,
`orchestration`, `review`, `evaluation` and `tests`.

`test-perf` and `mutation` are the two nightly ones. Which modules and layers
mutation covers is `[tool.mutmut]` in `pyproject.toml`; `mutmut browse` reads
the survivors.

## Cost

```bash
make spend LOG=run.log                    # totals from a captured log
make spend LOG=run.log SINCE=2026-09-19   # one day of it
make spend-by-shape LOG=run.log           # split by model and judgement
```

`LOG` is **required** and names the text log a drain wrote to a terminal —
`make questions | tee run.log` — not the shipped JSON. For a run happening
now, use Grafana's **2 · What each stage is doing** dashboard or Phoenix.

`spend-by-shape` splits by the model that answered and the Pydantic class the
call had to return, which is what each judgement costs.

## Orchestration

The asset graph already chains the stages. These decide **when**.

| Target | Does |
|---|---|
| `make runs` | The sensor, the schedule and the last five runs |
| `make pipeline` | Every stage but the topic fit once, as a recorded Dagster run |
| `make auto` | Start the `arrivals` sensor: an upload starts a run on its own |
| `make manual` | Stop it again |
| `make dagster-dev` | Run the code location on the host |

`auto` is the unattended mode and ships stopped. `pipeline` does the work of
`make corpus` without the release draw, in the container workers rather than
on the host, and survives the terminal closing.

All four have an equivalent through the api, for a deployment nobody drives
from a terminal: `POST /pipeline/run` is `make pipeline`, and
`PUT /pipeline/automation` is `auto` and `manual`. The Run button on the
Documents page is the first of those.
