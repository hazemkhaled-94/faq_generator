# Known bugs

Defects in what the pipeline produced, each with the fix that closes it.

Everything counted here was measured against the re-verified release that
[measurements.md](measurements.md) describes. That page holds the run's
figures; this one holds only what is wrong with them.

| | Release rows | Where the fix goes | Fixed |
|---|---|---|---|
| [Two subjects welded under one question word](#two-subjects-welded-under-one-question-word) | 11 | [`gates.py`](../backend/question_generation/gates.py) | no |
| [Questions that count their own citations](#questions-that-count-their-own-citations) | 4 | [`gates.py`](../backend/question_generation/gates.py) | partial |

15 of the 1,015 — **1.5%** — carry at least one of them.

Nothing here touches the structure. Across the accepted pool every citation
resolves to a validated fact, every passage and document scope agrees with
the citations it describes, no question is in a language its passages are
not, and no two normalised question texts repeat. The defects are all in what
the rows say, not in how they are wired.

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

## Known trade-offs

Not defects: each is a rule doing what it is for, at a cost in sound rows.

**More citations, fewer questions.** Giving boilerplate facts their missing
citations moved 6 accepted questions from one passage or document to several.
Re-verification rejects a question whose stored scope no longer matches its
citations as `source_changed`. That is re-verify working as designed, and it
cost 6 sound questions.

**The written-count gate has the digit rule's blind spot.** Of the 3 accepted
rows it moved, 2 were sound: `zwei Lernziele` (question 4255) and `zwei
Faktoren` (5355) count something their own facts state, and only happen to
equal the number of facts cited. The digit rule refuses the same shape —
`2 coverage items` (1409).

## Known pipeline defects not counted above

**F36 — German indefinite article read as definite.** `_counted` in
[`analysis.py`](../backend/nlp/analysis.py) sets `definite` on
`PronType=Art`, which German also gives `ein` and `eine`. It is read only by
`pointing`, the question-side check that routes a question to the
self-contained judge, never by the fact checks. It does not reproduce on the
pinned parser, which attaches `ein` to `paar` rather than to the noun. Fix:
require `Definite` not to be `Ind`.

## Reproducing this page

The counts are queries over `questions`, `facts`, `question_facts` and
`fact_passages` — the run's own tables, not a log. The same rows come out of
the workbook:

```bash
make questions-export OUT=audit.xlsx FILTER="--released"
```

Re-measuring means taking a corpus through again and rewriting both this page
and [measurements.md](measurements.md).
