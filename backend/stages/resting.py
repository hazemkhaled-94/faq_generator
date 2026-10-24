"""The questions that rest on what a rerun would replace.

A re-chunk or a re-extraction replaces passages and facts, and a question
resting on one is rejected as `source_changed`. Questions nobody has accepted
cost nothing to lose; the ones a person accepted, reviewed or released are the
dataset, so a rerun over them asks first.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select

from database.qa_generator import FactPassage, Question, QuestionFact, QuestionStatus


@dataclass(frozen=True)
class Resting:
    """How many questions rest on a set of passages, by what was decided of them.

    Attributes:
        questions: Questions that are released, accepted or reviewed.
        released: Of them, those in a release.
        accepted: Those whose status is accepted, released ones included.
        reviewed: Those a person gave a verdict.
    """

    questions: int
    released: int
    accepted: int
    reviewed: int

    def __bool__(self) -> bool:
        """Whether anything is at risk."""
        return self.questions > 0

    def refusal(self, how: str) -> str:
        """Says what the rerun would cost, and how to go on regardless."""
        return (
            f"{self.questions} question(s) rest on what this rerun replaces "
            f"({self.released} released, {self.accepted} accepted, "
            f"{self.reviewed} reviewed). They would be rejected as "
            f"source_changed and leave their release; nothing is deleted. "
            f"Go on with {how}."
        )


def resting_on(session, passages) -> Resting:
    """Counts the released, accepted or reviewed questions on these passages.

    Args:
        session: An open session.
        passages: A select of passage ids.
    """
    resting = (
        select(QuestionFact.question_id)
        .join(FactPassage, FactPassage.fact_id == QuestionFact.fact_id)
        .where(FactPassage.passage_id.in_(passages))
    )
    row = session.execute(
        select(
            func.count(),
            func.count().filter(Question.release_id.is_not(None)),
            func.count().filter(Question.status == QuestionStatus.ACCEPTED),
            func.count().filter(Question.reviewed_verdict.is_not(None)),
        ).where(
            Question.id.in_(resting),
            (Question.release_id.is_not(None))
            | (Question.status == QuestionStatus.ACCEPTED)
            | (Question.reviewed_verdict.is_not(None)),
        )
    ).one()
    return Resting(*row)
