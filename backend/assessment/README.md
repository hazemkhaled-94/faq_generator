# Assessment — the evaluation phase

An LLM judge over the facts, topics and answerable questions (a sample of
each kind, or all of them), run **after** the whole pipeline and never
during it. It records an opinion beside the checker's verdict and **decides
nothing**.

```bash
make assess-enrol            # write the rows a start would judge, and count them; not a dry run
make assess-start && make assess
make assess-status
```

Off unless `ASSESSMENT_ENABLED` is true in `.env`. Off, `assess-worker` waits
in place rather than exiting, and starts claiming within `WORKER_POLL_SECONDS`
of the flag being switched on from the Assessment page. A change to `.env`
reaches it with `make up`.

## Why it is called assessment

Because `evaluation/` is taken. That package is the golden-set runner — it
scores a served model against `cases.py` on the host. Two packages of one
name on two import roots is a `make` target that picks whichever `sys.path`
put first, so this is `assessment` everywhere the code says it and "the
evaluation phase" everywhere a person does.

## What it never does

**It is not a gate, and it cannot become one.** `facts.validated` is the
checker's and `questions.status` is the gates'. This phase writes neither.
It writes `assessments.approved`, which no stage reads.

That is not caution for its own sake. A judge asked a phrasing judgement over
labelled cases was reliable in English and near chance in German, and half of
this corpus is German: a phase that could reject rows would have thrown away
good German questions on the strength of a coin. `make eval-phrasing` scores
a judge against the floor an uninformed one reaches.

What a judge is good for is the **disagreement** — an artefact the pipeline
kept and the judge refused — and that is what this produces, at corpus
scale. A question a person accepted over a gate counts as kept. The
Assessment page marks the disagreements, and `make review-push-questions
IDS=` takes them to a reviewer.

## What is judged, and how

Three kinds, which are the three [`review/`](../../review/README.md)
already puts in front of a person. A passage and a parsed document are
absent: judging a conversion needs the source page rendered beside it, and
nothing here keeps one.

| Artefact | Judged on | Asked | Calls |
|---|---|---|---|
| `fact` | `hallucination` | Do the cited sentences support every part of the statement? | 3 |
| | `relevance` | Are those sentences *about* what the statement is about? | |
| | `toxicity` | Did the pipeline write something offensive of its own? | |
| `topic` | `summarization` | Is the label a good short name for these terms? | 2 |
| | `relevance` | Are these terms a subject, or the document's furniture? | |
| `question` | `hallucination` | Do the facts support every part of the answer? | 6 |
| | `qa_correctness` | Does the answer answer the question that was asked? | |
| | `refusal` | Is the answer an answer, or a refusal written down as one? | |
| | `conciseness` | Does the answer give what was asked for and stop? | |
| | `toxicity` | Did the pipeline write something offensive of its own? | |
| | `rubric_fluency` … `rubric_answerability` | The DataMorgana paper's six scores of the question, from one call; root questions only | |

### `refusal` is the one no gate makes

A question marked answerable whose stored answer is *"the document does not
specify"* is well formed, the right length, cites its facts and leaks no
source. **Every gate passes it**, and a benchmark built from it scores a
chatbot against a non-answer. Nothing else in this repository looks for it.

`conciseness` is the same shape one step down: `QUESTIONS_ANSWER_CHARS`
refuses an answer that is too long, and nothing refused one that spent its
allowance apologising.

`toxicity` is about what the pipeline **wrote**, not what the corpus is
about. A corpus may document harassment, and a neutral question about it is
not toxic — the templates say so at length, because a judge that conflates
the two would flag the most careful part of a difficult corpus.

### What is deliberately not asked

Of the evaluators phoenix-evals ships, the seven named above without a
`rubric_` prefix are the ones that apply.

| Not asked | Why |
|---|---|
| `faithfulness`, `correctness` | Near-duplicates of `hallucination` and `qa_correctness` — the same judgement with different rails. A second call asking the same question. |
| `hallucination_span_level`, `qa_span_level` | Span-level variants of two already asked. |
| `code_readability`, `code_functionality`, `sql_gen_eval` | No code and no SQL is produced. |
| `tool_calling`, `tool_selection`, `tool_parameter_extraction`, `tool_invocation`, `tool_response_handling` | Nothing here calls a tool. |
| `reference_link_correctness` | Artefacts carry no links. |
| `human_vs_ai` | Needs a human-written reference answer. `review/` stores a human **verdict**, not a human answer. |
| `user_frustration` | Needs a user conversation. |
| `document_relevance` | This *is* `relevance` above. |

**An artefact is approved only when every one of its metrics approves.** Not
a majority: an answer that is well-sourced and answers the wrong question is
worth somebody's time even though four of its five passed. The paper's six
scores count too, and only a 3 approves.

### Unanswerable questions are not judged

Every one of the five answer metrics reads the answer, and a deliberately
unanswerable question has none. Scoring it anyway would
report the pipeline's most careful output as its worst.

## The paper's judge

The DataMorgana paper ([Filice et al., 2025](#references), Appendix D)
measures a benchmark's questions with one judge prompt that scores each
question 1 to 3 on six dimensions: fluency, clarity and conciseness of the
question itself, and its relevance, consistency and answerability against the
passage it came from. That prompt is the `Rubric` template in
[`templates.py`](templates.py), so the scores here can be read beside the
paper's Table 3.

| Stored as | The paper asks whether the question… |
|---|---|
| `rubric_fluency` | is well formed, grammatical and fluent enough to be understood |
| `rubric_clarity` | is expressed clearly and unambiguously |
| `rubric_conciseness` | is concise, without redundant modifiers |
| `rubric_relevance` | asks for key information from the passage |
| `rubric_consistency` | agrees with the passage, without contradiction or hallucination |
| `rubric_answerability` | can be answered definitively from the passage |

It differs from the other templates in four ways, each for the comparison's
sake:

- **The words are the paper's.** Its definitions, its scoring guidelines and
  its six Wikipedia examples are kept, laid out under the same six headings
  every prompt here carries, with the sentence saying the material may be in
  any language. The one edit is Example 1's reply, which the paper prints as
  malformed JSON.
- **One call returns all six.** That is how the paper asked them, and scores
  asked another way would not compare. Each score is still stored as its own
  metric row.
- **It reads passages, not facts.** The judge is shown the passages the
  question's facts cite, each once, in document and reading order, at most
  four.
- **No explanation.** The paper asks for none, so these rows carry an empty
  one.

A score of 1, 2 or 3 is stored as its label, and as the score
(s − 1) / 2: 0, 0.5 or 1. The paper normalises a benchmark's mean the same way,
so the mean of a `rubric_` metric's stored scores over a set is the paper's
normalised figure for that set. Only a 3 approves. The prefix keeps these
apart from phoenix-evals' `relevance` and `conciseness`, which judge other
things.

Only a question that opens its thread is asked. A follow-up leans on the turn
before it, which the rubric is not shown, so it would be scored down for
context it was never given. A root question is due eleven metrics from six
calls, and a follow-up five from five.

### One judge of a question's relevance

Up to template version 3 a question was also asked phoenix-evals'
`relevance`: whether the facts it was written from hold what it needs. The
paper's judge asks the same of the passages, and before version 4 the two
were held against the labelled v0.3.0 review on 350 root questions, half in
each language. The paper's answerability agreed with the reviewers at least
as well (kappa 0.200 against 0.191 in German, 0.288 against 0.256 in
English), so version 4 asks a question the paper's judge alone. A fact and a
topic are still asked `relevance`, and a question's `relevance` row stored
under version 3 is kept, counted and listed under the same name.

## The names are phoenix-evals'. The prompts are not.

This is the one decision in the package worth arguing about, so:

**The names, the labels, the scores and the optimisation direction** are
taken from `arize-phoenix-evals`' evaluator configs and written out in
[`templates.py`](templates.py). A `hallucination`
annotation here sits in the same Phoenix Evaluations view as one posted by
anything else built on that package, and a reader sorts and charts them
together. Renaming it, or scoring it the other way round, would produce a
column that looks like the one they know and behaves differently.

> Three metrics score their good label 0.0: `hallucination` (`factual`),
> `toxicity` (`non-toxic`) and `refusal` (`answered`). The first two are
> **minimised**; phoenix-evals calls `refusal` neutral. That is why
> `assessment_metrics.approved` is a stored column
> rather than derived from the score: a reader summing scores across
> metrics would be adding a hallucination rate to a relevance rate.

**The prompts are this repository's**, for three reasons the shipped ones
cannot meet:

- **Half of this corpus is German.** The shipped templates instruct in
  English about an English answer. Every template here says the material may
  be in any language and that the judgement is about what it does, not what
  it is written in.
- **The artefacts are not a RAG answer.** phoenix-evals asks about a query,
  a context and a response. A fact has a statement and the sentences it
  cites; a topic has terms and a name. Substituting those into a three-slot
  template about retrieval asks the model to judge something it is not
  looking at.
- **An unexplained verdict is one a reviewer cannot act on.** Every template
  asks for the reason in the same call as the label.

`arize-phoenix-evals` is not a dependency of this repository, and using it
here would put a second LLM client, a second rate limiter and a
pandas dependency into a worker container to ask a question the client
already in that container can ask. The judging goes through
[`llm/client.py`](../llm/README.md) like every other model call: one retry
policy, one timeout, one place the reasoning tags are stripped, one place
the tokens and the spend are recorded.

**One call per judgement.** Three in one call is what
[`question_generation/phrasing.py`](../question_generation/README.md) exists
to undo. The paper's rubric is the one exception, for the reason above.

## Where a verdict shows up

Seven places, which is the point of it being a phase rather than a script.

| Where | What it shows |
|---|---|
| **Postgres** | `assessments` and `assessment_metrics`. The truth. |
| **Phoenix** | One annotation per metric, named as above, plus an `assessment` summary. `annotator_kind` is **LLM**, against **CODE** for the gates. |
| **The API** | `/assessment`, `/assessment/quality`, `/assessment/plan`, `POST /assessment/enrol`, and the five queue verbs. |
| **The UI** | The Assessment page — a tab per artefact kind, a search over the judge's own reasoning, and a checkbox per kind deciding what the queue verbs act on. |
| **Dagster** | The `assessments` asset, last in the graph, with a `judge_agrees_with_the_checker` check that never fails. |
| **Argilla** | A `judge` field and two metadata terms on all three datasets. |
| **The export** | Three columns on the Questions sheet (`Judge`, `Judge refused by`, `Why the judge said so`) and an Assessment sheet of its own. |

### In Phoenix

Each artefact opens an `assess` span. The annotations hang off it:

| Annotation | On an approved fact | On one the evidence does not support |
|---|---|---|
| `assessment` | `approved`, 1.0 | `refused`, 0.0 |
| `hallucination` | `factual`, **0.0** | `hallucinated`, **1.0** |
| `relevance` | `relevant`, 1.0 | `relevant`, 1.0 |

The summary scores 1.0 for approved, so a project's mean under that name
*is* the approval rate. The per-metric scores keep phoenix-evals' own
direction, which is why they cannot be averaged together and why each
annotation carries its `direction` as metadata.

Best-effort, like the gate verdicts: a Phoenix that is down costs the
annotation and not the run.

### In Argilla

The judge's verdict and its reasoning ride along on the records
[`review/`](../../review/README.md) already pushes — `judge` as a field, and
`judge_verdict` and `judge_disagrees` as metadata a reviewer can filter on.
The guidelines say in as many words that it is not an answer key.

Anchoring is the risk and it is the lesser one, for the reason that package
already gives: a sample nobody can interpret gets abandoned.

## The queue, which nothing upstream fills

Every other stage claims rows something before it created. Nothing creates
an assessment: a fact arrives from extraction with nowhere to record a
judgement.

So **`start` enrols and then queues**. `ON CONFLICT DO NOTHING` per kind, so
running it twice enrols only what arrived since, and a re-run over a judged
corpus costs one statement per kind rather than a model call per row. That
is topic modelling's arrangement — asking is what creates the work — reached
from the other direction.

`--enrol` does the first half alone: it writes the `new` rows and says how
many artefacts this would judge, before anybody pays for them.

Enrolment ignores `--only`. A row sitting `new` costs nothing and no worker
looks at one, so enrolling a kind nobody asked to judge yet is free; the
alternative was reading a value back out of a SQLAlchemy condition, which
this codebase does nowhere else.

## Cost

A model call per metric: **three per fact, two per topic, five per question**,
and one more for the paper's six scores of a root question.
A corpus of twenty thousand facts is sixty thousand calls, which is why the
default is a **sample per kind (`ASSESSMENT_SAMPLE`), newest first** and why
the phase ships off.

`ASSESSMENT_KINDS=question` is the setting that buys the most: the questions
are the deliverable, and they are the artefact whose `qa_correctness`
judgement has no counterpart anywhere upstream.

Like `topic-worker`, this worker loads **no** encoder — no spaCy pipeline,
no embedder, no NLI model — so it is the cheapest stage to scale
horizontally.

## Configuration

From `.env`, because each is one deployment's decision:

| Setting | What it does |
| --- | --- |
| `ASSESSMENT_ENABLED` | Whether the phase runs at all |
| `ASSESSMENT_JUDGE_MODEL` | Who judges. **Not** `LLM_MODEL`: a model asked whether its own facts follow from its own evidence says yes. Unset, nothing is judged, and `make assess-status` says so |
| `ASSESSMENT_JUDGE_CONTAINER_MODEL` | Who judges in the containers, which do not read `ASSESSMENT_JUDGE_MODEL` from `.env`. Unset, the worker judges nothing and its log says it refuses to claim work |

From [`configs/env/backend.env`](../../configs/env/backend.env), in git:

| Setting | What it does |
| --- | --- |
| `ASSESSMENT_KINDS` | Which artefacts are judged |
| `ASSESSMENT_SAMPLE` | How many of each kind one `start` enrols, newest first. 0 is all of them |
| `ASSESSMENT_STRATIFY` | Whether that sample spans every language, and every type of question, in an order fixed by a hash of the id, instead of taking the newest. Drawn again, it is the same rows |

## How varied the questions are

`make diversity` measures a set of questions the way the DataMorgana paper
([Filice et al., 2025](#references), Appendix E) measures a benchmark,
after [Shaib et al. (2024)](#references). It reads a workbook that `make questions-export`
wrote, asks no model, and runs whether or not this phase is switched on.

| Metric | What it is | More varied when |
|---|---|---|
| NGD, n-gram diversity | For n = 1 to 4, the distinct n-grams over all n-grams, summed. The questions are joined end to end, so an n-gram may run from one question into the next | higher |
| SR, self-repetition | The share of questions holding a four-word run that another question also holds | lower |
| word-CR, compression ratio | The joined text's size over its size gzipped at level 9 | lower |
| PoS-CR | The same ratio over the questions' part-of-speech tags, so it reads the shape of the sentences rather than their words | lower |
| HS, homogenization | The mean cosine between every two questions' vectors | lower |
| held | Not a diversity metric: how much of a question its cited evidence already holds, the share of its content lemmas (nouns, proper nouns, adjectives) that the evidence sentences carry too, averaged over the questions that have any | an easier question, when higher |

`held` is an easiness reading after the limits papers. Van Elburg et al.,
[*Can We Evaluate RAGs with Synthetic Data?*](https://arxiv.org/abs/2508.11758)
(2025, section 6.2), name surface overlap between a generated question and
its source as one reason such questions run easy, without measuring it.
`held` is a proxy for that, not their measure, which needs a chatbot's
scores on real and generated questions. It reads the facts' evidence
sentences, which are narrower than the passages, and is reported per
language, never pooled, because each language's pipeline lemmatises its
own way. A category meant to vary wording, such as distant-from-document,
should hold less than its sibling. `AGAINST=` leaves it out: it compares
the paper's five metrics only.

Words are split at whitespace with case and punctuation kept, so "card?" and
"card" are two words. Joining the questions with one space and gzipping at
level 9 are this project's reading of the paper, which does not say. A
language written without spaces between words, such as Chinese or Japanese,
would need its words split by its spaCy pipeline first; until one is
configured, its scores mean nothing.

PoS-CR reads UPOS tags from the language's spaCy pipeline in `NLP_MODELS`,
the tagset every language shares; the report names the pipeline and its
version, because another tagset or version moves the ratio. HS embeds each
question with `EMBEDDING_MODEL`, the model that embeds the corpus, rather
than the paper's English-only MiniLM. Its cosines sit higher, so its HS is
on a scale of its own: compare it only between sets embedded alike. The
report loads both models, so it takes a minute on the host.

Each language is measured on its own. These metrics move with the size of a
set (a smaller one looks more varied), so `SIZE=` draws that many questions
from each language, the same ones on every run, and names and leaves out a
language that has fewer. Two sets compare only at one size.

`AGAINST=` compares two workbooks the way the paper (Appendix E.2) tests
two methods. Each language of both is drawn fifty times, without
replacement, to 80% of the smaller set; each draw gets all five scores; and
each metric's two lists of fifty are put to Welch's t-test. The report
prints each side's mean and spread, the difference and p, starred below
0.05. The fifty draws overlap, so p is optimistic, as it is in the paper:
read the difference beside it.

`BY=category` measures each category of each language on its own, read
from the workbook's Categories column, so a question counts once in each of
its categories. A second table follows with three shares per category:

| Column | The share of the category's questions |
|---|---|
| in bounds | whose word count is inside the category's `words` bounds in `QUESTIONS_CATEGORIZATIONS`, a dash where it has none. A word is letters and digits, joined across a hyphen or an apostrophe, so `e-mail` and `What's` are one each |
| factoid | whose Answer form is a value or a list |
| open-ended | whose Answer form is an explanation |

The bounds are the ones configured when the report runs, read from the
stored settings through the question stage's own parser, so this table needs
the database the settings live in. A question stores the words its writer
was told and not the bounds, so one written under other bounds is counted
against today's, and the report says so.

`BY=kind` measures each kind of each language on its own (single,
needs_both, compound), read from the Kind column: the paper's judge is not
told a question's kind, and a compound question asks two things it was
never shown how to score. A second table gives each kind its factoid and
open-ended shares as above; word bounds are a category's, so it has no
in-bounds column.

And where the workbook holds the paper's judge (the `rubric_*` judgements on
its Assessment sheet), the report ends with that judge's mean scores for the
same groups: the mean stored score, which is the paper's normalised mean,
from 0 to 1.

`BY=document` ends with the documents and passages no accepted question
reaches, read from the workbook's Summary sheet (the export counts them under
its filter, in its documents and topic, so a curve over the documents that
have questions is read beside the ones that have none; an older workbook
prints nothing).

`BY=document` draws the paper's Figure 1, which asks whether a set stays
varied when it comes from few documents. For k = 5, 10, 15 ... up to the
language's documents, it draws fifty times k documents and SIZE questions
from them (200 unless given), each document giving its share, and prints
the mean part-of-speech compression ratio and its spread. A question counts
under the first document its Citations rows name, so export with citations.
It draws from questions already written, which were deduplicated against
the whole corpus, so it reads lower than writing SIZE questions anew from
k documents would. It needs a corpus of many documents: one of a single
document per language has no curve.

The export's filter chooses the set. The paper measured answerable
questions:

```sh
make questions-export OUT=set.xlsx FILTER="--status accepted --answerable --roots-only"
make diversity FILE=set.xlsx SIZE=200
make diversity FILE=new.xlsx AGAINST=old.xlsx
make diversity FILE=set.xlsx BY=category
make diversity FILE=set.xlsx BY=kind
make diversity FILE=pool.xlsx BY=document SIZE=200
```

## Labelled shares corrected by the judge

`make diversity FILE=<workbook> LABELS=<file>` reads reviewers' labels of
some of a workbook's questions and corrects each labelled share by the
paper's judge's verdict on all of them, as ARES ([Saad-Falcon et al.,
2024](#references), section 3.3) does with prediction-powered inference
([Angelopoulos et al., 2023](#references)). A judge can score every
question, but only a few have a reviewer's label. The method takes the
judge's share on the many and corrects it by how far the judge is from the
labels on the few. The estimate stays unbiased whatever the judge is like,
and it gets a confidence interval.

The labels file is JSONL: an integer `id`, an optional `question` (the
text, checked against the workbook's so that labels from another database,
whose ids overlap, are refused), and one field per label. Every other field
is a label, read as yes or true (1), no or false (0), na or null (no label).
Keep it to those fields: a `released` flag in it would be read as a label
too.

The predictor is the Judge column: `approved` is 1, `refused` 0, and a row
`not judged` is left out. The report prints, per language and per category
or kind, and pooled as `all`:

| Column | What it is |
|---|---|
| n, N | The labelled rows, and the judged rows without a label |
| judge | The share the judge approves, over every judged row |
| labels | The share labelled yes, over the labelled rows |
| corrected | The labelled share, corrected by the judge's verdict on the rest |
| 95% interval | Its interval, clipped to [0, 1] for display |
| weight | How much of the judge's prediction was kept: 0 is the labels alone, 1 the paper's plain method |

The weight is tuned from the data, as PPI++ ([Angelopoulos, Duchi and
Zrnic, 2023](#references)) does. A judge that agrees poorly with the labels
falls back towards the labels' own share instead of widening the interval,
as the plain method would. It can be negative: a label whose good side is
"no", such as `invalid`, is predicted by the judge's refusal.

Read it with three caveats:

- The labelled rows must be a random sample of the workbook's rows. A
  sample drawn evenly over languages is read per language and pooled by
  size, which the `all` row does.
- The guarantee is asymptotic, so an interval on a few dozen labels is
  rough. Each row's interval holds on its own; claiming K rows at once
  needs z at α/(2K).
- What it buys depends on the judge. With the paper's judge on this
  project's review, the intervals narrow by under 3% ([the measurements
  page](../../docs/measurements.md#the-judges-verdict-as-a-correction-prediction-powered-inference)).

```sh
make diversity FILE=set.xlsx LABELS=labels.jsonl BY=category
```

## Layout

| File | Holds |
|---|---|
| [`templates.py`](templates.py) | The eleven judging templates (three fact, two topic, six question) over thirteen metric names: the names, labels and scores borrowed from phoenix-evals, and the DataMorgana paper's judge |
| [`judge.py`](judge.py) | Asking one model one judgement, and abstaining when it will not answer |
| [`repository.py`](repository.py) | The queue, the enrolment, and reading the verdicts back |
| [`service.py`](service.py) | The drain loop, and the annotations it posts |
| [`config.py`](config.py) | The flag, the judge and the two cost dials |
| [`factory.py`](factory.py) | Wiring |
| [`diversity.py`](diversity.py) | How varied a set of questions is: the paper's metrics, as pure functions, and the word count and factuality a category is read by |
| [`ppi.py`](ppi.py) | Prediction-powered inference: a share corrected by a few labels, its interval, and strata pooled by size, as pure functions |
| [`run.py`](run.py) | The command line, and the diversity report on a workbook |

Reads `database.qa_generator` directly and no other service's repository —
this stage is about facts, topics and questions at once, and a package
importing all three services to read them would weld the four together. The
one exception is the diversity report's `BY=category`, which reads the
configured word bounds with `question_generation.config`'s parser rather
than a second one; `.importlinter` says why.

## Tests

```sh
poetry run pytest tests/unit/assessment
```

| File | Covers |
|---|---|
| [`test_templates.py`](../../tests/unit/assessment/test_templates.py) | The metric names, labels, scores and directions holding together, and every placeholder against the fields that fill it |
| [`test_judge.py`](../../tests/unit/assessment/test_judge.py) | One call per metric, the paper's six from one, the rubric spared a follow-up, and an abstention against a refusal |
| [`test_assessment_service.py`](../../tests/unit/assessment/test_assessment_service.py) | The row, the annotations, and the columns this phase does not write |
| [`test_assessment_config.py`](../../tests/unit/assessment/test_assessment_config.py) | The flag, the judge and the two cost dials |
| [`test_assessment_prompts.py`](../../tests/unit/assessment/test_assessment_prompts.py) | Every template recorded under a name of its own, with both halves and its version |
| [`test_diversity.py`](../../tests/unit/assessment/test_diversity.py) | The metrics against values worked out by hand, and the report on a workbook the exporter wrote |
| [`test_ppi.py`](../../tests/unit/assessment/test_ppi.py) | The estimate, the weight and the interval against values worked out by hand, the pooling, and two properties |

## Limits

- **Nothing here gates anything, ever.** No stage reads `approved`.
- **A judge that cannot be reached fails a row; it does not refuse an
  artefact.** `assess-retry` is what moves it.
- **One metric abstaining leaves a partial verdict.** The artefact is still
  `assessed`, its stored `approved` is false, and every reader counts it as
  thin: neither approved nor refused.
- **Unanswerable questions are not enrolled.** They have no answer to judge.
- **`hallucination`, `toxicity` and `refusal` score 1.0 for the bad label.**
  Read the direction.
- **A sample is the default.** `ASSESSMENT_SAMPLE=0` judges the corpus, and
  on a large one that is tens of thousands of model calls.
- **A root question costs six calls, a follow-up five and a fact three.**
  Judging questions alone is the setting that buys the most.
- **A row judged under template version 1 carries three metrics fewer, one
  under version 2 none of the paper's six, and a question judged under
  version 3 a `relevance` row version 4 no longer asks.** The version is on the row;
  `make assess-rerun` re-judges it.
- **Enrolment ignores `--only`.** The requeue after it does not.
- **A judge named as `LLM_MODEL` is marking its own work.** Warned, not
  refused. A judge named as nothing is refused.
- **Deleting a fact, topic or question deletes its assessment.** Three
  cascading foreign keys, so a verdict never outlives what it is about.
- **A re-run overwrites.** A corpus never holds two opinions from two
  template versions with nothing saying which is current.

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
