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
is planned `easy` and written as one of the mix's `factoid`, `entity` or `reason`
kinds (a mix with none of them writes the slot answerable). A kind that declares a floor of its own while needing one
passage is dealt one passage whatever its band, so it is never told to span. `GET /questions/plan` reports the configured mixes, shares
and answer bounds the next run will read.

Each slot is also dealt one **category** of every categorization in
`QUESTIONS_CATEGORIZATIONS`. Categorizations are how the DataMorgana paper
(Filice et al., [*Generating Q&A Benchmarks for RAG Evaluation in Enterprise
Settings*](https://aclanthology.org/2025.acl-industry.33/), ACL 2025 Industry Track)
describes the traffic a benchmark should look like:
each is a set of mutually exclusive categories, each category a description
of what a question of it is like and how often it is wanted. The setting
holds them as the paper's Figure 2 JSON. Unset, it reads three of the paper's
Table 5 categorizations, every category at even odds: Phrasing, a concise
natural question of fewer than 10 words or a verbose one of more than 9;
Linguistic variation, a question in the document's own terms or one in other
words that keeps every term's meaning and coins none, which passed its
calibration against the first reworded so; and Premise, a direct question or one opening with a short premise in which the
asker states, in the first person, a fact of their own situation, something
they have, did, bought or plan, never only the topic, the kind of answer
wanted or that they are reading or checking something. That one is reworded from the paper's, which made the asker
optional: a quarter of accepted with-premise rows opened on a label naming a
setting, never the asker, and one gave its answer away. `[]` deals none.

Table 5's User expertise is not dealt unset, and is there to opt into, the
expert described by what an expert asks, in the material's own terms. Its
conformance was 0.59 in calibration: told on slots whose fact is basic, it
asks basic questions in an expert's voice. A categorization left with its one
other category would rewrite every question. A value listing it beside the
default's three answerable ones deals it so:

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

The deal draws no random number, like the rest of the plan. Each
categorization's probabilities become an exact quota of the topic's slots,
rounded up or down by an offset hashed from the topic, so no category takes
the spare slot in every topic. The quota is then put in an order of its own,
hashed from the topic id and the categorization, so two categorizations meet
in every pairing and a topic that runs out of material early has drawn a
fair sample of the quota rather than its first category. A rerun of a topic
is dealt the same categories, and a slot swapped to another kind keeps the
ones it was dealt.

### Step 2 — Deal the facts

[`selection.py`](selection.py). `QUESTIONS_FACT_SAMPLE` sets how many facts
are offered, divided between the passages the sample holds and never fewer
than one from each. A reading type — an answerable slot whose answer form is
not a value — also takes the other unspent atomic facts citing the same
evidence as one it chose, the rest of that fact's list, up to 8 facts in the
whole sample, so its sample can be larger than `QUESTIONS_FACT_SAMPLE`. The
band decides the shape of the sample:

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
best, except for a compound sample, whose partner offers its own facts in its own
order. Cosine where the corpus is embedded, shared lemmas where it is not —
vectors are preferred because a lemma overlap cannot see a synonym. A fact is
weighed against the **nearest** of the facts already offered, not their mean.

A bridge fact is offered alone, whichever passage it was dealt from: it
already spans the passages a wide question needs, and offered beside a claim
of its own passage it was joined to that claim, whose second passage nothing
had weighed against it. The claim waits for its passage's next round.

Where nothing in the second passage meets the first, the sample is still
offered and the writer is told to narrow. `difficulty` is read off what it
cited, so a question that narrowed bands as what it is, and stands: nothing
asks it to widen.

A reading type is offered the condensed facts first; a `value` type is not.
A passage quoting another with a bracketed ellipsis, such as a change log, is
dealt only after every other passage, and an answerable `enumeration`,
`procedure` or `condition` slot prefers the passage stating the text in full.
An answerable `reason` slot is dealt the next passage holding a fact whose
evidence states a reason, and offered that fact first — see
[The thirteen kinds](#the-thirteen-kinds).
`QUESTIONS_MEETS_FLOOR` would narrow the sample where the second passage
meets nothing, and ships off — the sweep found no threshold that removes
the welds without throwing away sound questions. It weighs the fact the first
passage offers first, so for a reading type that is the condensed one.
The deal uses a relative floor instead, `QUESTIONS_MEETS_SHARE`: a second
passage is offered only when its best fact is among that share of the topic's
closest cross-passage fact pairs. The bar is read off the topic's own vectors,
so no cosine is tuned to a corpus or a language, and the closest pair always
clears it. While `QUESTIONS_MEETS_FLOOR` or `QUESTIONS_MEETS_SHARE` is above
0, the floor is read over the second passage's facts that do not restate the
head's first word for word, and a passage holding nothing but such copies is
not offered, since it answers nothing the head does not. A second passage
never offers a fact that copies one already offered word for word, and a
compound partner is never a passage whose claims are all copies of the head's.
A reading's lists leave each later passage room under the cap of eight facts.

**The corpus's own furniture is never offered.** A copyright notice, contents
page or revision table is real text a fact extracts from cleanly and no gate
downstream refuses. It is read by **repetition, not vocabulary** — a passage
with a twin above `QUESTIONS_BOILERPLATE_COSINE` in another document of its
own language — so nothing about a language, a domain or a section name is
assumed. Three ways it abstains: a language held by one document has nothing
to repeat into, a passage with no embedding cannot be compared, and a
threshold of `0` turns it off.

Acknowledgements defeat that reading, because every document thanks different
people. `QUESTIONS_PARTY_DENSITY` reads them instead: the share of a
passage's alphabetic tokens spaCy tags `PER`. `PER` and not `ORG`, because a
corpus names organisations throughout its subject matter. It runs in
[`service.py`](service.py) rather than in the queue, once per distinct
passage.

### Step 3 — Write one question

[`generation.py`](generation.py), [`types.py`](types.py). One shared rule
block holds what is true of every question — do not name the source, name the
subject, ask about the rule a person or a story in the material illustrates
and never about the person or the page's contact box, legend or list of
changes, one question, the language of the facts — and each kind adds what it
asks for, what its answer looks like, and one or two worked examples.

Each call returns **two answers**: `target_answer`, the key a chatbot is
scored against, and `answer_explanation` beside it.

Which facts a question cites is the **writer's** answer, not the sample's. A
sample wider than one passage also carries an instruction to use both halves.

The categories an answerable slot was dealt go into its user message, between
the passages and the request, one description per line:

```text
THE QUESTION - besides every rule you were given, it must be:
- phrased in the way people typically speak, ... less than 10 words.
Where one of these conflicts with a rule you were given, the rule wins.
```

The rules win because a category is an operator's text and the rules are
what keeps a question usable: fewer than ten words does not license dropping
the subject a searcher has to name. A description is sent as written, and a
placeholder typed into one fills nothing. An unanswerable slot is dealt
categories and told only its kind, where the unanswerable categorization
below is set, and none otherwise, because the paper asks only questions that
have an answer; a follow-up is told none either. A slot asked for as a compound
question is told none too, because its reply is one question joining two
asks, which a category written for one ask contradicts; one written single
for want of a partner is told its categories. A category a slot cannot hold
beside the others is not told, and is stored as no category of its
categorization: a category of `"form": "premise"`, as the default's
with-premise is, needs words of its own, so it is not told beside one capping
the question's words, as concise-and-natural does, nor beside a search query,
where the writer shrank it to a label naming a setting. A first draft told a
premise whose premise, the text before `asked()` finds the question or before
a dash set off by spaces where it finds none, holds none of its language's
first- or second-person pronouns and possessives (`_SPEAKING`), or whose main
verbs, read through the infinitive each takes, only want, try, check or
understand (`_ENQUIRING`: `I want to know` is noted, `I want to return a
jacket` is not), is written once more with a note asking for the asker's own
situation, and the second
draft is the one checked; nothing is refused for it, and a language with no
row is never noted. A slot told none is sent the
message prompt version 16 sent, byte for byte. A retry is sent the same block
as the draft it rewrites. The question records the categories it was told in
`questions.categories`, as categorization, category, role, form and
description, so a categorization edited later does not rewrite what an
earlier question was asked to be.

A categorization with `"role": "user"` describes the person asking rather
than the question, as the paper's Figure 3 does with its novice and expert.
Its categories go in a block of their own, before the question block, as the
paper's Figure 4 splits them:

```text
THE ASKER - write the question as this person would ask it:
- a regular user with no understanding of specialized terms.
Use this only to write the question. The answer and the explanation must ignore it: they assume nothing about the asker that the question does not say.
```

The asker shapes the question only. The verifier and the judges are never
shown it: the round trip reads the question and its passages alone, so an
answer that leans on something about the asker the question does not say
cannot be got back out of them and is refused as not recoverable. A slot
dealt only user categories gets no question block. Prompt version 18 is the
first to send the asker block; a slot dealt no user category is sent what
version 17 sent.

A category of `"form": "query"` is a search query: keywords typed into a
box, as Table 5's short and long search queries are. Neither is dealt
unset, and both are there to opt into: in calibration the short search query
was accepted for 30% of its rows against 82-86% for the natural phrasings on
the same slots, and the long one, described as keywords and nothing else,
reached 36 accepted rows, under the 40 a category is measured on. Neither is told on a slot that spans
two passages, whose keywords cannot say how the two meet, nor on a type whose
question word is the ask (`TypeSpec.keywords` false, which only `reason`
needs: `comparison`, `implication` and `temporal` span anyway); such a slot
is written as no category of the query's categorization. A Phrasing listing them beside the
two natural phrasings, set in place of the default's, deals all four at even
odds:

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

The rules ask for a
question ending in a question mark, and the rules win, so its question block
carries one more line, before the rules are said to win:

```text
This one is typed into a search box: keywords, no question mark. The rule about the question mark does not apply to it; every other rule does.
```

The gates lift that one rule for it too, and only that one: a query is
still refused for two question marks, for asking two things, for naming its
source or for an answer the passages do not give. A malformed query is
asked again for one well-formed search query in keywords, where a question
is told to end in a single question mark. Prompt version 19 is the first to
send the line; a slot dealt no query is sent what version 18 sent.

A draft a gate refused for how it was written — two questions welded
together, its source named, an answer of the wrong shape — is written again
with a note saying what went wrong, up to `QUESTIONS_RETRIES` times. An
accepted draft is never asked again, however narrow it came out: asking it
to cite every passage it was offered asks for the weld the span rules
forbid. Every draft is stored, and the last is the one kept: every draft
before it was refused.

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
| `aggregation` | a total no single fact states on its own, of figures or items the facts state and never of the facts themselves | value | 2 | analyse |
| `temporal` | what changed between two periods | list | 2 | analyse |
| `implication` | what must be true when two stated things both hold | explanation | 2 | analyse |
| `application` | which stated rule governs a case the material omits | explanation | 1 | apply |

A type needing two passages cannot be planned `easy`. `application` is the
exception and declares a **floor** of its own: it needs one passage, but the
case it puts the rule to is not in the material. Its band is that work, not a
wider sample: at `medium` and `hard` it is still dealt the one passage its
rule sits in, and never told to use two.

A `reason` is only as good as the reason the material states: dealt a rule,
the writer returns the rule restated or a reason it invented, and no gate
tells either from a sound one. So an answerable `reason` slot is dealt from
a passage holding a fact whose **evidence** carries a purpose marker —
`um … zu`, `damit`, `Zweck` (not under `für`), `weil`; `to prevent`,
`so that`, `because`, `in order to` — read as lemmas and tokens in
[`gates.py`](gates.py), so `For the purposes of` is not one. Those facts are
offered first; the rest of the sample is filled as any slot's is, so it may
carry unmarked facts beside them, and which ones the question cites is still
the writer's answer. Where no passage left holds one, the slot is written as
another kind of the mix that does not span, cycled in mix order, and skipped with a warning if the mix has none. A thread whose material
states no reason drops `reason` from its `QUESTIONS_FOLLOWUP_TYPES` cycle,
and is not followed, with a warning, if no other kind is left. It is a
preference over what is dealt, not a gate, and a language with no markers is
dealt as before.

**The writer may decline a slot.** Its answer carries `declined`, set where
the facts it was dealt cannot answer a question of the kind asked honestly —
a reason they never give, a list they hold one item of. A declined slot is
swapped to another kind of the mix on the same facts, in the shape and kind
the slot was dealt, cycled as the reason swap is (a slot spanning passages is
never swapped to `application`, which is dealt one), and skipped if the mix
has no such kind or the writer declines that too; a declined retry ends the retries, and a declined follow-up ends
its thread. The writer is also told to write about the subject and never
about the facts or the task: "the material says", "both statements".

### Question kinds

The thirteen types say what a question asks; a question's *kind* says how it
rests on the passages. Every slot the plan deals carries one, held in
`question_generation/kinds.py`: `single` (one passage), `needs_both` (takes
something from each of two passages) and `compound` (below); `false_premise`
is named for later. The kind, not the count of cited passages, chooses the
writer's instruction and response shape and the extra checks a draft gets; the
stored kind (`questions.kind`) follows the citations, so a `needs_both` draft
that ends up citing one passage is stored `single`, and `make questions-rescore`
narrows it the same way. A kind's entry may fix a band; none does yet except
`compound`, which is banded medium however the slot was first planned. `QUESTIONS_KIND_MIX` (optional,
`kind:weight`) shares the kinds out over the slots that span passages; it
names only kinds that span, and absent it deals `needs_both:5,compound:1`, and `needs_both:1` turns compound off.

An accepted `needs_both` question citing two passages is read once more by the verifier (prompt `verifier: stated`), which lists the parts of the answer and quotes each cited passage that states one; it stays two-passage only when each cited passage holds a part no other cited passage holds. Where every cited passage states every part and the question joins cases with a coordinating conjunction, both citations are kept. A reading that cannot be had keeps the question as cited, with a warning. A padded question that cites a bridge fact keeps both passages, because the bridge itself rests on two.

A `compound` question asks two separate things joined by "and", each answered
by one of two passages that share least. The writer returns the two halves,
each half is recovered from its own passage alone (two verifier reads, and no
round trip on the merged question), and a question claiming a relation between
its halves (a word such as "differ", "both" or "together", by the per-language
`_RELATES` table, read only in the words that join the halves) is refused as
`wrong_type`. The key is held to its answer form one half at a time. The
partner is the passage of the slot's topic and its bridges that shares least
with the head; a slot that is dealt one passage is written as `single`.
Compound is dealt by default, in about one of every six spanning slots
(`QUESTIONS_KIND_MIX=needs_both:5,compound:1`); `QUESTIONS_KIND_MIX=needs_both:1`
turns it off. It was calibrated on pairs built by its calibration script, not
through the deal, so the real path is not yet calibrated and the quality bars
were not met (see the bugs page); a corpus rebuild measures it.

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
| Supported | Every figure and date it asserts is in the cited passages |
| Not a copy | Fewer than 90% of its content lemmas are already in the target |

Only the units that carry a digit are read. A spelled-out numeral is not a
claim, so `48` is checkable and `two` is how a sentence is built. A name the
explanation uses to describe the answer is not one either: the key's own
checks hold its names, and a figure is what can be wrong.

The column is NULL on questions written before it and is not backfilled, and
NULL on every unanswerable question by CHECK. An answerable question written
without one is refused `explanation_unusable`; a stored row read without one is
not.

### What a question asks of a reader

`difficulty` says how far an answer is spread — how hard it is to **find**.
`cognitive_level` is the other axis, derived from the type the question is
stored as, so a count whose key names no figure, stored as a `factoid`, is
`recall`:

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
conclusion follows from the premises. A total no figures come to is refused
unasked; one some do come to is still asked of the model, since up to four
of the figures cited sum to most small totals whatever each counts. Where the passages hold fewer than two
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

All four are stored, and read again by `make questions-reverify`, which
rejects a question whose passage or document scope no longer matches its
citations. `make questions-rescore` rewrites the four from what each
question cites now, with no model call; run it before re-verify after `make
extract-dedup` only, which takes out citations a duplicate refusal had folded
into a fact, a move the question did not make. After a re-extraction or a
deletion it would make the scope of a question that lost a fact current, and
re-verify could no longer reject it as `source_changed`. A question citing a
fact that rests only on such a citation, its own being gone, is left as it
is, and re-verify rejects it.

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
| `wrong_type` | is not the kind it was planned as, where a rule can say so. A question whose opening asks for another kind (`Wann`, `What happens if`, by the per-language `_ASKED_FOR` table) is not refused for it: the checker types it by its opening and holds it to that kind's rules. The opening is read where the question begins after a premise, past the last sentence or clause end before its first question word that asks, one inside no relative or adverbial clause (`Ich bin neu bei der Bank. Wann …?`, `As a new customer, why …?`, and `When I travel abroad, why …?`, whose `When` opens the premise), or before its first question word at all where none asks; a question opening on its question word reads at its start. The checker stores a count whose key holds no single number as an enumeration (a list) or a factoid, and a count of the items listed by the cited fact the question asks about (the one sharing most of its content words) as a factoid, since that fact states it. An `enumeration` counts each part of a suspended compound (`Junioren-, Senioren- und Breitenfussball`) as an item, and a coordination with no noun phrase as a set where neither a conjunct nor what it is joined to is a verb and no conjunct is a number (`political, religious and personal`, but not `complete and signed` or `one or two days`). A `comparison` has to state a difference between the two subjects it names: a comparative with one subject before it and the other after, both within its stretch between seams (`;`, `,` or a conjunction, coordinating or subordinating); or, across a seam that divides the subjects, a comparative on each side, one comparative where the seam opens a subordinate clause (`…, while …` or `… while …`), or a word both sides share and the question does not | nothing |
| `restates_question` | is answered with almost no word the question did not already carry, counting nouns, proper nouns, adjectives, verbs, adverbs and interjections. An answer with a number, one saying yes or no where the question did not, one stating a negative the question did not (unless it asks why), an answer to a question asking who, and a `comparison`, are not read | nothing |
| `explanation_unusable` | is answerable and carries no long answer, or carries one that is the wrong length, asserts a figure the passages do not, or only restates the key | nothing |
| `asks_nothing_new` | is a follow-up citing nothing its root did not, unless every fact it cites is a summary or an outline and at least a quarter of its key's content words are new to the thread | nothing |
| `off_thread` | is a follow-up resting on no passage an earlier turn of its thread used | nothing |
| `duplicate` | is a near twin of one already accepted in its own language and of its own answerability. How near depends on what the two cite: a shared fact, a shared passage, or nothing in common, each a higher bar, and a different question word lifts any pair to the highest | one index probe among the accepted questions of its language and answerability; two for an unanswerable question, one per kind that can refuse it |
| `answerable_after_all` | was written to have no answer and turns out to have one: an accepted answerable question resting on the same fact sits near it, or its own passages settle it | the probe among answerable questions, the second of the two, or one `settles` call |
| `leaks_source` | names the material its answer is in | nothing, or one question-only call |
| `unanchored` | nobody could have asked without the passage in front of them | nothing, or up to two question-only calls |
| `not_recoverable` | cites evidence its own answer is not in, or asks why where the verifier, reading the passages for the reason, finds only the question's own rule or says they give no reason beyond it, or is a search query bounded to a few words that a passage it does not cite answers differently | the round trip; for such a query, a passage probe and one more read |
| `answer_incomplete` | has a `list` key naming far less than the verifier found, whether recall found the key or the entailment pass rescued it | the same round trip |
| `answerable_elsewhere` | was written to have no answer and a passage it does not cite settles it | a passage probe and a second `settles` call |
| `source_changed` | rests on a fact that no longer passes its own checks or that a person rejected, or whose citations no longer match its stored passage or document scope | nothing |

A `not_recoverable` row refused because a why has no reason beyond its rule, or
because an uncited passage answers a short search query differently, is told
from a plain miss only by the reason the checker logs.

A question written as a search query, dealt a category of form `query`, is
not `malformed` for ending without a question mark, when it is written or
when it is re-checked: a re-check reads the form off the categories the row
stores, so a row stored without one is held to the question mark as it was
when it was written. Every other rule above holds for it.

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
auxiliary with the label an embedded clause carries. A German `wo(r)` and a
preposition (`Worauf`, `Woran`) is a question word however the tagger tags
it, by the per-language `_ASKING_ADVERBS` table. It replaced a
model-judged `wrong_type` that never fired.

There is **no gate for "the question is its own fact rearranged"**. One was
written in two formulations and both refused questions that are as good as a
benchmark question gets: for a single atomic fact, a good question *is* the
fact minus its answer.

### The round trip

`not_recoverable` is the one no similarity measure makes. A second model is
shown **only the cited passages** and asked to answer, and to answer only
where they answer the question as it is asked rather than a narrower one, so
a reworded question that drifted from its passage comes back not in the
passages. The same read says whether a why has a reason beyond its own rule,
which `not_recoverable` refuses when it has none. The question survives
if what comes back carries every number, name and date the target asserts,
and enough of what it is about. A `value` is compared whole, on its verbs as
well as its nouns and adjectives, so `a report` is what a passage saying
`must be reported` says; a `list` or an `explanation` by overlap —
`QUESTIONS_ANSWER_OVERLAP` — over what it adds to the question, so a key
that restates the question before it answers is not held to the restatement.
Numbers are always exact, so `4 hours` never
passes for `48 hours`, and a count written out is its figure: `two
conditions` is `2 conditions` and `zehn Sekunden` is `10 Sekunden`, for the
languages whose number words the gates hold. A figure the passages or the
verifier's reply state is read by its language's decimal mark, `DECIMAL_MARK`
in [`nlp/analysis.py`](../nlp/analysis.py): a German `1,234 %` is a rate and
`1.234` a count, English the reverse, and `0,125 %` is never `125 %` in
either. A figure the key or the explanation writes with one mark before three
digits is read both ways, because a model writes either convention whatever
the language: a German key `1,000 EUR` is the `1.000 EUR` its passage states.
A range written with a dash (`68–70 cm`) asserts both ends, so a recovery giving each end (`between 68 cm and 70 cm`) holds it.

What the reader is given is not asked back. A name the question carries, or
every heading trail of the cited passages, need not come back, so `What is
a SEPA direct debit?` is answered without `SEPA`; never a figure, because a
`30-Day Return Policy` heading or a clause numbered 7 supplies exactly the
number a wrong key copies, and not where the recovery names a name the key
lacks, so `Mastercard charges 2 %` never stands for `Visa charges 2 %`. A
lemma only the heading trails carry, every one of them, is not looked for,
because the verifier is shown the passages without their headings. Every
trail, because passages under `Konten > Premiumkonto` and `Konten >
Basiskonto` are about two products and a key may pin one's figure on the
other. A heading excuses nothing where the recovery holds a content word the
key and the question lack: `a debit card and a Mastercard` under `Tariffs >
Premium > Visa` is not `a Visa card and a Mastercard`. A key's `one` is
never met by an indefinite article: `a debit card for each account holder`
is not `one debit card`, and `a few weeks` is not `one week`. And a lemma
comes back under an adjective or an adverb as well as its own part of
speech, never under a verb and never where the parse puts a negation on it
or on the word it hangs off: `kostenlose Überweisungen` is `Überweisungen
sind kostenlos` and not `Überweisungen sind nicht kostenlos`, and `das
Verpacken` is not `verpackt`.

The `recall` reading stored beside the verdict is the share the verdict
read, held to the bar the form was: all of it for a `value`, which records a reading only where it fell
short, and `QUESTIONS_ANSWER_OVERLAP` otherwise. So a `value` whose recovery
fell short and which the entailment pass then rescued carries a confidence of
0, and a `list` or `explanation` whose recovery holds no content word reads 0
rather than abstaining.

The entailment pass rescues only a recovery that fell short. A question
whose answer the verifier found not in the passages at all is refused: that
reading saw the question, and the pass scores the bare key against each
passage, which a fragment the passages happen to contain passes.

The form is the one the answer fits among those its type takes, and only a
`list` is then checked for completeness. Three items punctuated apart make a
list; two carrying no verb do where the type asks for a list first, so a
`condition` answered with two of the passage's conditions is held to
`answer_incomplete` rather than compared as a value. Two clauses carrying
verbs are an explanation where the type takes one, and a list where it does
not. A comma between two digits separates no items, so `49,90 €` is one
amount.

An `explanation` key of a `condition`, `procedure`, `enumeration`,
`consequence` or `definition` question is read for completeness in
**shadow**: the share of the recovery's content words the key carries is
stored in `gate_scores` as `coverage`, marked `shadow`, with
`QUESTIONS_ANSWER_COVERAGE` beside it, no margin and no part in the
confidence, and nothing is refused on it. It is stored on every such key
the verifier recovered, whichever way the round trip goes, and is 1 where
the recovery says no more than the key. It is there to set a bar on real
keys before it gates any.

Three things about it are load-bearing. The verifier is meant to be a
**different** model, because a model marking its own work recovers what it
just wrote; the stage warns when it is the writer's. The escape hatch is
explicit — the verifier answers whether the passage states it at all. And it
sees only the cited passages, never the corpus: what is being measured is
the dataset, not a retriever. One kind of question is read once more against
the rest of it: a search query bounded to a few words, as
short-search-query is, whose keywords drop the qualifier that tells two cases
apart. The passages the unanswerable probe would show it
(`QUESTIONS_ELSEWHERE_PASSAGES`) are read with it, and an answer they give
that does not agree with the key refuses it as `not_recoverable`. A long
query is not read so: its keys passed in calibration without it.

`unanchored` and `leaks_source` are asked of `QUESTIONS_PHRASING_MODEL`, one
judgement per call. Each is a judgement rather than a measurement — an
**opinion**, as the verifier's `settles` verdicts behind
`answerable_after_all` and `answerable_elsewhere` are too — and these two are
the phrasing model's, so the factory turns them off when the phrasing model is
the writer's own, and then they are not asked for at all: a verdict that may
not reject is a call per question buying a log line. The rule half of
`leaks_source` still fires, because a pattern is a measurement. Recoverability
stays on regardless.

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

`cites_source` matches what a pattern can settle — a numbered division of
the layout (`Abschnitt 2.2`, `section 4`), a bracketed reference (`[R22]`), an
author with a year (`Beck 2003`) — and returns **None** where nothing does,
because the absence of a pattern is not evidence. It returns False only
where the one numbered unit a question names is a unit of what the document
lays down — `Article 5`, `clause 12`, `Klausel 12` — which is what the
question is about rather than where its answer is, so no judge is asked.

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
planned `easy` and from one passage, written only as a kind that asks for one
detail - `factoid`, `entity` and `reason`, those the mix weights above 0, in
mix order: a set, a condition or a definition is what a closed list or a rule
in the material settles - and dealt an **atomic** fact first: a
summary perturbed moves a whole passage's claims at once, and the move lands
on one of them.

The writer is shown the passage its fact rests on as what the chatbot will
read, and the passages two ordinals either side of it in the same document —
the ones the probe reads too — under the same rule: no sentence of any of
them may answer the question, contradict its premise or cover its case.

The writer is told what "answered" means, because "not stated" is not the
same thing. The material answers a question when it states the answer, and
also when it **contradicts its premise**, names a **closed list or rule** its
case falls outside (`only`, `every`, `no other`, in any language), or states
a **general rule** that covers its case. Swapping the party or the period is
the move that most often lands on one of those, so neither the prompt nor the
retry note after `answerable_after_all` prescribes it.

**Kinds.** UAEval4RAG (Peng et al., [*Unanswerability Evaluation
for Retrieval Augmented Generation*](https://aclanthology.org/2025.acl-long.415/),
ACL 2025) writes unanswerable requests in kinds. Four of its six can be
dealt as one categorization, `UNANSWERABLE_CATEGORIZATION` in
[`config.py`](config.py), whose JSON [the configuration
guide](../../docs/configuration.md#a-json-value) quotes. The default deals
`out-of-corpus` alone, the one kind that passed calibration
([measurements](../../docs/measurements.md#unanswerable-kinds-v050)); the
other three are opt-in, in place of the default's own `Unanswerable` entry.
Each category
carries `settles`, the verdict the passages it cites must give, and
`behaviour`, what a good reply does:

| Category | Paper | `settles` | What it must do |
|---|---|---|---|
| `out-of-corpus` | Out-of-Database | `silent` | move one detail of the fact just out of reach, never to the absurd |
| `false-presupposition` | False-presupposition | `refutes` | take for granted something a sentence of the passage says is not so |
| `underspecified` | Underspecified | `answers` | leave out the detail the passage needs to choose between its cases, so each case has its own answer |
| `nonsensical` | Nonsensical, illogical content only | `silent` | join things the passage names in a way that makes no sense |

After link U the three opt-in kinds got writer-prompt fixes that were not
re-calibrated, so the measured figures describe the prompts before them and
the kinds stay opt-in. Nonsensical is told to ask of a thing what cannot be
so of it, checks that first, and its retry note keeps the senseless shape.
False presupposition also checks that no passage grants what its question
takes for granted in a case it names. Underspecified asks for the value that
varies by case and may decline a passage with none, which skips the slot
instead of swapping its kind. Out-of-corpus is unchanged.

Every slot is dealt it, and only an unanswerable slot is told its category:
the description in a `WHAT MAKES IT A TEST` block under the passages, and the
action, the step, the examples and the rule its `settles` verdict names in
the system prompt; nonsensical is also told its own action, check, fact line
and worked examples, since it shares out-of-corpus's verdict, and a kind of another name
is written as the shipped kind of its verdict. The block wins where a rule under FORMAT conflicts with
it, so a nonsensical question is not held to being plausible, except for two
rules that still hold: never name a source, and never ask about an unrelated
subject. Plausibility is in the other three kinds' descriptions instead.
Told none, the prompt is the one above, its single change moved just out of
reach and its action asking for a plausible question. The passages beside it
are told the same rule as the cited one, or, under a kind that must be
refuted or answered by case, that none of them may answer it as asked. A
refused draft is written again with its kind's note where it has one, never
with the out-of-corpus move: a false presupposition the passages answer is
told to take for granted something a sentence of the passage says is not so,
one they are silent about to take for granted something a sentence rules
out; an underspecified one the passages settle one way, or say nothing
about, to ask about a value the passage gives differently for cases the
question leaves open; a nonsensical one the material answers to join things
the passage names in a way that makes no sense; and each, off topic, to stay
on the subject of the fact with its own move. Out-of-corpus gets the notes
every unanswerable draft gets. The type gate's `wrong_type`, a question word
asking for another type, is not a kind's to answer and gets no retry, as
before. The check is `settle` with the kind's verdict: kept where the cited
passages give it with words of theirs behind it, a verdict without them
reading as `silent`; beside the probe, which looks for an answer elsewhere,
the kind's verdict and `silent` both keep it. Any other verdict that answers
it refuses it as before, and `silent` where the kind wants another is
`wrong_type`. The row's `settles` and `settles_elsewhere` readings are 1
where the reading kept it, so a kept refutation reads 1 as a kept silence
does. A categorization carrying `settles` must have the role `question` and
every category the form `question`: a kind is told in a block of its own,
which the asker's block or a search query's exemptions would undo. `make questions-rejudge` reads the verdict off the row's
stored category, `silent` where none is stored. Modality-limited and
safety-concerned are left out: they test a chatbot's abilities and policy,
not the documents. Typos and language barriers, inside the paper's
nonsensical, still have answers. `underspecified` has no check of its own:
under one reading its passage answers it, so only labels tell it from an
answerable question. Out-of-corpus alone is the default, as the one kind that
passed a calibration; the other three stay out until one admits them.

Attempted, not held: they face three gates of their own, and the two that are
on bite, which is why the default sits above the share a release should hold.
Over-setting is safe for the release, since `QUESTIONS_RELEASE_UNANSWERABLE`
is a ceiling, but not for the spend: every attempt
`QUESTIONS_UNANSWERABLE_SHARE` plans is written and checked, its `settles`
calls included, whatever the ceiling, so at a ceiling of 0 those calls buy
nothing the release can take; lower the share to save them. The ceiling is
0.10 as shipped, and the `settles` reading still keeps about a third of kept
rows that the material answers (docs/measurements.md, "Unanswerable kinds
(v0.5.0)"), so up to about a third of the unanswerable questions a release
holds are a known defect.

| | |
|---|---|
| `answerable_after_all` | the passages it cites settle it after all |
| `answerable_elsewhere` | a passage it does **not** cite settles it |
| `off_topic` | it is about nothing the material mentions at all |

**Settled, not stated.** Both are asked of `Verifier.settles`, not of the
round trip's `read`: whether the passages state the answer, **refute its
premise** (a closed list or an exception included), or cover its case with a
**general rule** — `answers`, `refutes`, `rule` — or settle nothing,
`silent`, which is the only verdict that keeps the question. The prompt's
role no longer says the question was written to have no answer, and the
verifier writes the reply a careful chatbot would give before its verdict,
because a model asked only to classify, and told which label to expect,
leans to `silent`. An answer
given in another form than asked (an event for a period, *any* party for one)
and a rule with *must*, *never* or *only* ruling out what the question assumes
both settle it. Its quote has to be
words the passages it was shown carry: one from memory reads as `silent`.
A quote stitched from two items of a list, two cells of a row or two
passages is looked for piece by piece, split at line breaks, ellipses, cell
bars, list markers and sentence ends. Each piece has to be whole words of
one passage, list markers and cell bars aside, and a piece shorter than
three words counts only in a passage the longest piece is in: `Refunds:`
heading one passage beside `within 14 days` in another settles nothing.
First over the passages it cites, then over them and the probe together, so
a case the cited passage sets up and a rule elsewhere decides are read in one
call; a quote the cited passages hold, found on this second reading, refuses
the question as `answerable_after_all`. The probe is the
`QUESTIONS_ELSEWHERE_PASSAGES` passages nearest by vector fused, by
reciprocal rank, with those sharing most of its content lemmas, and on top
of them the passages two ordinals either side of each cited one. A corpus
with no vectors is probed by shared lemmas, with no neighbours. Each verdict
is stored in `gate_scores`, `settles` and `settles_elsewhere`, 1 for silent
and 0 for settled, with the verifier's prompt version, so a row says what
the verifier made of it and under which prompt. It is an **opinion**: kept
with no margin, it moves no confidence.

**A settled question is recycled.** One refused because a passage of its own
topic `answers` it or covers it by a `rule` points at material holding an
answer, so the topic writes an answerable question in the same kind and
band at once, from its facts on the passage the quote is in — those whose
evidence carries the quote first. A refuted premise asks nothing that
passage answers, and a passage outside the topic is its own topic's to ask
about, so neither is recycled.

`make questions-rejudge` asks the same of the questions already accepted,
writes its verdicts on each row the same way, and does not ask again about
a row that already carries one given under the current prompt. The prompt is
the verifier's `PROMPT_VERSION`, which every verifier prompt shares: v0.4.3
moved it from 6 to 12 for the round trip's read alone, so on a database
upgraded to it the first rejudge asks again about every stored accepted
unanswerable question, one `settles` reading each and a second where the
cited passages are silent and the passage probe is on. A question the model will not answer about
is logged, counted in the last line, and written nothing, so the run goes on
and the next one asks it again. Five in a row stop the run with the last
error: the client raises the same for a refused key or an unknown model as
for a content filter, and a model that answers nothing would otherwise walk
every question and exit 0.

A recovery or quote that only says the question back is not an answer: a
`why` the passage gives no reason for comes back as the rule itself. So an
`answers` whose quote `restates` a question asked with a question word reads
as `silent`, here and in `make questions-rejudge`. A yes-or-no question is not
read so: `Ist das Gerät wasserdicht?` said back as `Das Gerät ist
wasserdicht.` is answered yes. Nor is a `refutes` or a `rule`, because its
quote is the rule.

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

A follow-up is stored `needs_both` only where its root was dealt `needs_both`; one on
a compound pair is stored `single`, as one on a one-passage root is.

`Deal.widen` adds unspent facts **of the same passages** once, before the
thread's first turn is written, and two gates hold the thread together:
`asks_nothing_new` refuses one citing nothing outside its root, and
`off_thread` refuses one resting on no passage an earlier turn of its thread used.
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

A sample **burns** every fact it offers, `QUESTIONS_FACT_SAMPLE` of them or,
for a reading type that took a list whole, up to 8, whether or not the
question cites them, and no fact is offered twice within one topic, so past a
point `QUESTIONS_PER_TOPIC` is inert. What raises coverage instead is running
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
| `QUESTIONS_RELEASE_UNANSWERABLE` | The most of the release that may have no answer. A ceiling, 0.10 as shipped; 0 releases none |
| `QUESTIONS_RELEASE_DIFFICULTY` | How it spreads over the bands. Unset follows the answerable pool's own band split |
| `QUESTIONS_RELEASE_TYPES` | How it spreads over the kinds. Unset reuses `QUESTIONS_TYPE_MIX` |
| `QUESTIONS_RELEASE_LANGUAGES` | How it spreads over the languages. Unset follows the pool's own language split |

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
its language and answerability rather than over the single nearest of each
kind that re-verify probes, so a twin the gate let past behind a closer
question is caught here.
A root whose twin is already in is skipped, a thread ends at a turn that
twins what is already in or whose band, kind or language has no place left
(the test a root passes), and of a group the question the draw's hash ranks
first is the one kept where it fits, so creation order does not decide which
twin stays.

The rule misses twins that restate one rule as two documents state it: they
share no citation and sit no closer than a pair asking two things. So the
draw is then put to the verifier, `Verifier.same_answer`: each released
question with its nearest released neighbour of its language and
answerability — rank, not a bar — asking whether one correct reply serves
both. A pair it reads as one answer joins the twin groups, and the release
is drawn again, up to three times, each pair asked once. The last draw is
asked about too, in a fourth round that does not draw: of each pair it reads
as one answer, the question the draw's hash ranks later is dropped with the
turns that follow it, so the release handed back holds no pair the verifier
read as one and is a little smaller than the draw. That is about one call per
released question. How it scored against the reviewers' twin
pairs is in [docs/bugs.md](../../docs/bugs.md#found-on-the-v022-rebuild-of-2026-10-14).

`QUESTIONS_RELEASE_SIZE=0` draws the largest release the pool can fill to
within `TOLERANCE` of every quota: the draw scans sizes down from the largest
the pool can place and keeps the first that fills, since a size can fill where
a larger one does not. The pool can place a size where the kinds, each capped
at what the pool holds of it, leave no more places unplaced than the
unanswerable ceiling takes: above that, answerable places have no kind to
spend them on. That is so where the ceiling is at least the tolerance, as the
shipped 0.10 is (the same release as the scan from the looser bound found, on
500 random pools of every shape); under it, `QUESTIONS_RELEASE_UNANSWERABLE`
of 0.05 or none, a size above the bound can still fill within the tolerance,
and the scan starts from the looser bound of every quota held for rows enough,
as it always did. The pool is
ranked, grouped and threaded once, and a draw takes a question out of its cell
by moving past it, so a draw is linear in the pool: at ten times the reviewed
build's, 21,750 questions, the scan is minutes where it was 39 a draw. A kind the
pool holds too few of to fill its share within `TOLERANCE` is asked for what
the pool can release of it (not the spare members of twin groups, not rows in a
language the release gives no weight), and the places it cannot take go to the
other kinds by largest remainder, but no kind is asked for more than its share
of the size plus `TOLERANCE`. So one scarce kind does not cap the whole release,
and the release grows only as far as that balance allows: where the others
cannot take the freed places the size is too big and the scan goes below it.
The command reports what it drew, the yield,
its spread over every share, the languages included, and any quota the pool
came up short on. It names a bucket only where the pool holds too few of it
for what its share asks (`reason (60 of the 90 asked)`): a kind capped at its
supply is released whole and short of nothing, and the places it cannot take
leave every band, language and answerability short as well, within the
tolerance and for no want of those, so a pool short of scarce kinds is told to
generate more of those and not of the rest. Where nothing is scarce the
shortfalls are logged without the advice.

It also reports the categories the released questions' writers were told, as
`categorization=category` on an axis of its own, so a category named like a
kind is never counted as one, and on the line after it the pool's counts for
the same labels:

```text
  category    Phrasing=concise-and-natural 30 (25%), Phrasing=verbose-and-natural 28 (23%), ...
  in the pool Phrasing=concise-and-natural 120 (24%), Phrasing=verbose-and-natural 131 (26%), ...
```

No quota holds a category. The shares the release is held to are kinds,
bands, languages and answerability, and those correlate with categories: a
search query, where a configured categorization deals one, tends to be a
factoid, and a thread brings the uncategorised follow-ups its quotas have room for,
ending at the first turn with no place left. So a
release can drift from the mix its questions were written in, and the two
lines are where that shows. A share is of every question in the release or
the pool, the unanswerable, compound and follow-up questions included, which
are told no category.

Nothing is deleted. The draw re-checks first, as `questions-reverify` does. A
question is rejected before it can be drawn when a fact it cites no longer
holds or its passage or document scope moved (`source_changed`), when it fails
the structural gates other than the document-title check, when it fails its
type's rules, or when the duplicate probe finds an earlier twin. A search
query is held to the structural gates as it was written, without the
question mark, by the form its row stores. A question a
person accepted is checked on its facts alone. The topic, explanation,
source-naming pattern and thread gates (`off_topic`, `explanation_unusable`,
the pattern half of `leaks_source`, `asks_nothing_new`, `off_thread`) are not
run again: they judge a question only when it is written. Beyond that, a
release is a column on rows already there, so questions left out stay
queryable, and running it again with different shares replaces the first. It
always draws over every accepted question: `--only` is refused, and `make
questions-balance` takes no `TOPIC=`.

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
| Questions | Question, with what it rests on folded in; a Kind column (single, needs_both, compound) follows Type |
| Citations | Question × fact × passage, so a bridge takes two |
| Assessment | Judgement of a question. Empty unless the evaluation phase has run |
| Summary | The counts, off the same quality report the page shows: types, bands, levels, rejections, and the kind and each `categorization=category` a question was written as, and the models that wrote, verified and phrase-judged the questions |

The Questions sheet's **Categories** column, after Language, names the
categories each question's writer was told, as `categorization=category`
(`Phrasing=concise-and-natural`), comma-joined; an unanswerable question
names only its kind (`Unanswerable=false-presupposition`). It is blank for a
question told none: an unanswerable one where no kind is configured, a
compound one, a follow-up, and every question written before prompt version
17.

An unanswerable question has no key, so its **Answer** cell gives what a good
reply does for its kind, as UAEval4RAG (Peng et al., [*Unanswerability
Evaluation for Retrieval Augmented Generation*](https://aclanthology.org/2025.acl-long.415/),
ACL 2025) accepts one in its Table 11: `Expected behaviour: asks which case
is meant, or gives the answer for each case the material distinguishes`. It
is the `behaviour` its stored kind carries, and blank on one stored with no
kind. It is a criterion for a judge or a person to score a reply against,
not a reference answer to match as a string.

The same on `GET /questions/export` and behind **Build a workbook** on the
Questions page, built when asked for rather than on every render.

A control character in any text is dropped from its cell, which Excel would otherwise refuse.
A document with no title is named by the first 12 characters of its digest on every sheet and in the listing.
`--question-type` and `--answer-form` on the command line take only the values the column holds, as the route does.
The Questions, Citations and Summary sheets are read in one database snapshot, so a question the worker writes meanwhile is on all of them or none.

**The filter is the caller's and there is no default scope.** Ask for nothing
and you get everything, rejected rows included, because that is what the same
request to `/questions` returns.

Argilla is not this: it holds a disposable copy of a stratified *sample*
pushed for review. The database is what has the set.

The Citations sheet is the expensive half; `--no-citations` leaves it empty.

### Reading the benchmark

Two studies of generated benchmarks set the limits within which a set from
this project should be read: van Elburg, van der Putten and Marx, [*Can We
Evaluate RAGs with Synthetic Data?*](https://arxiv.org/abs/2508.11758) (ECML
PKDD 2025 workshops), and Rahmani et al., [*Synthetic Test Collections for
Retrieval Evaluation*](https://arxiv.org/abs/2405.07767) (SIGIR 2024). Their
figures are on [the measurements page](../../docs/measurements.md#what-a-generated-benchmark-can-rank).
In short:

- It ranks retrieval set-ups (retriever, chunking, top-k) more reliably than
  it ranks the models that write the answers.
- Its questions run easier than real users' questions, so absolute scores
  are optimistic. Differences between two set-ups are what it measures
  best.
- A question's cited passages are one passage that answers it, not every
  passage that does. Score a retriever by whether the answer can be got
  from what it returned.
- Agreement with real questions was best where the generated questions
  matched their form, which is what the categories vary.
- As a precaution, judge the chatbot with another model family than the
  one that wrote the set. The Summary sheet names those models.

## Reading back the prompt that wrote a question

Every question carries `prompt_version`, and three modules declare one:
`types.PROMPT_VERSION` for the thirteen writers, `phrasing.PROMPT_VERSION`
for the three wording judgements and `verifier.PROMPT_VERSION` for the round
trip's four, `settles` and `same_answer`, the twin judgement
`questions-balance` asks for. They are bumped separately.

The stage records what it sends at start-up — [`prompts.py`](prompts.py)
declares it and `stages.prompts` writes it to the `prompts` table. Three ways
to read one back:

| Where | Shows |
|---|---|
| The Questions page | "The prompt that wrote this", under a selected question |
| `GET /prompts?service=questions&version=15&name=factoid` | The same, as JSON |
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
| `questions` | the question, its two answers, its type, form and cognitive level, the three scopes and the band derived from them, the planned band, the categories its writer was told, the thread columns, the embedding, the release id, the gate that stopped it, the models that wrote it, verified it and judged its phrasing, and the verdict a person reached |
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
make questions-rejudge          # ask whether the passages settle each accepted unanswerable; calls the verifier
make questions-rescore          # rewrite stored scopes and bands; no model call
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
| `QUESTIONS_FACT_SAMPLE` | How many facts are offered per call, divided between the passages, at least one from each. A reading type also takes the rest of a chosen fact's list, up to 8 |
| `QUESTIONS_SAMPLES_PER_PASSAGE` | How many times one passage is dealt before the stride moves on |
| `QUESTIONS_TYPE_MIX` | Which kinds are written and in what proportion |
| `QUESTIONS_DIFFICULTY_MIX` | Which bands the plan aims for |
| `QUESTIONS_CATEGORIZATIONS` | The paper's categorizations as JSON: one Figure 2 object or a list of them, the `{"categorization": ...}` wrapper read too. Each answerable root question is written as one category of each, bar a compound one, which is told none, as a follow-up is; an unanswerable question is told only its kind, where a categorization carrying `settles` is set, and none otherwise. A categorization's `role` is `question`, the default, or `user` for one describing the person asking; any other role is refused. A category's `form` is `question`, the default, `query` for a search query, which no gate holds to a question mark, or `premise` for a question opening on the asker's own situation; any other form is refused. A category may carry `"words": {"min": N, "max": N}`, either or both, whole numbers of at least 1: the writer is never sent them, no question is refused for missing them, and `make diversity BY=category` reports how many of the category's questions keep to them. A `max`, whatever the `min`, also keeps a premise from being told beside the category, and has a search query read once more against the passages it does not cite, which refuses it as not recoverable where one answers it differently. Probabilities are given for every category of a categorization or for none, which is uniform, and must sum to 1 within 0.01. A misspelt key, a duplicate name, an `=`, a comma or a line break in a name, or a blank description is refused by name. Unset reads the paper's two natural phrasings, its two premises and its two linguistic variations from code, and for an unanswerable question UAEval4RAG's out-of-corpus kind alone, concise bounded to at most 9 words and verbose to at least 10, because `backend.env` cannot hold JSON; set it on the settings page, with `PATCH /settings/questions` or with `python -m settings.run`. `[]` writes none. **Phrasing: concise and verbose; Premise: direct and with-premise; Linguistic variation: similar-to-document and distant-from-document; 0.5 each** |
| `QUESTIONS_ANSWER_CHARS` | Shortest and longest target answer per form |
| `QUESTIONS_ANSWER_COVERAGE` | How much of what the verifier found the target must account for. Lists only; `0` turns it off |
| `QUESTIONS_PARTY_DENSITY` | How much of a passage may be people's names before it is read as a credits page. `0` turns it off |
| `QUESTIONS_MEETS_SHARE` | The share of a topic's closest cross-passage fact pairs a second passage must be among before it is offered; while this or `QUESTIONS_MEETS_FLOOR` is above 0, a passage holding nothing but copies of the head's first fact is not offered. `0` sets no relative floor. **0.02** |
| `QUESTIONS_MEETS_FLOOR` | How much a candidate fact must share with the fact the head of its sample offers first before a second passage is offered. **Off** |
| `QUESTIONS_EXPLANATION_CHARS` | Shortest and longest `answer_explanation` |
| `QUESTIONS_BOILERPLATE_COSINE` | How alike a passage must be to one in another document of its own language before it is read as furniture. `0` turns it off |
| `QUESTIONS_ANSWER_OVERLAP` | How much of a list or explanation has to come back. Numbers are always exact |
| `QUESTIONS_UNANSWERABLE_SHARE` | What share are attempted with no answer in the corpus |
| `QUESTIONS_OFF_TOPIC_OVERLAP` | Below this share of shared lemmas, an unanswerable question is off-topic. **Off** |
| `QUESTIONS_ELSEWHERE_PASSAGES` | How many uncited passages, nearest by vector fused with those sharing most words, the `answerable_elsewhere` probe reads. On the vector path only, the passages two ordinals either side of each cited one are read on top |
| `QUESTIONS_ENTAILMENT_OVERLAP` | How much of what a question asks about must occur in its passages before the entailment pass may rescue it. `0` turns the guard off |
| `QUESTIONS_FOLLOWUP_SHARE` | What share of accepted answerable roots get a thread |
| `QUESTIONS_MAX_FOLLOWUPS` | How far a thread may run past its root |
| `QUESTIONS_FOLLOWUP_TYPES` | The kinds the turns of a thread take, cycled |
| `QUESTIONS_RETRIES` | How many further attempts a root question gets when a gate a rewrite can answer refuses it. An accepted draft is never asked again. Every attempt is stored |
| `QUESTIONS_LONG_ANSWER_CHARS` | Where an answer starts counting towards the band. Not a gate |
| `QUESTIONS_DUPLICATE_COSINE` | How alike two questions sharing a cited passage but no fact must be before the later one is dropped. Halfway from it to identical is the bar for two citing nothing in common, or asking with different question words |
| `QUESTIONS_DUPLICATE_SHARED_COSINE` | How alike two questions resting on the same fact must be before the later one is dropped. Unset holds them to `QUESTIONS_DUPLICATE_COSINE` |
| `QUESTIONS_DUPLICATE_FLOOR` | The cosine two unrelated questions score, which a question's stored confidence is measured from. Moves no verdict |
| `QUESTIONS_RELEASE_SIZE` | How many to draw. `0` is the largest the pool can fill |
| `QUESTIONS_RELEASE_UNANSWERABLE` | The most of a release that may have no answer. A ceiling, 0.10 as shipped; 0 releases none |
| `QUESTIONS_RELEASE_DIFFICULTY` | How a release spreads over the bands. Unset follows the bands the answerable pool holds, so the draw no longer takes nearly every multi-passage question to fill equal thirds; set it for any other split, equal thirds included |
| `QUESTIONS_RELEASE_TYPES` | How a release spreads over the kinds. Unset reuses `QUESTIONS_TYPE_MIX` |
| `QUESTIONS_RELEASE_LANGUAGES` | How a release spreads over the languages, by ISO 639-1 code. Unset follows the pool's own language split, so a corpus mostly in one language releases in proportion; set it for any other split, an equal one included |
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
| [`test_planning.py`](../../tests/unit/questions/test_planning.py) | What a topic is planned to be asked, and the categories each slot is dealt |
| [`test_categorizations.py`](../../tests/unit/questions/test_categorizations.py) | What `QUESTIONS_CATEGORIZATIONS` reads, and every value it refuses |
| [`test_selection.py`](../../tests/unit/questions/test_selection.py) | What the deal offers the writer, and how wide it is |
| [`test_generation.py`](../../tests/unit/questions/test_generation.py) | What the writer asks the model, and what it makes of the answer |
| [`test_verification.py`](../../tests/unit/questions/test_verification.py) | Every gate, and the order they are applied in |
| [`test_typing.py`](../../tests/unit/questions/test_typing.py) | What a question is typed as, read off how it opens, and how a count whose answer is no figure is labelled |
| [`test_competence.py`](../../tests/unit/questions/test_competence.py) | The types whose answers are reasoned to rather than found |
| [`test_balance.py`](../../tests/unit/questions/test_balance.py) | Choosing a balanced release |
| [`test_models.py`](../../tests/unit/questions/test_models.py) | Which model writes a question, and which one checks it; what a question's citations make its scopes |
| [`test_question_service.py`](../../tests/unit/questions/test_question_service.py) | What the service does with a topic |
| [`test_reverify.py`](../../tests/unit/questions/test_reverify.py) | What a re-check does with a question a person accepted |
| [`test_rejudge.py`](../../tests/unit/questions/test_rejudge.py) | What `questions-rejudge` does with the accepted unanswerable questions |
| [`test_settles.py`](../../tests/unit/questions/test_settles.py) | What the verifier is asked of a question written to have no answer |
| [`test_reasons.py`](../../tests/unit/questions/test_reasons.py) | Whether the material states why, which is what a `reason` slot is dealt |
| [`test_rescore.py`](../../tests/unit/questions/test_rescore.py) | Rewriting a stored question's scopes from its citations, and the re-verify after it |
| [`test_phrasing.py`](../../tests/unit/questions/test_phrasing.py) | What a question's own wording says, read without a model |
| [`test_abstention.py`](../../tests/unit/questions/test_abstention.py) | A judgement that could not be had is recorded, not read as a pass |
| [`test_context.py`](../../tests/unit/questions/test_context.py) | What the writer is told about where each fact came from |
| [`test_thread_cycle.py`](../../tests/unit/questions/test_thread_cycle.py) | A thread that closes into a loop is read once |
| [`test_export.py`](../../tests/unit/questions/test_export.py) | The workbook |
| [`test_prompt_catalogue.py`](../../tests/unit/questions/test_prompt_catalogue.py) | That every prompt the stage sends is in the catalogue a version resolves against |
| [`test_questions_cli.py`](../../tests/unit/questions/test_questions_cli.py) | The re-check, the rescore and the release draw on the command line |
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
  decision. So does `questions-rejudge`, released questions included, and
  it leaves a question a person accepted alone.
- **No rule gate overrules a person.** `questions-reverify` rejects a
  question a person accepted only when a fact it rests on no longer holds,
  which includes a fact a person rejected.
- **A language held by one document gets no boilerplate filtering.** Only
  another document of the same language counts as a twin, so a corpus
  holding one document per language, such as one document and its
  translation, offers its copyright pages and contents tables to the writer.
- **`planned_difficulty` disagreeing with `difficulty` is not a fault.** The
  writer cited fewer facts than it was offered.
- **`QUESTIONS_PER_TOPIC` is what a run costs, twice over.** Each candidate
  is a writer call and a verifier call, and `QUESTIONS_FOLLOWUP_SHARE` adds a
  pair on top for every thread.
