# Known bugs

Defects in what the pipeline produced, each with the fix that closes it or
the reason it is still open.

The entries come from two runs.

- The first two entries, *Measured limitations* and *Known trade-offs* were
  measured against the re-verified release that
  [measurements.md](measurements.md) describes: 16 certification syllabi,
  German and English.
- Every entry from [The release drew the language written first](#the-release-drew-the-language-written-first)
  on was measured on the run of **2026-10-13** over the IFAB *Laws of the
  Game 2026/27*, in German and English. That run's 1,476 questions (576
  accepted, 238 released) were each read by hand against their sources, and
  each defect was traced to its root cause in the code.

That page holds the runs' figures; this one holds only what is wrong with
them. "Usable" below means a reviewer verdict of good or minor. The reviewer
verdicts are model judgements, accurate to about five points.

A fix in v0.2.2 changes what the next run writes. Stored rows improve only
through the re-runs that [operations.md](operations.md#upgrading-to-v022)
lists.

| | Release rows | Where the fix goes | Fixed |
|---|---|---|---|
| [Two subjects welded under one question word](#two-subjects-welded-under-one-question-word) | 11 | [`gates.py`](../backend/question_generation/gates.py) | no |
| [Questions that count their own citations](#questions-that-count-their-own-citations) | 4 | [`gates.py`](../backend/question_generation/gates.py) | partial |
| [The release drew the language written first](#the-release-drew-the-language-written-first) | 238 | [`balance.py`](../backend/question_generation/balance.py) | v0.2.2 |
| [Near-twin questions decided on one cosine](#near-twin-questions-decided-on-one-cosine) | 12 | [`gates.py`](../backend/question_generation/gates.py), [`balance.py`](../backend/question_generation/balance.py) | v0.2.2, partial |
| [Fact dedup folded a different rule into a stored fact](#fact-dedup-folded-a-different-rule-into-a-stored-fact) | 24 | [`extraction/service.py`](../backend/extraction/service.py) | v0.2.2 |
| [The widen retry replaced an honest draft](#the-widen-retry-replaced-an-honest-draft) | 5 | [`service.py`](../backend/question_generation/service.py) | v0.2.2 |
| [The count rule misread stated counts](#the-count-rule-misread-stated-counts) | 2 | [`gates.py`](../backend/question_generation/gates.py) | v0.2.2 |
| [The comparison gate split at the wrong seam](#the-comparison-gate-split-at-the-wrong-seam) | 2 | [`gates.py`](../backend/question_generation/gates.py) | v0.2.2, partial |
| [A fact may drop its sentence's scope](#a-fact-may-drop-its-sentences-scope) | 4 | [`validation.py`](../backend/extraction/validation.py) | no |
| [A two-item key was read as a value](#a-two-item-key-was-read-as-a-value) | not measured | [`gates.py`](../backend/question_generation/gates.py) | v0.2.2, partial |
| [Unanswerable questions the passages answer](#unanswerable-questions-the-passages-answer) | 8 | [`verifier.py`](../backend/question_generation/verifier.py), [`checker.py`](../backend/question_generation/checker.py) | v0.2.2 |
| [Sibling list items refused as duplicates](#sibling-list-items-refused-as-duplicates) | 42 | [`extraction/service.py`](../backend/extraction/service.py), [`extraction/models.py`](../backend/extraction/models.py) | v0.2.2 |
| [Two passages paired by reading order](#two-passages-paired-by-reading-order) | part of 68 | [`selection.py`](../backend/question_generation/selection.py) | v0.2.2 |
| [Application questions always spanned two passages](#application-questions-always-spanned-two-passages) | 11 | [`planning.py`](../backend/question_generation/planning.py) | v0.2.2 |
| [Reason questions with no stated reason](#reason-questions-with-no-stated-reason) | 15 | [`service.py`](../backend/question_generation/service.py) | v0.2.2 |
| [The perturbation prompt read "not stated" as "unanswerable"](#the-perturbation-prompt-read-not-stated-as-unanswerable) | 3 | [`generation.py`](../backend/question_generation/generation.py) | v0.2.2 |
| [Struck-through text read as current](#struck-through-text-read-as-current) | 8 | [`parsing/pipelines/pdf.py`](../backend/preprocessing/parsing/pipelines/pdf.py) | v0.2.2 |
| [A list cut from its lead-in](#a-list-cut-from-its-lead-in) | 3 | [`passages.py`](../backend/preprocessing/chunking/passages.py) | v0.2.2 |
| [Stale section paths, running feet and index letters](#stale-section-paths-running-feet-and-index-letters) | exposure | [`furniture.py`](../backend/preprocessing/chunking/furniture.py) | v0.2.2 |
| [`off_topic` refused every perturbation it read](#off_topic-refused-every-perturbation-it-read) | 0 (9 lost) | [`backend.env`](../configs/env/backend.env) | v0.2.2 |
| [`restates_question` read nouns only](#restates_question-read-nouns-only) | 0 (13 lost) | [`gates.py`](../backend/question_generation/gates.py) | v0.2.2 |
| [The round trip missed verbs, number words and counts](#the-round-trip-missed-verbs-number-words-and-counts) | 0 (7 lost) | [`gates.py`](../backend/question_generation/gates.py), [`checker.py`](../backend/question_generation/checker.py) | v0.2.2 |
| [An embedded question word read as a second question](#an-embedded-question-word-read-as-a-second-question) | 0 (5 lost) | [`gates.py`](../backend/question_generation/gates.py) | v0.2.2 |
| [A pronoun its own statement resolves read as dangling](#a-pronoun-its-own-statement-resolves-read-as-dangling) | 0 (48 facts lost) | [`nlp/analysis.py`](../backend/nlp/analysis.py) | v0.2.2 |
| [A translation read as furniture](#a-translation-read-as-furniture) | 0 (16 passages) | [`queue.py`](../backend/question_generation/queue.py) | no |
| [Difficulty grades spread, not hardness](#difficulty-grades-spread-not-hardness) | 73 hard | [`models.py`](../backend/question_generation/models.py) | no |
| [The entailment rescue scores a bare fragment](#the-entailment-rescue-scores-a-bare-fragment) | 0 (10 lost) | [`checker.py`](../backend/question_generation/checker.py) | no |
| [The release reads no quality signal](#the-release-reads-no-quality-signal) | 22 | [`balance.py`](../backend/question_generation/balance.py) | no |
| [Signal-diagram labels become passage text](#signal-diagram-labels-become-passage-text) | 0 | [`passages.py`](../backend/preprocessing/chunking/passages.py) | no |
| [`explanation_unusable` reads any proper noun as a name](#explanation_unusable-reads-any-proper-noun-as-a-name) | 0 (3 lost) | [`gates.py`](../backend/question_generation/gates.py) | no |
| [A refusal used as a key](#a-refusal-used-as-a-key) | 0 | [`gates.py`](../backend/question_generation/gates.py) | no |
| [`asks_nothing_new` on outline facts](#asks_nothing_new-on-outline-facts) | 0 | [`selection.py`](../backend/question_generation/selection.py) | no |

On the earlier corpus, 15 of the 1,015 release rows — **1.5%** — carried at
least one of the first two defects. On the 2026-10-13 run, 49% of the
released rows were usable, and the release was 79% German.

On the earlier corpus nothing touched the structure. Across the accepted
pool every citation resolved to a validated fact, every passage and document
scope agreed with the citations it describes, no question was in a language
its passages are not, and no two normalised question texts repeated. On the
2026-10-13 run one defect did reach the structure: fact dedup filed
citations that widened question scope (see
[Fact dedup folded a different rule into a stored fact](#fact-dedup-folded-a-different-rule-into-a-stored-fact)).

## Two subjects welded under one question word

10 release rows join two subjects with *and* under one question word and
answer each in its own half, so a chatbot answering one half is neither right
nor wrong:

> *How should tool metrics and test result communications be handled to
> support stakeholders without harming the test team's credibility?* —
> `Tool metrics should be designed and collected for the needs of the test
> team and other stakeholders… Test result communications must be accurate,
> clear, objective and fair…`

`compound` refuses a weld only where it carries two question words, so this
shape passes it. One more row is a run-on with no answer in it:

> *When does selecting test techniques to mitigate product risks depend on
> particular factors?* — `when tester knowledge and experience matter, when
> domain knowledge matters, … and when project constraints such as time and
> budget apply`

The 11 are questions 69, 425, 446, 979, 1119, 1157, 1464, 2219, 2952, 2953
and 2734. No fix has been attempted.

Measured as: every answerable release row whose normalised answer carries
three or more `and`/`und`, read by hand. That proxy is what this entry used to
count, and it flags 53. The other 42 are sound dense answers and lists —
*A reactive test strategy is a dynamic and heuristic approach in which the
test team designs and implements tests…* — and no lexical reading tried
(coordinated clauses, a repeated `when`, a repeated `, and`) separates the 11
from them.

## Questions that count their own citations

4 release rows name the offer rather than the subject — *Welche Teststufen
werden in den Angaben genannt?*, *What page references are listed for
co-location and projects together?*. The question is about the prompt, not
the corpus, so the corpus cannot answer it.

**Fix shipped (partial).** A gate in
[`gates.py`](../backend/question_generation/gates.py) refuses to `malformed`
where the question opens *How many* / *Wie viele*, the answer opens on a count
— in digits, or written out from two to twelve in German or English — and that
count equals the number of cited facts. No release row counts its own
citations. The 4 that name the offer are not caught.

The 4 are questions 2250, 2775, 4248 and 4976. Measured as: every release
question carrying *in den Angaben*, *zusammen*, *insgesamt*, *together*,
*combined*, *in total* or *across … and …*, read by hand. That proxy flags 23;
the other 19 use the words in their ordinary sense — *zusammengesetzt*, *im
Zusammenhang mit*, *across the team*.

**Changed in v0.2.2.** The rule now exempts a count that a cited statement
states, and refuses a bare count whatever the question opens with: see
[The count rule misread stated counts](#the-count-rule-misread-stated-counts).
The 4 that name the offer are still not caught.

## The release drew the language written first

The release held 187 German questions and 51 English ones, although the
accepted pool was 278 German and 298 English. Every one of the 24 released
unanswerable questions was German. The draw read no language, and drained
each bucket in ascending id order. Ids are creation order, and German was
written first, so German filled every bucket before English was reached. Two
English topics written last had nothing released at all.

**Fixed in v0.2.2.** The release now holds a share of each language
alongside its other three shares, in
[`balance.py`](../backend/question_generation/balance.py). The language
shares are equal over the languages the pool holds, unless
`QUESTIONS_RELEASE_LANGUAGES` weighs them. Each bucket is drawn in the order
of an md5 of the question id, which is reproducible but not tied to the
order things were written. The release report logs a language line. A
re-draw over the stored pool gives a release of about 214–224 rows, split
evenly between the two languages.

## Near-twin questions decided on one cosine

The duplicate gate refused on question cosine alone, at 0.93. On this
corpus that does not separate twins from neighbours: 9 of the 24 duplicate
rejections had no real twin, at 0.93–0.96, and 6 of those were usable. Ten
same-language twin groups were released whole, which left 12 spare rows. An
answerable question was refused as the duplicate of an unanswerable one
(question 471), so the question with an answer was the one thrown away.

**Fixed in v0.2.2, in part.** The bar now depends on what the two questions
cite, in [`gates.py`](../backend/question_generation/gates.py):

- a shared cited fact refuses at `QUESTIONS_DUPLICATE_SHARED_COSINE` (0.88);
- a shared cited passage refuses at `QUESTIONS_DUPLICATE_COSINE` (0.93);
- nothing in common refuses only halfway to identical;
- a different question word raises any of these to the highest bar.

Only questions in the same language, and of an answerability that can refuse
the candidate, are compared, so a translation is never a duplicate. An
answerable question is never the duplicate of an unanswerable one. The
release now keeps one question of each twin group, read by the same rule
among each question's nearest neighbours, and prefers the twin with the
higher recorded confidence.

**Still open.** Most of the twins the reviewers named share only a passage
and sit below 0.93, or ask with a different question word. No rule built on
cosine, citations or question words separates them from the sound
neighbours: the closest such rule would have rejected 26 usable questions.
They are pinned as expected failures in
[`test_question_verdicts.py`](../tests/regression/test_question_verdicts.py).

## Fact dedup folded a different rule into a stored fact

A candidate fact scoring 0.95 or more against a stored fact was refused as a
duplicate, and the refusal also wrote the candidate's passage and evidence
onto the stored fact. 89 of the 289 such fold links on question-cited facts
stated a different rule: a goal against a goal kick, a direct against an
indirect free kick, 5.5 m against 16.5 m. The folds counted towards each
question's passage, document and topic scope, so 168 questions were scored
as spanning passages they did not use. 36 of them were released.

**Fixed in v0.2.2**, in [`extraction/service.py`](../backend/extraction/service.py)
and [`extraction/repository.py`](../backend/extraction/repository.py):

- two statements whose numbers differ are never duplicates, and a number
  written as a word counts as that number. The probe reads the five nearest
  facts, so a nearer fact naming other numbers does not hide a repeat;
- the probe reads only facts of the candidate's own language and kind;
- `EXTRACTION_DUPLICATE_COSINE` is now 0.985;
- a refusal names the fact it repeats and writes nothing onto it.

Two new commands repair a corpus extracted before v0.2.2 without calling a
model. `make extract-dedup` re-decides every stored duplicate refusal, gives
back the ones the new rule would not make, and removes the fold links. A fact
whose own citation is gone keeps its folds, and the command names it for
`make extract-rerun`.
`make questions-rescore` then rewrites each question's scope and difficulty
from the facts it now cites, so `make questions-reverify` does not reject
them as `source_changed`.

## The widen retry replaced an honest draft

When an accepted draft cited one passage where its slot planned two, the
writer was asked again to "cite them all", and the accepted retry replaced
the first draft, which was then filed as `duplicate`. In 6 slots this kept
the worse question. Four of the six retries welded two unrelated facts, and
one was invalid. Lineage reported the replaced draft as failing a gate it
had passed.

**Fixed in v0.2.2.** The widen retry is gone, in
[`service.py`](../backend/question_generation/service.py). An accepted draft
is never asked again. If two drafts of one slot are both accepted, the first
is kept, and the other carries `superseded` after the gates it passed, so
lineage blames none of them.

## The count rule misread stated counts

The rule that refuses a key which only counts its own citations fired on
counts the cited facts actually state (questions 70, 71 and 1384, all
usable). It also missed bare counts asked as "Welche zwei…?" or "In wie
vielen Fällen…?" (questions 258 and 598, both released, one invalid).

**Fixed in v0.2.2**, in [`gates.py`](../backend/question_generation/gates.py).
A count that appears in a cited statement is exempt. The rule applies to any
bare-count answer whatever the question opens with, and "how many" is read
anywhere in the question through a per-language table. A count word counts
only where the tagger marks it a number, so "außer Acht" is not eight.

## The comparison gate split at the wrong seam

`_contrasts` passed a comparison along three wrong paths: any comparative
anywhere in the answer, an answer with no seam at all, or an incidental word
both sides shared. Sound comparisons whose axis lives in the question were
refused. 20 of the comparisons it refused were usable, and 8 of those it
passed were not.

**Fixed in v0.2.2, in part**, in [`gates.py`](../backend/question_generation/gates.py).
An answer is split at the seam between the two subjects the question names.
A comparison passes when:

- a comparative has one subject before it and the other after, within its
  stretch between seams ("Card payments settle faster than bank
  transfers, which take a day");
- across a seam that divides the subjects, each side has its own
  comparative, or one comparative stands where the seam opens a subordinate
  clause ("…, while …");
- or the two sides share a word the question does not.

An answer with no seam and no dividing comparative is refused.

**Still open.** The question-subtraction rule, part (d) of the fix, is
deferred, so the 10 sound comparisons whose axis only the question carries
are still refused. They are pinned as expected failures.

## A fact may drop its sentence's scope

Extraction validation never checks that a statement keeps its sentence's
scope. A fact validates even when it drops a restrictive clause, a negation,
"only", one condition of two, or most of a list. 8 such facts were confirmed
by hand, and 4 questions on them were released.

**Not fixed.** A deterministic check was built and measured over the stored
validated atomic facts. Read by hand, it was right on 50 of the 109 facts it
flagged, 46% against a bar of 80%, because a marker in another clause or
another list line looks the same to it. An NLI version ("does the sentence
entail the statement") was right on 10 of 60 sampled, and read both
restrictive-clause examples as entailed. Neither shipped. A check that
aligns clause by clause, treating each list line as its own unit, is the
next step.

## A two-item key was read as a value

`fitting` tried the "three or more items is a list" hint before the type's
own first form, so a two-item `condition` key was read as a value and never
checked for completeness. Of the 128 accepted incomplete keys, 95 were out
of the gate's reach for this and three other reasons.

**Fixed in v0.2.2, in part**, in [`gates.py`](../backend/question_generation/gates.py).
A two-item answer that carries no verb, given to a type that asks for a list
first, is read as a list. **Still open:** a check of the item count against
an enumerated passage waits for re-extracted facts, because until then the
evidence itself is incomplete.

## Unanswerable questions the passages answer

76 of the 158 accepted "unanswerable" questions are answerable, and 8 of the
24 released ones. The checks asked only whether an answer is stated
outright, so a passage that refutes the premise, closes a list, or settles
the case by a general rule went unnoticed. The probe showed the verifier 4
uncited passages, and 34 answering passages ranked lower. In the other
direction, nearness to an accepted answerable question counted as an answer
by itself, and so did a recovery that only said the question back.

**Fixed in v0.2.2**, in [`verifier.py`](../backend/question_generation/verifier.py)
and [`checker.py`](../backend/question_generation/checker.py):

- a new verifier judgement, `settles`, asks whether the passages answer the
  question, refute its premise, settle it by a general rule, or settle
  nothing. It runs over the cited passages, then over the probe. Only
  "settles nothing" keeps the question, and an "answers" whose quote only
  restates the question counts as settling nothing;
- the probe shows `QUESTIONS_ELSEWHERE_PASSAGES` (now 10) nearest passages,
  plus the passages two ordinals either side of each cited one;
- nearness to an answered question counts only when the two rest on the same
  fact;
- `make questions-rejudge` asks `settles` of the questions already accepted,
  rejects those the material settles, released ones included, and records
  each verdict. A question a person accepted is left alone.

Calibrated with `azure/gpt-4.1` over the 158 stored accepted unanswerables
against the reviewers' verdicts, `settles` refuses 29 of the 76 answerable
ones and 3 of the 82 sound ones. That is precision 0.91 and agreement 0.68,
against 0.52 for the reading it replaces. The other 47 answerable ones stay
accepted until a later check or a person withdraws them.

## Sibling list items refused as duplicates

The prompt splits a list into one statement per item, and the items differ
by one word, so every item after the first was refused as a duplicate of
the item this passage had already kept. 198 of the 248 same-passage
refusals behind question-cited facts carried a different claim. On top of
that, `EXTRACTION_MIN_OTHER_SHARE=0.33` capped every passage at four atomic
facts: 137 of the 138 passages with five or more bullets hit the cap. 42
released questions rest on a fact whose sibling was refused.

**Fixed in v0.2.2**, in [`extraction/service.py`](../backend/extraction/service.py)
and [`extraction/models.py`](../backend/extraction/models.py). A passage's
own facts are compared across kinds only, so two items of one list, or two
conditions of one rule, are kept as two claims, while a summary repeating a
claim beside it is still refused. The cap is kept, but never below the
passage's sentences plus list items, in the prompt and in what is kept.
`PROMPT_VERSION` for atomic extraction is now 10.

## Two passages paired by reading order

Every topic of this corpus lies in one document, so a cross-passage deal
always fell back to the nearest passage by ordinal, with no likeness check.
The further apart the two passages, the more often the question welded
unrelated facts: 80% of pairs more than ten ordinals apart. 110 accepted
questions (68 released) are welded, a share this bug shares with the widen
retry and the application deal.

**Fixed in v0.2.2**, in [`selection.py`](../backend/question_generation/selection.py).
Candidates in one document are ranked by likeness, and reading order only
breaks a tie. The meets floor now measures the fact the deal actually
offers. `QUESTIONS_MEETS_FLOOR` stays 0, because the floor was measured on
pairs the new ranking no longer deals.

## Application questions always spanned two passages

`application` is a one-passage kind, but its floor of medium sent it through
the two-passage deal with an instruction to use both. 23 of the 48 accepted
applications are welded, the highest rate of any kind, and 11 of those were
released.

**Fixed in v0.2.2**, in [`planning.py`](../backend/question_generation/planning.py).
A one-passage kind raised by its own floor is dealt the one passage its rule
sits in, at every band.

## Reason questions with no stated reason

`reason` was planned from the type mix alone, whatever the material states,
and the prompt forbade an invented reason without offering a way out. 38 of
the 63 accepted reason questions are circular, trivial or invented, and 15
of them were released.

**Fixed in v0.2.2**, in [`service.py`](../backend/question_generation/service.py)
and [`gates.py`](../backend/question_generation/gates.py). A reason slot, and
a reason follow-up turn, prefer facts whose evidence states a purpose,
read per language as lemmas and tokens ("so that", "in order to", "um … zu",
"damit"). Where the topic states none, the slot becomes another kind, and
the swap is logged. A language with no marker table is not filtered.

## The perturbation prompt read "not stated" as "unanswerable"

The prompt that writes unanswerable questions taught a swapped party as a
move, checked only whether its own fact answers the new question, and gave
as its one right example a case the passage's general rule settles. 49% of
the unanswerables it wrote were answered by its own material.

**Fixed in v0.2.2**, in [`generation.py`](../backend/question_generation/generation.py).
The prompt says a refuted premise, a case outside a closed list and a case a
general rule covers are all answered. It gives a wrong example of a swapped
party refuted by "only". Its retry note no longer prescribes a party swap,
and an unanswerable slot is dealt an atomic fact rather than a passage
summary. `PROMPT_VERSION` for question writing is now 12.

## Struck-through text read as current

The *Details of all Law changes* chapter marks a deletion only with a drawn
line through the word, and nothing between the PDF and the passage read
drawn lines. 231 German and 240 English struck words survived as text,
including whole deleted rules, and one passage stated the opposite of the
new rule. 25 validated facts assert deleted wording, and 8 released
questions cite a struck passage.

**Fixed in v0.2.2**, in [`parsing/pipelines/pdf.py`](../backend/preprocessing/parsing/pipelines/pdf.py).
Conversion finds every word with a horizontal line drawn through its
x-height and removes it from the text, the headings and the table cells. An
underline or a table rule removes nothing, and a page with no strokes comes
out unchanged. On these two PDFs the detector finds exactly the 471 struck
words and nothing else. Stored passages change only with a re-parse.

## A list cut from its lead-in

The chunker's token budget closed a passage right after a lead-in ending in
":", so the list it introduced started the next passage with no condition.
7 such cuts were found. Facts drawn from the list read as general rules, and
3 questions built on them were released.

**Fixed in v0.2.2**, in [`passages.py`](../backend/preprocessing/chunking/passages.py).
A lead-in cut from its list moves into the list's passage when the two fit
the budget. When they don't, it joins that passage's heading trail, which
both model stages are shown. A list longer than one passage carries its
lead-in in the heading trail of every passage after the first. Stored
passages change only with a re-chunk.

## Stale section paths, running feet and index letters

Section paths carried the previous chapter's heading into the next one, so
the English glossary sat under "4. Disciplinary action" and 118 of the 127
Law-changes passages never named their chapter. A running foot read as body
text, and the glossary's index letters, were glued into passage text.

**Fixed in v0.2.2**, in [`furniture.py`](../backend/preprocessing/chunking/furniture.py).
Chunking reads each page's chapter from the document's own running heads and
feet. It leaves out fields printed on every page, page numbers, and fields
printed on a single page. A new chapter starts with an empty heading trail,
and its label leads every trail in it. A page printing only part of its
chapter's label, after pages printing all of it, stays in that chapter.
Running feet read as body text,
an index letter that heads the entries under it, where the document's index
letters are two or more in ascending order, and heading segments that
are a lone conjunction or no word at all are dropped. A document with no
running heads gets today's paths.

**Still open.** The German PDF prints an English running foot over one of
its own pages. It cannot be told apart from the German document's own
furniture, so it stays in that passage.

## `off_topic` refused every perturbation it read

`off_topic` compared an unanswerable question with the lemmas of the one
short passage it cites. A perturbation always carries words that passage
lacks, by design. All 27 of its rejections were wrong, 9 of them usable, and
no other unanswerable scored anywhere near its bar.

**Fixed in v0.2.2** by setting `QUESTIONS_OFF_TOPIC_OVERLAP=0`, in
[`backend.env`](../configs/env/backend.env), which turns the gate off. A
rework that compares against the corpus's vocabulary and section paths is
deferred.

## `restates_question` read nouns only

The gate counts the new words an answer adds, but read only nouns, proper
nouns and adjectives, so the deciding verb or adverb was never seen: "The
player must be cautioned" added nothing. 19 of its 60 rejections were
wrong, and 13 of those were usable.

**Fixed in v0.2.2**, in [`gates.py`](../backend/question_generation/gates.py).
`restates` now reads verbs, adverbs and interjections too. An answer saying
yes or no to a question with no question word counts as an answer.

**Trade-off.** The gate is looser. On the stored rejections it frees 36,
about 8 of which the reviewers rated as right refusals: restatements that
add one new verb. Those share the shape of sound answers that must pass.

## The round trip missed verbs, number words and counts

Three deterministic defects in the round-trip comparator lost 7 usable
questions:

- a value key that nominalises the passage's verb never agreed ("a report"
  against "must be reported");
- "two" and "2" were different numbers;
- a count was refused as a sum that did not add up, without asking the
  model.

The stored `recall` reading also recorded the list threshold for value keys.

**Fixed in v0.2.2**, in [`gates.py`](../backend/question_generation/gates.py)
and [`checker.py`](../backend/question_generation/checker.py). Value keys
compare on verbs as well. Number words read as their figures, where the
tagger marks them numbers. A count question goes to the model when every
figure in its passages counts some other noun. The `recall` reading records
the bar actually applied. One question (1296) stays refused by arithmetic.

## An embedded question word read as a second question

`compound` counted every question word, so "differ in where" or "Wovon hängt
ab, wann" read as two questions. 11 of its 39 rejections were wrong, 5 of
them usable.

**Fixed in v0.2.2**, in [`gates.py`](../backend/question_generation/gates.py).
A further question word counts as a second question only after a
coordinating conjunction. **Trade-off:** a comma splice with no conjunction
("Wann ist sie fällig, wie viel kostet sie?") now passes as one question.

## A pronoun its own statement resolves read as dangling

`unresolved_reference` refused any third-person pronoun, even one whose
antecedent sits earlier in the same statement ("Der Ball …, wenn er …").
48 of its 95 refusals were of this kind. These are the facts that carry
conditions.

**Fixed in v0.2.2**, in [`nlp/analysis.py`](../backend/nlp/analysis.py).
A personal pronoun is resolved by an earlier noun that agrees with it and
lies outside the pronoun's own clause. Only a possessive determiner may name
a noun of its own clause ("The bank replaces its cards"). A German `es` is a
correlate only under a verb that disagrees with it in number. A pronoun
resolved this way is not recorded at all.

## A translation read as furniture

The boilerplate filter calls a passage furniture when a passage of another
document scores 0.95 or more against it. With one rulebook in two languages,
16 subject passages sit just above that bar against their own translation,
and were never offered to the writer.

**Not fixed.** Requiring the twin to be in the same language turns the filter
off on a corpus of one document per language, which would also let the 7
real furniture passages back in. Telling furniture apart needs another
reading first.

## Difficulty grades spread, not hardness

The difficulty band adds a point each for spanning passages, documents and
topics, for a long answer, and for being a follow-up. It grades retrieval
spread rather than how hard a question is. Hard answerable questions were
usable 43% of the time, against 61% for easy ones. The equal-thirds release
draws 83% of the hard pool.

**Not fixed.** This is a product decision, not a defect: whether the band
should grade spread or hardness. The fold links that inflated it are fixed
above.

## The entailment rescue scores a bare fragment

When the round trip fails, the NLI rescue scores the bare key against the
passage. Scoring "question + key" instead would rescue 7 usable rows and
admit 9 invalid or major ones.

**Not fixed.** The rescue was calibrated over 173 stored rows against the
shipped `bge-m3-zeroshot-v2.0` and two other multilingual NLI models
(mDeBERTa-v3 and xlm-roberta-large-xnli), with four hypothesis shapes. No
model, shape or threshold rescued more usable rows than it admitted bad
ones in both languages without tuning to these rows, so the rescue is
unchanged.

## The release reads no quality signal

The draw reads only answerability, band, kind and thread. It drains any
bucket short of its quota: all 22 aggregations were released, 3 of them
invalid. A thread is debited for its turns without checking them, so
`reason` was released 25 times against a quota of 23.

**Not fixed.** The stored signals are weak: confidence quartiles give 46–58%
usable. An ordering by confidence would raise the release from 49% to 52%
usable. The levers are upstream.

## Signal-diagram labels become passage text

Illustrations print their captions as text, and the chunker keeps all body
text, so six passages hold signal-diagram labels. No accepted question was
harmed.

**Not fixed.** A narrow filter for runs of short, verbless, upper-case items
is the proposed fix.

## `explanation_unusable` reads any proper noun as a name

The gate treats every proper-noun token as a name the passages must carry,
and the German tagger tags some common nouns as proper nouns. 3 usable
questions were lost.

**Not fixed.** No variant measured cleanly: matching entities only frees
some and not others, and adding section paths also frees right refusals.
The README now says the gate checks names as well as figures.

## A refusal used as a key

One key out of 1,476 was a refusal sentence ("I cannot write a valid
combined total… from these facts"). It was rejected only because its
question was also compound. As a reason, procedure, condition or factoid, a
refusal key would pass every structural gate.

**Not fixed.** One row, and it was caught. A `declined` field in the writer
schema is the proposed fix.

## `asks_nothing_new` on outline facts

A follow-up citing an outline or summary fact that its root also cited reads
as asking nothing new, even when it asks about a different bullet. The gate
works as specified; the deal offers it those facts.

**Not fixed.** Keeping outline and summary facts out of follow-up deals is
the proposed fix.

## Measured limitations

**The comparison gate refuses some sound comparisons.** `_contrasts` in
[`gates.py`](../backend/question_generation/gates.py) refuses a comparison
whose answer states no difference between its two sides. Read by hand over 20
of the 154 comparisons it alone refuses, drawn at random, it was right on 13
and wrong on 7 (5 clear, 2 close calls). The 7 share the ceiling its docstring
already names: each side needs a value on an axis the question supplies —
*BDD und ATDD bei der Formulierung von Tests* — and a lexical reading cannot
see an axis that only the question carries. The gate is left as it is:
`QUESTIONS_RELEASE_TYPES` holds `comparison` at its weighted target from the
comparisons that pass.

v0.2.2 changes where the gate splits an answer and when a comparative
counts: see
[The comparison gate split at the wrong seam](#the-comparison-gate-split-at-the-wrong-seam).
The ceiling named here still holds.

## Known trade-offs

Not defects: each is a rule doing what it is for, at a cost in sound rows.

**More citations, fewer questions.** Giving boilerplate facts their missing
citations moved 6 accepted questions from one passage or document to several.
Re-verification rejects a question whose stored scope no longer matches its
citations as `source_changed`. That is re-verify working as designed, and it
cost 6 sound questions.
**Changed in v0.2.2:** a fact cites its own passage alone. `make extract-dedup`
takes out every citation after the first on a fact other than a bridge, and
these citations are among them. A claim two documents hold is now a fact on
one and a `duplicate` refusal on the other, so deleting the first document
took the claim with it and left the refusal standing.
`make delete` and `make delete-derived` now run `extract-dedup` afterwards,
which gives the refusal back and re-judges and re-caps its passage. A
deletion through the API or the UI needs `make extract-dedup` run after it.

**The written-count gate has the digit rule's blind spot.** Of the 3 accepted
rows it moved, 2 were sound: `zwei Lernziele` (question 4255) and `zwei
Faktoren` (5355) count something their own facts state, and only happen to
equal the number of facts cited. The digit rule refuses the same shape —
`2 coverage items` (1409).
**Closed in v0.2.2:** a count a cited statement states is now exempt from
both rules.

## Reproducing this page

The counts are queries over `questions`, `facts`, `question_facts` and
`fact_passages` — the run's own tables, not a log. The same rows come out of
the workbook:

```bash
make questions-export OUT=audit.xlsx FILTER="--released"
```

The entries measured on the 2026-10-13 run come from a hand review of all
1,476 of its questions, one verdict per question, against the same tables.
Each entry's root cause was confirmed in the code and reproduced by a test
before it was fixed.

Re-measuring means taking a corpus through again and rewriting both this page
and [measurements.md](measurements.md).
