# Measurements

Every number on this page describes one state of one pipeline run. The
corpus, parsing, chunking and topic figures, the topic judgements, the wall
clock and the spend are from the run of **2026-09-26**. The facts and
questions under *The evaluation phase* were judged on **2026-10-06** in a
stratified run of their own. The fact verdicts, the
accepted pool and the release are that run's output as it stands on
**2026-10-06**: the same 16 documents and the same 5,873 written questions,
re-verified under fixed gates with two targeted fact repairs applied. It is
not a fresh extraction, and no model was called for any of it. The run of
2026-09-26 ran every stage on the host and predates the rule that keeps
host parse, chunk and extract runs off the dataset.

The two repairs:

- 100 validated facts that open on a demonstrative pointing at prose they do
  not carry were judged again and refused as `unresolved_reference`.
- 117 validated facts whose evidence sits verbatim in more than one syllabus
  gained 214 citations, so each now cites every document that holds it.

Everything up to [The v0.3.0 rebuild](#the-v030-rebuild-of-2026-10-16)
describes that run. The rebuild is a second run, of a second corpus, and its
figures stand on their own.

This is the only place in the repository that holds run figures. A README
that needs one links here.

## The run

| | |
|---|---|
| Corpus | 16 PDF certification syllabi, German and English |
| Extractor, topic labeller, question writer | `azure/gpt-5.4` |
| Verifier and judge | `azure/gpt-4.1` |
| Wall clock | 7 h 31 min |
| Model calls | 20,218 |
| Tokens | 30,366,704 in, 1,471,085 out |
| Cost | USD 56.63 |

| Stage | Wall clock | Calls | Cost (USD) |
|---|---|---|---|
| Parsing | 5.6 min | — | — |
| Chunking | 1.2 min | — | — |
| Extraction | 116.2 min | 3,380 | 13.62 |
| Topic modelling | 1.6 min | 74 | 0.21 |
| Question generation | 296.5 min | 14,812 | 40.01 |
| Evaluation phase | 25.5 min | 1,952 | 2.79 |

Question generation is 66% of the wall clock and 71% of the spend.

## Corpus

| | German | English | Total |
|---|---|---|---|
| Documents | 8 | 8 | 16 |
| Pages | 645 | 582 | 1,227 |
| Characters | 1,648,644 | 1,527,068 | 3,175,712 |

All 16 parsed and chunked. None exceeded `MAX_FILE_SIZE_MB`.

## Parsing

| | |
|---|---|
| Mean confidence | 0.944 |
| Lower bound, across documents | 0.852 – 0.920 |

## Chunking

3,080 passages — 192.5 per document, from 92 to 294. Mean length 1,267
characters in German and 1,250 in English.

| Passage language | Count |
|---|---|
| German | 1,499 |
| English | 1,581 |

54 passages sit in a document of the other language: 50 English passages in
German documents, 4 the other way.

| Block type | Passages |
|---|---|
| `text` | 2,022 |
| `list_item` | 570 |
| `table` | 329 |
| `document_index` | 154 |
| `caption` | 3 |
| `section_header` | 1 |
| `footnote` | 1 |

## Extraction

12,154 statements written, **8,956 validated — 73.7%**.

| Kind | Written | Validated |
|---|---|---|
| `atomic` | 9,846 | 7,325 |
| `summary` | 1,154 | 1,037 |
| `outline` | 1,154 | 594 |

| Refused as | Count | Share of refusals |
|---|---|---|
| `duplicate` | 2,292 | 71.7% |
| `unsupported_addition` | 491 | 15.4% |
| `unresolved_reference` | 232 | 7.3% |
| `asserts_nothing` | 107 | 3.3% |
| `not_atomic` | 61 | 1.9% |
| `copied` | 8 | 0.3% |
| `not_condensed` | 7 | 0.2% |

2,240 of 3,080 passages carry a validated fact — 4.09 each on average, median
4, most 45.

| Block type | Passages | Carrying a validated fact |
|---|---|---|
| `text` | 2,022 | 1,673 |
| `list_item` | 570 | 365 |
| `table` | 329 | 199 |
| `document_index` | 154 | 0 |

`document_index` yields nothing: a contents page states no claim a citation
can rest on.

## Topic modelling

76 topics — 37 German, 39 English.

| | German | English |
|---|---|---|
| Vocabulary after filtering | 2,870 terms | 2,445 terms |
| Passages in no topic | 10 | 2 |
| Largest topic, share of its language | 6.6% | 5.9% |

Topics hold 10 to 99 dominant passages, 40.4 on average. 9 of the 76 went
unlabelled, below `TOPIC_LABEL_MIN_FACT_SHARE`.

## Question generation

5,873 questions written, **2,064 accepted — 35.1%**. 4,186 candidates were
first attempts and 1,687 were retries. Re-verification rejected 352 of the
questions the run had accepted.

| Gate | Refused | Share of written |
|---|---|---|
| `compound` | 881 | 15.0% |
| `not_recoverable` | 520 | 8.9% |
| `answerable_after_all` | 504 | 8.6% |
| `wrong_type` | 304 | 5.2% |
| `answerable_elsewhere` | 264 | 4.5% |
| `asks_nothing_new` | 231 | 3.9% |
| `answer_incomplete` | 200 | 3.4% |
| `restates_question` | 153 | 2.6% |
| `explanation_unusable` | 135 | 2.3% |
| `duplicate` | 131 | 2.2% |
| `leaks_source` | 120 | 2.0% |
| `off_thread` | 76 | 1.3% |
| `unanchored` | 71 | 1.2% |
| `off_topic` | 69 | 1.2% |
| `wrong_form` | 49 | 0.8% |
| `source_changed` | 41 | 0.7% |
| `answer_too_long` | 31 | 0.5% |
| `malformed` | 17 | 0.3% |
| `answer_too_short` | 12 | 0.2% |

How far each gate was reached:

| Gate group | Questions reaching it |
|---|---|
| `structural` | 5,873 |
| `kind_and_thread` | 4,823 |
| `near_duplicate` | 4,193 |
| `phrasing` | 4,055 |
| `round_trip` | 3,866 |
| `off_topic` | 1,349 |

### What was accepted

| Kind | Accepted | Share |
|---|---|---|
| `reason` | 355 | 17.2% |
| `condition` | 312 | 15.1% |
| `factoid` | 289 | 14.0% |
| `definition` | 249 | 12.1% |
| `application` | 175 | 8.5% |
| `procedure` | 165 | 8.0% |
| `enumeration` | 147 | 7.1% |
| `consequence` | 130 | 6.3% |
| `implication` | 117 | 5.7% |
| `aggregation` | 91 | 4.4% |
| `comparison` | 34 | 1.6% |

`entity` and `temporal` carry a weight of 0 and were not written.

| | | |
|---|---|---|
| Language | German 1,116 | English 948 |
| Answerable | 1,605 — 77.8% | Unanswerable 459 — 22.2% |
| Passage scope | `single_passage` 1,308 | `multi_passage` 756 |
| Document scope | `single_document` 1,447 | `cross_document` 617 |
| Topic scope | `single_topic` 1,710 | `multi_topic` 354 |

| Difficulty | Accepted | Share |
|---|---|---|
| `easy` | 1,111 | 53.8% |
| `hard` | 529 | 25.6% |
| `medium` | 424 | 20.5% |

| Cognitive level | Accepted |
|---|---|
| `analyse` | 727 |
| `apply` | 652 |
| `understand` | 396 |
| `recall` | 289 |

An accepted question cites 1.49 facts on average, at most 3.

### Answer length

| Form | Accepted | Median | Mean | Range |
|---|---|---|---|---|
| `explanation` | 958 | 127 | 141 | 25 – 594 |
| `value` | 344 | 29.5 | 33 | 1 – 80 |
| `list` | 303 | 100 | 109 | 9 – 291 |

### Follow-up threads

| Position | Written | Accepted |
|---|---|---|
| 1 — root | 4,879 | 1,773 |
| 2 | 717 | 218 |
| 3 | 277 | 73 |

Acceptance falls from 36.3% at the root to 30.4% and 26.4%.

## The balanced release

1,015 questions drawn from the 2,064 accepted — a 49.2% yield.

| Held at | Result |
|---|---|
| Kind | `condition`, `reason` 101; `application`, `definition`, `factoid`, `implication`, `procedure` 100; `consequence`, `enumeration` 99; `aggregation` 91; `comparison` 24 |
| Difficulty | `easy` 345, `medium` 325, `hard` 345 — 34.0 / 32.0 / 34.0% |
| Unanswerable | 103 — the ceiling of 10% of the 1,035 places the draw aimed at |

The draw aimed at 1,035 places and filled 1,015. Two quotas could not fill
from the pool. `aggregation`: all 91 accepted were drawn, 10 short of its
quota of 101. `medium`: 20 short of 345. Every medium root was drawn, and the
99 medium questions left over are follow-ups, which the draw takes only with
their root.

`comparison` is at its weighted target, not short of supply.
`QUESTIONS_RELEASE_TYPES` weighs it 1 against 4 for every other kind, so its
quota is 25; the release drew 24 of the 34 accepted, within `TOLERANCE`.

The accepted pool was 53.8% easy and 22.2% unanswerable; the release is
evenly banded and holds the unanswerable ceiling exactly. Re-verification shrank the
comparison pool from 188 to 34, and the release weight keeps that kind at a
quarter of the others' share.

## Coverage

| | |
|---|---|
| Passages | 3,080 |
| Passages a validated fact rests on | 2,240 — 72.7% |
| Passages an accepted question rests on | 1,463 — 65.3% of askable, 47.5% of all |
| Validated facts | 8,956 |
| Facts an accepted question cites | 2,842 — 31.7% |
| Questions per passage asked about | 1.41 |
| Questions per fact cited | 0.73 |
| Accepted questions per topic | 31.8 mean, 0 – 84 |

The 840 passages carrying no validated fact are ones the extractor skipped or
whose every statement a check refused.

## Confidence

How close a row came to the verdict that would have refused it.

| | Rows | Mean | Range |
|---|---|---|---|
| Validated facts | 8,955 | 0.190 | 0.000 – 0.915 |
| Accepted questions | 2,064 | 0.228 | 0.000 – 1.000 |

## The evaluation phase

`azure/gpt-4.1` judges a sample of facts and questions, and every topic. It
records an opinion and changes no verdict.

The facts and questions are one stratified run, identified in the database
as `assessments.run_id = 'assess-stratified-2026-10-06'`. 200 of each kind
were drawn with `ASSESSMENT_STRATIFY` set: questions spread evenly over
language and question type, facts over language, in random order within
each band. 8 of the 400 drawn had been judged before and were skipped, so
the run enrolled 198 facts and 194 questions.

1 verdict is left out. The network dropped during the run, and that row
was stored on fewer metrics than its kind is due. Every figure below counts
only the rows whose metrics are complete: the run's rows where the
`assessment_metrics` count reaches `metrics_due`.

| | German | English | Total |
|---|---|---|---|
| Facts | 100 | 98 | 198 |
| Questions | 92 | 101 | 193 |

The questions hold 17 to 19 of each of the 11 kinds. The facts are 140
validated and 58 refused; the questions 85 accepted and 108 rejected.

The 76 topics were judged in the run of 2026-09-26, all of them, so the
stratified run had none to add.

| Artefact | Judged | Approved | Refused |
|---|---|---|---|
| `fact` | 198 | 180 | 18 |
| `question` | 193 | 141 | 52 |
| `topic` | 76 | 56 | 20 |

| Metric | Judgements | Mean score | Approved |
|---|---|---|---|
| `toxicity` | 391 | 0.000 | 391 |
| `relevance` | 391 | 0.967 | 378 |
| `hallucination` | 391 | 0.100 | 352 |
| `conciseness` | 193 | 0.964 | 186 |
| `qa_correctness` | 193 | 0.834 | 161 |
| `refusal` | 193 | 0.041 | 185 |
| `relevance`, topics | 76 | 0.829 | 63 |
| `summarization`, topics | 76 | 0.803 | 61 |

`hallucination` is scored to minimise: 0.0 is the good label.

### Where the judge and the checker disagree

Facts:

| | Judge approved | Judge refused |
|---|---|---|
| Validated | 132 | 8 |
| Refused | 48 | 10 |

Questions:

| | Judge approved | Judge refused |
|---|---|---|
| Accepted | 57 | 28 |
| Rejected | 84 | 24 |

Questions by language:

| | Accepted, judge approved | Rejected, judge approved |
|---|---|---|
| German | 35 of 51 | 34 of 41 |
| English | 22 of 34 | 50 of 67 |

Judge approval of what the pipeline kept against what it refused, by a
two-proportion z-test, with Fisher's exact test beside it for the small
cells:

| | Kept | Refused | p, z-test | p, Fisher |
|---|---|---|---|---|
| Questions | 57 of 85 — 67% | 84 of 108 — 78% | 0.096 | 0.105 |
| Questions, German | 35 of 51 — 69% | 34 of 41 — 83% | 0.115 | 0.148 |
| Questions, English | 22 of 34 — 65% | 50 of 67 — 75% | 0.298 | 0.354 |
| Facts | 132 of 140 — 94% | 48 of 58 — 83% | 0.010 | 0.015 |
| Facts, German | 66 of 70 — 94% | 25 of 30 — 83% | 0.079 | 0.123 |
| Facts, English | 66 of 70 — 94% | 23 of 28 — 82% | 0.060 | 0.114 |

At this sample size the judge does not distinguish accepted from rejected
questions: the difference is not significant overall or in either language.
It approves validated facts more often than refused ones across the sample,
and the difference is significant there; within one language the samples
are too small to tell. The two do not measure the same thing: the checker
asks whether a citation resolves and a gate holds, the judge whether an
artefact reads as sound. The disagreeing pairs are the queue for a person.

## Model latency

Per call, over the run:

| Stage | Median | p95 | Slowest |
|---|---|---|---|
| Extraction | 1.6 s | 2.8 s | 10.0 s |
| Topic modelling | 0.8 s | 1.0 s | 1.3 s |
| Question generation | 0.8 s | 2.4 s | 12.6 s |
| Evaluation phase | 0.7 s | 1.0 s | 2.2 s |

`LLM_TIMEOUT_SECONDS` is sized against the slowest column. A locally served model of the same size is one to two orders
slower per call, and the wall clock above is the figure that moves.

## Test coverage

Not a run figure. `make test-coverage` re-measures.

| Package | Statements covered |
|---|---|
| `backend/topic_modelling` | 99% |
| `backend/extraction` | 99% |
| `backend/ingestion` | 99% |

## Reproducing this page

This run cannot be reproduced under today's rules. It ran every stage on the
host against hosted models. Today the container workers build the dataset,
their shared model is an Ollama model, each host drain refuses while its
stage's worker container runs, and host parse, chunk and extract runs are
kept off the dataset. No run those rules allow repeats the run above.

What can still be read again is what the run left in the tables. The
evaluation phase ran as `assess-stratified-2026-10-06`, and its figures count
only complete verdicts:

```sql
SELECT a.* FROM assessments a
WHERE a.run_id = 'assess-stratified-2026-10-06'
  AND (SELECT count(*) FROM assessment_metrics m WHERE m.assessment_id = a.id)
      >= a.metrics_due;
```

Per-stage wall clock comes from the run's log files in `./logs`, and the
counts from the tables. Nothing on this page is computed anywhere else.

## The v0.3.0 rebuild of 2026-10-16

The IFAB *Laws of the Game 2026/27*, one PDF in German and its English
translation, taken through every stage by v0.3.0 on **2026-10-16**. Nobody
read its output by hand; [bugs.md](bugs.md#after-the-fixes) sets its figures
beside the v0.2.2 rebuild of the same two PDFs, which was read in full.

| | |
|---|---|
| Corpus | 2 PDFs: German, 139 pages; English, 131 pages |
| Question writer | `azure/gpt-5.4` |
| Extractor, digest, topic labeller, verifier, phrasing judge | `azure/gpt-4.1` |
| Wall clock | 2 h 26 min |
| Model calls | 5,846 |
| Cost | USD 17.93 |

| Stage | Wall clock | Calls | Cost (USD) |
|---|---|---|---|
| Parsing | 1.3 min | — | — |
| Chunking | 0.6 min | — | — |
| Extraction | 32.1 min | 899 | 2.70 |
| Topic modelling | 0.4 min | 2 | 0.01 |
| Bridge facts | 5.3 min | 204 | 0.44 |
| Question generation | 99.9 min | 4,347 | 14.27 |
| Release | 5.9 min | 394 | 0.50 |

Question generation is 69% of the wall clock and 80% of the spend. The
table leaves out two runs the rebuild threw away: a first extraction, redone
after the fact-dedup guard measured on it was reverted (USD 2.82), and a
first release draw, redone at a lower `aggregation` weight (USD 0.18). With
them the rebuild cost USD 20.93.

### Passages, facts and topics

| | German | English |
|---|---|---|
| Passages | 417 | 403 |
| Passages carrying a validated fact | 361 | 339 |
| Facts, bridges aside | 1,961 | 1,758 |
| Validated | 1,692 | 1,488 |
| Refused `not_atomic`, per 1,000 facts | 32.1 | 61.4 |
| Refused `unresolved_reference`, per 1,000 | 30.1 | 21.0 |
| Refused `unsupported_addition`, per 1,000 | 9.2 | 18.2 |
| Refused `duplicate`, per 1,000 | 57.1 | 46.6 |
| Bridge facts written, validated | 134, 106 | 115, 73 |
| Topics | 9 | 8 |

Each topic fit reads only the passages that carry a validated fact, and
every one of them is in a topic. The 120 passages carrying none are in no
topic.

### Questions

| | German | English |
|---|---|---|
| Written | 780 | 727 |
| Accepted | 463 (59%) | 408 (56%) |
| Accepted with no answer in the material | 133 | 114 |
| Accepted citing two or more passages | 102 (22%) | 81 (20%) |

The most common refusals, German and English: `asks_nothing_new` 59 and 55,
`not_recoverable` 54 and 51, `answerable_elsewhere` 31 and 43,
`answer_incomplete` 27 and 34, `wrong_type` 37 and 29,
`answerable_after_all` 25 and 31.

The writer declined 36 slots and 10 follow-up turns whose facts could not
answer the kind asked for. 9 questions written to have no answer, which the
material turned out to answer, were written again as answerable ones. The
provider refused no prompt, and no topic failed.

### The release

343 questions drawn from the 871 accepted — a 39% yield.

| Held at | Result |
|---|---|
| Language | German 182, English 161 |
| Difficulty | `easy` 226, `medium` 94, `hard` 23: the answerable pool's own split |
| Kind | `condition` 57; `application`, `definition`, `factoid`, `reason` 34; `consequence`, `enumeration`, `implication`, `procedure` 33; `aggregation`, `comparison` 9 |
| Unanswerable | 0, as `QUESTIONS_RELEASE_UNANSWERABLE=0` sets |

Eight kinds came 2 or 3 short of their quota of 36 or 37, because the pool
held no more of them, and `condition`, which the pool held plenty of, took
the places they left. The draw put 12 pairs of released questions to the
verifier as possibly wanting one answer, and released one question of each
pair it said did.

The first draw weighed `aggregation` 4, like most kinds. The pool held only
13 aggregations, and that capped the whole release at 133 questions.
v0.3.0 weighs it 1, as it weighs `comparison`.

The counts are queries over the run's own tables. Wall clock, calls and
spend come from each stage's `make` output, which logs every model call with
its cost.
