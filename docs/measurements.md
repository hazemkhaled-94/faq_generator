# Measurements

The figures of the measured runs. This is the only place in the repository
that holds run figures. A README that needs one links here.

The first run is of 16 syllabi (2026-09-26 for the corpus, parsing, chunking,
topics, wall clock and spend; the evaluation phase was judged on 2026-10-06 in
a stratified run of its own). Its fact verdicts, accepted pool and release are
that run's output as of 2026-10-06: the same 16 documents and 5,873 written
questions, re-verified under fixed gates with two fact repairs (100 facts
refused again as `unresolved_reference`; 117 facts gained 214 citations). No
model was called for the re-verification. The run used host drains, before
container workers built the dataset. The later runs are rebuilds of the *Laws
of the Game 2026/27* (football rules), German and English, and their figures
stand on their own.

## What a generated benchmark can rank

Findings from two studies, which bound how this project's figures are read.

- van Elburg, van der Putten and Marx, [*Can We Evaluate RAGs with Synthetic
  Data?*](https://arxiv.org/abs/2508.11758) (ECML PKDD 2025 workshops,
  Springer CCIS, doi:10.1007/978-3-032-19102-1_11; read as
  arXiv:2508.11758v2). Four datasets, four or five RAG set-ups each, no
  significance test.
- Rahmani, Craswell, Yilmaz, Mitra and Campos, [*Synthetic Test Collections
  for Retrieval Evaluation*](https://arxiv.org/abs/2405.07767) (SIGIR 2024,
  doi:10.1145/3626772.3657942). 31 retrieval runs, 51 real and 31 generated
  queries.

| Finding | Use |
|---|---|
| Varying only retrieval, a generated benchmark ranked set-ups like the human one (mean Kendall's τ 0.84 on BLEU). With five generators it failed (mean τ −0.35, −1.00 on one dataset) (van Elburg et al., §5.2 to 5.3) | Compare retrievers, chunking and top-k with it. Compare generators with real questions beside it |
| Every system scored higher on generated questions. Context Precision could not rank retrievers (τ 0.08). A fully synthetic collection with LLM judgments overestimated NDCG@10; with human judgments it did not (Rahmani et al., §2.1, §3) | Read absolute scores as optimistic and differences between set-ups |
| Counting only the source passage as relevant ranked systems poorly (τ 0.157). Pooled judgments ranked them well (τ 0.82 human, 0.86 GPT-4) (Rahmani et al., §2.1 to 2.2) | Score retrieval by whether the answer can be got from what was retrieved |
| Agreement was best where generated and real questions matched in length and form (van Elburg et al., §6.1) | `make diversity BY=category` shows how far the categories widen the form |
| A bias towards the generating model is suggested, not tested (van Elburg et al.), and little or none was found on one collection (Rahmani et al., §3) | Judge a chatbot with another model family than the one that wrote the benchmark. The workbook's Summary sheet names the models |

## Every run at a glance

The *Laws of the Game 2026/27*, German and English, through every stage by
successive versions (`azure/gpt-5.4` writing questions, `azure/gpt-4.1`
everything else), each read in full by review agents working from one rubric.
The v0.4.0 column is the v0.3.8 code (reviewed, not released). Readers differ
by about five points. "Usable" is a verdict of good or minor. "Settled" means
unusable released questions were read again by a second reader and, on
disagreement, a third. n/a means not measured. The first two runs are detailed
in [bugs.md](bugs.md). The 16-syllabus run is not in the table.

| | 2026-10-13 (before v0.2.2) | v0.2.2, 2026-10-14 | v0.3.0, 2026-10-16 | v0.4.0, 2026-10-18 | v0.3.12, 2026-10-19 |
|---|---|---|---|---|---|
| Questions | | | | | |
| Written / accepted | 1,476 / 576 | 1,760 / 837 | 1,507 / 871 | 1,550 / 886 | 1,753 / 960 |
| Accepted usable (German / English) | 50% (51% / 50%) | 57% (54% / 60%) | 69.9% (69.5% / 70.3%) | 75.3% (75.0% / 75.6%) | 76.6% (73.5% / 79.8%) |
| Released (German / English) | 238 (187 / 51) | 321 (176 / 145) | 343 (182 / 161) | 318 (165 / 153) | 395 (205 / 190) |
| Released usable, settled | 49% | 52% | 79.0% | 82.7% | 82.3% |
| Answer keys correct / complete | 58% / 45% | 69% / 58% | 80.1% / 72.0% | 87.0% / 73.2% | 87.8% / 74.0% |
| Two-passage questions welded, accepted (released) | 19% of accepted carry a weld tag | 128/270, 47% (104 released) | 33/183, 18.0% (17/91) | 32/144, 22.2% (19/65) | 40/225, 17.8% (23/95) |
| Facts | | | | | |
| Validated facts stated correctly, read | n/a | 78.5% (all) | 86.7% (all 3,180) | 81.8% (560, three readers) | 85.3% (600; German 84.0%, English 86.8%) |
| Bridges | | | | | |
| Bridges validated (written) | none | none | 179 (249) | 140 (228) | 178 (243) |
| Topics and passages | | | | | |
| Cost | | | | | |
| Model spend for the run (USD) | n/a | n/a | 17.93 | 34.32 (two builds; the clean question pass 14.60) | 21.23 |

## The run

| | |
|---|---|
| Corpus | 16 PDF certification syllabi, German and English. All parsed and chunked |
| Models | `azure/gpt-5.4` for extraction, topic labels and questions; `azure/gpt-4.1` for the verifier and judge |
| Wall clock, calls, tokens, cost | 7 h 31 min, 20,218 calls, 30,366,704 in and 1,471,085 out, USD 56.63 |

| Stage | Wall clock | Calls | Cost (USD) |
|---|---|---|---|
| Parsing, chunking | 5.6 min, 1.2 min | n/a | n/a |
| Extraction | 116.2 min | 3,380 | 13.62 |
| Topic modelling | 1.6 min | 74 | 0.21 |
| Question generation | 296.5 min | 14,812 | 40.01 |
| Evaluation phase | 25.5 min | 1,952 | 2.79 |

## Corpus

German: 8 documents, 645 pages, 1,648,644 characters. English: 8 documents,
582 pages, 1,527,068 characters.

## Parsing

Mean confidence 0.944. Lower bound across documents 0.852 to 0.920.

## Chunking

3,080 passages (German 1,499, English 1,581), 192.5 per document (92 to 294),
mean length 1,267 characters (German) and 1,250 (English). 54 passages sit in
a document of the other language (50 English in German documents, 4 the other
way). Block types: `text` 2,022, `list_item` 570, `table` 329,
`document_index` 154 (no fact), 5 others.

## Extraction

12,154 statements written, 8,956 validated (73.7%): `atomic` 7,325 of 9,846,
`summary` 1,037 of 1,154, `outline` 594 of 1,154. 2,240 of 3,080 passages
carry a validated fact (4.09 each, median 4, most 45).

| Refused as | Count | Share of refusals |
|---|---|---|
| `duplicate` | 2,292 | 71.7% |
| `unsupported_addition` | 491 | 15.4% |
| `unresolved_reference` | 232 | 7.3% |
| `asserts_nothing`, `not_atomic`, `copied`, `not_condensed` | 107, 61, 8, 7 | 3.3%, 1.9%, 0.3%, 0.2% |

## Topic modelling

76 topics (37 German, 39 English) with 10 to 99 dominant passages (mean 40.4).
12 passages sit in no topic. The largest topic holds 6.6% of its language
(German) and 5.9% (English). 9 topics went unlabelled.

## Question generation

5,873 questions written, 2,064 accepted (35.1%); 4,186 were first attempts and
1,687 retries. Re-verification rejected 352 of those the run had accepted.

| Gate | Refused | Share of written |
|---|---|---|
| `compound` | 881 | 15.0% |
| `not_recoverable` | 520 | 8.9% |
| `answerable_after_all` | 504 | 8.6% |
| `wrong_type` | 304 | 5.2% |
| `answerable_elsewhere` | 264 | 4.5% |
| `asks_nothing_new` | 231 | 3.9% |
| `answer_incomplete`, `restates_question` | 200, 153 | 3.4%, 2.6% |
| `explanation_unusable`, `duplicate`, `leaks_source` | 135, 131, 120 | 2.3%, 2.2%, 2.0% |
| Eight more gates (`off_thread` 76, `unanchored` 71, `off_topic` 69, `wrong_form` 49, `source_changed` 41, `answer_too_long` 31, `malformed` 17, `answer_too_short` 12) | 366 | 0.2% to 1.3% each |

### What was accepted

Accepted by kind: `reason` 355, `condition` 312, `factoid` 289, `definition`
249, `application` 175, `procedure` 165, `enumeration` 147, `consequence` 130,
`implication` 117, `aggregation` 91, `comparison` 34 (`entity` and `temporal`
have weight 0).

| | |
|---|---|
| Language | German 1,116, English 948 |
| Answerable, unanswerable | 1,605 (77.8%), 459 (22.2%) |
| Scope | `single_passage` 1,308, `multi_passage` 756; `single_document` 1,447, `cross_document` 617; `single_topic` 1,710, `multi_topic` 354 |
| Difficulty | `easy` 1,111 (53.8%), `hard` 529 (25.6%), `medium` 424 (20.5%) |
| Answer length (median, mean, range) | `explanation` 127, 141, 25 to 594 (958 questions); `value` 29.5, 33, 1 to 80 (344); `list` 100, 109, 9 to 291 (303) |
| Follow-up acceptance by turn | 36.3% (root, 1,773 of 4,879), 30.4%, 26.4% |

## The balanced release

1,015 questions drawn from the 2,064 accepted (49.2%). The draw aimed at 1,035
places.

| Held at | Result |
|---|---|
| Kind | `condition`, `reason` 101; `application`, `definition`, `factoid`, `implication`, `procedure` 100; `consequence`, `enumeration` 99; `aggregation` 91 (10 short of 101); `comparison` 24 (quota 25, within tolerance) |
| Difficulty | `easy` 345, `medium` 325 (20 short), `hard` 345 |
| Unanswerable | 103, the ceiling of 10% of the places |
| Category | Not held to a quota. None here: every question predates writer prompt version 17 |

Every medium root was drawn. The 99 medium questions left over are follow-ups,
which the draw takes only with their root.

## Coverage

| | |
|---|---|
| Passages a validated fact rests on | 2,240 of 3,080 (72.7%) |
| Passages an accepted question rests on | 1,463 (65.3% of askable, 47.5% of all) |
| Facts an accepted question cites | 2,842 of 8,956 (31.7%) |

## Confidence

How close a row came to the verdict that would have refused it. Validated
facts: mean 0.190 (8,955 rows). Accepted questions: mean 0.228 (2,064 rows).

## Model latency

Per call (median, p95, slowest): extraction 1.6, 2.8, 10.0 s; topics 0.8, 1.0,
1.3 s; questions 0.8, 2.4, 12.6 s; evaluation 0.7, 1.0, 2.2 s.
`LLM_TIMEOUT_SECONDS` is sized against the slowest.

## Reproducing this page

This run cannot be reproduced under the current rules: it ran every stage on
the host against hosted models, while container workers now build the dataset
and each host drain refuses while its stage's worker runs. The evaluation
phase ran as `assess-stratified-2026-10-06`, and its figures count only
complete verdicts:

```sql
SELECT a.* FROM assessments a
WHERE a.run_id = 'assess-stratified-2026-10-06'
  AND (SELECT count(*) FROM assessment_metrics m WHERE m.assessment_id = a.id)
      >= a.metrics_due;
```

Wall clock comes from the run's logs in `./logs`, the counts from the tables.


## The evaluation phase

`azure/gpt-4.1` judges a sample of facts and questions, and every topic, and
changes no verdict.

One stratified run (`ASSESSMENT_STRATIFY` set): 200 of each kind drawn,
questions evenly over language and question type, facts over language. 8 had
been judged before, so 198 facts and 194 questions were enrolled; one question
verdict was stored on too few metrics and is left out. All 76 topics were
judged on 2026-09-26.

| Artefact | Judged | Approved | Refused |
|---|---|---|---|
| `fact` (100 German, 98 English; 140 validated, 58 refused) | 198 | 180 | 18 |
| `question` (92 German, 101 English; 85 accepted, 108 rejected) | 193 | 141 | 52 |
| `topic` | 76 | 56 | 20 |

| Metric | Judgements | Mean score | Approved |
|---|---|---|---|
| `toxicity` | 391 | 0.000 | 391 |
| `relevance` | 391 | 0.967 | 378 |
| `hallucination` (scored to minimise) | 391 | 0.100 | 352 |
| `conciseness` | 193 | 0.964 | 186 |
| `qa_correctness` | 193 | 0.834 | 161 |
| `refusal` | 193 | 0.041 | 185 |
| `relevance`, topics | 76 | 0.829 | 63 |
| `summarization`, topics | 76 | 0.803 | 61 |

### Where the judge and the checker disagree

Judge approval of what the pipeline kept against what it refused
(two-proportion z-test, Fisher's exact test beside it):

| | Kept | Refused | p, z-test | p, Fisher |
|---|---|---|---|---|
| Questions | 57 of 85 (67%) | 84 of 108 (78%) | 0.096 | 0.105 |
| Facts | 132 of 140 (94%) | 48 of 58 (83%) | 0.010 | 0.015 |

At this size the judge does not tell accepted from rejected questions, and
approves validated facts more often than refused ones. The disagreeing pairs
are the queue for a person.

### The paper's judge

From template version 3, a question that opens its thread is also scored by
the DataMorgana paper's judge (Filice et al., [*Generating Q&A Benchmarks for
RAG Evaluation in Enterprise
Settings*](https://aclanthology.org/2025.acl-industry.33/), ACL 2025 Industry
Track, Appendix D), in the paper's words with its six examples. One call over
at most four cited passages scores fluency, clarity, conciseness, relevance,
consistency and answerability from 1 to 3. Each is stored as `rubric_fluency`
to `rubric_answerability` with the score (s − 1) / 2. The paper's normalised
mean equals the per-language mean of the stored scores:

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

### The paper's judge against the review

Held against the labelled v0.3.0 review: 350 answerable root questions (175
accepted, 175 rejected, half per language), judged by `azure/gpt-4.1` for USD
1.26.

| | German | English |
|---|---|---|
| Spearman's rho, mean score against the reviewers' verdict | 0.385 | 0.295 |
| Kappa, answerability below 3 against the "breaks" signal | 0.200 | 0.288 |
| Kappa, question relevance's `unrelated` against the same signal | 0.191 | 0.256 |
| Questions called `unrelated` | 3 | 3 |
| Share the judge approves (every score 3), share reviewers found usable | 90%, 62% | 90%, 69% |
| Kappa, approval against "usable" | 0.239 | 0.212 |

The rule, set before the run: a question's `relevance` goes if answerability
agrees with the reviewers at least as well and the mean correlates with their
verdict, in both languages. Both held, so template version 4 does not ask it.

### The judge's verdict as a correction (prediction-powered inference)

ARES (Saad-Falcon et al., [*ARES: An Automated Evaluation Framework for
Retrieval-Augmented Generation
Systems*](https://aclanthology.org/2024.naacl-long.20/), NAACL 2024) corrects
a judge's figures with a few human labels by prediction-powered inference
(Angelopoulos et al., [*Prediction-powered
inference*](https://doi.org/10.1126/science.adi6000), Science 2023). `make
diversity LABELS=` does the same, with the weight tuned as in PPI++
(Angelopoulos, Duchi and Zrnic, [*PPI++*](https://arxiv.org/abs/2311.01453),
2023). On the 175 accepted rows a floor reads, 500 draws of 60 labelled rows
give:

| Label | Share | Correlation with the judge's approval | Mean weight | Half-width, corrected over labels only |
|---|---|---|---|---|
| Key correct | 0.806 | 0.26 | 0.24 | 0.971 |
| Key complete | 0.714 | 0.12 | 0.12 | 0.991 |
| Invalid | 0.051 | −0.02 | −0.01 | 0.995 |
| Usable | 0.766 | 0.26 | 0.26 | 0.971 |

The judge approves 91% of these rows, so the correction narrows the intervals
by under 3%. With this judge, a floor is read on the labels themselves.

## Unanswerable kinds (v0.5.0)

UAEval4RAG (Peng et al., [*Unanswerability Evaluation for Retrieval Augmented
Generation*](https://aclanthology.org/2025.acl-long.415/), ACL 2025) writes
unanswerable questions of several kinds. v0.5.0 can deal four to unanswerable
slots: out-of-corpus (the perturbation), false presupposition, underspecified
and nonsensical. Link U, run on 2026-10-22, measured them on copies of both
frozen calibration bases (the *Laws of the Game* and the EU consumer pages,
German and English), every slot unanswerable, writer `azure/gpt-5.4`, other
roles `azure/gpt-4.1`, USD 18.00 in all.

Arms: base (v0.4.5 code, 4 slots a topic); out-of-corpus and a first try at
the others (16 slots a topic, four kinds at even odds); the other three again
on fixed code (false presupposition at half the slots). 60 kept rows of each
kind and of the base were drawn evenly over corpus and language, shuffled, and
labelled blind by three labellers. A second pass labelled conformance on form.

| | Kept of drafts | Sound | Answered after all | Invalid | Conforms | Verdict |
|---|---|---|---|---|---|---|
| base (v0.4.5) | 80 of 157 (51%) | 0.667 | 20 | 5 | n/a | n/a |
| out-of-corpus | 88 of 138 (64%) | 0.683 | 19 | 1 | 0.95 | passes |
| false presupposition | 106 of 338 (31%) | 0.850 | 0 | 0 | 0.97 | misses one bar |
| nonsensical | 99 of 127 (78%) | 0.833 | 10 | 0 | 0.78 | misses conformance |
| underspecified | 92 of 123 (75%) | 0.367 | 38 | 2 | 0.35 | fails |

"Sound" means the corpus leaves the question unanswered (base, out-of-corpus,
nonsensical), a passage says the premise is false and none says it is true
(false presupposition), or the question has two or more readings the material
answers differently (underspecified). Bars, set before the run: sound no more
than 0.10 below the base; answered after all and invalid at most 2 above the
base; conformance at least 0.80; for false presupposition at most 2 rows of 60
whose premise the corpus supports somewhere; for underspecified at least 0.80
sound.

Out-of-corpus passes every bar, so the default deals unanswerable slots
out-of-corpus alone. The other three are opt-in. False presupposition fails
because 5 of 60 take for granted something a passage elsewhere allows (bar 2).
Nonsensical writes coherent questions in 13 of 60, one row short.
Underspecified mostly writes plain answerable questions, because the writer is
dealt facts with no cases to choose between. Writer-prompt fixes made after
link U were not re-calibrated, so these figures describe the prompts before
them.

The base arm falls short of its sanity bar of 0.70 sound, likely because a
labelling rule counted a standard such as "reasonable time" as settling a
how-long question. The comparisons stand. False presupposition was refused as
the wrong kind 158 times and as answered after all 47 times; underspecified as
the wrong kind 20 times. Case-folding the question brought one more answering
passage into the probe's 20 nearest (English 1, German 0), under the rule of
at least 2 set before the run, so the probe is unchanged (FIX-R55).


## The v0.3.0 rebuild of 2026-10-16

The *Laws of the Game 2026/27* (football rules), one PDF in German (139 pages)
and its English translation (131 pages), through every stage by v0.3.0. Not
read by hand; [bugs.md](bugs.md#after-the-fixes) sets its figures beside the
v0.2.2 rebuild. Writer `azure/gpt-5.4`; extractor, digest, topic labeller,
verifier and phrasing judge `azure/gpt-4.1`. 2 h 26 min, 5,846 calls, USD
17.93 (USD 20.93 with two discarded runs: a first extraction and a first
release draw at `aggregation` weight 4).

| Stage | Wall clock | Calls | Cost (USD) |
|---|---|---|---|
| Parsing, chunking | 1.3 min, 0.6 min | n/a | n/a |
| Extraction | 32.1 min | 899 | 2.70 |
| Topic modelling | 0.4 min | 2 | 0.01 |
| Bridge facts | 5.3 min | 204 | 0.44 |
| Question generation | 99.9 min | 4,347 | 14.27 |
| Release | 5.9 min | 394 | 0.50 |

### Passages, facts and topics

| | German | English |
|---|---|---|
| Passages, carrying a validated fact | 417, 361 | 403, 339 |
| Facts (bridges aside), validated | 1,961, 1,692 | 1,758, 1,488 |
| Refused per 1,000 facts: `not_atomic`, `unresolved_reference`, `unsupported_addition`, `duplicate` | 32.1, 30.1, 9.2, 57.1 | 61.4, 21.0, 18.2, 46.6 |
| Bridge facts written, validated | 134, 106 | 115, 73 |
| Topics | 9 | 8 |

The fit reads only passages carrying a validated fact; the 120 others are in
no topic.

### Questions

| | German | English |
|---|---|---|
| Written, accepted | 780, 463 (59%) | 727, 408 (56%) |
| Accepted with no answer in the material | 133 | 114 |
| Accepted citing two or more passages | 102 (22%) | 81 (20%) |

Most common refusals (German, English): `asks_nothing_new` 59, 55;
`not_recoverable` 54, 51; `answerable_elsewhere` 31, 43; `answer_incomplete`
27, 34; `wrong_type` 37, 29; `answerable_after_all` 25, 31. The writer
declined 36 slots and 10 follow-up turns. No topic failed.

### The release

343 questions drawn from 871 accepted (39%): German 182, English 161; `easy`
226, `medium` 94, `hard` 23; `condition` 57; `application`, `definition`,
`factoid`, `reason` 34; `consequence`, `enumeration`, `implication`,
`procedure` 33; `aggregation`, `comparison` 9; unanswerable 0
(`QUESTIONS_RELEASE_UNANSWERABLE=0`). Eight kinds came 2 or 3 short of their
quota because the draw takes a thread whole: `condition` follow-ups took 21
places over its quota. The verifier read 12 of 394 pairs as twins. The first
draw weighed `aggregation` 4 with only 13 in the pool, capping the release at
133, so v0.3.0 weighs it 1 like `comparison`.

## The v0.4.0 rebuild of 2026-10-18

The same two PDFs through the v0.3.8 code with every stored question deleted
before one questions pass. Not released. Every accepted and rejected question,
refused fact, 720 validated facts, bridge and topic was read.

Its figures are the v0.4.0 column of [Every run at a
glance](#every-run-at-a-glance). Released usable 82.7% (79.0% in v0.3.0), keys
correct 87.0% (80.1%), two-passage questions welded 22.2% (18.0%), released
318 (343).

## The v0.3.12 rebuild of 2026-10-19

The same two PDFs through the v0.3.12 code (v0.3.9 to v0.3.12), from a fresh
extraction, read as above with blind same-reader samples beside v0.3.0's.

Its figures are the v0.3.12 column of [Every run at a
glance](#every-run-at-a-glance). Released two-passage questions welded: 23 of
95 (24.2%), against 17 of 91 and 19 of 65.

- v0.3.9 offers a bridge on its own. Blind, accepted bridge-plus-fact
  questions fell from 54 (7 welded) to 7 (none). A bridge alone welds at 9% in
  both builds.
- The released weld rate rose while the accepted rate fell because of the
  draw. Over 100 hash salts both pools have the same expected released weld
  rate (21.8%). A blind same-reader test reads 13.2% against 20.0% (z = 1.25).
- Wrong `not_atomic` refusals fell from 82% to 40% (81 of 203). The repair
  call wrote 390 pieces, 262 validated, as correct as other facts (41 of 49
  against 471 of 551).
- Topics, the most cohesive of eight seeded draws, read coherent 0 / 14 / 3
  (yes / partly / no) against 0 / 11 / 5 for v0.4.0. Verifier prompt 6 lowered
  the share of kept unanswerables the corpus answers.
- Not fixed in this run: the release-size bisection shipped fewer than 200
  questions for 43 of 100 salts of this pool (the stored hash fills to 395;
  scanning downwards removes all 43 at an unchanged weld rate), and the
  per-passage cap refused 65 facts as `over_cap`, 78% wrongly.

Model spend: USD 21.23.

## The v0.3.13 to v0.4.0 cycle: replays and calibrations

No rebuild was made on v0.3.13 or later code. Every figure here is an offline
replay of stored data or a calibration of one model reading on labelled rows.
Until the first full build of this code, the release figures (usable share,
weld rate, release size) are the v0.3.12 rebuild's. The calibrations cost USD
1.60.

### The offline scoreboard, v0.3.12 against v0.4.0

The scoreboard replays the stored rows of the v0.3.0 rebuild under a
checkout's code, reading stored model verdicts and calling no model.

| Row | v0.3.0 as stored | v0.3.12 code | v0.4.0 code |
|---|---|---|---|
| Released invalid (draw replay at stored size) | 10 | 8 | 9 |
| Released welded of two-passage | 17/91 | 19/91 | 21/91 |
| Release German share (pool) | 0.531 (0.532) | 0.531 (0.531) | 0.523 (0.528) |
| Weld rate, accepted two-passage | 33/183 (0.180) | 32/181 (0.177) | 34/184 (0.185) |
| Answerable keys correct / complete | 0.801 / 0.720 | 0.8111 / 0.7264 | 0.8111 / 0.7264 |
| Validated facts stated correctly | 2,758/3,180 (0.8673) | 2,772/3,195 (0.8676) | 2,776/3,199 (0.8678) |
| Accepted pool replayed (usable share) | 871 | 859 (0.7113) | 879 (0.7088) |
| `answer_incomplete` refusals, German / English | n/a | 26 / 34 | 18 / 22 |

The pool grew by 20 questions and the weld rate crossed its floor because
`answer_incomplete` refuses a list key only when the recovery names an item
the key and question lack (v0.3.19). Of the 20 refusals removed, 15 were
wrong. The needs_both check below answers the weld rows.

### The needs_both check (v0.3.35): calibration on labelled rows

Verifier prompt `stated` 1 lists the parts of a needs_both question's answer
and quotes every cited passage that states each. The question stays
two-passage only when each cited passage holds a part no other holds. "Honest"
means a needs_both question readers judged to need both passages; "padded" one
a single passage answers whole.

| Step | Rows | Honest kept | Padded relabelled | Gold compounds relabelled | Result |
|---|---|---|---|---|---|
| 1, first iteration, v0.3.12 | 76 | 26/31 | 38/45 | 4/8 (bar at most 2) | fails; stopped (USD 0.19) |
| 1, second iteration, replayed | 76 | 30/31 | 33/45 | 0/8 | passes |
| 2, v0.3.0 holdout | 53 | 23/23 | 25/30 | 0/7 | passes (USD 0.14) |
| Gold rest, v0.3.12 | 208 | 29/36 | 76/107 (by citation 36/107) | 0/18 | passes lenient bar |
| Gold rest, v0.3.0 | | 20/20 | 68/97 (by citation 60/97) | 1/30 (row 4392) | fails by one row |

A padded question that cites a bridge keeps both passages, so the stored share
is lower than the share the reading decides. The check adds one verifier call
per accepted answerable needs_both question citing two passages (about USD
0.45 to 0.5 per build). Calibration spend USD 0.79.

### Bridges, the release draw, links and other replays

| Change | Figure | Release |
|---|---|---|
| Bridge checks read the heading trail; a bridge writing a cited passage's numbered heading is refused | 243 bridges: validated 178 to 184, judged correct 34 to 37 | v0.3.15 |
| Pairs follow the documents' own links across topics | 204 pairs, 47% across topics; labelled pairs 29% correct against 18% | v0.3.16 |
| Bridge prompt 6 with those pairs | Blind: 42% correct against 12%; wrong or unsupported 13% against 15% | v0.3.16 |
| Bridge prompts 7 and 8 and a bridge test at extraction (not shipped) | Prompt 8: 22% of correct parallel and contrast bridges refused as spread (bar 15%), 12/16 drift controls repeated (bar 13). The test refused 5 of 16 correct bridges (bar about 2) | deferred |
| Sizes scanned down instead of bisected, 100 salts | Draws under 200 rows 43 to 0; +139 rows on average; weld rate +0.5 points (interval −0.6 to +1.5) | v0.3.27 |
| Scan upper bound counts unanswerable rows up to the ceiling | 4,578-row pool: 1,653 draws and 59.7 s to 1 draw and 0.1 s, same ids | v0.4.0 |
| Compound and unanswerable samples never rest on a bridge | Compound slots on a bridge 5 to 0; unanswerable slots dealt a bridge 67 to 0 | v0.3.30 |
| Re-parse and re-chunk of the 30 football PDFs | One table row per language changes; footnotes and lead-ins change 0 passages; 5 image-only pages named, all real | v0.3.31, v0.3.32, v0.4.0 |
| Compound questions, 48 pairs built outside the deal | 28 accepted, all compound, none a false join; 21 usable (75% against 80% asked); 19 keys right (68% against 75%) | v0.3.22, v0.3.26 |
| Unanswerable questions | Kept-answered share on labelled drafts 0.342 to 0.253 (v0.3.17); settles prompt 7 flagged 4 of 20 answered drafts (not shipped) | v0.3.17 |


## The DataMorgana releases: how varied the questions are, and the categories (v0.4.1 and v0.4.2)

v0.4.1 and v0.4.2 added the diversity scores and question categories of the
DataMorgana paper (Filice et al., see [References](#references)). The figures
are the v0.3.12 release (325 accepted answerable root questions: 166 German,
159 English) and four calibration links. Tags come from `de_core_news_md`
3.8.0 and `en_core_web_md` 3.8.0, vectors from
`intfloat/multilingual-e5-large`.

### Diversity of the questions

`make diversity` reads a workbook from `make questions-export` and calls no
model. NGD is n-gram diversity (higher is more varied). SR is self-repetition,
word-CR and PoS-CR the compression ratios of words and part-of-speech tags, HS
the mean cosine between questions (lower is more varied for all four). The
metrics move with set size, so two sets compare only at one size.

| Language | n | NGD | SR | word-CR | PoS-CR | HS |
|---|---|---|---|---|---|---|
| de | 166 | 3.090 | 0.157 | 3.020 | 8.492 | 0.819 |
| en | 159 | 2.905 | 0.352 | 2.934 | 7.973 | 0.804 |

English questions repeat more (35% share a four-word run with another
question, against 16%). HS cosines sit at 0.80 to 0.82 for any two texts in a
language, so HS compares only with a set embedded with the same model. Against
the pool's 586 accepted answerable root questions (`AGAINST=`, fifty draws of
80%, Welch's t-test), no score moves by more than 0.1.

### The categories, calibrated on four links

Links ran the v0.4.2 code on copies of the *Laws of the Game* and EU
consumer-page databases, German and English, writer `azure/gpt-5.4`, other
roles `azure/gpt-4.1`, USD 8 each. Link 046 (Phrasing) and 049 (Phrasing and
Premise) ran at the planned N (USD 6.71, 6.80). Link 0410 (Linguistic
variation, User expertise) and 0411 (the two search queries) ran every topic
at a cut N (USD 5.92, 5.82). Link 040 is the v0.4.0 baseline on link 046's
topics (USD 6.64). 30 accepted answerable root questions per category were
labelled. Floors, set before the run: keys correct at least 0.80, complete at
least 0.72, and invalid rows failing a category only at 3 or more in 30 and
more than its sibling's.

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
| long-search-query | 0411 | 0.933 | 0.833 | 2 of 30 | 0.667 | passes, a third not queries; opt-in |
| no categories (v0.4.0) | 040 | 0.883 | 0.800 | 1 of 60 | 0.667 | baseline |

A categorization left with one category is dropped whole, so
similar-to-document and novice stay opt-in with the four that failed.

- Phrasing: German concise questions were accepted least (51.5% against
  verbose 67.9%), through `leaks_source` (10 of 103 rows). Sets are more
  varied in 19 of 20 comparisons (p at most 0.001). 14 of 30 concise questions
  do not stand alone or are ambiguous, against 2 of 30 verbose.
- Premise: with-premise acceptance 68.7% against direct's 57.1% (German),
  65.3% against 62.5% (English). 33 of 130 open with a scene label.
- Word-gate trigger fired in English (distant +12.4 points, novice +8.7), all
  on the EU pages. Meaning drift touched 7 of 60 rows.
- Search queries: none of 90 ends in a question mark; 88 of 90 keep their
  bounds. `unanchored` refused 10 of 84 German query rows against 7 of 95
  natural ones.

The calibration cost USD 26.51 with the judge's agreement run, and the
baseline link USD 6.64 more. Not measured: the paper's Figure 1 at size 200,
and the paper's judge per category and kind.

## The v0.4.3 calibration

v0.4.3 changes how questions are planned, written, accepted and released (see
[the finalize review](bugs.md#found-by-the-finalize-review-of-2026-10-21)).
Each pass rule was written before anything was measured.

### The floor rule

An arm is one set of accepted answerable root questions from one link under
one setting. A category is compared with its siblings in the same run; a code
fix with the base code on a copy of the same frozen base, same topics,
`QUESTIONS_PER_TOPIC` and seed.

| Rule | Value |
|---|---|
| Sample | 60 rows per arm, drawn evenly over languages and corpora; under 40 rows is "not measured" |
| Pass | Keys correct and complete at least the baseline's share minus 0.10; invalid per 60 at most the baseline's plus 2; conformance at least 0.80 for a category |
| Error rates (binomial simulation at 0.85 correct) | Equal arms pass keys correct 95%; an arm 0.10 worse passes 52 to 54%, 0.20 worse 11% |
| Sanity | A baseline under 0.70 correct or 0.62 complete flags the link; re-label once by a new labeller |
| Gate change replayed on stored rows | Every changed verdict labelled, up to 60. A loosening passes when newly admitted rows' usable share is at least the accepted baseline's minus 0.10 with at most 2 invalid per 60; a tightening when at most 35% of newly refused rows are usable |

### Scoreboard, release draw and read fields

| Row | v0.4.2 | v0.4.3 stack |
|---|---|---|
| Validated facts stated correctly | 2,776 of 3,199 (0.8678) | unchanged |
| Accepted pool replayed (usable share) | 879 (0.7088) | 878 (0.7084) |
| Answerable keys correct / complete | 0.8111 / 0.7264 | 0.8108 / 0.7259 |
| Weld rate, accepted two-passage | 34/184 (0.185) | 34/183 (0.186) |

The release draw of base and stack on the labelled v0.3.0 snapshot, 100 paired
hash salts (bars: welded share at most 0.005 above the base, invalid per 100
at most 0.5 above):

| | Base (v0.4.2) | v0.4.3 stack |
|---|---|---|
| Mean release size, rows | 371.1 | 453.3 (larger on every salt, +14 to +139) |
| Mean two-passage rows released | 95.8 | 124.2 |
| Welded share of released two-passage rows | 22.72% | 22.77% (interval −0.32 to +0.47) |
| Invalid rows per 100 released | 3.30 | 3.03 (interval −0.35 to −0.18) |
| Usable share of the release | 0.786 | 0.781 |

Two fields of the round trip's read on 300 labelled rows (35 welds, 22
circular reason keys, 183 usable), `azure/gpt-4.1`. Bars: each field refuses
at least half of its labelled rows, and at most 35% of what it refuses is
usable.

| Verifier version | Field | Refused | Caught | Usable among refused | Verdict |
|---|---|---|---|---|---|
| 10 | `asks_one` | 3 | 2 of 35 | 1 of 3 | fails recall |
| 10 | `reason_given` | 20 | 9 of 22 | 7 of 20 (0.35) | fails recall |
| 11 | `asks_one` | 16 | 8 of 35 | 8 of 16 | fails both |
| 11 | `reason_given` | 11 | 6 of 22 | 1 of 11 | fails recall |
| 12 (`asks_one` removed) | `reason_given` | 19 | 11 of 22 (0.500) | 5 of 19 (0.26) | passes |

Version 12 sits exactly at the bar. `asks_one` was withdrawn (see [the
withdrawn items](bugs.md#tried-in-v043-and-withdrawn-with-the-reason)).

### The title rule on stored rows

A question naming its page by a title that is also its subject was refused
`leaks_source` by a free rule. Replayed read-only on the ten link databases:
88 stored `leaks_source` rows, 79 refused by the free title rule; the v0.4.3
code admits 78 (1 remains, so the count bar passes). Of 60 admitted rows
labelled, 27 were usable and 16 invalid. After the later gates (USD 0.21), 31
non-compound rows remained: 21 usable (0.68, against 0.50 in Link Q's base
arm) and 6 invalid (11.6 per 60, limit 2). It fails the loosening bar and was
withdrawn.

### Link Q

The base code (v0.4.2) against v0.4.3 with the default categorizations on 10
topics (Laws 80 to 82 and 89 to 91 at `QUESTIONS_PER_TOPIC` 16; EU pages 7, 8,
2 and 3 at 26). USD 3.35 and 3.47.

| Bar | Base | v0.4.3 | Verdict |
|---|---|---|---|
| Keys correct (60) | 59 | 59 | passes (bound 0.88) |
| Keys complete, invalid per 60 | 53, 3 | 51, 4 | passes (bounds 0.78, 5) |
| Read refusals on reason rows: usable | 0 of 6 | 3 of 28 (22 circular) | passes (at most 0.35) |
| Acceptance, German / English | 52.2% / 52.6% | 47.7% / 56.3% | passes (within 10 points) |
| Verbose with-premise rows opening on a scene label | 6 of 17 | 4 of 17 | fails (at most 0.10) |
| With-premise conformance | n/a | 13 of 17 (0.76) | fails (at least 0.80) |

After the premise rework a premise-only run (USD 1.65, 36 rows, under the
40-row minimum) had 0 scene labels and conformance 34 of 36.

### Link C

The v0.4.3 code with three categorizations at calibration probabilities
(Phrasing with both search queries at 0.35, Linguistic variation and User
expertise at 0.5), all 27 topics at `QUESTIONS_PER_TOPIC` 22, USD 10.40 (plus
USD 1.23 for a stopped first run).

| Category | Compared with | Rows | Keys correct | Complete | Invalid per 60 | Conformance | Verdict |
|---|---|---|---|---|---|---|---|
| distant-from-document | similar | 60 vs 60 | 58 vs 57 | 57 vs 54 | 4 vs 11 | 48 of 60 | passes |
| expert | novice | 58 vs 60 | 51 vs 57 | 53 vs 54 | 13.4 vs 11 | 34 of 58 | fails |
| long-search-query | concise, verbose | 36 | 32 | n/a | 23.3 | 31 of 36 | not measured |
| short-search-query | concise, verbose | 19 | 19 | 19 | n/a | 15 of 19 | fails supply |

Linguistic variation joins the default. User expertise stays opt-in. The short
query is accepted on 29 to 31% of the slots it may take against 82 to 86% for
natural phrasing. The v0.4.3 calibrations cost USD 22.4.

## The v0.4.4 bars

v0.4.4 changes how documents are read (see [the finalize
review](bugs.md#fixed-in-v044-parsing-and-chunking)). Bars were written first.
All but one are replays on three real documents or the two frozen calibration
bases (`qa_cal_laws`, `qa_cal_shop`); the extraction run calls a model.

| Bar | Result |
|---|---|
| Parsing and chunking: a football PDF and two EU consumer pages parsed and chunked with base and fix code; every changed passage labelled; pass when none loses text or mixes languages and at most 2 are worse | Passes with nothing to label: byte-identical converted documents and passages (2, 7 and 16 passages). No fix has an instance in the three documents, so each rests on its red tests. With the QA pass's fixes the bar ran on five documents; the first build failed (88 passages changed, 28 of 60 labelled worse, bar 2) and was fixed |
| Fact validation: the scoreboard facts, v0.4.3 against v0.4.4, changed verdicts labelled; a tightening passes when at most 35% of newly refused facts are correct | 3,403 to 3,400 of 3,445 stored verdicts reproduced; validated 2,776 of 3,199 to 2,775 of 3,196 (0.8683); 0 newly validated, 3 newly refused (German *solche*, *folgenden*, *solcher*), all vague, refusals right; 0 of 3 correct, passes |
| QA-pass sentence-end fixes: 22 of 820 passages re-cut | 2 facts newly validated: one a figure ending a sentence (correct, kept), one narrowed (0 of 1 correct, withdrawn) |
| FIX-R13, a verbless definition | Not run: the rule was withdrawn after two reviews |
| FIX-R129, extraction prompts 13 and 14: 60 passages under a heading, extracted into copies of the bases with `azure/gpt-5.4` (digests `azure/gpt-4.1`), labelled blind, pooled; heading-as-situation facts at most 59.5 and correct share at least 0.817 | See below |
| Link pass: R168's expected-failure property unmarked and passes; unscoped rerun on the frozen bases writes the stored bridges unchanged | Passes. Links dealt 204/204 (Laws) and 109/109 (shop) in the same order; bridges written 17/17 and 37/37; the only change is each bridge's recorded `head` |
| Topics: fit replayed on both bases, no naming | Passes. Topic counts 9/9, 8/8 (Laws) and 5/5, 5/5 (shop); 5 of 1,150 passages take another main topic, all from the QAB-topics-3 reseed |

| | Prompt 12 | Prompt 13 | Prompt 14 |
|---|---|---|---|
| Validated facts labelled | 266 | 256 | 264 |
| Correct | 244 (0.917) | 203 (0.793) | 238 (0.902) |
| Heading written as a situation | 119 | 43 | 105 |
| Facts dropping a scope the heading gives | 5 | 32 | 7 |
| Verdict | | fails correct bar | fails heading bar |

Both prompts are out and extraction stays at prompt 12. The calibration cost
USD 0.90.

## References

- Simone Filice, Guy Horowitz, David Carmel, Zohar Karnin, Liane Lewin-Eytan
  and Yoelle Maarek. 2025. [*Generating Q&A Benchmarks for RAG Evaluation in
  Enterprise Settings*](https://aclanthology.org/2025.acl-industry.33/). In
  *Proceedings of the 63rd Annual Meeting of the Association for Computational
  Linguistics (Volume 6: Industry Track)*, pages 469–484, Vienna, Austria.
  doi:10.18653/v1/2025.acl-industry.33.
- Chantal Shaib et al. 2024. [*Standardizing the Measurement of Text
  Diversity: A Tool and a Comparative Analysis of
  Scores*](https://arxiv.org/abs/2403.00553). arXiv:2403.00553.
