# Question generation

Each topic's facts become questions with known answers, and each question
cites the facts it was written from.

A question that fails a gate is stored with the gate's name rather than
dropped: the rate at which that happens is how the writer is judged.

## What a question is

A question is written from one or more **facts**, and the writer is shown the
**passages** they came from as well. The facts are what the answer must rest
on; the passage is what the question can be phrased from — the institution,
the document and the period all come from the passage and its heading trail.

The unit of work is a **topic**. The facts a topic may be asked about are the
facts of the passages that topic is strongest in. A topic with
`include_in_coverage = false` is skipped, and so is a fact a person rejected
in review.

## What it does

### Step 1 — Plan

[`planning.py`](planning.py). Before anything is written, a topic gets one
slot per question, each carrying the kind to write, the difficulty band to
aim for, and whether it is meant to have an answer at all.

```ini
QUESTIONS_TYPE_MIX=factoid:<weight>,definition:<weight>,entity:<weight>,...
QUESTIONS_DIFFICULTY_MIX=easy:<weight>,medium:<weight>,hard:<weight>
```

Weights are spread over the slots by **highest averages**, so the counts are
exact over a run and interleaved along it. That matters because the
unanswerable share and the follow-up share are both taken by position.

A kind with a weight of `0`, or left out, is never planned; a follow-up takes
its kind from `QUESTIONS_FOLLOWUP_TYPES` instead. A band can be moved off its
weight: an `easy` slot is raised to its kind's floor, and an unanswerable one
is planned `easy`. `GET /questions/plan` reports the configured mixes, shares
and answer bounds the next run will read.

### Step 2 — Deal the facts

[`selection.py`](selection.py). `QUESTIONS_FACT_SAMPLE` caps how many facts
are offered, divided between the passages the sample holds. The band decides
the shape of the sample:

| Band | Shape | What the deal offers | Worth |
|---|---|---|---|
| `easy` | `single` | one passage | 0 |
| `medium` | `cross` | a passage in another document, ranked by likeness | 2 |
| `hard` | `bridge` | a bridging passage in another document — another file *and* another subject | 3 |

Passages are dealt strided over the whole topic, each offered
`QUESTIONS_SAMPLES_PER_PASSAGE` times. A topic sitting in one document falls
back to the passage of the same document most like the first, by the same
likeness, rather than writing nothing; the nearest in reading order breaks a
tie.

Likeness pairs the **passages**, then picks the **facts**: the second
passage's share is the facts closest to what the first offered, not its own
best. Cosine where the corpus is embedded, shared lemmas where it is not —
vectors are preferred because a lemma overlap cannot see a synonym. A fact is
weighed against the **nearest** of the facts already offered, not their mean.

Where nothing in the second passage meets the first, the sample is still
offered and the writer is told to narrow. `difficulty` is read off what it
cited, so a question that narrowed bands as what it is, and stands: nothing
asks it to widen.

A reading type is offered the condensed facts first; a `value` type is not.
`QUESTIONS_MEETS_FLOOR` would narrow the sample where the second passage
meets nothing, and ships off — the sweep found no threshold that removes
the welds without throwing away sound questions. It weighs the fact the first
passage offers first, so for a reading type that is the condensed one.

**The corpus's own furniture is never offered.** A copyright notice, contents
page or revision table is real text a fact extracts from cleanly and no gate
downstream refuses. It is read by **repetition, not vocabulary** — a passage
with a cross-document twin above `QUESTIONS_BOILERPLATE_COSINE` — so nothing
about a language, a domain or a section name is assumed. Three ways it
abstains: a corpus of one document has nothing to repeat into, a passage with
no embedding cannot be compared, and a threshold of `0` turns it off.

Acknowledgements defeat that reading, because every document thanks different
people. `QUESTIONS_PARTY_DENSITY` reads them instead: the share of a
passage's alphabetic tokens spaCy tags `PER`. `PER` and not `ORG`, because a
corpus names organisations throughout its subject matter. It runs in
[`service.py`](service.py) rather than in the queue, once per distinct
passage.

### Step 3 — Write one question

[`generation.py`](generation.py), [`types.py`](types.py). One shared rule
block holds what is true of every question — do not name the source, name the
subject, one question, the language of the facts — and each kind adds what it
asks for, what its answer looks like, and one or two worked examples.

Each call returns **two answers**: `target_answer`, the key a chatbot is
scored against, and `answer_explanation` beside it.

Which facts a question cites is the **writer's** answer, not the sample's. A
sample wider than one passage also carries an instruction to use both halves.

A draft a gate refused for how it was written — two questions welded
together, its source named, an answer of the wrong shape — is written again
with a note saying what went wrong, up to `QUESTIONS_RETRIES` times. An
accepted draft is never asked again, however narrow it came out: asking it
to cite every passage it was offered asks for the weld the span rules
forbid. Every draft is stored; should two drafts of one slot both be
accepted, the first is kept and the other is stored as `duplicate` with
`superseded` after the gates it passed in `gates_ran`.

### Step 4 — Gate it

[`checker.py`](checker.py), [`gates.py`](gates.py),
[`verifier.py`](verifier.py). See [The gates](#the-gates).

### Step 5 — Draw a balanced release

[`balance.py`](balance.py). See [The balanced release](#the-balanced-release).

## The thirteen kinds

Every one is a question **form**, never a subject, so the same list applies to
a manual, a contract, a policy or a report. Nothing in any prompt names a
domain.

| Kind | Asks for | Answer | Passages | Level |
|---|---|---|---|---|
| `factoid` | one checkable value | value | 1 | recall |
| `definition` | what a named thing or status is | explanation | 1 | understand |
| `entity` | who does, decides, owns or must be told something | value | 1 | recall |
| `enumeration` | which things belong to a named set | list | 1 | understand |
| `condition` | when, or under what circumstances, something applies | list | 1 | apply |
| `reason` | why something is required, done, or the way it is | explanation | 1 | analyse |
| `procedure` | how something is done, or in what order | explanation | 1 | apply |
| `consequence` | what happens when something is or is not done | explanation | 1 | analyse |
| `comparison` | how two named things differ | list | 2 | analyse |
| `aggregation` | a total no single fact states on its own | value | 2 | analyse |
| `temporal` | what changed between two periods | list | 2 | analyse |
| `implication` | what must be true when two stated things both hold | explanation | 2 | analyse |
| `application` | which stated rule governs a case the material omits | explanation | 1 | apply |

A type needing two passages cannot be planned `easy`. `application` is the
exception and declares a **floor** of its own: it needs one passage, but the
case it puts the rule to is not in the material.

### The answer form

`answer_form` is `value`, `list` or `explanation`. The kind declares the form
it asks for and the others it will take, and the form stored is the one of
those the answer turns out to fit, so a `factoid` answered with three things
is stored as a `list`. Every gate that reads an answer reads it against that
form: the verb rule applies to a `value` alone, an `explanation` is refused
for carrying *no* verb, and each form has its own bounds in
`QUESTIONS_ANSWER_CHARS`.

### The two answers

`target_answer` is short by design. `answer_explanation` is three to six
sentences that say what the thing is, enough that a reader who never saw the
passage understands the answer rather than merely being able to mark it.

They are two columns because they are scored by two gates. Recoverability's
denominator is the target's own content lemmas, so every lemma the target
gains is another one the verifier has to reproduce.

The explanation faces `explanation_unusable`, which reads three things and
calls no model:

| | |
|---|---|
| Length | Within `QUESTIONS_EXPLANATION_CHARS`. The floor is the half that matters |
| Supported | Every figure, date and name it asserts is in the cited passages |
| Not a copy | Fewer than 90% of its content lemmas are already in the target |

A spelled-out numeral is not a claim: a unit that `like_num` marks and that
carries no digit is dropped, so `48` is checkable and `two` is how a sentence
is built. Proper nouns stay.

The column is NULL on questions written before it and is not backfilled, and
NULL on every unanswerable question by CHECK.

### What a question asks of a reader

`difficulty` says how far an answer is spread — how hard it is to **find**.
`cognitive_level` is the other axis, derived from the question's type:

| level | types |
|---|---|
| `recall` | factoid, entity |
| `understand` | definition, enumeration |
| `apply` | condition, procedure, **application** |
| `analyse` | reason, consequence, comparison, aggregation, temporal, **implication** |

The two in bold are **derived**: the premises are in the material and the
conclusion is not, so answering means reasoning. `aggregation` is derived
too: its total is not in the material. Because their answers are absent by
construction, recoverability asks them the wrong question and they face one
of their own — `arithmetic`, for `aggregation`, asks whether the figures
come to the total, and `entailment`, for the two in bold, whether the
conclusion follows from the premises. Where the passages hold fewer than two
figures there is no total to compute, so a count of what they list is asked
of the model rather than refused. So is a count whose passages' figures all
count something else: `How many corner flagposts …?` over a height in metres.

`GET /questions/quality` also reports `cognitive_level_checked`, how many
accepted questions are of a type a rule settles. Only six of the thirteen
types have one, so the honest thing is to say how much of the column is
measured.

### The three criteria, and the band

Each is read off the facts the question reported citing:

| | |
|---|---|
| `passage_scope` | `single_passage` or `multi_passage` |
| `document_scope` | `single_document` or `cross_document` — the one a retriever cannot fake |
| `topic_scope` | `single_topic` or `multi_topic` |

`difficulty` is then **derived**. Five things each count one point — the
three scopes, an answer past `QUESTIONS_LONG_ANSWER_CHARS`, and following
another question — and the band is the total: 0–1 `easy`, 2 `medium`, 3+
`hard`. Nothing is weighted.

The band the plan asked for is stored as `planned_difficulty` beside it. The
two disagree when the writer cited fewer facts than it was offered.

## The gates

Applied cheapest first, in this order. The first five are one structural
step, and the free half of `leaks_source`, a question quoting the title of
its own document, runs in it too.

| Gate | Rejects a question that | Costs |
|---|---|---|
| `malformed` | is not a question, carries no target answer when it claims one, is in the wrong language, is one of its own facts handed back, or answers with the number of facts it cites where no cited fact states that number, when it asks how many or the answer is that count alone | nothing |
| `compound` | asks two things | nothing |
| `answer_too_short` | is scored against an answer below its form's floor | nothing |
| `answer_too_long` | answers past its form's ceiling | nothing |
| `wrong_form` | answers in the wrong shape | nothing |
| `off_topic` | was written to have no answer and is about nothing the material mentions. **Off** as shipped — see [Unanswerable questions](#unanswerable-questions) | nothing |
| `wrong_type` | is not the kind it was planned as, where a rule can say so. A `comparison` has to state a difference between the two subjects it names: a comparative with one subject before it and the other after, both within its stretch between seams (`;`, `,` or a conjunction); or, across a seam that divides the subjects, a comparative on each side, one comparative where the seam opens a subordinate clause (`…, while …`), or a word both sides share and the question does not | nothing |
| `restates_question` | is answered with almost no word the question did not already carry, counting nouns, adjectives, verbs and adverbs. An answer with a number, one saying yes or no where the question did not, and a `comparison`, are not read | nothing |
| `explanation_unusable` | carries a long answer that is the wrong length, asserts a figure or a name the passages do not — every proper noun it carries counts as a name — or only restates the key | nothing |
| `asks_nothing_new` | is a follow-up citing nothing its root did not | nothing |
| `off_thread` | is a follow-up resting on no passage the turn before it used | nothing |
| `duplicate` | is a near twin of one already accepted in its own language and of its own answerability, or is an accepted draft of a slot whose earlier accepted draft was kept (`superseded` closes its `gates_ran`). How near depends on what the two cite: a shared fact, a shared passage, or nothing in common, each a higher bar, and a different question word lifts any pair to the highest | one index probe among the accepted questions of its language and answerability; two for an unanswerable question, one per kind that can refuse it |
| `answerable_after_all` | was written to have no answer and turns out to have one: an accepted answerable question resting on the same fact sits near it, or its own passages answer it | the probe among answerable questions, the second of the two, or the round trip |
| `leaks_source` | names the material its answer is in | nothing, or one question-only call |
| `unanchored` | nobody could have asked without the passage in front of them | nothing, or up to two question-only calls |
| `not_recoverable` | cites evidence its own answer is not in | the round trip |
| `answer_incomplete` | has a `list` key naming far less than the verifier found | the same round trip |
| `answerable_elsewhere` | was written to have no answer and a passage it does not cite answers it | a passage probe and a second call |
| `source_changed` | rests on a fact that no longer passes its own checks or that a person rejected, or whose citations no longer match its stored passage or document scope | nothing |

`questions.rejected_reason` holds exactly these. `source_changed` is the one
no run of the writer produces — it is `make questions-reverify` carrying a
change further up the pipeline through to the questions resting on it.

`compound` is read off the tagger: a question word a conjunction introduces
after the first, a preposition at most between them, is a second question —
`Welche Vorschriften gelten und wie hoch ist die Gebühr?`, `When is it due
and for how long?`. One anywhere else opens a clause inside the one question
and asks nothing twice: `How do the two differ in where they are taken
from?`, `Wovon hängt ab, wann …`. It reads the neighbouring tokens rather than
the dependency tree, because the German parser hangs a main verb under its
auxiliary with the label an embedded clause carries. It replaced a
model-judged `wrong_type` that never fired.

There is **no gate for "the question is its own fact rearranged"**. One was
written in two formulations and both refused questions that are as good as a
benchmark question gets: for a single atomic fact, a good question *is* the
fact minus its answer.

### The round trip

`not_recoverable` is the one no similarity measure makes. A second model is
shown **only the cited passages** and asked to answer; the question survives
if what comes back carries every number, name and date the target asserts,
and enough of what it is about. A `value` is compared whole, on its verbs as
well as its nouns and adjectives, so `a report` is what a passage saying
`must be reported` says; a `list` or an `explanation` by overlap —
`QUESTIONS_ANSWER_OVERLAP`. Numbers are always exact, so `4 hours` never
passes for `48 hours`, and a count written out is its figure: `two
conditions` is `2 conditions` and `zehn Sekunden` is `10 Sekunden`, for the
languages whose number words the gates hold.

The `recall` reading stored beside the verdict is held to the bar the form
was: all of it for a `value`, which records a reading only where it fell
short, and `QUESTIONS_ANSWER_OVERLAP` otherwise. So a `value` whose recovery
fell short and which the entailment pass then rescued carries a confidence of
0, and a `list` or `explanation` whose recovery holds no content word reads 0
rather than abstaining.

The form is the one the answer fits among those its type takes, and only a
`list` is then checked for completeness. Three items punctuated apart make a
list; two carrying no verb do where the type asks for a list first, so a
`condition` answered with two of the passage's conditions is held to
`answer_incomplete` rather than compared as a value. Two clauses carrying
verbs are an explanation where the type takes one, and a list where it does
not.

Three things about it are load-bearing. The verifier is meant to be a
**different** model, because a model marking its own work recovers what it
just wrote; the stage warns when it is the writer's. The escape hatch is
explicit — the verifier answers whether the passage states it at all. And it
sees only the cited passages, never the corpus: what is being measured is
the dataset, not a retriever.

`unanchored` and `leaks_source` are asked of `QUESTIONS_PHRASING_MODEL`, one
judgement per call. Each is a judgement rather than a measurement, and they
are the only gates here that are **opinions** — so the factory turns them off
when the phrasing model is the writer's own, and then they are not asked for
at all: a verdict that may not reject is a call per question buying a log
line. The rule half of `leaks_source` still fires, because a pattern is a
measurement. Recoverability stays on regardless.

`unanchored` covers two ways of failing to stand alone: naming too little,
which `anchored()` counts, and naming plenty while **pointing outward**. The
second reads three things:

| Reading | Catches |
|---|---|
| `PronType=Dem` | `diesen beiden`, `this version` |
| a noun made definite and counted | `den beiden Lehrplänen`, `the two editions` |
| the anaphoric adjectives | `aforementioned`, `latter`, `besagt` |

It over-fires on purpose, so it only decides whether the phrasing model is
asked; the verdict is the model's.

### Where the phrasing judgements are answered

`read()` used to ask for five things at once and answered the small ones in
whatever language the hard one was thinking in. It now asks one thing, and
the three phrasing judgements are answered where each belongs:

| Judgement | Answered by |
|---|---|
| `subject` | `gates.subject` — spaCy noun chunks |
| `names_its_source` | `gates.cites_source`, a model for the residue |
| `self_contained` | `phrasing.py`, asked only where a pointer was found |

`cites_source` matches what a pattern can settle — a numbered division
(`Abschnitt 2.2`), a bracketed reference (`[R22]`), an author with a year
(`Beck 2003`) — and returns **None, never False**, because the absence of a
pattern is not evidence.

These are the readings that are words rather than features, and so the ones a
third language has to be added to. [`backend/nlp/`](../nlp/README.md) lists
every one, and what happens to a gate whose language is missing: nothing,
silently.

The phrasing gates run **before** the round trip, because none of them reads
a passage. `QUESTIONS_PHRASING_MODEL` is the dial; unset it falls back to
`QUESTIONS_VERIFIER_MODEL`.

## Unanswerable questions

Some questions are written to have no answer, by perturbing a verified fact
just out of reach. `QUESTIONS_UNANSWERABLE_SHARE` sets how many are
**attempted**, spread by position rather than at random. One is always
planned `easy` and from one passage.

Attempted, not held: they face three gates of their own, and the two that
are on bite, which is why the default sits above the share a release should hold. Over-setting is safe — `QUESTIONS_RELEASE_UNANSWERABLE` is a
ceiling.

| | |
|---|---|
| `answerable_after_all` | the corpus answers it after all. A recovery from its own passages that only says the question back is not an answer: a `why` the passage gives no reason for comes back as the rule itself |
| `answerable_elsewhere` | a passage it does **not** cite answers it |
| `off_topic` | it is about nothing the material mentions at all |

Being near an accepted answerable question is not an answer by itself. A
perturbation moves one detail of a fact out of reach, so it sits near the
question about that fact by construction. The probe refuses it only when
the two rest on the same fact; otherwise the checks that read passages
decide.

The last matters more than it looks: a chatbot refusing *"What is the capital
of Mars?"* has demonstrated nothing about whether it knows the limits of
**this** corpus.

It ships **off** (`QUESTIONS_OFF_TOPIC_OVERLAP=0`), because the vocabulary it
compares against is too small to tell. It is the stored lemmas of the cited
passages' text, which is usually one short passage and never its section
heading, where a glossary entry's headword sits. A perturbation moves one fact
out of that passage by design, so it always carries words the passage lacks:
the gate refused questions about the material and found none about anything
else. Measured against the vocabulary of the corpus's language, headings
included, it could be turned back on.

## Follow-up threads

A share of accepted questions get a **thread**, up to
`QUESTIONS_MAX_FOLLOWUPS` deep. `follows_id` and `thread_position` carry it.

Each turn takes the next kind in `QUESTIONS_FOLLOWUP_TYPES`, cycled, and the
cycle **starts where the thread sits** among the followed ones rather than at
the first kind, so a list longer than the depth is a rotation and not a
prefix with a dead tail.

A follow-up **may lean on the conversation** — *"And for an urgent one?"* —
which is the point. Two consequences: the `unanchored` half of the phrasing
gate is not applied to one, though `leaks_source` is, and the verifier is
shown the conversation when it judges recoverability.

`Deal.widen` adds unspent facts **of the same passages** once, before the
thread's first turn is written, and two gates hold the thread together:
`asks_nothing_new` refuses one citing nothing outside its root, and
`off_thread` refuses one resting on no passage the turn before it used.
`off_thread` is read on **passages and not on words**, because a good
follow-up may name nothing at all.

Only an accepted, **answerable** root is followed. A thread stops at the
first follow-up a gate refuses; a thread that widens to nothing stops at
`asks_nothing_new`, which is the material running out rather than a gate
misfiring.

Each follow-up is another writer call and another verifier call.

## Coverage

`topics_covered` counts every topic in coverage the stage has finished,
whether or not it produced an accepted question, which is a low bar, so
`/questions/quality` also reports how much of the **material** the accepted
questions reach.

Passages are counted against those a validated fact rests on, not against
every passage: a passage no fact rests on cannot be asked about, so counting
it would report extraction's refusals as this stage's gap.

A sample **burns** `QUESTIONS_FACT_SAMPLE` facts whether or not the question
cites them, and no fact is offered twice within one topic, so past a point
`QUESTIONS_PER_TOPIC` is inert. What raises coverage instead is running
again, lowering `QUESTIONS_FACT_SAMPLE`, and — marginally —
`QUESTIONS_FOLLOWUP_SHARE`. Figures in
[measurements](../../docs/measurements.md).

## The balanced release

Accepting a question says it is sound. It says nothing about what the SET
looks like — every gate can do its job and still leave a set skewed to one
band or one kind, because what survives a filter is whatever the material
happened to offer.

So the run overgenerates and the composition is chosen afterwards.
`make questions-balance` fills a quota out of everything accepted and writes
`questions.release_id` on what it drew. Four shares are held at once:

| | |
|---|---|
| `QUESTIONS_RELEASE_UNANSWERABLE` | The most of the release that may have no answer. A ceiling |
| `QUESTIONS_RELEASE_DIFFICULTY` | How it spreads over the bands |
| `QUESTIONS_RELEASE_TYPES` | How it spreads over the kinds. Unset reuses `QUESTIONS_TYPE_MIX` |
| `QUESTIONS_RELEASE_LANGUAGES` | How it spreads over the languages. Unset weighs every language the pool holds alike |

They are **marginals, not a joint distribution**: an even spread of kinds
within each band is not reachable, because a `factoid` answers with a value
and a short answer cannot earn the length point a `hard` question needs.

Within a bucket the draw goes in the order of an md5 of the question's id,
not of the id. Ids are creation order, and a run writes one language's
topics before the next, so an id-order draw released whatever was written
first. The hash is as reproducible: the same pool and settings draw the same
release twice.

A release holds one question of each twin group. Twins are read by the
`duplicate` gate's own rule, over each accepted question's few nearest of
its language and answerability rather than over the one neighbour the gate
probed, so a twin the gate let past behind a closer question is caught here.
A root whose twin is already in is skipped, a thread ends at a turn that
twins what is already in, and of a group the question the gates were surest
of, by `confidence`, is the one kept where it fits.

`QUESTIONS_RELEASE_SIZE=0` draws the largest release the pool can fill to
within `TOLERANCE` of every quota. The command reports what it drew, the yield,
its spread over every share, the languages included, and any quota the pool
came up short on.

Nothing is deleted. The draw re-checks first, as `questions-reverify` does,
so a question that no longer passes the free gates is rejected before it can
be drawn. Beyond that, a release is a column on rows already there, so
questions left out stay queryable, and running it again with different
shares replaces the first. It always draws over every accepted question:
`--only` is refused, and `make questions-balance` takes no `TOPIC=`.

`FILTER="--released"` exports the release, `released=true` narrows
`GET /questions` to it, and **Released** does the same on the Questions page.
Every workbook carries a Released column.

A released question is always accepted: one that a person or a re-check
moves off `accepted`, or that loses one of its facts, leaves the release.

## Getting the dataset out

[`export.py`](export.py).

```bash
make questions-export OUT=exam.xlsx FILTER="--status accepted --cognitive-level analyse"
```

One workbook, four sheets:

| Sheet | One row per |
|---|---|
| Questions | Question, with what it rests on folded in |
| Citations | Question × fact × passage, so a bridge takes two |
| Assessment | Judgement of a question. Empty unless the evaluation phase has run |
| Summary | The counts, off the same quality report the page shows |

The same on `GET /questions/export` and behind **Build a workbook** on the
Questions page, built when asked for rather than on every render.

**The filter is the caller's and there is no default scope.** Ask for nothing
and you get everything, rejected rows included, because that is what the same
request to `/questions` returns.

Argilla is not this: it holds a disposable copy of a stratified *sample*
pushed for review. The database is what has the set.

The Citations sheet is the expensive half; `--no-citations` leaves it empty.

## Reading back the prompt that wrote a question

Every question carries `prompt_version`, and three modules declare one:
`types.PROMPT_VERSION` for the thirteen writers, `phrasing.PROMPT_VERSION`
for the three wording judgements and `verifier.PROMPT_VERSION` for the round
trip's four. They are bumped separately.

The stage records what it sends at start-up — [`prompts.py`](prompts.py)
declares it and `stages.prompts` writes it to the `prompts` table. Three ways
to read one back:

| Where | Shows |
|---|---|
| The Questions page | "The prompt that wrote this", under a selected question |
| `GET /prompts?service=questions&version=10&name=factoid` | The same, as JSON |
| Phoenix | The prompt beside the traces, published by the stage that recorded it |

Each records the whole call: the system message, the user message as its
template, and the JSON schema the answer had to come back in.

A question also carries `trace_id` and `span_id` — the trace it was written
in and the span the gates ran in — which the Questions page turns into two
links. The span cannot carry the question id instead, because the question
has no id yet when the gates run.

**The source is the code.** A row is a record of what was sent; editing one
changes nothing. The next start-up rewrites it when its digest, user template,
response schema or model differs from the source's.
A text that moves under an unchanged version is logged at WARNING and fails
[`tests/static/test_prompts_pinned.py`](../../tests/static/test_prompts_pinned.py).

## The embedding model

`EMBEDDING_MODEL` runs locally in the worker whatever `LLM_MODEL` names. It
does three jobs, and they are one setting because they must agree:

| | |
|---|---|
| Chunking | Counts a passage's tokens. `EMBEDDING_MAX_TOKENS` is the model's window, which a passage is cut to less the tokens the embedder adds |
| Extraction | Embeds every passage and fact into `passages.embedding` and `facts.embedding`, which this stage reads to pair passages, to find the corpus's furniture and to probe for `answerable_elsewhere` |
| The `duplicate` gate | Embeds each question into `questions.embedding`, which the HNSW index serves |

A passage sized by one tokenizer and embedded by another is silently
truncated at embed time.

**Changing it is a migration.** `passages.embedding`, `facts.embedding`,
`questions.embedding` and `topics.embedding` are `vector(1024)`, and the
worker refuses a model of another width at start-up. A different model
means altering those columns, re-embedding every stored row, and
re-chunking if its window differs.

The cost is the first start: 2.2 GB of weights into the `models` volume
before `question-worker` claims anything, which is why the topics sit
`pending`.

## Inputs and outputs

**In:** one topic with `question_status = 'pending'`, the facts of the
passages it is strongest in, and those passages.

**Written:**

| Table | Holds |
|---|---|
| `questions` | the question, its two answers, its type, form and cognitive level, the three scopes and the band derived from them, the planned band, the thread columns, the embedding, the release id, the gate that stopped it, the models that wrote it, verified it and judged its phrasing, and the verdict a person reached |
| `question_facts` | which facts each question cites. A trigger deletes a question once its last citation is gone, and rejects one that loses a citation and keeps another |

**Serves:** `/questions`, `/questions/{id}`, `/questions/plan`,
`/questions/quality`, `/questions/export`, `PATCH /questions/{id}`, and the
five queue verbs under `/questions`. See the [API README](../api/README.md).

```bash
make questions-start            # queue every topic not yet asked about
make questions                  # drain the queue here, in the foreground
make questions-status
make questions-stop
make questions-retry
make questions-rerun
make questions-start TOPIC=7    # any of the five, over one topic
make questions-reverify         # re-check stored questions; no model call
make questions-balance          # draw the balanced release
make questions-export           # write what a filter selects to an .xlsx
```

## Configuration

The values are in [`configs/env/backend.env`](../../configs/env/backend.env),
each one exactly once, except `QUESTIONS_VERIFIER_MODEL`'s, which is in
`.env`. The three model settings are fixed: served read-only and never
stored, so changing one needs a restart.

| Setting | What it does |
| --- | --- |
| `QUESTIONS_PER_TOPIC` | How many to aim for per topic. Not below the number of kinds with a weight |
| `QUESTIONS_FACT_KINDS` | Which kinds of fact a question may be written from |
| `QUESTIONS_FACT_SAMPLE` | How many facts are offered per call, divided between the passages |
| `QUESTIONS_SAMPLES_PER_PASSAGE` | How many times one passage is dealt before the stride moves on |
| `QUESTIONS_TYPE_MIX` | Which kinds are written and in what proportion |
| `QUESTIONS_DIFFICULTY_MIX` | Which bands the plan aims for |
| `QUESTIONS_ANSWER_CHARS` | Shortest and longest target answer per form |
| `QUESTIONS_ANSWER_COVERAGE` | How much of what the verifier found the target must account for. Lists only; `0` turns it off |
| `QUESTIONS_PARTY_DENSITY` | How much of a passage may be people's names before it is read as a credits page. `0` turns it off |
| `QUESTIONS_MEETS_FLOOR` | How much a candidate fact must share with the fact the head of its sample offers first before a second passage is offered. **Off** |
| `QUESTIONS_EXPLANATION_CHARS` | Shortest and longest `answer_explanation` |
| `QUESTIONS_BOILERPLATE_COSINE` | How alike a passage must be to one in another document before it is read as furniture. `0` turns it off |
| `QUESTIONS_ANSWER_OVERLAP` | How much of a list or explanation has to come back. Numbers are always exact |
| `QUESTIONS_UNANSWERABLE_SHARE` | What share are attempted with no answer in the corpus |
| `QUESTIONS_OFF_TOPIC_OVERLAP` | Below this share of shared lemmas, an unanswerable question is off-topic. **Off** |
| `QUESTIONS_ELSEWHERE_PASSAGES` | How many uncited passages the `answerable_elsewhere` probe reads |
| `QUESTIONS_ENTAILMENT_OVERLAP` | How much of what a question asks about must occur in its passages before the entailment pass may rescue it. `0` turns the guard off |
| `QUESTIONS_FOLLOWUP_SHARE` | What share of accepted answerable roots get a thread |
| `QUESTIONS_MAX_FOLLOWUPS` | How far a thread may run past its root |
| `QUESTIONS_FOLLOWUP_TYPES` | The kinds the turns of a thread take, cycled |
| `QUESTIONS_RETRIES` | How many further attempts a root question gets when a gate a rewrite can answer refuses it. An accepted draft is never asked again. Every attempt is stored |
| `QUESTIONS_LONG_ANSWER_CHARS` | Where an answer starts counting towards the band. Not a gate |
| `QUESTIONS_DUPLICATE_COSINE` | How alike two questions sharing a cited passage but no fact must be before the later one is dropped. Halfway from it to identical is the bar for two citing nothing in common, or asking with different question words |
| `QUESTIONS_DUPLICATE_SHARED_COSINE` | How alike two questions resting on the same fact must be before the later one is dropped |
| `QUESTIONS_DUPLICATE_FLOOR` | The cosine two unrelated questions score, which a question's stored confidence is measured from. Moves no verdict |
| `QUESTIONS_RELEASE_SIZE` | How many to draw. `0` is the largest the pool can fill |
| `QUESTIONS_RELEASE_UNANSWERABLE` | The most of a release that may have no answer. A ceiling |
| `QUESTIONS_RELEASE_DIFFICULTY` | How a release spreads over the bands |
| `QUESTIONS_RELEASE_TYPES` | How a release spreads over the kinds. Unset reuses `QUESTIONS_TYPE_MIX` |
| `QUESTIONS_RELEASE_LANGUAGES` | How a release spreads over the languages, by ISO 639-1 code. Unset weighs every language the pool holds alike |
| `QUESTIONS_MODEL` | A different writer. Unset means `LLM_MODEL` |
| `QUESTIONS_VERIFIER_MODEL` | The second model. Unset means `LLM_MODEL`. Where it comes out the writer's own, the entailment pass is off, and so are the opinion gates while `QUESTIONS_PHRASING_MODEL` is unset |
| `QUESTIONS_PHRASING_MODEL` | The model asked what a question's wording amounts to. Never sees a passage. Unset means the verifier's. Where it comes out the writer's own, the opinion gates are off |

Seven more are the platform's: `EMBEDDING_MODEL`, `EMBEDDING_MAX_TOKENS`,
`NLI_MODEL`, `NLI_ENTAILMENT_THRESHOLD`, `QA_MODEL`, `QA_ANSWER_CONFIDENCE`
and `ENCODER_MAX_TOKENS`. They are documented in
[`backend/nlp/`](../nlp/README.md).

## Tests

```sh
poetry run pytest tests/unit/questions
poetry run pytest tests/integration/database/test_release.py
```

| File | Covers |
|---|---|
| [`test_planning.py`](../../tests/unit/questions/test_planning.py) | What a topic is planned to be asked |
| [`test_selection.py`](../../tests/unit/questions/test_selection.py) | What the deal offers the writer, and how wide it is |
| [`test_generation.py`](../../tests/unit/questions/test_generation.py) | What the writer asks the model, and what it makes of the answer |
| [`test_verification.py`](../../tests/unit/questions/test_verification.py) | Every gate, and the order they are applied in |
| [`test_competence.py`](../../tests/unit/questions/test_competence.py) | The types whose answers are reasoned to rather than found |
| [`test_balance.py`](../../tests/unit/questions/test_balance.py) | Choosing a balanced release |
| [`test_models.py`](../../tests/unit/questions/test_models.py) | Which model writes a question, and which one checks it |
| [`test_question_service.py`](../../tests/unit/questions/test_question_service.py) | What the service does with a topic |
| [`test_reverify.py`](../../tests/unit/questions/test_reverify.py) | What a re-check does with a question a person accepted |
| [`test_phrasing.py`](../../tests/unit/questions/test_phrasing.py) | What a question's own wording says, read without a model |
| [`test_abstention.py`](../../tests/unit/questions/test_abstention.py) | A judgement that could not be had is recorded, not read as a pass |
| [`test_context.py`](../../tests/unit/questions/test_context.py) | What the writer is told about where each fact came from |
| [`test_thread_cycle.py`](../../tests/unit/questions/test_thread_cycle.py) | A thread that closes into a loop is read once |
| [`test_export.py`](../../tests/unit/questions/test_export.py) | The workbook |
| [`test_prompt_catalogue.py`](../../tests/unit/questions/test_prompt_catalogue.py) | That every prompt the stage sends is in the catalogue a version resolves against |
| [`test_questions_cli.py`](../../tests/unit/questions/test_questions_cli.py) | The re-check and the release draw on the command line |
| [`test_embedding.py`](../../tests/unit/nlp/test_embedding.py) | The embedding behind the dedup gate. Skips unless the model is cached |
| [`test_question_queue.py`](../../tests/integration/database/test_question_queue.py) | Two queues on one table |
| [`test_release.py`](../../tests/integration/database/test_release.py) | Drawing a balanced release |
| [`test_trigger.py`](../../tests/integration/database/test_trigger.py) | The trigger that deletes a question once its last fact is gone |
| [`test_frontend_vocabularies.py`](../../tests/static/test_frontend_vocabularies.py) | That the Questions page lists exactly the gates the checker can reject under |

## Limits

- **A refit rewrites the topics of every language it fits but keeps every
  question.** Questions belong
  to their facts, not to a topic. Selection skips the facts an accepted
  question already rests on, so a second run writes only about what the first
  did not reach.
- **Re-extracting a single document rejects the cross-document questions
  resting on it.** One that loses a citation and keeps another is rejected
  as `source_changed` rather than deleted, a person's acceptance included.
- **`questions-reverify` only ever rejects.** Accepting is a person's
  decision.
- **No rule gate overrules a person.** `questions-reverify` rejects a
  question a person accepted only when a fact it rests on no longer holds,
  which includes a fact a person rejected.
- **A corpus of one document gets no boilerplate filtering.** There is no
  second document for a copyright notice to repeat into.
- **`planned_difficulty` disagreeing with `difficulty` is not a fault.** The
  writer cited fewer facts than it was offered.
- **`QUESTIONS_PER_TOPIC` is what a run costs, twice over.** Each candidate
  is a writer call and a verifier call, and `QUESTIONS_FOLLOWUP_SHARE` adds a
  pair on top for every thread.
