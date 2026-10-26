# Known bugs

Defects in what the pipeline produced, with the fix that closes each or the
reason it is still open. Open defects come first, then deferred items and
withdrawn attempts, then the fixed defects by release.

Figures come from hand reviews of full runs of the *Laws of the Game 2026/27*
(football rules), German and English, and from one earlier run over 16
certification syllabi. [measurements.md](measurements.md) holds the runs' own
figures. "Usable" means a reviewer verdict of good or minor. Reviewer verdicts
are model judgements, accurate to about five points.

A fix changes what the next run writes. Stored rows improve only through the
re-runs that operations.md lists for
[v0.2.2](operations.md#upgrading-to-v022),
[v0.3.0](operations.md#upgrading-to-v030) and
[v0.5.2](operations.md#upgrading-to-v052).

## Open defects

Each entry gives the symptom, one measured effect and the status. `Release
rows` are rows of the 2026-10-13 release unless another run is named.

### Two subjects welded under one question word

11 release rows join two subjects with *and* under one question word and
answer each in its own half, so a chatbot answering one half is neither right
nor wrong. Example: *How should tool metrics and test result communications be
handled to support stakeholders without harming the test team's credibility?*
`compound` refuses a weld only where it carries two question words. No fix has
been tried: of the 53 answers with three or more `and`/`und`, no lexical
reading separates these 11 from the 42 sound dense answers.

### Questions that count their own citations

4 release rows name the offer rather than the subject (*Welche Teststufen
werden in den Angaben genannt?*), so the corpus cannot answer them. A gate in
[`gates.py`](../backend/question_generation/gates.py) refuses a *How many*
question whose answer is a count equal to the number of cited facts, in digits
or written out from two to twelve. A count a cited statement states is exempt.
The 4 offer-naming rows are not caught.

### Near-twin questions

12 release rows were spare twins. The duplicate bar depends on what two
questions cite: a shared fact refuses at `QUESTIONS_DUPLICATE_SHARED_COSINE`
(0.88), a shared passage at `QUESTIONS_DUPLICATE_COSINE` (0.93), a different
question word raises the bar, and an answerable question is never the
duplicate of an unanswerable one. Twins that share only a passage and sit
below 0.93 still pass. The closest rule would reject 26 usable questions. They
are pinned as expected failures in
[`test_question_verdicts.py`](../tests/regression/test_question_verdicts.py).
The release asks the verifier about each question's nearest neighbour and
keeps one of each pair it says want one answer. The v0.3.0 release still holds
19 twin groups (43 rows). The shared-fact bar also refuses sound follow-ups
(12 on the v0.3.0 rebuild, all wrongly).

### The written-count gate has the digit rule's blind spot

A true count that only equals the number of facts cited, because each fact
states one item, is refused (`zwei Lernziele`, question 4255). The exemption
for stated counts reads the cited statements, not the cited passages. On the
v0.3.0 rebuild 4 of the 28 `malformed` refusals were this, all usable.

### The comparison gate refuses sound comparisons

`_contrasts` in [`gates.py`](../backend/question_generation/gates.py) splits
an answer at the seam between the two subjects the question names. A sound
comparison whose axis only the question names is refused (rows pinned as
expected failures). On the v0.3.0 rebuild 52 of the 62 `wrong_type` refusals
of comparisons were wrong, 37 of them usable, against 18 of 70 on the v0.2.2
rebuild. Reading the two sides by order and parallel structure frees 43 rows
that are 67% usable, under the pool's 70%.

### A fact may drop its sentence's scope

Validation does not check that a statement keeps its sentence's scope. A fact
validates when it drops a restrictive clause, a negation, "only", one
condition of two or most of a list. 8 such facts were confirmed by hand and 4
questions on them were released. The atomic prompt now keeps conditions,
exceptions and *only* in the statement, which lowered the share of facts
dropping a scope word in both languages.

Three checks were measured and none shipped:

| Check | Result | Bar |
|---|---|---|
| Deterministic marker check | Right on 50 of 109 flagged facts (46%) | 80% |
| NLI entailment check | Right on 10 of 60 sampled | |
| Repair reader (v0.5.0), replayed on 2,861 validated facts | Found 52% of drops (bar 50%); 30% of changed facts had dropped scope (bar 80%); 63% of repairs correct (bar 80%); broke 2.0% of complete facts (bar at most 1%) | see left |

Most false flags added the section heading as a situation. One class held up:
a limit stated in a sentence the fact does not cite (0.68 precision, no harm,
about a quarter of the drops). A design asking only for those is the next
step.

### A two-item key read as a value

A two-item answer joined only by *and* or *und* is read as a value and never
checked for completeness (8 accepted keys on the v0.3.0 rebuild, such as
question 3402). A comma- or semicolon-separated pair with no verb is read as a
list. Checking the item count against an enumerated passage waits for
re-extracted facts.

### Unanswerable questions the passages answer

76 of the 158 accepted "unanswerable" questions of the 2026-10-13 run were
answerable, 8 of the 24 released ones. The `settles` verifier judgement (`make
questions-rejudge` applies it to stored questions) refuses 29 of the 76 and 3
of the 82 sound ones (precision 0.91, agreement 0.68, `azure/gpt-4.1`). It
still leaves about half of the answerable ones as settling nothing:
false-omission rate 0.53 in German and 0.46 in English, against the 0.15 a
release can carry. Quoting, a fused probe of twenty passages, showing the
writer more passages and a second model (0.39 and 0.34) did not close it.

v0.3.0 to v0.4.5 released none (`QUESTIONS_RELEASE_UNANSWERABLE=0`). v0.5.0
releases up to 0.10. On link U's calibration 19 of 60 kept out-of-corpus rows
and 20 of 60 base rows answered after all
([measurements](measurements.md#unanswerable-kinds-v050)), so up to about a
third of released unanswerable questions test a chatbot for saying no to a
question it should answer. `0` releases none. Two decisions stay open: release
only questions a person confirmed, or write unanswerable slots as reason
questions only.

### Reason questions with no stated reason

A reason slot prefers facts whose evidence states a purpose (per-language
marker lemmas), and becomes another kind where the topic states none. The
filter passes a fact when a marker appears anywhere in its evidence. On the
v0.3.0 rebuild 29 of 62 accepted answerable reason questions and 20 of the 34
released ones have a circular key. A bar on a reason key's new words was
measured and held back: every bar that separates circular from sound reasons
sits between two of the corpus's own share values.

### Two passages paired by reading order, and welds

Candidates in one document are ranked by likeness, and a second passage is
offered only where its closest fact is among the topic's closest 2% of fact
pairs (`QUESTIONS_MEETS_SHARE`). The weld share of accepted questions citing
two or more passages fell from 128 of 270 to 33 of 183 (18%), and 17 of 91
released. Likeness cannot separate two rules on one subject. Padded questions
that cite a bridge keep both passages, and 56 of 71 (v0.3.12 pool) still cite
one.

### A list cut from its lead-in

A lead-in cut from its list moves into the list's passage when both fit the
budget, otherwise into the heading trail. 32 passages on both rebuilds still
lost a lead-in. A page join recreated one budget cut (passage 1755 into 1756).
Only a paragraph, or a list item, ending in a colon is taken for a lead-in.

### Stale running foot of another language

The German PDF prints an English running foot over one of its own pages. It
cannot be told from the document's own furniture, so it stays in that passage.

### Signal-diagram labels become passage text

Illustrations print their captions as text and the chunker keeps all body
text. The parser drops clipped text only where the visible page lacks the same
character in the same place (v0.3.6). The v0.3.0 rebuild held 17 passages with
diagram labels and 10 with clipped text, and 6 released questions cite
passages that still carry hidden labels. A label printed in view is body text.

### `restates_question`, the round trip and dangling pronouns

- `restates_question` reads a key written as a sentence around a one-word
  answer as adding too few words: 9 of 24 refusals on the v0.3.0 rebuild were
  wrong, 8 usable.
- The round trip refuses German derivations ("eine Verwarnung" against
  "verwarnt", question 3865), unit abbreviations and list keys: 74 of 105
  `not_recoverable` refusals were wrong, 57 usable, against 38 of 125 on the
  v0.2.2 rebuild. `answer_incomplete` on terse keys and German names the
  tagger does not mark as proper nouns are also open.
- `unresolved_reference` refuses a pronoun whose antecedent sits earlier in
  the same statement when a verb-first condition or gerund puts both in one
  clause: 21 of 77 wrong refusals. Readings that resolved them also resolved
  pronouns no reader could and were withdrawn.

### Difficulty grades spread, not hardness

The band adds a point each for spanning passages, documents and topics, a long
answer and being a follow-up. Hard answerable questions were usable 43% of the
time against 61% for easy ones, and the equal-thirds release draws 83% of the
hard pool. Whether the band should grade spread or hardness is a product
decision.

### The entailment rescue scores a bare fragment

When the round trip fails, the NLI rescue scores the bare key. Scoring
question plus key would rescue 7 usable rows and admit 9 invalid or major
ones. No model (`bge-m3-zeroshot-v2.0`, mDeBERTa-v3, xlm-roberta-large-xnli),
hypothesis shape or threshold rescued more usable than bad rows in both
languages without tuning to the 173 stored rows.

### The release reads no quality signal

The draw reads only answerability, band, kind and thread. It drains any bucket
short of its quota: all 22 aggregations were released, 3 invalid. Confidence
quartiles give 46% to 58% usable, and ordering by confidence would raise the
release from 49% to 52% usable.

### A translation read as furniture

The boilerplate filter reads repetition within one language only (v0.3.0), so
a passage and its translation are not furniture. On a corpus holding one
document per language the filter therefore finds nothing, and the 7 real
furniture passages of the *Laws of the Game* corpus reach the writer. The
extraction prompt's rule against facts about the document itself keeps their
facts out.

## Deferred and withdrawn

Deferred items stay open for the reason given. Withdrawn attempts were built,
measured against a bar written beforehand, and taken out. The defect each
meant to cure stays open.

### Known limits accepted in v0.5.2

| Limit | Why accepted |
|---|---|
| Restoring clauses the bookmark pass hid makes 3 of 33 changed passages read worse (bar 2) (C-007) | 52 clauses of regulation text reaching no passage was the larger loss. The one generic repair misfired on bank layouts |
| Two of 30 football titles stay wrong (C-096) | No generic rule reaches either title |
| A German title setting a product before its noun (*Kreditkarten Bedingungen 2025*) leaves *Diese Bedingungen* refused (C-021) | A conservative miss, chosen over a misfire |
| A fixed `QUESTIONS_RELEASE_SIZE` can put the unanswerable share a row or two in a thousand over `QUESTIONS_RELEASE_UNANSWERABLE` (C-030) | The fix broke two release invariants |
| The parts reading narrows 11 of 19 padded derived rows. The explanation check does not read space-grouped amounts (C-034, C-052) | No honest row is narrowed. The rest needs a model call for the arithmetic check |
| A compound question's halves are stored but not read again by `make questions-reverify` (C-053) | One model call per row |
| On Linux bash a stop gives the row back at once, and a worker stopped during `make corpus` leaves the wait polling (C-006) | Needs host process bookkeeping. Stop a run with `make corpus-hosted-stop` and read its log |
| Not run live: the production `make up` with a row queued per stage, the restore and two-database drills, the stale-lock check in a container, the walk from a fresh clone, the kill mid-row (C-001, C-003 to C-006, C-010, C-013, C-042, C-079) | Each needs a scratch stack. The offline halves pass. Run the Verify lines on the deployed release |
| The 10x load test's single-pass dedup probe p95 is 2.15x to 7.80x the build's size on CI, against a bar of 2x. The median stays 6.0 to 6.9 ms (C-011) | Decided 2026-10-26: the database is about 2% of a drain's time at ten times the build, so the sizing ships and the probe time is watched |
| Two-passage questions stay a slice to report apart: 0.548 of released ones usable (n 126) against 0.841 (C-014) | Every design to catch the welds failed its bar |
| C-037 and C-038 ship though their own bars missed on the rulebooks (ambiguous tag 2 to 5, not-standalone 5 to 3) | The arm bar that decides a change to what is written passed on both corpora. Confirmed 2026-10-26 |
| A currency in brackets after a space-grouped amount (`12 500 (EUR)`) reads as two figures (C-052). Spanish and French dates read as author and year (C-144, C-188) | No stored text changes (0 of 30,808). The parse refuses unconfigured languages (C-008) |

### Deferred to v0.5.3

| Item | Why it waits |
|---|---|
| The export builds whole in the API's 512 MB and failed past about 13,000 questions in v0.5.1 (C-066, C-071, C-241, C-175, C-240) | The streaming writer conflicts with the new workbook columns. Export a large corpus with `make questions-export` on the host, never through the pages |
| The workbook's note on what Kind means (C-239) | It waits with the streaming writer. `make diversity BY=kind` reports unanswerable rows apart |

### Deferred from the papers programme (v0.5.0)

| Item | Why it stays open |
|---|---|
| False presupposition, nonsensical and underspecified missed link U's bars | Writer-side fixes ship uncalibrated and the kinds stay opt-in. Checks left: a by-case count for underspecified, a reading for a passage granting the premise, a probe of the passages nearest each cited one |
| `QUESTIONS_UNANSWERABLE_SHARE=0.30` writes three times what the release takes | An unanswerable slot cost about USD 0.021 on link U against about USD 0.0086 for an average slot. Lower the share to save calls |
| FIX-R55: questions embedded as written, passages case-folded | Case-folding added one answering passage to the probe's 20 nearest, under the rule of at least 2 in a language |
| BL-B15: the judge approves about 90% of questions reviewers found 62 to 69% usable | The correction by reviewers' labels (`make diversity LABELS=`) narrows a floor's intervals by under 3% with this judge |
| More than two parallel question drains per database on Azure | gpt-4.1's token rate limit failed 3 of 10 topics with six drains on link U. Run at most two |

### Deferred in v0.4.5

| Item | Why it stays open |
|---|---|
| QA-extraction-9 | A bridge pass run twice can add a bridge the first left out. `make extract-bridge FORCE=1` deals the pass afresh. Pinned by a strict expected failure in `tests/property/test_bridge_reruns.py` |
| NEW-qa-parse-1 | Docling reads the football PDF's bullet glyph as U+221E and flattens one nested item. The reading is upstream |
| QA-security-3 | Hugging Face models load by repository id with no revision. Pinning touches the models the gates call. v0.5.2 pins them (C-117) |
| FIX-R110 | An internal storage network was not run end to end |
| FIX-R40, FIX-R10 | Parser passes for a two-column page and for a title that re-levels chapters, shown only on synthetic fixtures |
| FIX-R42, FIX-R66 | Product decisions: difficulty bands grade spread by design, and whether a container may call a hosted model |
| BL-C1, BL-C2, FIX-R43, FIX-R90, FIX-R84, FIX-R94, FIX-R58, FIX-R75, QAB-llm-nlp-5, -6, -8, FIX-R53, FIX-R112, VAR-link-pass-1, FIX-R87, FIX-R128, QAB-api-settings-6, -10, FIX-R113, FIX-R85, VAR-review-kind-1, FIX-R109, FIX-R67, FIX-R111 | No effect on current corpora or defaults, refactors without behaviour change, self-hosted-model cases, rollback-only or tooling items |
| BL-D4-picture, FIX-R165, QAB-preprocessing-12 | Text nested in a picture reaches no passage: 90% of picture text on the football PDFs was labels |
| FIX-R7, FIX-R167, BL-D4-extract, BL-B10 | The bridge test at extraction would refuse about 6 of 16 correct bridges against a bar of one. Bridge prompt 8 failed two of eight bars |
| NEW-extract-nlp-4 | A pronoun or *dies* pointing into a German verb-first condition, or an English *this* standing for an *if* clause, is refused `unresolved_reference`. Readings that free them also resolve four sentences that must stay refused |
| BL-B15, BL-B17, BL-E1, BL-E2, BL-G, FIX-R126, FIX-R140, FIX-R166 | Transferred to the DataMorgana features work |
| BL-F3, BL-F5 | The user's own: the Podman VM size, and their edits and untracked files |

### Deferred in the QA review (v0.3.28 to v0.4.0)

| Item | Why it stays open |
|---|---|
| A German spelled count read as a unit (llm-nlp-12) | The tightening would refuse 5 more German facts, 4 correct, and orphan 13 questions |
| Text a converter nests in a picture | Of 171 passages changed, about 90% of added lines were diagram labels and about 8% page numbers |
| Padded two-passage questions that cite a bridge | 56 of 71 (v0.3.12 pool) and 21 of 37 (v0.3.0 pool) cite a bridge. `question_facts` has no passage column. Refusing them fails the tightening rule |
| Bridge prompt 8 and the bridge test at extraction | Prompt 8 failed two of eight bars (22% of correct parallel and contrast bridges refused, bar 15%; 12 of 16 drift controls repeated, bar 13) |
| The unanswerable writer's reading (settles prompt 7) | Flagged 4 of 20 answered drafts. `QUESTIONS_RELEASE_UNANSWERABLE` stayed 0 |
| Two writer features for two-passage questions | The needs_both check relabels after writing. What it leaves (bridge-cited rows) no writer reaches |
| Questions on a false premise | Accepted 4 of 20 against a bar of 10. `QuestionKind.FALSE_PREMISE` stays named for a later design |
| One gold compound (row 4392) relabelled single by the needs_both check | By citation only 34% of padded questions are narrowed |

### Deferred in the v0.4.0 rebuild review

| Item | Why it stays open |
|---|---|
| Two-passage questions that weld two rules sharing a word or a party | The weld judge had precision 0.84 but recall 0.43 in German, and 36% of what it refuses is usable (bar 35%) |
| A count of one passage's list asked as an aggregation | Refusing such counts would remove rows 50% usable |
| Comparisons refused as `wrong_type` | Freeing them needs the weld judge's content check |
| `heard()` silences an answer on any question with a question word | It fired 4 times, 3 wrongly |
| The unanswerable writer returns no evidence of why its question is open | It fails on about 61% of drafts |
| Validated facts read a few points less correct than v0.3.0's (85.6% against 86.7%) | Within reader noise. Atomic prompt 12 writes a wrong heading into facts (about 0.2 points) |

### Deferred or low in the v0.3.0 rebuild review

| Item | Why it stays open |
|---|---|
| Explanation-form keys are not held to completeness | The only separating bar passed at 7 rows |
| Section paths are wrong at scale | Every Docling heading setting moves 200 or more right paths to fix about 160 wrong ones |
| Six readings that would free wrong fact refusals | They freed 47 wrong refusals but admitted 46 of 119 sentences that must be refused. They need coreference over competing antecedents |
| Duplicate refusals compare statements without headings | Embedding with the heading trail frees 19 to 31 wrong refusals but makes 71 to 121 new twins |
| Glossary definitions get no facts | The best rule reads 42 of 43 glossary passages but 14% of what it reads are cross-references |
| A circular reason caught only below a fixed share of new words | Every bar is fitted to this rulebook |
| Smaller structural gates (figures read from the question, `unanchored` pointers, `leaks_source`) | 4 of 6 and 2 of 3 freed rows usable, under 70% |
| Follow-up gates read ids, not content | Checking against every earlier turn would remove rows 53% usable |
| A wrapped fee-table row with an empty first cell merged into the row above | No rule separates it from wraps opening on a bracket or a German noun |
| A struck full stop under 2 pt kept | A relative strike length also reads a 1.5-pt mark over a decimal comma as a strike |
| A list nested at the top of a column stays flat | The depth guard cannot open a level there |
| Bridge facts that are not bridges | A judge caught a third of unsound bridges. Refusing them would remove questions 55 to 62% usable |
| Imprint and contact passages yield questions | A general fix needs to read what a passage asks of its reader |
| Topic membership is loose (a passage in three topics on average) | Every floor removed questions 46 to 78% usable |
| The API, Streamlit and Dagster have no authentication | Each binds to 127.0.0.1. Production adds `API_TOKEN` (v0.5.2) |
| Dagster's corpus job lacks the bridge pass `make corpus` runs | It waits for a bridge pass worth running unattended |
| Images and installs are not hash-pinned. Workers hold more credentials than they need | Infrastructure changes beyond a patch release |

### Tried in v0.5.2 and withdrawn, with the reason

| Item | Why withdrawn |
|---|---|
| Text nested in a picture written into its passage (C-140, C-284) | 5 of 26 changed passages read worse (bar 2) |
| A table's section path from a heading absorbed into its first row (C-097) | Tables with a major defect stayed at 0.50 of 50 (bar under 0.24) |
| Nested lists kept nested when every item wraps (C-120) | Probes read `(3)`, `3.` and `3)` as one numbering, and the fine-print threshold failed at +20% |
| A misread bullet glyph taken as the bullet (C-281) | It turned `€ 5,00` into `• 5,00` |
| A foot's contact line kept (C-160) | It kept a running foot printing a date in 12 of 20 probes |
| A restored clause's lead-in carried to sub-items (C-007) | It misfired in 33 of 90 bank-terms probes |
| A list item ending in a colon heading its sub-items (C-047) | It lost an outer list's lead-in |
| Page numbers read per printed page on spreads (C-182) | It dropped a margin figure such as 25 |
| A picture page counted as unread only with no body text (C-127) | A rotated scan went unnamed |
| A local entailment model checking digests (C-032), refusing low-scoring keys (C-044) | 39% to 86% of refused digests and about 85% of refused keys were sound (bar 35%) |
| Bridge refusals: one passage adds nothing (C-045), own numbered heading (C-130), no finite verb (C-173) | Correct shares 0.44, 3 of 5 and 3 of 5 against their bars |
| Extraction prompt 15 forbidding the heading as situation (C-094) | Heading frames fell from 51 to 1 but correct facts fell (build 48 of 60 against 53) |
| A list under a lead-in read without verbs (C-050), a table the cell reader composes nothing from (C-061) | 12 of 26 and 44 of 60 new facts correct, under their bars |
| A dotted figure read as a clock time (C-158) | `EUR 12.30` read as a time |
| A heading label taking a title after its number (C-025, C-190) | `iPhone 15 Pro` read as a numbered section |
| Parts reading refusing a two-passage question (C-014) | It called all 167 rows one question: 0 of 48 welds caught |
| Round trip keeping a key that names omitted items (C-017); entailment rescue with the question (C-018, C-035, C-062) | 3 of 7, 21 of 30 (0.70), 13 of 18 and 6 of 12 usable, under their bars |
| Keys naming part of a list held to the list's length (C-028, C-126) | 328 of 385 refused keys usable (0.85, bar at most 0.35) |
| The unanswerable ceiling applied inside the draw (C-030); silenced unanswerables drawn last (C-060) | It broke two release invariants. The redraw left 12 bad rows of 130 either way |
| The comparison gate split at another seam (C-046) | 78 admitted, 28 usable, 12 invalid |
| Every document's text fenced in `<material>` tags (C-106, C-223) | Fenced extraction narrowed 10 of 60 facts against 7 (bar 9) |
| Settles quote with `[...]` or a passage number (C-122); near questions put to the same-answer read (C-143) | 4 of 7 newly refused usable; 15 of 22 kept were true duplicates |
| A count equal to the cited facts kept where it counts a list (C-147); a count of list items refused (C-151) | 0 of 5 usable refusals cleared; 6 of 9 newly refused usable |
| A non-why key echoing the question kept (C-149) | Failed its second leg on shop (3 of 5 usable, 3.33 needed) |
| An explanation's figures read in its heading (C-421); a title in a question refused only when cited (C-423) | 15 of 28 usable (floor 0.751); 4 of 7 subject-naming rows stayed refused |

### Tried in v0.4.3 and withdrawn, with the reason

| Item | Why withdrawn |
|---|---|
| A topic's finished threads kept on an outage (FIX-R88) | The retry duplicates questions. It needs a slot index on the stored question |
| A spelled count validated anywhere in the passage, and German count words read as units (FIX-R164) | The first validated wrong counts. The second refused 2 correct facts of 3 |
| Only clause-heading verbs allowed in a key; a table of pronoun numerals (VAR-one-same-price) | A noun phrase and an imperative parse alike. Real counts (*at most one*) were dropped |
| A key naming part of a list read as incomplete (FIX-R24) | 2 of 3 newly refused German rows usable |
| A table of the writer prompt's labels, and a check for a person the passages lack (BL-B8) | 2 of 3 newly refused rows usable. The check refused an asker naming themselves in a premise |
| A space-grouped amount read as one figure by every reader (QA-questions-1, -4) | A claim's figures and a passage's are read by two readers that fold the amount differently |
| `asks_one` on the round trip's read (BL-B11) | It caught 2, then 8, of 35 welds, half of the refusals usable |
| A title naming its page's subject left to the phrasing judge (BL-B1) | The admitted rows held 6 invalid in 31 (bar 2 per 60) |
| Expert and the two search queries in the default (BL-A-expert, BL-A-short-query, BL-A-long-query) | Expert's conformance 0.59. The short query is accepted on 29 to 31% of its slots. The long one has too few rows |

### Tried in v0.4.4 and withdrawn, with the reason

| Item | Why withdrawn |
|---|---|
| A sentence cut dropped before a lower-case word after no full stop | It moved the cuts of 21 of 820 passages |
| A verbless definition under its heading extracted | One design admitted index lines, the other dropped definitions holding a figure |
| Extraction prompts 13 and 14 (FIX-R129) | Prompt 13 dropped the heading's scope (correct 0.917 to 0.793). Prompt 14 wrote 105 heading-as-situation facts (limit 59.5). Extraction stays at prompt 12 |
| A U+00AD hyphen read per document | It turned hyphenation points into hyphens |
| A lead-in set as a heading read as a paragraph | It reached sibling sections it does not introduce |

## Fixed defects

Fixed defects by release, newest review first.

## Found by the final review of 2026-10-22

The final review of v0.5.1 read one full build (30 football PDFs, German and
English, Azure models): 0.841 of released questions usable as they stand
(1,070 of 1,273), and 19 blockers in data safety, unattended operation,
credentials and documentation. It merged every open bug of the earlier reviews
into 427 items, `C-001` to `C-427`. The fix session took 171 to fix, 49 were
already fixed, 46 ride on another fix and 161 are deferred. The conditions a
deployment has to hold are in [Production
deployment](operations.md#production-deployment). What to run on stored data
is in [Upgrading to v0.5.2](operations.md#upgrading-to-v052). A change that
failed its bar written beforehand was withdrawn.

### Fixed in v0.5.2: data safety

| Defect | Fix |
|---|---|
| A re-chunk or re-extraction deleted the accepted, reviewed and released questions that rested on what it replaced (C-001) | A passage or fact that comes back identical keeps its id. A question resting on a changed one is rejected as `source_changed` and kept. A whole-stage rerun refuses without `FORCE=1` and names the questions at stake |
| A database name exported in the shell was overridden by `deployment.env`, and destructive targets named the main database whatever they acted on (C-002) | An exported `APP_DB_NAME` is honoured. Every destructive target refuses unless `CONFIRM=<database>` on the command line names the database it resolves to, and every warning names the database and port |
| There was no backup or restore procedure (C-003) | `make backup DIR=` dumps the application, SeaweedFS, Phoenix and Dagster databases and every object with a manifest, leaving secrets out. `make restore-backup` and `make restore-backup-stack` put them back |
| Object keys were the document digest alone, shared by every database, so a delete, re-parse or purge in one removed another's objects (C-004) | Every key is stored under the database's name. A bare key from before is read as a fallback, and `make s3-prefix` copies a database's own bare objects under its prefix |
| `make wipe` and the external stores were not scoped by database, so a wipe purged every database's Phoenix projects, Argilla workspace, logs and Dagster runs (C-005) | Phoenix projects, Argilla datasets, log lines and Dagster runs carry the database's name, and a wipe deletes only its own. `ALL_DATABASES=1` takes every database's and `KEEP=runs` keeps the run history |
| A restore put back every row archived since a time, including superseded facts and cleared settings, not only the deletion being undone (C-042) | `make restore-documents AT=` puts back only the deleting transactions it names. Settings and prompts return only when `TABLES` names them |
| `make wipe` ran six irreversible steps with no preflight and stopped half way on a misconfigured store (C-087) | `make wipe-preflight` authenticates to each running store before the first delete, and the wipe skips a stopped store with one note |
| The archive grew without bound and a purge held one transaction (C-118) | `make archive-purge` deletes in committed batches of 10,000 rows, only this database's. `make doctor` prints the archive's size |
| Concurrent deletes could deadlock on the cascade triggers (C-138) | A deletion locks the facts, then the questions it reaches, in id order |

### Fixed in v0.5.2: the model path and the production host

| Defect | Fix |
|---|---|
| The containers had no hosted-model path: the question worker fell back to a local Ollama model, and every model stage ran as an unsupervised host process tied to a login (C-006) | `make corpus-hosted` runs the corpus on the host, detached, refuses a second start, resumes a stopped run with its spend, and `make corpus-hosted-stop` stops it. `scripts/corpus-hosted.sh` exits with the stage's own code for a supervisor |
| Containers ran current code on the dependencies of the last image built, and a failed rebuild left them crash-looping (C-010) | Each image bakes the hash of its lock. A container whose checkout's lock differs refuses to start, waits ten minutes and exits 78 |
| The checkout, its `.env` and the certificate keys sat in a synced folder, and a hand-made backup wrote `.env` in clear (C-012) | `ENV_FILE` names a secrets file outside the checkout. `make doctor` warns about a checkout or secrets file under a sync client's folder, and a backup copies no secret |
| The production build ran through a private runner and the documented path was never walked (C-013) | The operations guide holds a runbook that a static test checks against the commands and settings a fresh clone needs, in order |
| No committed file described the model split (C-051) | `.env.example` ships the seven role models and `LLM_REASONING_EFFORT=none`. Every drain logs the split before its first row. With `HOST_RUNNER=1` a role resolving to an Ollama model, or an unset judge with `ASSESSMENT_ENABLED` on, is refused |
| One 8-hour timeout bounded every orchestrated stage, which extraction at ten times this corpus outlasts (C-073) | With `HOST_RUNNER=1` the orchestrated path is off: `make all`, `make pipeline`, `make auto` and the pipeline routes refuse and name the host runner |
| `make corpus` fitted no topics (C-048) | It fits topics between extraction and the bridge pass where a language holds passages and no live fit |
| Every model-loading stage asked the Hugging Face Hub at run time (C-072) | `make doctor` checks the cache (each encoder at its pinned commit, and Docling's) and fails on what is missing, naming the command that fetches it. `make docling-weights HOST=1` fills the host cache |
| `make doctor` proved the models with the environment while workers ran with stored overrides (C-074) | `make doctor` asks with the settings the stored rows make and names each value that comes from the store |
| Half of the 23 containers served nothing on the production path (C-080) | Argilla, Redis, Elasticsearch, Filebeat, Grafana and Adminer sit under profiles, and the production `make up` starts eleven services |
| Builds filled the engine's disk across upgrades (C-086) | `make upgrade` checks free space against `UPGRADE_FREE_GB`, builds, prunes what the build orphaned, stops the workers, migrates and starts |
| Hugging Face models were loaded by bare repository id (C-117) | `EMBEDDING_MODEL_REVISION`, `NLI_MODEL_REVISION` and `QA_MODEL_REVISION` pin each load |
| A database password holding URL characters broke the connection string (C-201) | `make doctor` and `make corpus-hosted` refuse an `APP_DB_PASSWORD` holding `@ / : # ? %` and name it |
| `POST /pipeline/run` read a Dagster error as nothing running and launched a run (C-255) | It answers 503 |
| A queue verb answered 202 where no worker of the stage exists (C-417) | On the production profile the answer names the command that drains the stage |

### Fixed in v0.5.2: drains that stop and say why

| Defect | Fix |
|---|---|
| A drain proved its model once, then failed every row through an outage and exited 0 (C-009) | A drain exits 3 when a row failed and 75 when it stopped itself. Five unreachable-model rows in a row stop it with the rows back in the queue. `make corpus` stops at a non-zero exit |
| A failed digest call discarded the passage's atomic facts (C-041) | The facts are kept and the passage is noted. `make extract-digests` digests the noted passages later |
| Nothing bounded a drain's spend, and a model answering "nothing found" for every passage marked the corpus extracted (C-091) | `SPEND_CAP` stops every drain, the bridge pass, the release draw and the rejudge with exit 75. 25 readable passages with nothing found in the last 50 stop extraction |
| A settings change reached no stored row, and a lowered digest floor reached no stored passage (C-057) | The digest pass also digests extracted passages above `EXTRACTION_DIGEST_MIN_CHARS` that hold none. `make settings` and `make doctor` list stored rows made before a change that stales them |
| Workers got 10 seconds on a stop while a row can take minutes (C-079) | A worker told to stop finishes its row. A second signal or its stage's grace gives the row back and exits 75 |
| More than two drains per database hit the provider's rate limit (C-082) | A rate limit is waited out for its `Retry-After`, ten minutes in all per call, without spending an attempt |
| An artefact deleted while the judge read it ended the drain (C-136) | The artefact is logged as gone and the drain takes the next row |
| A call litellm cannot price was logged with no cost (C-219) | It is logged as unpriced, and a drain with `SPEND_CAP` set refuses such a model |

### Fixed in v0.5.2: parsing and passages

| Defect | Fix |
|---|---|
| Clauses the converter's bookmark pass turned into headings reached no passage: 52 of 54 such items across two regulations (C-007) | A heading that is a member of a list is read as the list item it was |
| A document in a language no configured model names was read as German or English through every stage (C-008) | The document is refused at parse and its language is named. The reading refuses only above a confidence of 0.7 |
| Titles named nothing, were cut off or collided: 14 of 30 (C-096) | A PDF is titled by the heading in the largest type, else by its cover |
| Text a reader cannot see passed every parse step (C-107) | Text in render mode 3, fully transparent, under 2 points or white on bare paper is dropped from a page whose other text paints ink |
| List nesting and column breaks assumed left-to-right scripts (C-108) | A list or column in a right-to-left script is read from the right edge |
| A few garbled pages passed the confidence floor with no warning (C-109) | Every page under `PARSING_MIN_CONFIDENCE` is named in the parse note. A blank page is not |
| A table continued on the next page was joined wrongly or not at all (C-121) | A continuation joins its table when a column sets header and data alike, when the converter flags several leading header rows, or when it is captioned |
| A running head of the other language's edition stood as a passage (C-187) | A body paragraph where three or more other pages' running items sit is treated as furniture |
| The change boxes of a rulebook produced heading-only passages (C-230) | A list item alone in its list that repeats a heading leaves the body |
| A small spaCy pipeline changed what a fact is, silently (C-348) | A small pipeline, or one without word vectors, loads with a warning naming its language |
| A letterhead named a chapter of one page (C-368) | A running item printed once on the first page names no chapter |
| A two-column page read across the gutter interleaved its columns unseen (C-426) | Such a page is named in the parse note |

### Fixed in v0.5.2: scale

| Defect | Fix |
|---|---|
| One Postgres capped at 1 CPU and 512 MB served five databases and three vector indexes (C-011) | `deployment.env` sizes the container and server for the production corpus (4 CPUs, 4 GB, `shared_buffers` 1 GB, `/dev/shm` 1 GB). The operations guide gives the table by corpus size |
| Question slots stopped growing at 40 topics a language, and every topic of a language was named in one call (C-024, C-077) | `TOPIC_NUM_TOPICS` ships at 300 and topics are named 25 to a call. `make topics-name` names what a fit left unnamed |
| Two extract workers could keep one claim twice (C-026) | The store takes a lock per language and kind and judges the passage's facts again under it |
| Term links grew with the square of the corpus (C-027) | A term links passages only if it is rare (at most 0.5% of a language's passages, never more than six), and each passage keeps the eight partners it shares most with |
| Nothing bounded a document's pages before conversion (C-076) | `PARSING_MAX_PAGES` (180) refuses a longer document before conversion and names its page count |
| There was no sizing guide for a large corpus (C-084) | `make estimate` prints the time, calls and spend of the rows still to do |
| The release scan drew once per size, about the pool squared (C-089) | The scan starts where the pool can place the release and steps down in strides of a hundredth from 2,000 rows, by ones below. A draw reuses its cells |
| Every dedup probe joined the citations, so the vector index was never used (C-090) | A fact carries its language (`facts.language`), so the probe uses the index |
| The bridge pass held every vector as Python floats and parsed each passage twice (C-099) | It holds float32 arrays and parses each passage once |
| A compound slot that found only bridges abandoned the rest of the topic's plan (C-236) | The slot is passed over and the later slots are written |

### Fixed in v0.5.2: facts

| Defect | Fix |
|---|---|
| `unsupported_addition` refused sound facts because only the cited sentences counted as support (C-020) | An atomic fact is supported by its whole passage. A figure only the rest of the passage gives is still refused where a cited sentence states another of the same kind (a currency, a share, a period) |
| `unresolved_reference` refused facts whose demonstrative names the document itself, such as *these regulations* under a title that says so (C-021) | A demonstrative names the document when its noun is the head of a title line or the last part of that head's compound |
| `not_atomic` refused a German rule whose verb-final clause carries its condition or exception (C-019) | A verb-final clause after a comma and *und* goes on with the clause before it when that clause is subordinate and more than one constituent stands before its verb |
| `not_atomic` refused a bridge's contrast or limit (C-033) | A bridge whose relation is a contrast or a limit may carry two claims |
| The entailment encoder cut a long passage at 512 tokens without saying so (C-065) | A long premise is read in overlapping windows of sentences |
| A duplicate refusal kept no twin id, so every replacing drain replayed the dedup over the whole corpus (C-068) | `facts.twin_id` records the twin and is set NULL when the twin goes. The replay reads only refusals that lost their twin |
| Long list passages never got a digest because the floor counted claims and a list is one sentence (C-098) | The floor counts claims and list items together |
| `make extract-revalidate` rewrote every fact row (C-111) | It reads in batches and writes only the facts whose verdict or spans changed |
| `evidence_absent` refused list lines inside the passage's last sentence (C-129) | A citation one past the last sentence names a line of it when that sentence holds two or more list lines |
| A passage's outline was refused as a duplicate of its own summary (C-137) | An outline and a summary are never twins. Stored refusals of the kind come back through the dedup replay |
| A fee table in a currency beyond EUR, USD, GBP and CHF was read as an identifier grid and skipped (C-416) | A currency is an ISO 4217 code, any currency sign, or the language's own word |

### Fixed in v0.5.2: questions, topics and the workbook

| Defect | Fix |
|---|---|
| A why-question planned unanswerable was refused as answered on a quote that states only the rule (C-022) | The settles reading takes such a quote as silent (verifier prompt 15) |
| Small documents got no question: 9 of the 30 PDFs (C-023) | The deal gives each document of a topic its share first, and every document a sample before any gets a second. `make questions-status` counts the documents and passages no accepted question reaches |
| The writer wrote questions that need the document to make sense, or that read two ways (C-037, C-038) | Writer prompt 32 tells every writer the reader never sees the passage, and tells an answerable writer to put the case that makes its key the only answer into the question |
| The self-contained judge refused a question naming a set the domain fixes, such as *the two* (C-422) | The judge is shown definite sets and a repeated noun (phrasing prompt 5) |
| Topics bound unrelated passages through weak memberships (C-095) | `TOPIC_RELATIVE_WEIGHT` (0.5) keeps a membership only at least half the passage's strongest, replacing `TOPIC_MIN_WEIGHT` |
| A refit deleted the topics a question worker held and sent every topic back to be asked again (C-055) | A refit keeps a generated topic that is an old one with no new passage. A fit or topic delete refuses while a topic holds a live question claim |
| A workbook row did not stand on its own (C-102) | The Questions sheet gives each row its earlier turns and its source (document, pages, section path) |
| The workbook named the difficulty band hardness, and its Summary named no judge (C-029, C-135) | The band is titled Retrieval spread. The Summary names the judge's model and template, counts by language, and says its counts are not a quality estimate |
| An English date read as an author and year leaked the source (C-144) | A date the entity reading marks is not a citation |
| A deverbal noun phrase in a value key read as an action (C-188) | A participle inside a noun phrase is not read as an action |
| A follow-up was stored `needs_both` under a root narrowed to one passage (C-363) | A follow-up is dealt the kind its root was stored as |
| The parts reading never ran on derived questions (C-034) | A derived question citing two passages is read by parts like any `needs_both` question |
| Space-grouped amounts with a marked currency or a price dash were split into two figures (C-052) | Such an amount is one figure, before or after any currency sign |
| A compound question's halves were not stored (C-053) | Both halves are kept in `gate_scores` |

### Fixed in v0.5.2: platform, security and tests

| Defect | Fix |
|---|---|
| The API took every write from anyone who could reach it, and the page could point the local models at any repository (C-085) | Every write and every read of `/settings` carries `API_TOKEN` as `X-API-Token`, which `make setup` generates. `QA_MODEL`, `NLI_MODEL`, `EMBEDDING_MODEL` and `DOCLING_ARTIFACTS_PATH` are fixed settings |
| Any web page the operator opened could trigger the costly reads (C-202) | A cross-site request is refused on every method |
| Error paths sent the database's host and role to the caller (C-139) | An unhandled error is answered with one fixed sentence and logged in full |
| Whole-stage reruns and `DELETE /topics` acted on one click (C-040) | They need `confirm=true` and name what is at stake, and Redo asks first |
| The API opened every upload with no page or time cap (C-299) | `MAX_FILE_SIZE_MB` is bounded at 150. A PDF over `PARSING_MAX_PAGES` or read past `PARSING_TIMEOUT_SECONDS` is refused and the setting is named |
| The Upload page took any number of files into memory (C-114) | It refuses more than 20 files or 200 MB and names `make ingest DIR=`, which loads a folder from the host |
| The judged sample represented neither the pool nor the release (C-059) | Each stratum is sampled in proportion to its size, from the released questions once a release exists |
| A label defined on only part of the judged rows was corrected over all of them (C-039) | Rows labelled `na` leave both counts |
| The PPI interval was asymptotic and per row (C-067) | Under 30 labels the interval is the labels' own Wilson interval. From 30 it is the corrected interval with a t quantile, or the rule of three where the labels leave no spread |
| The diversity tables pooled languages by judged rows, named the wrong predictor, put unanswerable rows under single, read any extra field as a label and cut long labels (C-237) | Each is corrected. The workbook's note on what Kind means waits for v0.5.3 |
| Phoenix kept every prompt and passage for ever (C-103) | `make up` sets the default trace retention to `PHOENIX_TRACE_RETENTION_DAYS` (30), beside the per-database purge |
| A migration ran in one transaction with no lock or statement timeout (C-075) | Each revision is one transaction with a 5-second lock timeout and a 10-minute statement timeout |
| `make confidence-recalibrate` locked every question and fact for its run (C-078) | It reads without a lock and writes back in guarded batches of 300 |
| A deletion through the pages or the API did not replay the dedup (C-054) | Every deletion says how many duplicate refusals lost their twin, and an idle extraction worker replays the dedup whenever a refusal points at no twin |

### Fixed in v0.5.2: the documents, dependencies and what the release's own checks found

| Defect | Fix |
|---|---|
| No repository doc carried the production conditions, and three docs scaled `extract-worker` to four (C-425) | Production deployment lists the conditions, each with its item and what lifts it, and nothing scales `extract-worker` past two |
| Pillow 12.3.0 carried advisories fixed only in 13.0.0 (C-083) | The images ship Docling 2.142.1, docling-core 2.104.0, docling-parse 7.23.0 and Pillow 13.0.0 |
| `make corpus` with an exported `APP_DB_NAME` ran its drains on `deployment.env`'s database | `make corpus` and `make corpus-hosted` take the database from the command line or the environment, like every host command |

## Found by the papers programme of 2026-10-22

Before v0.5.0 shipped, every open item was listed (236) and ranked by what it
would do to a large build. The full build after v0.5.0 found two defects at
its start.

### Fixed in v0.5.1: the full build's start

| Defect | Fix |
|---|---|
| The Dagster webserver and daemon, `make dagster-wipe` and `make wipe` failed to start, because SQLAlchemy 2.1 reads a bare `postgresql://` as psycopg 3 | The storage URL names `postgresql+psycopg2`, the driver dagster-postgres installs |
| A split pairing a reasoning writer with a verifier, judge or phrasing model that does not reason failed every call of the latter | The reasoning effort is not sent to a hosted model that litellm knows does not reason. An unknown model still gets it |

## Found by the finalize review of 2026-10-21

A third review took the 269 items open at v0.4.2 (177 confirmed, 66 already
fixed, 8 refuted, 8 wrongly stated, 10 transferred to the DataMorgana paper
features) into v0.4.3 (questions), v0.4.4 (reading documents) and v0.4.5 (API,
frontend, stack).

### Fixed in v0.4.3: questions

| Defect | Fix |
|---|---|
| A compound slot planned hard kept the band hard, though a compound question is always banded medium (QAB-qg-plan-2) | A compound slot is planned at the medium band its kind fixes, and a declined slot written as another type takes the band its kept shape reaches |
| A follow-up on a compound pair was stored `needs_both` (QAB-qg-plan-8) | A follow-up is stored `needs_both` only where its root was dealt `needs_both` |
| A compound partner's facts were ranked toward the head, and a partner whose closest fact was a bridge offered nothing (QAB-qg-plan-7) | A compound partner offers its own facts in its own order |
| A second passage could offer a word-for-word copy of a fact already offered, and a compound partner could copy the head (FIX-R103) | No second passage offers a word-for-word copy of an offered fact, and a compound partner is never a copy of the head |
| A two-passage reading could hold nine facts, past its ceiling of eight (QAB-qg-plan-10) | Each later passage is left room under the ceiling before the head's list is filled |
| A premise's own *When*, or a *which* or *wo* opening a relative clause in it, typed the question (NEW-qg-plan-3) | A question opening on a premise is typed by the question word that asks: the first one outside a relative or adverbial clause |
| An amount written with spaces (`5 000 Euro`, `EUR 100 000`) was read as two figures, so a right total was refused (NEW-release-1) | An amount grouped by spaces is one figure where a currency code, symbol or word stands beside it. A table row or phone number keeps its separate figures |
| The pronoun *one* counted as a second number, so an aggregation was relabelled `factoid` (VAR-number-readings-1) | One predicate, `is_number`, decides what a number is everywhere |
| A count of the items one cited fact lists was stored as an aggregation (FIX-R127) | A count is stored as a factoid when the fact the question asks about lists that many items, and nothing is refused for it |
| A German keyword query typed in lower case lost every noun to the gates (BL-B2) | A text with no capital after its first word says nothing by its case, so the gates read its nouns. A lower-case query holding one capitalised word is read as written |
| An answerable question with no explanation passed (FIX-R105) | It is refused as `explanation_unusable`. A stored row read without an explanation still passes |
| With three cited passages the check lost a part that two other passages share (FIX-R169) | A question citing three or more passages keeps, besides the passages holding a part of their own, the first passage holding each part they leave uncovered |
| A circular reason key, the rule restated as its own reason, passed (BL-B5) | The round trip's read also says whether the passages give a reason beyond the rule, and a question with none is refused `not_recoverable` (verifier prompt 12) |
| A question reworded until it asked something the passage does not say was mapped back to the passage (BL-B12) | The read answers only where the passages answer the question as asked, and a drifted question is `not_recoverable` |
| The aggregation prompt invited counts of the facts the writer was handed (BL-B3) | The prompt says a count is of the figures or items the facts state, never of the facts themselves (writer prompt 28) |
| Questions about a case study's sample person, a phone number or a page's legend passed every gate (BL-B9) | The writer is told that a person or story in the material illustrates a rule, and to ask about the rule, never about a contact box, legend or list of changes |
| With-premise questions opened on a scene label such as *Beim Spiel:*, and a premise could give the answer away (BL-B6) | A with-premise category asks for a premise in which the asker states, in the first person, a fact of their own situation. A premise with no first- or second-person word is written once more with a note |
| The wording of distant-from-document, expert and long-search-query produced bad questions (BL-A-distant) | Distant keeps every term's meaning and coins no word. Expert is described by what an expert asks. Long-search-query is keywords with no question word |
| A search query was told on a slot that cannot be asked in keywords (BL-A-short-query) | A search query is not told on a slot that spans two passages or on a type whose question word is the ask (reason, comparison, implication, change over time) |
| distant-from-document drifted from the passage's meaning, and the default dealt no linguistic variation (BL-A-distant) | The default deals Linguistic variation {similar-to-document, distant-from-document} at even odds beside Phrasing and Premise |
| A short search query that another passage answers differently was accepted (BL-A-short-query) | A short query is read once more against the nearest passages it does not cite, and refused as `not_recoverable` where one of them answers it differently |
| The quality report, the Questions page, the API and the workbook Summary did not count the kind or the categories (NEW-api-frontend-export-2) | The report counts each kind and each category, and the three surfaces read those counts |
| A question's categories reached neither its Argilla record nor the Questions page, and a keyword query was judged as malformed (NEW-api-frontend-export-3) | Categories reach both, and the guideline judges a search query as a query. A dataset made before v0.4.3 must be recreated to carry them |
| A control character in exported text failed the whole workbook with a 500 (QA-api-frontend-1) | Control characters are dropped from every cell of every sheet |
| The release was sized by its scarcest kind, which asked for its whole share at every size and capped the release | A kind short of its share is capped at the rows a release can take of it. Its places go to other kinds by largest remainder |
| The release draw overshot its quotas with follow-up questions | A thread ends at the first turn whose band, kind or language has no place left, and later turns go with it |
| The release could hold twins the verifier never judged (FIX-R3) | The draw after the last twin round is read for twins once more, and the last round drops the later-ranked member of each pair with its thread |

### Fixed in v0.4.4: parsing and chunking

| Defect | Fix |
|---|---|
| A scanned page carrying one stamped line, such as a merge tool's `Seite 2 von 3`, was not named, so its text went missing without a warning (NEW-parse-chunk-2) | A page with no more than `PARSING_OCR_CHAR_THRESHOLD` characters (100 by default) under pictures covering at least half of it is named as image-only in the parse warning and `documents.parse_error` |
| Bidi marks, isolates and C1 controls survived text repair, so a model's quote of a phone number or opening hours matched nothing in the passage (QAB-preprocessing-10) | Every format character is dropped, and a C1 control is read as the cp1252 character it stands for |
| A table label wrapped over three lines lost its last line to the next row's label or left a row with no price (VAR-parse-text-1) | Each tail joins the nearest row still standing |
| A body line opening with the running foot's name, an imprint or a contact line was moved to the furniture layer whole (QAB-preprocessing-7) | A paragraph is furniture only when it is the running head or foot itself. A line that goes on past the foot's name stays passage text |
| A lone integer anywhere on a page was dropped as a page number, which lost values such as a notice period printed under its label (VAR-chunk-structure-1) | A lone integer is a page number only in the top or bottom tenth of its page and where the document's page numbering supports it |
| A sentence cut at a page or column break before a capitalised word stayed two half sentences (FIX-R101) | The two halves join when the tagger reads the first as ending on an article, preposition, conjunction or auxiliary and the second as opening with a noun |
| Text above a mid-page chapter opening was filed under the new chapter when the heading is spelled unlike its running head, such as `B. Geschäftskunden` against `Kapitel B:` (NEW-parse-chunk-3) | Headings and running-head fields are compared on their letters and digits |
| A lead-in left at the end of a list item by a page join (`bestehen, wenn:`) reached none of the list's pieces (FIX-R100) | A list item ending on a colon is a lead-in too and heads the list after it through the heading trail |
| A heading holding ` > ` (`Orders > 50 EUR`) was split in two by every reader of the section path (QAB-preprocessing-8) | A ` > ` inside a heading is written ` › `, and the path is read back with each heading as printed |
| A footnote the converter attaches to a picture, such as an offer's conditions under a banner, reached no passage (NEW-parse-chunk-4) | A picture's footnotes are written beneath its caption, as a table's are. Text nested inside a picture stays out |
| A list in two languages under one heading became one passage filed as one language (NEW-parse-chunk-5) | List items are read too, so a run of items that changes language ends the chunk |
| A running head or foot parted by a dash, middle dot or bullet between spaces was one field that numbers pages, so no chapter was read from it (QA-parse-chunk-1) | It is split at an en dash, em dash, middle dot or bullet between spaces, never at an ASCII hyphen |
| A short sub-heading that a chapter's running head holds, such as `Fees` under `Fees and charges`, was taken for the chapter's opening (QA-parse-chunk-2) | The heading and a field are compared word for word, and a field shorter than two letters or a bare numeral never opens a chapter alone |
| A sentence cut at a page break before a figure (`für die ersten` over `12 Monate kostenlos`) was never joined (QA-parse-chunk-3) | The cut is joined where the word before it cannot close a clause (an article, preposition, conjunction, or an adjective behind one) |
| A bullet with no full stop at a page foot absorbed the next page's paragraph when that opened on a name such as iPhone or eBay (QA-parse-chunk-4) | Only a run of letters all in lower case opens in lower case |
| A ligature (U+FB00 to U+FB06) was stored as written, so `Kontoeröﬀnung` and `Kontoeröffnung` were two words (QA-parse-chunk-6) | Ligatures are spelled out as their letters. A document holding one gets a new content digest, which `make parse-rerun` writes |
| The zero-width joiners of Persian, Indic, Khmer, Myanmar, Tibetan and emoji sequences were dropped (QA-parse-chunk-7) | A joiner is kept between two letters or marks of a script that joins with it, and inside an emoji sequence |

### Fixed in v0.4.4: fact validation, extraction and the link pass

| Defect | Fix |
|---|---|
| A sentence ended after an abbreviation that never closes one, such as `incl.` before `VAT`, and after clause or weekday abbreviations the table lacked (QAB-llm-nlp-3) | The table is split into abbreviations that end no sentence (`incl.`, `cf.`, `Ziff.`) and those that may end one only before a capital |
| A German fact opening on polite *Sie* was refused `unresolved_reference`: 19 German facts of the shop calibration base (NEW-extract-nlp-1) | The fact check passes the cited passages to the reading, and an opening *Sie* names the reader where a passage holds a polite form inside a sentence |
| A fact pointing outside through a modifier such as *such a card* or *the following fees* was validated (VAR-bridge-prompt8-1) | Two tables of anaphoric and cataphoric modifiers are read on the noun before the first finite verb, as an opening demonstrative is |
| A German *dies* after a free relative clause (*Wer die Karte verliert, muss dies sofort melden*) was refused (VAR-dies-free-relative) | A finite verb with a question word under it is a clause *dies* may stand for. *dies* after a relative clause on a noun is still refused |
| A narrowed `make extract-bridge` pass deleted a sibling or term bridge headed outside its scope and never wrote it back (QA-extraction-9) | A bridge records the passage that headed its link. A narrowed pass clears only bridges headed in its scope |
| A hold on pairs the link pass would not offer still changed what it dealt, so narrowed passes dealt other links than a fresh one (FIX-R168) | The pass deals as if nothing were held, then moves only a dealt link on a held pair to its head's next free link |
| The bridge check missed a passage's numbered heading named second in a list, such as *Sections 7 and 9* (NEW-extract-nlp-2) | One reader, `numbered` in `validation.py`, serves both. *Sections 7 and 3* names both sections |
| A single-quoted heading ending in a possessive (*‘Customers’ fees’*) was cut at the apostrophe and linked to nothing (VAR-link-references-1) | A single-quoted span is read on to a later closing mark on its line where that longer span is a heading |
| A figure ending a German sentence (`EUR 5.`, `Ziffer 3.`) opened the next sentence as if it numbered an item, so facts citing the sentence were refused `unsupported_addition` (QA-extraction-1) | A figure after a word or abbreviation finishes its sentence. Only a number opening its line numbers an item. A stored passage takes this through a re-chunk |
| An abbreviation in the tables still ended a sentence after an opening bracket or quote, as in `(cf. Section 4)` (QA-extraction-2) | A word's leading marks are stripped before the tables are read |
| A price abbreviation ended a sentence before a lower-case word, as in `2.5% p.a. on all balances` (QA-extraction-3) | `p.a.` and `mon.` are closing abbreviations, and a word joined by a slash ends on its last abbreviation |
| A German fact opening on an inflected pointing modifier, such as *Nachstehende Bedingungen* or *Besagter Kunde*, was validated (QA-extraction-5) | The tables are read with German adjective endings stripped as well |
| A fact opening on a back-pointing modifier no table held, such as *the above fees* or *die vorstehenden Bedingungen*, was validated (QA-extraction-6) | The three join the table. A modifier is also read joined to the word before it (`above-mentioned`), and only before its noun |
| A fee table whose amounts carry a currency code (`EUR 5`, `CHF 10`) was skipped whole as a grid of identifiers (QA-extraction-7) | A cell whose letters are a currency word of its language is a value, as a bare figure is. `make extract-rerun` reads passages skipped before |
| A section number with its subsection glued on, such as `Section 7(2)` or `§ 7(2) AGB`, named no section (QA-extraction-8) | A token opening on a section number before a bracket names that section, for the link pass and the bridge check |

### Fixed in v0.4.4: topics

| Defect | Fix |
|---|---|
| Two identical passages could get different topic memberships (QAB-topics-3) | The fit reseeds the projection for each passage, so its weights depend on its vector alone |
| A language with one passage, or only copies of one text, failed every fit, and its facts reached no question unit (NEW-topics-2) | A language whose passages are one text, or cannot be told apart and are too few for a second topic, gets one topic holding them |
| A topic dominant in no passage was sent to the naming model with no excerpt, and `TOPIC_LABEL_MIN_FACT_SHARE` could never fire (QAB-topics-4) | A topic is named only where it is some passage's strongest. `TOPIC_LABEL_MIN_FACT_SHARE` is removed |
| The naming model's "no subject" answer was recognised only as the words *Mixed* and *gemischt* (NEW-topics-3) | The answer carries a `no_subject` field the model sets, in any language (topics prompt 3) |
| The ending most topic names share was stripped even where that left a dangling preposition (*Fees for*) or a lone modifier (NEW-topics-1) | An ending is removed only when it is a prepositional phrase whose first word the language's pipeline tags as an adposition |
| Topic figures and models were keyed by language alone, so a second database on the same object store overwrote production's on its fit or delete (NEW-topics-5) | Both are stored under `topics/<database>/<language>`. A `DATABASE_URL` that names no database is refused. An upgraded database runs `make topics-d…` to rewrite the keys |
| A refit after a language's last document left that language's figure and model in the store, and the figure route served topics that were gone (QAB-topics-5) | The languages whose topics a refit deletes are read first, and their figure and model are archived |
| A word holding a closing script tag, kept as a lemma from an uploaded document, ended the topic map's data script (QA-security-1) | The page writes `<`, `>` and `&` in the data as JSON escapes |
| With `TOPIC_PASSAGES_PER_TOPIC` at 0, a language whose few passages could not be told apart still failed the refit | With the sizing off, a language with fewer distinct passages than `TOPIC_NUM_TOPICS` that cannot be told apart gets one topic |

### Fixed in v0.4.4: the archive, the database and operations

| Defect | Fix |
|---|---|
| A restore could bring a follow-up back released under a root that had left the release (NEW-ops-docs-1) | A restored follow-up keeps its release only under a turn that is still accepted and released in the same release. Otherwise it and every turn below it come back accepted but undrawn |
| The image locks had drifted from `poetry.lock`: 30 shared pins differed, among them pandas 3 against 2.3, protobuf 7 against 6 and Docling 2.132.0 against 2.137.0 (NEW-ops-docs-5) | `make lock` resolves both image locks under `poetry.lock`'s pins, and a static test holds every shared pin equal. The API image runs Docling 2.137.0 |
| The host `poetry.lock` was not audited, so `make audit` stayed green while Dependabot flagged aiohttp there (BL-D6-ops) | `make audit` reads `poetry.lock` too and fails after reading all three locks |
| A command-line value holding `( )`, `&` or a quote, such as `OUT="/tmp/Q&A (final).xlsx"`, failed every target that loads the environment with a shell syntax error (QA-ops-docs-1) | Each command-line variable is exported single-quoted with its own quotes escaped |
| A command-line value holding spaces named its later words in `QA_COMMAND_LINE` as settings a stored row gives way to (QA-ops-docs-2) | `QA_COMMAND_LINE` names only the variables whose origin is the command line |
| `make spend` and `make spend-by-shape` given a `LOG` that names no readable file printed "no priced calls in the log" and exited 0 (QA-ops-docs-3) | Both refuse a missing, unreadable or directory `LOG` with exit status 2 and name it |
| `make audit` read PyPI's advisory service, which lists 18 of the 21 advisories OSV holds on Pillow 12.3.0 and omits a critical one (QA-ops-docs-5) | Every lock is read against OSV. The make guide says the audit runs whole on Linux only, as the nightly job runs it |

### Fixed in v0.4.5: API and settings

| Defect | Fix |
|---|---|
| A setting, topic label or upload filename holding a NUL or a lone surrogate answered a 500 from the database (QAB-api-settings-1) | Each is refused at the edge: `out_of_range` for a setting, 422 for a topic label, 400 `invalid_value` for a filename |
| `EMBEDDING_MAX_TOKENS` accepted 1, which cuts every passage to nothing (QAB-api-settings-5) | The floor is 64 |
| Stop asked Dagster for one page of runs, so a run past it was never stopped (QAB-api-settings-7) | Stop asks for every unfinished run |
| `GET /pipeline/runs` took a limit with no bound, and a Dagster refusal answered 503 `no_orchestrator` as if Dagster were down (QAB-api-settings-8) | The route takes a bounded `limit`, and a refusal answers `orchestrator_refused` |
| The arrivals sensor retried a failed run on every tick (QAB-api-settings-9) | It retries once, then skips and names `make pipeline` and the Run button |
| The orchestrator accepted `nan`, negative and near-zero drain timeouts and poll intervals (QA-security-4) | Its reader takes finite values of at least one second |

### Fixed in v0.4.5: frontend and review

| Defect | Fix |
|---|---|
| A search longer than the 200 characters the listing routes take replaced the page with `Failed to load: 422` (QAB-frontend-review-10) | Every listing's search box holds at most 200 characters, and a static test holds it to the API's bound |
| The Topics search looked in terms joined by spaces while the table shows them joined by commas, so terms copied from the table found nothing (QA-api-frontend-4) | The search looks in the terms as the table shows them, and in the label and the terms each alone |
| A topic name longer than the 120 characters `PATCH /topics` takes was cut to 120 when somebody saved only the coverage choice (QAB-frontend-review-8) | The page sends the name only when it was edited. A pull leaves a longer corrected name in Argilla and logs the topic ids |
| A document's filename went into its panel heading as HTML, so `Konditionen <Entwurf> & Preise.pdf` showed a name no document has (QAB-frontend-review-12) | The heading escapes it |
| A filename was read as Markdown in the Delete question, the spinner and the upload messages, so a name could appear in italics right before an irreversible delete (NEW-api-frontend-export-1) | `page.plain` escapes every ASCII punctuation mark, and the filename goes through it in each place |
| The *How this was produced* fold drew each artefact's text as Markdown, so `$4.99 ... $20` read as math (QAB-frontend-review-11) | The artefact's text and the stage's reason go through `page.plain`. The links do not |
| Accept or Reject pressed for a question that had left the listing was dropped with the message *That row changed meanwhile.* (VAR-press-lost) | The caption names the row. No verdict is applied to a row that has left, because someone else, the gates or a release moved it |
| A compound slot written single for want of a second passage was shown with the spanning prompt it was not sent (VAR-review-kind-2) | The prompt fold says such a slot is stored single and was sent the plain prompt of its type |
| A second fact push before a pull offered the facts already answered in Argilla again (QAB-frontend-review-14) | The fact push leaves them out too |
| The facts review dataset carried no language, though the topic and question datasets do (QAB-frontend-review-15) | A fact record carries the language of its cited passage (`unknown` if none) as `language` metadata. A push to a dataset made before v0.4.5 warns that it is stale |

### Fixed in v0.4.5: the stack and tests

| Defect | Fix |
|---|---|
| A fresh clone switched to a hosted model still sent the Ollama address as the model's base URL (QA-move-2) | The address is dropped when the model is hosted and equals `OLLAMA_BASE_URL`. A gateway address is kept |
| Three model roles shipped pinned to an Ollama model the README never named and `make doctor` never checked (QA-move-3) | `make doctor` asks every model a stage calls, the judge only while the assessment is on, and the README names the three roles |
| A second checkout's images overwrote or reused the first's, and the smoke layer assumed Dagster on port 3000 (QA-move-5) | Image names follow the compose project, and the smoke layer reads the Dagster port from the env |
| `seaweedfs-ui` was a service nothing needed (FIX-R68) | The service, its Caddyfile and its catalogue row are deleted. On an existing stack `up -d --remove-orphans` removes the old container |
| There was no documented hosted-only path to a dataset, no way to run a second stack, no Podman VM size and no ingest step outside the frontend (QA-move-1) | The README and the operations guide document each |

## Found by the QA review of 2026-10-20

A second review read the v0.3.13 to v0.3.27 code: 107 entries (103 rated
findings: 3 high, 47 medium, 53 low; four leads that were not bugs). All three
high findings and 43 of the 47 medium ones are fixed. 38 low findings stay
open (NUL bytes in request bodies, unescaped text in page tables, the cut
after a few abbreviations). The fixes shipped as v0.3.28 to v0.3.36 and
v0.4.0.

### Fixed in v0.3.28: scoped bridges, review kind, dependencies

| Defect | Fix |
|---|---|
| A bridge pass narrowed by `TOPIC`, `SHA` or `PASSAGE` lost bridges | It clears only the bridges opening on a passage of the scoped topics, which it rewrites |
| A narrowed pass or a second `MISSING=1` run wrote a second bridge on a pair already bridged | The pass never offers a pair a stored bridge rests on, whichever side heads it |
| aiohttp 3.14.3 in the host's `poetry.lock` carried three published advisories | `poetry.lock` pins aiohttp 3.14.5 and yarl 1.25.1, and nothing else moved |
| Reviewers rejected compound questions for asking two things at once | The record's metadata carries the kind, and the guideline says a compound question asks two separate things on purpose and is judged one half at a time |

### Fixed in v0.3.29: references

| Defect | Fix |
|---|---|
| A German polite *Sie* addressing the reader was read as a dangling third person plural | A language-keyed table of polite forms is read by the capitalised surface form: a capital form inside a statement is polite, and one opening a statement only where another capitalised polite form follows. `Sie werden geliefert` is still refused |
| A pronoun after an exceptive clause that points back at its sentence's subject was refused | The verb heading the exceptive clause is marked as heading a clause of its own, as for a subordinator. A pronoun with no noun before it stays refused |
| A German *dies* standing for an earlier clause of its own sentence was refused | The earlier finite verb gets the same "heads a clause of its own" test. A *dies* with no clause before it stays refused |

### Fixed in v0.3.30: bridges in samples

| Defect | Fix |
|---|---|
| A compound question could rest on a bridge's own related pair | A compound sample prefers a passage's own claims and never keeps a bridge. A topic holding only bridges is exhausted for a compound slot |
| An unanswerable slot was dealt a bridge and perturbed it | An unanswerable slot is dealt only facts resting on one passage. A slot with only bridges left is skipped and logged while the topic goes on |
| A compound slot's second passage could hold only bridges | The partner is chosen among passages with an unspent non-bridge fact |

### Fixed in v0.3.31: table rows and soft hyphens

| Defect | Fix |
|---|---|
| A soft hyphen in a PDF text layer deleted every drawn hyphen | A soft hyphen directly before a lower-case letter is dropped, and any other is spelled `-`. A word broken at a line end is still rejoined |
| A group row of a table was glued to its first item | A label alone on a row joins the row below only when exactly one lower-case-labelled row with data follows |
| The tail of a wrapped table label was glued to the next row's label | A label-only row opening in lower case, or closing a bracket the label above left open, joins the label above it |

### Fixed in v0.3.32: table footnotes and lead-ins

| Defect | Fix |
|---|---|
| A footnote the converter attached to a table was in no passage | The footnote is written beneath the table in its passage, once, unless it sits outside the body layer or is also listed as a caption |
| A lead-in scoping a long table reached only its first piece | A table is read as a list is when a lead-in is carried to the pieces |

### Fixed in v0.3.33: number readings

| Defect | Fix |
|---|---|
| A price of four or more digits with a fraction was read as no figure | The figure pattern accepts a long head with a fraction and no thousands mark. A plain long head with three fraction digits stays a fraction |
| The same value in another format was refused as an addition | One owner, `nlp.analysis`, reads a figure's value for `numerals()`, `numbers()` and the question gates, which compare values in the text's language |
| A count written out past twelve was read as no number | Cardinals are composed to 99 (German to 999 and the thousands), and word runs join (`twenty thousand`). A word from thirteen up is a number whatever the tagger made of it |
| The English pronoun `one` was read as the count one | A word counts as a number only with a digit, the tag NUM or an ordinal ADJ, through one shared `is_number` |
| A recovery numbering its steps handed the numbers back as figures the key lacks | `unnamed()` strips the step numbers. An item number `n.` is stripped only where two or more numbered items run in order |
| A list opened by an adverb hid its new item | A verb with only an adverb before it and the list under it is a list head |

### Fixed in v0.3.34: review and page vocabulary

| Defect | Fix |
|---|---|
| The questions workbook had no kind column | A Kind column (single, needs_both, compound) follows Type on the Questions sheet |
| A follow-up reached Argilla without the turns it follows | The record has an optional `thread` field with the earlier turns, oldest first, and `turn` metadata. The guideline says a follow-up is judged after those turns |
| The Questions page named a compound question's prompt wrongly and used Kind for two things | A compound question's prompt is named `type (compound)`. `question_type` is shown as Type and the stored kind as Kind, with a help line for each kind |

### Fixed in v0.3.35: a needs_both question needs both

| Defect | Fix |
|---|---|
| A needs_both question kept both passages when each held only half of what it asked, or the same half | A verifier call lists the parts of the answer and quotes each cited passage that states them. The question stays two-passage only when each cited passage holds a part no other holds. Calibration figures are in [measurements.md](measurements.md) |

### Fixed in v0.3.36: a thread leaves the release whole

| Defect | Fix |
|---|---|
| A released thread lost its root but kept its follow-ups released | The trigger `questions_release_thread_whole` clears `release_id` on every follow-up below a question that leaves `accepted`. The upgrade also clears follow-ups already left under such a root |

### Fixed in v0.4.0: reading documents, questions, topics and pages

| Defect | Fix |
|---|---|
| A numbered reference was linked to another document's section | A numbered reference resolves in the head's own document or is dropped. A title names another document |
| A quoted heading with a typographic apostrophe was cut | Double-quoted spans may hold apostrophes, and single marks close only where no letter follows |
| An inflected label word before a number matched nothing | One shared matcher, `validation.label_word`, also accepts an inflected form (at most two extra letters) directly before a number |
| Sibling linking was quadratic in pure Python | Each head scores its family with one numpy product |
| A link whose partner had no validated fact was dropped after the heads were chosen | Heads and partners without a validated fact are removed before the links are dealt |
| A bridge group of three or more strided before it grew | Each head's link is grown before the quota is strided over |
| A passage held two languages | A chunk ends where its prose changes language, on a confident detection only |
| A running head refiled the text above a chapter's opening | A chapter starts at its own heading where its page holds one |
| A price whose digits equal a page number became a heading | Running names and paragraphs must hold a letter to count as a repeat |
| A German *dies* after a relative clause alone was resolved again (a regression of v0.3.29) | A relative verb does not count as the earlier clause *dies* stands for |
| One scanned page inside a digital PDF went missing silently | Each page with no text layer and pictures covering half of it is named in a warning, in the stored parse's `image-only-pages` metadata and in `documents.parse_error` |
| A vectorless passage always won as compound partner and always lost as needs_both partner | One candidate set is ranked on one scale: cosine only where the head and every candidate carry a vector, word overlap otherwise |
| Topic names lost their subject | A shared ending is removed only when none of its words is a top term of the topics that carry it |
| A small language got no topics and the fit reported success | The frequency filter is held to what the language's own passage count allows. A language still without a model fails the fit after the others are stored |
| Redo on the Assessment page wiped every verdict when the assessment could not run | It answers 409 `assessment_cannot_run` before any verdict is cleared, through a check shared with the CLI |
| A document or topic filter hid a cross-document question's other sources | The filter chooses question ids, and every source is still counted |
| A drawn question rejected before the write lost the whole release draw | The draw writes only the drawn questions still accepted and reports the shortfall |
| A re-check overruled a person's accept | A re-check rejects only a question still accepted and not accepted by a person since. `source_changed` alone overrules |
| A fact deleted while the writer ran lost every question of the topic | `store()` reads the surviving facts `FOR SHARE` and skips and logs the thread that lost one |
| A passage deleted mid-run failed a topic fit or stopped the bridge pass | The fit writes the memberships of passages that still exist, and the bridge pass drops and logs the link |
| A kind, band or language held only by unanswerable rows kept a quota the draw could never fill | The supply check counts only rows a draw can take |
| The default language weights counted rows the draw never takes | The weights count drawable rows, as the bands do |
| The size scan walked one draw per size | A bucket's supply counts unanswerable rows only up to the ceiling |
| A restored question kept the release of a draw that a later one superseded | The restore clears `release_id` unless a question live all along holds that release |
| A restore after a refit or re-chunk restored nothing, or left a question on a fact with no passage | A row whose parent is absent is left behind and counted per table. A restored fact with no passage, and a bridge with fewer than two, are dropped with the question resting on it |

## Found on the v0.3.12 rebuild of 2026-10-19

Every row of the v0.3.12 build was read again under a rubric. The releases
from v0.3.13 on fix what the reading found, one fix to a release.

### Fixed in v0.3.13 to v0.3.27

| Release | Defect | Fix |
|---|---|---|
| v0.3.14 | A fact the repair call split out of a statement competed for its passage's cap | A repair-call fact does not compete for the cap, in flight and in `make extract-recap`, which also gives back repair pieces an earlier cap refused. The model's own facts stay capped |
| v0.3.15 | A bridge was checked against its excerpts' text only, so one naming its own heading was let through | The heading trail and title are read as an atomic fact's are. A bridge that writes a cited passage's numbered heading whole is refused as `not_bridging` |
| v0.3.16 | Bridge pairs were each passage's nearest unused neighbour inside its own topic | `links.py` pairs passages by the documents' own links (a numbered or quoted heading named, sibling sections under one parent, a term only two passages share), per language and across topics |
| v0.3.16 | The bridge prompt invented a link on every pair it was shown | Bridge prompt 6 names the link the pairing found and asks for one bridge or none from a closed set of relations with a probe question. The pairing and the prompt ship together |
| v0.3.17 | An unanswerable question was written in any of eight kinds | An unanswerable slot is written only as a factoid, entity or reason question that the mix weights above 0. A mix with none of them writes the slot answerable |
| v0.3.18 | A range written with a dash was refused when the recovery gave its two ends apart | `agrees()` reads a dash range as its two ends. A key naming one figure does not agree with a range, and a range still needs both ends and its unit |
| v0.3.19 | `answer_incomplete` refused complete list keys | The key is refused only when the recovery also names an item the key and question lack (a conjunct, a marked line, a `;` part, a figure in digits, or the object of a coordinated verb phrase) |
| v0.3.20 | A question's kind was implied by its number of cited passages | Every slot carries a kind, `single` or `needs_both`, stored in `questions.kind`. The kind chooses the writer's instruction and the checks a draft gets. `QUESTIONS_KIND_MIX` shares the kinds out |
| v0.3.21 | A question's band followed the spread of its passages whatever its kind | Where a kind sets a band, that band holds. Other kinds keep the points rule |
| v0.3.22 | No question asked two separate things, one from each of two passages | A `compound` kind (off by default): the writer returns two halves joined by "and", each recovered from its own passage alone |
| v0.3.23 | A bridge kept neither the relation it named nor the question it was tested with | A nullable `facts.bridge` column keeps `{relation, question, answer}` for every bridge written by prompt 6 or later, refused ones too. The six relations live in one table |
| v0.3.25 | A stored compound question was refused when reverified | The re-check holds a stored question to the kind it was written as |
| v0.3.26 | Compound questions were built but never dealt | The kind mix defaults to `needs_both:5,compound:1`, one spanning slot in six. `QUESTIONS_KIND_MIX=needs_both:1` turns compound off |
| v0.3.27 | The release draw bisected for a size that fills | The draw scans sizes down from the largest the pool's supply allows and keeps the first that fills |

## Found on the v0.4.0 rebuild of 2026-10-18

The v0.3.8 code rebuilt the same two PDFs. The review found that welds rose
and topics loosened in the v0.4.0 build. The fixes below were measured on the
labelled rows of both builds.

### Fixed in v0.3.9 to v0.3.12

| Release | Defect | Fix |
|---|---|---|
| v0.3.9 | A bridge fact was offered beside an unrelated claim | A bridge is offered alone, whichever passage it was dealt from |
| v0.3.9 | The bridge prompt taught side-by-side claims | Bridge prompt 5's right example is a claim one excerpt changes by defining what the other's rule applies to. Side by side is a wrong example |
| v0.3.10 | A rule written as one statement joining two actions was lost | Statements refused as `not_atomic` go back to the model once per passage under a repair prompt (`repair-1`). What it writes faces every check, the dedup gate and the cap |
| v0.3.10 | A condition the parser hung as a conjunct counted as a second claim | A conjunct opened by its own subordinator, and a clause naming what an exception leaves out, restrict the rule |
| v0.3.11 | One seeded topic fit was kept unread | The fit draws eight factorisations seeded from `TOPIC_RANDOM_STATE` on and keeps the one whose members are most alike |
| v0.3.12 | The settles reading quoted the answering words and still said silent | Verifier prompt 6 asks for the best reply a chatbot could give before the verdict, with examples of an answer in another form. The elsewhere call reads the cited passages beside the probed ones |

## Found on the v0.3.0 rebuild of 2026-10-16

The v0.3.0 rebuild was reviewed in full: 871 accepted questions (70% usable),
343 released (76% on the first reading, 79% once disagreements were settled;
10 invalid), welds at 18% of two-passage questions. Each finding is fixed,
deferred or ranked low.

### Fixed in v0.3.1: model calls, settings and commands

| Defect | Fix |
|---|---|
| The instructor library re-asked up to 3 times inside each of the client's attempts, so one bad answer could cost 12 billed calls | Instructor is told to re-ask none |
| A rate limit's `Retry-After` was ignored because the 429 arrives wrapped, so the call backed off a second | `Retry-After` is read through the cause chain, for at most two minutes |
| A content-filtered answer failed its topic | A refusal ends after one call and the writer skips the slot |
| Failed calls were never costed | Every attempt is summed onto both log lines, and `make spend` reads both |
| Ollama-only options were sent to hosted models | They are sent only to the provider they belong to |
| A recommended mode stopped every stage | The stage takes the 8 modes it supports, and others are refused at start-up |
| A recalibration rewrote stored scores | Both the old and the new scores are kept |
| A copied `backend.env` stalled the question worker because a missing setting had no default | An absent setting reads 0.02 |
| An old API build went unnoticed | `make doctor` names the settings the API lacks |

### Fixed in v0.3.2: reading text and numbers

| Defect | Fix |
|---|---|
| An abbreviation before a figure ended a sentence | An abbreviation followed by a figure does not end a sentence, unless a line break or an item number follows |
| Two rules each ending in a full stop read as one sentence | A free dash or slash after a full stop and a space opens the next sentence, but not after an abbreviation |
| `provided` was read as an exception | A finite `provided` is read as the verb it is, from the parse's morphology |
| Times and glued figures carried no number | They are read into their own claim field and compared group by group, so `08:00` equals `8:00` and not `09:00` |
| A German decimal was read as an integer | A per-language `DECIMAL_MARK` decides. One mark before three digits that a key writes is read both ways, and a zero head is always a fraction |
| An aggregation key was accepted unasked | The verifier is asked for every aggregation |
| A relabelled aggregation kept its old level | The relabel takes the new kind's level |
| Figures-only paragraphs were dropped | Only a page number's shape is dropped |
| A hyphenated word broken across a table cell or a page stayed broken | The repair runs after them too, with a per-language table of completing words |

### Fixed in v0.3.3: the unit of a fact

| Defect | Fix |
|---|---|
| Dedup refused facts against facts about to be deleted | The extract worker replays dedup itself once its queue empties after replacing facts, under a database lock |
| A statement the tagger mis-rooted counted as two claims | The root is read past a subordinator |
| A verb the tagger gave a finite fine tag but no verb part of speech asserted nothing | The fine tag is read too |
| A fact copying one sentence was judged on the sentence counts stored at chunking | It is judged on the claims it reads as |
| A verbatim repeat inside one passage was kept twice | It is refused as a duplicate of the passage's own fact |
| Refusal messages misstated the dedup bar and reported over-cap twice | The messages are worded as the settings are set |
| A "the model proposed nothing" warning fired where no model ran | It fires only where a model read the passage |
| A figure table or priced list was skipped as an identifier grid | A figure in a cell is read as the value it is |
| A fact citing no sentence was dropped | It is stored as `evidence_absent` |

### Fixed in v0.3.4: round trip, reasons and typing

| Defect | Fix |
|---|---|
| The entailment rescue overrode a verifier that found nothing | A key the verifier read as not in the passages is refused, not rescued |
| The round trip asked the verifier for what only the writer was shown | A name the question carries, or every heading trail of the cited passages, does not have to come back unless the recovery names another. Figures never get this exemption |
| A German adjective tagged as an adverb did not come back | A lemma comes back under an adjective or an adverb unless a negation denies it |
| A set of kinds written as adjectives was refused as one thing | A coordination with no noun phrase is a set, unless a conjunct is a verb or a number |
| German *wo-* question words were missed by `compound` | A per-language table of question adverbs is read |
| The shadow coverage reading was stored on only half the answers it applies to | It is stored on every eligible answer, still in shadow |

### Fixed in v0.3.5: release record and unanswerables

| Defect | Fix |
|---|---|
| The release draw left no record | A trace has one span per twin round, one log line per judged pair with both ids and the verdict, and each bucket's distance from its quota |
| A correct answer was silenced because its quote was stitched from pieces | The quote is looked for piece by piece, each piece as whole words of one shown passage |
| A quote matched inside a longer word | Pieces match on word boundaries |

### Fixed in v0.3.6: parsing and chunking

| Defect | Fix |
|---|---|
| A re-chunk deleted every passage and the facts and questions on them | A passage whose text, section path, sentences and cells are unchanged is kept with its id, facts and topics |
| Hidden labels survived into passages and headings | A clipped character counts as shown only where the same character sits at the same place in the visible read |
| A continued table stopped at a row the converter flagged as a header | The row joins as data when it is set in the first table's data type and its cells match that table's column types |
| List depth was lost at column and page breaks | Depth is measured from each column's own edge, from text and list blocks only, with no new level across a break |
| A lone conjunction was promoted to a heading | It is read as text between two items or paragraphs of one passage, through a per-language table |
| A joined block or table cited only its first page | It cites every page it spans |
| `third- party` was mended to `thirdparty` | A hyphen is kept where the document prints the compound with it elsewhere |

### Fixed in v0.3.7: topics and the scope of a fact

| Defect | Fix |
|---|---|
| A topic's name carried onto the wrong topic | A person's decision moves only to the topic holding most of the same passages. A model's name is never carried. A decision with no match is dropped and counted |
| A fit reported itself stale the moment it was made | One shared rule decides staleness for both the fit and the page |
| A name or coverage choice saved while a fit ran was overwritten | The choice is carried again, under a lock on the rows the fit replaces |
| Smaller topic bookkeeping faults | Each is fixed. A dropped decision of a vanished language is logged and counted |
| Facts dropped the scope that a heading or a list's lead-in sets | Atomic prompt 12 names the heading trail as the situation a rule holds in and keeps a closing lead-in (*the only exceptions are*) as one fact. Digest prompt 5 keeps *should* and *may* |

### Fixed in v0.3.8: security, the frontend, orchestration and the docs

| Defect | Fix |
|---|---|
| Settings accepted values no service could run with, such as `nan`, a misspelt *true* or an unbounded topic count | The values are refused when written. A stored value outside its bounds is shown with a warning |
| The workbook export wrote cells starting with `=` as live formulas | They are written as text |
| The API docs page loaded a floating Swagger script from a CDN | The assets are pinned and `/redoc` is removed |
| Stop stopped only the newest run | Every queued or started run is stopped, and a run already stopping is said to be |
| A run whose worker died blocked the queue | Dagster's run monitoring is on, and a cancelling run counts as going |
| A topic `PATCH` reset what its body left out | It changes only what it names |
| A failed worker rebuild asked the model again every five seconds | It backs off, per version |
| The review sample drew questions already reviewed | It draws only unreviewed ones |
| Annotations stopped for good after one failed flush | They resume |
| A span named the worker's process run, not the run that queued its row | Every span of a row names the run that queued it |
| `make eval-score` scored a reader that production does not run | It scores the production reader |
| Deleting every document forgot the upload history first | It forgets uploads last, and the document listing says when it is cut |
| The configuration panel wrote stale values and showed `0.985` as `0.98` | The panel sends what it drew, redraws after a change, and keeps each number as written |
| Smaller frontend faults, such as confirming a fit twice or a refused write replacing the page | Each is fixed |
| The stack trusted any host name and any missing secret | Streamlit answers only `localhost` and `127.0.0.1`, and compose stops and names a missing secret |

## Found on the v0.2.2 rebuild of 2026-10-14

The run of 2026-10-13 (1,476 questions, 576 accepted, 238 released, 49% of
released rows usable, release 79% German) was read by hand against its
sources, and each defect was traced to its cause in the code. The v0.2.2
rebuild of 2026-10-14 ran the same corpus on `azure/gpt-5.4` (writer) and
`azure/gpt-4.1` (everything else) and was read in full: 475 of 837 accepted
questions usable (57%, against 50%), 166 of 321 released (52%, against 49%). A
hand review of the v0.3.0 rebuild checked its 41 defects again: 19 fixed, 16
fixed in part, 2 not fixed (circular *why* keys, release twins), 4 worse
(`not_atomic` refusals, duplicate refusals, repeated-heading and figure-only
passages, wrong type labels). What the v0.3.x releases fixed since is under
[Found on the v0.3.0 rebuild](#found-on-the-v030-rebuild-of-2026-10-16).

### Fixed in v0.2.2 and v0.3.0, from the 2026-10-13 run

| Defect | Fix |
|---|---|
| The release drew the language written first (187 German against 51 English released) | Language shares in `balance.py`, in the pool's split unless `QUESTIONS_RELEASE_LANGUAGES` weighs them; buckets drawn in md5 order of the question id |
| Fact dedup folded a different rule into a stored fact (24 released questions) | Facts with different numbers are never duplicates; a refusal writes nothing onto the fact it repeats; `EXTRACTION_DUPLICATE_COSINE` 0.985. Repair stored corpora with `make extract-dedup`, then `make questions-rescore` |
| The widen retry replaced an honest draft (5 rows) | The widen retry is removed |
| The count rule misread stated counts | A count in a cited statement is exempt; bare counts are refused whatever the question opens with |
| Sibling list items refused as duplicates (42 released questions) | A passage's own facts are compared across kinds only; the per-passage cap never falls below its sentences plus list items |
| Application questions always spanned two passages (11 released) | A one-passage kind is dealt its one passage at every band |
| The perturbation prompt read "not stated" as "unanswerable" (49% answered by their own material) | Prompt names refuted premises, closed lists and general rules as answered; `PROMPT_VERSION` 12 |
| Struck-through text read as current (471 struck words, 8 released questions) | Words with a drawn horizontal line are removed at conversion; a re-parse is needed |
| Stale section paths, running feet and index letters | Chapters are read from running heads and feet; running feet, index letters and bare conjunction segments are dropped; a re-chunk is needed |
| `off_topic` refused every perturbation (27 of 27 wrong) | `QUESTIONS_OFF_TOPIC_OVERLAP=0` turns the gate off |
| `restates_question` read nouns only | Reads verbs, adverbs and interjections too; a yes or no answer counts as an answer |
| The round trip missed verbs, number words and counts (7 usable lost); v0.3.4 asked the verifier for what only the writer saw | Value keys compare on verbs, number words read as figures, count questions go to the model; names and heading words need not come back |
| An embedded question word read as a second question | A further question word counts only after a coordinating conjunction; German `wo(r)` plus preposition read as question words (v0.3.4) |
| A pronoun its own statement resolves read as dangling (48 of 95 refusals) | A personal pronoun is resolved by an earlier agreeing noun outside its own clause |
| A translation read as furniture (16 passages) | Repetition is read within one language only (v0.3.0) |
| `explanation_unusable` read any proper noun as a name (3 usable lost) | The gate reads an explanation's figures only (v0.3.0) |
| A refusal used as a key | The writer's `declined` field writes the slot as another kind (v0.3.0) |
| `asks_nothing_new` on outline facts | A turn citing only its root's summary or outline moves on when a quarter of its key's content words are new (v0.3.0) |
| A refused model call failed its whole topic (content filter on the retry note) | A prompt refused under a content policy is sent once and costs one slot; a topic fails after five refusals in a row; retry notes read as reviewer feedback (v0.3.0) |

### Parsing

| Defect | Fix in v0.3.0 |
|---|---|
| A struck word survived, or took its neighbours with it | Strike-through is read per character. A bracket or comma beside a deletion stays |
| Text the page hides was read as body text (14 passages of signal-diagram labels) | Text the page clips out of view is dropped. A label printed in view stays |
| A raised ordinal such as `1 st` was read as a separate word | The superscript suffix is joined to its number |
| A table broken at a page or inside a wrapped cell | A header-less table right after one of its width joins it, and a wrapped cell or label rejoins its row |
| A two-column page was interleaved (2 passages) | Not fixed: reading order needs a better layout model |

### Chunking

| Defect | Fix in v0.3.0 |
|---|---|
| A one-page chapter lost its label (chapter missing on 20 German and 23 English passages) | A one-page foot laid out as a chapter's names the chapter. Guide words still name none |
| Chapter labels were letter-spaced in 178 German and 97 English section paths | A label takes the spaces the body puts in the same words |
| A lead-in was cut from its list by a sub-heading, or a sentence was cut by a page | The lead-in travels into the sub-headed chunk, and a sentence cut at a page or column joins its rest |
| A repeated heading or a page number became its own passage | A paragraph equal to a heading heads the passage after it, and a figures-only paragraph is dropped |
| Stale one-letter index segments (66 English passages) | Index letters are read from headings and text, and the longest run in order is the index |
| A nested list was flattened (152 German and 154 English items) | An indented item nests under the one above and is rendered indented |
| Heading levels came from numbering out of sequence | Not fixed: it needs Docling's style inference, which is not public |
| A group heading sat at its children's level (4 passages) | Not fixed: the headings differ only in font family and colour |

### Extraction

| Defect | Fix in v0.3.0 |
|---|---|
| A fact dropped its rule's scope (486 of 3,578 facts narrowed) | Atomic prompt 11: the smallest statement true read alone, with conditions, exceptions, *only* and modality kept and lead-ins restated and cited. Facts dropping a scope word fell from 16.6% to 10.8% (German) and 30.9% to 28.2% (English) |
| Sound facts were refused as `not_atomic` (25 German, 92 English) | A rule and its exception, and two alternatives, count as one claim |
| Sound facts were refused as `unresolved_reference` (84 German, 88 English) | Pronouns are resolved by the language's grammar |
| Sound facts were refused as `asserts_nothing` | A root verb with a subject counts, as does a German or Dutch plural spelled as the infinitive |
| Evidence was cut mid-sentence (76 German and 43 English facts) | No cut inside a slash-joined word, before a comma clause, after an abbreviation before lower case, or between an item number and its item |
| Sound facts were refused as `unsupported_addition` (43 German, 72 English) | Names and numbers are read against the evidence, the section path and the title, with numbers in any spelling |
| A different rule was refused as a duplicate (231 refusals, 13 wrong and 22 partly wrong) | Not fixed. A guard treating near statements as twins only when every word one has and the other lacks is in the other's passage was built and reverted |
| Summaries were about "the excerpt" (61% German, 78% English) | Digest prompt 4 opens on the subject. Summaries opening on the excerpt fell to 0% |
| Facts were written about the document itself (53 validated) | A prompt rule forbids them, and repetition is read within one language |
| No bridge fact was ever written | The bridge pass runs in `make corpus` for topics holding none |

### Topic modelling

| Defect | Fix in v0.3.0 |
|---|---|
| Labels were read off headings and stubs | Excerpts come from fact-bearing passages, ordered by weight times length |
| Headings and page numbers were fitted as subjects | The fit uses passages carrying a fact |
| Every label named the domain (9 of 10 German labels end "im Fußball") | One naming call per language, spelling held to the excerpts, and a shared trailing phrase taken off |
| A topic's passages were never asked about | A passage in no topic joins the nearest centroid |

### Question generation

| Defect | Fix in v0.3.0 |
|---|---|
| Two facts were welded into one question (128 of 270 two-passage questions) | A second passage is offered only where its closest fact is among the topic's closest 2% of pairs, and never a restatement |
| The release drew every hard question | The band split follows the answerable pool |
| Keys named only part of a list (79 released incomplete keys) | A reading or list slot is offered the whole list, up to eight items. Prose keys are read in shadow |
| Unanswerable questions the corpus answers (141 of 283 accepted) | The quote is held to the passages, a probe of twenty passages is fused by vector and words, and settled ones are recycled into answerable questions. The release share is 0 |
| Circular "why" keys (25 of 50 accepted reason keys) | A why whose recovery only restates the question is refused before the entailment rescue |
| A change log's quotations were used as the source (114 accepted questions) | An elided passage is dealt last and never to a list slot |
| Release twins (6 released twin pairs) | The verifier judges each released question against its nearest released neighbour |
| Follow-up comparisons were refused (141 of 151) | Comparison is out of the follow-up kinds, and suspended hyphens count as items |
| A rescued key was not checked for completeness | `incomplete` runs after the rescue too |
| A thread's later turn was refused | `off_thread` reads the whole thread, a negative or a party counts as an answer, and a summary turn moves on when its key is new |
| Sound explanations and numbered rules were refused (29 `explanation_unusable`, 11 `leaks_source`) | Explanations are held to figures, a numbered article, clause or rule is a subject, and a section is a source |
| Retries returned the same draft (22 of 291) | The note quotes the draft, and an unchanged retry is not stored again |
| A refused prompt failed its topic | A content-policy refusal skips one slot |
| Wrong type labels (160 of 837 accepted) and meta-text (73 explanations) | The type is read off the opening, a count with no figure is relabelled, and the writer may decline a slot |

### After the fixes

Counts of the v0.3.0 rebuild (2026-10-16; the weld rate and wrong duplicate
refusals come from a later hand review). Each cell reads German, then English.
[measurements.md](measurements.md#the-v030-rebuild-of-2026-10-16) has the run.

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

## Known trade-offs

### More citations, fewer questions

Giving boilerplate facts their missing citations moved 6 accepted questions
from one passage or document to several, and re-verification rejected them as
`source_changed`. A fact now cites its own passage alone. A claim two
documents hold is a fact on one and a `duplicate` refusal on the other. `make
delete` and `make delete-derived` run `make extract-dedup` afterwards, and an
idle extraction worker replays the dedup after a deletion through the API or
the pages. Where no extraction worker runs (the production profile), run `make
extract-dedup` after such a deletion.

## Reproducing this page

The counts are queries over `questions`, `facts`, `question_facts` and
`fact_passages`. The same rows come out of the workbook:

```bash
make questions-export OUT=audit.xlsx FILTER="--released"
```

Each entry's root cause was confirmed in the code and reproduced by a test
before it was fixed. Re-measuring means taking a corpus through again and
rewriting this page and [measurements.md](measurements.md).
