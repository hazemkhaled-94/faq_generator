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

The **bridge pass** is not a queue: its unit of work is a pair of passages
the documents link. `make extract-bridge` finds the links, caps them per topic
of the passage that heads each, and writes what they yield. Topics must be
fitted first. A second
pass replaces the bridges in scope, so it refuses, deleting nothing, while an
accepted question cites one of them; `FORCE=1` replaces them anyway, and
those questions are rejected or deleted with them. `MISSING=1` deletes
nothing and reads only the topics holding no bridge yet: `make corpus` runs it
that way after the topics are known, so a rebuild writes bridges and a second
one leaves cited ones alone. A pass narrowed by `TOPIC`, `SHA` or `PASSAGE`
clears only the bridges headed by a passage of the topics it reads again, so a
bridge headed outside the scope stays whichever passage it shows first, and no
pass offers a pair that already holds a stored bridge, whichever side heads it.
The links are dealt as if nothing were held, and a dealt link on a held pair
goes to its head's next free link, so a hold moves no other link.
`MISSING=1` reads a topic as holding a bridge when one of its passages headed
one. It asks the model one
question first, and deletes nothing if the model does not answer.

`make extract-revalidate` re-judges stored facts without calling a model,
which is how a change to the checks reaches a corpus extracted before it. It
leaves alone the `over_cap` and `duplicate` refusals, which no check
reaches, and any fact whose citation recorded no sentence. A refusal it
validates was refused before the dedup gate and the cap could see it, so it
meets both now: probed in id order against the validated facts and the ones
validated earlier in the pass, refused as a `duplicate` on a twin, and its
passage re-capped. It reads the facts in batches of whole facts by id, each in a
transaction of its own, and writes only the rows whose verdict, words, readings
or cited spans differ from what is stored, stamping only those with the current
settings version: a second pass under unchanged code writes nothing, and a row
keeps the version of the pass that last changed it.
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
  claims and list items it carries, and dense with digits. The shares are
  `_CHARS_PER_CLAIM` and `_NUMERIC_WORDS` in [`service.py`](service.py). A
  list item counts as a claim, so a price list is read.

A table is exempt from the last four, because it is read from its cell grid.
It is not exempt from one more: a grid whose filled cells are more than half
identifiers — `TA-BO1`, `K2`, `TM-2.2.1`, a tick — states nothing a reader
would look up. A bare figure, `5` or `12.50`, is a value and no identifier,
and so is one after a currency: an ISO 4217 code (a static standard, the same
in every language), a currency sign, or a word its language's `AMOUNT_WORDS`
names, `SEK 25` or `GBP 12.00`, so a fee table is read. The share is `_CODE_CELLS` in
[`service.py`](service.py).

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
than two claims, each list item counting as one, is not digested: a list is read
as one sentence, so its items are what it states.

`EXTRACTION_DIGEST_MODEL` names a model of its own; unset it uses whichever
model reads the passage.

A digest is optional. When the model cannot give one, because it is down or
the provider's filter refuses the passage, the passage still finishes
`extracted` with its atomic facts, and `extract_error` says
`digest failed: <reason>`. `make extract-digests` (`python -m extraction.run
--digests`, and `make corpus` runs it after `extract`) claims those passages,
and every extracted passage of `EXTRACTION_DIGEST_MIN_CHARS` or more that holds
no digest, so a floor lowered after a corpus was read reaches it without
re-reading it. A passage the drain skips (a contents page, a copyright
notice, a reference list) is finished without a call here too. It calls only the digest model, and replaces only the summary and the outline,
never an atomic fact or its id. A digest that fails again keeps its note and is
tried again on the next run, once per run. An unexpected error in the pass
does the same, and an interrupt gives the passage back as it was: the pass
never makes an extracted passage `failed`, which `make extract-retry` would
read again and replace the atomic facts of. A digest model that cannot be reached
for five passages in a row (`STOP_AFTER`) is asked no more for the rest of that
drain, since each passage would pay its whole retry budget: the drain goes on
reading atomic facts, each passage is noted, and `make extract-digests` gives
them theirs once the model answers. A deployment whose `EXTRACTION_KINDS`
names no digest kind has nothing to give: the command says so and exits 0, so
`make corpus` goes on.

### Step 5 — Check everything

Every check is structural rather than lexical. A citation is an index, so it
cannot be half-right, and no check reads a similarity: the one similarity
threshold in this service is the `duplicate` refusal below.

The citation is resolved first — a citation naming nothing that exists is
`evidence_absent` and no further check runs. One index past the last sentence
is read as a line of it only where that sentence holds two list lines or more (a
bullet or a numbered item), because the model reads a list line by line; past a
sentence of wrapped prose, or one whose only such line is a date opening a wrapped
line ("1. January"), it names nothing. Then the checks the kind calls
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

For an atomic fact, `unsupported_addition` reads the whole passage, its heading
trail and the document's title as what the fact may rest on: a figure the list
lead-in states or a name a neighbouring sentence gives is carried. A dotted
number that numbers a part of the heading's own number ("3.2" under "Article 3")
is carried only when the cited sentences say it. A figure only the rest of the
passage states is refused, with the cited figure named in the reason, when the
cited sentences state another of its kind (the same currency, unit or sign beside
it, read from the parse): "costs EUR 2" for a cited "costs EUR 5". Kinds are one
across spellings (a currency code, sign or word; a share; a period) and figures
written in words are read, in the languages that configure number words. The
rest of the passage includes the cited sentences, so a time or a range sharing a
digit group with the cited one is a swap too ("by 6:00 pm" for a cited "by 3:00
pm"). A cited figure the statement writes as well is kept, not swapped out. A digest rests
on the sentences it cites. For every kind a word is also carried in the form the text layer wrote
it in: an inflection, a hyphen split or dropped, and, where nouns are not all
capitalised, a capitalised first word of a list item.

For a bridge, `unsupported_addition` reads each cited passage's heading trail
and title as it does for an atomic fact (numbers in any spelling, hyphen parts,
noun forms), and `not_bridging` also refuses a statement naming the numbered
heading of a passage it cites ("Section 7", "Section 7(2)", or "Sections 7
and 9" under Section 9, read as the link pass reads a list of numbers): that is a claim
about the document.

An atomic statement the model wrote and the checks refused as `not_atomic` is sent
back to the same model once, in one more call for the passage, under a
prompt of its own. Shown the numbered sentences the first call was shown,
the refused statements and the reason each was refused, it writes each
claim as a fact of its own, repeating the subject and the condition or
exception the claims shared. What comes back faces the same checks, then
the `duplicate` gate beside the passage's other facts, but not the cap: the
passage's room counted the refused statement once. A piece still
joining two claims is refused again and not sent back. The refusals are
stored as they were, and a repaired fact carries the repair prompt's version
as its prompt version. A passage with no `not_atomic` refusal costs no extra
call, and a repair call that fails leaves the refusals standing and is
logged rather than failing the passage.

Two more refusals are the service refusing what the checks passed:

- `duplicate` — the corpus already holds the statement.
  `EXTRACTION_DUPLICATE_COSINE` is how alike two may be, and a candidate is
  probed through the HNSW index against every validated passage fact already
  stored in the corpus of its own language and kind that carries a vector,
  bar those citing only the passage being re-read, **and** against the facts of
  another kind this passage already kept - a summary or an outline
  repeating one of its claims, or of its kind saying it word for word. Two
  atomic facts of one passage are otherwise never twins: two items of a
  list, two conditions, a least and a most differ by a word and are two
  claims. A bridge is never its twin, and nor is a fact
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
  against never counts towards the scope of a question asked of it. The
  refusal does keep that fact's id (`twin_id`, indexed, set NULL when the fact
  is deleted), so after a drain that replaced facts the replay reads only the
  refusals that lost their twin. A refusal stored before the column existed
  has none, so the first replay after the upgrade reads every stored refusal
  once.
  `make extract-dedup` re-decides every stored refusal under the rule as it
  stands, giving back the ones it would no longer make with the reading
  taken against today's bar, or none, and takes out the
  citations an earlier version's refusal added to its twin, rebuilding that
  fact's evidence from the citation it keeps. No model is called.
  The probe narrows to the candidate's language and kind. The language is
  `facts.language`, written with the fact from the passage it opens on (its
  document's where that passage is too short to tell), so the narrowing is a
  filter on the vector index and not a join over the citations.
  The probe sees only what is committed, and two drains run side by side
  (`extract-worker` containers, or a drain on the host beside one) each probe
  before either stores. So the store takes a lock for each language and kind
  among a passage's validated facts, inside its transaction, and judges them
  again under it against what the other drain committed meanwhile: the second
  drain's twin is refused as a duplicate of the first's fact, as a single
  worker would have refused it. Drains writing facts of other languages or
  kinds do not wait on each other. The second look costs one more probe a
  fact, which the language column on the facts keeps to a vector-index lookup.
  Nothing ties a stored fact to the passages refused against it, so
  deleting its document leaves each repeat refused against a fact that is
  gone. `make delete` and `make delete-derived` therefore run
  `extract-dedup`, which gives the repeat back. A deletion through the API
  or the UI does not, so run `make extract-dedup` after it; it is also the
  recovery when the replay of a `make delete` fails, since the document is
  gone by then. A passage read again - a rerun, a retry - replaces its
  facts the same way, so a drain that replaced any runs the same replay
  itself once it finds its queue empty, under an advisory lock, so two
  `extract-worker` replicas never interleave it. Only with the gate on: at
  `EXTRACTION_DUPLICATE_COSINE` 0 the replay would give every refusal back. The passages of the refusals it gives back, and no others,
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
  compete, nor the ones the repair call wrote. `make extract-recap` re-applies it with no model call.

The gaps are the design: a `summary` and an `outline` carry several claims by
definition, an `outline` is a fragment the parser cannot read as a sentence,
a `summary` resolves its own pronoun, and a statement a deterministic reader
composed faces only `copied`. A written atomic fact copying a single
sentence does not face `copied` either: `not_atomic` counts the claims it
reads as now, where `copied` would read the count its sentence was stored
with when the passage was chunked.

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
no noun before it, are refused as before, and so is a statement opening on a
noun whose modifier points as far: "Such a card", "Die vorgenannte Karte", or
a plural "the following fees" (a singular one is the next, "am folgenden
Tag", as is one a figure counts, "the following 12 months", and one whose
items the statement lists after a colon points at them: both stand alone). A German statement opening on `Sie` names the
reader where a polite form follows inside it or stands inside a sentence of
the passage it was drawn from ("Bitte geben Sie Ihre IBAN an"); one opening a
sentence there is capitalised either way and says nothing, and a passage
that opens a sentence on `Sie` after a plural subject ("Händler werben Kunden.
Sie erhalten ...") leaves it a reference.

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

Passages are paired by the documents' own links (`extraction/links.py`), per
language and across topics: a passage that names another section's numbered
or quoted heading ("Section 7", "Returns"), two sections under one parent
heading, or a term almost no other passage uses: one in 0.5% of the
language's passages, never fewer than two and never more than six, so the
term links grow with the corpus and not with its square, and each passage
keeps the eight partners it shares the most such terms with, the nearest first
among those. A
reference outranks a
sibling, and a sibling a term; inside a kind the vectors rank the partners
and a tie goes to the lower id. Under a parent heading a passage keeps its
eight nearest sections, picked out of the family with one partition rather
than by building and sorting a link to each. Each passage heads at most one pair, a pair
is offered once, and a topic is worth `EXTRACTION_BRIDGES_PER_TOPIC` pairs on
the passages that head them, strided over the topic's heads in reading
order. The partner may sit in any topic of its language. The pass logs how
many links of each kind it offered. It reads each passage's vector as a
float32 array (4 KB, where a tuple of Python floats was 32) and parses each
passage once, for the sections it names and for its content lemmas together.
The bridges in scope are deleted after the links are dealt and before the
first model call, so a pass that dies reading the corpus deletes nothing. A heading numbered before its word
("1.2 Returns") gives no reference link: only "Section 7" style headings, a
word then a number, are learned, and such a section is still linked as a
sibling or by a shared term.

The model is shown the pair as `[P0]`, `[P1]` with sentences numbered inside
each, under each the validated atomic facts of that passage as `[F0]`, `[F1]`,
and one line naming the link. It answers with ONE bridge or `none` (the usual
answer): a relation from a closed set (defines, limits, consequence, applies,
parallel, contrast), one fact picked from each excerpt by number, the claim
relating them, and the question only both excerpts answer with its short
answer. The bridge cites the picked facts' own sentences, so it rests on what
was already checked. It is told not to compute: a total nobody wrote down
would be refused as `unsupported_addition`. A pair with a passage holding no
validated fact is not read; the per-language log line counts them. Two facts
set side by side ("both A and B", "stated separately") are not a bridge unless
a question about the two needs both. A bridge's fact row also stores its
reading in `facts.bridge`, the relation the model named and the question and
short answer the bridge is tested with, refused bridges included, so a
re-judgement tests the same thing, and the id of the passage that headed the
link (`head`): a sibling or a term link shows the earlier passage first,
whichever headed it. It is empty on every other fact and on a bridge written
before prompt 6, which is read as headed by the passage it shows first. Prompt version 6 replaces the list-of-claims
prompt 5.

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

Each of the three model-backed readers declares its own `PROMPT_VERSION`, and
the passage reader's repair prompt declares `REPAIR_PROMPT_VERSION` beside
it. Each prompt is written as composed to the `prompts` table before the
first claim.
[`prompts.py`](prompts.py) is the catalogue. The atomic prompt is recorded
with the cap paragraph `EXTRACTION_MIN_OTHER_SHARE` works out to, under its
version with that cap appended (`<version>+cap<n>`). A passage stating more
sentences and list items than the cap is sent the same text with its own count,
under the same version. Each prompt is recorded
under the model it is sent to: `EXTRACTION_MODEL` for the atomic, repair and
bridge prompts, and `EXTRACTION_DIGEST_MODEL` for the digest, the reader's where
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
make extract-digests                # digest the passages that finished without one

make extract-retry PASSAGE=<id>     # any of them but extract, narrowed to one passage
make extract-rerun SHA=<sha256>     # or to one document
```

`extract-embed` does **not** apply the dedup gate: a fact accepted before
that gate existed was accepted.

A passage read again keeps the facts that come back as they were. A fact with
the same kind, method, statement (whitespace collapsed) and citations keeps
its id, its embedding and the questions resting on it; its other columns take
the new reading. Only a fact the new reading does not repeat is deleted, and a
question resting on it is rejected as `source_changed`, never deleted.

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
| Static | `tests/static/test_facts_pinned.py` — the settings catalogued, the routes, the check matrix in order, and this README's sections, kinds and rejection codes; `tests/static/test_prompts_pinned.py` — the four prompts, by version and digest |
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
- **A list said to follow is taken as given wherever a figure or a colon
  stands.** A fact opening on "the following fees" is not refused when a
  figure counts the noun or a colon follows, even where the list is given
  elsewhere: "The following fees apply: see the price list.", "The following
  two documents are required."
- **A document name after a joined section number hides that number.** In
  "Ziffer 4 und 5 AGB" the 5 reads as counting the name after it, so neither
  the link pass nor the bridge check reads a Ziffer 5 there.
- **The bridge pass depends on topic modelling.** With no fit it finds no
  group, writes no bridge and logs that it wrote none, rather than failing.
