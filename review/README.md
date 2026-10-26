# Review

Human review of what the models decided, through Argilla.

| Dataset | The decision | Lands in |
|---|---|---|
| `4-facts` | Does the statement follow from the evidence and stand on its own? | `facts.reviewed_verdict` |
| `5-topic-labels` | Is this a good name for these terms, and a subject worth asking about? | `topics.label`, `topics.include_in_coverage` |
| `6-questions` | Would somebody ask this, and is the answer right? | `questions.status` |

The number is the producing stage, as in Phoenix and Dagster
([`telemetry/pipeline.py`](../telemetry/pipeline.py)). The command line takes
the bare name: `--push facts`. Datasets pushed under old names are not
migrated.

Argilla holds a copy of the rows and the answers, and deleting a dataset
loses nothing from the pipeline. No container carries the client.

## Using it

```bash
make review-push-facts                 # a sample, spread over the verdicts
make review-pull-facts                 # write the submitted verdicts back
make review-push-topics
make review-pull-topics
make review-push-questions             # a sample, spread over the gates
make review-push-questions IDS=12,34,56  # exactly those rows
make review-pull-questions
make review-status                     # how much has been looked at, and who agreed

make review                            # push both samples and every topic
make review-all                        # every row still to review, not a sample
make pull                              # pull all three back
make review-delete CONFIRM=<database>  # delete the three review datasets, and no other
```

Push, review in the UI at `ARGILLA_API_URL`, then pull. The Assessment page
lists the questions the gates kept and the judge refused, each with its `IDS=`
command. Underneath:

```bash
python -m review.run --push facts
python -m review.run --push facts --all
python -m review.run --pull questions
python -m review.run --status
python -m review.run --delete
```

`--push`, `--pull`, `--status` and `--delete` are mutually exclusive, one
required. `--all` and `--ids` modify a push.

## What a record carries

Each record carries the judge's decision from [the evaluation
phase](../backend/assessment/README.md): a `judge` field with its reasoning,
and `judge_verdict` and `judge_disagrees` metadata (`not_judged` where the
phase has not run). `judge_disagrees=yes` marks an artefact the pipeline kept
and the judge refused. Neither is an answer key.

Metadata also carries a `language` (for a fact, that of the passage at its own
citation, or `unknown`). A question record adds:

- `kind` metadata (single, needs_both, compound). A compound question asks two
  things on purpose and is rejected if either half fails.
- A `categories` field listing its categories as `Categorization=category`,
  with `(query)` after one written as a search query, which is judged as one.
- For a follow-up, a `thread` field of the turns it follows, oldest first, and
  a `turn` term. It is not rejected for leaning on them.

## What a review produces

`review-status` reports, per dataset, the rows with a verdict and how often
the person and the model agreed:

```text
facts: <reviewed> of <total> reviewed (<accepted> accepted, <rejected> rejected); agreed with the model on <agreed> of them, <share>%
questions: 0 of <total> reviewed; nobody has looked, so there is no agreement to report
```

The person's verdict is `reviewed_verdict`, separate from the machine's
(`validated` for a fact, `rejected_reason` for a question). Accepting a
question a gate refused leaves `rejected_reason` in place. A `rejected` fact
binds: question generation never writes from it, and re-verify rejects a
question resting on it as `source_changed`. An `accepted` changes nothing,
and `extract-revalidate` leaves `reviewed_verdict` alone. A pull takes only
submitted answers, not drafts.

## A sample, or the corpus

A push sends `REVIEW_SAMPLE_SIZE` facts or questions, stratified over the
verdicts with at least one row per group, and topics whole. `--all` sends
every unreviewed fact or question. A row with a verdict, or answered in
Argilla and not yet pulled, is not sent again.

## Configuration

From [`configs/env/review.env`](../configs/env/review.env), in git:

| Setting | What it does |
| --- | --- |
| `REVIEW_SAMPLE_SIZE` | How many records one push puts in front of a reviewer, split across the groups |

From [`configs/env/deployment.env`](../configs/env/deployment.env) and `.env`:

| Setting | What it does |
| --- | --- |
| `ARGILLA_API_URL` | The host's address, derived from `ARGILLA_PORT` in `deployment.env` |
| `ARGILLA_API_KEY` | In `.env`. Argilla shows it under "My settings". Not `ARGILLA_PASSWORD` |
| `ARGILLA_WORKSPACE` | In `deployment.env`. One per deployment |

Argilla shares the logs' Elasticsearch. `ES_JAVA_OPTS` in
[`configs/env/elasticsearch.env`](../configs/env/elasticsearch.env) raises its
heap.

## One workspace, many databases

Dataset names carry the database (`6-questions__qa_generator`), and push,
pull and `make review-delete` touch only this database's datasets. A dataset
under a bare name from an earlier version is left alone: pull it before
upgrading, then push again.

## Tests

```sh
poetry run pytest tests/unit/review
```

[`tests/unit/review/`](../tests/unit/review) covers sampling, records, pulls
and the command line, without a network.

## Limits

- Reviewers who disagree are not applied. A pull logs the record ids, and both
  answers stay in Argilla.
- A push never empties a dataset. A pull applies an answer only where the row
  still reads as its record and the answer is newer than the row's last
  decision (creation, a verdict, or a status change).
- A topic answer without a name keeps the topic's name and `labelled_by`, and
  one without coverage keeps its coverage. A topics dataset created while the
  name was required still asks for one: pull, delete it, push again.
- A corrected topic name over 120 characters is not pulled. A pull logs the
  topic ids and leaves the answer in Argilla.
- A facts dataset created before v0.4.5 has no `language` metadata, and a
  questions dataset created before v0.4.3 has no `categories` field. A push
  drops the term with a warning: pull, delete the dataset in Argilla, push
  again.
