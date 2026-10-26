# Facts

Turns passages into facts: short written statements, each citing the exact text
that supports it. A statement that fails a check is stored with the code that
refused it, because the share that failed measures how well the reading went.

| Kind | What it is |
|---|---|
| `atomic` | One claim, from one sentence, citing it by number |
| `summary` | Two or three sentences standing in for a whole passage |
| `outline` | The points that passage makes, one bullet each |
| `bridge` | One claim no single passage states |

## What it does

Two passes run independently.

The passage pass is a queue. One passage is claimed at a time, routed to a
reader by its block type, and read for its claims and then its digest. All
facts are checked and written in one transaction that marks the passage done.

The bridge pass is not a queue. Its unit of work is a pair of linked passages.
`make extract-bridge` finds the links, caps them per topic and writes what they
yield. Topics must be fitted first.

A second bridge pass replaces the bridges in its scope, so it refuses, deleting
nothing, while an accepted question cites one of them. `FORCE=1` replaces them
anyway, and those questions are rejected as `source_changed` and kept.
`MISSING=1` deletes nothing and reads only the topics holding no bridge yet;
`make corpus` runs it that way. A pass narrowed by `TOPIC`, `SHA` or `PASSAGE`
clears only the bridges headed in the topics it reads again. The pass asks the
model one question first, and deletes nothing if it does not answer.

`make extract-revalidate` re-judges stored facts without a model call, so a
change to the checks reaches a corpus extracted earlier. It leaves alone the
`over_cap` and `duplicate` refusals, which no check reaches, and any fact whose
citation recorded no sentence. A refusal it validates then meets the duplicate
gate and the cap. `make extract-recap` re-applies the cap, and
`make extract-dedup` re-decides the duplicates.

### Step 1: Claim a passage

`SELECT … FOR UPDATE SKIP LOCKED` on `passages.extract_status`. A later run
sweeps a claim that outlived its lease, which all stages share; see
[`backend/stages/`](../stages/README.md).

### Step 2: Skip what asserts nothing

A passage is skipped, and marked read with nothing found, when:

- it has no numbered sentences, so nothing can cite it;
- its block type is `document_index` or `code`;
- it is its own heading;
- none of its sentences has a finite verb (a caption, a bare list fragment);
- it carries a copyright notice;
- it reads as an index, a bibliography or a contents page: long for the claims
  and list items it carries, and dense with digits (`_CHARS_PER_CLAIM` and
  `_NUMERIC_WORDS` in [`service.py`](service.py)).

A table is exempt from the last four, because it is read from its cell grid.
It is skipped when more than half of its filled cells are identifiers (`TA-BO1`,
`K2`, a tick; `_CODE_CELLS` in [`service.py`](service.py)). A bare figure
(`5`, `12.50`) or one after a currency (`SEK 25`) is a value.

### Step 3: Read the claims

- A `table` goes to the deterministic reader, with no model call. It labels
  each value cell with every header above it and to the left, requires both a
  row and a column label, and cites the numbered Markdown line the value sits
  in. Prose outside the grid that carries a finite verb goes to the model.
- Everything else goes to the model. It sees one passage's numbered sentences
  and heading trail, and answers with a statement plus the numbers of the
  sentences it came from. The evidence is resolved from the numbers.

A fact is the smallest statement that is as true, and as strong, on its own as
in the passage. A sentence is split only where each part holds alone. A set
closed by "only", conditions needed together, and a rule with its exception
each stay one fact. A list item repeats its lead-in and cites its sentence.
Claims about the document itself (how it is published or laid out) are left
out.

### Step 4: Read the digest

One call produces both the `summary` and the `outline`, so naming both in
`EXTRACTION_KINDS` costs no more than naming one. A passage with fewer than two
claims is not digested. A list item counts as a claim. `EXTRACTION_DIGEST_MODEL`
names a model for this call.

A digest is optional. When the model cannot give one, the passage still
finishes `extracted` with its atomic facts, and `extract_error` says
`digest failed: <reason>`. `make extract-digests` (`make corpus` runs it after
`extract`) claims those passages and every extracted passage of
`EXTRACTION_DIGEST_MIN_CHARS` or more that holds no digest. It calls only the
digest model and replaces only the summary and the outline. A digest that fails
again keeps its note and is tried on the next run. A digest model unreachable
for five passages in a row (`STOP_AFTER`) is not asked again in that drain.
With no digest kind in `EXTRACTION_KINDS`, the command says so and exits 0.

### Step 5: Check everything

Every check is structural, and none reads a similarity. The one similarity
threshold is the `duplicate` refusal below. A citation naming nothing that
exists is `evidence_absent`, and no further check runs. Otherwise the checks the
kind calls for run, and the first failure wins:

| Check | Refuses | `atomic` | `summary` | `outline` | `bridge` |
|---|---|:-:|:-:|:-:|:-:|
| citation resolves | `evidence_absent` | ● | ● | ● | ● |
| not copied | `copied` | ● | | | |
| two points or more | `not_listed` | | | ● | |
| asserts something | `asserts_nothing` | ● | ● | | ● |
| exactly one claim | `not_atomic` | ● | | | ● |
| nothing invented | `unsupported_addition` | ● | ● | ● | ● |
| no dangling pronoun or demonstrative | `unresolved_reference` | ● | | | ● |
| shorter than its passage | `not_condensed` | | ● | ● | |
| rests on two passages | `not_bridging` | | | | ● |

A statement the deterministic reader composed faces only `copied`.

`unsupported_addition` compares numbers and proper nouns only. A number is read
in any spelling (`1st` and `1 st`, `two` and `2`), and a proper noun is
lemmatised. A fact may rest on the sentences it cites, the passage's heading
trail and the document's title. A name or number found only in an uncited
sentence is an addition. So is a figure only the rest of the passage states,
when the cited sentences state another of its kind: "costs EUR 2" for a cited
"costs EUR 5". `not_bridging` also refuses a statement naming the numbered
heading of a cited passage ("Section 7"), because that is a claim about the
document.

`unresolved_reference` refuses a pronoun or demonstrative that points outside
the statement. A pronoun is resolved when an earlier noun outside its own
clause agrees with it ("The card is blocked if it is reported stolen"). A noun
of its own clause never resolves it ("The operator must return it"). A
demonstrative, a pronoun opening the statement, and a noun whose modifier points
outside ("Such a card", a plural "the following fees") are refused.

An atomic statement refused as `not_atomic` is sent back to the same model once,
in one more call for the passage, under a prompt of its own. The model sees the
numbered sentences, the refused statements and the reason for each, and writes
each claim as a fact of its own. What comes back faces the same checks and the
`duplicate` gate, but not the cap. The original refusals are stored. A passage
with no `not_atomic` refusal costs no extra call, and a repair call that fails
leaves the refusals standing and is logged rather than failing the passage.

Two more refusals come from the service, not from a check:

- `duplicate`: the corpus already holds the statement.
  `EXTRACTION_DUPLICATE_COSINE` is how alike two may be. A candidate is probed
  through the HNSW index against every validated passage fact already stored in
  the corpus of its own language and kind that carries a vector, bar those
  citing only the passage being re-read, and against facts of another kind this
  passage kept. The refusal names the stored fact it repeats (`twin_id`) and
  writes nothing onto it. Two atomic facts of one passage, a bridge, and facts
  naming other numbers are never twins.
- `over_cap`: `EXTRACTION_MIN_OTHER_SHARE` is a floor on the share of a
  passage's facts that are not atomic, which caps the atomic ones. The cap is
  never below the passage's sentences plus its list items. Facts asserting a
  number, date or name are kept first. Composed and repaired facts do not count
  against it.

Two drains side by side (`extract-worker` containers, or a host drain beside
one) each probe before either stores. The store therefore takes a lock for each
language and kind among a passage's validated facts, inside its transaction, and
judges them again against what the other drain committed.

Deleting a document leaves each duplicate of its facts refused against a fact
that is gone (`twin_id` set NULL). `make delete` and `make delete-derived` run
`extract-dedup`, which gives those facts back. After a deletion through the API
or the UI, the worker replays the dedup when its queue is empty; with no worker
running, run `make extract-dedup`. It is also the recovery when the replay of a
`make delete` fails. `make extract-dedup` re-decides every stored refusal under
the current rule, gives back those the rule would no longer make, and re-judges
and re-caps their passages, with no model call. It, `extract-revalidate` and
`extract-recap` refuse to run while the `extract-worker` container drains the
queue.

### Step 6: Store

One transaction. The passage's existing citations are deleted and the new facts
written. A fact left citing nothing is deleted. Every fact gets one
`fact_passages` row per passage it rests on, the only route from a fact to a
passage, a document and a topic.

### Step 7: The bridge pass

Passages are paired by the documents' own links (`extraction/links.py`):

- a reference: a passage naming another section's heading ("Section 7",
  "Returns");
- a sibling: two sections under one parent heading;
- a shared term: one used by 0.5% of the language's passages, never fewer than
  two and never more than six. A passage keeps the eight partners it shares the
  most terms with.

A reference outranks a sibling, and a sibling outranks a term. Each passage
heads at most one pair, and a pair that already holds a stored bridge is not
offered. A topic is worth `EXTRACTION_BRIDGES_PER_TOPIC` pairs on the passages
that head them. A heading numbered before its word ("1.2 Returns") gives no
reference link.

The model sees the pair as `[P0]` and `[P1]`, each with numbered sentences and
its validated atomic facts, plus one line naming the link. It answers with one
bridge or `none` (the usual answer): a relation (defines, limits, consequence,
applies, parallel, contrast), one fact from each excerpt, the claim relating
them, and a question only both excerpts answer, with its short answer. A pair
with a passage holding no validated fact is not read. The model is told not to
compute, because a total nobody wrote down is refused as `unsupported_addition`.

`facts.bridge` stores the relation, the question, the short answer and the
heading passage (`head`), so a re-judgement tests the same thing. A trigger
deletes a bridge once any passage it rests on is gone.

## Inputs and outputs

**Reads:** `passages`, `documents.language`, `passage_topics` (bridge pass) and
the stored facts the `duplicate` probe compares against.

**Writes:** `facts` (one row per statement, refused ones included, with the
verdict, rejection code, model, prompt version and spaCy version),
`fact_passages` (one row per passage a fact rests on, with the cited sentences
and span), and on `passages` the `extract_*` columns and `embedding`.

For every `fact_passages` row with a recorded citation,
`passages.text[evidence_start:evidence_end]` runs from the first cited sentence
to the last.

| Route | Answers |
|---|---|
| `GET /facts` | One page of facts, narrowed by document, kind, method and a text search |
| `GET /facts/quality` | The figures under that same filter |
| `GET /facts/{id}/passages` | The passages one fact rests on |
| `GET /extraction/status` | The queue depth, and whether a worker is on it |
| `POST /extraction/{action}` | `start`, `stop`, `retry`, `rerun`, `reclaim` |
| `GET\|POST /extraction/{scope}/{value}/…` | The same, narrowed to one document or passage |

### Prompts

[`prompts.py`](prompts.py) is the catalogue. Each prompt is written to the
`prompts` table before the first claim, under the model it is sent to
(`EXTRACTION_MODEL`, or `EXTRACTION_DIGEST_MODEL` for the digest). The atomic
prompt is recorded as `<version>+cap<n>`, where `n` is the cap
`EXTRACTION_MIN_OTHER_SHARE` works out to. Read a prompt back with
`GET /prompts?service=extraction`, or in Phoenix.

A drain asks the reader's model and the digest model one question before it
claims anything. A one-off drain refuses to start if either will not answer, and
a watching worker waits until both do. See [`backend/llm/`](../llm/README.md).

## Configuration

Ten settings belong to this stage, in `configs/env/backend.env`. The rest are
shared: `LLM_*`, `NLP_*`, `EMBEDDING_MODEL`, `EMBEDDING_MAX_TOKENS` and
`DATABASE_*`.

| Setting | What it does |
| --- | --- |
| `EXTRACTION_KINDS` | Which digests the queue writes beside `atomic`, which is mandatory. `bridge` is accepted and ignored: `make extract-bridge` runs either way |
| `EXTRACTION_DIGEST_MAX_SHARE` | The longest a digest may be, as a share of its passage |
| `EXTRACTION_DIGEST_MIN_CHARS` | Shortest passage worth digesting |
| `EXTRACTION_BRIDGES_PER_TOPIC` | Groups one topic is worth |
| `EXTRACTION_BRIDGE_PASSAGES` | Passages one group holds. At least 2 |
| `EXTRACTION_MIN_OTHER_SHARE` | The floor a passage's non-atomic kinds keep |
| `EXTRACTION_DUPLICATE_COSINE` | How alike two facts may be |
| `EXTRACTION_DUPLICATE_FLOOR` | The cosine two unrelated facts score. Calibrates the stored confidence only |
| `EXTRACTION_MODEL` | A different reader. Unset means `LLM_MODEL` |
| `EXTRACTION_DIGEST_MODEL` | The model the digest call goes to |

Naming `summary` or `outline` adds one model call per passage. A change to
`EXTRACTION_KINDS` or either bridge setting affects the next run.
`EXTRACTION_DIGEST_MAX_SHARE` reaches stored facts with
`make extract-revalidate`.

### Commands

```bash
make extract-start                     # queue every passage never asked for
make extract                           # drain the queue here
make extract-status                    # passages by state, and facts held
make extract-stop                      # take back what has not begun
make extract-retry                     # return every failed passage to the queue
make extract-rerun CONFIRM=<database>  # read every passage again
make extract-revalidate                # re-judge stored facts; no model call
make extract-bridge                    # read every topic's groups for bridges
make extract-bridge FORCE=1            # even over cited bridges
make extract-bridge MISSING=1          # only topics holding no bridge
make extract-recap                     # re-apply the atomic cap; no model call
make extract-dedup                     # re-decide the duplicate refusals; no model call
make extract-embed                     # write vectors onto rows already stored
make extract-digests                   # digest passages that have none

make extract-retry PASSAGE=<id>        # narrow any of them but extract to one passage
make extract-rerun SHA=<sha256>        # or to one document
```

`extract-embed` does not apply the dedup gate.

A passage read again keeps a fact with the same kind, method, statement and
citations, along with its id, embedding and questions. A fact the new reading
does not repeat is deleted, and a question resting on it is rejected as
`source_changed`, never deleted.

## Tests

```bash
poetry run pytest tests/unit/extraction
make test-fast          # everything but spaCy, pyright and containers
make test-integration   # needs a container runtime
make test-eval          # needs LLM_MODEL and LLM_BASE_URL; never gates
```

| Layer | Holds |
|---|---|
| Unit | Every check on every kind, both readers, the passage gate, the bridge pass, revalidation and the config refusals |
| Integration | The SQL against a real Postgres, and the HTTP surface |
| Property | A verdict and its code always agree; a span always resolves |
| Regression | A golden table of candidates in both languages, with the verdict each should get |
| Static | `tests/static/test_facts_pinned.py` pins the settings, routes, check matrix and this README's sections, kinds and rejection codes. `tests/static/test_prompts_pinned.py` pins the prompts |
| Eval | A real served model against golden passages |
| Frontend | The Facts page against a scripted backend |

## Limits

- A number word outside the per-language number-word table is read as written.
- A bridge cannot aggregate. A total, difference or average appears in no
  passage, so it is refused.
- An outline is checked on its shape, not its grammar.
- A fact opening on "the following fees" is not refused when a figure counts
  the noun or a colon follows, even where the list is given elsewhere.
- A document name after a joined section number hides that number. In "Ziffer 4
  und 5 AGB" no Ziffer 5 link is read.
- With no topic fit, the bridge pass writes no bridge.
