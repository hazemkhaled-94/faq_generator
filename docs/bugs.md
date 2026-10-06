# Known bugs

Defects in what the pipeline produced, each with the fix that closes it.

Everything counted here was measured against the re-verified release that
[measurements.md](measurements.md) describes: 5,873 written questions, 2,108
accepted after re-verification on 2026-10-06, and the 1,039 the balanced
release drew. That page holds the run's figures; this one holds only what is
wrong with them.

| | Release rows | Where the fix goes | Fixed |
|---|---|---|---|
| [Answers carry run-on conjunctions](#answers-carry-run-on-conjunctions) | 53 | [`gates.py`](../backend/question_generation/gates.py) | no |
| [Facts that open on a demonstrative](#facts-that-open-on-a-demonstrative) | 25 | [`analysis.py`](../backend/nlp/analysis.py) | partial |
| [Questions that count their own citations](#questions-that-count-their-own-citations) | 27 | [`gates.py`](../backend/question_generation/gates.py) | partial |
| [Boilerplate cited to the wrong document](#boilerplate-cited-to-the-wrong-document) | 8 | [`extraction`](../backend/extraction/README.md) | partial |
| [The evaluation phase judges the newest rows](#the-evaluation-phase-judges-the-newest-rows) | — | [`repository.py`](../backend/assessment/repository.py) | yes |

110 of the 1,039 — **10.6%** — carry at least one of them.

Nothing here touches the structure. Across all 2,108 accepted questions every
citation resolves to a validated fact, every scope label agrees with the
citation graph it describes, no question is in a language its passages are
not, and two normalised question texts repeat. The defects are all in what
the rows say, not in how they are wired. The previous release also carried
welds (D1), type-interrogative mismatches (D2), orphaned follow-ups (D3) and
restatement answers (D4a); all four dropped to zero after re-verification
under fixed gates.

## Answers carry run-on conjunctions

35 release rows glue three or more clauses into one key with no answer in it:

> *When can a test charter include more than just the planned scope and
> objectives?* — `when it includes organizational details, and entry
> criteria, and product information and limitations, and the test
> environment, and supporting data sources, tools, historical information,
> constraints and risks`

`wrong_form` already knows the declared form, but the example above is stored
as a `list`, not a `value` or an `explanation`, and a `value` or
`explanation` carrying three or more `when` clauses is one accepted question
in this run, whose answer is sound. No reading tried — coordinated clauses,
coordinating conjunctions, repeated `when` — separates the 35 from the
answers that are lists of conditions.

18 more are answerable and carry three or more `and`/`und` conjunctions with
no list structure. No fix has been attempted.

Measured as: answerable questions where `and`/`und` appears three or more
times in the normalised answer.

## Facts that open on a demonstrative

121 of the 9,056 validated facts begin on a reference that resolves nowhere —
*These types of documentation…*, *Hierfür…*, *In such cases…*. 39 accepted
questions rest on one and 25 are in the release; for 4 it is the only fact
cited, so the answer arrives from text the citation does not carry and the
row breaks the promise the Citations sheet makes.

The extractor flagged 3 of the 121. `_references` in
[`analysis.py`](../backend/nlp/analysis.py) collects pronouns and a short
list of anaphoric adjectives; a demonstrative *determiner* heading a noun
phrase is neither, so `Diese Dokumentationsarten` reads as an ordinary
subject.

**Fix shipped.** `_opens` reads the demonstrative determiners and pronominal
adverbs that open a statement with no noun of their own before the finite
verb. The existing `unresolved_reference` refusal in
[`validation.py`](../backend/extraction/validation.py) fires on the longer
array without changing. Sized against this run it refuses 179 of the validated
facts the model wrote; 61 accepted questions rest on one, 36 in the old
release. Existing stored facts are unaffected until `make extract-revalidate`
re-reads them — the 25 in the current release are the residue.

**Known limitation.** `_counted` in
[`analysis.py`](../backend/nlp/analysis.py) tests
`"Art" in morph.get("PronType", [])`, which spaCy sets on German indefinite
articles (`ein`, `eine`). These false positives inflate the demonstrative
count. The 25 figure is an upper bound.

## Questions that count their own citations

3 release rows ask how many of something there are and answer with the number
of facts the writer was handed:

> *How many sections are identified across ATDD's approach type and the BDD
> scenario part that triggers behavior?* — `2 sections`

24 more name the offer rather than the subject — *in den Angaben*,
*together*, *across … and …*. The question is about the prompt, not the
corpus, so the corpus cannot answer it.

**Fix shipped (partial).** A gate in
[`gates.py`](../backend/question_generation/gates.py) refuses to `malformed`
where the question opens *How many* / *Wie viele*, the answer's leading token
is a digit, and that digit equals the number of cited facts. It caught 8
questions in the old release. Counts written as words (`zwei Faktoren`, `two`)
and the 24 that name the offer are not caught.

## Boilerplate cited to the wrong document

69 validated facts rest on evidence that appears verbatim in more than one of
the 16 syllabi. Dedup keeps one copy and attributes it to whichever document
reached the extractor first, so a question about one syllabus cites a page in
another. 11 accepted questions, 8 in the release. The answers happen to be
right — the sentence says the same thing in both — but the page number sends
a marker to the wrong one.

**Fix shipped (partial).** Where a duplicate is refused, `store` now records
its passage into `fact_passages` beside the surviving fact. `delete_fact_without_passage`
deletes a fact other than a bridge only on its last citation. A fact already
stored gains its second citation only when the passage is extracted again —
the 8 in the current release are the residue.

## The evaluation phase judges the newest rows

`_enrolment` orders by id descending so an incremental run judges what
arrived since the last one. On a first run over a finished corpus that takes
the tail: question ids 5,597–5,873 and fact ids 11,955–12,154, contiguous,
**200 of 200 German and no English at all**. The assessed facts are 52%
validated against 74.5% across the run, so the slice is not the corpus.

Every figure under *The evaluation phase* in
[measurements.md](measurements.md) therefore describes the last-written
German slice — `qa_correctness`, `hallucination`, both disagreement matrices.

**Fix shipped.** `ASSESSMENT_STRATIFY`, off by default in
[`backend.env`](../configs/env/backend.env), enrols evenly across language
and question type and orders randomly within each band. The figures in
measurements.md stay the last-written German slice until a run is judged with
it set.

## Known pipeline defects not counted above

**F36 — German indefinite article detected as pointer.** `_counted` in
[`analysis.py`](../backend/nlp/analysis.py) tests
`"Art" in morph.get("PronType", [])`. spaCy sets `Art` on indefinite articles
as well as definite ones, so `ein Abschnitt` reads as a pointer and a fact
containing it is refused as `unresolved_reference` rather than validated. The
figure for demonstrative facts is inflated accordingly. Fix: restrict the
check to `PronType=Dem` and exclude `Definite=Ind`.

**F74 — Arrivals sensor undoes Stop.** The `arrivals` sensor in the ingestion
Dagster job treats any `new` row in the parsing table as an unrequested
upload and re-runs the pipeline, overwriting a manual Stop. A deliberate stop
after corpus ingestion is complete does not persist across a Dagster restart.
Fix: gate the sensor on an explicit `INGESTION_OPEN` flag rather than on row
presence.

## Reproducing this page

The counts are queries over `questions`, `facts`, `question_facts` and
`fact_passages` — the run's own tables, not a log. The same rows come out of
the workbook:

```bash
make questions-export OUT=audit.xlsx FILTER="--status accepted"
```

Re-measuring means taking a corpus through again and rewriting both this page
and [measurements.md](measurements.md).
