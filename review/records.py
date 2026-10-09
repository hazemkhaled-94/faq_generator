"""Reading the rows a person should look at, and writing back what they said.

Three things in this pipeline are decided by a model and have somewhere for
a person to disagree: a fact's verdict, a topic's name, and whether a
question is any good. Those are the three datasets, and this is the half of
them that touches the database.

Stratified samples, not the first N. A review is a sample - nobody reads
twenty thousand facts - and a sample taken in id order is a sample of
whatever was extracted first, which for this corpus is one document. Drawn
evenly across the verdicts instead, because the question a review answers
is "is the checker right", and a sample of only what it accepted cannot
answer it. That the bands and the rejection codes exist to be sampled on
is what facts.rejection_code and questions.difficulty were for.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, NamedTuple

from sqlalchemy import case, func, select, update

from database.qa_generator import Fact, Question, ReviewVerdict, Topic
from database.qa_generator.repository import Repository

#: Each dataset's id column, the text its record shows, and the row's own
#: last decision: when it was made, or decided since. Keyed by the names in
#: `review.datasets`.
_HELD = {
    "facts": (
        Fact.id,
        Fact.statement,
        func.greatest(Fact.created_at, Fact.reviewed_at),
    ),
    "questions": (
        Question.id,
        Question.question_text,
        func.greatest(
            Question.created_at, Question.status_changed_at, Question.reviewed_at
        ),
    ),
    "topic-labels": (
        Topic.id,
        func.array_to_string(Topic.top_terms, ", "),
        func.greatest(Topic.fitted_at, Topic.decided_at),
    ),
}


class Held(NamedTuple):
    """What a row reads now, and when it was last decided."""

    text: str
    decided: datetime | None


@dataclass(frozen=True)
class FactRow:
    """One fact as a reviewer sees it."""

    id: int
    statement: str
    evidence: str
    kind: str
    validated: bool
    rejection_code: str | None
    validation_error: str | None


@dataclass(frozen=True)
class QuestionRow:
    """One question as a reviewer sees it."""

    id: int
    question_text: str
    target_answer: str | None
    answerable: bool
    difficulty: str | None
    question_type: str | None
    language: str
    status: str
    rejected_reason: str | None
    facts: list[str]
    #: The sentences those facts were drawn from, and the answer said at
    #: length. A reviewer is asked whether the answer follows from the
    #: facts, which is a question about the material and not about the
    #: statements somebody wrote from it.
    evidence: list[str] = field(default_factory=list)
    answer_explanation: str | None = None
    #: How close the weakest measuring gate came to refusing it. What a
    #: reviewer sorts by: the questions that survived a gate by nothing are
    #: the ones worth an opinion first. None where nothing measured it.
    confidence: float | None = None


def _even(total: int, groups: int) -> int:
    """How many to take from each group so the whole sample is `total`.

    At least one: a group with a share below one is a rejection code that
    fired twice in a corpus, and those are the interesting ones.
    """
    return max(1, total // max(groups, 1))


class ReviewRepository(Repository):
    """The rows a review is drawn from, and the verdicts it produces."""

    def facts(self, sample: int | None) -> list[FactRow]:
        """Draws a sample of facts, spread over the verdicts.

        Everything the checker rejected is grouped by its code, and what it
        accepted is one more group beside them, so a reviewer sees both the
        drops and the keeps in one sitting.

        `sample` of None takes every unreviewed fact instead, which is what
        `--all` asks for: the dataset is then the corpus rather than a draw
        from it, and a reviewer filters in Argilla rather than trusting the
        draw to have included what they were looking for.
        """
        with self._session() as session:
            groups = [
                code
                for (code,) in session.execute(
                    select(Fact.rejection_code).group_by(Fact.rejection_code)
                )
            ]
            each = None if sample is None else _even(sample, len(groups))
            rows: list[FactRow] = []
            for code in groups:
                found = session.execute(
                    select(
                        Fact.id,
                        Fact.statement,
                        Fact.evidence_text,
                        Fact.kind,
                        Fact.validated,
                        Fact.rejection_code,
                        Fact.validation_error,
                    )
                    .where(
                        Fact.rejection_code.is_(code)
                        if code is None
                        else Fact.rejection_code == code,
                        # Never the same row twice: a second push would
                        # otherwise ask for a verdict already given.
                        Fact.reviewed_verdict.is_(None),
                    )
                    # Randomly, so two pushes are two samples rather than
                    # the same rows in the same order.
                    .order_by(Fact.id if each is None else func.random())
                    .limit(each)
                ).all()
                rows += [FactRow(*one) for one in found]
        return rows

    def questions(
        self, sample: int | None, ids: Sequence[int] | None = None
    ) -> list[QuestionRow]:
        """Draws a sample of questions, spread over difficulty and verdict.

        Both, because they are the two things a reviewer is judging at
        once: whether the gate was right, and whether a question the band
        calls hard is actually hard.

        `ids` replaces the sampling with exactly those rows, in id order.
        That is how a queue somebody else built gets reviewed - the
        disagreements the Assessment page marks, where the gates kept a
        question and the judge refused it. A stratified sample cannot find those: they are
        spread over every band and every verdict and are rare in all of
        them, which is exactly the shape a proportional draw misses.
        """
        if ids:
            with self._session() as session:
                found = session.execute(
                    select(Question).where(Question.id.in_(ids)).order_by(Question.id)
                ).scalars()
                return [self._question(one) for one in found]
        with self._session() as session:
            groups = session.execute(
                select(Question.difficulty, Question.rejected_reason).group_by(
                    Question.difficulty, Question.rejected_reason
                )
            ).all()
            each = None if sample is None else _even(sample, len(groups))
            rows: list[QuestionRow] = []
            for difficulty, reason in groups:
                found = session.execute(
                    select(Question)
                    .where(
                        Question.difficulty.is_(difficulty)
                        if difficulty is None
                        else Question.difficulty == difficulty,
                        Question.rejected_reason.is_(reason)
                        if reason is None
                        else Question.rejected_reason == reason,
                    )
                    .order_by(Question.id if each is None else func.random())
                    .limit(each)
                ).scalars()
                rows += [self._question(one) for one in found]
        return rows

    @staticmethod
    def _question(one) -> QuestionRow:
        """One stored question, as a reviewer is shown it."""
        return QuestionRow(
            id=one.id,
            question_text=one.question_text,
            target_answer=one.target_answer,
            answerable=one.answerable,
            difficulty=one.difficulty,
            question_type=one.question_type,
            language=one.language,
            status=one.status,
            rejected_reason=one.rejected_reason,
            facts=[link.fact.statement for link in one.fact_links],
            evidence=[link.fact.evidence_text for link in one.fact_links],
            answer_explanation=one.answer_explanation,
            confidence=one.confidence,
        )

    def held(self, name: str, ids: Sequence[int]) -> dict[int, Held]:
        """What each of these rows reads now, and when it was last decided.

        A row that is gone is missing.
        """
        key, text, decided = _HELD[name]
        with self._session() as session:
            return {
                row_id: Held(said, at)
                for row_id, said, at in session.execute(
                    select(key, text, decided).where(key.in_(ids))
                )
            }

    def review_facts(self, verdicts: list[tuple[int, str, datetime]]) -> int:
        """Records what a person decided about some facts.

        Writes `reviewed_verdict` and never `validated`: that one is the
        checker's and extract-revalidate rewrites it in full, so a verdict
        written there would last until the next re-judgement.

        Args:
            verdicts: Each fact's id, `accepted` or `rejected`, and when the
                person said so.

        Returns:
            How many rows were written.
        """
        if not verdicts:
            return 0
        written = 0
        with self._session.begin() as session:
            for fact_id, verdict, at in verdicts:
                written += session.execute(
                    update(Fact)
                    .where(Fact.id == fact_id)
                    .values(
                        reviewed_verdict=ReviewVerdict(verdict),
                        reviewed_at=at,
                    )
                ).rowcount
        return written

    def date_questions(self, dated: list[tuple[int, datetime]]) -> None:
        """Sets each question's `reviewed_at` to when the person decided."""
        with self._session.begin() as session:
            for question_id, at in dated:
                session.execute(
                    update(Question)
                    .where(Question.id == question_id)
                    .values(reviewed_at=at)
                )

    def cover(self, topic_id: int, include: bool, at: datetime) -> int:
        """Sets whether a topic counts toward coverage, and when that was decided.

        Returns:
            How many rows were written.
        """
        with self._session.begin() as session:
            return session.execute(
                update(Topic)
                .where(Topic.id == topic_id, Topic.topic_index.is_not(None))
                .values(include_in_coverage=include, decided_at=at)
            ).rowcount

    def counts(self) -> dict[str, Any]:
        """How much of the corpus has been looked at, and who agreed.

        Both datasets a verdict can land in, and for each the number the
        sample exists to produce: how often the person and the model
        reached the same verdict. A count of rows reviewed says a review
        happened; the agreement says what it found.

        The model's verdict is read off a different column in each. A fact
        carries the checker's as `validated`. A question carries the
        gates' as `rejected_reason` - NULL means no gate stopped it - which
        is only readable because `decide()` stopped clearing it.
        """
        gated = case((Question.rejected_reason.is_(None), "accepted"), else_="rejected")
        checked = case((Fact.validated, "accepted"), else_="rejected")
        with self._session() as session:
            return {
                "facts": self._looked(session, Fact, Fact.reviewed_verdict, checked),
                "questions": self._looked(
                    session, Question, Question.reviewed_verdict, gated
                ),
            }

    @staticmethod
    def _looked(session, table, verdict, model) -> dict[str, Any]:
        """One dataset: how big it is, what was said, and how often it matched."""
        total = session.execute(select(func.count()).select_from(table)).scalar_one()
        rows = session.execute(
            select(verdict, model.label("model"), func.count())
            .where(verdict.is_not(None))
            .group_by(verdict, model)
        ).all()
        said: dict[str, int] = {}
        agreed = 0
        for person, machine, count in rows:
            said[person] = said.get(person, 0) + count
            if person == machine:
                agreed += count
        reviewed = sum(said.values())
        return {
            "total": total,
            "reviewed": reviewed,
            "verdicts": said,
            "agreed": agreed,
            # None rather than 0.0 when nothing has been reviewed: a rate
            # over no rows is not a rate, and printing 0% would read as
            # "the reviewer never agreed" instead of "nobody has looked".
            "agreement": round(agreed / reviewed, 3) if reviewed else None,
        }
