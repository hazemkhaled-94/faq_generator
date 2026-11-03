"""What the judge is asked, per metric, and what its answers are called.

**The names are arize-phoenix-evals'. The templates are not.**

That split is the whole of this module. A `hallucination` annotation in
Phoenix's Evaluations view means something to anybody who has used Phoenix
before: two labels, `factual` and `hallucinated`, scored 0.0 and 1.0
because the metric's optimisation direction is *minimise*. Renaming it, or
scoring it the other way round, would produce a column that looks like the
one they know and sorts backwards. So the name, the labels, the scores and
the direction here are read off phoenix-evals' own evaluator configs and
pinned in `_CHOICES` below.

The prompts behind them are this repository's, for three reasons the
shipped ones cannot meet:

- **Part of this corpus is German.** The shipped templates instruct in
  English about an English answer. Every template here says the artefact
  may be in any language and that the judgement is about what it does, not
  what it is written in.
- **The artefacts are not a RAG answer.** phoenix-evals asks about a
  query, a context and a response. A fact has a statement and the sentences
  it cites; a topic has terms and a name. Substituting those into a
  three-slot template about retrieval asks the model to judge something it
  is not looking at.
- **An answer with no reason is not usable.** What this phase produces is
  a queue for `review/`, so every template asks for the explanation in the
  same call as the label.

The examples are deliberately about nothing - see
`tests/static/test_prompts_name_no_domain.py`, which reads this file.

One template departs from all of this but the language: `Rubric`, the
DataMorgana paper's judge, is the paper's prompt and not this repository's,
with its Wikipedia examples, its own names and no explanation asked for,
because its scores are only worth having where they compare with the
paper's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from assessment.models import Judgement
from database.qa_generator import ArtifactKind, JudgeMetric
from llm.prompt import fill, grounded

#: Bumped whenever a template below changes what it asks for, or when the
#: SET a kind is asked changes. Recorded on every assessment, because two
#: template versions are two judgements the way two extraction prompts are
#: two datasets.
#:
#: Version 2 added `toxicity`, `conciseness` and `refusal`. A row judged
#: under version 1 carries three metrics fewer, and that is readable rather
#: than mysterious because the version is on the row.
#:
#: Version 3 added the DataMorgana paper's rubric: one more call for a root
#: question, returning six scores.
#:
#: Version 4 stopped asking a question `relevance`: the paper's judge reads
#: the question against its passages, and its answerability agreed with the
#: labelled review at least as well. A root is due eleven metrics from six
#: calls and a follow-up five from five; a question's `relevance` row stored
#: under version 3 is kept and read as it was.
#:
#: Version 5 fences the document's text in every template that shows it, under
#: a line saying it is material and never instructions.
PROMPT_VERSION = "5"

#: The DataMorgana paper's six dimensions (Filice et al., 2025, Appendix D),
#: in its order, by the name each score is stored under. One call answers
#: all six, which is how the paper asks them and the only way its Table 3
#: compares.
RUBRIC: tuple[str, ...] = (
    JudgeMetric.RUBRIC_FLUENCY,
    JudgeMetric.RUBRIC_CLARITY,
    JudgeMetric.RUBRIC_CONCISENESS,
    JudgeMetric.RUBRIC_RELEVANCE,
    JudgeMetric.RUBRIC_CONSISTENCY,
    JudgeMetric.RUBRIC_ANSWERABILITY,
)

#: Each metric's labels and the score phoenix-evals gives them, and which
#: label is the good one. Taken from that package's own evaluator configs:
#: `hallucination` scores 1.0 for `hallucinated` because its optimisation
#: direction is minimise, `toxicity` and `refusal` score 1.0 for the bad
#: label too, and every other metric here scores 1.0 for the label it wants.
#: `approved` is stored per metric rather than derived from the score for
#: exactly that reason - summing scores across these would add a
#: hallucination rate to a relevance rate.
_CHOICES: dict[str, tuple[dict[str, float], str]] = {
    JudgeMetric.HALLUCINATION: ({"hallucinated": 1.0, "factual": 0.0}, "factual"),
    JudgeMetric.RELEVANCE: ({"relevant": 1.0, "unrelated": 0.0}, "relevant"),
    JudgeMetric.QA_CORRECTNESS: ({"correct": 1.0, "incorrect": 0.0}, "correct"),
    JudgeMetric.SUMMARIZATION: ({"good": 1.0, "bad": 0.0}, "good"),
    JudgeMetric.TOXICITY: ({"toxic": 1.0, "non-toxic": 0.0}, "non-toxic"),
    JudgeMetric.CONCISENESS: ({"concise": 1.0, "verbose": 0.0}, "concise"),
    # `refused` is the 1.0 and `answered` is what approves, which is the
    # third metric here whose good label scores zero. phoenix-evals calls
    # its direction NEUTRAL - a refusal is not a defect in a chat assistant
    # - but in a reference dataset it is exactly one: an answerable
    # question whose stored answer is "the document does not say" is a row
    # nothing else in this pipeline rejects.
    JudgeMetric.REFUSAL: ({"refused": 1.0, "answered": 0.0}, "answered"),
    # The paper's 1 to 3, scored (s - 1) / 2: the shift it applies to a
    # benchmark's mean, applied per question, so its normalised mean of a
    # set is the mean of the stored scores. Only a 3 approves - a 2 is the
    # paper's "partly", and `approved` is every metric on its good side.
    **dict.fromkeys(RUBRIC, ({"1": 0.0, "2": 0.5, "3": 1.0}, "3")),
}

#: How each metric is optimised, as phoenix-evals declares it. Recorded on
#: the annotation's metadata so a Phoenix chart of the mean is read the
#: right way up.
_DIRECTION: dict[str, str] = {
    JudgeMetric.HALLUCINATION: "minimize",
    JudgeMetric.RELEVANCE: "maximize",
    JudgeMetric.QA_CORRECTNESS: "maximize",
    JudgeMetric.SUMMARIZATION: "maximize",
    JudgeMetric.TOXICITY: "minimize",
    JudgeMetric.CONCISENESS: "maximize",
    #: phoenix-evals' own word for this one. Kept rather than corrected to
    #: `minimize`: the name, the labels, the scores and the direction are
    #: that package's vocabulary, and a reader who knows `refusal` there
    #: should not find it declaring something else here. What this
    #: repository thinks of a refusal is in `_CHOICES` above, where
    #: `answered` is the label that approves.
    JudgeMetric.REFUSAL: "neutral",
    **dict.fromkeys(RUBRIC, "maximize"),
}

#: The sentence every template carries, because the corpus is not in one
#: language and the judgement is not about which one.
_ANY_LANGUAGE = """The material may be in any language, and the examples below are in English
only because these instructions are. Judge what it does, not what it is
written in."""


@dataclass(frozen=True)
class Template:
    """One judgement, as the model is asked it and as Phoenix files it.

    Attributes:
        metric: The name Phoenix shows, which is phoenix-evals' name.
        kind: Which artefact this judges.
        system: What the model is told it is doing.
        user: The material, with `{{name}}` where a row is substituted.
        labels: The answers allowed, in the order the prompt offers them.
        scores: What each label scores, as phoenix-evals scores it.
        good: The label that counts as approval.
    """

    metric: str
    kind: str
    system: str
    user: str
    #: The placeholders `user` carries, which is also what `rendered` must
    #: be given. Declared rather than scraped, so a template gaining a
    #: `{{name}}` that nothing supplies is caught by the check below and by
    #: `tests/unit/assessment/test_templates.py` rather than reaching a
    #: model as the braces themselves.
    fields: tuple[str, ...]
    #: Asked of a question that opens its thread and not of a follow-up,
    #: which leans on a turn before it that the template is not shown.
    roots_only: bool = False
    #: The fields that are a document's text, sent fenced. Each such template's
    #: system prompt says material is never an instruction.
    material: tuple[str, ...] = ()

    @property
    def metrics(self) -> tuple[str, ...]:
        """The metrics one answer to this template is recorded as."""
        return (self.metric,)

    @property
    def labels(self) -> tuple[str, ...]:
        """The answers this metric allows."""
        return tuple(_CHOICES[self.metric][0])

    @property
    def scores(self) -> dict[str, float]:
        """What each label scores."""
        return dict(_CHOICES[self.metric][0])

    @property
    def good(self) -> str:
        """The label that counts as approval."""
        return _CHOICES[self.metric][1]

    def rendered(self, **fields: str) -> str:
        """The user message with this artefact's text substituted in.

        `{{name}}` rather than a format specifier, because the template is
        also what `stages/prompts.py` records for Phoenix, and a prompt
        recorded with `{}` in it is one the playground cannot show.

        Raises:
            KeyError: If a placeholder was left unfilled. A template
                variable nobody substitutes reaches the model as the braces
                themselves, with no error anywhere and an answer that looks
                fine - which is the failure
                `tests/static/test_prompts_name_no_domain.py` catches for
                the prompts that fill theirs one `.replace` at a time. This
                one substitutes generically, so it checks instead.
        """
        missing = [name for name in self.fields if name not in fields]
        if missing:
            raise KeyError(
                f"{self.metric} on a {self.kind} needs {', '.join(self.fields)} "
                f"and was not given {', '.join(missing)}"
            )
        return fill(
            self.user,
            {"{{" + name + "}}": value for name, value in fields.items()},
            material=["{{" + name + "}}" for name in self.material],
        )

    def shape(self) -> type[BaseModel]:
        """The Pydantic shape this metric's answer must come back in.

        Built per template so the `label` field is a `Literal` of exactly
        this metric's labels: an answer outside the rails is then a schema
        failure the client retries, rather than a string nothing maps.
        """
        labels = Literal[self.labels]  # pyright: ignore[reportInvalidTypeForm]

        class Judgement(BaseModel):
            """One judgement, and why."""

            label: labels = Field(  # pyright: ignore[reportInvalidTypeForm]
                description=f"One of: {', '.join(self.labels)}."
            )
            explanation: str = Field(
                description="One or two sentences saying why, naming the part "
                "of the material that decided it."
            )

        # Named for the metric, because the shape's name is what reaches the
        # span as `tag.tags` and the log line as `llm.shape`. Left alone,
        # every one of the seven would arrive as `Judgement`.
        Judgement.__name__ = f"_{self.metric.title().replace('_', '')}"
        return Judgement

    def judged(self, said: BaseModel) -> tuple[Judgement, ...]:
        """What one answer in this template's shape is recorded as."""
        label = str(said.label)  # pyright: ignore[reportAttributeAccessIssue]
        return (
            Judgement(
                metric=self.metric,
                label=label,
                score=self.scores[label],
                approved=label == self.good,
                explanation=" ".join(
                    str(said.explanation).split()  # pyright: ignore[reportAttributeAccessIssue]
                ),
            ),
        )


class _Rubric(BaseModel):
    """The paper's reply: six scores, named as it names them, and no reason."""

    fluency: Literal[1, 2, 3]
    clarity: Literal[1, 2, 3]
    conciseness: Literal[1, 2, 3]
    relevance: Literal[1, 2, 3]
    consistency: Literal[1, 2, 3]
    answerability: Literal[1, 2, 3]


@dataclass(frozen=True)
class Rubric(Template):
    """The DataMorgana paper's judge: one call, six scores, about the question.

    The five phoenix-evals templates above it judge the ANSWER, one call
    each. This one judges the question against the passages it was written
    from, and asks the six together because that is how the paper asked
    them: its Table 3 compares with nothing asked another way. The single
    call is what `question_generation/phrasing.py` warns against, and here
    it is the price of the comparison.

    No explanation, as the paper asks for none. What it produces is a
    measurement to put beside the paper's, not a reason for a reviewer.
    """

    @property
    def metrics(self) -> tuple[str, ...]:
        """The paper's six, in its order."""
        return RUBRIC

    def shape(self) -> type[BaseModel]:
        """Six scores of 1 to 3, a reply outside them a schema failure."""
        return _Rubric

    def judged(self, said: BaseModel) -> tuple[Judgement, ...]:
        """One judgement per score, labelled with the score as the paper gave it."""
        recorded = []
        for metric in self.metrics:
            label = str(getattr(said, metric.removeprefix("rubric_")))
            scores, good = _CHOICES[metric]
            recorded.append(
                Judgement(
                    metric=metric,
                    label=label,
                    score=scores[label],
                    approved=label == good,
                    explanation="",
                )
            )
        return tuple(recorded)


# ── Facts ────────────────────────────────────────────────────────────────

_FACT_HALLUCINATION = grounded(
    f"""ROLE
You are a fact checker. You judge ONE property of ONE statement and nothing
else about it.

ACTION
Say whether the cited sentences support every part of the statement.

STEPS
1. Read the cited sentences.
2. Read the statement, and list every thing it asserts - every number, name,
   date, quantity, condition and claim.
3. For each one, find where the cited sentences say it.
4. Answer `factual` only when every part is found. Answer `hallucinated` if
   any part is absent, altered, or asserted more strongly than the sentences
   do.

CONTEXT
The statement was drawn FROM the cited sentences, so the question is not
whether it is true in the world. It is whether these sentences say it.

A statement that says LESS than the sentences is still factual. A statement
that rounds, generalises, or adds a qualifier the sentences do not carry is
not.

{_ANY_LANGUAGE}

EXAMPLES
factual:      sentences say a request must be confirmed within five working
              days; statement says a request must be confirmed within five
              working days.
factual:      sentences list four conditions; statement asserts the second of
              them alone.
hallucinated: sentences say a review happens quarterly; statement says a
              review happens quarterly and is chaired by the site manager.
              (nothing says who chairs it)
hallucinated: sentences say a threshold is "usually" met; statement says it
              "is always" met.

FORMAT
Return `label`, one of `factual` or `hallucinated`, and `explanation`."""
)

_FACT_RELEVANCE = grounded(
    f"""ROLE
You are a source checker. You judge ONE property of ONE statement and nothing
else about it.

ACTION
Say whether the cited sentences are the right evidence for this statement -
whether they are ABOUT what the statement is about.

STEPS
1. Read the statement and name its subject.
2. Read the cited sentences and name theirs.
3. Decide whether somebody looking for evidence for this statement would be
   satisfied by these sentences.
4. Answer `relevant` when they bear on the statement's subject, `unrelated`
   when they are about something else.

CONTEXT
This is not the same question as whether the sentences SUPPORT the statement,
which is asked separately. Evidence can be on-subject and still not support
what is claimed, and that case is `relevant` here.

What this catches is a citation that points at the wrong place: a statement
about one thing resting on sentences about another, which is what happens
when the sentence numbering and the text have come apart.

{_ANY_LANGUAGE}

EXAMPLES
relevant:  statement is about a notice period; sentences discuss notice
           periods, even if they give a different number.
relevant:  statement names a duty; sentences set out who holds that duty.
unrelated: statement is about a reporting deadline; sentences are a list of
           document revisions.
unrelated: statement asserts a definition; sentences are a page header and a
           copyright notice.

FORMAT
Return `label`, one of `relevant` or `unrelated`, and `explanation`."""
)

_FACT_USER = """STATEMENT
{{statement}}

CITED SENTENCES
{{evidence}}"""


# ── Topics ───────────────────────────────────────────────────────────────

_TOPIC_SUMMARIZATION = f"""ROLE
You are a librarian. You judge ONE property of ONE label and nothing else
about it.

ACTION
Say whether the label is a good short name for the terms beneath it.

STEPS
1. Read the terms.
2. Decide what, if anything, they are collectively about.
3. Read the label.
4. Answer `good` when somebody shown the label alone would expect these
   terms; `bad` when the label is wrong, far too broad, or names only a
   fraction of them.

CONTEXT
The terms are the strongest words of one cluster, in weight order, so the
first few matter most. A label that names those and ignores a long tail is
still good.

A label is `bad` when it is generic enough to fit any cluster at all - "General
information", "Various topics", "Document" - because such a label tells a
reader nothing they did not already know.

{_ANY_LANGUAGE}

EXAMPLES
good: terms are response, deadline, escalation, urgent, acknowledge; label is
      "Response times and escalation".
good: terms are heat, thermal, insulation, transfer, conductivity; label is
      "Thermal behaviour".
bad:  terms are invoice, payment, net, due, remittance; label is "Documents".
      (true of the terms and true of every other cluster too)
bad:  terms are training, competence, assessor, certificate, refresher; label
      is "Safety equipment". (names something the terms do not)

FORMAT
Return `label`, one of `good` or `bad`, and `explanation`."""

_TOPIC_RELEVANCE = f"""ROLE
You are a librarian. You judge ONE property of ONE cluster of terms and
nothing else about it.

ACTION
Say whether these terms describe a SUBJECT the material is about, or the
furniture that surrounds it.

STEPS
1. Read the terms.
2. Decide whether they name something a reader could want to know about.
3. Answer `relevant` when they do, `unrelated` when they are page furniture,
   boilerplate, or a mixture with no subject in it.

CONTEXT
Every corpus carries text that is real, well-formed and about nothing anybody
wants to ask: page headers and footers, copyright notices, revision tables,
tables of contents, distribution lists, document control blocks.

A cluster of those is not a bad cluster. It is an accurate description of
material that should not be asked about, and saying so is what this judgement
is for.

A mixture is also `unrelated`: terms drawn from several unconnected subjects
at once describe no subject.

{_ANY_LANGUAGE}

EXAMPLES
relevant:  storage, temperature, humidity, ambient, range.
relevant:  appeal, decision, grounds, deadline, submit.
unrelated: page, figure, table, see, appendix.
unrelated: version, revision, approved, date, issued, supersedes.
unrelated: colour, deadline, welding, invoice, staffing. (five subjects, no
           subject)

FORMAT
Return `label`, one of `relevant` or `unrelated`, and `explanation`."""

_TOPIC_USER = """TERMS, strongest first
{{terms}}

LABEL
{{label}}"""

_TOPIC_TERMS_ONLY = """TERMS, strongest first
{{terms}}"""


# ── Questions ────────────────────────────────────────────────────────────

_QUESTION_HALLUCINATION = grounded(
    f"""ROLE
You are an examiner. You judge ONE property of ONE expected answer and
nothing else about it.

ACTION
Say whether the facts beneath support every part of the expected answer.

STEPS
1. Read the facts.
2. Read the question, then the expected answer.
3. List every thing the answer asserts.
4. For each one, find where the facts say it.
5. Answer `factual` only when every part is found. Answer `hallucinated` if
   any part is absent from the facts or contradicts them.

CONTEXT
The question is here so you know what was asked, not to be judged. Whether
the answer is the RIGHT answer is a different judgement, asked separately.
This one is only about whether the answer rests on the facts shown.

An answer that is correct in the world and absent from the facts is
`hallucinated`: the facts are what this dataset's answers have to be
checkable against.

{_ANY_LANGUAGE}

EXAMPLES
factual:      facts state a limit of thirty days; answer is "thirty days".
factual:      facts state three conditions; answer names all three.
hallucinated: facts state a limit of thirty days; answer is "thirty days, or
              sixty by agreement". (nothing about an agreement)
hallucinated: facts describe a procedure; answer names the department that
              runs it, which no fact names.

FORMAT
Return `label`, one of `factual` or `hallucinated`, and `explanation`."""
)

_QUESTION_QA_CORRECTNESS = grounded(
    f"""ROLE
You are an examiner. You judge ONE property of ONE question-and-answer pair
and nothing else about it.

ACTION
Say whether the expected answer actually answers the question that was asked.

STEPS
1. Read the question and decide precisely what it asks for.
2. Read the expected answer.
3. Decide whether it answers THAT, completely.
4. Answer `correct` when it does; `incorrect` when it answers a different
   question, answers only part of the one asked, or does not answer at all.

CONTEXT
Whether the answer rests on the facts is judged separately. This is about
fit: a true, well-sourced statement that answers a question nobody asked is
`incorrect` here.

A question asking "how many" wants a number. One asking "why" wants a reason.
One asking for a list wants the whole list, and an answer giving two of four
items is `incorrect`.

{_ANY_LANGUAGE}

EXAMPLES
correct:   "How long is allowed for a reply?" / "Five working days."
correct:   "Why must a change be recorded?" / "So that the previous
           configuration can be restored if the change fails."
incorrect: "How long is allowed for a reply?" / "Replies are handled by the
           duty officer." (answers who, not how long)
incorrect: "Which three checks are required?" / "A visual check and a
           pressure test." (two of three)

FORMAT
Return `label`, one of `correct` or `incorrect`, and `explanation`."""
)

_QUESTION_REFUSAL = f"""ROLE
You are an examiner. You judge ONE property of ONE expected answer and
nothing else about it.

ACTION
Say whether the expected answer actually answers, or whether it is a
refusal written down as though it were an answer.

STEPS
1. Read the expected answer on its own.
2. Decide whether somebody reading it learns the thing the question asked
   for.
3. Answer `answered` when they do, even if the answer is short, hedged or
   wrong. Answer `refused` when the text declines, deflects, or says the
   material does not cover it.

CONTEXT
This question is marked as one the material DOES answer. So a stored answer
that says the material is silent is not a careful answer - it is a failure
that got written into the dataset, and a benchmark carrying it would score
a chatbot against "the document does not specify".

Being wrong is not refusing. An answer that confidently states the wrong
number has answered, and a different judgement decides whether it is right.

{_ANY_LANGUAGE}

EXAMPLES
answered: "Five working days."
answered: "Around thirty, though the figure is given as an estimate."
answered: "Twelve." (even where the material says eleven)
refused:  "The document does not specify a period."
refused:  "This information is not available in the provided context."
refused:  "I could not determine the answer from the passages."
refused:  "See the relevant section of the manual." (points, does not answer)

FORMAT
Return `label`, one of `answered` or `refused`, and `explanation`."""

_QUESTION_CONCISENESS = f"""ROLE
You are an examiner. You judge ONE property of ONE expected answer and
nothing else about it.

ACTION
Say whether the answer gives what was asked for and stops.

STEPS
1. Read the question and decide exactly what it asks for.
2. Read the expected answer.
3. Strike out everything that is not that.
4. Answer `concise` when little or nothing goes. Answer `verbose` when the
   answer carries pleasantries, restatement of the question, hedging,
   meta-commentary, or an explanation nobody asked for.

CONTEXT
This answer is the target a chatbot is scored against. Every word in it
that was not asked for is a word a correct chatbot can be marked down for
missing, so padding here is not a matter of taste - it makes the benchmark
measure the wrong thing.

Length is not the test. A question asking for four conditions wants all
four, and an answer listing them is concise. A one-line answer that spends
half its line apologising is not.

{_ANY_LANGUAGE}

EXAMPLES
concise: "Five working days."
concise: "A visual check, a pressure test and a sign-off." (three asked for)
verbose: "Great question! The reply period is five working days."
verbose: "The reply period, which is an important part of the process, is
         five working days, though this may vary."
verbose: "As stated in the question about reply periods, the answer is five
         working days."

FORMAT
Return `label`, one of `concise` or `verbose`, and `explanation`."""

_QUESTION_TOXICITY = f"""ROLE
You are a reviewer. You judge ONE property of ONE question-and-answer pair
and nothing else about it.

ACTION
Say whether the text is unacceptable to put in front of somebody.

STEPS
1. Read the question and the answer.
2. Look for content that is racist, sexist, demeaning, harassing, violent,
   or otherwise abusive.
3. Answer `toxic` only when the text ITSELF is such content. Answer
   `non-toxic` otherwise.

CONTEXT
This is about what the pipeline WROTE, not about what the source material
is about. A corpus may document discrimination, describe an assault, or
quote abusive language as evidence, and a neutral question about that
material is not toxic - describing a subject is not being one.

What this catches is a model that produced something offensive of its own,
which is rare and worth knowing about before a dataset is published.

{_ANY_LANGUAGE}

EXAMPLES
non-toxic: "What must a manager do after a harassment complaint?"
non-toxic: "Which categories does the anti-discrimination policy name?"
non-toxic: "How are injuries from an assault recorded?"
toxic:     a question or answer that insults a group of people
toxic:     an answer that recommends harming somebody

FORMAT
Return `label`, one of `non-toxic` or `toxic`, and `explanation`."""

_FACT_TOXICITY = grounded(
    f"""ROLE
You are a reviewer. You judge ONE property of ONE statement and nothing
else about it.

ACTION
Say whether the statement is unacceptable to put in front of somebody.

STEPS
1. Read the statement.
2. Look for content that is racist, sexist, demeaning, harassing, violent,
   or otherwise abusive.
3. Answer `toxic` only when the statement ITSELF is such content. Answer
   `non-toxic` otherwise.

CONTEXT
This is about what the pipeline WROTE, not about what the source material
is about. A fact drawn from a document describing discrimination, injury or
abusive conduct is a neutral report of what that document says, and
reporting a subject is not being one.

{_ANY_LANGUAGE}

EXAMPLES
non-toxic: "A complaint must be recorded within two working days."
non-toxic: "The policy lists harassment as grounds for dismissal."
non-toxic: "Injuries are reported to the site supervisor."
toxic:     a statement that insults a group of people
toxic:     a statement recommending harm

FORMAT
Return `label`, one of `non-toxic` or `toxic`, and `explanation`."""
)

#: Toxicity reads the artefact and nothing else: there is no evidence to
#: compare it against, because the question is not whether the text is
#: supported but whether it should have been written.
_FACT_TEXT_ONLY = """STATEMENT
{{statement}}"""

_QUESTION_TEXT_ONLY = """QUESTION
{{question}}

EXPECTED ANSWER
{{answer}}"""

_QUESTION_USER = """QUESTION
{{question}}

EXPECTED ANSWER
{{answer}}

FACTS IT WAS WRITTEN FROM
{{facts}}"""


#: Figures 5-7 of the paper, its words and its six examples, in the six
#: sections every prompt here carries. The examples are about Wikipedia and
#: not about nothing, as every other example in this module is: they are the
#: paper's, kept so the scores compare with its Table 3. Example 1's reply is
#: corrected, because the paper prints it as `"clarity: 1` and a judge shown
#: malformed JSON as the answer to give is being taught to give it.
_RUBRIC_STEPS = """## Fluency
Whether the question is wellformed, grammatically correct, coherent, and fluent
enough to be understood. Provide it one of 3 scores according to these
guidelines

Score 1: The question is incoherent, with imprecise wording or significant
grammatical errors, making it difficult to comprehend its meaning.
Score 2: The question is slightly incoherent or contains minor grammatical
errors, but it does not hinder the understanding of the question's meaning.
Score 3: The question is fluent and grammatically correct.

## Clarity
Whether the question is expressed clearly and unambiguously, avoiding excessive
generality and ambiguity

Score 1: The question is too broad or expressed in a confusing manner, making
it difficult to understand or leading to ambiguity. Particularly, if the
generated sentence is not a question but a declarative sentence, it should be
considered in this situation.
Score 2: The question is not expressed very clearly and specifically, but it is
possible to infer the question's meaning based on the given passage.
Score 3: The question is clear and specific, without any ambiguity.

## Conciseness
Whether the question is concise and not abnormally verbose with redundant
modifiers

Score 1: The question contains too much redundant information, making it
difficult to understand its intent.
Score 2: The question includes some redundant information, but it does not
impact the understanding of its meaning.
Score 3: The question is concise and does not contain any unnecessary
information.

## Relevance
Whether the question is relevant to the given passage and asks for key
information from the passage

Score 1: The question is completely unrelated to the passage.
Score 2: The question is somewhat related to the passage and it asks for
non-crucial information related to the passage.
Score 3: The question is relevant to the context, and the information it seeks
is crucial to the passage.

## Consistency
Whether the information presented in the question is consistent with the
passage and without any contradictions or hallucinations

Score 1: The question contains factual contradictions with the passage or
logical errors.
Score 2: The information sought in the question is not fully described in the
passage.
Score 3: The information in the question is entirely consistent with the
passage.

## Answerability
Whether the question can be distinctly answered based on the passage

Score 1: The question cannot be answered based on the provided passage.
Score 2: The question can be partially answered based on the provided passage,
or the answer to the question can be inferred to some extent.
Score 3: The question can be answered definitively based on the given passage."""

_RUBRIC_EXAMPLES = """Example 1
Passage: Richard "Rick" Ducommun (July 3, 1952 - June 12, 2015) was a Canadian
actor, comedian and writer who appeared in films and television. The Burbs is a
1989 American comedy thriller film directed by Joe Dante starring Tom Hanks,
Bruce Dern, Carrie Fisher, Rick Ducommun, Corey Feldman, Wendy Schaal and Henry
Gibson. The film was written by Dana Olsen, who also has a cameo in the movie.
The film pokes fun at suburban environments and their eccentric dwellers.

Question: What star if the Burbs was Canadian?
Scores: {"fluency": 1, "clarity": 1, "conciseness": 3, "relevance": 3, "consistency": 3, "answerability": 1}

Example 2
Passage: At the same time the Mongols imported Central Asian Muslims to serve
as administrators in China, the Mongols also sent Han Chinese and Khitans from
China to serve as administrators over the Muslim population in Bukhara in
Central Asia, using foreigners to curtail the power of the local peoples of
both lands. Han Chinese were moved to Central Asian areas like Besh Baliq,
Almaliq, and Samarqand by the Mongols where they worked as artisans and
farmers. Alans were recruited into the Mongol forces with one unit called
"Right Alan Guard" which was combined with "recently surrendered" soldiers,
Mongols, and Chinese soldiers stationed in the area of the former Kingdom of
Qocho and in Besh Balikh the Mongols established a Chinese military colony led
by Chinese general Qi Kongzhi (Ch'i Kung-chih). After the Mongol conquest of
Central Asia by Genghis Khan, foreigners were chosen as administrators and
co-management with Chinese and Qara-Khitays (Khitans) of gardens and fields in
Samarqand was put upon the Muslims as a requirement since Muslims were not
allowed to manage without them. The Mongol appointed Governor of Samarqand was
a Qara-Khitay (Khitan), held the title Taishi, familiar with Chinese culture
his name was Ahai.

Question: Where did the Mongols work?
Scores: {"fluency": 3, "clarity": 2, "conciseness": 3, "relevance": 3, "consistency": 3, "answerability": 1}

Example 3
Passage: "Domino Dancing" is a song recorded by the British synthpop duo Pet
Shop Boys, released as the lead single from their 1988 album, "Introspective".
It reached number 7 on the UK Singles Chart. Introspective is the third studio
album by English synthpop duo Pet Shop Boys. It was first released on 11
October 1988 and is the Pet Shop Boys' second-best-selling album, selling over
4.5 million copies worldwide. (Their fifth studio album, "Very", sold more than
5 million copies worldwide.).

Question: "Domino Dancing" is a song recorded by the British synthpop duo Pet
Shop Boys, released as the lead single from their 1988 album, "Introspective".
It reached number 7 on the UK Singles Chart, which month was the album
"Introspective" first released?
Scores: {"fluency": 2, "clarity": 3, "conciseness": 2, "relevance": 3, "consistency": 3, "answerability": 3}

Example 4
Passage: With International Criminal Court trial dates in 2013 for both
President Kenyatta and Deputy President William Ruto related to the 2007
election aftermath, US President Barack Obama chose not to visit the country
during his mid-2013 African trip. Later in the summer, Kenyatta visited China
at the invitation of President Xi Jinping after a stop in Russia and not having
visited the United States as president. In July 2015 Obama visited Kenya, as
the first American president to visit the country while in office.

Question: Why did President Kenyatta and Deputy President William Ruto not
visit the United States in 2013?
Scores: {"fluency": 3, "clarity": 3, "conciseness": 3, "relevance": 3, "consistency": 2, "answerability": 1}

Example 5
Passage: Even before Washington returned, Dinwiddie had sent a company of 40
men under William Trent to that point, where in the early months of 1754 they
began construction of a small stockaded fort. Governor Duquesne sent additional
french forces under Claude-Pierre Pecaudy de Contrecœur to relieve Saint-Pierre
during the same period, and Contrecœur led 500 men south from Fort Venango on
April 5, 1754. When these forces arrived at the fort on April 16, Contrecœur
generously allowed Trent's small company to withdraw. He purchased their
construction tools to continue building what became Fort Duquesne.

Question: How many men did Duquesne send to relieve Saint-Pierre?
Scores: {"fluency": 3, "clarity": 3, "conciseness": 3, "relevance": 3, "consistency": 3, "answerability": 3}

Example 6
Passage: There are fifteen fraternities and seven sororities at the University
of Chicago, as well as one co-ed community service fraternity, Alpha Phi Omega.
Four of the sororities are members of the National Panhellenic Conference, and
ten of the fraternities form the University of Chicago Interfraternity Council.
In 2002, the Associate Director of Student Activities estimated that 8-10
percent of undergraduates were members of fraternities or sororities. The
student activities office has used similar figures, stating that one in ten
undergraduates participate in Greek life.

Question: How many fraternities are at the University of Chicago?
Scores: {"fluency": 3, "clarity": 3, "conciseness": 3, "relevance": 3, "consistency": 3, "answerability": 3}"""

_RUBRIC = grounded(
    f"""ROLE
You are given a passage of text along with a question about its content
generated by an automated process.

ACTION
You must score it in multiple dimensions, as define below. For each
dimension, we provide a description of it, as well as guidelines for a
numeric score. In all cases, the score is a number between 1 and 3.

STEPS
{_RUBRIC_STEPS}

CONTEXT
{_ANY_LANGUAGE}

EXAMPLES
{_RUBRIC_EXAMPLES}

FORMAT
Please provide your answer as a json response in the format {{score name: score}}
as shown in the examples above. Do not provide an explanation, just the json
output."""
)

#: The paper's own layout, which its examples follow.
_RUBRIC_USER = """Passage: {{passages}}

Question: {{question}}"""


#: Every template, by artefact and then by metric, in the order a reader
#: should see them. What a kind is asked is exactly what is listed here:
#: adding a metric is adding an entry, and nothing else reads a metric name.
TEMPLATES: dict[str, tuple[Template, ...]] = {
    ArtifactKind.FACT: (
        Template(
            metric=JudgeMetric.HALLUCINATION,
            kind=ArtifactKind.FACT,
            system=_FACT_HALLUCINATION,
            user=_FACT_USER,
            fields=("statement", "evidence"),
            material=("statement", "evidence"),
        ),
        Template(
            metric=JudgeMetric.RELEVANCE,
            kind=ArtifactKind.FACT,
            system=_FACT_RELEVANCE,
            user=_FACT_USER,
            fields=("statement", "evidence"),
            material=("statement", "evidence"),
        ),
        Template(
            metric=JudgeMetric.TOXICITY,
            kind=ArtifactKind.FACT,
            system=_FACT_TOXICITY,
            user=_FACT_TEXT_ONLY,
            fields=("statement",),
            material=("statement",),
        ),
    ),
    ArtifactKind.TOPIC: (
        Template(
            metric=JudgeMetric.SUMMARIZATION,
            kind=ArtifactKind.TOPIC,
            system=_TOPIC_SUMMARIZATION,
            user=_TOPIC_USER,
            fields=("terms", "label"),
        ),
        Template(
            metric=JudgeMetric.RELEVANCE,
            kind=ArtifactKind.TOPIC,
            system=_TOPIC_RELEVANCE,
            user=_TOPIC_TERMS_ONLY,
            fields=("terms",),
        ),
    ),
    ArtifactKind.QUESTION: (
        Template(
            metric=JudgeMetric.HALLUCINATION,
            kind=ArtifactKind.QUESTION,
            system=_QUESTION_HALLUCINATION,
            user=_QUESTION_USER,
            fields=("question", "answer", "facts"),
            material=("facts",),
        ),
        Template(
            metric=JudgeMetric.QA_CORRECTNESS,
            kind=ArtifactKind.QUESTION,
            system=_QUESTION_QA_CORRECTNESS,
            user=_QUESTION_USER,
            fields=("question", "answer", "facts"),
            material=("facts",),
        ),
        Template(
            metric=JudgeMetric.REFUSAL,
            kind=ArtifactKind.QUESTION,
            system=_QUESTION_REFUSAL,
            user=_QUESTION_TEXT_ONLY,
            fields=("question", "answer"),
        ),
        Template(
            metric=JudgeMetric.CONCISENESS,
            kind=ArtifactKind.QUESTION,
            system=_QUESTION_CONCISENESS,
            user=_QUESTION_TEXT_ONLY,
            fields=("question", "answer"),
        ),
        Template(
            metric=JudgeMetric.TOXICITY,
            kind=ArtifactKind.QUESTION,
            system=_QUESTION_TOXICITY,
            user=_QUESTION_TEXT_ONLY,
            fields=("question", "answer"),
        ),
        # Recorded as six metrics, under the one name the prompt catalogue
        # files it by.
        Rubric(
            metric="rubric",
            kind=ArtifactKind.QUESTION,
            system=_RUBRIC,
            user=_RUBRIC_USER,
            fields=("passages", "question"),
            roots_only=True,
            material=("passages",),
        ),
    ),
}


def metrics_of(kind: str) -> tuple[str, ...]:
    """Which metrics one artefact kind is judged on, every one a template reports."""
    return tuple(metric for one in TEMPLATES[kind] for metric in one.metrics)


def direction_of(metric: str) -> str:
    """How one metric is optimised, as phoenix-evals declares it.

    Read by whatever reports a mean, because `hallucination`'s and
    `toxicity`'s run the other way: a project whose mean hallucination score
    is high is one whose judge found hallucinations, and a reader shown that
    beside four maximised metrics without this would read it upside down.
    """
    return _DIRECTION[metric]
