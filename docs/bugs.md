# Known bugs

Defects in what the pipeline produced, each with the fix that closes it or
the reason it is still open.

The entries come from three runs.

- The first two entries, *Measured limitations* and *Known trade-offs* were
  measured against the re-verified release that
  [measurements.md](measurements.md) describes: 16 certification syllabi,
  German and English.
- Every entry from [The release drew the language written first](#the-release-drew-the-language-written-first)
  on was measured on the run of **2026-10-13** over the IFAB *Laws of the
  Game 2026/27*, in German and English. That run's 1,476 questions (576
  accepted, 238 released) were each read by hand against their sources, and
  each defect was traced to its root cause in the code.
- [Found on the v0.2.2 rebuild of 2026-10-14](#found-on-the-v022-rebuild-of-2026-10-14) was measured on that
  rebuild of the same rulebook, read in full by hand. Its
  [After the fixes](#after-the-fixes) counts what the v0.3.0 rebuild of
  2026-10-16 changed.

That page holds the runs' figures; this one holds only what is wrong with
them. "Usable" below means a reviewer verdict of good or minor. The reviewer
verdicts are model judgements, accurate to about five points.

A fix changes what the next run writes. Stored rows improve only through the
re-runs that operations.md lists for [v0.2.2](operations.md#upgrading-to-v022)
and [v0.3.0](operations.md#upgrading-to-v030).

| | Release rows | Where the fix goes | Fixed |
|---|---|---|---|
| [Two subjects welded under one question word](#two-subjects-welded-under-one-question-word) | 11 | [`gates.py`](../backend/question_generation/gates.py) | no |
| [Questions that count their own citations](#questions-that-count-their-own-citations) | 4 | [`gates.py`](../backend/question_generation/gates.py) | partial |
| [The release drew the language written first](#the-release-drew-the-language-written-first) | 238 | [`balance.py`](../backend/question_generation/balance.py) | v0.2.2 |
| [Near-twin questions decided on one cosine](#near-twin-questions-decided-on-one-cosine) | 12 | [`gates.py`](../backend/question_generation/gates.py), [`balance.py`](../backend/question_generation/balance.py) | v0.2.2, partial; v0.3.0 in the release |
| [Fact dedup folded a different rule into a stored fact](#fact-dedup-folded-a-different-rule-into-a-stored-fact) | 24 | [`extraction/service.py`](../backend/extraction/service.py) | v0.2.2 |
| [The widen retry replaced an honest draft](#the-widen-retry-replaced-an-honest-draft) | 5 | [`service.py`](../backend/question_generation/service.py) | v0.2.2 |
| [The count rule misread stated counts](#the-count-rule-misread-stated-counts) | 2 | [`gates.py`](../backend/question_generation/gates.py) | v0.2.2 |
| [The comparison gate split at the wrong seam](#the-comparison-gate-split-at-the-wrong-seam) | 2 | [`gates.py`](../backend/question_generation/gates.py) | v0.2.2, partial |
| [A fact may drop its sentence's scope](#a-fact-may-drop-its-sentences-scope) | 4 | [`validation.py`](../backend/extraction/validation.py), [`extractors/llm.py`](../backend/extraction/extractors/llm.py) | v0.3.0, in part |
| [A two-item key was read as a value](#a-two-item-key-was-read-as-a-value) | not measured | [`gates.py`](../backend/question_generation/gates.py) | v0.2.2, partial |
| [Unanswerable questions the passages answer](#unanswerable-questions-the-passages-answer) | 8 | [`verifier.py`](../backend/question_generation/verifier.py), [`checker.py`](../backend/question_generation/checker.py) | v0.2.2, in part; none released in v0.3.0 |
| [Sibling list items refused as duplicates](#sibling-list-items-refused-as-duplicates) | 42 | [`extraction/service.py`](../backend/extraction/service.py), [`extraction/models.py`](../backend/extraction/models.py) | v0.2.2 |
| [Two passages paired by reading order](#two-passages-paired-by-reading-order) | part of 68 | [`selection.py`](../backend/question_generation/selection.py) | v0.2.2, v0.3.0 |
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
| [A translation read as furniture](#a-translation-read-as-furniture) | 0 (16 passages) | [`queue.py`](../backend/question_generation/queue.py) | v0.3.0 |
| [Difficulty grades spread, not hardness](#difficulty-grades-spread-not-hardness) | 73 hard | [`models.py`](../backend/question_generation/models.py) | no |
| [The entailment rescue scores a bare fragment](#the-entailment-rescue-scores-a-bare-fragment) | 0 (10 lost) | [`checker.py`](../backend/question_generation/checker.py) | no |
| [The release reads no quality signal](#the-release-reads-no-quality-signal) | 22 | [`balance.py`](../backend/question_generation/balance.py) | no |
| [Signal-diagram labels become passage text](#signal-diagram-labels-become-passage-text) | 0 | [`parsing/pipelines/pdf.py`](../backend/preprocessing/parsing/pipelines/pdf.py) | v0.3.0, mostly |
| [`explanation_unusable` reads any proper noun as a name](#explanation_unusable-reads-any-proper-noun-as-a-name) | 0 (3 lost) | [`gates.py`](../backend/question_generation/gates.py) | v0.3.0 |
| [A refusal used as a key](#a-refusal-used-as-a-key) | 0 | [`generation.py`](../backend/question_generation/generation.py) | v0.3.0 |
| [`asks_nothing_new` on outline facts](#asks_nothing_new-on-outline-facts) | 0 | [`gates.py`](../backend/question_generation/gates.py) | v0.3.0 |
| [A refused model call fails its whole topic](#a-refused-model-call-fails-its-whole-topic) | 1 topic | [`service.py`](../backend/question_generation/service.py), [`llm/client.py`](../backend/llm/client.py) | v0.3.0 |
| [Found on the v0.2.2 rebuild of 2026-10-14](#found-on-the-v022-rebuild-of-2026-10-14) | 321 | every stage | v0.3.0, mostly |
| [Found on the v0.3.0 rebuild of 2026-10-16](#found-on-the-v030-rebuild-of-2026-10-16) | 343 | every stage | v0.3.1 on, in part |

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
[`balance.py`](../backend/question_generation/balance.py). Unset, the
language shares follow the pool's own language split, unless
`QUESTIONS_RELEASE_LANGUAGES` weighs them otherwise. Each bucket is drawn in
the order of an md5 of the question id, which is reproducible but not tied
to the order things were written. The release report logs a language line.

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
among each question's nearest neighbours, and keeps the twin the draw's
hash ranks first, so creation order does not decide which one stays.

**Still open.** Most of the twins the reviewers named share only a passage
and sit below 0.93, or ask with a different question word. No rule built on
cosine, citations or question words separates them from the sound
neighbours: the closest such rule would have rejected 26 usable questions.
They are pinned as expected failures in
[`test_question_verdicts.py`](../tests/regression/test_question_verdicts.py).

**Narrowed in v0.3.0, for the release.** The draw asks the verifier whether
each released question and its nearest released neighbour want one answer,
and releases one question of each pair it says do (see *Release twins* under
[Found on the v0.2.2 rebuild](#found-on-the-v022-rebuild-of-2026-10-14)). Twins in the accepted pool stay.

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
is never asked again.

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

**Narrowed in v0.3.0, at the source.** The atomic prompt now keeps a rule's
conditions, exceptions and *only* in the statement, and restates the lead-in
a list item depends on. Validation still does not check scope. The share of
facts dropping a scope word fell in both languages; see
[After the fixes](#after-the-fixes).

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

**Still open in v0.3.0.** Measured again on the v0.2.2 rebuild's reviewed
rows, `settles` leaves about half of the questions the material answers as
settling nothing: a false-omission rate of 0.53 in German and 0.46 in
English, against the 0.15 a release can carry. Quoting, a fused probe of
twenty passages and showing the writer the passages beside its own did not
move it, and a second-opinion model only brought it to 0.39 and 0.34. v0.3.0
therefore releases none of these questions
(`QUESTIONS_RELEASE_UNANSWERABLE=0`); they stay in the accepted pool.

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

**Narrowed further in v0.3.0.** A second passage is offered only where its
closest fact is among the topic's closest 2% of fact pairs
(`QUESTIONS_MEETS_SHARE`), so many deals now offer one passage. On the
v0.3.0 rebuild, 6 of 40 sampled two-passage questions were welded, against
128 of 270 before; see [After the fixes](#after-the-fixes).

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
the bar actually applied. Question 1296 goes to the model too: its passage's
figures count a height, not flagposts.

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

**Fixed in v0.3.0**, at a cost. Repetition is now read within one language
only, so a passage and its translation are no longer furniture. On a corpus
holding one document per language the filter therefore finds nothing, and
the 7 real furniture passages of this corpus are offered again; the
extraction prompt's rule against facts about the document itself, also new
in v0.3.0, is what keeps their facts out.

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

**Mostly fixed in v0.3.0.** The labels were mostly text the page clips out
of view, and the parser now drops that: on the v0.2.2 rebuild it cleaned 11
of the 14 passages holding labels. A label printed in view is still body
text.

## `explanation_unusable` reads any proper noun as a name

The gate treats every proper-noun token as a name the passages must carry,
and the German tagger tags some common nouns as proper nouns. 3 usable
questions were lost.

**Fixed in v0.3.0.** The gate reads an explanation's figures only: a name it
uses to describe the answer is not a claim the passages must carry, and the
key's own checks hold its names. On the v0.2.2 rebuild that frees 14 of its
29 refusals, every one wrong or partly wrong, and refuses no accepted row.

## A refusal used as a key

One key out of 1,476 was a refusal sentence ("I cannot write a valid
combined total… from these facts"). It was rejected only because its
question was also compound. As a reason, procedure, condition or factoid, a
refusal key would pass every structural gate.

**Fixed in v0.3.0.** The writer's answer carries `declined`, set where the
facts it was dealt cannot answer the kind asked; the slot is written as
another kind on the same facts instead. It is also told to write about the
subject, never about the facts or the task.

## `asks_nothing_new` on outline facts

A follow-up citing an outline or summary fact that its root also cited reads
as asking nothing new, even when it asks about a different bullet. The gate
works as specified; the deal offers it those facts.

**Fixed in v0.3.0**, at the gate rather than in the deal: follow-ups citing
a summary or outline fact were the best ones (13 of 15 usable). A turn
citing only its root's summary or outline facts moves on when at least a
quarter of its key's content words are new to the thread. Replayed on the
v0.2.2 rebuild, that frees 10 refusals, 8 of them wrong.

## A refused model call fails its whole topic

Found on the v0.2.2 rebuild of **2026-10-14**, which ran the same corpus
again through every stage on `azure/gpt-5.4` (writer) and `azure/gpt-4.1`
(verifier, phrasing, extraction, topics). One of the 20 topics, the English
*Referee decisions and goal incidents*, ended `failed` with no questions. Its
writer had an unanswerable question refused as `answerable_elsewhere` and was
asked again, and Azure refused that retry prompt three times over: its
content filter returned every harm category as safe and **jailbreak detected**
(Prompt Shields). First drafts from the same material passed, so what the
shield most likely reads as an attempt to override instructions is the retry
note telling the writer to ask for something the corpus leaves unanswered.
The client reports the refusal as `ModelUnavailable`, and
question generation fails the whole topic on it. A retry fails the same way:
the same slot sends the same prompt.

**Fixed in v0.3.0.** A prompt the provider refuses under its content policy
is sent once, not retried, and costs its one slot or thread; the topic fails
only after five refusals in a row. The retry notes now read as a reviewer's
feedback on the quoted draft, and no longer tell the writer what it is
supposed to produce.

## Found on the v0.3.0 rebuild of 2026-10-16

The v0.3.0 rebuild of the same two PDFs was reviewed in full: every question,
fact, bridge, passage and topic was read against the corpus, the code was
audited, and every earlier claim on this page was checked again. Of its 871
accepted questions 70% were usable, and of its 343 released ones 76% on the
first reading (79% once disagreements were settled), with 10 invalid. Welds
fell to 18% of the questions citing two passages. The review left 39 ranked
defects, 145 verified code findings and 154 documentation gaps; each is now
fixed, deferred with its numbers, ranked low or found not to be a defect. The
fixes ship in the v0.3.x releases, and each was measured before it went in by
a replay of the review's labels over the stored v0.3.0 data, not by a
rebuild.

### Fixed in v0.3.1: model calls, settings and commands

| Defect | Found | Fix | Measured |
|---|---|---|---|
| Hidden re-asks inside each attempt | instructor re-asked up to 3 times within each of the client's attempts: up to 12 billed calls for one bad answer, 4 for a preflight | instructor asked for none ([`llm/client.py`](../backend/llm/client.py)) | 12 calls to 3, 4 to 1, with fake completions |
| A rate limit's `Retry-After` ignored | the 429 arrives wrapped, so the call backed off a second | read through the cause chain, at most two minutes | waits 30 s for `Retry-After: 30` |
| A filtered answer failed its topic | `content_filter` retried as a schema failure and reported as an unreachable model | a refusal after one call; the writer skips the slot | 1 call |
| Failed calls never costed | the "did not answer" line carried no cost; the answered line only the last response | every attempt summed onto both lines; `make spend` reads both | — |
| Ollama-only options sent to hosted models | `LLM_NUM_CTX` and Ollama's `off` effort reached a hosted override | sent only to the provider they belong to ([`llm/config.py`](../backend/llm/config.py)) | — |
| A recommended mode stopped every stage | 30 of the 38 offered `LLM_STRUCTURED_MODE` values, `ANTHROPIC_TOOLS` among them, are refused by litellm's client | the 8 it takes, others refused at start-up ([`settings/catalog.py`](../backend/settings/catalog.py)) | — |
| A recalibration rewrote stored scores | `confidence-recalibrate` dropped the shadow mark and prompt version | both kept ([`stages/recalibrate.py`](../backend/stages/recalibrate.py)) | on the v0.3.0 data it would have moved 40 confidences (21 released) and re-asked 377 verdicts; now none |
| A copied `backend.env` stalled the question worker | `QUESTIONS_MEETS_SHARE` had no default | absent reads 0.02 ([`question_generation/config.py`](../backend/question_generation/config.py)) | — |
| An old API build went unnoticed | the rebuild ran against an API still serving v0.2.2's settings | `make doctor` names the settings the API lacks ([`settings/drift.py`](../backend/settings/drift.py)) | — |
| `make test` failed in one run | the question CLI's tests wrote prompt rows into the test container; a logging test depended on order | the recorder stubbed; a unit test opening a database fails | green in one run, in any order |
| Make targets that misbehaved | `make audit` always passed; command-line ports missed the derived URLs; `make delete` refused only after deleting; `logs-wipe` unlinked open files; `certs` and `logs-prune` reported success after a failure; Argilla had no API key; the run dashboard matched other runs | each fixed ([`Makefile`](../Makefile), [`compose.yaml`](../compose.yaml)) | static tests per target |

### Fixed in v0.3.2: reading text and numbers

| Defect | Found | Fix | Measured |
|---|---|---|---|
| An abbreviation before a figure ended a sentence | `approx. 3 days`, `incl. 19 % VAT` split in two | an abbreviation is followed by a figure, not a sentence ([`nlp/analysis.py`](../backend/nlp/analysis.py)), unless a line break or an item number follows | 0 boundaries move in this rulebook |
| Two rules each ending in a full stop read as one sentence | a dash or slash after a sentence's end joined it to the next | a free dash or slash after a full stop and a space opens the next sentence, not after an abbreviation's | 7 English sentence cuts, all correct, 0 German; the audit's broader rule was measured wrong on 42 of 53 new pieces and not used |
| `provided` read as an exception | "The bank provided the card" lost its main verb | a finite `provided` is read as the verb it is, from the parse's morphology | 0 statements move here |
| Times and glued figures carried no number | `08:00`, `2.5x` asserted nothing a gate could check | read into their own claim field, compared group by group, so `08:00` is `8:00` and not `09:00` | 0 fact or question verdicts move here |
| A German decimal read as an integer | `0,125` read as 125, so the guard against 4 against 48 passed a wrong rate | a per-language `DECIMAL_MARK`; one mark before three digits that a key writes is read both ways, a zero head always a fraction | 0 of 2,371 German and 2,204 English texts read differently |
| An aggregation key accepted unasked | a key equal to any sum of passage figures skipped the verifier | the verifier is asked for every aggregation | 2 accepted rows now need the verifier's call |
| A relabelled aggregation kept its old level | a count typed as a factoid still counted as analysed | the relabel takes the new kind's level | 24 stored rows carried the wrong level |
| Figures-only paragraphs dropped | a price, a phone number or a date with no letter went as a page number | only a page number's shape is dropped ([`chunking/furniture.py`](../backend/preprocessing/chunking/furniture.py)) | 0 passages change here; fee-schedule fixtures keep their figures |
| A hyphenated word broken across a table cell or a page stayed broken | the mend ran before the joins | the mend runs after them too, with a per-language table of completing words ([`nlp/text.py`](../backend/nlp/text.py)) | 0 such breaks in this rulebook |

Still read wrongly, and left as they were before v0.3.2: `Mon. - Fri.` splits when `Mon.` is not in the language's abbreviation table; `1.234,567` reads as one integer; a German `8.30 Uhr` and `08:30` do not agree; a key `1000 EUR` does not agree with a German reply `1,000 EUR`.

### Fixed in v0.3.3: the unit of a fact

| Defect | Found | Fix | Measured |
|---|---|---|---|
| Dedup refused facts against facts about to be deleted | a re-extraction probed new facts against old ones it then replaced; `make extract-revalidate` skipped the dedup gate and the cap | the extract worker replays dedup itself once its queue empties after replacing facts, under a database lock; a revalidation probes what it validates against what is validated, in id order ([`extraction/service.py`](../backend/extraction/service.py)) | on the reviewed refusals 5 given back, 0 twins created |
| A statement the tagger mis-rooted counted as two claims | a subordinate clause's verb read as a second main verb | the root is read past a subordinator ([`nlp/analysis.py`](../backend/nlp/analysis.py)) | English: 5 wrong `not_atomic` refusals freed, 0 right lost |
| A verb the tagger gave a finite fine tag but no verb part of speech asserted nothing | `asserts_nothing` on a stated rule | the fine tag is read too | German: 1 freed |
| A fact copying one sentence was judged on the sentence counts stored at chunking | `copied` refused facts whose sentence had been re-split since | judged on the claims it reads as now | 20 `copied` refusals become `not_atomic`, on the claims they make |
| A verbatim repeat inside one passage kept twice | the cap and the dedup gate never saw the twin | refused as a duplicate of the passage's own fact | 0 in the stored data |
| Refusal messages misstated the dedup bar, and over-cap twice | — | worded as set | — |
| A "the model proposed nothing" warning where no model ran | the warning fired on passages the pre-filter skipped | fires only where a model read the passage | — |
| A figure table or priced list skipped as an identifier grid | the pre-filter took cells of bare figures for noise | a figure in a cell is read as the value it is | 0 stored passages change |
| A fact citing no sentence dropped | the model's uncited fact vanished without a refusal | stored as `evidence_absent` | — |

### Deferred or low, with the reason

| Defect | Why it stays open |
|---|---|
| The release draw overshoots its quotas with follow-up questions, and its size search halves over a test that is not monotonic | Every change to the draw was measured over 100 paired draws on the stored pool, a pool without bridges and a pool a third the size. Counting follow-ups within their quota raised the weld rate on all three (on the stored pool from 18.8 to 24.9 welded per draw on average): the places it frees go to root questions and short kinds, which cite two passages more often. Scanning for the size and dropping a later turn at the round cap are weld-neutral, but the floor says welds never rise, so they wait for a decision on a non-inferiority reading |
| Explanation-form keys are not held to completeness | The only bar that separated complete from partial keys passed at 7 rows, one more usable row would fail it, and German commas inflate the item count it reads |
| Section paths are wrong at scale | Docling now offers public heading options, but every setting tried moves 200 or more paths the review judged right while fixing about 160 wrong ones. A general fix needs a re-levelling pass from the PDF's own styles, checked against a judged set |
| `make doctor` checks only the container's shared model and verifier | Whether containers may call a hosted model is a deployment policy to settle first |
| Six readings that would have freed most wrong fact refusals | Measured on this rulebook they freed 47 wrong refusals for 0 right ones: a pronoun resolved within its own clause, English `this` read as resolved, an `it`/`es` before an *if* clause read as a placeholder, a subjectless *but* clause read as part of one claim, a German verb-first condition, and a name borrowed from an earlier sentence. An independent review then ran 119 bank and shop sentences a validator must refuse through them: they admitted 46. They read agreement where a reader needs to know which of several nouns is meant, so they fail the rule that a fix must hold for any corpus. A general fix needs coreference that sees competing antecedents |
| Duplicate refusals compare statements without their headings | Embedding each statement with its heading trail frees 19 to 31 wrong refusals but makes 71 to 121 new twins on the stored facts. It waits for facts that carry their scope (R23) |
| Two extract workers can both keep one claim | Each probe sees only committed facts; closing it needs a lock across workers or a uniqueness rule on the statement |
| Glossary definitions get no facts | A verbless passage under a term heading can be read as a definition, but on this corpus it also reads 13 junk passages made of diagram labels, which the parsing release removes first. It moves to that release |
| Tooling odds and ends | The CI cache key hashes the whole Makefile; an unused SeaweedFS UI container; `make dev` waits for Postgres without a timeout. Low |

## Found on the v0.2.2 rebuild of 2026-10-14

The v0.2.2 rebuild ran the same corpus again through every stage, with
`azure/gpt-5.4` writing and `azure/gpt-4.1` verifying, naming topics and
extracting. Every item it produced was read by hand against the corpus:
1,760 questions, 4,312 facts, 833 passages against the PDF pages, and the 20
topics. Of the 837 accepted questions 475 (57%) were usable, against 50% on
the run before; of the 321 released, 166 (52%), against 49%. Each defect
below was traced to its cause, and each fix was measured offline on the
reviewed rows before it went in. "Usable" means a reviewer verdict of good
or minor, accurate to about five points.

What the v0.3.0 rebuild of the same corpus measured after the fixes is in
[After the fixes](#after-the-fixes).

### Parsing

| Defect | Found | Fix in v0.3.0 | Measured on the reviewed rows |
|---|---|---|---|
| A struck word survived, or took its neighbours with it | struck text kept in 5 German and 6 English passages; 5 passages over-stripped | Strike-through read per character; a bracket or comma beside a deletion stays; apostrophes and dashes folded before matching | the passages' struck text gone in the replay; what is left is source quirks |
| Text the page hides read as body text | 14 passages of signal-diagram labels (8 German, 6 English) | Text the page clips out of view is dropped | 11 of the 14 cleaned; a label printed in view stays |
| A raised ordinal read as a separate word | 9 English `1 st`; 8 facts refused for it | The superscript suffix is joined to its number | all 9 joined |
| A table broken at a page or inside a wrapped cell | 8 German and 7 English broken tables | A header-less table right after one of its width joins it; a wrapped cell or label rejoins its row | continuations joined: 3 German, 2 English; wrapped rows joined: 2 English |
| A two-column page interleaved | 2 passages | not fixed, **low**: reading order needs a better layout model | — |

### Chunking

| Defect | Found | Fix in v0.3.0 | Measured on the reviewed rows |
|---|---|---|---|
| A one-page chapter lost its label | chapter missing on 20 German and 23 English passages | A one-page foot laid out as a chapter's names one; guide words still name none | chapter missing 20 → 0 and 23 → 0 |
| Letter-spaced chapter labels | 178 German and 97 English section paths | A label takes the spaces the body puts in the same words | 178 → 0 and 97 → 0 |
| A lead-in cut from its list by a sub-heading, or a sentence cut by a page | lead-ins lost: 15 German, 17 English; sentences split: 7 and 4; passages ending on a colon: 8 and 7 | The lead-in travels into the sub-headed chunk; a sentence cut at a page or column joins its rest | colon endings 8 → 5 and 7 → 3; mid-sentence cuts 1 → 0 in each language |
| A repeated heading or a page number as its own passage | 15 German and 16 English passages | A heading-equal paragraph heads the passage after; a figures-only paragraph goes | figure-only passages 2 → 0 and 3 → 0; passages 424 → 417 and 412 → 407 |
| Stale one-letter index segments | 66 English passages | Index letters read from headings and text; the longest run in order is the index | 66 → 0 |
| A nested list flattened | 152 German and 154 English items in 42 and 38 passages | An indented item nests under the one above and is rendered indented | 123 German and 147 English items nested |
| Heading levels from numbering out of sequence | quoted `5.3` / `3.2` as parents of 36 passages; the change log's stale parents | not fixed, **low**: needs Docling's style inference, which is not a public interface, and the right parent needs words | — |
| A group heading at its children's level | 4 passages | not fixed, **low**: the headings differ only in font family and colour | — |

### Extraction

| Defect | Found | Fix in v0.3.0 | Measured on the reviewed rows |
|---|---|---|---|
| A fact dropped its rule's scope | 486 of 3,578 facts narrowed (16% German, 10% English): lead-ins lost 264 times, conditions 249, exceptions 91, *only* 28 | Atomic prompt 11: the smallest statement true read alone; conditions, exceptions and *only* kept; lead-ins restated and cited; modality kept | in the rebuild, by a word-level count: atomic facts dropping *only*, *if*, *unless* or *except* from their evidence 16.6% → 10.8% German, 30.9% → 28.2% English |
| Sound facts refused as `not_atomic` | 25 German, 92 English | A rule and its exception, and two alternatives, count as one claim | freed 12 and 40, no right refusal lost |
| Sound facts refused as `unresolved_reference` | 84 German, 88 English | Pronouns resolved by the language's grammar | freed 57 and 73; 1 right refusal lost |
| Sound facts refused as `asserts_nothing` | 2 German, 12 English | A root verb with a subject counts, as does a German or Dutch plural spelled as the infinitive | freed 2 and 3 |
| Evidence cut mid-sentence | 76 German and 43 English facts | No cut inside a slash-joined word, before a comma clause, after an abbreviation before lower case, or between an item number and its item | every such cut gone; 63 passages re-split |
| Sound facts refused as `unsupported_addition` | 43 German, 72 English | Names and numbers read against the evidence, the section path and the title, numbers in any spelling | freed 27 and 45 |
| A different rule refused as a duplicate | 231 duplicate refusals, 13 of them wrong and 22 partly | not fixed: a guard taking two near statements as twins only when every word one has and the other lacks is in the other's passage was built and then **reverted** | on the review it gave back 11 of 13 wrong and 13 of 22 partly, at a cost of 25 of 196 right; on the rebuilt facts it kept 9 distinct rules apart and 26 restatements of one rule |
| Summaries about "the excerpt" | 61% German, 78% English | Digest prompt 4 opens on the subject | in the rebuild, summaries opening on the excerpt went from 52% to 0% in German and from 75% to 0% in English |
| Facts about the document itself | 53 validated; 10 subject passages excluded as a translation's furniture | Prompt rule; repetition read within one language | not counted: telling these facts apart needs a hand review |
| No bridge fact ever written | 0 bridges | The bridge pass runs in `make corpus` for topics holding none | in the rebuild: 249 written, 179 validated |

### Topic modelling

| Defect | Found | Fix in v0.3.0 | Measured on the reviewed rows |
|---|---|---|---|
| Labels read off headings and stubs | 28 of 80 label excerpts carried no fact | Excerpts from fact-bearing passages, by weight times length | citation-unit share 42% → 54% |
| Headings and page numbers fitted as subjects | 135 barren members | Fit on passages carrying a fact | German NPMI 0.005 → 0.053; barren label excerpts → 0 |
| Every label named the domain | 9 of 10 German labels end "im Fußball", all spell ß though no passage does | One naming call per language; spelling held to the excerpts; a shared trailing phrase taken off | ß 10 → 0; shared endings 9 → 1. In the rebuild the 6 German topics named afresh have neither; 3 kept their v0.2.2 names, which a fit carries over where the top terms still match |
| A topic's passages never asked about | 21 of one topic's 32 fact-bearing passages; 2 passages in no topic | The refusal that killed the topic fixed (below); a passage in no topic joins the nearest centroid | in the rebuild: every passage carrying a fact is in a topic; those no question cites went from 9 to 17 German and from 28 to 11 English |

### Question generation

| Defect | Found | Fix in v0.3.0 | Measured on the reviewed rows |
|---|---|---|---|
| Two facts welded into one question | 128 of 270 two-passage questions (47%); 104 released | A second passage only where its closest fact is among the topic's closest 2% of pairs, never a restatement | removes 100 of 128 welds, keeps 95 of 142 sound pairs |
| The release drew every hard question | release 52% usable | The band split follows the answerable pool | 57% usable alone, about 67% with the weld fix |
| Keys naming part of a list | 79 released incomplete keys | A reading or list slot is offered the whole list, up to eight items; prose keys read in shadow | not counted without a hand review. The shadow reading is stored on 75 accepted prose keys whose recovery says more than they do: on average they hold 52% of its content words. No bar is set on it yet |
| Unanswerable questions the corpus answers | 141 of 283 accepted, 19 of 32 released | Quote held to the passages; probe of twenty fused by vector and words; neighbours shown to the writer; settled ones recycled into answerable questions; **release share 0** | calibration: false-omission rate 0.53 German, 0.46 English, unchanged by the prompt; a second-opinion model gets it to 0.39 and 0.34 |
| Circular "why" keys | 25 of 50 accepted reason keys | A why whose recovery only restates the question is refused before the entailment rescue | it refused 1 draft in the rebuild, and the spot check below still met one circular key (question 3853) |
| A change log's quotations used as the source | 114 accepted cite it; 36 an elided passage | An elided passage is dealt last and never to a list slot | rule flags 44 passages, 43 in the change log |
| Release twins | 6 released twin pairs; 42 released rows in twin groups | The verifier judges each released question against its nearest released neighbour | calibration: 24 of 29 twins found, none of 60 non-twins called one. The rebuild's draw held 12 pairs to one question each |
| Follow-up comparisons refused | 141 of 151 | Comparison out of the follow-up kinds; ISO opener table; suspended hyphens count as items | — |
| A rescued key not checked for completeness | rescue held 13 of the 32 wrong accepted keys | `incomplete` runs after the rescue too | not counted: the stored readings do not say which keys the rescue passed |
| A thread's later turn refused | 6 wrong `off_thread`; 27 `restates_question`; summary follow-ups refused | `off_thread` reads the whole thread; a negative or a party counts as an answer; a summary turn moves on when its key is new | frees the 6, 7 restates refusals and 10 summary turns |
| Sound explanations and numbered rules refused | 29 `explanation_unusable`, 11 `leaks_source` | Explanations held to figures; a numbered article, clause or rule is a subject, a section a source | frees 14 explanations and 3 leaks, none rightly refused |
| Retries returning the same draft | 22 of 291 | The note quotes the draft; an unchanged retry is not stored again | 13 stopped, none accepted lost |
| A refused prompt failed its topic | 1 topic | A content-policy refusal skips one slot | the rebuild met no refusal and lost no topic |
| Wrong type labels and meta-text | 160 of 837 accepted tagged wrong type; meta-text in 73 explanations | Type read off the opening; a count with no figure relabelled; the writer may decline | 50 wrong-type refusals pass the free gates (24 usable), still facing the model gates; 21 labels corrected. In the rebuild the writer declined 36 slots and 10 follow-up turns |

### After the fixes

The v0.3.0 rebuild of **2026-10-16** took the same two PDFs through every
stage again, with the same models. Nobody read it in full: the figures below
are counts over its tables, except the weld rate, which is a spot check of
40 accepted questions citing two or more passages, 20 per language, drawn at
random. [measurements.md](measurements.md#the-v030-rebuild-of-2026-10-16)
has the run itself. Each cell reads German, then English.

| | v0.2.2 rebuild | v0.3.0 rebuild |
|---|---|---|
| Letter-spaced section paths | 178, 97 | 0, 0 |
| Passages carrying a validated fact | 358, 331 | 361, 339 |
| Validated facts, bridges aside | 1,976, 1,602 | 1,692, 1,488 |
| `not_atomic` refusals per 1,000 facts | 17.8, 56.4 | 32.1, 61.4 |
| `unresolved_reference` per 1,000 | 42.4, 48.4 | 30.1, 21.0 |
| `unsupported_addition` per 1,000 | 19.1, 45.4 | 9.2, 18.2 |
| Atomic facts dropping *only*, *if*, *unless* or *except* | 16.6%, 30.9% | 10.8%, 28.2% |
| Summaries opening on "the excerpt" | 52%, 75% | 0%, 0% |
| Bridge facts | 0 | 249 |
| Passages carrying a fact that no question cites | 9, 28 | 17, 11 |
| Accepted questions citing two or more passages | 270 of 837 (32%) | 183 of 871 (21%) |
| Of those, welded | 128 of 270 (47%), all read | 6 of 40 (15%), spot check |
| Released | 321 | 343 |
| Released `hard` | 100 | 23 |
| Released citing two or more passages | 209 | 91 |
| Released with no answer | 32 | 0 |

Fewer facts now cover more passages: the atomic prompt keeps a rule with its
conditions and exceptions in one statement, where it used to write each
piece as a fact of its own. The validator refuses more of these joined
statements as `not_atomic`, in German nearly twice as often as before.
Passages carrying a validated fact still rose in both languages.

The weld rate's 95% interval is 7% to 29%, so the spot check does not rule
out a rate just above a quarter. 1 of the 22 released questions in the
sample was welded; over the 91 released questions citing two or more
passages, that puts the release's welds at about 4 to 14, against 104 in
v0.2.2. Each weld the check found joins two rules that share a subject but
not a situation, such as two signals asked about as one *why*.

None of the questions with no answer were released, by setting: the
`settles` judgement that keeps them still misses too many the material does
answer, and its false-omission rate did not move (see the unanswerable row
above).

Not counted without a hand review: the usable share, key completeness, type
labels, circular reasons and the facts about the document itself.

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

[Found on the v0.2.2 rebuild of 2026-10-14](#found-on-the-v022-rebuild-of-2026-10-14) comes from a hand review
of all 1,760 questions of that rebuild, with its facts, its passages against
the PDF pages, and its topics. Its *After the fixes* figures are queries over
the v0.3.0 rebuild's tables.

Re-measuring means taking a corpus through again and rewriting both this page
and [measurements.md](measurements.md).
