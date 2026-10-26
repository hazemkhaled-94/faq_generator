# Question generation

The question generation stage turns each topic's facts into questions with
known answers. Each question cites the facts it was written from.

A question that fails a gate is stored with the gate's name instead of being
dropped. The rate of such failures is how the writer is judged.

## What a question is

A question is written from one or more **facts**. The writer also sees the
**passages** the facts came from. The answer must rest on the facts. The
passage and its heading trail supply the institution, document and period the
question can be phrased from.

The unit of work is a **topic**. A topic is asked about the facts of the
passages it is strongest in. A topic with `include_in_coverage = false` is
skipped, and so is a fact a person rejected in review.

## What it does

### Step 1: Plan

[`planning.py`](planning.py). A topic gets one slot per question. Each slot
carries the kind to write, the difficulty band to aim for, and whether the
question has an answer.

```ini
QUESTIONS_TYPE_MIX=factoid:<weight>,definition:<weight>,entity:<weight>,...
QUESTIONS_DIFFICULTY_MIX=easy:<weight>,medium:<weight>,hard:<weight>
```

Weights are spread over the slots by highest averages, so counts are exact
over a run and interleaved along it. A kind with a weight of `0`, or left out,
is never planned. A follow-up takes its kind from `QUESTIONS_FOLLOWUP_TYPES`.
An `easy` slot is raised to its kind's floor. An unanswerable slot is planned
`easy` and written as one of the mix's `factoid`, `entity` or `reason` kinds,
or answerable if the mix has none. `GET /questions/plan` reports the mixes,
shares and answer bounds the next run reads.

Each slot is also dealt one **category** of every categorization in
`QUESTIONS_CATEGORIZATIONS`. A categorization is a set of mutually exclusive
categories, each with a description and a probability, as in the DataMorgana
paper (Filice et al., [*Generating Q&A Benchmarks for RAG Evaluation in
Enterprise Settings*](https://aclanthology.org/2025.acl-industry.33/), ACL
2025 Industry Track). The setting holds them as the paper's Figure 2 JSON, and
`[]` deals none. Unset, it deals three categorizations at even odds: Phrasing
(concise or verbose), Linguistic variation (the document's own terms or other
words) and Premise (a direct question, or one opening with the asker's own
situation).

User expertise is not dealt unset: its conformance was 0.59 in calibration.
To opt in, list it beside the three default categorizations:

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

The deal draws no random number, so a rerun of a topic is dealt the same
categories.

### Step 2: Deal the facts

[`selection.py`](selection.py). `QUESTIONS_FACT_SAMPLE` sets how many facts
are offered, divided between the passages the sample holds and never fewer
than one from each. A reading type (an answerable slot whose answer form is
not a value) also takes the other unspent atomic facts citing the same
evidence as a fact it chose, up to 8 facts in the whole sample. The band
decides the shape of the sample:

| Band | Shape | What the deal offers | Worth |
|---|---|---|---|
| `easy` | `single` | one passage | 0 |
| `medium` | `cross` | a passage in another document, ranked by likeness | 2 |
| `hard` | `bridge` | a bridging passage in another document: another file and another subject | 3 |

Every document is dealt before any is dealt twice. Each passage
is offered `QUESTIONS_SAMPLES_PER_PASSAGE` times. The second passage is the one most like
the first, by cosine where the corpus is embedded and by shared lemmas where it
is not. A topic in one document pairs its passages within that document. A
bridge fact is offered alone.

- A passage quoting another with a bracketed ellipsis, such as a change log,
  is dealt last.
- `QUESTIONS_MEETS_SHARE` offers a second passage only when its best fact is
  among that share of the topic's closest cross-passage fact pairs. The bar is
  read from the topic's own vectors, so it is tuned to no corpus or language.
  `QUESTIONS_MEETS_FLOOR`, a fixed floor, ships off.
- A passage that is the corpus's own furniture (a copyright notice, contents
  page or revision table) is never offered. It has a twin above
  `QUESTIONS_BOILERPLATE_COSINE` in another document of its own language. The
  reading abstains for a language held by one document and for a passage with
  no embedding, and `0` turns it off.
- `QUESTIONS_PARTY_DENSITY` catches acknowledgements: the share of a passage's
  alphabetic tokens that spaCy tags `PER`.

### Step 3: Write one question

[`generation.py`](generation.py), [`types.py`](types.py). One shared rule
block holds what is true of every question: do not name the source, name the
subject in its own words because the reader never sees the passage, and ask one
question in the language of the facts. Each kind adds what it asks for, what
its answer looks like, and worked examples. An answerable writer is also told
to put into the question the case, party or condition that makes its key the
only right answer. Each call returns `target_answer`, the key a chatbot is
scored against, and `answer_explanation`. The writer decides which facts a
question cites.

The categories an answerable slot was dealt go into its user message, one
description per line, under `THE QUESTION - besides every rule you were given,
it must be:`. Where a category conflicts with a rule, the rule wins.

Some slots are told no category. An unanswerable slot is told only its kind,
and only where a categorization carrying `settles` is set (see
[Unanswerable questions](#unanswerable-questions)). A follow-up and a compound
question are told none. A category a slot cannot hold beside the others is not
told and is stored as none: a `"form": "premise"` category needs words of its
own, so it is not told beside a category that caps the words, nor beside a
search query. A premise draft with no first- or second-person speaker (`I want
to know` is noted, `I want to return a jacket` is not) is written once more
with a note asking for the asker's own situation. The question stores its
categories in `questions.categories`.

A categorization with `"role": "user"` describes the person asking. Its
categories go in a separate block headed `THE ASKER`, before the question
block, with an instruction to use it only to write the question. The verifier
and the judges never see it, so an answer that leans on something about the
asker that the question does not say is refused as not recoverable.

A category of `"form": "query"` is a search query: keywords typed into a box.
Neither of the paper's two search queries is dealt unset: in calibration the
short one was accepted for 30% of its rows, against 82-86% for the natural
phrasings. A query is not told on a slot that spans two passages or on a
`reason` slot. To deal all four phrasings at even odds, set this Phrasing in
place of the default:

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

A query's question block carries one more line saying that the question mark
rule does not apply to it. The gates lift that one rule for a query and no
other.

A draft that a gate refused for how it was written is written again with a
note saying what went wrong, up to `QUESTIONS_RETRIES` times. An accepted draft
is never asked again. Every draft is stored, and the last is the one kept.

Each topic ends in one line saying how far its plan got:

```text
topic 7: 38 of 120 slots written, stopped: deal, 0 fact(s) left
```

The topic stopped on `plan` when every slot was written, on `deal` when no
passage was left to deal from, and on `refusals` when the provider refused
every prompt in a row.

### Step 4: Gate it

[`checker.py`](checker.py), [`gates.py`](gates.py),
[`verifier.py`](verifier.py). See [The gates](#the-gates).

### Step 5: Draw a balanced release

[`balance.py`](balance.py). See [The balanced release](#the-balanced-release).

## The thirteen kinds

Every kind is a question form, never a subject, so the list applies to a
manual, a contract, a policy or a report.

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
| `aggregation` | a total no single fact states, of figures or items the facts state | value | 2 | analyse |
| `temporal` | what changed between two periods | list | 2 | analyse |
| `implication` | what must be true when two stated things both hold | explanation | 2 | analyse |
| `application` | which stated rule governs a case the material omits | explanation | 1 | apply |

A kind that needs two passages cannot be planned `easy`. `application` needs
one passage, so at `medium` and `hard` it is still dealt the one passage its
rule sits in.

An answerable `reason` slot is dealt a passage holding a fact whose evidence
carries a purpose marker (`um … zu`, `damit`, `weil`, `to prevent`, `so that`,
`because`, `in order to`). Where no passage left holds one, the slot is written
as another kind of the mix, or skipped with a warning.

The writer may decline a slot by returning `declined`, when the facts cannot
honestly answer a question of the kind asked. A declined slot is swapped to
another kind of the mix on the same facts, or skipped. A declined retry ends
the retries, and a declined follow-up ends its thread.

### Question kinds

The thirteen types say what a question asks. A question's *kind* says how it
rests on the passages, and is held in `question_generation/kinds.py`:

- `single`: one passage.
- `needs_both`: takes something from each of two passages.
- `compound`: two separate asks, one from each of two passages.
- `false_premise`: named, not written.

A `needs_both` draft citing one passage is stored `single`. `QUESTIONS_KIND_MIX`
(optional, `kind:weight`) shares the slots that span passages between kinds.
Unset it deals `needs_both:5,compound:1`, and `needs_both:1` turns compound
off. An accepted `needs_both` question citing two passages is read once more by
the verifier (prompt `verifier: stated`). It stays two-passage only when each
cited passage holds a part of the answer that no other cited passage holds.

A `compound` question joins two asks with "and", each answered by one of two
passages that share least. Each half is recovered from its own passage alone,
with no round trip on the merged question, and the row keeps both halves in
`gate_scores` as a `halves` reading. A question that claims a relation between
its halves ("differ", "both", "together", from the per-language `_RELATES`
table) is refused as `wrong_type`. The compound path is not calibrated through
the deal and missed its quality bars (see the [bugs page](../../docs/bugs.md)).

### The answer form and the two answers

`answer_form` is `value`, `list` or `explanation`. The stored form is the one
the answer fits among those the kind takes, so a `factoid` answered with three
things is stored as a `list`. Each form has its own bounds in
`QUESTIONS_ANSWER_CHARS`.

`target_answer` is short by design. `answer_explanation` is three to six
sentences saying what the thing is, for a reader who never saw the passage.
`explanation_unusable` reads it with no model call. It checks the length
(within `QUESTIONS_EXPLANATION_CHARS`, where the floor is the half that
matters), that every figure and date it asserts is in the cited passages, and
that fewer than 90% of its content lemmas are already in the target. The
column is NULL on every unanswerable question by CHECK. An answerable question
written without one is refused `explanation_unusable`.

### Cognitive level

`cognitive_level` is derived from the stored type: `recall` for factoid and
entity, `understand` for definition and enumeration, `apply` for condition,
procedure and application, and `analyse` for the rest. The answers to
`application`, `implication` and `aggregation` are not in the material, so
recoverability cannot check them. `aggregation` faces `arithmetic`, which asks
whether the cited figures come to the total. `application` and `implication`
face `entailment`, which asks whether the conclusion follows from the premises.
`GET /questions/quality` reports `cognitive_level_checked`, the number of
accepted questions of a type that a rule settles. Six types have one.

### The three criteria and the band

Each criterion is read off the facts the question reported citing:
`passage_scope` is `single_passage` or `multi_passage`, `document_scope` is
`single_document` or `cross_document`, and `topic_scope` is `single_topic` or
`multi_topic`. `difficulty` is a question's **retrieval spread**: one point for
each scope, for an answer past `QUESTIONS_LONG_ANSWER_CHARS`, and for following
another question. A total of 0-1 is `easy`, 2 `medium`, 3 or more `hard`. The
workbook calls it "Retrieval spread". The band the plan asked for is stored as
`planned_difficulty`. The two differ when the writer cited fewer facts than it
was offered, which is not a fault.

`make questions-reverify` rejects a question whose scope no longer matches its
citations. `make questions-rescore` rewrites the scopes and band from what each
question cites now, with no model call. Run it before re-verify after `make
extract-dedup` only. After a re-extraction or a deletion, skip it: re-verify
could then no longer reject a question that lost a fact as `source_changed`.

## The gates

Gates run cheapest first, in this order. The first five are one structural
step, and the free half of `leaks_source` runs in it too.

| Gate | Rejects a question that | Costs |
|---|---|---|
| `malformed` | is not a question, carries no target answer when it claims one, is in the wrong language, is one of its own facts handed back, or answers with the number of facts it cites | nothing |
| `compound` | asks two things | nothing |
| `answer_too_short` | is scored against an answer below its form's floor | nothing |
| `answer_too_long` | answers past its form's ceiling | nothing |
| `wrong_form` | answers in the wrong shape | nothing |
| `off_topic` | was written to have no answer and is about nothing the material mentions. Off as shipped | nothing |
| `wrong_type` | is not the kind it was planned as, where a rule can say so | nothing |
| `restates_question` | is answered with almost no word the question did not already carry. Answers with a number, a yes or no, or a negative, and answers to a `comparison` or a who question, are not read | nothing |
| `explanation_unusable` | is answerable and has no long answer, or one of the wrong length, with an unsupported figure, or that only restates the key | nothing |
| `asks_nothing_new` | is a follow-up citing nothing its root did not, unless it cites only summaries or outlines and a quarter of its key's content words are new | nothing |
| `off_thread` | is a follow-up resting on no passage an earlier turn of its thread used | nothing |
| `duplicate` | is a near twin of an accepted question in its own language and answerability. The bar is higher for questions sharing a passage than a fact, and highest for sharing nothing or using a different question word | one index probe |
| `answerable_after_all` | was written to have no answer and has one: an accepted answerable question on the same fact sits near it, or its own passages settle it | the probe, or one `settles` call |
| `leaks_source` | names the material its answer is in | nothing, or one question-only call |
| `unanchored` | nobody could have asked without the passage in front of them | nothing, or up to two question-only calls |
| `not_recoverable` | cites evidence its own answer is not in; or asks why where the passages give no reason beyond the question's own rule; or is a short search query that an uncited passage answers differently | the round trip |
| `answer_incomplete` | has a `list` key naming far less than the verifier found | the round trip |
| `answerable_elsewhere` | was written to have no answer and a passage it does not cite settles it | a passage probe and a second `settles` call |
| `source_changed` | rests on a fact that no longer passes its checks or that a person rejected, or whose citations no longer match its stored scope | nothing |

`questions.rejected_reason` holds exactly these values. No run of the writer
produces `source_changed`: `make questions-reverify` carries a change further
up the pipeline through to the questions resting on it.

`wrong_type` types a question whose opening asks for another kind (`Wann`,
`What happens if`, from the per-language `_ASKED_FOR` table) by that opening and
holds it to that kind's rules. After a premise, the opening is read past the
last sentence or clause end before the first question word that asks (`Ich bin
neu bei der Bank. Wann …?`).

`compound` reads a question word introduced by a conjunction after the first
(`When is it due and for how long?`) as a second question. A search query (a
category of form `query`) is not `malformed` for lacking a question mark. A
re-check reads the form off the categories the row stores, so a row stored
without one is held to the question mark.

### The round trip

`not_recoverable` is the gate no similarity measure can replace. A second
model is shown only the cited passages and asked to answer. It answers only
where the passages answer the question as asked, and says whether a why has a
reason beyond its own rule. The question survives if what comes back carries
every number, name and date the target asserts, and enough of what it is
about.

- A `value` is compared whole. A `list` or `explanation` is compared by
  overlap (`QUESTIONS_ANSWER_OVERLAP`) over what it adds to the question.
- Numbers are always exact: `4 hours` never passes for `48 hours`. A written
  count is its figure (`two conditions` is `2 conditions`) for the languages
  whose number words the gates hold.
- A figure is read by its language's decimal mark, `DECIMAL_MARK` in
  [`nlp/analysis.py`](../nlp/analysis.py): a German `1,234 %` is a rate and
  `1.234` a count, and English is the reverse. A range (`68–70 cm`) asserts
  both ends.
- A name the question carries, or every heading trail of the cited passages,
  need not come back. A heading never supplies a figure.
- Only a `list` is checked for completeness. An `explanation` key of a
  `condition`, `procedure`, `enumeration`, `consequence` or `definition`
  question is also read in shadow: the share of the recovery's content words
  the key carries is stored in `gate_scores` as `coverage`, with
  `QUESTIONS_ANSWER_COVERAGE` beside it, and refuses nothing.

The entailment pass rescues only a recovery that fell short, never a question
whose answer the verifier found not in the passages at all.

The verifier should be a different model from the writer, because a model
marking its own work recovers what it just wrote. The stage warns when the two
are the same. The verifier never sees the corpus. A search query bounded to a few
words (`short-search-query`) is read once more against the
`QUESTIONS_ELSEWHERE_PASSAGES` passages nearest it that it does not cite. An
answer they give that disagrees with the key refuses it as `not_recoverable`.

`unanchored` and `leaks_source` are opinions asked of
`QUESTIONS_PHRASING_MODEL`, one judgement per call, before the round trip. They
are off when the phrasing model is the writer's own, except the rule half of
`leaks_source`. `unanchored` also catches a question that points outward: a
demonstrative (`this version`), a counted definite noun (`the two editions`),
or an anaphoric adjective (`aforementioned`, `latter`). These readings are
words, so a third language has to be added to each.
[`backend/nlp/`](../nlp/README.md) lists them. A gate whose language is
missing does nothing, silently. Unset, `QUESTIONS_PHRASING_MODEL` falls back to
`QUESTIONS_VERIFIER_MODEL`.

## Unanswerable questions

Some questions are written to have no answer, by perturbing a verified fact
just out of reach. `QUESTIONS_UNANSWERABLE_SHARE` sets how many are
attempted, spread by position. Each is planned `easy` from one passage, dealt
an atomic fact first, and written only as a `factoid`, `entity` or `reason`
kind: a set, a condition or a definition is settled by a closed list or a rule
in the material.

The writer is shown the passage its fact rests on and the passages two
ordinals either side of it. None of them may answer the question, contradict
its premise, name a closed list or rule the case falls outside (`only`,
`every`, `no other`), or state a general rule that covers the case.

### Kinds

UAEval4RAG (Peng et al., [*Unanswerability Evaluation for Retrieval Augmented
Generation*](https://aclanthology.org/2025.acl-long.415/), ACL 2025) writes
unanswerable requests in kinds. Four of its six can be dealt as one
categorization, `UNANSWERABLE_CATEGORIZATION` in [`config.py`](config.py),
whose JSON the [configuration
guide](../../docs/configuration.md#a-json-value) quotes. The default deals
`out-of-corpus` alone, the one kind that passed calibration
([measurements](../../docs/measurements.md#unanswerable-kinds-v050)). The
other three are opt-in, in place of the default's own `Unanswerable` entry,
and their current prompts are not calibrated. Each category carries
`settles`, the verdict the passages it cites must give, and `behaviour`, what
a good reply does:

| Category | Paper | `settles` | What it must do |
|---|---|---|---|
| `out-of-corpus` | Out-of-Database | `silent` | move one detail of the fact just out of reach, never to the absurd |
| `false-presupposition` | False-presupposition | `refutes` | take for granted something a sentence of the passage says is not so |
| `underspecified` | Underspecified | `answers` | leave out the detail the passage needs to choose between its cases, so each case has its own answer |
| `nonsensical` | Nonsensical, illogical content only | `silent` | join things the passage names in a way that makes no sense |

Modality-limited and safety-concerned are left out: they test a chatbot, not
the documents.

Only an unanswerable slot is told its category, in a `WHAT MAKES IT A TEST`
block under the passages. The block wins over the FORMAT rules. `underspecified` may
decline a passage with no value that varies by case, which skips the slot.

A draft is kept where the cited passages give the kind's `settles` verdict with
words of theirs behind it, and where the probe gives that verdict or `silent`.
Any other verdict that answers it refuses it, and `silent` where the kind wants
another is `wrong_type`. A categorization carrying `settles` must have the role
`question` and every category the form `question`. `underspecified` has no
check of its own.

### Attempted, not held

Unanswerable questions face `answerable_after_all`, `answerable_elsewhere` and
`off_topic`. The two that are on bite, so the default share sits above the
release share. Every attempt `QUESTIONS_UNANSWERABLE_SHARE` plans
is written and checked, `settles` calls included, whatever
`QUESTIONS_RELEASE_UNANSWERABLE` allows. At a ceiling of 0 those calls buy
nothing, so lower the share to save them.

**Known defect.** The ceiling ships at 0.10, and the `settles` reading still
keeps about a third of kept rows that the material answers (see
[measurements](../../docs/measurements.md#unanswerable-kinds-v050)). Up to
about a third of the unanswerable questions a release holds are answered by
the corpus after all.

`Verifier.settles` asks whether the passages state the answer, refute its
premise (a closed list or an exception included), or cover its case with a
general rule (`answers`, `refutes`, `rule`), or settle nothing (`silent`, the
only verdict that keeps the question). The verifier writes the reply a careful
chatbot would give before its verdict.

- The verdict's quote must be words the passages it was shown carry. A quote
  from memory reads as `silent`.
- The reading runs over the cited passages first, then over them and the probe
  together. The probe is the `QUESTIONS_ELSEWHERE_PASSAGES` passages nearest
  by vector, fused with those sharing most lemmas, plus the passages two
  ordinals either side of each cited one. A corpus with no vectors is probed
  by shared lemmas alone.
- Each verdict is stored in `gate_scores` as `settles` and `settles_elsewhere`
  (1 for silent, 0 for settled). It takes no part in confidence.

A question refused because a passage of its own topic `answers` it or covers
it by a `rule` is recycled: the topic at once writes an answerable question of
the same kind and band from that passage's facts.

`make questions-rejudge` asks the same of the questions already accepted and
writes each verdict on the row. It skips a row that already carries a verdict
given under the current verifier `PROMPT_VERSION`, so after the version
changes the first run asks again about every accepted unanswerable question.
A question the model will not answer about is logged and written nothing. Five
in a row stop the run with the last error.

`off_topic` ships off (`QUESTIONS_OFF_TOPIC_OVERLAP=0`): its vocabulary, the
lemmas of the cited passages, is too small to tell off-topic questions from
questions about the material.

## Follow-up threads

A share of accepted questions get a thread, up to `QUESTIONS_MAX_FOLLOWUPS`
deep. `follows_id` and `thread_position` carry it. Each turn takes the next
kind in `QUESTIONS_FOLLOWUP_TYPES`, cycled from where the thread sits among
the followed ones.

A follow-up may lean on the conversation (*"And for an urgent one?"*), so it
skips `unanchored` and the verifier is shown the conversation.
A follow-up is stored `needs_both` only where its root was dealt `needs_both`.
`asks_nothing_new` and `off_thread` hold the thread together. Only an accepted,
answerable root is followed. A thread stops at the first follow-up a gate
refuses. Each follow-up costs a writer call and a verifier call.

## Coverage

`topics_covered` counts every finished topic in coverage, whether or not it
produced an accepted question. `/questions/quality` also reports how much of
the material the accepted questions reach.

A sample burns every fact it offers, whether or not the question cites it:
`QUESTIONS_FACT_SAMPLE` of them or, for a reading type that took a list whole,
up to 8. No fact is offered twice within one topic, so past a point
`QUESTIONS_PER_TOPIC` is inert. Coverage rises by running again and by
lowering `QUESTIONS_FACT_SAMPLE`. Figures are in
[measurements](../../docs/measurements.md).

## The balanced release

The run overgenerates, and `make questions-balance` then fills a quota out of
everything accepted and writes `questions.release_id` on what it drew. Four
shares are held at once: `QUESTIONS_RELEASE_UNANSWERABLE` (a ceiling, 0.10 as
shipped), `QUESTIONS_RELEASE_DIFFICULTY`, `QUESTIONS_RELEASE_TYPES` and
`QUESTIONS_RELEASE_LANGUAGES`. They are marginals, not a joint distribution:
an even spread of kinds within each band is not reachable, because a short
`factoid` answer cannot earn the length point a `hard` question needs. The
draw goes in the order of an md5 of the question's id, so the same pool and
settings draw the same release twice.

A release holds one question of each twin group. Twins are read by the
`duplicate` gate's own rule, then by `Verifier.same_answer`: each released
question and its nearest released neighbour are asked whether one correct reply
serves both. A pair read as one answer joins the twin groups and the release is
drawn again, up to three times. A fourth round drops the later question of each
remaining pair, so the release is a little smaller. That is about
one call per released question. Its scores are in
[docs/bugs.md](../../docs/bugs.md#found-on-the-v022-rebuild-of-2026-10-14).

`QUESTIONS_RELEASE_SIZE=0` draws the largest release the pool can fill to
within `TOLERANCE` of every quota. A kind the pool holds too few of is asked
for what the pool has, and the other kinds take its places by largest
remainder.

The command reports what it drew, its spread over every share, and any quota
the pool came up short on (`reason (60 of the 90 asked)`). It also reports the
categories the released questions were told and the pool's counts for the same
labels. No quota holds a category, so a release can drift from the mix its
questions were written in:

```text
  category    Phrasing=concise-and-natural 30 (25%), Phrasing=verbose-and-natural 28 (23%), ...
  in the pool Phrasing=concise-and-natural 120 (24%), Phrasing=verbose-and-natural 131 (26%), ...
```

Nothing is deleted. The draw re-checks first, as `questions-reverify` does, and
rejects a question before it can be drawn when a fact it cites no longer holds
or its scope moved (`source_changed`), when it fails the structural gates other
than the document-title check or its type's rules, or when the duplicate probe
finds an earlier twin. A question a person accepted is checked on its facts
alone. The gates that judge a question only when it is written (`off_topic`,
`explanation_unusable`, the pattern half of `leaks_source`, `asks_nothing_new`,
`off_thread`) are not run again. Beyond that, drawing again with different
shares replaces the first release. The draw always covers every accepted
question: `--only` is refused, and `make questions-balance` takes no
`TOPIC=`.

`FILTER="--released"` exports the release, `released=true` narrows `GET
/questions` to it, and **Released** does the same on the Questions page. A
released question that a person or a re-check moves off `accepted`, or that
loses one of its facts, leaves the release.

## Getting the dataset out

[`export.py`](export.py).

```bash
make questions-export OUT=exam.xlsx FILTER="--status accepted --cognitive-level analyse"
```

The workbook has four sheets:

| Sheet | One row per |
|---|---|
| Questions | Question, with what it rests on folded in. A Kind column (single, needs_both, compound) follows Type |
| Citations | Question, fact and passage, so a bridge takes two. The Document ID column is the head of the document's digest, which `--diversity --by document` splits by |
| Assessment | Judgement of a question. Empty unless the evaluation phase has run |
| Summary | The counts from the quality report: types, bands, levels, rejections, kinds, each `categorization=category`, languages, and the models that wrote, verified and judged the questions |

A row reads on its own. **Earlier turns** holds a follow-up's parent questions
and keys, oldest first. **Source** gives the document, pages and section path
of each fact the question rests on. **Retrieval spread** is the `difficulty`
band. The **Categories** column names the categories each question's writer
was told (`Phrasing=concise-and-natural`), or only the kind for an
unanswerable question (`Unanswerable=false-presupposition`). The Summary says
its counts are not a quality estimate, and counts the documents and passages
that no accepted question the filter selects reaches. `make questions-status`
counts them over the whole corpus.

An unanswerable question has no key, so its **Answer** cell gives what a good
reply does for its kind, as UAEval4RAG accepts one in its Table 11:
`Expected behaviour: asks which case is meant, or gives the answer for each
case the material distinguishes`. A judge or a person scores a reply against
it. It is not a reference answer to match as a string.

The same workbook comes from `GET /questions/export` and from **Build a
workbook** on the Questions page. With no filter it holds everything, rejected
rows included. `--no-citations` leaves the Citations sheet empty and skips its
cost. A document with no title is named by the first 12 characters of its
digest.

### Reading the benchmark

A generated benchmark ranks retrieval set-ups more reliably than it ranks the
models that write the answers, and its questions run easier than real users'
questions, so absolute scores are optimistic. Judge the chatbot with another
model family than the one that wrote the set. The studies behind this, van
Elburg et al. (ECML PKDD 2025 workshops) and Rahmani et al. (SIGIR 2024), are
on [the measurements
page](../../docs/measurements.md#what-a-generated-benchmark-can-rank).

## Reading back the prompt that wrote a question

Every question carries `prompt_version`. Three modules declare one, bumped
separately: `types.PROMPT_VERSION` for the thirteen writers,
`phrasing.PROMPT_VERSION` for the three wording judgements, and
`verifier.PROMPT_VERSION` for the verifier's reads.

The stage records what it sends at start-up: [`prompts.py`](prompts.py)
declares it and `stages.prompts` writes it to the `prompts` table, with the
system message, the user message as its template, and the JSON schema. Read one
back on the Questions page
("The prompt that wrote this", under a selected question), as JSON with `GET
/prompts?service=questions&version=15&name=factoid`, or in Phoenix beside the
traces. A question also carries `trace_id` and `span_id`, which the Questions
page turns into two links.

The source is the code. Editing a row changes nothing: the next start-up
rewrites it when its digest, template, schema or model differs from the
source's. A text that changes under an unchanged version is logged at WARNING
and fails
[`tests/static/test_prompts_pinned.py`](../../tests/static/test_prompts_pinned.py).

## The embedding model

`EMBEDDING_MODEL` runs locally in the worker, whatever `LLM_MODEL` names. One
setting serves three jobs: counting a passage's tokens for chunking
(`EMBEDDING_MAX_TOKENS` is the model's window), embedding every passage and
fact (which this stage reads to pair passages, to find furniture and to probe
for `answerable_elsewhere`), and embedding each question into
`questions.embedding`, which the HNSW index serves to the `duplicate` gate.

Changing the model is a migration. The `embedding` columns of `passages`,
`facts`, `questions` and `topics` are `vector(1024)`, and the worker refuses a
model of another width at start-up. A different model means altering those
columns, re-embedding every stored row, and re-chunking if its window differs. The first start downloads 2.2 GB of weights into the `models` volume
before `question-worker` claims anything, so topics sit `pending` until then.

## Inputs and outputs

The stage reads one topic with `question_status = 'pending'` and writes rows
in `questions` and `question_facts` (which facts each question cites). A
trigger deletes a question once its last citation is gone, and rejects one that
loses a citation and keeps another. It serves `/questions`, `/questions/{id}`,
`/questions/plan`, `/questions/quality`, `/questions/export`, `PATCH
/questions/{id}` and the five queue verbs under `/questions`. See the [API
README](../api/README.md).

```bash
make questions-start            # queue every topic not yet asked about
make questions                  # drain the queue here, in the foreground
make questions-status           # also: documents and passages no accepted question reaches
make questions-stop
make questions-retry
make questions-rerun CONFIRM=<database>
make questions-start TOPIC=7    # any of the five, over one topic
make questions-reverify         # re-check stored questions; no model call
make questions-rejudge          # ask whether the passages settle each accepted unanswerable; calls the verifier
make questions-rescore          # rewrite stored scopes and bands; no model call
make questions-balance          # draw the balanced release
make questions-export           # write what a filter selects to an .xlsx
```

## Configuration

The values are in [`configs/env/backend.env`](../../configs/env/backend.env),
each one exactly once, except `QUESTIONS_VERIFIER_MODEL`'s, which is in `.env`.
The three model settings are served read-only and never stored, so changing
one needs a restart.

| Setting | What it does |
|---|---|
| `QUESTIONS_PER_TOPIC` | Questions to aim for per topic. Not below the number of kinds with a weight |
| `QUESTIONS_FACT_KINDS` | Which kinds of fact a question may be written from |
| `QUESTIONS_FACT_SAMPLE` | Facts offered per call, at least one from each passage. A reading type also takes the rest of a chosen fact's list, up to 8 |
| `QUESTIONS_SAMPLES_PER_PASSAGE` | How many times one passage is dealt before the stride moves on |
| `QUESTIONS_TYPE_MIX` | Which kinds are written and in what proportion |
| `QUESTIONS_KIND_MIX` | Optional `kind:weight` list sharing the slots that span passages between `needs_both` and `compound`. Default `needs_both:5,compound:1` |
| `QUESTIONS_DIFFICULTY_MIX` | Which bands the plan aims for |
| `QUESTIONS_CATEGORIZATIONS` | The categorizations as JSON: one Figure 2 object or a list. `role` is `question` (default) or `user`. `form` is `question` (default), `query` or `premise`. A category may carry `"words": {"min": N, "max": N}`, which `make diversity BY=category` reports on and no question is refused for. Probabilities are given for every category or for none (uniform) and sum to 1 within 0.01. A bad key, duplicate name, `=`, comma or line break in a name, or blank description is refused. Unset reads the defaults from code. Set it on the settings page, with `PATCH /settings/questions`, or with `python -m settings.run`. `[]` writes none |
| `QUESTIONS_ANSWER_CHARS` | Shortest and longest target answer per form |
| `QUESTIONS_EXPLANATION_CHARS` | Shortest and longest `answer_explanation` |
| `QUESTIONS_LONG_ANSWER_CHARS` | Where an answer starts counting towards the band. Not a gate |
| `QUESTIONS_ANSWER_OVERLAP` | How much of a list or explanation has to come back. Numbers are always exact |
| `QUESTIONS_ANSWER_COVERAGE` | How much of what the verifier found a list key must cover. `0` turns it off |
| `QUESTIONS_ENTAILMENT_OVERLAP` | How much of a question's subject must occur in its passages before the entailment pass may rescue it. `0` turns it off |
| `QUESTIONS_PARTY_DENSITY` | How much of a passage may be people's names before it is read as a credits page. `0` turns it off |
| `QUESTIONS_BOILERPLATE_COSINE` | How alike a passage must be to one in another document of its own language to be read as furniture. `0` turns it off |
| `QUESTIONS_MEETS_SHARE` | The share of a topic's closest cross-passage fact pairs a second passage must be among. `0` sets no floor. Default 0.02 |
| `QUESTIONS_MEETS_FLOOR` | A fixed floor on the first fact offered. Off |
| `QUESTIONS_UNANSWERABLE_SHARE` | What share of questions are attempted with no answer in the corpus |
| `QUESTIONS_OFF_TOPIC_OVERLAP` | Below this share of shared lemmas, an unanswerable question is off-topic. Off |
| `QUESTIONS_ELSEWHERE_PASSAGES` | How many uncited passages the `answerable_elsewhere` probe reads |
| `QUESTIONS_FOLLOWUP_SHARE` | What share of accepted answerable roots get a thread |
| `QUESTIONS_MAX_FOLLOWUPS` | How far a thread may run past its root |
| `QUESTIONS_FOLLOWUP_TYPES` | The kinds the turns of a thread take, cycled |
| `QUESTIONS_RETRIES` | Further attempts a root question gets after a refusal a rewrite can fix. Every attempt is stored |
| `QUESTIONS_DUPLICATE_COSINE` | Similarity at which the later of two questions sharing a passage but no fact is dropped. Halfway to identical is the bar for two sharing nothing |
| `QUESTIONS_DUPLICATE_SHARED_COSINE` | The same for two questions resting on one fact. Unset uses `QUESTIONS_DUPLICATE_COSINE` |
| `QUESTIONS_DUPLICATE_FLOOR` | The cosine two unrelated questions score. Sets stored confidence and moves no verdict |
| `QUESTIONS_RELEASE_SIZE` | Questions to draw. `0` is the largest the pool can fill |
| `QUESTIONS_RELEASE_UNANSWERABLE` | The most of a release that may have no answer. A ceiling, 0.10 as shipped; 0 releases none |
| `QUESTIONS_RELEASE_DIFFICULTY` | How a release spreads over the bands. Unset follows the answerable pool |
| `QUESTIONS_RELEASE_TYPES` | How a release spreads over the kinds. Unset reuses `QUESTIONS_TYPE_MIX` |
| `QUESTIONS_RELEASE_LANGUAGES` | How a release spreads over the languages, by ISO 639-1 code. Unset follows the pool |
| `QUESTIONS_MODEL` | A different writer. Unset means `LLM_MODEL` |
| `QUESTIONS_VERIFIER_MODEL` | The second model. Unset means `LLM_MODEL`. Where it is the writer's own, the entailment pass is off, and so are the opinion gates while `QUESTIONS_PHRASING_MODEL` is unset |
| `QUESTIONS_PHRASING_MODEL` | The model asked what a question's wording amounts to. Never sees a passage. Unset means the verifier's. Where it is the writer's own, the opinion gates are off |

Seven more settings belong to the platform: `EMBEDDING_MODEL`,
`EMBEDDING_MAX_TOKENS`, `NLI_MODEL`, `NLI_ENTAILMENT_THRESHOLD`, `QA_MODEL`,
`QA_ANSWER_CONFIDENCE` and `ENCODER_MAX_TOKENS`. They are documented in
[`backend/nlp/`](../nlp/README.md).

## Tests

```sh
poetry run pytest tests/unit/questions
poetry run pytest tests/integration/database/test_release.py
```

The unit tests in [`tests/unit/questions`](../../tests/unit/questions) cover
every step above, the gates and the release. The integration tests
[`test_question_queue.py`](../../tests/integration/database/test_question_queue.py),
[`test_release.py`](../../tests/integration/database/test_release.py) and
[`test_trigger.py`](../../tests/integration/database/test_trigger.py) cover
the queue, the release draw and the trigger that deletes a question with its
last fact. [`test_embedding.py`](../../tests/unit/nlp/test_embedding.py) skips
unless the embedding model is cached.
[`test_frontend_vocabularies.py`](../../tests/static/test_frontend_vocabularies.py)
checks that the Questions page lists exactly the gates the checker can reject
under.

## Limits

- A refit rewrites the topics of every language it fits but keeps every
  question. Selection skips the facts an accepted question already rests on,
  so a second run writes only about what the first did not reach. `make
  questions-rerun` asks again about every topic. A fit or a delete is refused
  while a worker is writing from a topic.
- Re-extracting a single document rejects the cross-document questions
  resting on it as `source_changed`, a person's acceptance included.
- `questions-reverify` and `questions-rejudge` only reject, and neither
  overrules a person. `questions-reverify` rejects a question a person
  accepted only when a fact it rests on no longer holds, which includes a fact
  a person rejected. `questions-rejudge` covers released questions and leaves
  a question a person accepted alone.
- A language held by one document gets no boilerplate filtering. Only another
  document of the same language counts as a twin, so a corpus holding one
  document per language offers its copyright pages and contents tables to the
  writer.
