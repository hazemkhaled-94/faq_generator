"""The judging templates, and the two things about them that must not drift.

Phoenix is a shared vocabulary. A `hallucination` annotation posted by this
pipeline sits in the same Evaluations view as one posted by anything else
built on arize-phoenix-evals, and a reader sorts and charts them together.
So the name, the labels, the scores and the optimisation direction are that
package's, and what is checked here is that they hold together.

The prompts are ours. What is checked about those is only that every
placeholder a template carries is one the repository actually supplies: a
template variable nobody fills reaches the model as the braces themselves,
with no error anywhere and an answer that looks fine.
"""

from __future__ import annotations

import re

import pytest

from assessment.templates import (
    PROMPT_VERSION,
    RUBRIC,
    TEMPLATES,
    Rubric,
    direction_of,
    metrics_of,
)
from database.qa_generator import ArtifactKind, JudgeMetric

#: Every template, flattened, so one failure names one judgement.
EVERY = [one for group in TEMPLATES.values() for one in group]

#: The templates answering with one label, which is all but the rubric.
SINGLE = [one for one in EVERY if not isinstance(one, Rubric)]

#: The paper's judge, as the question kind asks it.
THE_RUBRIC = next(one for one in EVERY if isinstance(one, Rubric))

#: A `{{name}}` in a template.
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def test_every_kind_is_judged() -> None:
    """A kind with no template is a kind the queue would claim and drop."""
    assert set(TEMPLATES) == {
        ArtifactKind.FACT,
        ArtifactKind.TOPIC,
        ArtifactKind.QUESTION,
    }
    assert all(TEMPLATES.values()), "a kind with no judgement is not judged"


@pytest.mark.parametrize("one", EVERY, ids=lambda one: f"{one.kind}-{one.metric}")
def test_a_metric_is_one_the_database_accepts(one) -> None:
    """A metric outside the CHECK constraint fails at write, not at ask."""
    assert set(one.metrics) <= set(JudgeMetric)


@pytest.mark.parametrize("one", EVERY, ids=lambda one: f"{one.kind}-{one.metric}")
def test_every_placeholder_is_declared(one) -> None:
    """A placeholder nobody fills reaches the model as its own braces.

    The static check over the other prompt modules counts each name twice,
    once in the template and once at its `.replace`. This module renders
    generically, so the pairing is between the template and the `fields`
    it declares - and that is what `rendered` refuses to go without.
    """
    assert set(PLACEHOLDER.findall(one.user)) == set(one.fields)


@pytest.mark.parametrize("one", EVERY, ids=lambda one: f"{one.kind}-{one.metric}")
def test_rendering_without_a_field_is_refused(one) -> None:
    """Rather than sending the braces and getting a plausible answer back."""
    with pytest.raises(KeyError, match=one.fields[0]):
        one.rendered()


@pytest.mark.parametrize("one", EVERY, ids=lambda one: f"{one.kind}-{one.metric}")
def test_rendering_leaves_no_placeholder_behind(one) -> None:
    """Every declared field is substituted, not just checked for."""
    filled = one.rendered(**{name: f"<{name}>" for name in one.fields})

    assert not PLACEHOLDER.findall(filled)
    assert all(f"<{name}>" in filled for name in one.fields)


@pytest.mark.parametrize("one", SINGLE, ids=lambda one: f"{one.kind}-{one.metric}")
def test_a_score_is_zero_or_one_and_the_shape_is_closed(one) -> None:
    """The column is CHECKed between 0 and 1, and the answer is a Literal.

    A `Literal` of the rails is what makes an answer outside them a schema
    failure instructor retries, rather than a string nothing maps to a
    score.
    """
    assert set(one.scores.values()) == {0.0, 1.0}
    assert one.scores[one.good] in (0.0, 1.0)

    field = one.shape().model_fields["label"]

    assert set(getattr(field.annotation, "__args__", ())) == set(one.labels)


def test_hallucination_is_scored_the_way_phoenix_scores_it() -> None:
    """The one metric here whose good label scores ZERO.

    Its optimisation direction is minimise, so `hallucinated` is 1.0 and
    `factual` is 0.0 - the opposite of the other three. This is the single
    most confusable thing in this package: a reader summing scores across
    metrics would be adding a hallucination rate to a relevance rate, which
    is why `approved` is stored per metric rather than derived from the
    score.
    """
    one = TEMPLATES[ArtifactKind.FACT][0]

    assert one.metric == JudgeMetric.HALLUCINATION
    assert one.good == "factual"
    assert one.scores["factual"] == 0.0
    assert one.scores["hallucinated"] == 1.0
    assert direction_of(JudgeMetric.HALLUCINATION) == "minimize"


@pytest.mark.parametrize(
    "metric",
    [
        JudgeMetric.RELEVANCE,
        JudgeMetric.QA_CORRECTNESS,
        JudgeMetric.SUMMARIZATION,
        JudgeMetric.CONCISENESS,
    ],
)
def test_every_maximised_metric_says_so(metric: str) -> None:
    """So a mean read as "how much the judge backed" is right for these."""
    assert direction_of(metric) == "maximize"


@pytest.mark.parametrize(
    "metric",
    [JudgeMetric.HALLUCINATION, JudgeMetric.TOXICITY],
)
def test_the_minimised_metrics_score_one_for_the_bad_label(metric: str) -> None:
    """Both of them, so neither is averaged in with the rest by accident."""
    one = next(t for group in TEMPLATES.values() for t in group if t.metric == metric)

    assert direction_of(metric) == "minimize"
    assert one.scores[one.good] == 0.0


def test_a_refusal_approves_on_the_label_that_scores_zero() -> None:
    """phoenix-evals calls this one NEUTRAL, and here it is not.

    A refusal is not a defect in a chat assistant, which is what that
    package is usually pointed at. In a reference dataset it is exactly
    one: an answerable question whose stored answer is "the document does
    not say" is a row every gate passes and no benchmark should carry.

    So the direction stays theirs - a reader who knows `refusal` should
    not find it declaring something else - and `answered` is what
    approves.
    """
    one = next(
        t
        for group in TEMPLATES.values()
        for t in group
        if t.metric == JudgeMetric.REFUSAL
    )

    assert direction_of(JudgeMetric.REFUSAL) == "neutral"
    assert one.good == "answered"
    assert one.scores["answered"] == 0.0
    assert one.scores["refused"] == 1.0


def test_a_shape_is_named_after_its_metric() -> None:
    """The shape's name is what reaches the span and the log line.

    `tag.tags` in Phoenix and `llm.shape` in Grafana are both the class
    name, so seven judgements sharing one would be seven calls nothing
    could tell apart.
    """
    names = {one.shape().__name__ for one in EVERY}

    assert len(names) == len({one.metric for one in EVERY})
    assert "_Hallucination" in names


def test_a_question_is_judged_on_more_than_a_fact() -> None:
    """Eleven judgements against three, and most are about the answer.

    A fact is asked whether its evidence supports it and whether the
    evidence is about the right thing. A question is asked the first of
    those about its ANSWER, plus whether the answer answers the question -
    which is the judgement that has no counterpart upstream - and then the
    paper's six about the question itself, from one call.
    """
    assert metrics_of(ArtifactKind.QUESTION) == (
        JudgeMetric.HALLUCINATION,
        JudgeMetric.QA_CORRECTNESS,
        JudgeMetric.REFUSAL,
        JudgeMetric.CONCISENESS,
        JudgeMetric.TOXICITY,
        JudgeMetric.RUBRIC_FLUENCY,
        JudgeMetric.RUBRIC_CLARITY,
        JudgeMetric.RUBRIC_CONCISENESS,
        JudgeMetric.RUBRIC_RELEVANCE,
        JudgeMetric.RUBRIC_CONSISTENCY,
        JudgeMetric.RUBRIC_ANSWERABILITY,
    )
    assert metrics_of(ArtifactKind.FACT) == (
        JudgeMetric.HALLUCINATION,
        JudgeMetric.RELEVANCE,
        JudgeMetric.TOXICITY,
    )


def test_a_question_is_asked_its_relevance_by_the_papers_judge_alone() -> None:
    """One judge of whether the passages bear on the question, not two.

    The paper's answerability agreed with the labelled review at least as
    well as the question-relevance template did, in both languages, so
    template version 4 asks a question the paper's six and no `relevance`.
    A fact and a topic are still asked theirs, and a question's relevance
    row stored under version 3 stays readable under the same name.
    """
    assert JudgeMetric.RELEVANCE not in metrics_of(ArtifactKind.QUESTION)
    assert JudgeMetric.RELEVANCE in metrics_of(ArtifactKind.FACT)
    assert JudgeMetric.RELEVANCE in metrics_of(ArtifactKind.TOPIC)
    assert direction_of(JudgeMetric.RELEVANCE) == "maximize"
    assert PROMPT_VERSION == "4"


def test_a_template_says_the_material_may_be_in_any_language() -> None:
    """The German half is why this phase cannot be a gate.

    Every template says so explicitly, because a judge must not start
    reasoning about the language rather than the artefact.
    """
    for one in EVERY:
        assert "any language" in one.system, one.metric


def test_the_version_is_a_version() -> None:
    """Recorded on every row, so two template versions are two judgements."""
    assert PROMPT_VERSION and PROMPT_VERSION.strip() == PROMPT_VERSION


@pytest.mark.parametrize("metric", RUBRIC)
@pytest.mark.parametrize(("score", "normalised"), [(1, 0.0), (2, 0.5), (3, 1.0)])
def test_a_rubric_score_is_the_papers_normalised_score(
    metric: str, score: int, normalised: float
) -> None:
    """(s - 1) / 2, the shift the paper puts each benchmark's mean through.

    Stored per question, so the paper's normalised mean of a set is the mean
    of this column over it. Only a 3 approves: a 2 is the paper's "partly",
    and `approved` means every metric landed on its good side. No
    explanation, because the paper asks for none.
    """
    said = THE_RUBRIC.shape()(**{one.removeprefix("rubric_"): score for one in RUBRIC})

    one = next(one for one in THE_RUBRIC.judged(said) if one.metric == metric)

    assert (one.label, one.score, one.approved, one.explanation) == (
        str(score),
        normalised,
        score == 3,
        "",
    )
    assert direction_of(metric) == "maximize"


#: The paper's six dimensions, each heading and its definition as Figures 5-7
#: print them.
DIMENSIONS = (
    (
        "## Fluency Whether the question is wellformed, grammatically correct, "
        "coherent, and fluent enough to be understood."
    ),
    (
        "## Clarity Whether the question is expressed clearly and unambiguously, "
        "avoiding excessive generality and ambiguity"
    ),
    (
        "## Conciseness Whether the question is concise and not abnormally verbose "
        "with redundant modifiers"
    ),
    (
        "## Relevance Whether the question is relevant to the given passage and asks "
        "for key information from the passage"
    ),
    (
        "## Consistency Whether the information presented in the question is "
        "consistent with the passage and without any contradictions or "
        "hallucinations"
    ),
    (
        "## Answerability Whether the question can be distinctly answered based on "
        "the passage"
    ),
)

#: The paper's six example questions.
EXAMPLES = (
    "Question: What star if the Burbs was Canadian?",
    "Question: Where did the Mongols work?",
    (
        'Question: "Domino Dancing" is a song recorded by the British synthpop duo '
        "Pet Shop Boys, released as the lead single from their 1988 album, "
        '"Introspective". It reached number 7 on the UK Singles Chart, which month '
        'was the album "Introspective" first released?'
    ),
    (
        "Question: Why did President Kenyatta and Deputy President William Ruto not "
        "visit the United States in 2013?"
    ),
    "Question: How many men did Duquesne send to relieve Saint-Pierre?",
    "Question: How many fraternities are at the University of Chicago?",
)


def test_the_rubric_is_the_papers_prompt() -> None:
    """Figures 5-7 in the paper's words, under this repository's headings.

    Read with its whitespace folded, because the words are the paper's and
    the line breaks were its PDF's. Example 1's reply is the one change: the
    paper prints `"clarity: 1`, and a judge shown malformed JSON as the
    answer it should give is being taught to give it.
    """
    said = " ".join(THE_RUBRIC.system.split())

    for one in (*DIMENSIONS, *EXAMPLES):
        assert one in said, one[:40]
    assert '"clarity": 1' in said
    assert '"clarity: 1' not in said
    assert "any language" in said
    assert THE_RUBRIC.user == "Passage: {{passages}}\n\nQuestion: {{question}}"
    assert THE_RUBRIC.roots_only
