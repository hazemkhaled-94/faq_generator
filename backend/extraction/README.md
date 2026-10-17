# Facts

Turns passages into facts: short written statements, each carrying a pointer
back to the exact text that supports it.

A statement that fails a check is stored with the code that refused it rather
than dropped, because the share that failed is how the reading is measured.

The corpus is read four ways, all stored in the same table:

| Kind | What it is |
|---|---|
| `atomic` | One claim, from one sentence, citing it by number |
| `summary` | Two or three sentences standing in for a whole passage |
| `outline` | The points that passage makes, one bullet each |
| `bridge` | One claim no single passage states |

## What it does

Two passes, and they are independent.

The **passage pass** is a queue. One passage is claimed at a time, routed to
a reader by its block type, read for its claims and then for its digest.
Everything both readers propose is checked, and the lot is written in one
transaction that also marks the passage done.

The **bridge pass** is not a queue: its unit of work is a group of passages
the topic model put together. `make extract-bridge` walks every topic, forms
groups, and writes what they yield. Topics must be fitted first. A second
pass replaces the bridges in scope, so it refuses, deleting nothing, while an
accepted question cites one of them; `FORCE=1` replaces them anyway, and
those questions are rejected or deleted with them. `MISSING=1` deletes
nothing and reads only the topics holding no bridge yet: `make corpus` runs it
that way after the topics are known, so a rebuild writes bridges and a second
one leaves cited ones alone. It asks the model one
question first, and deletes nothing if the model does not answer.

`make extract-revalidate` re-judges stored facts without calling a model,
which is how a change to the checks reaches a corpus extracted before it. It
leaves alone the `over_cap` and `duplicate` refusals, which no check
reaches, and any fact whose citation recorded no sentence. A refusal it
validates was refused before the dedup gate and the cap could see it, so it
meets both now: probed in id order against the validated facts and the ones
validated earlier in the pass, refused as a `duplicate` on a twin, and its
passage re-capped.
`make extract-recap` re-applies the cap, and `make extract-dedup` re-decides
the duplicates.

### Step 1 — Claim a passage

`SELECT … FOR UPDATE SKIP LOCKED` on `passages.extract_status`. The claim is
timestamped rather than held as a row lock, and a later run sweeps a claim
that outlived its lease. The lease is the one every stage shares; see
[`backend/stages/`](../stages/README.md).

### Step 2 — Skip what asserts nothing

A passage is skipped, and marked read with nothing found, when:

- it has **no numbered sentences** — nothing can cite it;
- its block type is **`document_index` or `code`** — navigation rather than
  content;
- it **is its own heading**;
- **none of its sentences carries a finite verb** — a caption, a navigation
  line, a bare list fragment;
- it carries a **copyright notice** — it is about the document;
- it reads as **an index, a bibliography or a contents page** — long for the
  claims it carries, and dense with digits. The shares are
  `_CHARS_PER_CLAIM` and `_NUMERIC_WORDS` in [`service.py`](service.py).

A table is exempt from the last four, because it is read from its cell grid.
It is not exempt from one more: a grid whose filled cells are more than half
identifiers — `TA-BO1`, `K2`, `1.7`, a tick — states nothing a reader would
look up. The share is `_CODE_CELLS` in [`service.py`](service.py).

### Step 3 — Read the claims

Routed by block type:

- **`table` → the deterministic reader.** Walks the cell grid and labels each
  value cell with every header above it and to the left. No model. Both a row
  and a column label are required. Each fact cites the numbered Markdown line
  its value sits in.
- **everything else → the model.** Shown one passage's numbered sentences and
  its heading trail, it answers with a statement plus the *numbers* of the
  sentences it came from. The evidence is resolved from the numbers
  afterwards; nothing is copied.

A fact is the smallest statement that is as true, and as strong, on its own
as it is in the passage. So a sentence is split only where what it says holds
for each part: a set closed by "only", conditions needed together, and a rule
with its exception each stay one fact, because any one part alone says
something the passage does not. Each item of a list says its lead-in's
situation again and cites the lead-in's sentence too. "Should" stays
"should". Claims about the document itself - how it is published, laid out
or obtained, and how its changes are marked - are left out.

A table passage that also carries prose outside its grid gets both: the
deterministic reader for the grid, and the model shown only the prose lines
that carry a finite verb.

### Step 4 — Read the digest

One call produces both the `summary` and the `outline`, so naming both in
`EXTRACTION_KINDS` costs no more than naming one. A passage carrying fewer
than two claims is not digested.

`EXTRACTION_DIGEST_MODEL` names a model of its own; unset it uses whichever
model reads the passage.

### Step 5 — Check everything

Every check is structural rather than lexical. A citation is an index, so it
cannot be half-right, and no check reads a similarity: the one similarity
threshold in this service is the `duplicate` refusal below.

The citation is resolved first — a citation naming nothing that exists is
`evidence_absent` and no further check runs. Then the checks the kind calls
for, first failure winning:

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

Two more refusals are the service refusing what the checks passed:

- `duplicate` — the corpus already holds the statement.
  `EXTRACTION_DUPLICATE_COSINE` is how alike two may be, and a candidate is
  probed through the HNSW index against every validated passage fact in the
  corpus of its own language and kind that carries a vector, bar those
  citing only the passage being re-read, **and** against the facts of
  another kind this passage already kept - a summary or an outline
  repeating one of its claims. Two atomic facts of one passage are never
  twins: two items of a list, two conditions, a least and a most differ by
  a word and are two claims. A bridge is never its twin, and nor is a fact
  naming other numbers - another value, or the same one a different number
  of times, a number word read as the value it names. The index is read
  for the five nearest and the closest naming the candidate's numbers is
  taken, so a nearer fact of another value does not hide a repeat. Its scan
  reads on past the facts of another language or kind, so a language
  holding a small share of the corpus is probed as fully as the rest. The bar
  sits near identity: the vector is read off the bare statement, and two
  statements about one subject score high on the subject alone. The
  refusal names the stored fact it repeats and writes nothing onto it: the
  stored fact rests on its own passage alone, so a passage it was refused
  against never counts towards the scope of a question asked of it.
  `make extract-dedup` re-decides every stored refusal under the rule as it
  stands, giving back the ones it would no longer make with the reading
  taken against today's bar, or none, and takes out the
  citations an earlier version's refusal added to its twin, rebuilding that
  fact's evidence from the citation it keeps. No model is called.
  Nothing ties a stored fact to the passages refused against it, so
  deleting its document leaves each repeat refused against a fact that is
  gone. `make delete` and `make delete-derived` therefore run
  `extract-dedup`, which gives the repeat back. A deletion through the API
  or the UI does not, so run `make extract-dedup` after it; it is also the
  recovery when the replay of a `make delete` fails, since the document is
  gone by then. The passages of the refusals it gives back, and no others,
  are then judged again and re-capped, as `make extract-revalidate` and
  `make extract-recap` would: a fact given back was judged when it was
  extracted and never counted against the cap. `extract-dedup`,
  `extract-revalidate` and `extract-recap` each refuse to run while the
  `extract-worker` container drains the queue.
- `over_cap` — `EXTRACTION_MIN_OTHER_SHARE` is a floor on the share of a
  passage's facts that are not atomic, which works out to a cap on the atomic
  ones. A passage's cap is never below what it states, its sentences - a
  line with no verb included - and its list items together, so the cap
  never cuts a list short: the splitter reads a list as one sentence, and a
  few of its items read as the whole rule. The facts asserting a number, date or name
  are kept first, and the ones the deterministic reader composed do not
  compete. `make extract-recap` re-applies it with no model call.

The gaps are the design: a `summary` and an `outline` carry several claims by
definition, an `outline` is a fragment the parser cannot read as a sentence,
a `summary` resolves its own pronoun, and a statement a deterministic reader
composed faces only `copied`.

A pronoun the statement resolves itself is not dangling, and is not recorded
in `unresolved_references` at all: one with a noun before it, outside the
pronoun's own clause, that agrees with it in gender and number where the
language marks them, or that is a subject or an object where it does not -
"The card is blocked if it is reported stolen" - and a German `es` standing
beside the object or clause it anticipates, under a verb that does not agree
with it in number. A noun of the pronoun's own clause never resolves it:
"The customer must return it" points outside, and so does "The customer has
the right to return it", since a to-infinitive has no subject of its own and
reads as the clause it hangs in. A possessive determiner may
name one, as in "The bank replaces its cards"; a standalone possessive,
"hers", may not. A demonstrative, and a pronoun opening its statement with
no noun before it, are refused as before.

What `nothing invented` compares is **numbers and proper nouns only** — both
are things a writer reports rather than chooses. A number keeps its surface
form; a proper noun is lemmatised.

An atomic fact is read against the sentences it cites, the passage's section
path and the document's title, since a heading or a title names what a
sentence under it calls "the card" or "the bank". A sentence of the passage it
did not cite does not count: a name or number found only there is still an
addition. A number is read in any spelling, so `1st` and `1 st`, or `two` and
`2`, are the same number.

### Step 6 — Store

One transaction. The passage's existing citations are deleted and the new
facts written, scoped to that passage. A fact left citing nothing goes with
them; one another passage still cites stays. A bridge resting on it keeps
its citation.

Every fact gets one `fact_passages` row per passage it rests on. That link is
the only route from a fact to a passage, and so to a document and a topic.

### Step 7 — The bridge pass

Passages are grouped by the topic they carry most strongly, then paired on
their vectors — each head takes whichever unused passage it most nearly
meets. Within a topic the documents are taken in turn, and the groups are
strided over the whole topic.

The model is shown the group as `[P0]`, `[P1]`, … with sentences numbered
inside each, and answers with a claim plus, per passage, the numbers of the
sentences it read it in. It is told not to compute: a total nobody wrote down
would be refused as `unsupported_addition`.

A trigger deletes a bridge once any passage it rests on is gone. Re-running
the pass replaces what the previous one wrote.

## Inputs and outputs

**Reads:** `passages` (text, numbered sentences, section path, block type,
table grids), `documents.language`, `passage_topics` for the bridge pass, the
stored facts the `duplicate` probe compares against, and the served model,
with a second where `EXTRACTION_DIGEST_MODEL` names one.

**Writes:**

- `facts` — one row per statement, refused ones included, with the verdict,
  the rejection code, and the model, prompt version, temperature and spaCy
  version it was produced under.
- `fact_passages` — one row per passage the fact rests on, with the sentences
  and the span the claim rests on there.
- `passages.extract_status`, `extract_error`, `extract_claimed_at`,
  `extract_trigger`, and the passage's own `embedding`.

**Invariant:** for every `fact_passages` row whose citation was recorded,
`passages.text[evidence_start:evidence_end]` runs from the first sentence the
claim cites there to the last. `facts.evidence_text` is the cited sentences
alone: a gap between two of them, or a second passage, is a line break.

**Serves**

| Route | Answers |
|---|---|
| `GET /facts` | One page of facts, narrowed by document, kind, method and a text search |
| `GET /facts/quality` | The figures under that same filter |
| `GET /facts/{id}/passages` | The passages one fact rests on |
| `GET /extraction/status` | The queue depth, and whether a worker is on it |
| `POST /extraction/{action}` | `start`, `stop`, `retry`, `rerun`, `reclaim` |
| `GET\|POST /extraction/{scope}/{value}/…` | The same, narrowed to one document or passage |

## Prompts

Each of the three model-backed readers declares its own `PROMPT_VERSION` and
writes its composed prompt to the `prompts` table before the first claim.
[`prompts.py`](prompts.py) is the catalogue. The atomic prompt is recorded
with the cap paragraph `EXTRACTION_MIN_OTHER_SHARE` works out to, under its
version with that cap appended (`<version>+cap<n>`). A passage stating more
sentences and list items than the cap is sent the same text with its own count,
under the same version. Each prompt is recorded
under the model it is sent to: `EXTRACTION_MODEL` for the atomic and bridge
readers, and `EXTRACTION_DIGEST_MODEL` for the digest, the reader's where
unset.

Read one back with `GET /prompts?service=extraction`, or in Phoenix, where
this stage publishes whatever it records when it starts.

A drain asks the passage reader's model and the digest's one question before
it claims anything. A one-off drain refuses to start if either will not
answer; a watching worker waits until both do. See
[`backend/llm/`](../llm/README.md).

## Configuration

Ten settings of its own, in `configs/env/backend.env`. Everything else is
shared: `LLM_*`, `NLP_*`, `EMBEDDING_MODEL`, `EMBEDDING_MAX_TOKENS`,
`DATABASE_*`.

| Setting | What it does |
| --- | --- |
| `EXTRACTION_KINDS` | Which digests the passage queue writes beside `atomic`, which is mandatory. `bridge` is accepted and read by nothing |
| `EXTRACTION_DIGEST_MAX_SHARE` | The longest a digest may be, as a share of its passage |
| `EXTRACTION_DIGEST_MIN_CHARS` | Shortest passage worth digesting |
| `EXTRACTION_BRIDGES_PER_TOPIC` | Groups one topic is worth |
| `EXTRACTION_BRIDGE_PASSAGES` | Passages one group holds. At least 2 |
| `EXTRACTION_MIN_OTHER_SHARE` | The floor a passage's non-atomic kinds keep |
| `EXTRACTION_DUPLICATE_COSINE` | How alike two facts may be |
| `EXTRACTION_DUPLICATE_FLOOR` | The cosine two unrelated facts score. Calibrates the stored confidence; refuses nothing |
| `EXTRACTION_MODEL` | A different reader. Unset means `LLM_MODEL` |
| `EXTRACTION_DIGEST_MODEL` | The model the digest call goes to |

Naming `summary` or `outline` adds one model call per passage. Naming
`bridge` changes nothing: `make extract-bridge` runs the bridge pass whether
it is named or not.

Changing `EXTRACTION_KINDS` or either bridge setting affects the next run;
`EXTRACTION_DIGEST_MAX_SHARE` can be applied to stored facts with
`make extract-revalidate`.

### Commands

```bash
make extract-start                  # queue every passage never asked for
make extract                        # drain the queue here, for developing the stage
make extract-status                 # passages by state, and facts held
make extract-stop                   # take back whatever has not begun
make extract-retry                  # return every failed passage to the queue
make extract-rerun                  # read every passage again
make extract-revalidate             # re-judge stored facts; no model call
make extract-bridge                 # read every topic's groups for bridges
make extract-bridge FORCE=1         # even over bridges accepted questions cite
make extract-bridge MISSING=1       # only the topics holding no bridge yet
make extract-recap                  # re-apply the atomic cap; no model call
make extract-dedup                  # re-decide the duplicate refusals, then re-judge and re-cap what moved; no model call
make extract-embed                  # write vectors onto rows already stored

make extract-retry PASSAGE=<id>     # any of them but extract, narrowed to one passage
make extract-rerun SHA=<sha256>     # or to one document
```

`extract-embed` does **not** apply the dedup gate: a fact accepted before
that gate existed was accepted.

## Tests

```sh
poetry run pytest tests/unit/extraction
```

Twenty-five files over seven layers. Non-UI tests act through a driver —
`Checker`, `Model`, `Queue`, `Catalogue`, `Vectors`, `Extraction` in
`tests/drivers.py`, and `FactStore` in `tests/integration/facts.py`.

| Layer | Holds |
|---|---|
| Unit | Every check on every kind, both readers, the passage gate, the per-passage flow, the bridge pass, grouping, revalidation and the config refusals |
| Integration | The SQL against a real Postgres, what the database refuses, and the HTTP surface |
| Property | A verdict and its code always agree; a span always resolves; a bridge never records a passage it was not offered |
| Regression | A golden table of every candidate anybody has seen, in both languages, with the verdict it should get |
| Static | `tests/static/test_facts_pinned.py` — the settings catalogued, the routes, the check matrix in order, and this README's sections, kinds and rejection codes; `tests/static/test_prompts_pinned.py` — the three prompts, by version and digest |
| Eval | A real served model against golden passages. Prints; never gates |
| Frontend | `tests/frontend/test_facts_page.py` — the Facts page against a scripted backend |

```bash
make test-fast          # everything but spaCy, pyright and containers
make test-unit
make test-integration   # needs a container runtime
make test-eval          # needs LLM_MODEL and LLM_BASE_URL; never gates
```

## Limits

- **A number word the table does not name counts as a unit.** A number is
  read in any spelling the per-language number-word table holds, so `two
  parties` drawn from `2 parties` is supported; a word outside that table is
  still read as written.
- **A bridge cannot aggregate.** A total, difference or average appears in no
  passage, so it is refused. Bridges relate what is written.
- **An outline is checked on its shape, not its grammar.** The parser cannot
  read a fragment, so an outline faces neither `asserts something` nor
  `exactly one claim`.
- **The bridge pass depends on topic modelling.** With no fit it finds no
  group, writes no bridge and logs that it wrote none, rather than failing.
