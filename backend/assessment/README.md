# Assessment

The assessment phase is an LLM judge over facts, topics and answerable
questions (a sample of each kind, or all of them). It runs after the whole
pipeline, never during it, and records an opinion beside the checker's
verdict. It decides nothing.

```bash
make assess-enrol            # write the rows a start would judge, and count them; not a dry run
make assess-start && make assess
make assess-status
```

The phase is off unless `ASSESSMENT_ENABLED` is true in `.env`. While off,
`assess-worker` waits instead of exiting, and starts claiming within
`WORKER_POLL_SECONDS` of the flag being switched on from the Assessment page.
A change to `.env` reaches the worker with `make up`.

## Not a gate

`facts.validated` belongs to the checker and `questions.status` to the gates.
This phase writes neither. It writes `assessments.approved`, which no stage
reads. A judge was near chance on German phrasing judgements, so a phase
that rejected rows would discard good German questions.

The useful output is a disagreement: an artefact the pipeline kept (a question
a person accepted over a gate counts as kept) and the judge refused. The
Assessment page marks them, and `make review-push-questions IDS=` sends them
to a reviewer.

## What is judged

The phase judges the three kinds [`review/`](../../review/README.md) puts in
front of a person.

| Artefact | Judged on | Asked | Calls |
|---|---|---|---|
| `fact` | `hallucination` | Do the cited sentences support the statement? | 3 |
| | `relevance` | Are those sentences about the statement's subject? | |
| | `toxicity` | Did the pipeline write something offensive? | |
| `topic` | `summarization` | Is the label a good short name for these terms? | 2 |
| | `relevance` | Are these terms a subject, or the document's furniture? | |
| `question` | `hallucination` | Do the facts support the answer? | 6 |
| | `qa_correctness` | Does the answer answer the question asked? | |
| | `refusal` | Is the answer an answer, or a refusal written as one? | |
| | `conciseness` | Does the answer give what was asked and stop? | |
| | `toxicity` | Did the pipeline write something offensive? | |
| | `rubric_fluency` to `rubric_answerability` | The paper's six scores, from one call. Root questions only | |

An artefact is approved only when every metric approves. Of the paper's six
scores, only a 3 approves.

`refusal` is the one metric no gate checks: an answerable question whose
stored answer is "the document does not specify" passes every gate.
`toxicity` covers what the pipeline wrote, not what the corpus is about.
Unanswerable questions are not judged.

## The paper's judge

The DataMorgana paper ([Filice et al., 2025](#references), Appendix D) scores
each question from 1 to 3 on six dimensions with one prompt, the `Rubric`
template in [`templates.py`](templates.py). The scores are stored as
`rubric_fluency`, `rubric_clarity`, `rubric_conciseness`, `rubric_relevance`,
`rubric_consistency` and `rubric_answerability`, so they can be read beside
the paper's Table 3.

The template keeps the paper's definitions, guidelines and six examples. One
call returns all six scores, each stored as its own row with an empty
explanation. The judge reads the passages the question's facts cite, each
once, in reading order, at most four. A score s is stored as its label and as
(s - 1) / 2, so the mean of a `rubric_` metric over a set is the paper's
normalised figure.

Only a question that opens its thread is asked, because a follow-up depends
on a turn the rubric is not shown. A root question gets eleven metrics from
six calls, a follow-up five from five. A question is not also asked
`relevance`, which `rubric_answerability` replaces. A fact and a topic are
still asked it.

## Names and prompts

The metric names, labels, scores and optimisation direction come from
`arize-phoenix-evals`, which is not a dependency. They are written out in
[`templates.py`](templates.py), so an annotation sits in the same Phoenix view
as one from any tool built on that package. Each judgement is one call through
[`llm/client.py`](../llm/README.md).

Three metrics score their good label 0.0: `hallucination` (`factual`),
`toxicity` (`non-toxic`) and `refusal` (`answered`). The first two are
minimised. For that reason `assessment_metrics.approved` is a stored column,
and scores must not be summed across metrics.

The prompts are this repository's. Each says the material may be in any
language and asks for the reason with the label.

## Where a verdict shows up

| Where | What it shows |
|---|---|
| Postgres | `assessments` and `assessment_metrics`. The source of truth |
| Phoenix | One annotation per metric, plus an `assessment` summary scoring 1.0 for approved, on an `assess` span. A Phoenix that is down costs the annotation only |
| The API | `/assessment`, `/assessment/quality`, `/assessment/plan`, `POST /assessment/enrol`, and the five queue verbs |
| The UI | The Assessment page: a tab per artefact kind, a search over the judge's reasoning, and a checkbox per kind for the queue verbs |
| Dagster | The `assessments` asset, last in the graph, with a `judge_agrees_with_the_checker` check that never fails |
| Argilla | A `judge` field, and `judge_verdict` and `judge_disagrees` metadata, on all three datasets. The verdict is not an answer key |
| The export | Three Questions sheet columns (`Judge`, `Judge refused by`, `Why the judge said so`) and an Assessment sheet |

## The queue

Nothing upstream creates an assessment, so `start` enrols and then queues.
Enrolment inserts one `new` row per artefact with `ON CONFLICT DO NOTHING`,
so a second `start` enrols only what arrived since. `--enrol` does the first
half alone and reports how many artefacts a start would judge. Enrolment
ignores `--only`.

## Cost

Each metric is one model call: three per fact, two per topic, five per
question, and one more for a root question's paper scores. Twenty thousand
facts are sixty thousand calls, so the default is a sample per kind
(`ASSESSMENT_SAMPLE`), newest first. `ASSESSMENT_KINDS=question` buys the
most.

## Configuration

From `.env`:

| Setting | What it does |
| --- | --- |
| `ASSESSMENT_ENABLED` | Whether the phase runs at all |
| `ASSESSMENT_JUDGE_MODEL` | The judging model. Not `LLM_MODEL`: a model judging its own facts says yes. Unset, nothing is judged, and `make assess-status` says so |
| `ASSESSMENT_JUDGE_CONTAINER_MODEL` | The judging model in the containers, which do not read `ASSESSMENT_JUDGE_MODEL`. Unset, the worker refuses to claim work and its log says so |

From [`configs/env/backend.env`](../../configs/env/backend.env), in git:

| Setting | What it does |
| --- | --- |
| `ASSESSMENT_KINDS` | Which artefacts are judged |
| `ASSESSMENT_SAMPLE` | How many of each kind one `start` enrols, newest first. 0 is all of them |
| `ASSESSMENT_STRATIFY` | Spreads the sample over every language and question type in proportion to size (900 and 100 questions give 180 and 20 of 200), ordered by a hash of the id, so a second draw gives the same rows |

## How varied the questions are

`make diversity` measures a set of questions as the DataMorgana paper
([Filice et al., 2025](#references), Appendix E) measures a benchmark, after
[Shaib et al. (2024)](#references). It reads a workbook from `make
questions-export`, asks no model, and runs whether or not this phase is on.

| Metric | What it is | More varied when |
|---|---|---|
| NGD, n-gram diversity | For n = 1 to 4, the distinct n-grams over all n-grams, summed. The questions are joined end to end | higher |
| SR, self-repetition | The share of questions holding a four-word run that another question also holds | lower |
| word-CR, compression ratio | The joined text's size over its size gzipped at level 9 | lower |
| PoS-CR | The same ratio over the questions' part-of-speech tags | lower |
| HS, homogenization | The mean cosine between every two questions' vectors | lower |
| held | Not a diversity metric. The share of a question's content lemmas (nouns, proper nouns, adjectives) that its cited evidence sentences also carry | a higher value means an easier question |

`held` proxies the surface overlap that Van Elburg et al., [*Can We Evaluate
RAGs with Synthetic Data?*](https://arxiv.org/abs/2508.11758) (2025, section
6.2), name as a reason generated questions run easy. It is reported per
language, and `AGAINST=` leaves it out.

Words are split at whitespace, so a language written without spaces (Chinese,
Japanese) has meaningless scores until its spaCy pipeline splits its words.
PoS-CR reads UPOS tags from the pipeline in `NLP_MODELS`. HS embeds with
`EMBEDDING_MODEL`, so compare HS only between sets embedded alike. The report
loads both models and takes about a minute on the host.

Each language is measured on its own. A smaller set looks more varied, so
`SIZE=` draws that many questions per language, the same ones on every run,
and leaves out a language with fewer. Compare two sets only at one size.

`AGAINST=` compares two workbooks as the paper (Appendix E.2) does: each
language of both is drawn fifty times to 80% of the smaller set, and Welch's
t-test compares each metric. The report prints each side's mean and spread,
the difference and p, starred below 0.05. The draws overlap, so p is
optimistic.

`BY=category` measures each category of each language from the Categories
column, a question counting once in each of its categories. A second table
gives three shares per category:

| Column | The share of the category's questions |
|---|---|
| in bounds | whose word count is inside the category's `words` bounds in `QUESTIONS_CATEGORIZATIONS` (a dash where it has none) |
| factoid | whose Answer form is a value or a list |
| open-ended | whose Answer form is an explanation |

The bounds come from the stored settings, so this table needs the database. A
question written under other bounds is counted against the current ones.

`BY=kind` measures each kind (single, needs_both, compound) from the Kind
column, with a table of factoid and open-ended shares. A question with no
answer reads `single` there; the report lists it as `unanswerable` and leaves
it out of `held`.

Where the workbook holds the paper's judge (`rubric_*` rows), the report ends
with that judge's mean stored score per group, and with the documents and
passages no accepted question reaches.

`BY=document` draws the paper's Figure 1: whether a set stays varied when it
comes from few documents. For k = 5, 10, 15 and so on up to the language's
document count, it draws fifty times k documents and `SIZE` questions (200
unless given) and prints the mean PoS-CR and its spread. Export with
citations: a question counts under the first document its Citations rows
name. A corpus of one document per language has no curve.

The export's filter chooses the set. The paper used answerable questions:

```sh
make questions-export OUT=set.xlsx FILTER="--status accepted --answerable --roots-only"
make diversity FILE=set.xlsx SIZE=200
make diversity FILE=new.xlsx AGAINST=old.xlsx
make diversity FILE=set.xlsx BY=category
make diversity FILE=set.xlsx BY=kind
make diversity FILE=pool.xlsx BY=document SIZE=200
```

## Labelled shares corrected by the judge

`make diversity FILE=<workbook> LABELS=<file>` reads reviewers' labels of some
of a workbook's questions and corrects each labelled share by the paper's
judge's verdict on all of them. The method is the prediction-powered
inference ([Angelopoulos et al., 2023](#references)) that ARES ([Saad-Falcon
et al., 2024](#references), section 3.3) uses.

The labels file is JSONL with an integer `id`, an optional `question` (refused
if it differs from the workbook's, which catches labels from another
database) and one field per label. A label of yes or true is 1, no or false
is 0, and na or null leaves the row out of the count. A field named like a
workbook column (`released`, `status`, `answerable`) is refused. `--fields
usable,key_correct` (`FIELDS=` in make) names the labels where the file holds
other things.

The predictor is the Judge column: `approved` is 1, `refused` is 0, and `not
judged` rows are left out. The report prints, per language and per category or
kind, and pooled as `all`:

| Column | What it is |
|---|---|
| n, N | The labelled rows, and the judged rows without a label |
| judge | The share the judge approves, over every judged row |
| labels | The share labelled yes, over the labelled rows |
| corrected | The labelled share, corrected by the judge's verdict on the rest |
| 95% interval | Under 30 labels it is the labels' own Wilson interval and the row says `rough`. From 30 labels it is the corrected estimate plus and minus a t quantile. In a simulation with random labels it covered 0.94 to 0.97 from 5 to 29 labels and 0.92 to 0.95 from 30 to 100, and about 0.85 where the share is 0.95. Labels that all agree leave no spread, and the bound is the rule of three |
| width | The interval's width |
| labels-only | The width of the labels' own Wilson interval, to read the correction against |
| weight | How much of the judge's prediction was kept: 0 is the labels alone, 1 the paper's plain method |

The weight is tuned from the data, as in PPI++ ([Angelopoulos, Duchi and
Zrnic, 2023](#references)), so a judge that agrees poorly falls back towards
the labels' own share. It is negative for a label whose good side is "no",
such as `invalid`.

Caveats:

- The labelled rows must be a random sample of the workbook's rows.
- The guarantee is asymptotic, so an interval on a few dozen labels is rough.
  Each interval holds alone: K rows at once need a wider quantile.
- With the paper's judge on this project's review, intervals narrow by under
  3% ([measurements](../../docs/measurements.md#the-judges-verdict-as-a-correction-prediction-powered-inference)).

```sh
make diversity FILE=set.xlsx LABELS=labels.jsonl BY=category
```

## Layout

[`templates.py`](templates.py) holds the eleven judging templates over
thirteen metric names. [`judge.py`](judge.py) asks one model one judgement and
abstains when it will not answer. [`repository.py`](repository.py) holds the
queue, the enrolment and the verdict reads, and [`service.py`](service.py) the
drain loop and the annotations. [`config.py`](config.py) and
[`factory.py`](factory.py) hold settings and wiring. [`diversity.py`](diversity.py)
and [`ppi.py`](ppi.py) are pure functions. [`run.py`](run.py) is the command
line and the diversity report.

The package reads `database.qa_generator` directly and no other service's
repository, except that `BY=category` reads word bounds with
`question_generation.config`'s parser (see `.importlinter`).

## Tests

```sh
poetry run pytest tests/unit/assessment
```

[`tests/unit/assessment/`](../../tests/unit/assessment) covers the templates,
judge, service, configuration, prompts, diversity metrics and PPI estimate.

## Limits

- An unreachable judge fails a row and does not refuse the artefact.
  `assess-retry` requeues it.
- One abstaining metric leaves a partial verdict: the artefact is `assessed`,
  its `approved` is false, and readers count it as thin, neither approved nor
  refused.
- Once a release is drawn, only released questions are enrolled. Before one is
  drawn, every judgeable question is eligible.
- `hallucination`, `toxicity` and `refusal` score 1.0 for the bad label.
- A row judged under template version 1 has three metrics fewer, under
  version 2 none of the paper's six, and a question under version 3 keeps a
  `relevance` row that version 4 does not ask. `make assess-rerun` re-judges
  and overwrites.
- A judge named as `LLM_MODEL` marks its own work: this is warned, not
  refused. A judge named as nothing is refused.
- Deleting a fact, topic or question deletes its assessment.

## References

- Simone Filice, Guy Horowitz, David Carmel, Zohar Karnin, Liane Lewin-Eytan
  and Yoelle Maarek. 2025. [*Generating Q&A Benchmarks for RAG Evaluation in
  Enterprise Settings*](https://aclanthology.org/2025.acl-industry.33/). In
  *Proceedings of the 63rd Annual Meeting of the Association for
  Computational Linguistics (Volume 6: Industry Track)*, pages 469–484,
  Vienna, Austria. Association for Computational Linguistics.
  doi:10.18653/v1/2025.acl-industry.33. The DataMorgana paper.
- Jon Saad-Falcon, Omar Khattab, Christopher Potts and Matei Zaharia. 2024.
  [*ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation
  Systems*](https://aclanthology.org/2024.naacl-long.20/). In *Proceedings of
  the 2024 Conference of the North American Chapter of the Association for
  Computational Linguistics: Human Language Technologies (Volume 1: Long
  Papers)*, pages 338–354, Mexico City, Mexico. Association for Computational
  Linguistics. doi:10.18653/v1/2024.naacl-long.20.
- Anastasios N. Angelopoulos, Stephen Bates, Clara Fannjiang, Michael I.
  Jordan and Tijana Zrnic. 2023. [*Prediction-powered
  inference*](https://doi.org/10.1126/science.adi6000). *Science*
  382(6671):669–674. doi:10.1126/science.adi6000.
- Anastasios N. Angelopoulos, John C. Duchi and Tijana Zrnic. 2023.
  [*PPI++: Efficient Prediction-Powered Inference*](https://arxiv.org/abs/2311.01453).
  arXiv:2311.01453.
- Chantal Shaib et al. 2024. [*Standardizing the Measurement of Text
  Diversity: A Tool and a Comparative Analysis of Scores*](https://arxiv.org/abs/2403.00553).
  arXiv:2403.00553.
