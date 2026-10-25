"""The base every repository shares."""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select

from database.qa_generator.engine import sessions
from database.qa_generator.facts import Fact
from database.qa_generator.question_facts import QuestionFact
from database.qa_generator.questions import Question


class Repository:
    """Holds the shared session factory, and nothing else."""

    def __init__(self) -> None:
        """Binds to the session factory."""
        self._session = sessions()


def lock_reached(session, fact_ids: Any) -> None:
    """Locks the facts, then the questions on them, in id order, before a delete.

    The orphan triggers lock each fact and question as the cascade reaches
    it, in the order the rows are stored, so two deletions that reach the
    same facts through different rows each hold one and wait for the other's.
    Taking them first in id order makes both wait in the same line, and the
    triggers' own locks find them held.

    Args:
        session: The transaction that is about to delete.
        fact_ids: The facts the deletion reaches: a list of ids, or a select
            of them.
    """
    session.execute(
        select(Fact.id).where(Fact.id.in_(fact_ids)).order_by(Fact.id).with_for_update()
    ).all()
    session.execute(
        select(Question.id)
        .where(
            Question.id.in_(
                select(QuestionFact.question_id).where(
                    QuestionFact.fact_id.in_(fact_ids)
                )
            )
        )
        .order_by(Question.id)
        .with_for_update()
    ).all()


def storable(text: str) -> bool:
    """Whether a text column can hold `text`, rather than the write raising.

    PostgreSQL text cannot hold a NUL, and psycopg cannot encode a lone
    surrogate, which a JSON escape or a form decoded in a charset the
    caller names can carry.
    """
    try:
        text.encode()
    except UnicodeEncodeError:
        return False
    return "\x00" not in text


def matching(search: str, *columns: Any) -> Any:
    """Builds the condition a search box's words select over some columns.

    Here rather than in each stage's own filter, because the one thing every
    copy has to remember is `autoescape`: without it a `%` or `_` a person
    typed is a wildcard, and the third copy is where that gets forgotten.
    """
    return or_(*(column.icontains(search, autoescape=True) for column in columns))
