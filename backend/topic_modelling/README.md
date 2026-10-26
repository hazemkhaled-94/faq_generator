# Topic modelling

Finds what a corpus is about: groups of words that tend to appear together,
one model per language, built from the corpus's own vocabulary. Nothing is
pretrained, so no word list or domain model has to be supplied.

Question generation works one topic at a time. A corpus with no topics
generates no questions.

## What it does

For each language separately, the service builds a vocabulary from the
passages' content lemmas, drops terms that are too rare or too common, weights
the rest by tf-idf and factorises the passage-by-term matrix into
non-negative components. Each component is a topic. Every passage is scored
against the model, a served model names each topic, and the model is drawn as
a figure.

Only passages carrying a validated fact are fitted, where a language has any.
Each language has its own model, so topic numbers mean something only within a
language.

A fit is always the whole corpus. The components are estimated jointly, so one
topic cannot be refitted, and adding a document makes every topic stale. This
stage has no per-item controls and no `start`: one fit request replaces the
model of every language it fits.

### The steps

`topics` is both the queue and the result. A row with a NULL `topic_index` is
an outstanding request. A row with an index is a topic.

1. Claim the request: the oldest row that is outstanding and `pending`, with
   `FOR UPDATE SKIP LOCKED`.
2. List the languages in `passages.language`. A passage with no language is in
   no model, and `GET /topics/fit` reports how many. If no passage has a
   language, the fit fails and says to chunk the corpus first.
3. Build the vocabulary from `passages.lemmas`, streamed by id in batches of
   500. A language whose passages are one text, or copies of it, is not
   fitted. It gets one topic holding them.
4. Filter the vocabulary. `filter_extremes` drops terms in fewer than
   `TOPIC_NO_BELOW` passages or more than `TOPIC_NO_ABOVE` of them. The fit
   fails on an empty vocabulary, and on one whose terms all have an idf of
   zero. A language with fewer distinct passages than two topics' worth of
   `TOPIC_PASSAGES_PER_TOPIC` (or than `TOPIC_NUM_TOPICS` with that sizing
   off), whose passages the filter cannot tell apart, gets the one topic of
   step 3 instead of failing.
5. Fit `Nmf` with the components `TOPIC_NUM_TOPICS` and
   `TOPIC_PASSAGES_PER_TOPIC` allow and `TOPIC_PASSES` passes, in eight draws
   seeded from `TOPIC_RANDOM_STATE` on. The draw kept is the one whose topics'
   members are most alike.
6. Read out the `TOPIC_TOP_TERMS` highest-weighted terms of each topic.
7. Score every passage. A membership is every topic whose weight is at least
   `TOPIC_RELATIVE_WEIGHT` times the passage's strongest, which is always
   kept. Weights are clamped to 1.0.
8. Carry over what a person decided. `carry_labels` matches an old topic to a
   new one when each holds more than half of the other's dominant passages,
   counted over the passages both fits hold. A person's name, coverage choice
   and decision time are carried. A model's name is not. A decision matching
   no topic is logged as a warning and counted on the span as
   `topic.decisions_dropped`. A decision made while the fit runs is carried
   too, but an undo made then, and a `make review-pull-topics` decision dated
   before the fit was requested, are not.
9. Name the unnamed topics. Only topics with no label are offered to the
   model, 25 to a call, each call told the names the earlier calls gave. A
   call the model cannot answer is split once into two halves. The model sees
   each topic's terms and up to four excerpts (passages the topic is strongest
   in, those with a validated fact first), and is told which language to answer
   in. A trailing phrase shared by more than half of three or more names, such
   as `im Fussball` or `in banking`, is removed. A topic the model flags
   `no_subject` is stored with no name. A topic that is no passage's strongest
   is never offered. `labelled_by` records `person` or the model.
   `make topics-name` names the topics a fit left unnamed, with no refit.
10. Replace the fitted languages in one transaction. A language the fit
    skipped keeps its topics and memberships. A language no passage carries
    any more loses its topics, and its figure and model move to the `archive`
    bucket. A passage placed in no topic joins its language's topic with the
    nearest centroid. A passage with no vector stays out. If the request was
    withdrawn or claimed again meanwhile, the fit writes nothing.
11. Keep the model and draw the figure. This runs after the topics are
    written, so a failure is logged and left. The previous model and figure go
    to the `archive` bucket first.

On failure, the previous topics stay as they were, beside the reason. A
language the fitter refuses is logged and left out. The run fails only if no
language produced a model.

Where `LLM_MODEL` is set, the worker asks the naming model (`TOPIC_MODEL`, or
`LLM_MODEL` without one) one question before claiming the request. See
[`backend/llm/`](../llm/README.md).

### Limits of the output

Figures are in [measurements](../../docs/measurements.md).

- Title-cased foreign text reaches the German vocabulary.
- German compounds fragment the vocabulary: `Gewerbeimmobilienmärkte` is one
  term where English writes three words.
- Some topics are document apparatus, such as table headers. A person
  excludes them with `include_in_coverage`, so a refit needs a few minutes of
  review.

## Inputs and outputs

**Reads:** `topics`, `passages` (language, lemmas, text, block type) and
`facts.validated`.

**Writes:**

- `topics`: one row per topic per language.
- `passage_topics`: one row per passage-topic pair kept by the relative
  weight.
- `topics/<database>/<language>.npz` in the `models` bucket, the factorisation.
- `topics/<database>/<language>.html` in the `export` bucket, the figure.

`<database>` is the path of `DATABASE_URL`. The previous fit's files move to
the `archive` bucket. See
[`blob_store/`](../blob_store/README.md#the-five-buckets).

| Route | Answers |
|---|---|
| `GET /topics/status` | Queue depth by status |
| `GET /topics` | Every topic with how much of the corpus it holds |
| `GET /topics/fit` | The model's state, one entry per language |
| `GET /topics/visualisation/{language}` | One language's figure. 400 `invalid_language`, 404 `no_visualisation` |
| `PATCH /topics/{topic_id}` | Records a label and a coverage choice, and when they were made. A field left out is left as it is |
| `POST /topics/discover` | Queues a fit. 202 |
| `POST /topics/stop` | Withdraws a queued fit |
| `POST /topics/retry` | Returns a failed fit to the queue |
| `DELETE /topics?confirm=true` | Deletes every topic, membership, stored model and figure into the archive, which `make restore-documents` restores from |

**Command line:** `python -m topic_modelling.run`. `--status`, `--discover`,
`--stop`, `--retry` and `--delete` do what their routes do. `--visualise`
writes the figures, and `--render` redraws them from the stored models.
`--discover` queues and drains in one go. `--watch` is what the worker runs.

`make topics-discover` runs a fit on the host, first or refit.
Neither `make corpus` nor the Dagster corpus job requests one. Bare
`make topics` drains only a fit already queued. `make topics-status` reports
how many passages are in no topic.

A refit keeps `question_status` as `generated` on a new topic that matches an
old generated one and holds no new passage.

A fit request, `DELETE /topics` and `make topics-delete` are refused (409
`questions_running`, or exit 1) while a topic holds a live question claim, one
the worker beat within the queue's lease. A fit that finds one at the end fails
with the same message. `make topics-retry` returns it to the queue.

After a refit that changed the topics, run `make questions-reverify` and then
`make questions-rescore`, in that order, so stored questions take the new topic
scope and band, and one that lost a citation is caught as `source_changed`
first.

### The database

`topics` carries two queues: `status` is this stage's and `question_status` is
question generation's. A CHECK requires a `modelled` row to have an index, a
language and at least one term. `(language, topic_index)` is unique.

`passage_topics` cascades from both sides, so re-chunking a document removes
its memberships and leaves the model stale, which `GET /topics/fit` shows. The
dominant topic is derived, not stored.

## Configuration

Settings come from the environment, overridden by values stored on the
settings page, with no default in code. A watching worker rebuilds when one
changes. `TOPIC_MODEL` and `LLM_MODEL` are served read-only and never stored,
so changing one needs a restart. Values are in
[`configs/env/backend.env`](../../configs/env/backend.env), and `LLM_MODEL`'s
in `.env`.

Changing any of the first eight changes what the topics are. There is no
partial refit: run `make topics-discover`.

| Setting | What it does |
| --- | --- |
| `TOPIC_PASSAGES_PER_TOPIC` | How many passages one topic is worth. Above 0 it turns `TOPIC_NUM_TOPICS` into a ceiling and fits `passages / this`, at least 2, counting the passages that carry a validated fact. `0` turns it off |
| `TOPIC_NUM_TOPICS` | Topics per language, and the ceiling above. At least 2. Shipped at 300 |
| `TOPIC_PASSES` | Times the factorisation walks the corpus |
| `TOPIC_RANDOM_STATE` | Seed of the first of the eight draws. The same passages in the same order give the same topics. A document deleted and chunked again (`make delete-derived`) returns under new ids and can regroup other documents' passages |
| `TOPIC_TOP_TERMS` | Terms stored as a topic's signature |
| `TOPIC_RELATIVE_WEIGHT` | The share of a passage's strongest weight another must reach to be stored. In `(0, 1)`. A stored row named `TOPIC_MIN_WEIGHT` stops the topic stage until it is deleted (see the settings README) |
| `TOPIC_NO_BELOW` | Drop a term appearing in fewer than this many passages |
| `TOPIC_NO_ABOVE` | Drop a term appearing in more than this share. In `(0, 1]` |
| `TOPIC_LANGUAGE_NAMES` | ISO code to language name, for the naming prompt |
| `TOPIC_MODEL` | The model that names a topic. Read only when `LLM_MODEL` is set |
| `LLM_MODEL` | What `TOPIC_MODEL` falls back to. Without it, topics are fitted but not named |

Fixed in code: excerpts per naming call (4), excerpt length (400 characters),
the figure's bar-chart length (30) and the streaming batch size (500).

## Tests

`make test` runs all of them.

| Layer | Covers |
|---|---|
| Unit | The fitter, the labeller, the visualisation, the service flow and reporting |
| Regression | One test per defect |
| Property | Every weight a probability, every passage placed or counted, a seeded fit reproducible |
| Integration | Both repositories against a migrated Postgres, and all nine routes |
| Frontend | The Topics page against a scripted backend |
| Static | The pinned surface |

The quality of the topics is not asserted. It is a measurement.
