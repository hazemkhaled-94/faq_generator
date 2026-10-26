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
| The figure-swap guard misses kinds it cannot type (*Werktagen* against *Tagen*, *per cent*) (C-020). One German clause pair reads as one claim (C-019) | Each kind is a word table per language. Found by probes outside the measured corpora |
| On Linux bash a stop gives the row back at once, and a worker stopped during `make corpus` leaves the wait polling (C-006) | Needs host process bookkeeping. Stop a run with `make corpus-hosted-stop` and read its log |
| Not run live: the production `make up` with a row queued per stage, the restore and two-database drills, the stale-lock check in a container, the walk from a fresh clone, the kill mid-row (C-001, C-003 to C-006, C-010, C-013, C-042, C-079) | Each needs a scratch stack. The offline halves pass. Run the Verify lines on the deployed release |
| The 10x load test's single-pass dedup probe p95 is 2.15x to 7.80x the build's size on CI, against a bar of 2x. The median stays 6.0 to 6.9 ms (C-011) | Decided 2026-10-26: the database is about 2% of a drain's time at ten times the build, so the sizing ships and the probe time is watched |
| The blind topic relabel and the refit drill are not run (C-095, C-055) | C-095 ships on its offline fit replay (passes at 0.4, 0.5 and 0.6) |
| From 2,000 rows the release found is at most a hundredth below the largest that fills (C-089). More than two extraction drains are not measured (C-026) | The bar allows 2%. The deployment runs no more than two |
| The corrected interval covers under 0.93 at 13 to 15 of 71 label counts from 30 to 100 (average 0.935) (C-067) | The item's bar and unit tests are met |
| Three page numbers stand as passages again in two spread PDFs (C-182) | The fix misread single pages elsewhere |
| Two-passage questions stay a slice to report apart: 0.548 of released ones usable (n 126) against 0.841 (C-014) | Every design to catch the welds failed its bar |
| C-037 and C-038 ship though their own bars missed on the rulebooks (ambiguous tag 2 to 5, not-standalone 5 to 3) | The arm bar that decides a change to what is written passed on both corpora. Confirmed 2026-10-26 |
| A question that lost its last fact before the upgrade carries no stamp, so a deletion of its document leaves it (C-001) | The stamp exists from the migration on |
| Two database names differing only in characters the stores reject (`qa.x`, `qa_x`) share one scope in Phoenix, Argilla and the logs (C-005) | Give databases names that differ in letters or digits |
| A release export lists a document whose accepted questions were not drawn. Two documents sharing a title print as two alike rows (C-023) | `make questions-status` counts them over the whole corpus |
| A currency in brackets after a space-grouped amount (`12 500 (EUR)`) reads as two figures (C-052). Spanish and French dates read as author and year (C-144, C-188) | No stored text changes (0 of 30,808). The parse refuses unconfigured languages (C-008) |
| A property test can fail on a recovered list whose first item is new | Found on the release's base, pinned for the owner of that reading |

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
| FIX-R15, FIX-R37 | A follow-up gate through `adds_to` has too few rows (about 10 in 60) to measure. No stored signal separates usable rows (confidence AUC 0.55 on 298 rows) |
| FIX-R42, FIX-R66 | Product decisions: difficulty bands grade spread by design, and whether a container may call a hosted model |
| BL-C1, BL-C2, FIX-R43, FIX-R90, FIX-R84, FIX-R94, FIX-R58, FIX-R75, QAB-llm-nlp-5, -6, -8, FIX-R53, FIX-R112, VAR-link-pass-1, FIX-R87, FIX-R128, QAB-api-settings-6, -10, FIX-R113, FIX-R85, VAR-review-kind-1, FIX-R109, FIX-R67, FIX-R111 | No effect on current corpora or defaults, refactors without behaviour change, self-hosted-model cases, rollback-only or tooling items |
| NEW-parse-chunk-6 | It would change `content_sha256` of every stored document and need every document parsed again |
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
| Topics listed by every membership over the floor | It would change the catalogue, pages and exports for no measured failure |
| Validated facts read a few points less correct than v0.3.0's (85.6% against 86.7%) | Within reader noise. Atomic prompt 12 writes a wrong heading into facts (about 0.2 points) |
| A duplicate refusal can name a twin since deleted (35 of 180) | Low |

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
| Generated German writes *ß* where the corpus writes *ss*. Writer meta-text and gender drift | Low |
| The API, Streamlit and Dagster have no authentication | Each binds to 127.0.0.1. Production adds `API_TOKEN` (v0.5.2) |
| Dagster's corpus job lacks the bridge pass `make corpus` runs | It waits for a bridge pass worth running unattended |
| Images and installs are not hash-pinned. Workers hold more credentials than they need | Infrastructure changes beyond a patch release |
| A language missing from a word table disables a gate. Review push loads facts one query at a time. Tooling odds and ends | A static test holds every table to `NLP_MODELS`. No wrong result |

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
| A re-chunk or re-extraction deleted the accepted (C-001) | A passage or fact that comes back identical keeps its id |
| A database name exported in the shell was replaced (C-002) | An exported `APP_DB_NAME` is honoured |
| No backup or restore procedure (C-003) | `make backup DIR=` dumps the application |
| Object keys were the document's digest alone (C-004) | Every key is stored under the database's name |
| `make wipe` and the external stores were not scoped (C-005) | Phoenix projects and golden sets, Argilla datasets |
| A restore put back every row archived since a time (C-042) | `make restore-documents AT=` puts back only the deleting transactions it names |
| `make wipe` ran six irreversible steps with no preflight (C-087) | `make wipe-preflight` authenticates to each running store before the first delete |
| The archive grew without bound (C-118) | `make archive-purge` deletes in committed batches of 10,000 rows |
| A question rejected `source_changed` stayed rejected after its sources were (C-166) | The restore counts such questions, names the first 20 and `make questions-reverify` |
| A failure between archiving a document's objects (C-203) | The rows go inside a transaction |
| A NOT NULL column added after a row was archived (C-211) | The restore fills such a column from its default |
| A document deleted while it was parsed left an orphan (C-222) | The parse worker reads the document's row again before it writes |
| A restore after `make delete-derived` re-chunked documents it did not (C-332) | Only documents with a restored passage are re-chunked |

### Fixed in v0.5.2: the model path and the production host

| Defect | Fix |
|---|---|
| The containers had no hosted-model path: the question worker fell (C-006) | `make corpus-hosted` runs the corpus on the host |
| The checkout, its `.env` and the certificate keys sat in a synced folder (C-012) | `ENV_FILE` names a secrets file outside the checkout |
| The production build ran through a private runner (C-013) | The runbook in the operations guide |
| No committed file described the model split (C-051) | `.env.example` ships the seven role models and `LLM_REASONING_EFFORT=none`, and `backend.env` names none |
| One 8-hour timeout bounded every orchestrated stage (C-073) | With `HOST_RUNNER=1` the orchestrated path is off: `make all` |
| `make corpus` fitted no topics (C-048) | It fits them between extraction and the bridge pass |
| Every model-loading stage asked the Hugging Face Hub at run (C-072) | `make doctor` reads the cache: each encoder at its pinned commit with its weights |
| `make doctor` proved the models with the environment (C-074) | It asks with the settings the stored rows make |
| Half the 23 containers served nothing on the production path (C-080) | Argilla, Redis and Elasticsearch, Filebeat and Grafana, and Adminer sit under profiles |
| Builds filled the engine's disk across upgrades (C-086) | `make upgrade` checks the free space against `UPGRADE_FREE_GB` |
| litellm downloaded its model map from GitHub at every import (C-088) | `LITELLM_LOCAL_MODEL_COST_MAP=true` is committed |
| Hugging Face models loaded by bare repository id (C-117) | `EMBEDDING_MODEL_REVISION`, `NLI_MODEL_REVISION` and `QA_MODEL_REVISION` pin each load, the chunking tokenizer's included |
| A stored override beat the file for good (C-119) | Every stage checks the stored rows against the catalogue |
| A database password holding URL characters broke the connection string (C-201) | `make doctor` and `make corpus-hosted` refuse an `APP_DB_PASSWORD` holding `@ / : # ? %` |
| `.dockerignore` sent workbooks and PDFs of the corpus owner into (C-253) | It lists only what the three Dockerfiles copy |
| `POST /pipeline/run` read a Dagster error as nothing running (C-255) | It answers 503 |
| The judge-marking-its-own-work warning compared the judge with `LLM_MODEL` alone (C-355) | It compares with every role whose output the judge reads, naming each |
| One `LLM_BASE_URL` serves every role, unsaid (C-366) | The configuration guide says so, and that a split across resources needs |
| A queue verb answered 202 (C-417) | On the production profile its answer names the command that drains the stage |

### Fixed in v0.5.2: drains that stop and say why

| Defect | Fix |
|---|---|
| A drain proved its model once (C-009) | A drain exits 3 when a row failed |
| A failed digest call discarded the passage's atomic facts (C-041) | The facts are kept and the passage is noted |
| Nothing bounded a drain's spend (C-091) | `SPEND_CAP` stops every drain, the bridge pass |
| A settings change reached no stored row (C-057) | The digest pass also digests extracted passages above `EXTRACTION_DIGEST_MIN_CHARS` that hold none |
| Workers got 10 seconds on a stop (C-079) | A worker told to stop finishes its row |
| More than two drains a database hit the provider's rate (C-082) | A rate limit is waited out for its `Retry-After` |
| An artefact deleted while the judge read it ended (C-136) | It is logged as gone and the drain takes the next row |
| A call litellm cannot price was logged with no cost (C-219) | It is logged as unpriced and warned about once a model |

### Fixed in v0.5.2: parsing and passages

| Defect | Fix |
|---|---|
| Clauses the converter's bookmark pass made headings reached no passage (C-007) | A heading that is a member of a list is read |
| A document in a language no configured model names (C-008) | It is refused at parse, naming its language |
| Titles named nothing, were cut off or collided: 14 (C-096) | A PDF is titled by the heading that heads it in the largest type |
| Text a reader cannot see passed every parse step (C-107) | Text in render mode 3, fully transparent |
| List nesting and column breaks assumed left-to-right scripts (C-108) | A list or column in a right-to-left script is read from the right |
| A few garbled pages passed the confidence floor with no (C-109) | Every page under `PARSING_MIN_CONFIDENCE` is named in the parse note |
| A table continued on the next page was joined wrongly (C-121) | A continuation joins its table when a column sets header |
| A running head of the other language's edition stood (C-187) | A body paragraph where three or more other pages' running items sit |
| Heading-only passages from the change boxes of a rulebook (C-230) | A list item alone in its list that repeats a heading leaves |
| A small spaCy pipeline changed what a fact is, silently (C-348) | A small pipeline, or one without word vectors |
| A letterhead named a chapter of one page (C-368) | A running item printed once on the first page names no chapter |
| A two-column page read across the gutter interleaved its columns (C-426) | Such a page is named in the parse note |

### Fixed in v0.5.2: scale

| Defect | Fix |
|---|---|
| One Postgres capped at 1 CPU (C-011) | `deployment.env` sizes the container and the server for the production corpus |
| Question slots stopped growing at 40 topics a language (C-024) | `TOPIC_NUM_TOPICS` ships at 300 |
| Term links grew with the square of the corpus (C-027) | A term is rare in at most 0.5% of a language's passages |
| The deal built a dense cosine matrix over each topic's (C-070) | A large topic's floor is read from a sample of 200,000 pairs |
| Nothing bounded a document's pages before conversion (C-076) | `PARSING_MAX_PAGES` (180) refuses a longer document before conversion, naming its pages |
| No sizing guide for a large corpus (C-084) | `make estimate` prints the time, calls |
| The release scan drew once a size (C-089) | The scan starts where the pool can place the release |
| Every dedup probe joined the citations (C-090) | A fact carries its language |
| The bridge pass held every vector as Python floats (C-099) | float32 arrays and one parse |
| Nothing said how many of its slots a topic wrote (C-185) | One line a topic says both |
| A compound slot that found only bridges abandoned the rest (C-236) | It is passed over and the later slots are written |
| Sibling linking was quadratic (C-277) | The eight nearest siblings are picked with a partition |

### Fixed in v0.5.2: facts

| Defect | Fix |
|---|---|
| `unsupported_addition` refused sound facts: only the cited sentences counted as support (C-020) | An atomic fact is supported by its whole passage |
| `unresolved_reference` refused facts whose demonstrative names the document itself (C-021) | A demonstrative names the document when its noun is the head |
| `not_atomic` refused a German rule whose verb-final clause carries (C-019) | A verb-final clause after a comma |
| `not_atomic` refused a bridge's contrast or limit (C-033) | A bridge whose relation is a contrast or a limit may carry two |
| The entailment encoder cut a long passage at 512 tokens (C-065) | A long premise is read in overlapping windows of sentences |
| A duplicate refusal kept no twin id (C-068) | `facts.twin_id`, set NULL when the twin goes, and indexed (revision `7a41c9d2e8b0`) |
| Long list passages never got a digest: the floor counted claims (C-098) | The floor counts claims and list items together |
| `make extract-revalidate` rewrote every fact row (C-111) | It reads in keyset batches and writes only the facts whose verdict |
| `evidence_absent` refused list lines inside the passage's last sentence (C-129) | A citation one past the last sentence names a line of it |
| A passage's outline was refused as a duplicate (C-137) | They are never twins of each other |
| A fee table in a currency beyond EUR (C-416) | A currency is an ISO 4217 code or any currency sign |

### Fixed in v0.5.2: questions, topics and the workbook

| Defect | Fix |
|---|---|
| A why-question planned unanswerable was refused as answered (C-022) | The settles reading takes such a quote as silent |
| Small documents got no question: 9 of the 30 PDFs (C-023) | The deal gives each document of a topic its share first |
| The writer wrote questions that need the document to make sense (C-037) | Writer prompt 32 tells every writer the reader never sees the passage |
| The self-contained judge refused a question naming a set the domain fixes (C-422) | It is shown definite sets and a repeated noun |
| Topics bound unrelated passages: weak memberships over a floor (C-095) | `TOPIC_RELATIVE_WEIGHT` (0.5) keeps a membership at least half the passage's strongest, replacing `TOPIC_MIN_WEIGHT` |
| A refit deleted the topics a question worker held (C-055) | A refit keeps a topic generated |
| A workbook row did not stand on its own (C-102) | The Questions sheet gives each row its earlier turns |
| The workbook named the difficulty band hardness (C-029) | The band is titled Retrieval spread |
| An English date read as an author (C-144) | A date the entity reading marks is no citation |
| A follow-up was stored `needs_both` under a root narrowed (C-363) | A follow-up is dealt the kind its root was stored as |
| The parts reading never ran on derived questions (C-034) | A derived question citing two passages is read by parts like any `needs_both` |
| Space-grouped amounts with a marked currency or a price dash (C-052) | Such an amount is one figure, before or after any currency sign |
| A compound question's halves were not stored (C-053) | Both halves are kept in `gate_scores`, through a structural refusal and a recalibration |

### Fixed in v0.5.2: platform, security and tests

| Defect | Fix |
|---|---|
| The API took every write from anyone who could reach it (C-085) | Every write and every read of `/settings` carries `API_TOKEN` as `X-API-Token` |
| Any web page the operator opened could trigger the costly (C-202) | A cross-site request is refused on every method |
| Error paths sent the database's host (C-139) | An unhandled error is answered with one fixed sentence and logged whole |
| Whole-stage reruns and `DELETE /topics` acted on one click (C-040) | They need `confirm=true` and name what is at stake, and Redo asks first |
| The API opened every upload with no page or time (C-299) | `MAX_FILE_SIZE_MB` is bounded at 150, and a PDF over `PARSING_MAX_PAGES` or read past `PARSING_TIMEOUT_SECONDS` is refused |
| The Upload page took any number of files into memory (C-114) | It refuses more than 20 files or 200 MB |
| The judged sample represented neither the pool nor the release (C-059) | Each stratum in proportion to its size |
| A label defined on part of the judged rows (C-039) | Rows labelled `na` leave both counts |
| The PPI interval was asymptotic and per row (C-067) | Under 30 labels the labels' own Wilson interval |
| The diversity tables pooled languages (C-237) | Each fixed as named |
| The bridge pass and the rejudge left no trace (C-069) | Each exports a span per link or question |
| Phoenix kept every prompt, every passage, for ever (C-103) | `make up` sets the default trace retention to `PHOENIX_TRACE_RETENTION_DAYS` (30) |
| Phoenix's cost and the runner's differed (C-198) | The cost log is named the spend of record |
| A deletion through the pages or the API did not (C-054) | Every deletion says how many duplicate refusals lost their twin |
| Status reads hashed the whole queue (C-105) | A status read hashes rows only |
| The Questions page recomputed whole-corpus joins about 18 times (C-113) | One statement, its filter read once |
| Two of three texts on the categorization default left out (C-206) | All three name it |
| The end-to-end test stopped at writing questions (C-043) | It goes on through the bridge pass |
| No test ran a real PDF through Docling (C-110) | `make test-golden` converts and chunks shop pages |

### Fixed in v0.5.2: the documents, dependencies and what the release's own checks found

| Defect | Fix |
|---|---|
| The configuration guide said no file overrides another (C-254) | It says `.env` may, and `make doctor` lists every name it sets over |
| This page gave two stale Pillow counts (C-418) | One statement, in the finalize review's deferred table |
| Pillow 12.3.0, with advisories fixed only in 13.0.0 (C-083) | Docling 2.142.1, docling-core 2.104.0, docling-parse 7.23.0 and Pillow 13.0.0 |
| With the data-safety and model-path changes together | `make corpus` and `make corpus-hosted` take a database from the command line or the environment |

## Found by the papers programme of 2026-10-22

Before v0.5.0 ships, every open item was listed (236) and ranked by what it
would do to a large build. The full build after v0.5.0 found two defects in
its start.

### Fixed in v0.5.1: the full build's start

| Defect | Fix |
|---|---|
| The Dagster webserver and daemon failed at start | the storage URL names `postgresql+psycopg2`, the driver dagster-postgres installs |
| A split pairing a reasoning writer with a verifier | the effort is not sent to a hosted model litellm knows does not |

## Found by the finalize review of 2026-10-21

A third review took the 269 items open at v0.4.2 (177 confirmed, 66 already
fixed, 8 refuted, 8 wrongly stated, 10 transferred to the DataMorgana paper
features) into v0.4.3 (questions), v0.4.4 (reading documents) and v0.4.5 (API,
frontend, stack).

### Fixed in v0.4.3: questions

| Defect | Fix |
|---|---|
| A compound slot planned hard kept the band hard (QAB-qg-plan-2) | a compound slot is planned at the medium band its kind fixes |
| A follow-up on a compound pair was stored `needs_both` (QAB-qg-plan-8) | a follow-up is stored `needs_both` only where its root was dealt `needs_both` |
| A compound partner's facts were ranked toward the head (QAB-qg-plan-7) | a compound partner offers its own facts in its own order |
| A second passage offered a word-for-word copy of a fact already offered (FIX-R103) | no second passage offers a word-for-word copy of an offered fact |
| A two-passage reading could hold nine facts (QAB-qg-plan-10) | each later passage is left room under the ceiling before the head's list |
| A premise's own *When*, or a *which* or *wo* opening (NEW-qg-plan-3) | a question opening on a premise is typed |
| An amount written with spaces (NEW-release-1) | an amount grouped by spaces is one figure |
| An ordinal written as a word on one side (QAB-qg-check-6) | the ordinal tables of the language make *the third reminder* |
| The pronoun *one* made a second number (VAR-number-readings-1) | one predicate, `is_number`, decides what a number is for all three |
| A count of the items one cited fact lists (FIX-R127) | a count is stored as a factoid only |
| A German keyword query typed in lower case lost every (BL-B2) | a text that writes no capital after its first word says nothing |
| An answerable question with no explanation passed (FIX-R105) | an answerable question written without one is refused `explanation_unusable` |
| With three cited passages the check kept only the passages owning a part (FIX-R169) | a question citing three or more passages keeps |
| A circular reason key, the rule restated as its own reason (BL-B5) | the round trip's read also says whether the passages give a why |
| A question reworded until it asked something the passage does (BL-B12) | the read answers only where the passages answer the question as it is asked |
| The aggregation prompt invited counts of the facts the writer (BL-B3) | the prompt says a count is of the figures or items the facts state |
| Questions about a case study's sample person (BL-B9) | the writer is told that a person or a story in the material illustrates a rule |
| With-premise questions opened on a label naming a setting (BL-B6) | the default with-premise category asks for a premise in |
| A search query was told on a slot that cannot | a search query is not told on a slot that spans two passages |
| A short search query another passage answers differently was accepted | a search query bounded to a few words is read once more against |
| The quality report, the Questions page (NEW-api-frontend-export-2) | the report counts each kind and each `categorization=category` |
| `make diversity BY=kind` printed no factoid and open-ended table (BL-B21) | it prints each kind's shares and leaves out the word-bounds column |
| A control character in any exported text (QA-api-frontend-1) | they are dropped from every cell of every sheet |
| An untitled document was named (QA-api-frontend-2) | both name it by the head of its digest |
| The export read its rows (QA-api-frontend-3) | the API and the command line read all three in one snapshot |
| The configuration guide listed too few refusals of `QUESTIONS_CATEGORIZATIONS` (BL-B22) | the guide lists all nine ways it is refused as the parser checks |
| Test runs from a checkout loaded the checkout's `.env` (BL-B23) | `LITELLM_MODE=PRODUCTION` is set with `setdefault` in `backend/llm/__init__.py` and `tests/conftest.py` |
| The release is sized by its scarcest type | a kind short of its share beyond what `close_enough` allows is capped |
| The release draw overshoots its quotas with follow-up questions | a thread ends at the first turn whose band |
| The release handed back could hold twins the verifier never (FIX-R3) | the draw after the last twin round is read for twins once more |

### Fixed in v0.4.4: parsing and chunking

| Defect | Fix |
|---|---|
| A scanned page carrying one stamped line (NEW-parse-chunk-2) | a page holding no more than `PARSING_OCR_CHAR_THRESHOLD` characters |
| Bidi marks, isolates and C1 controls survived the mend (QAB-preprocessing-10) | every format character is dropped, and a C1 control is read |
| A table label wrapped over three lines lost its last (VAR-parse-text-1) | each tail joins the nearest row still standing |
| A body line opening with the running foot's name (QAB-preprocessing-7) | a paragraph is furniture only when it is the running head or foot itself |
| A lone integer anywhere on a page was dropped as a page number (VAR-chunk-structure-1) | a lone integer is a page number only in the top or bottom |
| A sentence cut at a page or column break before a capitalised word (FIX-R101) | a rest opening in capitals joins too |
| Text above a mid-page chapter opening was filed under the new chapter (NEW-parse-chunk-3) | headings and running-head fields are compared on their letters |
| A lead-in that a page join leaves at the end (FIX-R100) | a list item ending on a colon is a lead-in too: it stays |
| A heading holding ` > ` (`Orders > 50 EUR`) was split in two (QAB-preprocessing-8) | a ` > ` inside a heading is written ` › ` |
| A footnote the converter attaches to a picture (NEW-parse-chunk-4) | a picture's footnotes are written beneath its caption, as a table's are |
| A list in two languages under one heading became one passage (NEW-parse-chunk-5) | list items are read too, so a run of items that changes language |
| A running head or foot parted (QA-parse-chunk-1) | it is split at an en dash |
| A short sub-heading that a chapter's running head holds (QA-parse-chunk-2) | the heading and a field are compared word for word |
| A sentence cut at a page break before a figure (QA-parse-chunk-3) | the cut is joined where the word before it cannot close a clause |
| A bullet with no full stop at a page foot (QA-parse-chunk-4) | only a run of letters all in lower case opens in lower case |
| Tidying took time in the square of a document's pages (QA-parse-chunk-5) | the blocks after a lead-in are found in one walk |
| A ligature (U+FB00 to U+FB06) was stored as written (QA-parse-chunk-6) | ligatures are spelled out as their letters |

### Fixed in v0.4.4: fact validation, extraction and the link pass

| Defect | Fix |
|---|---|
| A sentence ended after an abbreviation that never closes one (QAB-llm-nlp-3) | the table is split in two : `_ABBREVIATIONS` holds those that end no |
| A German fact opening on polite *Sie* was refused `unresolved_reference` (NEW-extract-nlp-1) | the fact check passes the cited passages to the reading |
| A fact pointing outside through a modifier of its opening noun (VAR-bridge-prompt8-1) | two tables of the fact side's own |
| A German *dies* after a free relative clause | a finite verb standing as its head's subject or object |
| A pass of `make extract-bridge` narrowed (NEW-extract-nlp-3) | a bridge's reading in `facts.bridge` records the passage that headed its link (`head`) |
| A hold on pairs the link pass would not offer (FIX-R168) | the pass deals and strides as if nothing were held |
| The bridge check missed a passage's numbered heading named second in a list (NEW-extract-nlp-2) | one reader, `numbered` in `validation.py`, serves both |
| A single-quoted heading ending in a possessive (VAR-link-references-1) | a single-quoted span is read on to a later closing mark on its line |
| A figure ending a German sentence (QA-extraction-1) | a figure on its line after a word or an abbreviation finishes its sentence |
| An abbreviation the tables list still ended a sentence after (QA-extraction-2) | a word's leading marks are stripped before the tables are read |
| A price abbreviation ended a sentence before a lower-case word (QA-extraction-3) | `p.a.` and `mon.` are closing abbreviations |
| A German fact opening on a pointing modifier the lemmatizer leaves inflected (QA-extraction-5) | the tables are read with the language's adjective endings stripped as well |
| A fact opening on a back-pointing modifier no table held (QA-extraction-6) | the three join the table |
| A section number with its subsection glued on (QA-extraction-8) | a token opening on a section number before a bracket names that section |

### Fixed in v0.4.4: topics

| Defect | Fix |
|---|---|
| Two identical passages could get different topic memberships (QAB-topics-3) | the fit reseeds the projection for each passage |
| A language with one passage (NEW-topics-2) | a language whose passages are one text |
| A topic dominant in no passage was sent (QAB-topics-4) | a topic is named only where it is some passage's strongest |
| The naming model's "no subject" answer was recognised only as the words *Mixed* (NEW-topics-3) | the answer carries a `no_subject` field the model sets, in any language |
| The ending most topic names share was stripped even (NEW-topics-1) | an ending is taken off only |
| Topic figures and models were keyed (NEW-topics-5) | both are stored under `topics/<database>/<language>`, the database read from the path of `DATABASE_URL` |
| A refit after a language's last document went left that language's figure (QAB-topics-5) | the languages whose topics a refit deletes are read before it |
| A word holding a closing script tag (QA-security-1) | the page writes the data with `<` |
| With `TOPIC_PASSAGES_PER_TOPIC` at 0, a language whose few passages (NEW-topics-2) | with the sizing off, a language with fewer distinct passages than `TOPIC_NUM_TOPICS` |

### Fixed in v0.4.4: the archive, the database and operations

| Defect | Fix |
|---|---|
| Three column comments misdescribed their columns: `questions.categories` named no compound (BL-B20) | one comment-only revision, `20e31b1656f7` on `626a5b07ae34` |
| `make dev` waited for Postgres forever and in silence (FIX-R71) | it waits at most 60 seconds |
| `make questions-export OUT=`, `make diversity FILE=` (QA-security-5) | they quote it |
| `cannot_run`'s docstring said the command line (BL-C3) | it says so, and that the command line relies on the queue's preflight |
| The written-count gate's blind spot (FIX-R41) | it is an open entry of its own |

### Fixed in v0.4.5: API and settings

| Defect | Fix |
|---|---|
| A setting, a topic label or an upload's filename holding a NUL (QAB-api-settings-1) | each is refused at the edge: `out_of_range` for a setting |
| `EMBEDDING_MAX_TOKENS` took 1, which cuts every passage to nothing (QAB-api-settings-5) | the floor is 64 |
| Stop asked Dagster for one page of runs (QAB-api-settings-7) | Stop asks for every unfinished run |
| `GET /pipeline/runs` took a limit with no bound (QAB-api-settings-8) | it takes `limit`, and a refusal answers `orchestrator_refused` |
| The arrivals sensor retried a failed run on every tick (QAB-api-settings-9) | it retries once, then skips and names `make pipeline` and the Run button |
| Reviewing questions read their facts one query per row (FIX-R77) | they are loaded with the questions, 13 queries down to at most 3 |
| The orchestrator took `nan`, negative (QA-security-4) | its reader takes finite values of at least one second |

### Fixed in v0.4.5: frontend and review

| Defect | Fix |
|---|---|
| A search longer than the 200 characters the listing routes (QAB-frontend-review-10) | every listing's search box holds at most `SEARCH_MAX` |
| The Topics search showed a topic's terms joined (QA-api-frontend-4) | the search looks in the terms joined as the table shows them |
| A document's filename went into its panel heading as HTML (QAB-frontend-review-12) | both escape it |
| A filename was read as Markdown in the Delete question (NEW-api-frontend-export-1) | `page.plain` puts a backslash before every ASCII punctuation mark |
| The *How this was produced* fold drew each artefact's own text as Markdown (QAB-frontend-review-11) | the artefact's text and the stage's reason go through `page.plain` |
| Accept or Reject pressed for a question that had left the listing was dropped | the caption names the row, *Row 8036 is not in this list any* |
| A compound slot written single for want of a second (VAR-review-kind-2) | the prompt fold of a question stored single on a spanning slot says |
| A second fact push before a pull offered the facts (QAB-frontend-review-14) | the fact push leaves them out too |
| The facts review dataset carried no language (QAB-frontend-review-15) | a fact record carries the language of the passage at its own citation |

### Fixed in v0.4.5: the stack and tests

| Defect | Fix |
|---|---|
| A fresh clone switched to a hosted model still sent (QA-move-2) | the address is dropped when the model is hosted |
| A second checkout's images overwrote or reused the first's (QA-move-5) | image names follow the compose project |
| `seaweedfs-ui` was a service nothing needed (FIX-R68) | the service, its Caddyfile and its catalogue row are deleted |

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
| A bridge pass narrowed by `TOPIC` | it clears only the bridges opening on a passage of the scoped topics |
| A narrowed pass or a second `MISSING=1` run wrote | the pass never offers a pair a stored bridge rests on |
| Compound questions were rejected by reviewers for asking two things | the record's metadata carries the kind |

### Fixed in v0.3.29: references

| Defect | Fix |
|---|---|
| A German polite Sie addressing the reader was read | a language-keyed table `_POLITE` |
| A pronoun after an exceptive clause that points back | the verb heading the exceptive clause is marked |
| A German `dies` standing for an earlier clause | the earlier finite verb is asked the same "heads a clause |

### Fixed in v0.3.30: bridges in samples

| Defect | Fix |
|---|---|
| A compound question could rest on a bridge's own related | a compound sample prefers a passage's own claims |
| An unanswerable slot was dealt a bridge and perturbed it | an unanswerable slot is dealt only facts resting on one passage |
| A compound slot's second passage could hold only bridges | the partner is chosen among passages with an unspent non-bridge fact |

### Fixed in v0.3.31: table rows and soft hyphens

| Defect | Fix |
|---|---|
| A soft hyphen in a PDF text layer deleted every | one directly before a lower-case letter is dropped (a soft hyphen inside a word) |
| A group row of a table was glued | a label alone on a row joins the row below only |
| The tail of a wrapped table label was glued | a label-only row opening in lower case or closing a bracket the label |

### Fixed in v0.3.32: table footnotes and lead-ins

| Defect | Fix |
|---|---|
| A footnote the converter attached to a table | the footnote is written beneath the table in its passage |
| A lead-in scoping a long table reached only its first | a table is read as a list is |

### Fixed in v0.3.33: number readings

| Defect | Fix |
|---|---|
| A price of four or more digits with a fraction | the figure pattern has an alternative for a long head with a fraction |
| The same value in another format was refused | one owner of the figure's value reading |
| A count written out past twelve was read as no | cardinals are composed from ISO-keyed `_SPELLING` rows to 99 |
| The English pronoun `one` was read as the count one | a word counts as a number only with a digit |
| A recovery numbering its steps handed the numbers back | `unnamed()` strips the step numbers, the label word read from the ISO-keyed `_STEP_LABEL` |
| A list opened by an adverb hid its new item | a verb with only an adverb before it |

### Fixed in v0.3.34: review and page vocabulary

| Defect | Fix |
|---|---|
| The questions workbook had no kind column | a Kind column (single, needs_both, compound) follows Type on the Questions sheet |
| A follow-up reached Argilla without the turns it follows | the record has an optional `thread` field |
| The Questions page named a compound question's prompt wrongly | a compound question's prompt is named `type (compound)` |

### Fixed in v0.3.35: a needs_both question needs both

| Defect | Fix |
|---|---|
| A needs_both question kept both passages | a new verifier call lists the parts of the answer |
| Build | Padded ones relabelled single |
| v0.3.12, C1 rows | 33/45 |
| v0.3.12, all gold rows | 76/107 by reading, 36/107 (0.34) by citation |
| v0.3.0, C1 rows | 25/30 |
| v0.3.0, all gold rows | 68/97 by reading, 60/97 (0.62) by citation |

### Fixed in v0.3.36: a thread leaves the release whole

| Defect | Fix |
|---|---|
| A released thread lost its root | a trigger `questions_release_thread_whole` (revision `d5b2f8a60c14`) clears `release_id` on every follow-up below a question that leaves `accepted` |

### Fixed in v0.4.0: reading documents, questions, topics and pages

| Defect | Fix |
|---|---|
| A numbered reference was linked to another document's section | a numbered reference resolves in the head's own document or is dropped |
| A quoted heading with a typographic apostrophe was cut | double-quoted spans may hold apostrophes and single marks close only |
| An inflected label word before a number matched nothing | one shared matcher `validation.label_word` also accepts an inflected form |
| Sibling linking was quadratic in pure Python | each head scores its family with one numpy product |
| A link whose partner had no validated fact was dropped | heads and partners without a validated fact are removed before the links |
| A bridge group of three or more strided before it | each head's link is grown before the quota is strided over |
| A passage held two languages | a chunk ends where its prose changes language |
| A running head refiled the text above a chapter's opening | a chapter starts at its own heading where its page holds one |
| A price whose digits equal a page number became | running names and paragraphs must hold a letter to count as a repeat |
| A German dies after a relative clause alone was resolved | a relative verb does not count as the earlier clause `dies` stands for |
| One scanned page inside a digital PDF went missing silently | each page with no text layer |
| A vectorless passage always won as compound partner | one candidate set is ranked on one scale: cosine only |
| Topic names lost their subject | a shared ending is taken off only |
| A small language got no topics | the frequency filter is held to what the language's own passage count allows |
| Redo on the Assessment page wiped every verdict | it answers 409 `assessment_cannot_run` before any verdict is cleared |
| A listing's row pick followed the position, not the row | the pick is kept by row id on all six listings |
| A failed topic-map fetch replaced the whole Topics page | the failure is a caption in the map's place |
| A document or topic filter hid a cross-document question's other | the filter chooses question ids and every source is still counted |
| A drawn question rejected before the write lost the whole | the draw writes only the drawn questions still accepted |
| A re-check overruled a person's accept | a re-check rejects only a question still accepted |
| A fact deleted while the writer ran lost every question | `store()` reads the surviving facts `FOR SHARE` |
| A passage deleted mid-run failed a topic fit or stopped | the fit writes the memberships of passages that still exist |
| A kind, band or language held only | the supply check counts only rows a draw can take |
| The default language weights counted rows the draw never takes | the weights count drawable rows, as the bands do |
| The size scan walked one draw per size | a bucket's supply counts unanswerable rows only up to the ceiling |
| A restored question kept the release of a draw | restore clears `release_id` unless a question live all along holds that release |
| A restore after a refit or re-chunk restored nothing | a row whose parent is absent is left behind and counted per table |

## Found on the v0.3.12 rebuild of 2026-10-19

Every row of the v0.3.12 build was read again under a rubric. The releases
from v0.3.13 on fix what the reading found, one fix to a release.

### Fixed in v0.3.13: dependencies

| Defect | Fix |
|---|---|

### Fixed in v0.3.14: facts

| Defect | Fix |
|---|---|
| A fact the repair call split out of a statement | a fact the repair call wrote does not compete for the cap |

### Fixed in v0.3.15: bridge checks

| Defect | Fix |
|---|---|
| A bridge was checked against its excerpts' text only | the heading trail and title are read as an atomic fact's are |

### Fixed in v0.3.16: bridge pairing and prompt

| Defect | Fix |
|---|---|
| Bridge pairs were each passage's nearest unused neighbour inside | `links.py` pairs passages by the documents' own links: a numbered or quoted heading named |
| The bridge prompt invented a link on every pair it | bridge prompt 6 names the link the pairing found |

### Fixed in v0.3.17: unanswerable questions

| Defect | Fix |
|---|---|
| An unanswerable question was written in any of eight kinds | an unanswerable slot is written only as a factoid |

### Fixed in v0.3.18: dash ranges

| Defect | Fix |
|---|---|
| A range written with a dash was refused | `agrees()` reads a dash range |

### Fixed in v0.3.19: answer_incomplete

| Defect | Fix |
|---|---|
| `answer_incomplete` refused complete list keys | the share test still fires first |

### Fixed in v0.3.20: question kinds

| Defect | Fix |
|---|---|
| A question's kind was implied | every slot the plan deals carries a kind |

### Fixed in v0.3.21: a band follows its kind

| Defect | Fix |
|---|---|
| A question's band followed the spread of its passages whatever | `criteria_of` takes the stored kind |

### Fixed in v0.3.22: compound questions (off by default)

| Defect | Fix |
|---|---|
| No question asked two separate things | a `compound` kind, off by default: the slot is dealt the passage of its topic |

### Fixed in v0.3.23: bridge relations stored and shared

| Defect | Fix |
|---|---|
| A bridge kept neither the relation it named nor | the six relations move into one table |

### Fixed in v0.3.24: answer-check readings

| Defect | Fix |
|---|---|
| A numbered list's markers counted as figures in `answer_incomplete` | `unnamed()` strips a numbered or bulleted list's marker at the start of each |
| A range's unit was not matched | the unit after a dash range must come back |

### Fixed in v0.3.25: reverify keeps the kind

| Defect | Fix |
|---|---|
| A stored compound question was refused when reverified | the re-check holds a stored question to the kind it was written as |

### Fixed in v0.3.26: compound questions dealt by default

| Defect | Fix |
|---|---|
| Compound questions were built but never dealt | the kind mix defaults to `needs_both:5,compound:1` |

### Fixed in v0.3.27: the release size

| Defect | Fix |
|---|---|
| The release draw bisected for a size that fills | the draw scans sizes down from the largest the pool's supply allows |

## Found on the v0.4.0 rebuild of 2026-10-18

The v0.3.8 code rebuilt the same two PDFs. The review found fewer welds fixed
and looser topics in the v0.4.0 build; the fixes below were measured on the
labelled rows of both builds.

### Fixed in v0.3.9: two-passage questions

| Defect | Fix |
|---|---|
| A bridge fact was offered beside an unrelated claim | a bridge is offered alone, whichever passage it was dealt from |
| The bridge prompt taught side-by-side claims | the right example is a claim one excerpt changes |

### Fixed in v0.3.10: facts

| Defect | Fix |
|---|---|
| A condition the parser hung as a conjunct counted | a conjunct opened by its own subordinator |

### Fixed in v0.3.11: topics

| Defect | Fix |
|---|---|
| One seeded topic fit was kept unread | the fit draws eight factorisations seeded from `TOPIC_RANDOM_STATE` on |

### Fixed in v0.3.12: unanswerable questions

| Defect | Fix |
|---|---|
| The settles reading quoted the answering words | verifier prompt 6: a role that does not say the question was written to have no answer |

## Found on the v0.3.0 rebuild of 2026-10-16

The v0.3.0 rebuild was reviewed in full: 871 accepted questions (70% usable),
343 released (76% on the first reading, 79% once disagreements were settled;
10 invalid), welds at 18% of two-passage questions. Each finding is fixed,
deferred or ranked low.

### Fixed in v0.3.1: model calls, settings and commands

| Defect | Fix |
|---|---|
| Hidden re-asks inside each attempt | instructor asked for none |
| A rate limit's `Retry-After` ignored | read through the cause chain, at most two minutes |
| A filtered answer failed its topic | a refusal after one call |
| Failed calls never costed | every attempt summed onto both lines |
| Ollama-only options sent to hosted models | sent only to the provider they belong to |
| A recommended mode stopped every stage | the 8 it takes, others refused at start-up |
| A recalibration rewrote stored scores | both kept |
| A copied `backend.env` stalled the question worker | absent reads 0.02 |
| An old API build went unnoticed | `make doctor` names the settings the API lacks |
| `make test` failed in one run | the recorder stubbed |
| Make targets that misbehaved | each fixed |

### Fixed in v0.3.2: reading text and numbers

| Defect | Fix |
|---|---|
| An abbreviation before a figure ended a sentence | an abbreviation is followed by a figure |
| Two rules each ending in a full stop read | a free dash or slash after a full stop |
| `provided` read as an exception | a finite `provided` is read as the verb it is |
| Times and glued figures carried no number | read into their own claim field |
| A German decimal read as an integer | a per-language `DECIMAL_MARK` |
| An aggregation key accepted unasked | the verifier is asked for every aggregation |
| A relabelled aggregation kept its old level | the relabel takes the new kind's level |
| Figures-only paragraphs dropped | only a page number's shape is dropped |
| A hyphenated word broken across a table cell | the mend runs after them too, with a per-language table of completing words |

### Fixed in v0.3.3: the unit of a fact

| Defect | Fix |
|---|---|
| A statement the tagger mis-rooted counted as two claims | the root is read past a subordinator |
| A verb the tagger gave a finite fine tag | the fine tag is read too |
| A fact copying one sentence was judged on the sentence | judged on the claims it reads as now |
| A verbatim repeat inside one passage kept twice | refused as a duplicate of the passage's own fact |
| Refusal messages misstated the dedup bar, and over-cap twice | worded as set |
| A "the model proposed nothing" warning where no model ran | fires only where a model read the passage |
| A figure table or priced list skipped as an identifier | a figure in a cell is read as the value it is |
| A fact citing no sentence dropped | stored as `evidence_absent` |

### Fixed in v0.3.4: round trip, reasons and typing

| Defect | Fix |
|---|---|
| The entailment rescue overrode a verifier that found nothing | no rescue after that reading |
| The round trip asked for what only the writer | given, unless the recovery says more than key and question |
| A German adjective tagged as an adverb did not come | a lemma comes back under an adjective or adverb, never negated |
| A set of kinds written as adjectives refused as one | a coordination with no noun phrase is a set |
| German *wo-* question words missed by `compound` | a per-language table of question adverbs |

### Fixed in v0.3.5: release record and unanswerables

| Defect | Fix |
|---|---|
| The release draw left no record | a trace with one span per twin round |
| A correct answer silenced because its quote was stitched | the quote is looked for piece |
| A quote matched inside a longer word | pieces match on word boundaries |

### Fixed in v0.3.6: parsing and chunking

| Defect | Fix |
|---|---|
| A re-chunk deleted every passage | a passage whose text, section path |
| Hidden labels survived into passages and headings | a character counts as shown only |
| A continued table stopped at a row the converter flagged | the row joins as data when it is set in the first table's data type |
| List depth lost at column and page breaks | depth measured from each column's own edge |
| A lone conjunction promoted to a heading | read as text between two items or paragraphs of one passage |
| A joined block or table cited only its first page | it cites every page it spans |
| `third- party` mended to `thirdparty` | a hyphen is kept where the document prints the compound with it elsewhere |

### Fixed in v0.3.7: topics and the scope of a fact

| Defect | Fix |
|---|---|
| A topic's name carried onto the wrong topic | a person's decision moves only to the topic holding most of the same passages |
| A fit reported itself stale the moment it was made | one shared rule for both |
| Smaller topic bookkeeping | each fixed, a dropped decision of a vanished language logged and counted |
| Facts dropped the scope a heading or a list's lead-in | atomic prompt 12 names the heading trail as the situation a rule holds in |

### Fixed in v0.3.8: security, the frontend, orchestration and the docs

| Defect | Fix |
|---|---|
| Settings accepted values no service could run with | refused when written  |
| The workbook export wrote formulas | written as text |
| Stop stopped only the newest run | every queued or started run is stopped |
| A run whose worker died blocked the queue | Dagster's run monitoring is on, and a cancelling run counts as going |
| A topic `PATCH` reset what its body left out | it changes only what it names |
| A failed worker rebuild asked the model again every five | it backs off, per version |
| The review sample drew questions already reviewed | only unreviewed ones |
| Annotations stopped for good after one failed flush | they resume |
| A span named the worker's process run | every span of a row names the run that queued it |
| `make eval-score` scored a reader production does not run | it scores the production reader |
| Deleting every document forgot the upload history first | it forgets uploads last |
| The configuration panel wrote stale values | it sends what it drew, redraws after a change |
| Smaller frontend faults | each fixed |
| The stack trusted any host name and any missing secret | Streamlit answers only `localhost` and `127.0.0.1`, the only names it is published on |

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

### After the fixes

The v0.3.0 rebuild's counts (2026-10-16; the weld rate and wrong duplicate
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
