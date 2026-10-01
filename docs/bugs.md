# Known bugs

Defects in what the pipeline produced, each with the fix that closes it.

Everything counted here was measured against the run
[measurements.md](measurements.md) describes, over all 5,873 written
questions and the 1,341 the balanced release drew. That page holds the run's
figures; this one holds only what is wrong with them.

| | Release rows | Where the fix goes | Fixed |
|---|---|---|---|
| [The weld answers in two fragments](#the-weld-answers-in-two-fragments) | 100 | [`gates.py`](../backend/question_generation/gates.py) | yes |
| [The type disagrees with the interrogative](#the-type-disagrees-with-the-interrogative) | 57 | [`checker.py`](../backend/question_generation/checker.py) | yes |
| [The release breaks threads](#the-release-breaks-threads) | 46 | [`catalog.py`](../backend/question_generation/catalog.py) | yes |
| [Answers that are not answers](#answers-that-are-not-answers) | 52 | [`gates.py`](../backend/question_generation/gates.py) | the 17 |
| [Facts that open on a demonstrative](#facts-that-open-on-a-demonstrative) | 30 | [`analysis.py`](../backend/nlp/analysis.py) | yes |
| [Questions that count their own citations](#questions-that-count-their-own-citations) | 42 | [`gates.py`](../backend/question_generation/gates.py) | 8 of them |
| [Boilerplate cited to the wrong document](#boilerplate-cited-to-the-wrong-document) | 6 | [`extraction`](../backend/extraction/README.md) | yes |
| [The evaluation phase judges the newest rows](#the-evaluation-phase-judges-the-newest-rows) | — | [`repository.py`](../backend/assessment/repository.py) | yes |

292 of the 1,341 — **21.8%** — carry at least one of them.

Nothing here touches the structure. Across all 2,416 accepted questions every
citation resolves to a validated fact, every scope label agrees with the
citation graph it describes, no question is in a language its passages are
not, and two normalised question texts repeat. The defects are all in what
the rows say, not in how they are wired.

## The weld answers in two fragments

`compares` asks that a comparison name two things and answer with two sides.
It counts noun phrases on both, and two fragments glued with a comma are two
noun phrases:

> *How does algorithmic bias differ from area under curve (AUC)?*
> — `a type of bias caused by the ML algorithm, a measure of how well a
> classifier can distinguish between two classes`

138 of the 188 accepted `comparison` questions answer this way — 85% of the
English and 59% of the German — and 100 of them are in the release. The
answer names both subjects and states no difference between them, so nothing
a chatbot says can be scored against it.

The pair underneath is the weld `meets_floor` was written for, and that
mechanism is off on purpose: the sweep recorded in
[`config.py`](../backend/question_generation/config.py) found no knee. This
run says why. Cosine between co-cited facts spans **0.730 to 0.950** across
all 1,272 multi-fact accepted questions, and the per-type means sit between
0.847 and 0.876 — welded pairs and sound ones occupy the same tenth of the
scale. The signal is too compressed on this corpus for any threshold to cut,
so raising the floor cannot be the fix.

**Fix.** Gate the answer instead of the pair, where the defect is legible.
`compares` in [`gates.py`](../backend/question_generation/gates.py) needs a
third condition beside its two phrase counts:

```python
def compares(question: str, answer: str, language: str | None) -> bool:
    if len(phrases(question, language)) < 2 or len(phrases(answer, language)) < 2:
        return False
    return _contrasts(question, answer, language)
```

`_contrasts` reads true where the answer carries a comparative, or where its
two sides share a content lemma the question did not supply — the attribute
the two differ in. It already routes to `wrong_type` through
[`checker.py`](../backend/question_generation/checker.py), so no new
rejection code is needed. Sized against this run it removes 155 rows — 6.4%
of the accepted pool, 97 of them in the release — and leaves 33 comparisons.
A release drawn at an even mix of kinds out of 33 holds 395 questions, so
`QUESTIONS_RELEASE_TYPES` gives `comparison` a lower weight in the release
than `QUESTIONS_TYPE_MIX` gives it in the writer's plan. Re-draw the release
after.

## The type disagrees with the interrogative

57 release rows carry a type no reading of their question supports — a *Why*
typed `procedure`, a *How many* typed `definition`, a *What is* typed
`consequence`. Over the whole accepted pool it is 7.6% of the questions whose
form names a type.

| Form | Questions | Outside the family |
|---|---|---|
| Why / Warum | 408 | 3.4% |
| When / Wann | 341 | 9.7% |
| How many / Wie viele | 98 | 11.2% |
| What is / Was ist | 135 | 9.6% |
| How … differ | 106 | 11.3% |

The type is a column the release bands on, so a wrong one silently
mis-composes every quota drawn from it.

**Fix.** `wrong_type` already fires in
[`checker.py`](../backend/question_generation/checker.py) and reads only the
answer. Give it the question too: where the interrogative names a family,
refuse a type outside it. One dict of five forms, `_ASKED_FOR` in
[`gates.py`](../backend/question_generation/gates.py):

| Form | Family |
|---|---|
| Why / Warum | `reason`, `implication`, `consequence` |
| When / Wann | `condition`, `temporal`, `factoid` |
| How many / Wie viele | `factoid`, `aggregation` |
| What is / Was ist | `definition`, `factoid`, `aggregation` |
| How … differ | `comparison` |

Sized against this run it refuses 88 accepted questions, 64 of them in the
release.

## The release breaks threads

`releasable` projects four columns — id, answerable, difficulty and type. It
never reads `follows_id`, so `choose` cannot know a question has a parent and
draws follow-ups away from the threads that explain them. 46 of the 240
follow-ups in the release have a parent outside it. Row 2011 ships as:

> *Why are they shown there?*

**Fix.** Add `follows_id` and `thread_position` to the projection in
[`catalog.py`](../backend/question_generation/catalog.py), then draw whole
threads: a root carries its descendants into the release and counts against
its own quota. The alternative, a pool of roots only, is exact on quota and
drops the 377 accepted follow-ups entirely. Prefer threads-whole — the
follow-ups are the part of the set that tests multi-turn retrieval.

`thread_position` is not needed: `choose` walks `follows_id`. Redrawn over
this run's pool, the release holds 247 follow-ups and none without its
parent.

## Answers that are not answers

Two shapes, 52 release rows between them.

17 restate the question and add nothing:

> *Why can accurate test metrics be hard to determine for exploratory testing
> sessions?* — `accurate test metrics for exploratory testing sessions can be
> challenging to determine`

35 glue three or more clauses into one key with no answer in it:

> *When can a test charter include more than just the planned scope and
> objectives?* — `when it includes organizational details, and entry
> criteria, and product information and limitations, and the test
> environment, and supporting data sources, tools, historical information,
> constraints and risks`

**Fix.** `restates_question` exists and is too loose — it fires on the whole
string where the defect is that the answer's content words are a subset of
the question's. Read it on content lemmas and refuse where fewer than a
quarter are new. A comparison is exempt: it names both of its subjects by
construction, and `compares` is its gate. Sized against this run that
refuses 30 accepted questions, 19 of them in the release.

The run-ons are not fixed. `wrong_form` already knows the declared form,
but the example above is stored as a `list`, not a `value` or an
`explanation`, and a `value` or `explanation` carrying three or more `when`
clauses is one accepted question in this run, whose answer is sound. No
reading tried — coordinated clauses, coordinating conjunctions, repeated
`when` — separates the 35 from the answers that are lists of conditions.

## Facts that open on a demonstrative

121 of the 9,056 validated facts begin on a reference that resolves nowhere —
*These types of documentation…*, *Hierfür…*, *In such cases…*. 44 accepted
questions rest on one, 30 of those are in the release, and for 13 it is the
only fact cited, so the answer arrives from text the citation does not carry
and the row breaks the promise the Citations sheet makes.

The extractor flagged 3 of the 121. `_references` in
[`analysis.py`](../backend/nlp/analysis.py) collects pronouns and a short
list of anaphoric adjectives; a demonstrative *determiner* heading a noun
phrase is neither, so `Diese Dokumentationsarten` reads as an ordinary
subject.

**Fix.** Extend `_references` to return the demonstrative determiners and
pronominal adverbs that open a statement with no noun of their own before
the finite verb. Both shipped spaCy pipelines carry the tags, so this costs
no model call, and the existing `unresolved_reference` refusal in
[`validation.py`](../backend/extraction/validation.py) fires on the longer
array without changing.

Shipped as what `_opens` reads before the first finite verb, which also takes
`The effectiveness of this approach`. Sized against this run it refuses 179
of the validated facts the model wrote; 61 accepted questions rest on one,
36 in the release and 15 on it alone. A fact already stored changes only on
`make extract-revalidate`. `In such cases` is not caught: `such` carries no
demonstrative tag.

## Questions that count their own citations

25 release rows ask how many of something there are and answer with the
number of facts the writer was handed:

> *How many sections are identified across ATDD's approach type and the BDD
> scenario part that triggers behavior?* — `2 sections`

17 more name the offer rather than the subject — *in den Angaben*,
*together*, *across … and …*. One asks what page numbers a book index lists.
The question is about the prompt, not the corpus, so the corpus cannot answer
it.

The directive is not the problem. The `AGGREGATION` spec in
[`types.py`](../backend/question_generation/types.py) already says the
figures must be the same kind of thing and that two numbers sharing a corpus
do not add up to anything. The writer ignores it.

**Fix.** A gate, in [`gates.py`](../backend/question_generation/gates.py):
refuse to `malformed` where the question opens *How many* / *Wie viele* and
the answer's leading integer equals the number of cited facts. Three lines,
and it catches what the directive cannot enforce from inside the prompt.

Shipped for two or more cited facts and a count written in digits. Sized
against this run it refuses 8 accepted questions, all 8 in the release. The
counts written as words — `zwei Faktoren`, `two` — and the 17 that name the
offer are not caught.

## Boilerplate cited to the wrong document

69 validated facts rest on evidence that appears verbatim in more than one of
the 16 syllabi. Dedup keeps one copy and attributes it to whichever document
reached the extractor first, so a question about one syllabus cites a page in
another. 10 accepted questions, 6 in the release. The answers happen to be
right — the sentence says the same thing in both — but the page number sends
a marker to the wrong one.

**Fix.** Where a duplicate is refused, record its passage into
`fact_passages` beside the surviving fact rather than dropping it. The fact
then cites every document that states it, and the Citations sheet gains a row
instead of naming the wrong one.

Shipped with two changes the citation needs. `store` replaces a passage's
citations rather than its facts, and `delete_fact_without_passage` deletes a
fact other than a bridge only on its last citation. Without them, reading
the second document again, or deleting it, would delete the fact the first
document states. A fact already stored gains its citation only when the
passage is extracted again.

## The evaluation phase judges the newest rows

`_enrolment` orders by id descending so an incremental run judges what
arrived since the last one. On a first run over a finished corpus that takes
the tail: question ids 5597–5873 and fact ids 11955–12154, contiguous, **200
of 200 German and no English at all**. The assessed facts are 52% validated
against 74.5% across the run, so the slice is not the corpus.

Every figure under *The evaluation phase* in
[measurements.md](measurements.md) therefore describes the last-written
German slice — `qa_correctness`, `hallucination`, both disagreement matrices.
The page calls it a sample.

**Fix.** Nothing is wrong with newest-first for the incremental case it was
written for. Add `ASSESSMENT_STRATIFY`, default off, which enrols evenly
across language and question type and orders randomly within each band, and
set it for a measurement run. Until it exists,
[measurements.md](measurements.md) says which rows were judged.

Shipped as `ASSESSMENT_STRATIFY`, off in
[`backend.env`](../configs/env/backend.env). A fact's band is the language
of the passage it was read from, a topic's its own language, a question's
its language and its type. The figures in measurements.md stay the
last-written German slice until a run is judged with it set.

## Reproducing this page

The counts are queries over `questions`, `facts`, `question_facts` and
`fact_passages` — the run's own tables, not a log. The same rows come out of
the workbook:

```bash
make questions-export OUT=audit.xlsx FILTER="--status accepted"
```

Re-measuring means taking a corpus through again and rewriting both this page
and [measurements.md](measurements.md).
