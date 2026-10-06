# Measurements

Every number on this page describes one state of one pipeline run. The
corpus, parsing, chunking, topic and evaluation figures, the wall clock and
the spend are from the run of **2026-09-26**. The fact verdicts, the
accepted pool and the release are that run's output as it stands on
**2026-10-06**: the same 16 documents and the same 5,873 written questions,
re-verified under fixed gates with two targeted fact repairs applied. It is
not a fresh extraction, and no model was called for any of it.

The two repairs:

- 100 validated facts that open on a demonstrative pointing at prose they do
  not carry were judged again and refused as `unresolved_reference`.
- 117 validated facts whose evidence sits verbatim in more than one syllabus
  gained 214 citations, so each now cites every document that holds it.

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

`azure/gpt-4.1` over a sample of 200 facts, 200 questions and all 76 topics.
It records an opinion and changes no verdict.

The sample was drawn newest-first by id, not stratified: facts 11,955–12,154
and questions 5,597–5,873 — the last-written German slice. These figures
describe that slice, not the corpus as a whole.

| Artefact | Judged | Approved | Refused |
|---|---|---|---|
| `fact` | 200 | 186 | 14 |
| `question` | 200 | 144 | 56 |
| `topic` | 76 | 56 | 20 |

| Metric | Judgements | Mean score | Approved |
|---|---|---|---|
| `toxicity` | 400 | 0.000 | 400 |
| `conciseness` | 200 | 1.000 | 200 |
| `refusal` | 200 | 0.040 | 192 |
| `relevance` | 476 | 0.935 | 445 |
| `qa_correctness` | 200 | 0.870 | 174 |
| `hallucination` | 400 | 0.105 | 358 |
| `summarization` | 76 | 0.803 | 61 |

`hallucination` is scored to minimise: 0.0 is the good label.

### Where the judge and the checker disagree

Facts:

| | Judge approved | Judge refused |
|---|---|---|
| Validated | 100 | 3 |
| Refused | 86 | 11 |

Questions:

| | Judge approved | Judge refused |
|---|---|---|
| Accepted | 60 | 15 |
| Rejected | 84 | 41 |

The judge approves 86 of the 97 facts the checker refused and 84 of the 125
questions the gates rejected. The two do not measure the same thing: the
checker asks whether a citation resolves and a gate holds, the judge whether
an artefact reads as sound. The disagreeing pairs are the queue for a person.

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

```bash
make corpus                       # every stage in order
make questions-balance            # draw the release
make assess-start && make assess  # the evaluation phase
make pipeline-status              # the counts
make spend LOG=run.log            # the calls and the cost
```

Per-stage wall clock comes from the run's log files in `./logs`, and the
counts from the tables. Nothing on this page is computed anywhere else.
