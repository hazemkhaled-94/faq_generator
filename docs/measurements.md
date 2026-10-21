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
2026-09-26 ran every stage on the host and predates the rule that the
container workers, not a host drain, build the dataset.

The two repairs:

- 100 validated facts that open on a demonstrative pointing at prose they do
  not carry were judged again and refused as `unresolved_reference`.
- 117 validated facts whose evidence sits verbatim in more than one syllabus
  gained 214 citations, so each now cites every document that holds it.

Everything from [The run](#the-run) up to
[The v0.3.0 rebuild](#the-v030-rebuild-of-2026-10-16) describes that run. The
rebuilds are later runs, of a second corpus, and their figures stand on
their own.

This is the only place in the repository that holds run figures. A README
that needs one links here.

## What a generated benchmark can rank

The figures in this section are not this project's: they come from two
studies of generated benchmarks. Read them as the limits within which the
project's figures below should be read. The first study is van Elburg, van
der Putten and Marx, [*Can We Evaluate RAGs with Synthetic
Data?*](https://arxiv.org/abs/2508.11758) (ECML PKDD 2025 workshops,
Springer CCIS, doi:10.1007/978-3-032-19102-1_11; read as arXiv:2508.11758v2).
It compares a generated benchmark with a human one over four datasets, on
four or five RAG set-ups each, with no significance test. The second is
Rahmani, Craswell, Yilmaz, Mitra and Campos, [*Synthetic Test Collections for
Retrieval Evaluation*](https://arxiv.org/abs/2405.07767) (SIGIR 2024,
doi:10.1145/3626772.3657942). It ranks 31 retrieval runs on 51 real and 31
generated, curated queries.

- **A generated benchmark ranks retrieval set-ups better than generators.**
  With only the retrieval varied, it ranked the set-ups close to the human
  benchmark: mean Kendall's τ 0.84 on BLEU over the four datasets. With five
  generators it failed: mean τ −0.35 on BLEU, and −1.00 on one dataset (van
  Elburg et al., §5.2–5.3, Fig. 2). Use a benchmark from this project to
  compare retrievers, chunking and top-k. Compare generators with care, and
  with real questions beside it.
- **Its questions run easier than real ones.** Every system scored higher
  on the generated questions under every metric (van Elburg et al., §5.2,
  Fig. 3–6). Context Precision stayed high at every k on generated questions
  (Fig. 4), so it could not rank retrievers (τ 0.08 over four systems). In
  Rahmani et al., a fully synthetic collection, with generated queries and
  LLM relevance judgments, overestimated NDCG@10 for every system type. With
  human judgments, the generated queries did not (§2.1, Fig. 1; §3, Fig. 3).
  So part of the effect belongs to the LLM judge, which holds for this
  project's own judge too. Read absolute scores as optimistic, and read
  differences between set-ups.
- **The cited passages are not a full relevance set.** Counting only the
  passage a query was written from as relevant ranked systems poorly
  (τ 0.157). Pooled judgments ranked them well (τ 0.82 with human
  judgments, 0.86 with GPT-4's) (Rahmani et al., §2.1–2.2, Fig. 1–2). A
  retriever that returns another passage stating the same answer is not
  wrong. Score retrieval by whether the answer can be got from what was
  retrieved, not only by whether the cited passage came back.
- **Form matters.** Agreement was best where the generated and the real
  questions matched in length and form (van Elburg et al., §6.1). The
  project's categories exist to widen the form, and `make diversity
  BY=category` shows how far they do.
- **Judge a chatbot with another model family than the one that wrote the
  benchmark, as a precaution.** Van Elburg et al. suggest a stylistic bias
  towards the generating model without testing it (§6.1). Rahmani et al.
  tested one collection and found little to no bias, with hedges (§3,
  Fig. 3).

## Every run at a glance

The IFAB *Laws of the Game 2026/27*, German and English, taken through every
stage by successive versions, each run read in full against the corpus by
review agents working from one rubric (`azure/gpt-5.4` writing questions,
`azure/gpt-4.1` for everything else). The v0.4.0 column is the code of
v0.3.8; it was reviewed and not released. Readers differ by about five
points, so a move smaller than that between two columns is judged by a blind
same-reader test, given where one was run. "Usable" is a reviewer verdict of
good or minor; "settled" means released questions judged unusable were read
again by a second and, where the two disagreed, a third reader. A dash is a
figure that run did not measure. The 2026-10-13 and v0.2.2 runs are detailed
in [bugs.md](bugs.md); the later three each have a section of their own
below. The first run on this page, of 16 syllabi, used another corpus and is
not in the table.

| | 2026-10-13 (before v0.2.2) | v0.2.2, 2026-10-14 | v0.3.0, 2026-10-16 | v0.4.0, 2026-10-18 | v0.3.12, 2026-10-19 |
|---|---|---|---|---|---|
| **Questions** | | | | | |
| Written / accepted | 1,476 / 576 | 1,760 / 837 | 1,507 / 871 | 1,550 / 886 | 1,753 / 960 |
| Accepted usable (German / English) | 50% (51% / 50%) | 57% (54% / 60%) | 69.9% (69.5% / 70.3%) | 75.3% (75.0% / 75.6%) | 76.6% (73.5% / 79.8%) |
| Released (German / English) | 238 (187 / 51) | 321 (176 / 145) | 343 (182 / 161) | 318 (165 / 153) | 395 (205 / 190) |
| Released usable, settled | 49% | 52% | 79.0% | 82.7% | 82.3% |
| Released invalid | 30 | 48 | 10 | 8 | 9 |
| Release German share (pool) | 79% (48%) | 55% (55%) | 53% (53%) | 51.9% (51.8%) | 51.9% (52.0%) |
| Answer keys correct / complete | 58% / 45% | 69% / 58% | 80.1% / 72.0% | 87.0% / 73.2% | 87.8% / 74.0% |
| Two-passage questions welded, accepted (released) | 19% of accepted carry a weld tag | 128/270, 47% (104 released) | 33/183, 18.0% (17/91) | 32/144, 22.2% (19/65) | 40/225, 17.8% (23/95) |
| Usable by band, accepted answerable: easy / medium / hard | 55% / 43% / 43% | 62% / 44% / 47% | 78% / 70% / 68% | 87% / 64% / 53% | 85% / 70% / 70% |
| Accepted unanswerables the corpus answers (German / English) | 76/158, 48% | 141/283, 50% | 107/247, 43.3% (41.4% / 45.6%) | 94/247, 38.1% (38.8% / 37.3%) | 82/241, 34.0% (37.2% / 30.4%) |
| Rejected questions the gate refused wrongly / usable ones lost | 21% / 133 | 21% / 140 | 37.9% / 183 | 33.7% / 168 | 33.4% / 214 |
| **Facts** | | | | | |
| Facts validated (written) | about 1,849 | 3,578 | 3,359 (3,968) | 3,290 (3,910) | 3,591 (4,305) |
| Validated facts stated correctly, read | — | 78.5% (all) | 86.7% (all 3,180) | 81.8% (560, three readers) | 85.3% (600; German 84.0%, English 86.8%) |
| Validated facts correct, blind same-reader tests against v0.3.0 | — | — | (the reference) | 50/60 vs 50/60; 84/100 vs 92/100 | 81/100 vs 87/100 |
| Fact refusals judged wrong, all codes | — | 84% (`duplicate` aside) | 57.3% (309/539) | 56.0% (298/532) | 43.9% (285/649) |
| `not_atomic` refusals judged wrong | — | — | 77% (131/171) | 82% (152/186) | 40% (81/203) |
| Facts recovered by the repair call | — | — | — | — | 262 validated of 390 written |
| **Bridges** | | | | | |
| Bridges validated (written) | none | none | 179 (249) | 140 (228) | 178 (243) |
| Validated bridges judged correct | — | — | 22% (40/179) | 16% | 19% (34/178) |
| Blind same-reader test against v0.3.0 | — | — | (the reference) | 8 vs 7 of 40 | 12 vs 9 of 40 |
| **Topics and passages** | | | | | |
| Topics (German / English) | — | 20 (one failed) | 17 (9 / 8) | 16 (8 / 8) | 17 (9 / 8) |
| Topics coherent yes / partly / no | — | — | 1 / 14 / 2 | 0 / 11 / 5 | 0 / 14 / 3 |
| Topic labels fit yes / partly / no | — | 6 / 11 / 3 | 4 / 12 / 1 | 8 fit | 3 / 11 / 3 |
| Passages faithful to the PDF: good / minor / major | — | 387 / 381 / 65 | 530 / 225 / 65 | 35 re-chunked: 25 better, 0 worse | unchanged from v0.4.0 |
| **Cost** | | | | | |
| Model spend for the run (USD) | — | — | 17.93 | 34.32 (two builds; the clean question pass 14.60) | 21.23 |

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
unlabelled, below the fact share that `TOPIC_LABEL_MIN_FACT_SHARE` set and
v0.4.4 removed.

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
| Category | Not held to a quota, only reported beside the pool's counts. None here: every question of this rebuild was written before prompt version 17 told a writer any category |

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

### The paper's judge

From template version 3, a question that opens its thread is also scored by
the DataMorgana paper's judge (Filice et al., [*Generating Q&A Benchmarks for RAG Evaluation in Enterprise
Settings*](https://aclanthology.org/2025.acl-industry.33/), ACL 2025 Industry Track,
Appendix D). The run above was judged under version 2 and carries none of
these scores.

The judge is the paper's prompt, in its words and with its six Wikipedia
examples. It is shown the passages the question's facts cite, each once and at
most four, and in one call it scores the question 1 to 3 on fluency, clarity,
conciseness, relevance, consistency and answerability. Each score is stored as
its own metric, `rubric_fluency` to `rubric_answerability`, with the score
(s − 1) / 2.

The paper reports, per benchmark, the mean of each score shifted by
(mean − 1) / 2 into the range 0 to 1. The shift is linear, so that figure
equals the mean of the stored scores over the same questions, and it can be
read straight from `assessment_metrics`:

```sql
SELECT q.language, m.metric, count(*) AS questions,
       round(avg(m.score)::numeric, 3) AS normalised
FROM assessment_metrics m
JOIN assessments a ON a.id = m.assessment_id
JOIN questions q ON q.id = a.question_id
WHERE m.metric LIKE 'rubric%'
GROUP BY q.language, m.metric
ORDER BY q.language, m.metric;
```

The figures are per language, as everything on this page is: the paper
judged English questions with an English prompt, and this corpus is half
German.

### The paper's judge against the review

Under template version 3, the paper's judge was held against the labelled
v0.3.0 review: 350 answerable root questions of the Laws of the Game (175
accepted, 175 rejected, half in each language), judged by azure/gpt-4.1 for
USD 1.26, every reply complete.

| | German | English |
|---|---|---|
| Spearman's rho, the judge's mean score against the reviewers' verdict | 0.385 | 0.295 |
| Kappa, answerability below 3 against the reviewers' "breaks" signal | 0.200 | 0.288 |
| Kappa, question relevance's `unrelated` against the same signal | 0.191 | 0.256 |
| Questions question relevance called `unrelated` | 3 | 3 |
| Share the judge approves (every score 3) | 90% | 90% |
| Share the reviewers found usable | 62% | 69% |
| Kappa, the judge's approval against "usable" | 0.239 | 0.212 |
| Kappa, question relevance's approval against "usable" | 0.114 | 0.064 |

The rule was set before the run: a question's `relevance` goes if the
paper's answerability agrees with the reviewers at least as well and the
judge's mean correlates with their verdict, in both languages. Both held, so
template version 4 no longer asks it. The margins are thin, since question
relevance called three questions in each language `unrelated`. These are
agreement figures on one corpus; nothing was tuned to them.

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
their shared model is an Ollama model, and each host drain refuses while its
stage's worker container runs. No run those rules allow repeats the run
above.

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

Eight kinds came 2 or 3 short of their quota of 36 or 37. The pool still
held answerable questions of every one of them but `enumeration`: the draw
takes a thread whole, so `condition` follow-ups drawn with their roots took
21 places over its quota, the places the short kinds lost. The draw put 394
pairs of released questions to the verifier as possibly wanting one answer;
it read 12 of them as twins, and one question of each of those was released.

The first draw weighed `aggregation` 4, like most kinds. The pool held only
13 aggregations, and that capped the whole release at 133 questions.
v0.3.0 weighs it 1, as it weighs `comparison`.

The counts are queries over the run's own tables. Wall clock, calls and
spend come from each stage's `make` output, which logs every model call with
its cost.

## The v0.4.0 rebuild of 2026-10-18

The same two PDFs taken through every stage by the code of v0.3.8, with the
same models, and every stored question deleted before a single questions
pass. Not released. Every accepted question and every rejected one was read
against the corpus, every refused fact, 720 validated facts, every bridge and
topic, and the passages whose text changed.

| | v0.3.0 | v0.4.0 |
|---|---|---|
| Questions accepted / written | 871 / 1,507 | 886 / 1,550 |
| Released (German / English) | 343 (182 / 161) | 318 (165 / 153) |
| Released usable, settled | 79.0% | 82.7% |
| Released invalid | 10 | 8 |
| Accepted usable | 69.9% | 75.3% |
| Answer keys correct / complete | 80.1% / 72.0% | 87.0% / 73.2% |
| Two-passage questions welded, accepted | 33 / 183 (18.0%) | 32 / 144 (22.2%) |
| Rejections wrong | 38% (183 usable lost) | 34% (168 usable lost) |
| Fact refusals wrong | 57.3% | 56.0% |
| Validated facts correct, blind same-reader tests (160 each) | 88.8% | 83.8% |
| Validated bridges / of them judged correct | 179 / 22% | 140 / 16% |
| Topics (German / English) | 9 / 8 | 8 / 8 |
| Accepted unanswerables the corpus answers | 43.3% | 38.1% |

## The v0.3.12 rebuild of 2026-10-19

The same two PDFs taken through every stage by the code of v0.3.12 (the
stack v0.3.9 to v0.3.12), with the same models, from a fresh extraction.
Every accepted and every rejected question was read against the corpus, as
were every refused fact, 600 validated facts, every bridge and topic, and
blind same-reader samples of facts, bridges and two-passage questions beside
v0.3.0's.

| | v0.3.0 | v0.4.0 | v0.3.12 |
|---|---|---|---|
| Questions accepted / written | 871 / 1,507 | 886 / 1,550 | 960 / 1,753 |
| Released (German / English) | 343 (182 / 161) | 318 (165 / 153) | 395 (205 / 190) |
| Released usable, settled | 79.0% | 82.7% | 82.3% |
| Released invalid | 10 | 8 | 9 |
| Accepted usable | 69.9% | 75.3% | 76.6% |
| Answer keys correct / complete | 80.1% / 72.0% | 87.0% / 73.2% | 87.8% / 74.0% |
| Two-passage questions welded, accepted | 33 / 183 (18.0%) | 32 / 144 (22.2%) | 40 / 225 (17.8%) |
| Two-passage questions welded, released | 17 / 91 (18.7%) | 19 / 65 (29.2%) | 23 / 95 (24.2%) |
| Rejections wrong | 38% (183 usable lost) | 34% (168 usable lost) | 33% (214 usable lost) |
| Fact refusals wrong | 57.3% | 56.0% | 43.9% |
| Validated facts read correct | 86.7% | 81.8% | 85.3% |
| Validated bridges / of them judged correct | 179 / 22% | 140 / 16% | 178 / 19% |
| Topics (German / English) | 9 / 8 | 8 / 8 | 9 / 8 |
| Accepted unanswerables the corpus answers | 43.3% | 38.1% | 34.0% |

What moved, and why:

- **Bridge-plus-fact questions are gone.** v0.3.9 offers a bridge on its own
  rather than beside an unrelated claim of its anchor passage. Blind, the
  accepted bridge-plus-fact questions fell from 54 (7 welded) to 7 (none), and
  a bridge alone welds at 9% in both builds.
- **The released weld rate rose while the accepted rate fell.** It is the
  draw. Replayed over 100 hash salts, the release code gives the v0.3.0 and the
  v0.3.12 pools the same expected released weld rate, 21.8%. v0.3.0's stored
  release sits at the 2nd percentile of its own distribution, v0.3.12's at the
  72nd. A blind same-reader test reads 13.2% against 20.0% (z = 1.25).
- **Wrong `not_atomic` refusals fell from 82% to 40%** (81 of 203). The
  v0.3.10 repair call wrote 390 pieces, and 262 of them were validated. Read,
  they are as correct as the other facts (41 of 49, against 471 of 551).
- **Validated facts read correct 85.3%**, below v0.3.0's 86.7% but within
  reader spread. Blind same-reader: 81 against 87 of 100, not significant.
- **Topics, the most cohesive of eight seeded draws**, read coherent 0 / 14 / 3
  (yes / partly / no), against 0 / 11 / 5 for v0.4.0's single draw.
- **Verifier prompt 6** lowers the share of kept unanswerables the corpus
  answers, most in English. Unanswerables are still not released.

Found on this run, not fixed in it:

- The release-size bisection ships fewer than 200 questions for 43 of 100
  hash salts of this pool, against 6 of v0.3.0's. The stored hash fills to 395,
  so this release is unaffected. Scanning sizes downwards instead removes all
  43 at an unchanged weld rate.
- The per-passage fact cap refused 65 facts as `over_cap`, 59 of them repaired
  pieces, 78% of them wrongly.

Model spend for the run: USD 21.23.

## The v0.3.13 to v0.4.0 cycle: replays and calibrations

**No rebuild of the Laws of the Game corpus was made on the code of v0.3.13 or later.** The last build on this page is the v0.3.12 rebuild of 2026-10-19, and every figure below is an offline replay of stored data or a calibration of one model reading on labelled rows; none is a fresh run of the whole pipeline. A replay moves only what a code change decides without a model, so a change that rests on a model reading (the needs_both check, the bridge prompts, the unanswerable reading) is shown through its own calibration, with the rows and the bar it was held to. The first full build of this code is still to be made; until then the figures that matter for a release (usable share, weld rate, release size) are the v0.3.12 rebuild's.

### The offline scoreboard, v0.3.12 against v0.4.0

The scoreboard replays the stored rows of the v0.3.0 rebuild (its questions, facts and release) under the checkout's code and compares the result with what v0.3.0 stored. It reads stored model verdicts and calls no model, so it shows exactly what changes in the code's own decisions. The same two rows fail from v0.3.19 on; the v0.3.12 pool, not these rows, decided that they were an acceptable move (see the notes below the table).

| Row | v0.3.0 as stored | v0.3.12 code | v0.3.27 code | v0.3.34 code | v0.4.0 code |
|---|---|---|---|---|---|
| Released invalid (draw replay at stored size) | 10 (11 replayed) | 8 | 9 | 9 | 9 |
| Released welded of two-passage (draw replay) | 17/91 (19/96 replayed) | 19/91 | 21/91 (fails) | 21/91 | 21/91 |
| Release German share (pool) | 0.531 (0.532) | 0.531 (0.531) | 0.523 (0.528) | 0.523 (0.528) | 0.523 (0.528) |
| Release bands, easy / hard (pool) | 0.659 / 0.067 (0.662 / 0.064) | 0.659 / 0.067 (0.662 / 0.065) | 0.651 / 0.064 (0.657 / 0.064) | 0.651 / 0.064 (0.657 / 0.064) | 0.651 / 0.064 (0.657 / 0.064) |
| Weld rate, accepted two-passage | 33/183 (0.180) | 32/181 (0.177) | 34/184 (0.185, fails) | 34/184 | 34/184 |
| Answerable keys correct / complete | 0.801 / 0.720 | 0.8111 / 0.7264 | 0.8111 / 0.7264 | 0.8111 / 0.7264 | 0.8111 / 0.7264 |
| Validated facts stated correctly | 2,758/3,180 (0.8673) | 2,772/3,195 (0.8676) | 2,772/3,195 (0.8676) | 2,776/3,199 (0.8678) | 2,776/3,199 (0.8678) |
| Accepted pool replayed (usable share) | 871 | 859 (0.7113) | 879 (0.7088) | 879 (0.7088) | 879 (0.7088) |
| `answer_incomplete` refusals, German / English | n/a | 26 / 34 | 18 / 22 | 18 / 22 | 18 / 22 |
| German `unresolved_reference` refusals | n/a | 59 | 59 | 56 | 56 |
| English `unsupported_addition` refusals | n/a | 32 | 32 | 31 | 31 |
| Unanswerables: recall German / English | n/a | 0.518 / 0.610 | 0.518 / 0.610 | 0.518 / 0.610 | 0.518 / 0.610 |

What moved, and why:

- **The pool grew by 20 questions and the weld rate crossed its floor** because the `answer_incomplete` gate now refuses a list key only when the recovery names an item the key and question lack (v0.3.19), together with two reading fixes (v0.3.18, v0.3.24). Of the 20 `answer_incomplete` refusals it removed on these rows (German 8, English 12), the stored labels call 15 wrong, 2 partly right and 3 right. The weld rows fail by half a point on these rows (0.185 against 0.180) and by two released rows (21 against 19). The shipped answer to them is the needs_both check of v0.3.35, which the scoreboard cannot replay because it calls the model; the calibration below is what stands for it.
- **Three German facts** were admitted by the reference fixes of v0.3.29 (facts 11566, 12590 and 12469, all stated correctly) and **one English fact** by the number readings of v0.3.33 (fact 13216, a throw-in countdown, correct); no right refusal was lost in either.
- **Nothing else moved** across v0.3.28 to v0.4.0 in questions, release, unanswerables or passages: each release was replayed against the one before, and v0.4.0 against the v0.3.27 code.

### The needs_both check (v0.3.35): calibration on labelled rows

Verifier prompt `stated` 1 lists the parts of a needs_both question's answer and quotes every cited passage that states each; code finds the quotes, and the question stays two-passage only when each cited passage holds a part no other holds (with a tie kept two-passage when the question joins cases with a coordinating conjunction). It was calibrated through the pipeline's own function on rows read by people, with the bar fixed before any call. "Honest" means a needs_both question the readers judged to need both passages; "padded" one that one passage answers whole; "compound" a gold compound question, which the check must not relabel.

| Step | Rows | Honest kept | Padded relabelled | Gold compounds relabelled | Result | Cost |
|---|---|---|---|---|---|---|
| 0, fixtures (bank and shop, German and English) | 12 | 10/12 decided as labelled; both two-cases-one-answer fixtures stay two-passage | | | passes | USD 0.02 |
| 1, first iteration, v0.3.12 | 76 | 26/31 (0.84) | 38/45 (0.84) | 4/8 (bar at most 2) | fails on the compounds; stopped | USD 0.19 |
| 1, second iteration, replayed from stored replies, v0.3.12 | 76 | 30/31 (de 17/18, en 13/13) | 33/45 (de 16/21, en 17/24) | 0/8 | passes (no call) | USD 0 |
| 2, v0.3.0 holdout | 53 | 23/23 (de 12/12, en 11/11) | 25/30 (de 12/15, en 13/15) | 0/7 | passes | USD 0.14 |
| 3, blind same-reader read | 31 | 10 kept controls: yes 0/10 (all "partly", so keeping them two-passage was right) | 20 padded relabelled: yes 20/20 | 0 relabelled | passes (bar: at least 14 yes, at most 2 no) | USD 0 |
| Gold rest, v0.3.12 (176 gold rows in all) | 208 for both builds (171 calls) | 29/36 (0.81; de 18/23, en 11/13) | 76/107 (0.71; de 39/55, en 37/52); by citation 36/107 (0.34) | 0/18 | passes the lenient bar (0.68 / 0.64) | USD 0.44 for both builds |
| Gold rest, v0.3.0 (161 gold rows in all) | (counted above) | 20/20 | 68/97 (0.70; de 36/52, en 32/45); by citation 60/97 (0.62; en 0.58) | 1/30 (row 4392, English) | fails "no compound relabelled" by one row | included above |

The second iteration changed code only: a tie where every passage states every part now keeps both passages when the question has a coordinating conjunction (the universal tag CCONJ). It was fitted on step 1's rows, so the v0.3.0 holdout of step 2 decided it. On the hand-made gold labels, read by the same function on 129 of the 337 gold rows, the check kept 21/23 needs_both questions of v0.3.12 (0.91; de 0.87, en 1.00) and relabelled 32/44 padded ones (0.73; de 0.75, en 0.71) and 0/8 compounds; on v0.3.0 it kept 13/13 and relabelled 25/30 (0.83) and 0/8. Total spend on the calibration: USD 0.79 for about 300 calls.

The counts "by citation" are what is stored afterwards: a padded question that cites a bridge fact keeps both passages, because the bridge itself rests on two. That is why the share narrowed in the store is lower than the share the reading decides, and why bridge-cited padded questions remain the largest open item. The check adds one verifier call per accepted answerable needs_both question citing two passages, about USD 0.45 to 0.5 per build the size of the Laws of the Game. A design that asked the writer for the key as parts tagged by passage was analysed offline against this check and rejected: a yes/no judge on the same rows dropped 4 to 6 honest questions and relabelled 1 to 2 compounds, and the design would cost about USD 0.9 to 1.0 a build.

### Bridges: pairing and prompts

| Change | Figure | Release |
|---|---|---|
| Bridge checks read the heading trail and title as an atomic fact's are; a bridge writing a cited passage's numbered heading whole is refused as `not_bridging` | over the 243 bridges of the v0.3.12 build, validated 178 to 184, those judged correct 34 to 37, five label refusals, no validated bridge newly refused | v0.3.15 |
| Pairs follow the documents' own links across topics (numbered or quoted heading named, sibling sections under one parent, a term only two passages share) | offline over the v0.3.12 passages: 204 pairs, 47% across topics; labelled pairs 29% correct against 18% for nearest-neighbour pairs | v0.3.16 |
| Bridge prompt 6 (link named, one bridge or none, closed relation set), with the pairs above | read blind: 42% correct against 12%; wrong and unsupported 13% against 15%. The new pairs with the old prompt 5 had raised wrong and unsupported from 15% to 37%, which is why they shipped together. About USD 0.25 more a build in input tokens | v0.3.16 |
| Bridge prompt 7, one form per relation (not shipped) | 80 calls: 36 bridges validated, 15 correct (41.7% against 42% asked; German 29% against 30%), wrong or unsupported 13.9% against 13% allowed | session A, set aside |
| Bridge prompt 8 against prompt 6 (not shipped) | 80 fresh pairs, 80 calls (USD 0.43 with the prompt-6 comparison): correct per 100 calls 16.2 to 17.5, correct 13/26 to 14/26 (50% to 54%; German 45% to 50%), wrong or unsupported 3/26 (11.5%); but 2 of 9 correct parallel or contrast bridges refused as spread (22%, bar at most 15%) and 12/16 drift controls repeated (bar at least 13). On the same pairs prompt 6 gave 10 of 19 correct (53%) against prompt 8's 7 of 14 (50%) | this cycle, deferred |
| A bridge test at extraction (every bridge refused unless it needs both passages; not built) | session A's version refused 5 of 16 correct bridges (bar at most 15%, about 2) and kept 11.5 correct bridges per 100 calls; the plan predicted about 6 of 16 refused, so it was not built | this cycle, deferred |

The bridge relation and probe question are stored in `facts.bridge` from v0.3.23 on; every prompt digest and output was unchanged by that release.

### The release draw

| Check | Figure | Release |
|---|---|---|
| Sizes scanned down instead of bisected, over 100 paired hash salts of the v0.3.12 pool | draws under 200 rows: 43 before, none after; 139 rows more on average (126 over 200 salts); weld rate +0.5 points (interval -0.6 to +1.5; over 200 salts +0.1, -0.5 to +0.8); invalid rows per 100 -0.002; German share unchanged; worst band deviation 0.62 to 0.27 points; the stored salt-0 releases unchanged. On the older v0.4.0 pool the weld rate rises 0.30 points (0.08 to 0.52) | v0.3.27 |
| A kind, band or language held only by unanswerable rows is dropped as an absent one | released ids identical on 100 of 100 salts | v0.4.0 |
| Default language weights count drawable rows | 100 paired salts: mean release size 399.1 to 399.2, mean id overlap 0.937, release German share 0.520 to 0.514 (answerable pool 0.515); weld count +0.03 (-0.39 to +0.45), weld per 100 released +0.006 (-0.100 to +0.112), released invalid +0.01 (-0.18 to +0.20, mean 8.82); intervals also include 0 on the v0.3.0 and v0.4.0 pools | v0.4.0 |
| The scan's upper bound counts unanswerable rows only up to the ceiling | 4,578-row pool with one kind left only as unanswerable rows: 1,653 draws and 59.7 s before, 1 draw and 0.1 s after, same ids; no gain on the v0.3.12 pool (17.1 draws either way); 2,000 to 10,000 rows of typical shape take 0.1 to 37 s | v0.4.0 |

### Links

| Check | Figure | Release |
|---|---|---|
| Sibling linking scores a family with one matrix product | flat parent with 1,024-dimension vectors: 1,000 sections 37.5 s to 5.7 s, 2,000 sections 132 s to 16 s, 4,000 sections about 8 minutes to 59 s; the pairs offered are identical to the old ones on the v0.3.12 passages and on synthetic flat parents of 300 and 2,000 (no, random, tied and partial vectors). Still quadratic in building the links, about eight times flatter | v0.4.0 |
| Links are dealt among passages that hold a validated fact | v0.3.12 corpus, two passages per bridge: 158 links to 164; three passages: 148 to 162 | v0.4.0 |
| A numbered reference resolves in its own document | links over the v0.3.12 passages 166 to 166 (German unchanged; English 7 removed, 7 added, all 7 added right) | v0.4.0 |

### Replays of the other fixes

| Change | Figure | Release |
|---|---|---|
| Compound and unanswerable samples never rest on a bridge | v0.3.12 pool, 17 topics: compound slots resting on a bridge 5 to 0 (68 still dealt); unanswerable slots dealt a bridge 67 to 0 (364 dealt, 358 after, 6 skipped); unanswerable share of written slots 0.295 to 0.293 | v0.3.30 |
| Re-parse of the 30 football PDFs (15 German, 15 English) | one table row per language changes (`b) c) d) e)` in uefa-equipment-regulations.pdf, now two rows) | v0.3.31 |
| Re-chunk of the 30 football PDFs | table footnotes and lead-ins: 0 passages change (German 1,000, English 966); chunk structure: German 1,000 to 1,003 (a footer and a running header split off), English unchanged | v0.3.32, v0.4.0 |
| Image-only pages in the 30 football PDFs | 5 name one page each, all real picture pages (back covers, a photo cover) | v0.4.0 |
| Topic labels and small languages | Laws fit identical (German 9, English 8 topics, 0 memberships changed, 17 labels unchanged) | v0.4.0 |
| Compound questions, calibrated on pairs built outside the deal | 28 of 48 pairs accepted (German 14 of 24, English 14 of 24); read blind, all 28 compound, none a false join; 21 usable (75% against the 80% asked) and 19 keys right (68% against 75%). The real path through the deal was not calibrated | v0.3.22, v0.3.26 |
| Unanswerable questions | v0.3.17: kept-answered share on the labelled drafts 0.342 to 0.253 on replay. The reading of settles prompt 7 flagged 4 of 20 drafts the passages answer (not shipped) | v0.3.17, deferred |
| Per-passage atomic cap | v0.3.14: 65 `over_cap` refusals to 0 on the v0.3.12 build; readers called 51 sound, 10 rightly refused, 4 partly right | v0.3.14 |
| Dash ranges and answer completeness | over 919 stored recoveries two verdicts move, both wrong refusals (v0.3.18, v0.3.24); `answer_incomplete` frees 31 of 75 refusals on the v0.3.12 build (27 wrong, 3 partly right, 1 right; 80.6% usable) and 23 of 67 on the v0.4.0 build (19, 4, 0; 73.9% usable) (v0.3.19) | v0.3.18, v0.3.19, v0.3.24 |

Model spend of the cycle's calibrations: USD 1.60 of the USD 10 cap (the needs_both check 0.79, bridge prompt 8 0.43, the false-premise redesign 0.26, settles prompt 7 0.12). The rebuild of the corpus that was planned for this cycle was dropped, so no build cost was spent.

## The DataMorgana releases: how varied the questions are, and the categories (v0.4.1 and v0.4.2)

v0.4.1 and v0.4.2 added the diversity scores of the DataMorgana paper (Filice et al., Appendix E) and the question categories of its Figure 2 and Table 5; the paper is cited in full under [References](#references). Their figures were measured when the releases were made and stood only in the release notes until now. Every figure below was measured on the production database's release, the v0.3.12 build of the Laws of the Game (325 accepted answerable root questions: 166 German, 159 English), or on the calibration links named in the text. That database still runs v0.3.12's schema, so the workbook was exported with v0.3.12's code. Tags come from de_core_news_md 3.8.0 and en_core_web_md 3.8.0, and vectors from intfloat/multilingual-e5-large.

### Diversity of the questions

`make diversity` reads a workbook that `make questions-export` wrote and asks no model. NGD is n-gram diversity (higher is more varied). SR is self-repetition, word-CR the compression ratio of the words, PoS-CR the compression ratio of the part-of-speech tags and HS the homogenization score, the mean cosine between every two questions (lower is more varied for all four). The metrics move with the size of a set, so two sets compare only at one size. v0.4.1 measured the first three, and v0.4.2 added PoS-CR and HS.

| Language | n | NGD | SR | word-CR | PoS-CR | HS |
|---|---|---|---|---|---|---|
| de | 166 | 3.090 | 0.157 | 3.020 | 8.492 | 0.819 |
| en | 159 | 2.905 | 0.352 | 2.934 | 7.973 | 0.804 |

- The English questions repeat themselves more than the German ones: 35% of them share a four-word run with another question in the set, against 16%. At a size of 150 the rows read 3.107, 0.127 and 2.951 (German) and 2.923, 0.340 and 2.929 (English): a smaller set shares fewer runs.
- The embedding model's cosines sit at 0.80 to 0.82 for any two texts in one language, so an HS figure says something only beside another set embedded with the same model. It is on a scale of its own, because the corpus's multilingual model replaces the paper's English-only one.
- Against its pool of 586 accepted answerable root questions, comparing the two workbooks with `AGAINST=` (fifty draws of 80% of the smaller set, Welch's t-test, as in the paper's Appendix E.2) finds that the release keeps the pool's variety: no score moves by more than 0.1. Eight of the ten differences still read as significant, because fifty overlapping draws spread little. The size of a difference matters more than its p.

### The categories, calibrated on four links

Four calibration links ran the v0.4.2 code on copies of two frozen corpus databases, the Laws of the Game and the Your Europe consumer pages, each in German and English. The writer was azure/gpt-5.4 and every other role azure/gpt-4.1. Each link was held to USD 8, so each is a sample. Links 046 (Phrasing) and 049 (Phrasing and Premise) ran the lowest topic ids at the planned N (24 questions a topic on the Laws of the Game, 41 on Your Europe) for USD 6.71 and 6.80. Links 0410 (adding Linguistic variation and User expertise) and 0411 (adding the two search queries) ran every topic at a cut N for USD 5.92 and 5.82. Link 040 is the baseline, v0.4.0's code with no categories, on link 046's topics, for USD 6.64. Thirty accepted answerable root questions of each category were labelled against the calibration rubric. The floors, set before the run, were keys correct at least 0.80, keys complete at least 0.72, and invalid rows failing a category only at 3 or more in 30 and more than its sibling's in the same link. (Read literally, the earlier floor of 2.9% invalid fails on any one invalid row in 30; the v0.4.3 calibration below replaces it.)

| Category | Link | Keys correct | Keys complete | Invalid | Usable | Outcome |
|---|---|---|---|---|---|---|
| concise-and-natural | 046 | 0.933 | 0.733 | 1 of 30 | 0.500 | passes; default |
| verbose-and-natural | 046 | 1.000 | 0.900 | 0 of 30 | 0.733 | passes; default |
| direct | 049 | 0.833 | 0.767 | 3 of 30 | 0.633 | passes; default |
| with-premise | 049 | 0.900 | 0.733 | 3 of 30 | 0.633 | passes; default |
| similar-to-document | 0410 | 0.933 | 0.800 | 1 of 30 | 0.700 | passes; opt-in |
| distant-from-document | 0410 | 0.900 | 0.567 | 3 of 30 | 0.467 | fails; opt-in |
| expert | 0410 | 0.867 | 0.600 | 4 of 30 | 0.533 | fails; opt-in |
| novice | 0410 | 0.967 | 0.767 | 0 of 30 | 0.633 | passes; opt-in |
| short-search-query | 0411 | 0.700 | 0.567 | 3 of 30 | 0.433 | fails; opt-in |
| long-search-query | 0411 | 0.933 | 0.833 | 2 of 30 | 0.667 | passes, but a third are not queries; opt-in |
| no categories (v0.4.0) | 040 | 0.883 | 0.800 | 1 of 60 | 0.667 | baseline |

A categorization left with one category is dropped whole, so similar-to-document and novice, which passed, stay opt-in with the four that did not.

- **Phrasing** (link 046 against link 040, same topics). Acceptance was 56.1% of German rows and 55.6% of English, against 51.4% and 56.7%. German concise questions were accepted least (51.5%, against verbose's 67.9%), mostly through `leaks_source` (10 refusals in 103 rows), because the gate took a one-word page title used as the subject for naming the source. The measured sets are more varied in 19 of 20 comparisons (p at most 0.001), most of all in PoS-CR, by 0.290 to 0.404. Concise questions lose their situation: 14 of 30 do not stand alone or are ambiguous, against 2 of 30 verbose. The word bounds hold for 53 of 53 German and 52 of 55 English concise questions, and for 52 of 53 and 53 of 54 verbose ones.
- **Premise** (link 049). With-premise questions were accepted more often: 68.7% against direct's 57.1% in German, and 65.3% against 62.5% in English. Their sets are less varied on every score in every cell but one tie. Of 130, 33 open with a scene label (*Beim Spiel:*) rather than a premise about the asker.
- **Linguistic variation and User expertise** (link 0410). The word-gate trigger fired in English (distant +12.4 points, novice +8.7), all of it on Your Europe. Meaning drift touched 7 of 60 rows and is not specific to the reworded categories.
- **Search queries** (link 0411). None of the 90 accepted queries ends in a question mark, and 88 of 90 keep their bounds. The German parse finds no subject in lower-cased keyword queries, so `unanchored` refused 10 of 84 German query rows, against 7 of 95 natural ones. `not_recoverable` refused 20 of 161 query rows, against 28 of 170 natural ones, but the verifier agrees with the key on queries that could mean two needs (8 of 60) or that another passage answers differently (6 of 60).
- **The release mix.** Links 046 and 049 release within 10.0 points of their pools on every category. Links 0410 and 0411 release 14 to 21 categorised questions a corpus and drift by up to 33.9 points.

The categories calibration cost USD 26.51 together with the judge's agreement run, against a cap of 40, and the baseline link cost USD 6.64 more.

### What these releases did not measure

- Figure 1 of the paper (PoS-CR over a growing number of documents) was not measured at a size of 200: link 046's Your Europe workbook holds 202 German questions across 20 documents and 186 English ones across 23, and the first point needs 5 documents of at least 40 questions each, where the fullest hold 25 and 22.
- The paper's judge was checked against the labelled v0.3.0 review (see [The paper's judge against the review](#the-papers-judge-against-the-review)) but not run on any calibration link, so its means per category and per kind, and its reading of search queries, are not measured.
- `intent`, a planned stored restatement of what each question asks, was not built, and without it the offline check of meaning drift was not run.

## The v0.4.3 calibration

v0.4.3 changes how questions are planned, written, accepted and released (see [the finalize review](bugs.md#found-by-the-finalize-review-of-2026-10-21)). Its calibration has a rule for what counts as a pass, written before anything was measured, and replays that need no model or only a small one. The two calibration links, Link Q and Link C, and the premise iteration's own run are below.

### The floor rule

The rule replaces the floors above (keys correct at least 0.80, complete at least 0.72, invalid at most 2.9% of 30 rows), which fail on one invalid row in 30, and each link of the DataMorgana work had its own labeller, drain and topics.

- **Arms.** An arm is one set of accepted answerable root questions from one link, sharing one setting. A category is compared with its sibling or siblings in the same categorization, dealt in the same run on the same topics and code, on the slots both could be told. A code fix is compared with the base code run on a copy of the same frozen base, with the same topics, `QUESTIONS_PER_TOPIC` and seed.
- **Sample.** 60 rows per arm, drawn evenly over the languages and corpora present, or every row where an arm has fewer. An arm under 40 rows is "not measured", never passed.
- **Labelling.** One labeller labels every arm of a link, against one rubric, with the rows shuffled across arms and the arm and category hidden. Conformance (does the question look like its category) is labelled in a second pass that shows the category's description.
- **Pass**, when every row holds: keys correct, and keys complete, at least the baseline's share minus 0.10; invalid per 60 at most the baseline's plus 2; and, for a category, conformance at least 0.80.
- **Error rates**, simulated with binomial draws at a baseline of 0.85 correct, 0.75 complete and 3 to 5% invalid, with 60 rows per arm: equal arms pass keys correct 95% of the time, and an arm 0.10 worse passes 52 to 54%, 0.15 worse 29% and 0.20 worse 11%. A category as good as its sibling passes every measure 78 to 80% of the time, and about 95% after its one re-run.
- **Sanity.** A link is suspect when its baseline arm falls below 0.70 keys correct or 0.62 complete, which flags about 1% of healthy links. A suspect link is investigated and re-labelled once by a new labeller, never until it passes.
- **Gate changes replayed on stored rows.** Every row whose verdict changes is labelled, up to 60. A loosening passes when the newly admitted rows' usable share is at least the accepted baseline's minus 0.10, with at most 2 invalid per 60. A tightening passes when at most 35% of the newly refused rows are usable.

### The offline scoreboard, base against the v0.4.3 stack

The scoreboard replays the stored rows of the v0.3.0 rebuild under a checkout's code (see [above](#the-offline-scoreboard-v0312-against-v040)). At the stack's code before the prompt changes, which it cannot replay, against v0.4.2:

| Row | v0.4.2 | v0.4.3 stack |
|---|---|---|
| Validated facts stated correctly | 2,776 of 3,199 (0.8678) | 2,776 of 3,199 (0.8678), unchanged |
| Accepted pool replayed (usable share) | 879 (0.7088) | 878 (0.7084) |
| Answerable keys correct / complete | 0.8111 / 0.7264 | 0.8108 / 0.7259 |
| Weld rate, accepted two-passage | 34/184 (0.185) | 34/183 (0.186) |
| Unanswerables: recall German / English | 0.518 / 0.610 | 0.518 / 0.610 |

The one accepted row that moves is a German row newly refused `not_recoverable`, which the labels call minor.

### The read fields on 300 labelled rows

The round trip's read is the one call every answerable question gets. Two fields were tried on it and replayed on the 300 rows that the five calibration links' spot checks labelled (the 2026-10-21 labels: 35 welds, 22 circular reason keys, 183 usable rows), each with the question, key and cited passages as stored. The bars, set before the calls: each field must refuse at least half of its labelled rows, and at most 35% of the rows it refuses may be usable. The model was azure/gpt-4.1 and each replay was 300 calls.

| Verifier version | Field | Refused | Caught | Usable among refused | Verdict | Cost |
|---|---|---|---|---|---|---|
| 10 | `asks_one` (welds) | 3 | 2 of 35 (0.057) | 1 of 3 | fails recall | USD 0.54 |
| 10 | `reason_given` (circular reasons) | 20 | 9 of 22 (0.409) | 7 of 20 (0.35) | fails recall | |
| 11 | `asks_one` | 16 | 8 of 35 (0.229) | 8 of 16 (0.50) | fails both | USD 0.66 |
| 11 | `reason_given` | 11 | 6 of 22 (0.273) | 1 of 11 (0.09) | fails recall | |
| 12 (`asks_one` removed) | `reason_given` | 19 | 11 of 22 (0.500) | 5 of 19 (0.26) | passes | USD 0.84 |

- `asks_one` failed twice: the first version caught 2 of 35 welds and, after its one iteration on the instruction alone, 8 of 35 with half of its refusals usable. It was taken out in version 12 (see [the withdrawn items](bugs.md#tried-in-v043-and-withdrawn-with-the-reason)).
- `reason_given` counts here as the checker's reason branch attributes it. Counted as one read, over the 54 reason rows, the read refuses 33, 28 and 28 rows in versions 10, 11 and 12, catching 21, 20 and 19 of the 22 circular keys, with 8, 4 and 5 usable rows among the refused.
- Over all 300 rows, version 12's read refuses 30 of the 245 rows it reaches, 5 of them usable (0.17).
- The model at temperature 0 still varies between runs: the rows the read recovers nothing for went from 22 to 11 between versions 11 and 12, so the strict recall of `reason_given` could fall on either side of 0.50 in a rerun. Version 12's figure sits exactly at the bar.

### The B1 title rule on stored rows

A question naming its page by a title that is also its subject (a page titled *Kreditkarten*, asked about as *Kreditkarten*) was refused `leaks_source` by a free rule. The rule was replayed read-only, with no model call, on every stored `leaks_source` row of the ten link databases (`qa_cal_laws` and `qa_cal_shop`, builds 040, 046, 049, 0410 and 0411), the base against the v0.4.3 code.

| | Laws | Shop | Total |
|---|---|---|---|
| Stored `leaks_source` rows | 8 | 80 | 88 |
| Refused by the base's free title rule | 4 | 75 | 79 |
| Refused only by the phrasing judge | 4 | 5 | 9 |
| Admitted by the v0.4.3 code | 4 | 74 | 78 |
| Still refused | 0 | 1 | 1 |

The bar for the count was that the refusals whose only trigger is a title naming the subject fall to at most 20% of the base's 79: 1 remains (1.3%), so it passes. The loosening bar, that the newly admitted rows are about as usable as the accepted pool, is decided on labelled rows: 60 of the 78 were drawn (41 German shop, 15 English shop, 4 German Laws; 8 unanswerable, 6 follow-ups) and labelled. The labeller found 27 usable and 16 invalid, with 43 of 52 answerable keys correct. These rows stopped at the free rule in the base and never met the later gates (the phrasing judge's own readings, the round trip's read), so the labels describe rows before those gates, not rows newly accepted. The decision is read on the rows that also pass the later gates. Those gates were replayed on the 60 rows (USD 0.21): 39 pass, 31 of them not compound (the compound rows' halves are not stored, so their per-half check cannot run). Of those 31, 21 are usable (0.68, against 0.50 in Link Q's base arm) and 6 are invalid (11.6 per 60). The loosening bar allows at most 2 invalid per 60, and in the floor rule's own form at most the base arm's 3 plus 2; both fail. None of the 6 is invalid for naming its title: they are welded sums across two passages, a question about a case-study person, two incomplete keys, a key the question gives away and a question word the key does not answer. The change was withdrawn from v0.4.3 with the writer line that went with it.

### The release draw over 100 salts

The release draw of the base and of the v0.4.3 stack were run on the labelled v0.3.0 snapshot (every released row carries a reviewer's label) with 100 paired hash salts. The bars, set before the run: the welded share of released two-passage rows at most 0.005 above the base's, and invalid rows per 100 released at most 0.5 above the base's.

| | Base (v0.4.2) | v0.4.3 stack | Difference |
|---|---|---|---|
| Mean release size, rows | 371.1 | 453.3 | +82.2 (larger on every salt, 14 to 139) |
| Smallest release of the 100 salts | 300 | 400 | |
| Mean two-passage rows released | 95.8 | 124.2 | |
| Welded share of released two-passage rows | 22.72% | 22.77% | +0.06 points (interval -0.32 to +0.47) |
| Invalid rows per 100 released | 3.30 | 3.03 | -0.26 (interval -0.35 to -0.18) |
| Usable share of the release | 0.786 | 0.781 | -0.005 |

Both bars hold. The intervals are 95% bootstrap intervals over the 100 salts. The same draw on the link pools, whose released rows carry no labels, is judged on size only and belongs to Link Q and Link C below.

### Link Q

Two arms on copies of the frozen bases, the base code (v0.4.2) against the v0.4.3 code, with the default categorizations (Phrasing, Premise), the same 10 topics (Laws 80 to 82 and 89 to 91 at `QUESTIONS_PER_TOPIC` 16; Your Europe 7, 8, 2 and 3 at 26) and the production model split. One labeller labelled 60 drawn rows per arm, every reason row the fix arm's read refused (28) and the base arm's (6), and every accepted row dealt verbose and with-premise (17 per arm), shuffled with the arm hidden. Cost: USD 3.35 and 3.47.

| Bar | Base | v0.4.3 | Verdict |
|---|---|---|---|
| Keys correct (60 drawn) | 59 | 59 | passes (bound 0.88) |
| Keys complete | 53 | 51 | passes (bound 0.78) |
| Invalid per 60 | 3 | 4 | passes (bound 5) |
| Read refusals on reason rows: usable | 0 of 6 | 3 of 28 (0.11); 22 of the 28 circular | passes (at most 0.35) |
| Acceptance, German / English | 52.2% / 52.6% | 47.7% / 56.3% | passes (within 10 points) |
| Verbose with-premise rows opening on a scene label | 6 of 17 | 4 of 17 (0.24) | fails (at most 0.10) |
| With-premise conformance | | 13 of 17 (0.76) | fails (at least 0.80) |

Reported beside them, deciding nothing: meaning drift 4 against 3 of 60, questions about a person or page furniture 7 against 8, welds 5 against 3, usable 30 against 33. The base arm's sanity holds (0.98 correct, 0.88 complete).

The premise rework then had its one iteration (a premise states a fact of the asker's own situation; a premise whose verbs only want, try, check or understand gets the retry note) and a run of its own on the same topics, every slot dealt verbose and with-premise (USD 1.65): of 36 accepted rows told a premise, none opens on a scene label, and 34 of 36 conform to the description. It passes. It holds 36 rows, under the 40-row minimum, with a zero rate. Acceptance there is 43% German and 48% English, within 10 points of the fix arm's.

### Link C

One run of the v0.4.3 code with three categorizations at probabilities set for calibration: Phrasing {concise 0.15, verbose 0.15, short-search-query 0.35, long-search-query 0.35}, Linguistic variation {similar, distant} and User expertise {novice, expert} at 0.5 each, on all 27 topics at `QUESTIONS_PER_TOPIC` 22. Premise was not dealt: the rule that tells no query on a with-premise slot halved the query rows in a first run, which was stopped after 6% (USD 1.23). Cost: USD 10.40. The same labeller as Link Q labelled each comparison's rows and then their conformance.

| Category | Compared with | Rows | Keys correct | Complete | Invalid per 60 | Conformance | Acceptance against sibling | Verdict |
|---|---|---|---|---|---|---|---|---|
| distant-from-document | similar, within novice rows | 60 vs 60 | 58 vs 57 | 57 vs 54 | 4 vs 11 | 48 of 60 (0.80) | +6.6 / +15.7 points | passes |
| expert | novice, within similar rows | 58 vs 60 | 51 vs 57 | 53 vs 54 | 13.4 vs 11 | 34 of 58 (0.59) | +11.6 / +3.8 points | fails (invalid, conformance) |
| long-search-query | concise and verbose on the same slots | 36 | 32 | | 23.3 | 31 of 36 | -4.1 / -7.5 points | not measured (36 rows) |
| short-search-query | concise and verbose on the same slots | 19 | 19 | 19 | | 15 of 19 | -52.9 / -54.7 points | fails supply; not measured |

Counted on all its rows, distant's conformance is 61 of 93 (0.66): the rows also told expert conform 12 of 32 times, because the two descriptions pull apart (one avoids the document's wording, the other asks for it). Linguistic variation enters the default with its two categories at even odds. User expertise stays opt-in: told on a slot whose fact is basic, the writer asked a basic question in an expert's voice. The two search queries stay opt-in: the short one is accepted on 29 to 31% of the slots a query may take, against 82 to 86% for natural phrasing there, and the long one has too few rows to measure.

| Cell | Labelled rows | Keys correct / complete | Invalid | Acceptance German / English |
|---|---|---|---|---|
| similar x novice | 62 | 0.95 / 0.90 | 12 | 0.43 / 0.42 |
| similar x expert | 58 | 0.88 / 0.91 | 13 | 0.55 / 0.46 |
| distant x novice | 61 | 0.97 / 0.95 | 4 | 0.50 / 0.58 |
| distant x expert | 32 | 1.00 / 0.97 | 6 | 0.54 / 0.55 |

### Spend

The v0.4.3 calibrations cost USD 22.4 of a USD 30 cap: Link Q 6.82, Link C 11.63 (with the stopped first run), the premise run 1.65, the read replays and the later-gates replay 2.25.

## The v0.4.4 bars

v0.4.4 changes how documents are read: parsing, chunking, the NLP readings that only fact validation calls, extraction and topics (see [the finalize review](bugs.md#fixed-in-v044-parsing-and-chunking)). Each bar was written before anything was measured. All but one are replays that call no model, on three real documents or on the two frozen calibration bases, `qa_cal_laws` (the Laws of the Game in German and English) and `qa_cal_shop` (the Your Europe consumer pages); the one that calls a model extracts facts with two prompts in copies of those bases. The base is the code before the fixes.

### Parsing and chunking

The rule: three real PDFs, one football PDF from `resources/` and two Your Europe pages, are parsed in process into a temporary folder, never the shared store, with the base and the fix code, then chunked, and the passages are diffed. A labeller reads every changed passage, up to 60. It passes when no changed passage loses source text or mixes two languages, and at most 2 are worse than the base. A fix whose target has no instance in the sample rests on its red tests.

| Document | Language | Pages | Passages, base / fix | Changed |
|---|---|---|---|---|
| `ifab-circular-attk.pdf`, the smallest German football PDF | de | 2 | 2 / 2 | 0 |
| `shopping-returns_de.pdf`, a lead-in and an eight-item list across a page break | de | 4 | 7 / 7 | 0 |
| `shopping-guarantees_en.pdf`, a country list and boxed panels | en | 8 | 16 / 16 | 0 |

It passes with nothing to label: base and fix wrote byte-identical converted documents and byte-identical passages. None of the parse and chunk fixes has an instance in the three documents (no lone integer outside the footer, no heading holding ` > `, no format character, no footnote on any of the 8 pictures, no table Docling labels, no page under 100 characters, no body line opening with a running head), so each rests on its red tests. Both sides read the football PDF's bullets as `∞` and flatten one nested item, which is the converter's reading and no change of this release.

### Fact validation

The rule: the scoreboard's facts section, v0.4.3's tip against v0.4.4's, under the replay rule, with the changed verdicts labelled against the rubric. A loosening passes when the newly validated facts' correct share is at least 0.867 − 0.10, and a tightening when at most 35% of the newly refused facts are correct. Under 20 changed rows the shares are read as counts and reported with the rows.

| Row | v0.4.3 | v0.4.4 |
|---|---|---|
| Stored verdicts the replay reproduces | 3,403 of 3,445 | 3,400 of 3,445 |
| Bridge verdicts reproduced | 227 of 248 | 227 of 248 |
| Validated facts, German / English | 1,700 / 1,499 | 1,697 / 1,499 |
| Validated facts stated correctly, by the v0.3.0 review's labels | 2,776 of 3,199 (0.8678) | 2,775 of 3,196 (0.8683) |
| Newly validated / newly refused | | 0 / 3 |

The three newly refused facts are German, and each is refused `unresolved_reference` by the new modifier tables. One labeller read them blind against the rubric:

| Fact | Statement | Read | Label |
|---|---|---|---|
| 11783 | *Eine solche Entscheidung kann nicht geändert werden, es sei denn, es handelt sich um eine klare und offensichtliche Fehlentscheidung.* | *solche* | vague, refusal right: the decision meant is the referee's on the field, which the statement does not carry |
| 11287 | *Die folgenden einfachen Leitlinien sollen Wettbewerbsorganisatoren bei der Anwendung der Kapitänsregelung unterstützen.* | *folgenden* | vague, refusal right: the guidelines follow the passage and are in neither it nor the statement |
| 11500 | *Das Abbilden solcher Logos und Embleme ist auf den Fahnen an den Fahnenstangen erlaubt.* | *solcher* | vague, refusal right: which bodies' logos are meant is in the passage only |

0 of the 3 are correct, under the 35% a tightening may refuse, so it passes. The v0.3.0 review had labelled fact 11287 correct, which is why the snapshot's count of correct facts falls by one; the blind label decides the bar. The other fact-check changes (polite *Sie* read against its passage, *dies* after a free relative, the list reader of the bridge check) move no verdict on this snapshot, and the new abbreviation tables cut a passage's sentences at chunking, while the replay reads the sentences as stored.

### The fixes from the QA pass, under the same bars

The QA pass of 2026-10-21 found defects in parsing, chunking and extraction that v0.4.4 also fixes (see [the finalize review](bugs.md)). They were held to the same two bars, on the same code they join.

**Parsing and chunking.** The bar ran on five documents this time: the three above, the 52-page UEFA disciplinary regulations (`uefa-disciplinary-regulations.pdf`, English) and a 4-page German IFAB circular (`ifab-circular-cooling.pdf`), both with running heads and page breaks. The first build of the fixes failed it: 88 passages changed (82 of the UEFA document's, 6 of the circular's), and of the 60 labelled, 28 were worse than the base against the 2 the rule allows, none losing text or mixing languages. Two causes: the running head was also split at a hyphen between spaces, so `IV - Other provisions` became two fields and the chapter's own heading stayed in every trail under it, and a one-letter field `I` matched `TITLE I - SUBSTANTIVE LAW`, so chapter I opened one heading early. Both were fixed (a head is split at dashes, dots and bullets, never at a hyphen; a heading is matched to a field word for word, and a one-letter field or a bare numeral never opens a chapter alone) and the bar ran twice more: on both later builds every document's converted text, passages and content digest are byte-identical to the base's, so it passes with nothing to label, and each fix rests on its red tests.

**Fact validation.** The replay re-cuts the stored passages' sentences with each build's code, so it measures the sentence-end fixes where a cut moves: 22 of 820 passages. No fact is newly refused; two are newly validated, a loosening, and were labelled blind:

| Fact | Fix | Label |
|---|---|---|
| 13367, *The minimum length of the goal line for international matches is 64 metres (70 yards).* | a figure ending a sentence stays in it (QA-extraction-1) | correct |
| 11898, *Wenn der Schiedsrichter nicht abschätzen kann, …, erfolgt der Schiedsrichterball mit einem Spieler des Teams, das den Ball zuletzt berührt hat.* | a cut before a lower-case word after no full stop is dropped (QA-extraction-4) | narrowed: it drops the condition that the ball was outside the penalty area |

Read per fix, the first passes (1 of 1 correct, against 0.767) and the second fails (0 of 1). The second also moved the cuts of 21 of the 22 passages, mostly joining clauses at a semicolon, so it was withdrawn and its row stays open. The fee-table fix (QA-extraction-7) changes which passages extraction skips, which a replay of stored facts cannot see; it rests on its red tests.

### A verbless definition (FIX-R13)

The rule: count the passages the new rule admits in both frozen bases, extract them into copies (USD 0.5 at most) and label every new fact; it passes at a correct share of at least 0.767, and under 20 facts with at most 2 wrong per 10. Not run: the rule was withdrawn after two reviews, before its extraction (see [the withdrawn items](bugs.md#tried-in-v044-and-withdrawn-with-the-reason)).

### Extraction prompts 13 and 14 (FIX-R129)

The rule: 60 passages under a heading, extracted with both prompts in copies of the bases (USD 0.6 at most). The facts that write the heading as a situation must fall to half or fewer, and the correct share must be non-inferior with a margin of 0.10.

The 60 passages are 15 per corpus and language, text or list passages of 120 to 1,100 characters under a trail of two or more headings, chosen from their text and trail alone where the sentences leave their subject or situation to the heading. Copies of both bases re-extracted them with `azure/gpt-5.4` (digests with `azure/gpt-4.1`). One labeller read every validated fact blind, the prompts pooled and hidden. A fact is correct when it is true against the passage read with its trail and keeps the scope it needs to be true alone; it writes the heading as a situation when it frames heading material as a condition or a setting the cited sentence does not state (*For a corner kick*, *Beim Abstoss*).

| | Prompt 12 | Prompt 13 | Prompt 14 |
|---|---|---|---|
| Validated facts labelled | 266 | 256 | 264 |
| Correct | 244 (0.917) | 203 (0.793) | 238 (0.902) |
| Heading written as a situation | 119 | 43 | 105 |
| Facts dropping a scope the heading gives | 5 | 32 | 7 |
| Heading bar (at most 59.5) | | passes | fails |
| Correct bar (at least 0.817) | | fails | passes |
| Cost (USD) | 0.59 with prompt 13 | | 0.31 |

- Prompt 13 stopped writing the heading as a situation by dropping it: of its 53 wrong facts, 32 drop a scope the heading gives and 15 lean on a word pointing outside the fact, concentrated in procedure lists under a restart and in procedures that only the heading names. Counting a fact that only drops the heading's scope as correct would give 0.936 against 0.918, a pass: the verdict rests on counting such facts wrong.
- Prompt 14, the one iteration, carried the heading in as what a fact is about and kept the scope, but named the heading's procedure or case as a setting the sentence does not state, as its own example does (*When an order is cancelled, the goods must be sent back within 14 days*), so 105 facts still count against the bar, 100 of them correct.
- Both prompts are out of v0.4.4, and extraction stays at prompt 12. A next try first settles whether a correct fact scoped by its heading counts against the bar.

### The link pass and bridges

The rule: R168's expected-failure property passes and is unmarked, and an unscoped rerun, replayed in process on the frozen bases, writes the stored bridges unchanged.

The property test that held R168 as an expected failure carries no marker in v0.4.4 and passes at 200 and at 1,000 examples. The replay ran each code's bridge pass, unscoped and forced, over read-only copies of both bases (`EXTRACTION_BRIDGES_PER_TOPIC` 12, `EXTRACTION_BRIDGE_PASSAGES` 2), the extractor answering each dealt link with the bridge stored on the same passages, so no model was called.

| | Laws, base / v0.4.4 | Shop, base / v0.4.4 |
|---|---|---|
| Stored bridges (prompt) | 243 (5) | 37 (6) |
| Links dealt | 204 / 204, the same in the same order | 109 / 109, the same in the same order |
| Bridges written | 17 / 17 | 37 / 37 |
| Written bridges differing | none | none, apart from the head |

It passes. The only difference v0.4.4 makes is the `head` each written bridge now records: on the shop base 26 of the 37 name the passage shown first and 11 the second, sibling or term links that the later passage headed. The Laws base's 243 bridges were written by prompt 5 before the bridge pass paired the passages the documents link, so only 17 sit on a link either code deals in the same order, and neither writes the other 226 back; and one stored Laws bridge refused `unsupported_addition` (fact 23175) is validated by both codes, from a heading check that predates this release. Neither comes from v0.4.4.

### Topics

The rule: a fit replayed in process on both frozen bases' passages, without naming (naming is a model call) and with no store write. No language may fail, and topic counts and passage assignments must match the base's except where a fix says why.

Each code's fitter ran with the bases' settings (at most 40 topics, 40 passages per topic, 10 passes, seed 42, 12 terms, weight floor 0.05, `TOPIC_NO_BELOW` 3, `TOPIC_NO_ABOVE` 0.5) over each language's fact-bearing passages. The base code reproduces the stored topics exactly.

| Base, language | Topics, base / v0.4.4 | Passages fitted | Passages placed elsewhere |
|---|---|---|---|
| Laws, German | 9 / 9 | 362 | 1 |
| Laws, English | 8 / 8 | 346 | 1 |
| Shop, German | 5 / 5 | 228 | 1 |
| Shop, English | 5 / 5 | 216 | 2 |

It passes: no language fails, every topic keeps its top terms, and 5 of the 1,150 passages placed take another main topic (the two Laws passages left unplaced stay so on both sides). All 5 come from the reseed of QAB-topics-3: with the reseed taken out, v0.4.4's fit moves none.

### Spend

The v0.4.4 calibration cost USD 0.90, against a plan of about USD 1: the two FIX-R129 extraction runs, 0.59 and 0.31. FIX-R13's run was not made, and every other bar called no model.

## References

- Simone Filice, Guy Horowitz, David Carmel, Zohar Karnin, Liane Lewin-Eytan and Yoelle Maarek. 2025. [*Generating Q&A Benchmarks for RAG Evaluation in Enterprise Settings*](https://aclanthology.org/2025.acl-industry.33/). In *Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics (Volume 6: Industry Track)*, pages 469–484, Vienna, Austria. Association for Computational Linguistics. doi:10.18653/v1/2025.acl-industry.33.
- Chantal Shaib et al. 2024. [*Standardizing the Measurement of Text Diversity: A Tool and a Comparative Analysis of Scores*](https://arxiv.org/abs/2403.00553). arXiv:2403.00553.
