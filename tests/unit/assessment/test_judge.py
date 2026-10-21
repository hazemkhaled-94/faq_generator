"""Asking the judge, and what happens when it will not answer.

The distinction this file exists for is abstention against refusal. A model
that could not be reached has found nothing wrong with the artefact, and a
phase that recorded that as disapproval would fill a review queue with rows
whose only fault was that the runtime was restarting.
"""

from __future__ import annotations

import pytest

from assessment.judge import Judge, JudgeUnavailable
from assessment.models import ArtifactToJudge
from assessment.templates import RUBRIC, TEMPLATES, Rubric
from database.qa_generator import ArtifactKind, JudgeMetric
from llm.client import ModelUnavailable

#: Which of each metric's two labels approves, by the shape's name.
_GOOD = {
    one.shape().__name__: one.good
    for group in TEMPLATES.values()
    for one in group
    if not isinstance(one, Rubric)
}

#: The paper's six scores, all of them 3, by the name its reply gives them.
_FULL_MARKS = {one.removeprefix("rubric_"): 3 for one in RUBRIC}


def _approving(shape) -> str:
    """The label that approves, for whichever metric this shape belongs to."""
    return _GOOD[shape.__name__]


class _Answering:
    """A client that answers every call with a named label."""

    model = "test/judge"

    def __init__(
        self, *labels: str, fails: int = 0, scores: dict[str, int] | None = None
    ) -> None:
        """Answers with each label in turn, after `fails` refusals.

        The rubric is answered with `scores`, or full marks.
        """
        self._labels = list(labels)
        self._fails = fails
        self._scores = scores or _FULL_MARKS
        self.asked: list[tuple[str, str]] = []

    def answer(self, *, system, user, shape, prompt_version=None):
        """Answers one judgement, or refuses."""
        self.asked.append((shape.__name__, user))
        if self._fails:
            self._fails -= 1
            raise ModelUnavailable("the runtime is restarting")
        if shape.__name__ == "_Rubric":
            return shape(**self._scores)
        # Left to itself, each metric's own approving label. A fixed
        # default would fail the shape's Literal the moment a test asked
        # about a metric whose rails are not the hallucination pair.
        label = self._labels.pop(0) if self._labels else _approving(shape)
        return shape(label=label, explanation="  because   the evidence  says so ")


def _fact() -> ArtifactToJudge:
    """One fact for the judge to read."""
    return ArtifactToJudge(
        assessment_id=1,
        kind=ArtifactKind.FACT,
        artifact_id=7,
        fields={"statement": "A reply is due in five days.", "evidence": "…"},
    )


def test_every_metric_of_a_kind_is_asked() -> None:
    """One call per judgement, never one call asking all of them."""
    client = _Answering("factual", "relevant", "non-toxic")

    judged = Judge(client).judge(_fact())

    assert [one.metric for one in judged] == [
        JudgeMetric.HALLUCINATION,
        JudgeMetric.RELEVANCE,
        JudgeMetric.TOXICITY,
    ]
    assert len(client.asked) == 3
    assert {shape for shape, _ in client.asked} == {
        "_Hallucination",
        "_Relevance",
        "_Toxicity",
    }


def test_the_artefact_reaches_the_prompt() -> None:
    """The statement and its evidence, substituted into the template."""
    client = _Answering()

    Judge(client).judge(_fact())

    assert "A reply is due in five days." in client.asked[0][1]
    assert "{{statement}}" not in client.asked[0][1]


def test_a_label_carries_the_score_and_the_side_phoenix_gives_it() -> None:
    """`factual` approves and scores 0.0, which is the confusable pair."""
    judged = Judge(_Answering("factual", "relevant", "non-toxic")).judge(_fact())
    by_metric = {one.metric: one for one in judged}

    assert by_metric[JudgeMetric.HALLUCINATION].approved is True
    assert by_metric[JudgeMetric.HALLUCINATION].score == 0.0
    assert by_metric[JudgeMetric.RELEVANCE].approved is True
    assert by_metric[JudgeMetric.RELEVANCE].score == 1.0


def test_a_hallucinated_label_does_not_approve() -> None:
    """And scores 1.0, because the metric is minimised."""
    judged = Judge(_Answering("hallucinated", "relevant", "non-toxic")).judge(_fact())

    assert judged[0].approved is False
    assert judged[0].score == 1.0


def test_an_explanation_is_kept_and_its_whitespace_is_not() -> None:
    """A reviewer reads this. It must not arrive with the model's spacing."""
    judged = Judge(_Answering()).judge(_fact())

    assert judged[0].explanation == "because the evidence says so"


def test_one_metric_failing_still_records_the_others() -> None:
    """An abstention is a judgement nobody made, not a refusal.

    Losing one opinion must not fail a row the rest of the metrics judged,
    so what comes back is short rather than empty.
    """
    judged = Judge(_Answering("relevant", "non-toxic", fails=1)).judge(_fact())

    assert [one.metric for one in judged] == [
        JudgeMetric.RELEVANCE,
        JudgeMetric.TOXICITY,
    ]


def test_no_metric_answering_is_a_failed_row_and_not_a_refusal() -> None:
    """The model being down is a row to retry, not an artefact to reject.

    This is the whole distinction the phase rests on. Recorded as
    disapproval, a Phoenix that was restarting would read as a corpus the
    judge rejected.
    """
    client = _Answering(fails=len(TEMPLATES[ArtifactKind.FACT]))

    with pytest.raises(JudgeUnavailable, match="answered none"):
        Judge(client).judge(_fact())


def _question(answer: str = "Five days.", root: str = "True") -> ArtifactToJudge:
    """One question, with every field the repository claims it with."""
    return ArtifactToJudge(
        assessment_id=2,
        kind=ArtifactKind.QUESTION,
        artifact_id=9,
        fields={
            "question": "How long is allowed for a reply?",
            "answer": answer,
            "facts": "- A reply is due in five days.",
            "passages": "A reply is due in five days of the request.",
            "root": root,
        },
    )


def test_a_question_is_asked_every_metric_its_kind_declares() -> None:
    """Eleven of them, and three have no counterpart anywhere upstream.

    `qa_correctness` asks whether the answer answers the question,
    `refusal` whether it is an answer at all, and `conciseness` whether it
    is only the answer. No gate asks any of those. The paper's six come
    after them, about the question rather than its answer.
    """
    client = _Answering("factual", "correct", "answered", "concise", "non-toxic")

    judged = Judge(client).judge(_question())

    assert [one.metric for one in judged] == [
        JudgeMetric.HALLUCINATION,
        JudgeMetric.QA_CORRECTNESS,
        JudgeMetric.REFUSAL,
        JudgeMetric.CONCISENESS,
        JudgeMetric.TOXICITY,
        *RUBRIC,
    ]
    assert all(one.approved for one in judged)


def test_an_answer_that_declines_to_answer_is_caught_by_nothing_else() -> None:
    """The judgement this phase added that no gate makes.

    A question marked answerable whose stored answer is "the document does
    not specify" is well formed, the right length, cites its facts and
    leaks no source. Every gate passes it, and a benchmark built from it
    scores a chatbot against a non-answer.
    """
    client = _Answering("factual", "correct", "refused", "concise", "non-toxic")
    question = _question(answer="The document does not specify a period.")

    judged = {one.metric: one for one in Judge(client).judge(question)}

    assert judged[JudgeMetric.REFUSAL].label == "refused"
    assert judged[JudgeMetric.REFUSAL].approved is False
    assert judged[JudgeMetric.REFUSAL].score == 1.0


def test_one_call_returns_the_six_scores() -> None:
    """The paper's judge, asked the paper's way: all six in one reply.

    Each score is its own judgement, labelled as the paper scored it and
    normalised as the paper normalises a mean. Only a 3 approves.
    """
    client = _Answering(
        scores={
            "fluency": 1,
            "clarity": 1,
            "conciseness": 3,
            "relevance": 3,
            "consistency": 3,
            "answerability": 1,
        }
    )

    judged = Judge(client).judge(_question())

    assert [
        (one.metric, one.label, one.score, one.approved)
        for one in judged
        if one.metric in RUBRIC
    ] == [
        (JudgeMetric.RUBRIC_FLUENCY, "1", 0.0, False),
        (JudgeMetric.RUBRIC_CLARITY, "1", 0.0, False),
        (JudgeMetric.RUBRIC_CONCISENESS, "3", 1.0, True),
        (JudgeMetric.RUBRIC_RELEVANCE, "3", 1.0, True),
        (JudgeMetric.RUBRIC_CONSISTENCY, "3", 1.0, True),
        (JudgeMetric.RUBRIC_ANSWERABILITY, "1", 0.0, False),
    ]
    assert len(client.asked) == 6
    assert (
        "_Rubric",
        (
            "Passage: A reply is due in five days of the request.\n\n"
            "Question: How long is allowed for a reply?"
        ),
    ) in client.asked


@pytest.mark.parametrize(("root", "calls", "due"), [("False", 5, 5), ("True", 6, 11)])
def test_a_follow_up_is_not_asked_the_rubric(root: str, calls: int, due: int) -> None:
    """A follow-up leans on the turn before it, which the rubric is not shown.

    So it is asked the five about its answer and not the paper's six, and is
    due five metrics where a root is due eleven from six calls.
    """
    client = _Answering()
    judge = Judge(client)

    judged = judge.judge(_question(root=root))

    assert len(client.asked) == calls
    assert judge.due(_question(root=root)) == due
    assert len(judged) == due
