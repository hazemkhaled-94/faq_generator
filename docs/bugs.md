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
| [Near-twin questions decided on one cosine](#near-twin-questions-decided-on-one-cosine) | 12 | [`gates.py`](../backend/question_generation/gates.py), [`balance.py`](../backend/question_generation/balance.py) | v0.2.2, partial; v0.3.0, partial |
| [Fact dedup folded a different rule into a stored fact](#fact-dedup-folded-a-different-rule-into-a-stored-fact) | 24 | [`extraction/service.py`](../backend/extraction/service.py) | v0.2.2 |
| [The widen retry replaced an honest draft](#the-widen-retry-replaced-an-honest-draft) | 5 | [`service.py`](../backend/question_generation/service.py) | v0.2.2 |
| [The count rule misread stated counts](#the-count-rule-misread-stated-counts) | 2 | [`gates.py`](../backend/question_generation/gates.py) | v0.2.2, partial |
| [The written-count gate has the digit rule's blind spot](#the-written-count-gate-has-the-digit-rules-blind-spot) | not measured | [`gates.py`](../backend/question_generation/gates.py) | v0.2.2, partial |
| [The comparison gate split at the wrong seam](#the-comparison-gate-split-at-the-wrong-seam) | 2 | [`gates.py`](../backend/question_generation/gates.py) | v0.2.2, partial; worse in v0.3.0 |
| [A fact may drop its sentence's scope](#a-fact-may-drop-its-sentences-scope) | 4 | [`validation.py`](../backend/extraction/validation.py), [`extractors/llm.py`](../backend/extraction/extractors/llm.py) | v0.3.0, in part |
| [A two-item key was read as a value](#a-two-item-key-was-read-as-a-value) | not measured | [`gates.py`](../backend/question_generation/gates.py) | v0.2.2, partial |
| [Unanswerable questions the passages answer](#unanswerable-questions-the-passages-answer) | 8 | [`verifier.py`](../backend/question_generation/verifier.py), [`checker.py`](../backend/question_generation/checker.py) | v0.2.2, in part; none released in v0.3.0 |
| [Sibling list items refused as duplicates](#sibling-list-items-refused-as-duplicates) | 42 | [`extraction/service.py`](../backend/extraction/service.py), [`extraction/models.py`](../backend/extraction/models.py) | v0.2.2 |
| [Two passages paired by reading order](#two-passages-paired-by-reading-order) | part of 68 | [`selection.py`](../backend/question_generation/selection.py) | v0.2.2, v0.3.0 |
| [Application questions always spanned two passages](#application-questions-always-spanned-two-passages) | 11 | [`planning.py`](../backend/question_generation/planning.py) | v0.2.2 |
| [Reason questions with no stated reason](#reason-questions-with-no-stated-reason) | 15 | [`service.py`](../backend/question_generation/service.py) | v0.2.2, not effective |
| [The perturbation prompt read "not stated" as "unanswerable"](#the-perturbation-prompt-read-not-stated-as-unanswerable) | 3 | [`generation.py`](../backend/question_generation/generation.py) | v0.2.2 |
| [Struck-through text read as current](#struck-through-text-read-as-current) | 8 | [`parsing/pipelines/pdf.py`](../backend/preprocessing/parsing/pipelines/pdf.py) | v0.2.2 |
| [A list cut from its lead-in](#a-list-cut-from-its-lead-in) | 3 | [`passages.py`](../backend/preprocessing/chunking/passages.py) | v0.2.2, partial |
| [Stale section paths, running feet and index letters](#stale-section-paths-running-feet-and-index-letters) | exposure | [`furniture.py`](../backend/preprocessing/chunking/furniture.py) | v0.2.2 |
| [`off_topic` refused every perturbation it read](#off_topic-refused-every-perturbation-it-read) | 0 (9 lost) | [`backend.env`](../configs/env/backend.env) | v0.2.2 |
| [`restates_question` read nouns only](#restates_question-read-nouns-only) | 0 (13 lost) | [`gates.py`](../backend/question_generation/gates.py) | v0.2.2, partial |
| [The round trip missed verbs, number words and counts](#the-round-trip-missed-verbs-number-words-and-counts) | 0 (7 lost) | [`gates.py`](../backend/question_generation/gates.py), [`checker.py`](../backend/question_generation/checker.py) | v0.2.2 and v0.3.4, partial |
| [An embedded question word read as a second question](#an-embedded-question-word-read-as-a-second-question) | 0 (5 lost) | [`gates.py`](../backend/question_generation/gates.py) | v0.2.2 |
| [A pronoun its own statement resolves read as dangling](#a-pronoun-its-own-statement-resolves-read-as-dangling) | 0 (48 facts lost) | [`nlp/analysis.py`](../backend/nlp/analysis.py) | v0.2.2, partial |
| [A translation read as furniture](#a-translation-read-as-furniture) | 0 (16 passages) | [`queue.py`](../backend/question_generation/queue.py) | v0.3.0 |
| [Difficulty grades spread, not hardness](#difficulty-grades-spread-not-hardness) | 73 hard | [`models.py`](../backend/question_generation/models.py) | no |
| [The entailment rescue scores a bare fragment](#the-entailment-rescue-scores-a-bare-fragment) | 0 (10 lost) | [`checker.py`](../backend/question_generation/checker.py) | v0.3.4, partial |
| [The release reads no quality signal](#the-release-reads-no-quality-signal) | 22 | [`balance.py`](../backend/question_generation/balance.py) | no |
| [Signal-diagram labels become passage text](#signal-diagram-labels-become-passage-text) | 0 | [`parsing/pipelines/pdf.py`](../backend/preprocessing/parsing/pipelines/pdf.py) | v0.3.0 and v0.3.6, in part |
| [`explanation_unusable` reads any proper noun as a name](#explanation_unusable-reads-any-proper-noun-as-a-name) | 0 (3 lost) | [`gates.py`](../backend/question_generation/gates.py) | v0.3.0 |
| [A refusal used as a key](#a-refusal-used-as-a-key) | 0 | [`generation.py`](../backend/question_generation/generation.py) | v0.3.0 |
| [`asks_nothing_new` on outline facts](#asks_nothing_new-on-outline-facts) | 0 | [`gates.py`](../backend/question_generation/gates.py) | v0.3.0 |
| [A refused model call fails its whole topic](#a-refused-model-call-fails-its-whole-topic) | 1 topic | [`service.py`](../backend/question_generation/service.py), [`llm/client.py`](../backend/llm/client.py) | v0.3.0 |
| [Found on the v0.2.2 rebuild of 2026-10-14](#found-on-the-v022-rebuild-of-2026-10-14) | 321 | every stage | v0.3.0 on, in part |
| [Found on the v0.3.0 rebuild of 2026-10-16](#found-on-the-v030-rebuild-of-2026-10-16) | 343 | every stage | v0.3.1 on, in part |
| [Found on the v0.4.0 rebuild of 2026-10-18](#found-on-the-v040-rebuild-of-2026-10-18) | 318 | every stage | v0.3.9 on, in part |

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

**Narrowed in v0.3.0, for the release; still open.** The draw asks the
verifier whether each released question and its nearest released neighbour
want one answer, and releases one question of each pair it says do (see
*Release twins* under
[Found on the v0.2.2 rebuild](#found-on-the-v022-rebuild-of-2026-10-14)). It
asks about one neighbour per question, and the draw made after its last round
is not asked about, so the v0.3.0 release still holds 19 twin groups (43
rows); 13 of the 21 twin pairs are a follow-up re-asking its own thread. The
shared-fact bar also refuses sound follow-ups: on the v0.3.0 rebuild 12
follow-ups were refused as twins of their own root, all wrongly. Twins in the
accepted pool stay.

## Fact dedup folded a different rule into a stored fact

A candidate fact scoring 0.95 or more against a stored fact was refused as a
duplicate, and the refusal also wrote the candidate's passage and evidence
onto the stored fact. 89 of the 289 such fold links on question-cited facts
stated a different rule: a goal against a goal kick, a direct against an
indirect free kick, 5.5 m against 16.5 m. The folds counted towards each
question's passage, document and topic scope, so 168 questions were scored as
spanning passages they did not use, and 36 of them were released. The table
counts the 24 released questions that rested on a fold stating a different
rule.

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

Folding is gone: no fact other than a bridge cites two passages on either
rebuild. The dedup that replaced it has defects of its own; see *A different
rule refused as a duplicate* under
[Found on the v0.2.2 rebuild](#found-on-the-v022-rebuild-of-2026-10-14) and
*Duplicate refusals compare statements without their headings* under
[Found on the v0.3.0 rebuild](#found-on-the-v030-rebuild-of-2026-10-16).

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

**Fixed in v0.2.2, in part**, in [`gates.py`](../backend/question_generation/gates.py).
A count that appears in a cited statement is exempt. The rule applies to any
bare-count answer whatever the question opens with, and "how many" is read
anywhere in the question through a per-language table. A count word counts
only where the tagger marks it a number, so "außer Acht" is not eight.

**Still open.** The exemption reads the cited statements, not the cited
passages, so a count only the passage states is still refused, and so is a
true count that equals the number of facts cited because each fact states one
item: see
[The written-count gate has the digit rule's blind spot](#the-written-count-gate-has-the-digit-rules-blind-spot).

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

**Still open, and worse since v0.3.0.** The question-subtraction rule, part
(d) of the fix, is deferred, so a sound comparison whose axis only the
question names is still refused; those are pinned as expected failures. Since
v0.3.0 an opening such as "Wie unterscheiden" also sends a question written
for another kind to this gate. On the v0.3.0 rebuild 52 of the 62 `wrong_type`
refusals of comparisons were wrong, 37 of them usable, against 18 of 70 on the
v0.2.2 rebuild; 13 of the 14 questions retyped to the gate by their opening
were refused wrongly. A reading of the two sides by order and parallel
structure was measured and held back; see *Deferred or low* under
[Found on the v0.3.0 rebuild](#found-on-the-v030-rebuild-of-2026-10-16).

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
A two-item answer that carries no verb and separates its items by a comma or a
semicolon, given to a type that asks for a list first, is read as a list. A
pair joined only by *and* or *und* is still read as a value: 8 accepted keys
on the v0.3.0 rebuild, such as question 3402, because the split holds no
per-language conjunction. **Still open:** a check of the item count against an
enumerated passage waits for re-extracted facts, because until then the
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
(`QUESTIONS_MEETS_SHARE`), so many deals now offer one passage. On the v0.3.0
rebuild a hand review of all 183 accepted questions citing two or more
passages found 33 welded (18%; German 19 of 102, English 14 of 81), against
128 of 270 before, and 17 of the 91 released; see
[After the fixes](#after-the-fixes). A share of likeness cannot separate two
rules on one subject; see
[Two subjects welded under one question word](#two-subjects-welded-under-one-question-word).

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

**Changed in v0.2.2**, in [`service.py`](../backend/question_generation/service.py)
and [`gates.py`](../backend/question_generation/gates.py). A reason slot, and
a reason follow-up turn, prefer facts whose evidence states a purpose,
read per language as lemmas and tokens ("so that", "in order to", "um … zu",
"damit"). Where the topic states none, the slot becomes another kind, and
the swap is logged. A language with no marker table is not filtered.

**Still open.** The filter passes a fact when a purpose marker appears
anywhere in its cited evidence, so a rule whose evidence states a purpose for
something else still gets a reason slot, and its key restates the rule. On the
v0.3.0 rebuild 29 of the 62 accepted answerable reason questions and 20 of the
34 released ones have a circular key; 23 of the 29 rest on evidence the
markers pass. A bar on a reason key's new words was measured and held back;
see *Deferred or low* under
[Found on the v0.3.0 rebuild](#found-on-the-v030-rebuild-of-2026-10-16).

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

**Still open in part.** The budget move holds, but lead-ins lost from their
lists did not fall (32 passages tagged on both rebuilds), and v0.3.0's join of
a sentence cut at a page recreated one budget cut (passage 1755 into 1756).
Only a paragraph ending in a colon is taken for a lead-in, and since v0.4.4
a list item ending in one, as a page join can leave it, which heads the list
after it.

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

**Still open in part.** A key written as a sentence echoes the question around
a one-word answer and adds too few new words: on the v0.3.0 rebuild 9 of the
24 `restates_question` refusals were wrong, 8 of them usable (questions 3376,
3884, 4257).

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

**Fixed further in v0.3.4**, in the same files. The round trip asked the
verifier to give back what only the writer had been shown. A name the
question carries, or every heading trail of the cited passages, no longer
has to come back, unless the recovery names another; a lemma only the
headings carry, every one of them, is not looked for; and a lemma comes
back under an adjective or an adverb, as German predicative adjectives are
tagged, where no negation denies it. Every trail, because two passages
under two products' headings let a key pin one product's figure on the
other; and a heading excuses nothing where the recovery holds a content
word the key and the question lack, because `a debit card and a
Mastercard` under a `Visa` heading is not `a Visa card and a Mastercard`.
On the v0.3.0 rows this passes 7 wrong `not_recoverable` refusals and loses
no right one; 5 are accepted, all usable, and 2 are then refused as near
twins of those. Figures stay strict, and a key's `one` is never met by an
indefinite article, because `a debit card for each account holder` is not
`one debit card`.

**Still open.** The English nominalisation is fixed, but a German derivation
("eine Verwarnung" against "verwarnt", question 3865), a unit abbreviation and
a list key still fail: on the v0.3.0 rebuild 74 of the 105 `not_recoverable`
refusals were wrong, 57 of them usable, against 38 of 125 (29 usable) on the
v0.2.2 rebuild, and the v0.3.4 change frees 7 of the 74. Also open:
`answer_incomplete` on terse keys, and German names `de_core_news_md` does not
tag as proper nouns, which `Visa` is not, so a German key naming the wrong
card is still read as naming none.

## An embedded question word read as a second question

`compound` counted every question word, so "differ in where" or "Wovon hängt
ab, wann" read as two questions. 11 of its 39 rejections were wrong, 5 of
them usable.

**Fixed in v0.2.2**, in [`gates.py`](../backend/question_generation/gates.py).
A further question word counts as a second question only after a
coordinating conjunction. **Trade-off:** a comma splice with no conjunction
("Wann ist sie fällig, wie viel kostet sie?") now passes as one question.

**Fixed further in v0.3.4.** `de_core_news_md` tags some German question
words, `Worauf` and `Woran`, as pronominal adverbs, so "Worauf ..., und was
...?" read as one question. `compound` now reads the closed class of
`wo(r)` and a preposition as question words through a per-language table.
On the v0.3.0 rows this moves one question, already refused as
`answer_incomplete`, to `compound`, and changes no accepted one.

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

**Still open in part.** A verb-first condition or a gerund puts the noun and
the pronoun in one clause, so the antecedent is not read: on the v0.3.0
rebuild 21 of the 77 wrong `unresolved_reference` refusals are pronouns whose
antecedent stands earlier in the same statement (facts 12853, 12098, 13931).
Readings that resolved them were built for v0.3.3 and withdrawn, because on
bank and shop text they also resolved pronouns no reader could; see *Deferred
or low* under
[Found on the v0.3.0 rebuild](#found-on-the-v030-rebuild-of-2026-10-16).

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
unchanged where the verifier found a recovery that fell short.

**Fixed in v0.3.4 where the verifier found nothing.** A key the verifier
read as not in the passages is refused, not rescued: that reading saw the
question, and the rescue reads the bare key. On the v0.3.0 rows this
refuses 9 accepted questions, 1 of them usable.

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

**Narrowed in v0.3.0 and v0.3.6; still open.** The labels were mostly text the
page clips out of view. v0.3.0's parser dropped a clipped word only when none
of its characters lay on a visible one, so a hidden label printed under the
visible label of the other language was kept: the v0.3.0 rebuild holds 17
passages tagged with diagram labels and 10 with clipped text, only 1 of the 14
label passages of the v0.2.2 rebuild is clean, and 6 released questions cite
passages that still carry hidden labels. Since v0.3.6 a clipped character
counts as shown only where the visible page has the same character in the same
place, so a hidden label over a visible one is dropped too; replayed on the
stored v0.3.0 data, that changes 13 passages (see *Fixed in v0.3.6* under
[Found on the v0.3.0 rebuild](#found-on-the-v030-rebuild-of-2026-10-16)). A
label printed in view is still body text.

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

## Found by the finalize review of 2026-10-21

A third review went through every open item at v0.4.2 before the next feature work began. Nine checkers, one for each area of the code, took the 269 items that were open: every item of the backlog, the 57 rows of the v0.4 fix ledger that were not fixed, the 116 entries of the QA review's finders, 18 logged variants of earlier bugs, and the variants that the checkers found while they worked. Each checker either wrote a failing test or printed a reproduction for every item, on bank and shop rows in German and English where the item allowed it. The items ended in five states: 177 confirmed, 66 already fixed (the commit that fixed each is named in the register), 8 refuted, 8 wrongly stated (the item was real but described wrongly, and its correction is recorded) and 10 transferred to the work on the DataMorgana paper's features, which owns them. The confirmed items were cut into three releases: v0.4.3 for everything that decides which questions are planned, written, accepted and released, v0.4.4 for reading documents, and v0.4.5 for the API, the frontend and what a whole-project QA pass finds. Every item is either in one of those releases or deferred below with its reason. A change that a replay on stored rows could judge was held to a bar written before it was measured: a loosening of a gate had to admit rows about as usable as the accepted pool, and a tightening had to refuse at most 35% usable rows. Where the replay failed its bar, the change was tried once, and was then taken out of the release and listed under *Tried in v0.4.3 and withdrawn*. The full record of each item, with its evidence, reproduction and red test, is the register that the finalize session keeps beside its plan.

### Fixed in v0.4.3: questions

The Measured column says what was measured. "Red tests" means tests that failed on v0.4.2 and pass now. "The scoreboard" is the offline replay of the labelled v0.3.0 snapshot; at the tip of this stack, before the prompt changes (which it cannot replay), it holds the facts unchanged (2,776 of 3,199 validated facts stated correctly, as before) and moves the accepted question pool by one row (879 to 878: a German row newly refused as `not_recoverable`), with answerable keys correct 0.8111 to 0.8108 and complete 0.7264 to 0.7259. Rows whose figure comes from a calibration with a model read "calibration: see docs/measurements.md".

| Defect | Found | Fix | Measured |
|---|---|---|---|
| **Planning** | | | |
| A compound slot planned hard kept the band hard, though a compound question is always banded medium (QAB-qg-plan-2, BL-D1) | the planner gave the slot the band of its type, so `planned_met` missed slots that could never meet it | a compound slot is planned at the medium band its kind fixes, and a declined slot written as another type takes the band its kept shape reaches (NEW-qg-plan-2, BL-B19) ([`planning.py`](../backend/question_generation/planning.py)) | red tests |
| A follow-up on a compound pair was stored `needs_both` (QAB-qg-plan-8) | every follow-up resting on two passages was stored `needs_both`, whatever its root's kind, so it was counted as a weld and given the `needs_both` read | a follow-up is stored `needs_both` only where its root was dealt `needs_both` ([`service.py`](../backend/question_generation/service.py)) | red tests |
| A compound partner's facts were ranked toward the head, and one whose closest fact was a bridge offered nothing (QAB-qg-plan-7, NEW-qg-plan-1) | the partner was ranked by closeness to the head, the opposite of what a compound slot wants, and a bridge near the head displaced the claim its passage was dealt for, so the slot was written single and the partner's round was spent | a compound partner offers its own facts in its own order ([`selection.py`](../backend/question_generation/selection.py)) | red tests |
| A second passage offered a word-for-word copy of a fact already offered, and a compound partner could copy the head (FIX-R103, QAB-qg-plan-3) | two editions of one clause both reached the writer, which welded them | no second passage offers a word-for-word copy of an offered fact, and a compound partner is never a copy of the head; a rule that differs by a verb, a negation or a preposition is still offered | red tests |
| A two-passage reading could hold nine facts, past its ceiling of eight (QAB-qg-plan-10) | the head's whole list was taken before the later passages were given room | each later passage is left room under the ceiling before the head's list is filled | red tests |
| The questions README said an unset `QUESTIONS_KIND_MIX` deals every spanning slot `needs_both` (QAB-qg-plan-11) | the default has been `needs_both:5,compound:1` since v0.3.26 | the README says so ([`README.md`](../backend/question_generation/README.md)) | read against the code |
| A premise's own *When*, or a *which* or *wo* opening a relative clause in it, typed the question (NEW-qg-plan-3, NEW-qg-plan-4, BL-B18) | the type rules read the first question word, wherever it stood | a question opening on a premise is typed by the question word that asks: the first one outside a relative or adverbial clause, or the first one at all where the parser hangs the question under its premise ([`gates.py`](../backend/question_generation/gates.py)) | red tests |
| **Readings** | | | |
| An amount written with spaces (5 000 Euro, EUR 100 000, 1 299,99 EUR) was read as two figures, so one amount written two ways disagreed and a right total was refused (NEW-release-1) | the parse and the figure reading took the space as the end of a figure | an amount grouped by spaces is one figure where a currency code, symbol or word of the language stands beside it and no reference label (*Section*, *Abschnitt*) stands before it; a table row or a phone number keeps its separate figures ([`analysis.py`](../backend/nlp/analysis.py)) | red tests; the scoreboard moves no fact; the README names the table-row limit that remains |
| An ordinal written as a word on one side and as a figure on the other never agreed, and an explanation writing *3rd* where the passage spells *third* was refused (QAB-qg-check-6, NEW-qg-writer-gates-4) | the figure was read as the count of its digits | the ordinal tables of the language make *the third reminder*, *the 3rd reminder* and *ab der 3. Mahnung* one ordinal, never the count 3; the 5th day is not 5 days | red tests |
| A spelled ordinal past twelve (thirteenth, dreizehnten) never agreed with its figure (13th, 13.) (QA-questions-3) | the ordinal table stopped at twelve | the ordinals are composed from the cardinals in both languages; a hyphenated English ordinal (twenty-first) is still read as its last word, a limit the nlp README names | red tests |
| The pronoun *one* made a second number, so an aggregation was relabelled `factoid` (VAR-number-readings-1) | the relabelling, the numbered-source check and a range's unit each read a word spelled like a number their own way | one predicate, `is_number`, decides what a number is for all three | red tests; the reviewer's regression cases for the German count, the bare *one*, the imperative key and the passage-wide excuse are pinned as the base behaviour |
| A count of the items one cited fact lists was stored as an aggregation (FIX-R127) | the count rule looked at any cited fact that listed as many items | a count is stored as a factoid only when the fact the question asks about, the one sharing most of its content words, lists that many; nothing is refused for it ([`checker.py`](../backend/question_generation/checker.py)) | red tests |
| **Gates** | | | |
| A German keyword query typed in lower case lost every noun to the gates (BL-B2, NEW-qg-writer-gates-3) | `_foreign` read case as a language signal in a text that writes no word after its first with a capital, so the query was neither anchored nor held to its passages | a text that writes no capital after its first word says nothing by its case, so the gates read its nouns; a lower-case query that holds one capitalised word (a brand) is still read as written, which the NLP guide lists as a limit | red tests |
| An answerable question with no explanation passed (FIX-R105) | no gate required an explanation | an answerable question written without one is refused `explanation_unusable`; a stored row read without one still passes | red tests |
| With three cited passages the check kept only the passages owning a part and lost a part two others share (FIX-R169) | the cover dropped a part that only the other passages share | a question citing three or more passages keeps, besides the passages holding a part of their own, the first passage holding each part they leave uncovered | red tests |
| **The read and the writer** | | | |
| A circular reason key, the rule restated as its own reason, passed (BL-B5) | the only reason check was the overlap between the question and the verifier's recovery, and a key that restates the rule in the passage's words adds the new words the overlap counts | the round trip's read also says whether the passages give a why a reason beyond its own rule, and a question they give none is refused `not_recoverable` ([`verifier.py`](../backend/question_generation/verifier.py)); verifier prompt version 12, from 6 | on the 300 labelled spot-check rows: 19 of 22 circular reason keys refused by the read, 11 of 22 as the checker's reason branch attributes them (bar: at least half), 5 of the 19 refusals usable (26%, bar: at most 35%); calibration: see docs/measurements.md |
| A question reworded until it asked something the passage does not say was mapped back to the passage (BL-B12) | the read answered charitably | the read answers only where the passages answer the question as it is asked, and a drifted question comes back `not_recoverable` | the replays above; calibration: see docs/measurements.md |
| The aggregation prompt invited counts of the facts the writer was handed (BL-B3) | a third of aggregation slots were spent on drafts the count rule rightly refused | the prompt says a count is of the figures or items the facts state, never of the facts themselves; writer prompt version 28, from 19 ([`prompts.py`](../backend/question_generation/prompts.py)) | calibration: see docs/measurements.md |
| Questions about a case study's sample person, a phone number or a page's legend passed every gate (BL-B9, FIX-R36) | no gate refuses them | the writer is told that a person or a story in the material illustrates a rule, so it asks about the rule, and never about a page's contact box, legend or list of changes | calibration: see docs/measurements.md |
| With-premise questions opened on a label naming a setting (*Beim Spiel:*, *In football,*), and a premise could give the answer away (BL-B6, BL-B7) | the default description made the asker optional, and a quarter of accepted with-premise questions in calibration were such labels | the default with-premise category asks for a premise in which the asker states, in the first person, a fact of their own situation (something they have, did, bought or plan), never the topic, the answer wanted or that they are reading or checking something; a premise is a form of its own, never told beside a word bound or a search query (the slot is written as no category of its categorization); a premise holding no first- or second-person word in the language's own parse is written once more with a note, and is not refused, as is one whose verbs only want, try, check or understand (a per-language table read through the infinitive each takes); the asker is read off a per-language table of pronouns, and a premise joined to its question by a dash is read as a premise | Link Q: verbose with-premise rows opening on a scene label 4 of 17 against the base's 6 of 17, and conformance 13 of 17, both short of their bars; after the one iteration, a premise-only run: 0 of 36 scene labels, conformance 34 of 36 (see docs/measurements.md) |
| **Categories** | | | |
| The wording of distant-from-document, expert and long-search-query produced bad questions (BL-A-distant, BL-A-expert, BL-A-long-query) | the paper's wording swapped the terms that carry the meaning, invented insider words, and a third of long queries were written as sentences | distant keeps every term's meaning and coins no word, expert is described by what an expert asks in the material's own terms, and long-search-query is keywords with no question word and nothing about the asker ([`configuration.md`](configuration.md)) | Link C: distant passes and joins the default (next row); expert and long-search-query stay opt-in (see the withdrawn table and docs/measurements.md) |
| A search query was told on a slot that cannot be asked in keywords (BL-A-short-query) | two thirds of the short queries' wrong keys in calibration came from slots spanning two passages or asking why | a search query is not told on a slot that spans two passages or on a type whose question word is the ask (reason, comparison, implication, a change over time); the slot is written as no category of its categorization | Link C: the short query is accepted on 29 to 31% of the slots it may take, against 82 to 86% for natural phrasing there, and the long one has 36 rows, under the 40-row minimum; both stay opt-in (see docs/measurements.md) |
| distant-from-document drifted from the passage's meaning, and the default dealt no linguistic variation (BL-A-distant) | its description invited swapping the terms that carry the meaning | distant-from-document keeps every thing, party, period and action it names at the meaning the document gives it and coins no word, and the default deals Linguistic variation {similar-to-document, distant-from-document} at even odds beside Phrasing and Premise ([`config.py`](../backend/question_generation/config.py)) | Link C, within novice rows: keys correct 58 against 57 of 60, complete 57 against 54, invalid 4 against 11 per 60, conformance 48 of 60 (0.80) |
| A short search query another passage answers differently was accepted (BL-A-short-query) | its keywords drop the qualifier that tells two cases apart | a search query bounded to a few words is read once more against the passages nearest it that it does not cite, and is refused `not_recoverable` where one of them answers it differently; long queries are not read this way, because their keys passed | calibration: see docs/measurements.md |
| **Review and export** | | | |
| The quality report, the Questions page, the API and the workbook Summary did not count the kind or the categories (NEW-api-frontend-export-2) | only types, bands, levels and refusals were counted | the report counts each kind and each `categorization=category`, and the three surfaces read those counts ([`export.py`](../backend/question_generation/export.py)) | red tests |
| A question's categories reached neither its Argilla record nor the Questions page, and a keyword query was judged by a guideline written for questions put to a service desk (NEW-api-frontend-export-3) | the record carried no categories | they reach both, and the guideline says a question written as a search query is judged as a query, not rejected as malformed; the review README says a dataset made before v0.4.3 must be recreated to carry them | red tests |
| `make diversity BY=kind` printed no factoid and open-ended table (BL-B21) | only `BY=category` printed it | it prints each kind's shares and leaves out the word-bounds column that is a category's alone ([`run.py`](../backend/assessment/run.py)) | red tests |
| A control character in any exported text, a vertical tab pasted into a topic's name or an escape in a model's answer, failed the whole workbook with a 500 (QA-api-frontend-1) | openpyxl refuses those characters in a cell, and nothing removed them | they are dropped from every cell of every sheet ([`export.py`](../backend/question_generation/export.py)) | red tests |
| An untitled document was named by its whole 64-character digest on the Questions sheet and by its 12-character head on the Citations sheet (QA-api-frontend-2) | the listing and the citations named it in two ways | both name it by the head of its digest | red tests |
| The export read its rows, citations and counts in three database sessions, so a question written meanwhile was counted and cited without a row (QA-api-frontend-3) | each read opened its own session | the API and the command line read all three in one snapshot | red tests |
| The export command line took any `--question-type` and `--answer-form`, so a typo wrote an empty workbook and exited 0 (QA-api-frontend-5) | the command line took free text | it takes only the types and forms that exist and refuses a typo, as `GET /questions/export` does with a 422 | red tests |
| The configuration guide listed too few refusals of `QUESTIONS_CATEGORIZATIONS`, and diversity figures were absent from the measurements page (BL-B22) | the v0.4.2 wiki pass found the gaps | the guide lists all nine ways it is refused as the parser checks them; the measurements page now holds the v0.4.1 and v0.4.2 figures ([`configuration.md`](configuration.md), [`measurements.md`](measurements.md)) | read against the parser |
| Test runs from a checkout loaded the checkout's `.env`, model settings and secrets included, into every worker (BL-B23, NEW-assess-1) | litellm loads a `.env` of its own unless it is told it runs in production; the v0.4.2 build's accidental evaluation run most likely made billed Azure calls | `LITELLM_MODE=PRODUCTION` is set with `setdefault` in `backend/llm/__init__.py` and `tests/conftest.py` | a test pins that no run loads the checkout's `.env` |
| **The release draw** | | | |
| The release is sized by its scarcest type | a kind the pool holds few of asked for its whole share at every size, so it refused every large size and capped the release at a fraction of what was accepted | a kind short of its share beyond what `close_enough` allows is capped at the rows a release can take of it (not the spare members of twin groups, not rows in a language the release gives no weight); its places go to the other kinds by largest remainder, none taking more than its share of the size plus the tolerance, and the downward scan finds the largest size that fills under those caps ([`balance.py`](../backend/question_generation/balance.py)) | over 100 paired salts on the labelled v0.3.0 snapshot (replay of the whole v0.4.3 stack, below): mean release size 371.1 to 453.3 rows, larger on every salt |
| The release draw overshoots its quotas with follow-up questions | a thread was drawn whole, each turn counted after the fact, so a kind ended past its quota and the others short | a thread ends at the first turn whose band, kind or language has no place left, the test a root passes, and the turns after it go with it | the same replay: welded share of released two-passage rows 22.72% to 22.77% (+0.06 points; 95% interval -0.32 to +0.47 over the 100 salts), invalid per 100 released 3.30 to 3.03 (-0.26; interval -0.35 to -0.18) |
| The release handed back could hold twins the verifier never judged (FIX-R3) | the draw made after the last twin round was returned without being read for twins, and a twin found in the last round dropped the question and its follow-up | the draw after the last twin round is read for twins once more, and the last round drops the later-ranked member of each pair it finds, with its thread, instead of keeping known twins | red tests; the same replay |
| `docs/bugs.md` still listed the release's halving size search as deferred (NEW-release-2) | the downward scan shipped in v0.3.27 | the entry says so | read against the code |

The replay of the release draw ran the draw of the base (v0.4.2) and the draw of this stack over the same 100 hash salts of the labelled v0.3.0 snapshot, where every released row carries a reviewer's label. Over the 100 salts the mean release grew from 371.1 to 453.3 rows (82.2 more on average, 14 to 139 more on every salt), the mean number of two-passage rows from 95.8 to 124.2, the welded share of released two-passage rows stayed at 22.7%, invalid rows per 100 released fell from 3.30 to 3.03, and the usable share of the release moved from 0.786 to 0.781. The bars, written before the run, were a welded share at most 0.005 above the base and invalid rows per 100 at most 0.5 above it. Both hold.

### Tried in v0.4.3 and withdrawn, with the reason

| Item | What was tried, and what withdrew it |
|---|---|
| A topic's finished threads kept on an outage (FIX-R88) | The retry writes the topic's full plan again, with the same seed and no record of which slots are stored, so it duplicates questions. The honest fix needs a slot index on the stored question. The base behaviour, which discards the topic and fails it so the retry rewrites it, writes no duplicates |
| A spelled count validated where its value appears anywhere in the passage, and German count words read as units (FIX-R164, QAB-llm-nlp-12) | The first change validated wrong counts ("costs four euros" beside "four account models"). The second refused correct facts on the scoreboard ("zwei Verwarnungen" against "zweimal verwarnt"): 2 of the 3 newly refused facts were correct, against the 35% a tightening may refuse. It needs a reading of the count in its own sentence |
| Only clause-heading verbs allowed in a key (NEW-qg-writer-gates-6) | A bare English noun phrase ("return shipping") and an imperative ("Sign the contract") parse alike, and the copular frame tried turned imperatives into values |
| A table of pronoun numerals so that *one* is never a number (VAR-one-same-price) | It dropped real counts ("at most one", "one per customer") |
| A key naming part of a list read as incomplete when its question asks for a set (FIX-R24) | One try on the labelled snapshot (24 of 300 incomplete): it newly refused 3 German rows as incomplete, 2 of them usable (67%, bar at most 35%) |
| A table of the writer prompt's own labels, and a check that a question names no person its passages lack (BL-B8, NEW-qg-writer-gates-5, FIX-R38) | The label table newly refused 3 accepted rows on the labelled snapshot, 2 of them usable ("The facts of a match" is the corpus's own wording), and read everyday text as a label ("die Passage" as a shopping arcade). The person check refused an asker who names themselves in a premise, which the with-premise category invites. The writer prompt line of BL-B9 addresses personas instead |
| An `asks_one` field on the round trip's read, refusing a question that asks two things under one question word (BL-B11, FIX-R123, BL-B4) | Replayed on the 300 labelled spot-check rows (35 labelled welds, 26 of them reached by the read): the first version refused 3 rows and caught 2 of 35 welds; its one iteration refused 16 and caught 8 of 35, with half of its refusals usable (8 of 16). The bars were at least half of the welds and at most 35% usable. It was taken out and the writer prompts went back to version 27. Welds need the writer not to weld, or a reading of their own with their own calibration |
| A title that names its page's subject left to the phrasing judge instead of the free title rule, with the writer line that allowed naming it (BL-B1, NEW-qg-writer-gates-1, NEW-qg-writer-gates-2) | Replayed on the ten link databases, the change cut the free rule's wrong refusals from 79 to 1. Of the 60 rows it admitted, the 31 that also pass the later gates held 21 usable (0.68, against 0.50 in Link Q's base arm) and 6 invalid (11.6 per 60), against the loosening bar's 2 and the floor rule's 5. None is invalid for naming its title: they are welded sums, a case-study person, incomplete keys and a key the question gives away |
| A space-grouped amount read as one figure wherever a figure is read, beside a currency word carrying a mark or a price dash too (QA-questions-1, QA-questions-4) | Three review rounds each found a case where the reading got worse than v0.4.2's: a price dash glued to the currency dropped the amount, a count of notes (*3 500-Euro-Scheine*) merged into one figure, and then a right explanation was refused, because a claim's figures and a passage's figures are read by two readers that fold the amount differently (*100 000,- EUR*; a passage writing the amount with a no-break space). Fixing it means one reader for both sides. Until then a wrong space-grouped amount in an explanation is not caught by the explanation check, as in v0.4.2 |
| The expert and the two search-query categories in the default (BL-A-expert, BL-A-short-query, BL-A-long-query) | Link C: expert's conformance was 0.59 (34 of 58) and its invalid rows 13.4 per 60 against a bound of 13.0, because told on a slot whose fact is basic the writer asks a basic question in an expert's voice; the short query is accepted on 29 to 31% of its slots against 82 to 86% for natural phrasing; the long query has 36 rows, too few to measure. All three stay definable through `QUESTIONS_CATEGORIZATIONS` |

### Fixed in v0.4.4: parsing and chunking

v0.4.4 changes how documents are read: parsing, chunking, the NLP readings that only fact validation calls, extraction, topics, the archive and operations. It changes no question code and no NLP function a gate reaches. The Measured column reads as in v0.4.3's tables, and the bars and their figures are in [docs/measurements.md](measurements.md#the-v044-bars). The parse bar parsed and chunked three real documents, a two-page German PDF of the football corpus and two Your Europe pages of four and eight pages, in process and into a temporary folder, with the base code and with these fixes: the converted documents and all 25 passages came out byte-identical. None of the three holds an instance of any row below, so each rests on its red tests. A stored passage changes only through `make parse-rerun` and `make chunk-rerun`.

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A scanned page carrying one stamped line, a merge tool's `Seite 2 von 3` or an annex mark, was not named, so its text went missing without a warning (NEW-parse-chunk-2) | a page holding any character at all was taken for a text page | a page holding no more than `PARSING_OCR_CHAR_THRESHOLD` characters (100 by default) under pictures covering at least half of it is named as image-only, in the parse warning, the stored parse's metadata and `documents.parse_error` ([`pdf.py`](../backend/preprocessing/parsing/pipelines/pdf.py)) | red tests |
| Bidi marks, isolates and C1 controls survived the mend, so a model's quote of an isolated phone number or an opening-hours range matched nothing in the passage (QAB-preprocessing-10) | the mend dropped the C0 controls and five zero-width marks only | every format character is dropped, and a C1 control is read as the cp1252 character it stands for (`U+0096` as an en dash), the five that cp1252 leaves unassigned dropped | red tests |
| A table label wrapped over three lines lost its last line to the next row's label, or left a row with no price (VAR-parse-text-1) | each tail was compared with the row directly above it, which the first join had already emptied | each tail joins the nearest row still standing, so the label is joined line after line | red tests |
| A body line opening with the running foot's name, an imprint or a contact line, was moved to the furniture layer whole (QAB-preprocessing-7) | the check compared only a paragraph's leading fields with a running head or foot, so whatever followed them went too | a paragraph is furniture only when it is the running head or foot itself, page numbers allowed after it; a line that goes on past the foot's name stays passage text ([`furniture.py`](../backend/preprocessing/chunking/furniture.py)) | red tests; the chunking README names the limit that remains: the foot's name followed by a bare phone number reads as the foot with a page number |
| A lone integer anywhere on a page was dropped as a page number, so a value printed beside or under its label, a notice period or a return window, was lost (VAR-chunk-structure-1) | every bare integer alone in its paragraph was read as a page number, with no check of where it stands | a lone integer is a page number only in the top or bottom tenth of its page; where the document's running page numbers show an offset, only when it equals its page's number plus that offset; and where they show none, not right after a block ending on a lead-in's colon. An integer whose item has no position stays text | red tests |
| A sentence cut at a page or column break before a capitalised word, a German noun or an English name, stayed two half sentences (FIX-R101) | the join needed the rest to open in lower case | a rest opening in capitals joins too where the language's tagger reads the first block as ending on an article, a preposition, a conjunction or an auxiliary and the second as opening with a noun (a proper noun only, in a language `NLP_CAPITALISED_NOUNS` does not name). An adjective is not among those words, since a list item or a tagline can end on one (`Kreditkarte für Neukunden gratis`). A script without case joins by the tags alone | red tests |
| Text above a mid-page chapter opening was filed under the new chapter where the chapter's heading is spelled unlike its running head, with a letter prefix (`B. Geschäftskunden`) or a mark of its own (`Kapitel B:`) (NEW-parse-chunk-3) | the heading had to equal a running-head field with only spaces removed | headings and running-head fields are compared on their letters and digits, and either may hold the other | red tests |
| A lead-in that a page join leaves at the end of a list item (`bestehen, wenn:`) reached none of the list's pieces (FIX-R100) | only a paragraph ending in a colon was taken for a lead-in | a list item ending on a colon is a lead-in too: it stays where it is and heads the list after it through the heading trail ([`passages.py`](../backend/preprocessing/chunking/passages.py)). The other half of the item, a lead-in the converter labels a heading, was withdrawn (see below) | red tests |
| A heading holding ` > ` (`Orders > 50 EUR`) was split in two by every reader of the section path (QAB-preprocessing-8) | the trail is joined with ` > `, and the link pass, the table extractor, fact validation and the heading check split it there | a ` > ` inside a heading is written ` › `, and `headings_of` in [`database/qa_generator/passages.py`](../backend/database/qa_generator/passages.py) reads the path back with each heading as printed; the link pass keys a section's parent through the same writer. A stored path keeps its old form until its document is chunked again | red tests |
| A footnote the converter attaches to a picture, an offer's conditions under a banner, reached no passage (NEW-parse-chunk-4) | only the table serializer wrote footnotes | a picture's footnotes are written beneath its caption, as a table's are; the text nested inside a picture still stays out (deferred below) | red tests |
| A list in two languages under one heading became one passage, read and filed as one language (NEW-parse-chunk-5) | only paragraphs were read for their language when a chunk is cut | list items are read too, so a run of items that changes language ends the chunk as prose does, each item keeping its marker | red tests; the chunking README names a German item heavy with English words, which can cut its list, as a limit |
<!-- QA v0.4.4: parse-chunk -->

### Fixed in v0.4.4: fact validation, extraction and the link pass

"The facts replay" is the scoreboard's facts section: the labelled v0.3.0 snapshot judged by v0.4.3's code and by this stack's. Of the 3,445 facts it replays, 3 change verdict, all German and all newly refused by the modifier tables below; no fact is newly validated and no bridge's verdict moves. "The second facts replay" judged the same snapshot with this stack's code before and after the rows marked QA-extraction, each stored passage's sentences cut again by the code judging it: the cuts of 1 of its 820 passages move, and one fact refused before validates, correct. "The link replay" ran each code's unscoped bridge pass in process over read-only copies of the two frozen calibration bases, answering each dealt link with the bridge stored on it, so no model was called.

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A sentence ended after an abbreviation that never closes one, `incl.` before `VAT` or `cf.` before `Section 4` (QAB-llm-nlp-3), and after a clause, limit or weekday abbreviation the table lacked, `Art.`, `Ziff.`, `max.`, `mtl.` or `Mo.–Fr.` (QAB-preprocessing-3) | the parser's cut after a listed abbreviation was dropped only before a lower-case word or a figure, and the per-language table held no clause, limit or weekday abbreviation | the table is split in two ([`analysis.py`](../backend/nlp/analysis.py)): `_ABBREVIATIONS` holds those that end no sentence on their line whatever follows (`incl.`, `cf.`, `inkl.`, `zzgl.`, `gem.`, `Ziff.`, `Abschn.`), and `_CLOSING_ABBREVIATIONS` those that may end one and end none before a lower-case word or a figure (`etc.`, `No.`, `Art.`, `max.`, the weekdays). A range or a hyphenated compound is read by its last part, so `Mo.–Fr. 8–18 Uhr` is one sentence and `Ihre Kunden-Nr. Die Bank prüft ...` is still two | red tests, among them a regression test on stored passages; a stored passage takes it only through `make chunk-rerun` |
| A German fact opening on polite *Sie* was refused `unresolved_reference` where only its passage, not the fact, showed the polite address: 19 German facts of the shop calibration base (NEW-extract-nlp-1) | an opening *Sie* counted as polite only when another polite form followed inside the statement itself | the fact check passes the cited passages to the reading, and an opening *Sie* names the reader where a passage holds a polite form inside a sentence (`Bitte geben Sie Ihre IBAN an`), unless a sentence there opens on *Sie* after one whose subject is plural (`Händler werben neue Kunden. Sie erhalten eine Provision.`). The question gates pass no passage and read as before | red tests; the facts replay moves no verdict |
| A fact pointing outside through a modifier of its opening noun, *such a card*, *eine solche Karte*, *the aforementioned card* or a plural *the following fees*, was validated (VAR-bridge-prompt8-1) | the opening check read pronouns and demonstrative determiners only; 1.4% (Laws) and 2.2% (shop) of the bases' validated facts carry such a word, an upper bound | two tables of the fact side's own, `_ANAPHORIC_MODIFIERS` and `_CATAPHORIC_MODIFIERS` (not the question side's `_ANAPHORIC`), are read on a noun before the first finite verb, as an opening demonstrative is. A plural *following* is spared where a figure counts its noun (*the following 12 months*) or the statement lists its items after a colon; a singular one means the next one (*am folgenden Tag*) and stands alone | the facts replay: 3 German facts newly refused, labelled blind: all 3 vague and the refusal right, so 0 of 3 correct against a tightening bar of at most 35%; the READMEs name the limit that a figure or a colon spares a list given elsewhere (*The following fees apply: see the price list.*) |
| A German *dies* after a free relative clause, *Wer die Karte verliert, muss dies sofort melden*, was refused (VAR-dies-free-relative) | the parser hangs the *wer* clause's verb on the main verb as its subject, so it sat in the main clause and *dies* found no clause to stand for | a finite verb standing as its head's subject or object, with a question word under it, is a clause *dies* may stand for, as a *wenn* clause is; *dies* after a relative clause on a noun, or alone, is still refused | red tests; the facts replay moves no verdict; the NLP README names as a limit that *dies* naming a thing after such a clause (*Wer ein Konto eröffnet, erhält dies per Post.*) is read as resolved, pinned as a strict expected failure |
| A pass of `make extract-bridge` narrowed by `TOPIC`, `SHA` or `PASSAGE` deleted a sibling or term bridge headed from outside its scope and never wrote it back, and `MISSING=1` asked the model again in a topic whose passages already headed a bridge (NEW-extract-nlp-3) | a sibling or term link stores its earlier passage first whichever passage headed it, and the clear and `MISSING=1` read the first passage as the head | a bridge's reading in `facts.bridge` records the passage that headed its link (`head`); a narrowed pass clears only the bridges headed in its scope, and `MISSING=1` counts the head's topic as bridged. A bridge written before this reads as headed by the passage it shows first ([`repository.py`](../backend/extraction/repository.py), [`service.py`](../backend/extraction/service.py)) | red tests, among them the bridge-scope property tests; the link replay writes the stored bridges unchanged apart from the head (on the shop base 26 of 37 heads are the first passage and 11 the second) |
| A hold on pairs the link pass would not offer still changed what it dealt, so a `MISSING=1` or narrowed pass dealt other links than a fresh one (FIX-R168) | the held pairs were taken out of each head's choices before the topic's quota was strided | the pass deals and strides as if nothing were held, and then moves only a dealt link on a held pair to its head's next free link ([`links.py`](../backend/extraction/links.py)) | the property test that was an expected failure passes at 200 and 1,000 examples and is no longer marked; the link replay deals the same links in the same order as the base on both bases (204 and 109) |
| The bridge check missed a passage's numbered heading named second in a list, *Sections 7 and 9* under *Section 9* (NEW-extract-nlp-2) | the check read only the number right after the label word, while the link pass read the whole list | one reader, `numbered` in [`validation.py`](../backend/extraction/validation.py), serves both; after a singular label word a joined number that counts what follows it (*Under Section 7, 3 transfers a month are free*) is no section, while *Sections 7 and 3* names both | red tests; the extraction README names the limit that a document name after a joined number hides it (*Ziffer 4 und 5 AGB*) |
| A single-quoted heading ending in a possessive, *‘Customers’ fees’*, was cut at the apostrophe and linked to nothing (VAR-link-references-1) | an apostrophe before a space closed the quoted span | a single-quoted span is read on to a later closing mark on its line where that longer span is a heading; every other quoted span reads as before | red tests |
| The bridge relation names were spelled in several places that tests tied only in part, and the LLM README said the question checker reads the table (BL-C3, QAB-llm-nlp-10) | the prompt's FORMAT line and the answer schema copied the names of [`llm/spans.py`](../backend/llm/spans.py), and its `RelationName` had no reader | both read the names off the one table, so a relation added there is one the model is offered and may answer; the prompt and the schema stay byte-identical (bridge prompt 6 unchanged), `RelationName` goes, the table's test pins the `facts` CHECK instead of a frozen migration, and the README says only the bridge pass reads the table | red tests; the bridge prompt's pinned digest is unchanged |
| A figure ending a German sentence, `EUR 5.`, `Ziffer 3.` or `Kapitel 2.`, opened the next sentence as if it numbered an item, so a fact citing the sentence lacked its figure and was refused `unsupported_addition` (QA-extraction-1) | the parser cuts such a sentence before the figure and after it, the cut before a figure on its line was kept, and the item rule read the line off the parser's span, which held the figure alone | a figure on its line after a word or an abbreviation finishes its sentence, and an item's number is read off the sentence built so far, so only a number opening its line numbers an item ([`analysis.py`](../backend/nlp/analysis.py)). A stored passage takes this only through a re-chunk | red tests; the second facts replay: the cuts of 1 of 820 passages move, and a fact on the goal line's minimum length, refused before, validates and is correct. Limit: where the parser leaves no cut after the figure, two sentences are read as one (*Fees are listed in Sect. 4. Section 5 lists the limits.*), which still keeps the figure in its sentence |
| An abbreviation the tables list still ended a sentence after an opening bracket or quote, `(cf. Section 4)` or `"incl. VAT"` (QA-extraction-2) | the word looked up kept the mark before it, so `(cf.` was in neither table | a word's leading marks are stripped before the tables are read. A stored passage takes this only through a re-chunk | red tests; no passage of the snapshot holds a case |
| A price abbreviation ended a sentence before a lower-case word where the tables lacked it or a slash hid it, `2.5% p.a. on all balances` or `5 EUR/Mon. zzgl. MwSt.` (QA-extraction-3) | English had no `p.a.` and German no `mon.`, and a word was split only on a dash to find the abbreviation it ends on | `p.a.` and `mon.` are closing abbreviations, and a word joined by a slash ends on its last abbreviation, as a dashed one does. A stored passage takes this only through a re-chunk | red tests; no passage of the snapshot holds a case |
| A German fact opening on a pointing modifier the lemmatizer leaves inflected, *Nachstehende Bedingungen*, *Besagter Kunde* or *Obengenannte Gebühren*, was validated (QA-extraction-5) | the tables were matched against the lemma and the word as written, the lemmatizer leaves a capitalised opening adjective as written, and *Obengenannte* is parsed as its noun's head | the tables are read with the language's adjective endings stripped as well (`_ADJECTIVE_ENDINGS`, German only), and an adjective the parser made its noun's head modifies that noun; a preposition opening a fact, or a word heading its object there (*Above EUR 500,*, *Following the update,*), points nowhere whatever the tagger made its head | red tests; the second facts replay moves no verdict |
| A fact opening on a back-pointing modifier no table held, *the above fees*, *the said card*, *die vorstehenden Bedingungen* or *die oben genannten Gebühren* written apart, was validated (QA-extraction-6) | the table held no `vorstehend`, `above` or `said`, and read each word alone | the three join the table; a modifier is also read joined to the word before it (`oben genannt`, `above-mentioned`), and only before its noun, so *Withdrawals above EUR 500* and the first part of a compound (*above-average*) point nowhere. A bare `genannt` stays out, since *die im Preisverzeichnis genannten Gebühren* says where to look | red tests; the second facts replay moves no verdict |
| A fee table whose amounts carry a currency code, `EUR 5`, `GBP 12.00` or `CHF 10`, was skipped whole as a grid of identifiers, though the extraction README says a fee table is read (QA-extraction-7) | letters, a space and digits read as a code like `TM-2.2.1`, and a table whose filled cells are more than half codes is skipped | a cell whose letters are a currency word of its language's `AMOUNT_WORDS` is a value, as a bare figure is ([`service.py`](../backend/extraction/service.py)). A passage skipped before was marked read, so only `make extract-rerun` reads it | red tests; no passage of the snapshot is skipped differently. Limit: a language with no `AMOUNT_WORDS` row, French or Spanish, still skips such a table |
| A section number with its subsection glued on, `Section 7(2)` or `§ 7(2) AGB`, named no section, so the link pass offered no reference and the bridge check read no heading (QA-extraction-8) | the tokenizer keeps `7(2` as one token, and the reader took only a token that is a number whole | a token opening on a section number before a bracket names that section, for the link pass and the bridge check alike ([`validation.py`](../backend/extraction/validation.py)) | red tests; the second facts replay moves no bridge verdict (it does not replay which links are dealt) |

### Fixed in v0.4.4: topics

"The topics replay" fitted both frozen calibration bases' passages in process with each code, without naming them and with no store write: no language fails, every topic count and every topic's top terms are the base's, and 5 of the 1,150 passages placed change their main topic, all of them from the reseed in the first row.

| Defect | Found | Fix | Measured |
|---|---|---|---|
| Two identical passages could get different topic memberships (QAB-topics-3) | each passage was scored on the model's one random generator, which the projection draws from on every call, so a passage's weights depended on how many passages were scored before it | the fit reseeds the projection for each passage, so its weights depend on its vector alone ([`topics.py`](../backend/topic_modelling/topics.py)) | red tests; the topics replay: 5 of 1,150 passages change their main topic, none without this fix |
| A language with one passage, or only copies of one text, failed every fit, its facts reached no question unit, and the error advised a setting that cannot help (NEW-topics-2) | the frequency filter or tf-idf leaves no term that tells such passages apart, and the fit raised `NoVocabulary` | a language whose passages are one text, however many copies, gets one topic holding them, its most frequent lemmas as terms, and so does one whose passages the filter or tf-idf cannot tell apart while it is too small for a second topic by `TOPIC_PASSAGES_PER_TOPIC`; a larger language the filter empties still raises `NoVocabulary`, naming `TOPIC_NO_BELOW` and `TOPIC_NO_ABOVE` | red tests; the topics replay: no language fails |
| A topic dominant in no passage was sent to the naming model with no excerpt, while `TOPIC_LABEL_MIN_FACT_SHARE` could never fire (QAB-topics-4, FIX-R96, FIX-R104) | the fit reads only fact-bearing passages, so every topic's share of them is one, and the guard never saw a topic no passage holds most strongly | a topic is named only where it is some passage's strongest; `TOPIC_LABEL_MIN_FACT_SHARE` and the unused `label()` are deleted ([`service.py`](../backend/topic_modelling/service.py)) | red tests |
| The naming model's "no subject" answer was recognised only as the words *Mixed* and *gemischt* (NEW-topics-3) | the refusal was a two-language word list, while the model writes in the corpus's language | the answer carries a `no_subject` field the model sets, in any language; topics prompt version 3, from 2 ([`labels.py`](../backend/topic_modelling/labels.py)) | red tests; the prompt's pin |
| The ending most topic names share was stripped even where that left a dangling preposition (*Fees for*) or a lone modifier (*Debit*) (NEW-topics-1) | any two- or three-word ending more than half the names share was taken off | an ending is taken off only when it is a prepositional phrase, its first word tagged as an adposition by the language's pipeline (*im Fussball*, *in banking*) | red tests |
| Topic figures and models were keyed by language alone, so a second database on the same object store overwrote and archived production's on its fit or delete (NEW-topics-5) | the keys `topics/<language>.html` and `.npz` named no database | both are stored under `topics/<database>/<language>`, the database read from the path of `DATABASE_URL`, and a `DATABASE_URL` that names no database is refused, naming the variable. The old key is not read, so an upgraded database runs `make topics-discover` again ([`bucket.py`](../backend/blob_store/s3/bucket.py)) | red tests |
| A refit after a language's last document went left that language's figure and model in the store, and the figure route served topics that were gone (QAB-topics-5) | a fit archived and drew only the languages it fitted | the languages whose topics a refit deletes are read before it, and their figure and model are archived | red tests |
| A word holding a closing script tag, kept whole as a lemma from an uploaded document, ended the topic map's data script (QA-security-1) | pyLDAvis writes its data unescaped into a script block, and the vocabulary is lemmas of uploaded text | the page writes the data with `<`, `>` and `&` as JSON escapes, so the figure draws the same terms and nothing in it is markup ([`visualisation.py`](../backend/topic_modelling/visualisation.py)) | red tests |
| The Topics page, the `PATCH /topics` schema and two column comments described the top-term carry of before v0.3.7 and an unread centroid, and the page's help said a passage above no floor stays unplaced and named the dead setting (QAB-topics-7, NEW-topics-4) | the behaviour changed in v0.3.7 and later and these texts did not | they describe the passage-majority rule: a person's name and coverage choice go to the new topic holding most of the same passages, a model's name is given again, and a passage above no floor joins its nearest topic where it has a vector; the two comments change in the comment-only revision below | a page test; read against the code |
| After a refit, stored questions kept the topic scope and difficulty band of the old fit, and no document said to rescore them (QAB-topics-6) | re-verify skips the topic scope by design, and the guides kept `questions-rescore` for the v0.2.2 upgrade | the topics README and the make guide say that after a refit that changed the topics, `make questions-reverify` and then `make questions-rescore` bring them up to date | read against the code |
| The topics README said the fixed seed gives the same topics for the same corpus, while the same passages read in another order can give other topics (QA-topics-1) | the fit reads passages by id, and its vocabulary and factorisation follow that order: 200 synthetic English bank passages read in a shuffled order took main topics agreeing with the first fit at an adjusted Rand index of 0.82 | the README and `TOPIC_RANDOM_STATE`'s comment say the same passages read in the same order give the same topics, and that a document deleted and chunked again (`make delete-derived`) comes back under new ids, is read last and can regroup the passages of other documents; a re-chunk keeps an unchanged passage's id. The fit keeps its order: one sorted by the passages' lemmas gave other topics than the id order on all four synthetic test corpora, so it would have moved every unchanged database | a test that two fits in the same order give the same topics, weights and unplaced passages; read against the code |
| With `TOPIC_PASSAGES_PER_TOPIC` at 0, a language whose few passages the filter or tf-idf cannot tell apart, the same words in other counts, still failed the refit (a variant of NEW-topics-2) | the one-topic fallback asked only the sizing, which 0 turns off | with the sizing off, a language with fewer distinct passages than `TOPIC_NUM_TOPICS` that the filter or tf-idf cannot tell apart gets one topic, as it does under the sizing ([`topics.py`](../backend/topic_modelling/topics.py)) | red tests. Limit: at `TOPIC_NUM_TOPICS=2` two such passages still fail, naming `TOPIC_NO_BELOW`; the shipped settings never reach it |

### Fixed in v0.4.4: the archive, the database and operations

Every row rests on its red tests, most of them static tests of the Makefile, the workflows and the locks, or on a reading against the code.

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A restore could bring a follow-up back released under a root that left the release while the follow-up sat in the archive (NEW-ops-docs-1) | the restore kept a question's release wherever a question live all along held the same one, and the thread trigger fires on the root's update, when the follow-up was not in the table | a restored follow-up keeps its release only under a turn that is still accepted and released in the same release; otherwise it, and every turn below it, comes back accepted but undrawn ([`restore.py`](../backend/archive/restore.py)) | red tests |
| The archive README said a row whose parent is gone restores nothing at all, and named neither the release clearing nor the drop of a fact left on no passage (NEW-ops-docs-4), nor that a question a partial deletion rejected comes back rejected (NEW-ops-docs-2) | the restore changed in v0.4.0 and the README did not | the README says what a restore does to each, and lists the rejected question as a limit ([`README.md`](../backend/archive/README.md)) | read against the code |
| Three column comments misdescribed their columns: `questions.categories` named no compound question among its NULL rows, `topics.top_terms` called itself what a label is matched on across a refit, and `topics.embedding` said nothing reads it (BL-B20, QAB-topics-7) | the code moved on and the comments did not; `facts.bridge` now also holds the head | one comment-only revision, `20e31b1656f7` on `626a5b07ae34`, rewrites the four comments and puts the old texts back on downgrade | a migration test |
| The database README's section on cascades and triggers left out the trigger that keeps a thread whole in the release (VAR-thread-release-1) | only its revision row named it | the section describes `questions_release_thread_whole`, and that a restore applies its rule to the follow-ups it puts back ([`README.md`](../backend/database/README.md)) | read against the code |
| The image locks had drifted from `poetry.lock`: 30 shared pins differed, among them pandas 3 in the API's workbook export against the 2.3 the suite runs, protobuf 7 against 6, aiohttp 3.14.4 against 3.14.5 and Docling 2.132.0 against 2.137.0 (NEW-ops-docs-5, BL-C3-aiohttp) | each image lock was resolved on its own | `make lock` resolves both image locks in the image's base under `poetry.lock`'s pins, torch included, and a static test holds every shared pin equal. The API image now runs Docling 2.137.0, so its parse output can differ from a build parsed with 2.132.0 | red tests |
| The host `poetry.lock` was not audited, so `make audit` stayed green while Dependabot flagged aiohttp there (BL-D6-ops; listed as deferred under the QA review of 2026-10-20) | `make audit` read only the two image locks | it reads `poetry.lock` too, torch and torchvision left out as in the image lock, and fails after reading all three | red tests |
| `make audit` and `make lock` wrote their scratch files into the source tree, unignored, and an interrupted run left them there (NEW-ops-docs-6) | the recipes removed them only on success | both write to a temporary directory removed on any exit | red tests |
| CI ran on `ubuntu-latest` and installed whatever poetry PyPI served that day, so a moved runner image or a poetry release could change a run no commit touched (BL-D6-ops, NEW-ops-docs-7) | neither was pinned | every job runs on `ubuntu-24.04` and installs poetry 2.3.2, the version that wrote `poetry.lock` | red tests |
| `make dev` waited for Postgres forever and in silence (FIX-R71; listed as deferred under the v0.3.0 rebuild's tooling odds and ends) | the wait had no bound | it waits at most 60 seconds, 30 tries two seconds apart, and says so when Postgres never answers | red tests |
| `make questions-export OUT=`, `make diversity FILE=` and `AGAINST=`, and the spend targets' `LOG=`, cut a path holding a space in two (QA-security-5) | the recipes put the path in unquoted | they quote it | red tests |
| `cannot_run`'s docstring said the command line and the API share it (BL-C3) | only the API's rerun calls it | it says so, and that the command line relies on the queue's preflight instead | read against the code |
| The written-count gate's blind spot, a false refusal still open, was filed under the known trade-offs that are not defects (FIX-R41) | the entry itself says it is open | it is an open entry of its own, [The written-count gate has the digit rule's blind spot](#the-written-count-gate-has-the-digit-rules-blind-spot), with its four wrongly refused questions counted, and the count rule's entry points to it | read against the code |
| A command-line value holding `( )`, `&` or a quote, `OUT="/tmp/Q&A (final).xlsx"`, failed every target that loads the environment with a shell syntax error (QA-ops-docs-1) | `LOADENV` exported the command line as make writes it, with only its spaces escaped, and the shell read it again | each command-line variable is exported single-quoted, its own quotes escaped, so its value reaches the command whole ([`Makefile`](../Makefile)) | red tests |
| A command-line value holding spaces, `OUT="/tmp/Projects - Code/r.xlsx"`, named its later words in `QA_COMMAND_LINE` as settings a stored row gives way to (QA-ops-docs-2) | the names were read off the words of `MAKEOVERRIDES`, where make writes such a value as several | `QA_COMMAND_LINE` names the variables whose origin is the command line, and nothing else | red tests |
| `make spend` and `make spend-by-shape` given a `LOG` that names no readable file printed "no priced calls in the log" and exited 0, which reads as a run that cost nothing (QA-ops-docs-3) | the log was read through `cat` unchecked, and the targets took the status of the last command in the pipe | both refuse a `LOG` that is missing, unreadable or a directory with exit status 2, naming it; an empty log still reads as no priced calls | red tests |
| The configuration guide and the settings README left `QUESTIONS_KIND_MIX` out of the settings that read a default in code (QA-ops-docs-4) | its line in `backend.env` is a comment, so every deployment deals `needs_both:5,compound:1` from code | both name it beside `QUESTIONS_MEETS_SHARE` | a static test of the settings the docs list |
| `make audit` read PyPI's advisory service, which lists 18 of the 21 advisories OSV holds on Pillow 12.3.0 and leaves out the critical GHSA-8g5g-8vmr-9782 (QA-ops-docs-5) | pip-audit reads PyPI's service unless told otherwise, and one service a run | every lock is read against OSV, which lists all 18 that PyPI's service does on Pillow. The make guide says the audit runs whole on Linux only, as the nightly job runs it: on a Mac the `poetry.lock` leg fails on CUDA wheels with no macOS build, not on an advisory | red tests; the flag was checked against pip-audit's help, not by a live run |

### Tried in v0.4.4 and withdrawn, with the reason

| Item | What was tried, and what withdrew it |
|---|---|
| A verbless definition under the heading it defines extracted, as a glossary entry is (FIX-R13) | A passage with no finite verb is skipped whatever its heading. Two designs read one built on a noun or a gerund that defines its heading as a passage to extract: the first admitted index and page-reference lines as definitions, and the second, which held those to the index check, dropped every short definition holding a figure. Telling a glossary definition from an index line needs more than the line's own shape. Both were reverted, so such a passage is skipped as before, and the extraction run its bar planned was not made |
| Extraction prompt 13: a heading names the subject a sentence leaves out, and is a condition only where the sentence states it (FIX-R129, the heading part of BL-B10) | Extracted from 60 passages under a heading, 15 per corpus and language, with prompt 12 and the new prompt, every validated fact labelled blind. Prompt 13 cut the facts that write the heading as a situation from 119 to 43, but dropped the heading's scope instead (32 of its 53 wrong facts) or leaned on words pointing outside (15): the correct share fell from 0.917 to 0.793, under the floor of 0.817. Its one iteration, prompt 14, carried the heading in as what a fact is about: it kept the scope (0.902) but wrote 105 heading-as-situation facts against a limit of 59.5, 100 of them correct, naming the heading's procedure or case as a setting the sentence does not state, as its own example does. A next try first settles whether a correct fact scoped by its heading counts against the bar. Extraction stays at prompt 12 |
| A U+00AD hyphen read per document (NEW-parse-chunk-1) | A text layer that draws its hyphen as U+00AD was to keep it before a lower-case letter (`pick-up`, `3-facher`) where the document prints no hyphen of its own. The rule turned hyphenation points into hyphens: telling a drawn hyphen from a hyphenation point needs more than the document's own characters. It was reverted, and such a U+00AD is still dropped before a lower-case letter |
| A lead-in the converter labels a heading read as a paragraph (the heading half of FIX-R100) | With flat heading levels nothing says where such a lead-in's scope ends, and read as a paragraph it reached sibling sections it does not introduce. The chunking README lists the loss as a limit: a lead-in set as a heading reaches no passage when sub-headings of its own level follow it |
| A parser cut before a lower-case word dropped where nothing ends a sentence before it on its line, so *Der Kunde zahlt gem. Preisverzeichnis eine Gebühr.* is one sentence (QA-extraction-4) | In the second facts replay it moved the cuts of 21 of the 820 passages, most of them joining clauses after a semicolon, and validated one fact the base refused, which the blind label found narrowed: it drops the condition that the ball was outside the penalty area. 0 of 1 correct, against a floor of 0.767: the snapshot's share of validated facts stated correctly (0.867) minus 0.10. It was reverted, so such a clause is still stored as two halves, held by a strict expected failure |

### Deferred, with the reason

| Items | Why they stay open |
|---|---|
| FIX-R40, FIX-R10 | Feature-sized parser passes for a two-column page and for a title that re-levels chapters, shown so far only on synthetic fixtures. No real document in hand has either, and the build corpus is single-column, so no bar is possible (the section-path entry of the v0.3.0 section is the same root as R10) |
| FIX-R15 | A follow-up gate that failed its bar before. The next try, earlier turns' facts through `adds_to`, touches follow-up rows, of which a 60-row arm holds too few (about 10) to measure |
| FIX-R37 | No stored signal separates usable rows: the confidence's AUC is 0.55 on 298 labelled link rows |
| FIX-R42 | A product decision: difficulty bands grade retrieval spread by design |
| FIX-R34 | Report only: only Swiss spelling meets it, and a per-document spelling table is a feature |
| BL-C1 | The exact downward scan stays: at build size (500 to 1,000 accepted rows) it takes 0.3 to 0.9 s and releases more than bisection |
| BL-C2 | A new overlap threshold with no observed case (0 of 2 compound rows in the spot checks), and no bar can measure it: the labelled snapshot predates compound questions |
| QAB-qg-plan-4, NEW-qg-plan-5 | No effect on current corpora (every passage has a vector) or on the default mix |
| FIX-R43 | A report surface that writes nothing; the full build reports coverage itself |
| FIX-R90, FIX-R84, FIX-R94, FIX-R58, FIX-R75 | Refactors with no behaviour change; FIX-R90 would also churn the verifier inside a calibrated release |
| QAB-llm-nlp-5, -6, -8 | They affect only self-hosted models; the build runs on Azure |
| FIX-R53 | It matters only with more than one extract worker replica; the default is one |
| FIX-R112 | Nothing changes for German and English, and the static test already holds every table to `NLP_MODELS` |
| VAR-link-pass-1 | Only families of thousands of sections are slow; the corpus's largest has 66 |
| NEW-ops-docs-3 | It would edit the downgrade of a released migration (733a3eadef7c), for a rollback-only case |
| FIX-R87, FIX-R128, QAB-preprocessing-14 | A stray object nothing reads, a refusal's audit text and a rare split row: none changes what a build writes |
| QAB-api-settings-6, -10, FIX-R113, FIX-R85 | No effect on a build, and the API listens on 127.0.0.1. The full build exports about 9,000 rows (about 410 MB against 512 MB), so a streamed export waits until a corpus nears 13,000 questions. FIX-R113 would add a setting, and FIX-R85 a unique index on existing data |
| VAR-review-kind-1 | A new filter mode (picker, API and CLI) with no effect on a build |
| FIX-R109, FIX-R67, FIX-R111 | A supply-chain bundle with no effect on data (its poetry pin ships in v0.4.4; image digests need image rebuilds); no defect worth a change, since the cache key follows the install recipe; and least-privilege database roles, which need a live stack's provisioning |
| FIX-R66 | A policy decision for the user: may a container call a hosted model? |
| NEW-parse-chunk-6 | Low. It would change `content_sha256` of every stored document, so an upgraded database would need every document parsed again for duplicate detection to hold |
| BL-D4-picture, FIX-R165, QAB-preprocessing-12 | Text a converter nests inside a picture still reaches no passage. A filter has to tell a statement from a diagram label, and no real document with a banner statement is in hand to measure one on (on the football PDFs 90% of picture text was labels). A footnote attached to a picture is written since v0.4.4 (NEW-parse-chunk-4) |
| FIX-R7, FIX-R167, the bridge part of BL-D4-extract, the bridge and conjunct parts of BL-B10 | The bridge test at extraction was predicted to refuse about 6 of 16 correct bridges against a bar of one, and bridge prompt 8 failed two of its eight bars (2026-10-20). A dropped conjunct needs a model reading that no design has measured |
| NEW-extract-nlp-4 | A pronoun or *dies* pointing into a German verb-first condition (*Wird eine Karte gestohlen, muss sie sofort gesperrt werden*), or an English *this* standing for an *if* clause, is still refused `unresolved_reference`. Both readings that free them, tried outside the release, also resolve the four must-refuse sentences pinned in `test_references.py` (*Wird das Konto eröffnet, sendet die Bank es per Post.*), the failure that withdrew them in v0.3.3. It needs coreference that weighs competing antecedents |
| QA-security-2, GitHub's 9 open Dependabot alerts on Pillow 12.3.0 (1 critical, 6 high, 2 medium) | Accepted, with its exposure. OSV lists 21 advisories against Pillow 12.3.0, all fixed only in 13.0.0, and no released Docling allows Pillow 13: docling 2.141.0 and docling-core 2.103.1 still cap it below 13 (upstream merged the lift on 2026-10-21, in docling PR 4929 and docling-core PR 907, unreleased). None is reached by the parse of an uploaded PDF: OCR is off and embedded bitmaps are not read, so docling-parse renders each page itself and hands Pillow a raw RGBA buffer through `frombuffer`, and no Pillow file decoder, PDF parser or encoder runs. No product module imports PIL, uploads are PDFs an operator puts in, and neither image installs Ghostscript. The upgrade is the next docling and docling-core releases, with docling-parse 7.22.4, docling-ibm-models 4.0.4 and streamlit 1.66.1 or later, then `make lock` and the parse bar again |
| BL-B13 | No code change: the gap between the two calibration links is explained by their different topics, N and type mix (neither language is significant: p 0.145 and 0.122) |
| BL-B15, BL-B17, BL-E1, BL-E2, BL-G, FIX-R126, FIX-R140, FIX-R166, FIX-R55, the unanswerable and false-premise parts of BL-D4 | Transferred to the work on the DataMorgana paper's features (v0.5.0 and the full build), where unanswerable and false-premise questions are redesigned |
| BL-F1, BL-F2 | The calibration databases stay for that work, which drops them after its report |
| BL-F3, BL-F5 | The user's own: the podman VM size, and their own edits and untracked files |

## Found by the QA review of 2026-10-20

A second review hunted bugs on the top of the v0.3.13 to v0.3.27 stack. The
releases from v0.3.28 on fix what it found. The first two also close the known
issues that the release notes of v0.3.16 (the scoped bridge pass) and v0.3.26
(the review guideline and kind) listed.

### Fixed in v0.3.28: scoped bridges, review kind, dependencies

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A bridge pass narrowed by `TOPIC`, `SHA` or `PASSAGE` lost bridges | it deleted every bridge resting on a passage of the scope but re-read only the heads inside it, so a bridge opening outside the scope whose partner sat inside was lost and never written back (cross-topic links, since v0.3.16) | it clears only the bridges opening on a passage of the scoped topics, which it rewrites ([`repository.py`](../backend/extraction/repository.py)) | red tests on bank and shop rows in German and English, green after; the scoreboard moves no value |
| A narrowed pass or a second `MISSING=1` run wrote a second bridge on a pair already bridged | a sibling or cross-topic pair can be headed from either side and the pass remembered topics, not pairs | the pass never offers a pair a stored bridge rests on, whichever side heads it ([`links.py`](../backend/extraction/links.py), [`service.py`](../backend/extraction/service.py)) | red tests on bank and shop rows in German and English (8 red before, green after); the scoreboard moves no value |
| aiohttp 3.14.3 in the host's `poetry.lock` carried CVE-2026-111063, CVE-2026-111064 and GHSA-2g87-pp6c-29x5 | Dependabot alerts 30 to 32; v0.3.13 had bumped only the API image's lock | `poetry.lock` pins aiohttp 3.14.5 and yarl 1.25.1, nothing else moved | the three alerts close |
| Compound questions were rejected by reviewers for asking two things at once | the Argilla question record carried no kind while the guideline said to reject a question that asks two things at once | the record's metadata carries the kind, and the guideline says a compound question asks two separate things on purpose and is judged one half at a time ([`review/`](../review/)) | a unit test holds the kind in the record; not covered by the scoreboard |

Session A's QA test commits (mutation tests of the unanswerable
turn, the answer-incomplete reading, the bridge prompt and the link helpers)
ship here as tests only.

### Fixed in v0.3.29: references

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A German polite Sie addressing the reader was read as a dangling third person plural | a fact that is the passage's own sentence addressing the reader (`Sie können Ihre Karte sperren`) was refused `unresolved_reference`, because the German tagger gives the polite form Person=3 with no polite feature | a language-keyed table `_POLITE` (German: Sie, Ihnen, Ihr, Ihre and their cases; English none) is read by the capitalised surface form: a capital form inside a statement is polite, one opening a statement only where another capitalised polite form follows it, so `Sie werden geliefert`, `Sie wurde gesperrt` and a lower-case `sie` stay refused ([`analysis.py`](../backend/nlp/analysis.py)) | red tests on bank and shop sentences in German and English, green after; the Laws of the Game never address their reader, so the scoreboard moves no value |
| A pronoun after an exceptive clause that points back at its sentence's subject was refused | the parsers hang the clause an exceptive run opens (`es sei denn`, `außer`, `except where`, `provided`, `unless`) as a conjunct of the root or the complement of the run word, so the pronoun and its antecedent counted as one clause | the verb heading the exceptive clause is marked and `_clause` treats it as heading a clause of its own, as it does for a subordinator; a pronoun with no noun before it stays refused ([`analysis.py`](../backend/nlp/analysis.py)) | scoreboard facts: 2 German facts newly admitted (11566, 12590), both stated correctly |
| A German `dies` standing for an earlier clause of its own sentence was refused | `Wenn die Karte gesperrt ist, gilt dies als Kündigung`: the check placed the `wenn` clause's verb in the main clause | the earlier finite verb is asked the same "heads a clause of its own" test the clause walk applies; a `dies` with no clause before it stays refused ([`analysis.py`](../backend/nlp/analysis.py)) | scoreboard facts: 1 more German fact admitted (12469), stated correctly |

Together on the scoreboard: German `unresolved_reference` refusals 59 to 56, validated facts 1697 to 1700, all three newly admitted facts stated correctly, no right refusal lost.

### Fixed in v0.3.30: bridges in samples

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A compound question could rest on a bridge's own related pair | the sample returned the head alone when the head spans and kept a bridge alone, so 5 of 68 compound slots of the v0.3.12 pool rested on the two passages a bridge relates, not on two unrelated ones | a compound sample prefers a passage's own claims, never keeps a bridge, and a topic holding only bridges is exhausted for a compound slot ([`selection.py`](../backend/question_generation/selection.py)) | replay on the stored build: compound slots resting on a bridge 5 to 0, the 68 compound slots still dealt |
| An unanswerable slot was dealt a bridge and perturbed it | the perturbation of a fact resting on two passages was stored `hard` against the planned `easy`: 67 of 364 unanswerable slots of the v0.3.12 pool were dealt a bridge | an unanswerable slot is dealt only facts resting on one passage, and a slot with only bridges left is skipped and logged while the topic goes on ([`service.py`](../backend/question_generation/service.py)) | replay: unanswerable slots dealt a bridge 67 to 0 (364 dealt before, 358 after, 6 skipped); the unanswerable share of written slots 0.295 to 0.293 |
| A compound slot's second passage could hold only bridges | the sample dropped that passage's facts and left the head alone, after the slot had spent a round on it | the partner is chosen among passages with an unspent non-bridge fact ([`selection.py`](../backend/question_generation/selection.py)) | red tests on bank and shop rows in German and English (4 red, green after); the replay is identical to the previous commit |

On the scoreboard no value moves (it replays stored data). The slots of single and needs_both questions after the first unanswerable slot of a topic shift, because that slot no longer spends a bridge.

### Fixed in v0.3.31: table rows and soft hyphens

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A soft hyphen in a PDF text layer deleted every drawn hyphen | a PDF whose font maps its drawn hyphen to U+00AD lost every such hyphen in the mend: `3-5 Werktage` became `35 Werktage` and `Kredit- oder` became `Kreditoder`, because the cleanup deleted each U+00AD | one directly before a lower-case letter is dropped (a soft hyphen inside a word) and any other is spelled `-`; a word broken at a line end is still joined by the rejoin ([`parsing`](../backend/preprocessing/parsing)) | red tests with bank and shop sentences in German and English; 0 elements change on the 30 Laws PDFs, which hold no U+00AD |
| A group row of a table was glued to its first item | in a fee table a label alone over a lower-case label was read as a wrapped label, so `Cards` over `debit card` and `credit card` became `Cards debit card` | a label alone on a row joins the row below only when exactly one lower-case-labelled row with data follows ([`parsing`](../backend/preprocessing/parsing)) | red tests, bank and shop tables in German and English; on the 30 Laws PDFs 1 element per language changes (one table row of uefa-equipment-regulations.pdf, `b) c) d) e)`, now two rows), the scoreboard moves no value |
| The tail of a wrapped table label was glued to the next row's label | in a top-aligned table whose label wraps while the other cells stay on the first line, the tail (`only)`) became the head of the next label (`only) next day`) or a priceless row | a label-only row opening in lower case or closing a bracket the label above left open joins the label above it ([`parsing`](../backend/preprocessing/parsing)) | red tests; the same 1 element per language on the Laws PDFs. Known gap: a three-line wrapped label joins only its first tail |

### Fixed in v0.3.32: table footnotes and lead-ins

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A footnote the converter attached to a table was in no passage | a table footnote (`TableItem.footnotes`) was in no passage, because the table serializer writes captions only | the footnote is written beneath the table in its passage, unless it sits outside the serializer's body layer or is also listed as a caption, so it is written once ([`chunking`](../backend/preprocessing/chunking)) | red tests with bank and shop tables in German and English; on the 30 Laws PDFs 0 passages change (no table footnote in the corpus) |
| A lead-in scoping a long table reached only its first piece | a lead-in ending in a colon was kept with the pieces of a list but not of a table longer than one passage, so every piece after the first lost what scopes it | a table is read as a list is when a lead-in is carried to the pieces ([`chunking`](../backend/preprocessing/chunking)) | red tests with bank and shop tables in German and English; 0 passages change on the 30 Laws PDFs |

Deferred: the text a converter nests in a picture is not written into passages (the README now says so). Most of it is page numbers, running heads and diagram labels (259 new lines in the German Laws, 382 in the English), so keeping it needs a filter first; no fix is made here.

### Fixed in v0.3.33: number readings

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A price of four or more digits with a fraction was read as no figure | `1299,99 EUR` and `2500.00` matched no figure, so `agrees()` refused one price written two ways and `adds_up()` let a wrong total through | the figure pattern has an alternative for a long head with a fraction and no thousands mark; a plain long head with three fraction digits stays a fraction ([`gates.py`](../backend/question_generation/gates.py)) | red tests with bank and shop prices in German and English; the offline corpus holds no such price, the scoreboard moves no value |
| The same value in another format was refused as an addition | `1,000` and `1000`, `5.00` and `5`, `2.50%` and `2.5%`, German `1.000` and `1000`, `4,90` and `4,9` were refused `unsupported_addition` and read as two numbers by the dedup, because extraction compared digit runs as strings | one owner of the figure's value reading, in `nlp.analysis` (`figures`, `FIGURE`), used by `numerals()`, `numbers()` and the question gates, which compare values in the text's language ([`analysis.py`](../backend/nlp/analysis.py)) | red tests in German and English; no corpus row moves |
| A count written out past twelve was read as no number | `thirty days`, `dreißig Tage`, `twenty thousand`, `fünfundzwanzig` read as no number or as their own word, so a fact restating `30 days` from `thirty days` was refused | cardinals are composed from ISO-keyed `_SPELLING` rows to 99 (German to 999 and the thousands), word runs join (`twenty thousand`, `one hundred twenty-five`), a word from thirteen up is a number whatever the tagger made of it; a hyphen joins only into another cardinal ([`analysis.py`](../backend/nlp/analysis.py)) | red tests in German and English; no corpus row spells a count past twelve |
| The English pronoun `one` was read as the count one | `No one may withdraw` and `the one you bought` were read as the count, because `like_num` is a spelling test, so the fact check refused a sound fact, the key check refused a key and the echo-answer gate was exempted | a word counts as a number only with a digit, the tag NUM or an ordinal ADJ: one shared `is_number` used by `_units` and `restates` ([`analysis.py`](../backend/nlp/analysis.py)) | red tests; on the scoreboard one wrong refusal freed (fact 13216, an English throw-in countdown, correct), none right lost. Known gap: `one of the same price`, which the tagger tags NUM, stays refused |
| A recovery numbering its steps handed the numbers back as figures the key lacks | `Step 1:`, `Schritt 1:`, `(1) ... (2)` and `1. A; 2. B` made `answer_incomplete` refuse good keys | `unnamed()` strips the step numbers, the label word read from the ISO-keyed `_STEP_LABEL`; an item number `n.` is stripped inline only where two or more numbered items run in order, and the label's terminator is mandatory ([`gates.py`](../backend/question_generation/gates.py)) | red tests in German and English; the offline corpus holds no numbered-step recovery |
| A list opened by an adverb hid its new item | `also commissions, fees and taxes` against the key `fees and taxes`: the tagger read the first item as a verb, so every item was taken for a predicate and `unnamed()` named nothing; found by session A's property test | a verb with only an adverb before it and the list under it is a list head ([`gates.py`](../backend/question_generation/gates.py)) | red tests (also, also returns, as well as); session A's property tests (`tests/property/test_cycle_invariants.py`) ship here; the same single scoreboard move as above |

Deferred (llm-nlp-12): a German spelled count read as a unit would also refuse facts whose count the cited sentence lacks but the passage states. On the scoreboard it refuses 5 more German facts (unsupported_addition 18 to 23), of which readers judged 4 correct, so the tightening would remove 4 usable facts of 5 and orphan 13 more questions; it is not shipped, and the decision is whether the check reads the passage context.

### Fixed in v0.3.34: review and page vocabulary

| Defect | Found | Fix | Measured |
|---|---|---|---|
| The questions workbook had no kind column | a compound question read as an ordinary multi-passage row | a Kind column (single, needs_both, compound) follows Type on the Questions sheet ([`export.py`](../backend/question_generation/export.py)) | a unit test holds the column; not covered by the scoreboard |
| A follow-up reached Argilla without the turns it follows | reviewers rejected context-dependent follow-ups that read fine in their thread | the record has an optional `thread` field (the earlier turns, oldest first, walked up `follows_id` with a loop guard) and `turn` metadata, and the guideline says a follow-up is judged after those turns ([`records.py`](../review/records.py), [`datasets.py`](../review/datasets.py)) | unit tests, with a loop-guard test whose mutant hangs and is killed |
| The Questions page named a compound question's prompt wrongly and called two things Kind | `_sent_as` ignored `kind=compound` and showed the spans prompt, and the column `Kind` held `question_type` while the stored kind was `Written as` | a compound question's prompt is named `type (compound)`; `question_type` is `Type` in the table, the detail, the filter and the analysis rows, and the stored kind is `Kind`, with a help line for each kind ([`questions.py`](../frontend/views/questions.py)) | page tests; a slot of the compound kind that fell short of passages and was written plain still shows `(spans)`, since the prompt name is not stored |

### Fixed in v0.3.35: a needs_both question needs both

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A needs_both question kept both passages when each held only half of what it asked, or the same half | the round trip's recall check passed on half an answer, so a question that one passage states whole, cited with a second passage that adds nothing, kept both citations and was counted as spanning two | a new verifier call lists the parts of the answer and quotes each cited passage that states them, and the code finds the quotes; the question stays two-passage only when each cited passage holds a part no other holds, where every passage states every part and the question joins cases with a coordinating conjunction both are kept, and a reading that cannot be had (model unavailable or refused) keeps the question as cited with a warning ([`checker.py`](../backend/question_generation/checker.py), verifier prompt `stated` 1) | calibrated on 12 fixtures and the labelled rows: see the figures below |

Figures and limits of the parts reading (verifier prompt `stated` 1, new and pinned). Calibration rows are session C1's labelled rows; "by reading" counts what the call decides, "by citation" counts what is stored afterwards.

| Build | Honest needs_both kept | Padded ones relabelled single | Gold compounds relabelled |
|---|---|---|---|
| v0.3.12, C1 rows | 30/31 | 33/45 | 0/8 |
| v0.3.12, all gold rows | 29/36 | 76/107 by reading, 36/107 (0.34) by citation | 0/18 |
| v0.3.0, C1 rows | 23/23 | 25/30 | 0/7 |
| v0.3.0, all gold rows | 20/20 | 68/97 by reading, 60/97 (0.62) by citation | 1/30 (row 4392) |

A blind read of 20 rows agreed on 20. Limits: a padded question that cites a bridge fact keeps both passages, because the bridge itself rests on two, which is why the counts by citation are lower (0.34 on v0.3.12, 0.62 on v0.3.0); one gold compound of v0.3.0 (row 4392) is relabelled single, so the calibration bar of none was missed on that build; a tie where every cited passage states every part keeps both only if the question joins cases with a coordinating conjunction. The check adds one verifier call per accepted two-passage needs_both question, about USD 0.45 to 0.5 per build, and does not rejudge stored questions. It supersedes session A's `fix/two-passage-v2` and `fix/needs-both`, which stay unmerged.

### Fixed in v0.3.36: a thread leaves the release whole

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A released thread lost its root but kept its follow-ups released | threads are drawn and released whole, but rejecting or reverting a released root (a person, a re-check, or the trigger that rejects a question losing a fact) cleared `release_id` on that row only, so its follow-ups stayed released without it | a trigger `questions_release_thread_whole` (revision `d5b2f8a60c14`) clears `release_id` on every follow-up below a question that leaves `accepted`, in the same statement, and exits at once for a question with no follow-up; the upgrade also clears the release of follow-ups already left under a root that is not accepted ([`database`](../backend/database)) | red integration tests on a German bank thread and an English shop thread (trigger, decide, reject, back to draft, a three-turn thread already split; 8 red before, green after); 1,500 rejects of questions with no follow-up take 0.022 s with the trigger against 0.023 s without |

### Fixed in v0.4.0: reading documents, questions, topics and pages

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A numbered reference was linked to another document's section | a bank passage naming `Section 7` was linked to the shop's Section 7: the shallowest depth was taken across all documents before the head's own was preferred | a numbered reference resolves in the head's own document or is dropped; a title names another document ([`links.py`](../backend/extraction/links.py)) | links over the v0.3.12 passages 166 to 166, German unchanged, English 7 removed and 7 added, all 7 added right; no validated bridge newly refused |
| A quoted heading with a typographic apostrophe was cut | `Customers’ rights`, `Conditions d’accès` were cut at the apostrophe and never linked | double-quoted spans may hold apostrophes and single marks close only where no letter follows ([`links.py`](../backend/extraction/links.py)) | red tests in German, English and French |
| An inflected label word before a number matched nothing | `Sections 7 and 9`, `Abschnitte 7 und 9`, tagged as a proper noun, matched neither the learned label nor its lemma, so no reference link and a bridge naming where its passage sits passed | one shared matcher `validation.label_word` also accepts an inflected form (at most two extra letters, from an ISO-keyed `_INFLECTIONS` table) directly before a number ([`validation.py`](../backend/extraction/validation.py)) | red tests in German and English |
| Sibling linking was quadratic in pure Python | one flat parent: a dot product per candidate per head, 2,000 sections 132 s | each head scores its family with one numpy product ([`links.py`](../backend/extraction/links.py)) | pairs byte-identical on the v0.3.12 passages and on synthetic flat parents; 1,000 sections 37.5 s to 5.7 s, 2,000 132 s to 16 s, 4,000 about 8 minutes to 59 s |
| A link whose partner had no validated fact was dropped after the heads chose | the head lost its pair and the topic slot stayed empty | heads and partners without a validated fact are removed before the links are dealt ([`service.py`](../backend/extraction/service.py)) | v0.3.12 corpus, two passages per bridge: 158 links to 164; three: 148 to 162 |
| A bridge group of three or more strided before it grew | a pair that could not grow took the slot of one that could | each head's link is grown before the quota is strided over ([`links.py`](../backend/extraction/links.py)) | size 2 identical; size 3 more links; red tests |
| A passage held two languages | a page printing each German paragraph beside its English translation became one passage read as one language | a chunk ends where its prose changes language, on a confident detection only (`nlp.language.detect_surely`, 0.9 of lingua's confidence; [`chunking`](../backend/preprocessing/chunking)) | 30 football PDFs: German 1,000 to 1,003 passages (a footer and a running header split off), English 966 to 968; scoreboard unchanged |
| A running head refiled the text above a chapter's opening | the running head named the chapter that opens mid-page | a chapter starts at its own heading where its page holds one ([`chunking`](../backend/preprocessing/chunking)) | same re-chunk as the row above |
| A price whose digits equal a page number became a heading | `5 €`, `£5`, `2,5 %` were taken for a repeated running head | running names and paragraphs must hold a letter to count as a repeat ([`chunking`](../backend/preprocessing/chunking)) | same re-chunk |
| A German dies after a relative clause alone was resolved again (a regression of v0.3.29) | `Für Konten, die Zinsen zahlen, gilt dies nicht.` passed, because a relative verb heads a clause; found by QA round 1 | a relative verb no longer counts as the earlier clause `dies` stands for ([`analysis.py`](../backend/nlp/analysis.py)) | red tests; the three facts v0.3.29 admitted stay admitted; the sentence is refused `unresolved_reference` again, as on v0.3.27 |
| One scanned page inside a digital PDF went missing silently | the scanned test reads the document's mean characters per page | each page with no text layer and pictures covering half of it (overlaps counted once) is named in a warning, in the stored parse's `image-only-pages` metadata and in `documents.parse_error` when the parse completes, so the documents page (Parsing error row), the API and `make parse-status` show it; a re-parse clears it; the document is still parsed for its text pages, a wholly scanned one is still refused, OCR is not built ([`pdf.py`](../backend/preprocessing/parsing/pipelines/pdf.py)) | 30 football PDFs: 5 name one real picture page each (covers and back covers); no text change |
| A vectorless passage always won as compound partner and always lost as needs_both partner | a word-overlap score (about 0.06) was ranked against cosines (0.7 to 1.0) | one candidate set is ranked on one scale: cosine only where the head and every candidate carry a vector, word overlap otherwise, the relative floor only on all-vectored topics ([`selection.py`](../backend/question_generation/selection.py)) | planning-trace replay byte-identical on the v0.3.12 data, vectorless and with synthetic vectors |
| Topic names lost their subject | `Credit card payment` became `Credit` when two of three names shared an ending | a shared ending is taken off only when none of its words is a top term of the topics that carry it ([`topic_modelling`](../backend/topic_modelling)) | Laws fit identical, 17 stored labels unchanged |
| A small language got no topics and the fit reported success | fewer than 6 fitted passages failed `TOPIC_NO_BELOW=3` / `TOPIC_NO_ABOVE=0.5` | the frequency filter is held to what the language's own passage count allows; a language still without a model fails the fit after the others are stored ([`topic_modelling`](../backend/topic_modelling)) | Laws fit identical |
| Redo on the Assessment page wiped every verdict when the assessment could not run | `POST /assessment/rerun` answered 202 with `ASSESSMENT_ENABLED` off or no judge | it answers 409 `assessment_cannot_run` before any verdict is cleared, through `assessment.config.cannot_run` shared with the CLI ([`backend/api`](../backend/api)) | 6 red tests green; `openapi.json` regenerated |
| A listing's row pick followed the position, not the row | a page, filter or search change opened another row's panel, and Accept or Reject went to another question | the pick is kept by row id on all six listings and dropped when the row is absent ([`frontend`](../frontend)) | red page tests |
| A failed topic-map fetch replaced the whole Topics page | an unguarded optional fetch | the failure is a caption in the map's place; table, naming and Delete stay ([`frontend`](../frontend)) | red page test |
| A document or topic filter hid a cross-document question's other sources | the WHERE ran before the GROUP BY | the filter chooses question ids and every source is still counted ([`frontend`](../frontend)) | red test, facts 1 against 2 |
| A drawn question rejected before the write lost the whole release draw | a reviewer or the fact trigger rejected it during the twin rounds | the draw writes only the drawn questions still accepted; the shortfall is reported ([`catalog.py`](../backend/question_generation/catalog.py)) | red integration test |
| A re-check overruled a person's accept | `reverify`'s bulk reject touched a question a person accepted after the stream was read | a re-check rejects only a question still accepted and not accepted by a person since (`source_changed` alone overrules) | red integration test |
| A fact deleted while the writer ran lost every question of the topic | the `question_facts` foreign key failed | `store()` reads the surviving facts `FOR SHARE` and skips and logs the thread that lost one | red integration test |
| A passage deleted mid-run failed a topic fit or stopped the bridge pass | the `passage_topics` foreign key, an `IntegrityError` per link | the fit writes the memberships of passages that still exist; the bridge pass drops and logs the link | red integration tests |
| A kind, band or language held only by unanswerable rows kept a quota the draw could never fill | at the default ceiling of 0 the release shrank to a handful of rows (2 of 200) | the supply check counts only rows a draw can take ([`balance.py`](../backend/question_generation/balance.py), [`service.py`](../backend/question_generation/service.py)) | released ids identical on 100 of 100 paired salts |
| The default language weights counted rows the draw never takes | a language mostly unanswerable shrank the release (49 of 205) | the weights count drawable rows, as the bands do; the comment on `QUESTIONS_RELEASE_LANGUAGES` says so | 100 paired salts: release German share 0.520 to 0.514, mean size 399.1 to 399.2, id overlap 0.937; weld and invalid intervals include 0 |
| The size scan walked one draw per size | unanswerable rows the ceiling never draws were counted: 623 draws for a few dozen rows, 4,578 rows 1,653 draws and 60 s | a bucket's supply counts unanswerable rows only up to the ceiling ([`balance.py`](../backend/question_generation/balance.py)) | same ids on 100 of 100 salts; the 4,578-row pool 1 draw and 0.1 s |
| A restored question kept the release of a draw a later one superseded | it counted as released beside the current release | restore clears `release_id` unless a question live all along holds that release ([`archive`](../backend/archive)) | red integration tests |
| A restore after a refit or re-chunk restored nothing, or left a question on a fact with no passage | archived rows whose foreign-key parent was replaced failed the foreign key | a row whose parent is absent is left behind and counted per table; a restored fact with no passage and a bridge with fewer than two are dropped with the question resting on it ([`archive`](../backend/archive)) | red integration tests |
| The workflows ran Node 20 actions | GitHub warned on every run | checkout v5, cache v5, upload-artifact v6, download-artifact v7 and setup-python v6, the first node24 releases, still pinned by commit SHA | tests/static pins them |
| certifi 2026.7.22 carried GHSA-6q48-6c7w-9gw2 | `make audit` failed on a new advisory, found by the scanned-page implementer | the images' locks and the host `poetry.lock` pin certifi 2026.10.19; nothing else moved | `make audit` and `make deps` green |

Deferred: text a converter nests in a picture stays out of passages (the chunking README says so).

### What the review found, and where it stands

Nine finders, one per area of the code, read the top of the v0.3.13 to v0.3.27 stack and reported 107 entries: 103 rated findings (3 high, 47 medium, 53 low) and four leads that turned out not to be bugs. By area, the rated findings were: preprocessing 15 (1 high, 9 medium, 5 low), frontend and review 15 (7 medium, 8 low), question plan 13 (5 medium, 8 low), NLP readings 13 (1 high, 6 medium, 6 low), database 12 (6 medium, 6 low), API and settings 10 (2 medium, 8 low), question checks and release 9 (1 high, 7 medium, 1 low), extraction 9 (3 medium, 6 low) and topics 7 (2 medium, 5 low). Testers then wrote a failing test for 59 of them, with bank and shop rows in German and English: 54 were confirmed, 1 was refuted and 4 low ones were not run. Every high and every medium finding was fixed, refuted or deferred.

All three high findings are fixed: the German polite "Sie" read as a pronoun pointing outside its statement, which refused every "Sie können ..." fact (v0.3.29); a table footnote the converter attached to a table, which reached no passage (v0.3.32); and the re-check that rejected every stored compound question, which session A fixed in v0.3.25 before this cycle's first release. Of the 47 medium findings, 43 are fixed in this cycle, one (the archive backfill of the kind column) was fixed inside the v0.3.20 migration, one was refuted and two are deferred (a wrong German spelled-out count, and text inside a picture, which the chunking README now says reaches no passage). Of the 53 low findings, 13 are fixed, two were fixed by session A, and 38 stay open because none was judged worth a release of its own (the main ones are the NUL-byte crashes in request bodies, unescaped text in the page tables and the cut after a few abbreviations; the full list is in the finders' files). The fixes shipped as nine releases from v0.3.28 to v0.3.36, one fix group each, and in v0.4.0, which carries the rest: scoped bridges, review kind and dependencies (v0.3.28); references (v0.3.29); bridges in samples (v0.3.30); PDF text and tables (v0.3.31); table footnotes and lead-ins (v0.3.32); number readings (v0.3.33); review and page vocabulary (v0.3.34); the needs_both check (v0.3.35); the thread release trigger (v0.3.36); write races (v0.4.0); release supply (v0.4.0); Node 24 workflow actions (v0.4.0); link references (v0.4.0); topic labels (v0.4.0); mixed similarity measures (v0.4.0); archive restore (v0.4.0); assessment rerun (v0.4.0); listing state (v0.4.0); link pass (v0.4.0); chunk structure (v0.4.0); and the scanned page (v0.4.0).

One finding was refuted by its tester: the export of the questions was said to exhaust the API container's 512 MB at ten times the size, but its memory grows linearly at 15.3 KB a question, so 15,800 questions add about 241 MB and the finder's own peak of 471 MB is under the limit; the real risk begins near 17,000 to 19,000 questions and stays open as a design note. Four leads were closed as not bugs: the 69 surviving mutants of the link helpers (a gap in the tests, with the output right today), a bridge answer check that ignores negation (it lives only on a deferred branch, not in the shipped stack), the language tables for a language with no row (they behave as documented), and the single log line for a language with no relation words. Mutation and property tests written for the v0.3.28 to v0.3.30 code (the first QA round; eight test commits in v0.4.0) found one real bug: since v0.3.29 a German *dies* after a relative clause alone ("Für Konten, die Zinsen zahlen, gilt dies nicht.") passed the unresolved-reference check. v0.4.0 fixes it. The rounds for the v0.3.31 to v0.3.36 code follow in the next release.

### Deferred, with the reason

| Defect or feature | Why it stays open |
|---|---|
| A German spelled count read as a unit (llm-nlp-12) | The tightening would refuse 5 more German facts on the scoreboard, 4 of which readers judged correct, and orphan 13 more questions, so it removes 4 usable facts of 5, above the 35% a tightening may remove. It needs a reading of the passage's own count, not the bare spelled word |
| Text a converter nests in a picture | Of the 171 passages the change touched, about 90% of the added lines were diagram labels, about 8% page numbers and only about 14 passages held a real sentence; the change also wrote invisible and furniture items and wrote 39 captions twice. A filter that tells banner text from labels comes first, and the chunking README now says picture text is not kept |
| Padded two-passage questions that cite a bridge | The needs_both check reads a bridge-cited question as resting on two passages, because the bridge fact itself does. Of the padded questions that still cite two passages, 56 of 71 (v0.3.12 pool) and 21 of 37 (v0.3.0 pool) cite a bridge. No writer change can alter that, because a fact has no passage column on `question_facts`; refusing such questions would also fail the tightening rule, since padded rows are about 81% usable |
| Bridge prompt 8, and the bridge test at extraction | Prompt 8 failed two of its eight pre-set bars: the share of correct parallel and contrast bridges refused for being spread was 22% against 15%, and the blind reader repeated its earlier verdict on 12 of 16 controls against 13. On the same pairs prompt 6 does as well or better (53% correct against 50%), so there is no gain to outweigh a prompt change. The bridge test waits for a prompt that writes its own probe per relation |
| The unanswerable writer's reading (settles prompt 7) | Of 20 drafts the passages answer, it flagged 4 (it needed more than 4): in 16 the reader listed only silent statements while its own replies said the passages give no answer. `QUESTIONS_RELEASE_UNANSWERABLE` stays 0. Two choices are left open: release only unanswerable questions a person confirmed, or write unanswerable slots as reason questions only |
| The two writer features for two-passage questions | Both are dropped: the needs_both check relabels after writing, and what it leaves (bridge-cited rows) no writer reaches. Writer v1 would remove about 1.0 to 1.3 false joins a build; writer v2 about 1.7 padded rows a build, and would lose about half of the honest needs_both rows dealt as pairs |
| Questions on a false premise | Redesigned (F1): a premise built from one passage's plausible misreading (a dropped condition, a misremembered number, a scope stretched too far), accepted only when the settles reading refutes it with a quote the passage holds. On 20 passages of the v0.3.12 corpus it accepted 4 (German 1 of 10, English 3 of 10) against a bar of 10 and 4 per language: 7 premises the passage did not refute, 5 malformed drafts, 3 the passage answered as asked and 1 that named its source. Not merged; `QuestionKind.FALSE_PREMISE` stays named for a later design |
| The limits of the shipped needs_both check | One gold compound of the v0.3.0 pool (row 4392) is still relabelled single, so the calibration bar of none was missed on that build; by citation only 34% of padded questions of the v0.3.12 pool are narrowed, because of the bridge-cited rows above |

## Found on the v0.3.12 rebuild of 2026-10-19

The code of v0.3.12 rebuilt the same two PDFs and every row of the build was
read again under a rubric, which also checked the analysis of the earlier
review. The releases from v0.3.13 on fix what it found, one fix to a release.

### Fixed in v0.3.13: dependencies

| Defect | Found | Fix | Measured |
|---|---|---|---|
| The API image's lock pinned an aiohttp with three published advisories | CVE-2026-111063, CVE-2026-111064 and GHSA-2g87-pp6c-29x5 were published against aiohttp 3.14.3 during the review, so `make audit` failed on every branch | the one pin is edited to 3.14.4, the release that fixes them; `make lock` would have moved every pin ([`requirements.lock`](../backend/api/requirements.lock)) | `make audit` reads no known vulnerability in either lock; aiohttp 3.14.4 needs yarl 1.25.1 or later, which the lock pins. The host environment's `poetry.lock` still holds 3.14.3, and the audit reads only the two image locks |

### Fixed in v0.3.14: facts

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A fact the repair call split out of a statement competed for its passage's cap | the per-passage atomic cap refused 65 facts as `over_cap` on the v0.3.12 rebuild, 59 of them pieces the repair call wrote for a statement refused as `not_atomic` and 6 model statements the pieces' numbers or names ranked out; the passage's room counted the refused statement's sentence once, but each of its 2.4 pieces on average competed for a place alone and lost by position; readers judged 51 of the 65 sound | a fact the repair call wrote no longer competes for the cap, in flight and in `make extract-recap`, which also gives back the repair pieces an earlier cap refused; the model's own facts stay capped beside them ([`service.py`](../backend/extraction/service.py), [`repository.py`](../backend/extraction/repository.py)) | replay on the stored facts of the v0.3.12 build: `over_cap` 65 to 0, all 65 freed (German 20, English 45), none newly refused; readers' labels on the 65: 51 sound, 10 rightly refused, 4 partly, so 51 wrong refusals freed for 10 right ones lost (5.1 to 1, the partly ones neutral) and 78.5% of what is admitted sound |

### Fixed in v0.3.15: bridge checks

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A bridge was checked against its excerpts' text only, and one naming its own heading was let through | `check_bridge` refused as `unsupported_addition` any unit only a heading trail or the title carried, and let through a bridge naming its own passage's numbered heading ("in Regel 5"), a claim about the document | the heading trail and title are read as an atomic fact's are (one shared reading of carried units), and a bridge whose statement writes a cited passage's numbered heading whole, the label word directly followed by its number, is refused as `not_bridging` ([`validation.py`](../backend/extraction/validation.py)) | replay over the 243 bridges of the v0.3.12 build: validated 178 to 184, those a reader judged correct 34 to 37, five label refusals, no validated bridge newly refused |

### Fixed in v0.3.16: bridge pairing and prompt

| Defect | Found | Fix | Measured |
|---|---|---|---|
| Bridge pairs were each passage's nearest unused neighbour inside its own topic | the pairs offered restatements (10 of 121 explicit references offered, 56 blocked by the one-topic gate) and left 19% of validated bridges correct | `links.py` pairs passages by the documents' own links: a numbered or quoted heading named, sibling sections under one parent heading, a term only two passages share; per language and across topics ([`links.py`](../backend/extraction/links.py), [`service.py`](../backend/extraction/service.py)) | offline replay over the v0.3.12 passages: 204 pairs, 47% across topics, none of the 4 pairs behind invalid questions offered; of the labelled pairs 29% (17 of 58) were correct against 18% for today's, wrong and unsupported 8.6% against 23% |
| The bridge prompt invented a link on every pair it was shown | on linked pairs with prompt 5, 37% of bridges read wrong or unsupported against 15% for the old pairs | bridge prompt 6 names the link the pairing found, shows each excerpt's validated facts, and asks for one bridge or none from a closed set of relations with a probe question; the bridge cites the chosen facts' sentences ([`bridge.py`](../backend/extraction/extractors/bridge.py)); the pairing and the prompt ship together, since the pairs alone were harmful | Azure, linked pairs, prompt 6 with v0.3.15's checks, read blind (31 bridges): 42% correct against 12% for today's pairs and prompt, wrong and unsupported 13% against 15%, 3 of 31 claims about the document |

### Fixed in v0.3.17: unanswerable questions

| Defect | Found | Fix | Measured |
|---|---|---|---|
| An unanswerable question was written in any of eight kinds | the plan cycled an unanswerable slot over every kind of the mix that does not span passages, so a set, a condition, a definition, a procedure or a consequence was written unanswerable and the passages often settled it: the writer failed 0.67 of the time on those kinds against 0.45 for factoid and reason questions, over three builds | an unanswerable slot is written only as a factoid, entity or reason question, those of them the mix weights above 0, in mix order; a mix with none of them writes the slot answerable, in the kind it was allocated ([`planning.py`](../backend/question_generation/planning.py)) | on the labelled drafts of the v0.3.12 build the other kinds were answered two times in three against under one in two; the plan replays to a kept-answered share of 0.253 from 0.342 (interval 0.158 to 0.356); a topic of 120 slots at today's mix plans 18 factoid and 18 reason unanswerables where it planned 4 or 5 of each of eight kinds. Answerable slots are unchanged. Not re-measurable offline beyond that replay: it is read on the next build |

### Fixed in v0.3.18: dash ranges

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A range written with a dash was refused when the recovery gave its two ends apart | a key holding "100–110 m" or "8–10 Werktage" was refused `not_recoverable` when the verifier's recovery wrote "mindestens 100 m, höchstens 110 m": the dash range was one figure token, so the key asserted a value no recovery could hold, and a key with no content word fell to raw containment, which wanted the dash back | `agrees()` reads a dash range (the en dash; the tokenizer already splits an ASCII-hyphen range into its two figures) as its two ends and checks the words around it by lemma; the ends the recovery states count only against a key that holds a range, so a key naming one figure, "110 m", does not agree with "100–110 m"; a range still needs both ends and its unit ([`gates.py`](../backend/question_generation/gates.py)) | over 919 stored recoveries of the v0.3.12 and v0.4.0 builds two verdicts move (8106 and 7735), both wrong refusals; no right refusal lost; none of the v0.3.0 rows moves |

### Fixed in v0.3.19: answer_incomplete

| Defect | Found | Fix | Measured |
|---|---|---|---|
| `answer_incomplete` refused complete list keys | 39 of the 43 usable questions the gate cost on the v0.3.12 build were complete terse keys: the verifier answers in a full sentence that restates the question, so a terse key held under 0.4 of its content lemmas | the share test still fires first, but the key is refused only when the recovery also names an item the key and the question lack: a conjunct, a marked line, a `;` part, a figure written in digits, or the direct object of a coordinated verb phrase ([`gates.py`](../backend/question_generation/gates.py), [`checker.py`](../backend/question_generation/checker.py)) | replay on the stored recoveries: the v0.3.12 build frees 31 of 75 refusals (27 wrong, 3 partly right, 1 right; 80.6% usable), the v0.4.0 build 23 of 67 (19, 4, 0; 73.9% usable); over 100 paired hash salts with the release-size scan the release keeps its size (2.9 rows fewer) and loses 0.36 invalid rows (interval below 0), the weld rate moving by +0.3 points (interval includes 0); without the scan the release shrinks by about a hundred rows, because more pool rows tighten a type quota. 16 wrong refusals on the v0.3.12 build (15 on v0.4.0) stay, where the recovery names the key's items in other words |

### Fixed in v0.3.20: question kinds

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A question's kind was implied by its number of cited passages | the plan, the writer and the checker told a question that spans two passages from one that does not by counting citations, so a new kind of question (a compound one, a false-premise one) had no place to be named | every slot the plan deals carries a kind, `single` or `needs_both` today, held in `kinds.py`; the kind chooses the writer's instruction and response shape and the checks a draft gets, and is stored in a new `questions.kind` column, backfilled from the passage scope and narrowed to `single` by `make questions-rescore` when the citations come to rest on one passage; `QUESTIONS_KIND_MIX` (optional) shares the kinds out over the slots that span, and refuses a kind that deals one passage ([`kinds.py`](../backend/question_generation/kinds.py), [`planning.py`](../backend/question_generation/planning.py)) | no behaviour change: every plan, prompt and verdict is byte-identical to v0.3.19's over 3,120 plans and every writer prompt, and the scoreboard moves no value |

### Fixed in v0.3.21: a band follows its kind

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A question's band followed the spread of its passages whatever its kind | the band was read from the points of the cited facts alone, so a kind that fixes its own difficulty (a compound question asks two lookups) could not say so | `criteria_of` takes the stored kind; where a kind's entry in `KINDS` sets a band that band holds, and every other kind keeps the points rule; a rescore and the checker's verdict both pass the stored kind ([`models.py`](../backend/question_generation/models.py), [`kinds.py`](../backend/question_generation/kinds.py)) | no kind sets a band yet, so no stored band moves: replayed over all 1,753 questions of the v0.3.12 build, single and needs_both questions band exactly as before |

### Fixed in v0.3.22: compound questions (off by default)

| Defect | Found | Fix | Measured |
|---|---|---|---|
| No question asked two separate things, one from each of two passages | a chatbot is also asked questions that join two unrelated lookups, and the pipeline had no kind for them: such a draft was refused as `compound` for its two question words | a `compound` kind, off by default: the slot is dealt the passage of its topic and its bridges that shares least with its head and asks two separate things joined by "and"; the writer returns the two halves, each is recovered from its own passage alone, a question claiming a relation between its halves is refused as `wrong_type`, the key is held to its form one half at a time, and a slot dealt one passage is written as `single`; the stored kind is `compound`, banded medium (writer prompt 16; [`kinds.py`](../backend/question_generation/kinds.py), [`selection.py`](../backend/question_generation/selection.py), [`checker.py`](../backend/question_generation/checker.py)) | on pairs built by its calibration script, not through the deal: 8 of 8 fixtures written as two halves, and 28 of 48 pairs of the v0.3.12 build accepted (German 14 of 24, English 14 of 24); read blind, the 28 were all compound, none a false join, 21 usable (75%, against the 80% bar; English 64% against 70%) and 19 with a right key (68%, against 75%), so the quality bars are not met. The real path through the deal, and the review's fixes since the calibration, are not measured, and compound stays off until they are |

### Fixed in v0.3.23: bridge relations stored and shared

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A bridge kept neither the relation it named nor the question it was tested with | prompt 6 makes the model name one of six relations and write the question only both passages answer, and neither was stored: a re-judgement could not re-test the bridge and a later stage could not tell a contrast from a definition | the six relations move into one table, `llm/spans.py`, read by the bridge pass and the question checker, and the quote check moves into `nlp/text.py`; a nullable `facts.bridge` column keeps `{relation, question, answer}` for every bridge prompt 6 or later writes, refused ones too, constrained to bridges, and `make extract-revalidate` reads it back ([`spans.py`](../backend/llm/spans.py), [`facts.py`](../backend/database/qa_generator/facts.py)) | no number moves: every prompt digest and every output is unchanged and the scoreboard moves no value; every non-`none` bridge carries its relation. A bridge prompt 7 that writes each relation in its own form missed its calibration bar (41.7% correct against 42%, German 29% against 30%, wrong and unsupported 13.9% against 13%) and is not in this release |

### Fixed in v0.3.24: answer-check readings

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A numbered list's markers counted as figures in `answer_incomplete` | the figure branch of the gate read the whole recovery, markers included, so a recovery set out as "1. card fraud\n2. unpaid fees" against a key and a question carrying both items named 1 and 2 as figures the key lacked, and a complete key was refused whenever its coverage was under 0.4; a dash, a bullet or an a)/b) list was fine | `unnamed()` strips a numbered or bulleted list's marker at the start of each line before it reads the recovery; a figure inside an item still counts ([`gates.py`](../backend/question_generation/gates.py)) | found by property and mutation tests; the replay of the answer_incomplete refusals is unchanged (v0.3.12 frees 31, 27 wrong, 3 partly, 1 right, 80.6% usable; v0.4.0 frees 23, 19, 4, 0, 73.9%) |
| A range's unit was not matched when the tagger read it as a number | the key "1–3 cm" was not recovered by "between 1 and 3 cm" (nor "8–13 kg", "8–13 hours", "3–63 days"), because the tagger gives the unit a different part of speech in the recovery (a number) and in the key (a noun), so its lemma never came back; "m" and "minutes" passed | the unit after a dash range must come back by its surface form or its lemma, whatever part of speech the tagger gives it ([`gates.py`](../backend/question_generation/gates.py)) | found by a property test over recovery styles (between, to, from-to); the replay over 919 stored recoveries still moves 2 verdicts (8106 and 7735), both wrong refusals, and loses no right one |

### Fixed in v0.3.25: reverify keeps the kind

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A stored compound question was refused when reverified | the re-check passed no kind to the structural checks, so a stored compound question was read as a single-passage one and refused for its two question words (`make questions-reverify`); the checker had always passed the kind | the re-check holds a stored question to the kind it was written as, so a compound question is no longer refused for its two question words while a single-passage row with two questions still is ([`service.py`](../backend/question_generation/service.py)); found before compound is dealt by default | red tests on bank and shop rows in German and English, green after. Known gap: a re-check cannot re-run the compound checks of the halves, because the halves are not stored; it only skips the two-question-word refusal |

### Fixed in v0.3.26: compound questions dealt by default

| Defect | Found | Fix | Measured |
|---|---|---|---|
| Compound questions were built but never dealt | the compound kind of v0.3.22 had no weight in the kind mix, so no build wrote one | the kind mix defaults to `needs_both:5,compound:1`, one spanning slot in six dealt as compound; `QUESTIONS_KIND_MIX=needs_both:1` turns it off ([`config.py`](../backend/question_generation/config.py)) | measured on pairs built by the calibration script, not through the deal: 28 of 48 accepted and, read blind, 28 of 28 compound, none a false join, 75% usable (the bar was 80%) and keys right 68% (the bar was 75%). The real path through the deal is not calibrated yet; the corpus rebuild on this release measures it |

### Fixed in v0.3.27: the release size

| Defect | Found | Fix | Measured |
|---|---|---|---|
| The release draw bisected for a size that fills | the bisection assumes a size fills whenever a larger one does, and it does not: a thread's follow-ups overfill their kind, so whether a size fills flips from one size to the next, and one failing middle size sent the bisection down for good; 43 of 100 hash salts of the v0.3.12 pool released under 200 rows, against 6 of v0.3.0's | the draw scans sizes down from the largest the pool's supply allows and keeps the first that fills ([`balance.py`](../backend/question_generation/balance.py)) | over 100 paired hash salts of the v0.3.12 pool: none under 200 rows, 139 rows more on average (126 over 200 salts), the weld rate +0.5 points with an interval that includes 0 (-0.6 to +1.5; over 200 salts +0.1, -0.5 to +0.8), invalid rows per 100 -0.002, the German share unchanged, the worst band deviation 0.62 to 0.27 points; the stored salt-0 releases are unchanged. On the v0.4.0 pool the weld rate rises by +0.30 points (0.08 to 0.52), above 0, which the current pools overrule. A scan over a pool of 10,000 rows takes minutes where the bisection took seconds; pools are one to two thousand rows today |

## Found on the v0.4.0 rebuild of 2026-10-18

The code of v0.3.8 rebuilt the same two PDFs as v0.4.0, a build that was
reviewed in full and not released: 886 accepted questions, 318 released.
Its released questions were more usable than v0.3.0's (82.7% against 79.0%)
and its keys more often correct (87.0% against 80.1%), but more of its English
two-passage questions welded two unrelated rules (26.6% against 17.3%), its
release was smaller (318 against 343), and its topics were looser. A second
review read what the first had left: all 664 rejected questions (a gate was
wrong on 33.7%, against 37.9% in v0.3.0) and all 532 refused facts. Each
worse figure was traced to its cause; the fixes below were measured on the
labelled rows of both builds and, where a model reading changed, calibrated on
Azure before they went in. [measurements.md](measurements.md#the-v040-rebuild-of-2026-10-18)
holds the build's figures.

### Fixed in v0.3.9: two-passage questions

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A bridge fact was offered beside an unrelated claim | the deal tested only the first fact of a passage for spanning two passages, and the first is a single claim wherever the passage holds one; such questions welded 28 of 98 times against 4 of 56 for a bridge offered alone | a bridge is offered alone, whichever passage it was dealt from ([`selection.py`](../backend/question_generation/selection.py)) | on the stored rows, the 98 questions of this kind are the cell it removes |
| The bridge prompt taught side-by-side claims | its right example was "response times are stated separately for standard and urgent requests" | the right example is a claim one excerpt changes by defining what the other's rule applies to; side by side is now a wrong example (bridge prompt 5, [`bridge.py`](../backend/extraction/extractors/bridge.py)) | the same 48 passage groups, both prompts, read blind by one reader: correct bridges 2 of 29 (7%) became 5 of 41 (12%), not bridging 62% became 56% |

### Fixed in v0.3.10: facts

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A rule written as one statement joining two actions was lost | 152 of the 186 `not_atomic` refusals were judged wrong; the counter is right that two finite verbs are two claims, but nothing asked for the split facts | the statements the model wrote and the checker refused as `not_atomic` go back to the same model once per passage, under a repair prompt of their own (`repair-1`), and what it writes faces every check, the dedup gate and the cap; the refusal is stored as it was ([`extractors/llm.py`](../backend/extraction/extractors/llm.py), [`service.py`](../backend/extraction/service.py)) | Azure, 60 passages holding 78 refusals: 166 facts written, 143 validated, 120 of those correct (84%; German 76%, English 90%), and the refused claims recovered in full or mostly in 48 of 60 passages |
| A condition the parser hung as a conjunct counted as a second claim | "but only if it has not been executed" and the members of "es sei denn, A und B" were counted as claims of their own | a conjunct opened by its own subordinator, and a clause joined to the case an exception or an alternative leaves out, restrict the rule ([`nlp/analysis.py`](../backend/nlp/analysis.py)) | 8 refusals of the v0.4.0 build and 9 of v0.3.0 freed, every one judged a wrong refusal; no right refusal lost |

### Fixed in v0.3.11: topics

| Defect | Found | Fix | Measured |
|---|---|---|---|
| One seeded topic fit was kept unread | the factorisation's seed decides how alike a topic's members come out, by as much as two rebuilds differed; v0.4.0's draw was the second loosest of nine | the fit draws eight factorisations seeded from `TOPIC_RANDOM_STATE` on and keeps the one whose members are most alike in the tf-idf space it already builds ([`topics.py`](../backend/topic_modelling/topics.py)); the same passages read in the same order still keep the same draw | over the v0.4.0 passages, members came out 1.67 times as alike as the corpus in German instead of 1.46, and 1.55 instead of 1.44 in English; German topics looser than 1.3 times fell from 3 to 1, English stayed at 4 |

### Fixed in v0.3.12: unanswerable questions

| Defect | Found | Fix | Measured |
|---|---|---|---|
| The settles reading quoted the answering words and still said silent | its prompt named the label it expected, asked for the quote before the verdict, showed no answer given in another form than asked, and the elsewhere call never saw the cited passages that set up the case | verifier prompt 6: a role that no longer says the question was written to have no answer, the best reply a chatbot could give before the verdict, examples of an answer in another form and of a categorical rule ruling out what the question assumes; the elsewhere call reads the cited passages beside the probed ones, a quote they hold being refused as answerable after all ([`verifier.py`](../backend/question_generation/verifier.py), [`checker.py`](../backend/question_generation/checker.py)) | Azure, 179 labelled drafts of the v0.4.0 build, old and new prompt on the same day: answered drafts caught 59% to 70%; the share of kept unanswerables the corpus answers 0.40 to 0.34 (German 0.41 to 0.37, English 0.38 to 0.28); open drafts refused 7.5% to 10%, the accepted ones newly refused at most 28% usable. Still far above the 0.15 a release share needs |

### Deferred, with the reason

| Defect | Why it stays open |
|---|---|
| Two-passage questions that weld two rules sharing only a word or a party | A verifier judge asked whether a question is about one situation was calibrated on Azure over all 268 labelled two-passage questions of both builds: precision 0.84, half of the welds both readers saw caught, 6 of 179 sound rows refused. It misses the bar in German (recall 0.43) and on the rows left once a bridge is offered alone, where what it refuses is 36% usable, above the 35% a tightening may remove. A per-passage round trip would catch at most a fifth of the welds |
| A count of the items in one passage's list is asked as an aggregation | Refusing such counts would remove rows 50% usable across both builds (6 of 12), above the 35% a tightening may remove; relabelling one as an enumeration does not change what it asks |
| Comparisons refused as `wrong_type` | Freeing them needs the content check the weld judge above would be |
| `heard()` silences an answer on any question with a question word | It fired 4 times, 3 of them wrongly; reading it for reasons only would also undo a right silencing a test pins, for at most 2 questions |
| The elsewhere probe cuts each ranking before fusing them | No measured miss at the depth it reads |
| The unanswerable writer returns no evidence of why its question is open | The writer fails on about 61% of its drafts; a change to its prompt can be measured only by writing questions, which needs a calibration of its own. Unanswerable questions are not released |
| Topics listed by every membership over the floor | Listing a topic by the passages it dominates changes the catalogue, the Topics page, the exports and the review's own measure, for no failure measured on questions |
| Validated facts read a few points less correct than v0.3.0's in blind tests | Over all validated facts the estimate is 85.6% against 86.7%, within reader and sampling noise: most of the blind tests' gap fell on statements byte-identical in both builds. One small cause is real: atomic prompt 12 names the heading trail as a fact's situation, so a passage under a wrong heading now writes that heading into its facts (about 0.2 points). Low |
| A duplicate refusal can name a twin since deleted | 35 of 180; the replay keeps the refusal against a current twin but leaves the old id in its reason. Low |

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

### Fixed in v0.3.4: round trip, reasons and typing

| Defect | Found | Fix | Measured |
|---|---|---|---|
| The entailment rescue overrode a verifier that found nothing | a key the verifier read as not in the passages was rescued by scoring the bare key against each passage | no rescue after that reading ([`checker.py`](../backend/question_generation/checker.py)) | 9 accepted questions refused, 1 of them usable; released invalid 11 to 9 |
| The round trip asked for what only the writer was shown | a name the question or every heading trail carries, or a lemma only the headings carry, had to come back | given, unless the recovery says more than key and question; figures never ([`gates.py`](../backend/question_generation/gates.py)) | 7 wrong `not_recoverable` refusals freed, 0 right lost; 5 accepted, all usable, none welded |
| A German adjective tagged as an adverb did not come back | `kostenlos` predicative against `kostenlose` | a lemma comes back under an adjective or adverb, never negated | included above |
| A set of kinds written as adjectives refused as one thing | `enumerates` counted noun phrases only | a coordination with no noun phrase is a set, unless a conjunct is a verb or a number | 2 wrong `wrong_type` refusals freed, both usable, 0 right lost |
| German *wo-* question words missed by `compound` | `Worauf …, und was …?` read as one question | a per-language table of question adverbs | 1 question moves between refusal codes; no accepted one changes |
| The shadow coverage reading stored on half the answers it applies to | 75 of 156 | stored on every eligible answer, still in shadow | 171 readings, 0 verdicts moved |

### Fixed in v0.3.5: release record and unanswerables

| Defect | Found | Fix | Measured |
|---|---|---|---|
| The release draw left no record | the balance ran with no trace, and the twin pairs it judged were logged only as counts | a trace with one span per twin round, one log line per judged pair with both ids and the verdict, and each bucket's distance from its quota ([`service.py`](../backend/question_generation/service.py)) | — |
| A correct answer silenced because its quote was stitched | a quote taken from two bullets, two cells or a passage and its continuation is not one unbroken run, so the answer was ignored and the question kept as unanswerable | the quote is looked for piece by piece, each piece as whole words of one shown passage ([`checker.py`](../backend/question_generation/checker.py)) | 7 kept unanswerable questions refused, all answered by the corpus; false-omission rate 0.414 to 0.405 in German, 0.456 to 0.431 in English; released invalid 9 to 8 |
| A quote matched inside a longer word | `Ja` found in `Jahresgebühr` settled a question | pieces match on word boundaries | in the red tests |

### Fixed in v0.3.6: parsing and chunking

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A re-chunk deleted every passage, and the facts and questions on them | a parsing fix forced a rebuild of every fact and question | a passage whose text, section path, sentences and cells are unchanged is kept with its id, facts and topics ([`chunking/repository.py`](../backend/preprocessing/chunking/repository.py)) | one transaction; the table's comment corrected by a comment-only migration |
| Hidden labels survived into passages and headings | a clipped word counted as shown if any of its characters lay inside any visible glyph | a character counts as shown only where the same character sits at the same place in the visible read ([`parsing/pipelines/pdf.py`](../backend/preprocessing/parsing/pipelines/pdf.py)) | 13 passages change (6 German, 7 English), all tagged by the review |
| A continued table stopped at a row the converter flagged as a header | a page-break continuation became a second table | the row joins as data when it is set in the first table's data type and its cells match that table's column types | 3 German passages change, all tagged; two schedules of the same width stay two tables |
| List depth lost at column and page breaks | depth compared absolute left edges across columns | depth measured from each column's own edge, read from text and list blocks only, and no new level across a break ([`chunking/passages.py`](../backend/preprocessing/chunking/passages.py)) | 7 passages change (4 German, 3 English), all tagged, none of those the review judged right |
| A lone conjunction promoted to a heading | `oder` between two list items split the passage | read as text between two items or paragraphs of one passage, through a per-language table ([`chunking/furniture.py`](../backend/preprocessing/chunking/furniture.py)) | 7 German passages change, all tagged; English unchanged |
| A joined block or table cited only its first page | — | it cites every page it spans | pages only; no text changes |
| `third- party` mended to `thirdparty` | — | a hyphen is kept where the document prints the compound with it elsewhere ([`nlp/text.py`](../backend/nlp/text.py)) | 0 stored passages |

Across both PDFs the release changes 30 passages, 20 German and 10 English, all but one tagged as defective by the review and the last a target of the conjunction fix; the review judged none of them right. They carry 237 facts and 86 questions, which a re-chunk replaces. An independent review then tried every rule on 33 bank fee schedule and shop returns layouts: against v0.3.2 the release reads 11 better, 21 the same and 1 worse, a `re- sign` that becomes `re-sign` where the document prints the compound.

### Fixed in v0.3.7: topics and the scope of a fact

| Defect | Found | Fix | Measured |
|---|---|---|---|
| A topic's name carried onto the wrong topic | a name moved wherever 12 top terms overlapped by 0.4, order ignored, so one topic held penalties under a free-kick name, and carried names skipped the naming rules | a person's decision moves only to the topic holding most of the same passages, both ways and as a majority of what the old topic held; a model's name is never carried; a decision with no match is dropped and counted ([`topics.py`](../backend/topic_modelling/topics.py)) | on 8 refits: 17 carried, 0 wrong, 0 missed (top-term overlap: 22 carried, 10 wrong) |
| A fit reported itself stale the moment it was made | the stale check counted every passage, the fit only those carrying a fact | one shared rule for both ([`repository.py`](../backend/topic_modelling/repository.py)) | a fresh fit is no longer stale |
| A name or coverage choice saved while a fit ran was overwritten | the fit wrote back what it read when it started | carried again, under a lock on the rows the fit replaces | an undo during a fit, and a review answer dated before the fit, are still not carried |
| Smaller topic bookkeeping | the count of passages in no topic ignored the nearest-topic placement; a language with no passages kept its topics; topic naming respelled a correctly printed word (`Masse` to `Maße`) | each fixed, a dropped decision of a vanished language logged and counted | — |
| Facts dropped the scope a heading or a list's lead-in sets | lead-ins lost 133 times, conditions 117, exceptions 53 in the validated facts | atomic prompt 12 names the heading trail as the situation a rule holds in and keeps a closing lead-in (*the only exceptions are*) as one fact; digest prompt 5 keeps *should* and *may* ([`extractors/llm.py`](../backend/extraction/extractors/llm.py), [`extractors/digest.py`](../backend/extraction/extractors/digest.py)) | a calibration on 40 passages, one judge over all three: facts stated correctly 60.8% to 69.4% in German and 79.0% to 84.0% in English, scope lost per 100 facts 34.5 to 25.2 and 25.0 to 16.0, `not_atomic` refusals unchanged; one new failure, a heading pasted into a fact as a clause |

### Fixed in v0.3.8: security, the frontend, orchestration and the docs

| Defect | Found | Fix |
|---|---|---|
| Settings accepted values no service could run with | `nan`, a misspelt *true*, an unbounded topic count or seed were stored, and the service failed later | refused when written ([`settings/env.py`](../backend/settings/env.py), [`settings/catalog.py`](../backend/settings/catalog.py)); a value already stored outside its bounds is shown with a warning so it can be corrected, and a stored `nan` no longer takes the question plan down |
| The workbook export wrote formulas | a cell starting with `=` was a live formula in a spreadsheet | written as text ([`export.py`](../backend/question_generation/export.py)) |
| The API docs page loaded a floating script | `/docs` fetched the newest Swagger assets from a CDN | pinned assets; `/redoc` removed |
| Stop stopped only the newest run | an older live run kept going | every queued or started run is stopped, one already stopping is said to be ([`routes/pipeline.py`](../backend/api/routes/pipeline.py)) |
| A run whose worker died blocked the queue | no run monitoring | Dagster's run monitoring is on, and a cancelling run counts as going |
| A topic `PATCH` reset what its body left out | — | it changes only what it names |
| A failed worker rebuild asked the model again every five seconds | — | it backs off, per version |
| The review sample drew questions already reviewed | — | only unreviewed ones |
| Annotations stopped for good after one failed flush | — | they resume |
| A span named the worker's process run, not the run that queued its row | — | every span of a row names the run that queued it |
| `make eval-score` scored a reader production does not run | — | it scores the production reader |
| Deleting every document forgot the upload history first | — | it forgets uploads last; the document listing says when it is cut |
| The configuration panel wrote stale values | it sent the version read at save, kept old values after a change elsewhere, sent an untouched `0.30` as `0.3` and showed `0.985` as `0.98` | it sends what it drew, redraws after a change, and keeps each number as written ([`configure.py`](../frontend/lib/configure.py)) |
| Smaller frontend faults | a fit could be confirmed twice, shadow readings were shown as gates, a refused write replaced the page, a new search kept the old page | each fixed |
| The stack trusted any host name and any missing secret | Streamlit accepted any `Host`; compose started with empty passwords | Streamlit answers only `localhost` and `127.0.0.1`, the only names it is published on; compose stops and names a missing secret |
| Docs that misled an operator | 157 statements in the docs, the READMEs, the Makefile help, the settings page and the wiki no longer matched the code | each corrected, the operator-facing ones pinned by tests ([`test_docs_pinned.py`](../tests/static/test_docs_pinned.py)) |

### Deferred or low, with the reason

| Defect | Why it stays open |
|---|---|
| Explanation-form keys are not held to completeness | The only bar that separated complete from partial keys passed at 7 rows, one more usable row would fail it, and German commas inflate the item count it reads |
| Section paths are wrong at scale | Docling now offers public heading options, but every setting tried moves 200 or more paths the review judged right while fixing about 160 wrong ones. A general fix needs a re-levelling pass from the PDF's own styles, checked against a judged set |
| `make doctor` checks only the container's shared model and verifier | Whether containers may call a hosted model is a deployment policy to settle first |
| Six readings that would have freed most wrong fact refusals | Measured on this rulebook they freed 47 wrong refusals for 0 right ones: a pronoun resolved within its own clause, English `this` read as resolved, an `it`/`es` before an *if* clause read as a placeholder, a subjectless *but* clause read as part of one claim, a German verb-first condition, and a name borrowed from an earlier sentence. An independent review then ran 119 bank and shop sentences a validator must refuse through them: they admitted 46. They read agreement where a reader needs to know which of several nouns is meant, so they fail the rule that a fix must hold for any corpus. A general fix needs coreference that sees competing antecedents |
| Duplicate refusals compare statements without their headings | Embedding each statement with its heading trail frees 19 to 31 wrong refusals but makes 71 to 121 new twins on the stored facts. It waits for facts that carry their scope (R23) |
| Two extract workers can both keep one claim | Each probe sees only committed facts; closing it needs a lock across workers or a uniqueness rule on the statement |
| Glossary definitions get no facts | Measured on the v0.3.6 passages, the best rule found, a one-line paragraph under a heading shorter than it, reads 42 of 43 glossary passages, but 14% of what it reads are cross-references and one-line notes, and a four-word heading limit is a number fitted to one corpus. Telling a cross-reference or a caption from a definition without a word list needs a signal the parse does not give yet |
| A circular reason caught only below a fixed share of new words | Every bar that separates circular from sound reasons on this corpus sits in the gap between two of its own share values (3/7 and 4/9), and the same sentence scores differently in German and English; it would be a bar fitted to this rulebook |
| Comparisons refused as `wrong_type` | Reading the two sides by order and parallel structure frees 43 rows, but they are 67% usable, under the pool's 70%; it needs a model-backed replay before it ships |
| Smaller structural gates: figures read from the question for `explanation_unusable`, pointers the question resolves for `unanchored`, `leaks_source` | Each was re-measured: 4 of 6 and 2 of 3 of the rows they free are usable, under 70%, and `leaks_source`'s rows carry no stored judgement to replay |
| Unanswerable questions the corpus answers are still kept | The false-omission rate is 0.40 in German and 0.43 in English, against the 0.15 a release share needs, so `QUESTIONS_RELEASE_UNANSWERABLE` stays 0. Reading `heard()` only for why-questions regresses reason questions asked without a why-word; holding back a reply that is silent but quotes something removes rows half of which are usable; a second model and a wider probe would cost a calibration and, on the best estimate, still leave the rate near 0.2 |
| Follow-up gates read ids, not content | Checking a follow-up against every earlier turn's facts would remove rows 53% usable; judging each follow-up against its own thread belongs with the release-draw change above |
| The release reads no quality signal | The stored confidence does not separate invalid or welded rows, so weighing the draw by it would move the release on noise |
| A wrapped fee-table row with an empty first cell merged into the row above | Requiring every filled cell of the continuation to open in lower case stops the merge, but breaks wraps that open on a bracket (`(inkl. MwSt.)`) or a German noun; no rule that tells the two apart was found |
| A struck full stop under 2 pt kept | A strike length relative to the type size catches it, but also reads a 1.5-pt mark over a decimal comma in small type as a strike (`0,10 EUR` to `010 EUR`) and slows pages of dot leaders three times |
| A list nested right at the top of a column stays flat | The guard that keeps depth from jumping across a break cannot open a new level there |
| Bridge facts that are not bridges | A model judge shown both passages caught a third of the unsound bridges, and refusing even exactly the bridges the review called unsound would remove questions that are 55 to 62% usable, which the rule for tightening a gate forbids. A fix belongs where bridges are written, in the bridge prompt and the pairing of passages, and has to be measured on new extractions |
| Imprint and contact passages yield questions | A share of contact text was fitted to this corpus, and a count of contact kinds against claims skipped one-line complaint rules and missed national phone numbers on bank and shop text. A general fix needs to read what a passage asks of its reader |
| Topic membership is loose (a passage sits in three topics on average) | Every floor tried, relative ones included, removed questions that are 46 to 78% usable |
| Generated German writes *ß* where the corpus writes *ss* | A spelling variant of one corpus. Low |
| Writer meta-text and gender drift | Needs a rule in the question-writing prompt, which changes only with a calibration. Low |
| The API, Streamlit and Dagster have no authentication | Each binds to 127.0.0.1, so an attacker needs another local account; adding sign-in is a feature, not a fix |
| Dagster's corpus job lacks the bridge pass `make corpus` runs | It waits for a bridge pass worth running unattended (see the bridge entry above) |
| Uploaded PDFs are opened inside the API process, with no page or time limit | Moving the read into a worker changes the upload contract |
| Images and installs are not hash-pinned; SeaweedFS and redis accept any caller on the stack's network; workers hold more credentials than they need | Infrastructure changes beyond a patch release |
| A language missing from a word table silently disables a gate | A static test holds every table to `NLP_MODELS`; a start-up check would need a registry of tables |
| Review push loads each question's facts one query at a time; some frontend helpers repeat each other | Speed and tidiness, no wrong result |
| Tooling odds and ends | The CI cache key hashes the whole Makefile; an unused SeaweedFS UI container. Low (`make dev`'s unbounded wait for Postgres is fixed in v0.4.4) |

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

A hand review of the v0.3.0 rebuild checked each of the 41 defects below
again: 19 are fixed, 16 fixed in part, 2 not fixed (circular *why* keys,
release twins) and 4 worse than before (`not_atomic` refusals, duplicate
refusals, repeated-heading and figure-only passages, wrong type labels). What
the v0.3.x releases fixed since is under
[Found on the v0.3.0 rebuild](#found-on-the-v030-rebuild-of-2026-10-16).

### Parsing

| Defect | Found | Fix in v0.3.0 | Measured on the reviewed rows |
|---|---|---|---|
| A struck word survived, or took its neighbours with it | struck text kept in 5 German and 6 English passages; 5 passages over-stripped | Strike-through read per character; a bracket or comma beside a deletion stays; apostrophes and dashes folded before matching | the passages' struck text gone in the replay; what is left is source quirks |
| Text the page hides read as body text | 14 passages of signal-diagram labels (8 German, 6 English) | Text the page clips out of view is dropped | a prototype's replay cleaned 11 of the 14; on the v0.3.0 rebuild 1 of the 14 is clean; a label printed in view stays |
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
stage again, with the same models. Nobody read it in full when it was written
up: the figures below are counts over its tables, except the weld rate and the
wrong duplicate refusals, which a later hand review of the rebuild read: every
accepted question citing two or more passages, and every duplicate refusal.
[measurements.md](measurements.md#the-v030-rebuild-of-2026-10-16) has the run
itself. Each cell reads German, then English.

| | v0.2.2 rebuild | v0.3.0 rebuild |
|---|---|---|
| Letter-spaced section paths | 178, 97 | 0, 0 |
| Passages carrying a validated fact | 358, 331 | 361, 339 |
| Validated facts, bridges aside | 1,976, 1,602 | 1,692, 1,488 |
| `not_atomic` refusals per 1,000 facts | 17.8, 56.4 | 32.1, 61.4 |
| `unresolved_reference` per 1,000 | 42.4, 48.4 | 30.1, 21.0 |
| `unsupported_addition` per 1,000 | 19.1, 45.4 | 9.2, 18.2 |
| Duplicate refusals, wrong and partly wrong | 13 and 22 of 231, all read | 35 and 27 of 194, all read |
| Atomic facts dropping *only*, *if*, *unless* or *except* | 16.6%, 30.9% | 10.8%, 28.2% |
| Summaries opening on "the excerpt" | 52%, 75% | 0%, 0% |
| Bridge facts | 0 | 249 |
| Passages carrying a fact that no question cites | 9, 28 | 17, 11 |
| Accepted questions citing two or more passages | 270 of 837 (32%) | 183 of 871 (21%) |
| Of those, welded | 128 of 270 (47%), all read | 33 of 183 (18%), all read |
| Released | 321 | 343 |
| Released `hard` | 100 | 23 |
| Released citing two or more passages | 209 | 91 |
| Released with no answer | 32 | 0 |

Fewer facts now cover more passages: the atomic prompt keeps a rule with its
conditions and exceptions in one statement, where it used to write each
piece as a fact of its own. The validator refuses more of these joined
statements as `not_atomic`, in German nearly twice as often as before.
Passages carrying a validated fact still rose in both languages.

A hand review of every accepted question citing two or more passages found 33
of 183 welded (18%). Of the 91 released ones, 17 are welded, against 104 in
v0.2.2. Each weld joins two rules that share a subject but not a situation,
such as two signals asked about as one *why*. The spot check first reported
here read 6 of 40 as welded; the full reading finds 9 of the same 40, and the
sample held 24 released questions, not 22.

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

**The enumeration gate reads two properties of one thing as two kinds.**
`enumerates` in [`gates.py`](../backend/question_generation/gates.py)
counted noun phrases only, so a set of kinds written as adjectives,
`politische, religiöse und persönliche`, was refused as one thing. Since
v0.3.4 a coordination with no noun phrase is a set where neither a conjunct
nor what it is joined to is a verb and no conjunct is a number, so `complete
and signed` and `geöffnet oder benutzt`, two things said of one document or
article, and `one or two days`, one span of time, are still refused. On the
v0.3.0 rows this passes 2 wrong `wrong_type` refusals, both usable, and
loses no right one; whether the later gates keep them needs a
phrasing-judge call the run never made. The parse cannot tell a kind from a
property, so `schnell und kostenlos` and `unverzüglich und schriftlich` pass
as two items; the round trip still refuses such a key where the verifier
gives back one of them, because a key with no content lemma has to be held
in its recovery rather than hold it. The comparison half of the same fix is
held until a model-backed replay measures it.

## The written-count gate has the digit rule's blind spot

Of the 3 accepted rows the written-count gate moved, 2 were sound: `zwei
Lernziele` (question 4255) and `zwei Faktoren` (5355) count something their
own facts state, and only happen to equal the number of facts cited. The digit
rule refuses the same shape: `2 coverage items` (1409).

**Fixed in v0.2.2, in part; open.** A count a cited statement states is
exempt from both rules. A true count that only equals the number of facts
cited, because each fact states one item, is still refused, which is the
blind spot itself. On the v0.3.0 rebuild 4 of the 28 `malformed` refusals were
this, all usable: questions 3248, 3773 and 4336, and 4316, whose count only
its passage states. It is the part
[The count rule misread stated counts](#the-count-rule-misread-stated-counts)
left open, in [`gates.py`](../backend/question_generation/gates.py).

## Known trade-offs

Not a defect: a rule doing what it is for, at a cost in sound rows.

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
