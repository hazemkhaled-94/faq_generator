"""The base every repository shares."""

from __future__ import annotations

from typing import Any

from sqlalchemy import CHAR, BigInteger, any_, literal, or_, select
from sqlalchemy.dialects.postgresql import ARRAY

from database.qa_generator.engine import sessions
from database.qa_generator.facts import Fact
from database.qa_generator.question_facts import QuestionFact
from database.qa_generator.questions import Question


class Repository:
    """Holds the shared session factory, and nothing else."""

    def __init__(self) -> None:
        """Binds to the session factory."""
        self._session = sessions()


def lock_reached(session, fact_ids: Any, digests: list[str] | None = None) -> None:
    """Locks the facts, then the questions on them and their whole threads, in id order, before a delete.

    The orphan triggers lock each fact and question as the cascade reaches
    it, in the order the rows are stored, so two deletions that reach the
    same facts through different rows each hold one and wait for the other's.
    Taking them first in id order makes both wait in the same line, and the
    triggers' own locks find them held. A rejected root's follow-ups are
    updated by a trigger and a deleted root's are cascaded, and a thread
    crossing two passages is reached from both, so each question's whole
    thread (parents and follow-ups, through `follows_id`) is locked in the
    same line. So is every duplicate refusal naming a reached fact as its
    twin: the delete sets its `twin_id` NULL, an update of a row of another
    document, so two deletions whose refusals name each other's facts would
    otherwise each hold the other's.

    Args:
        session: The transaction that is about to delete.
        fact_ids: The facts the deletion reaches: a list of ids, or a select
            of them.
        digests: The documents the deletion takes, whose stamped questions it
            deletes too.
    """
    session.execute(
        select(Fact.id)
        .where(or_(_among(Fact.id, fact_ids), _among(Fact.twin_id, fact_ids)))
        .order_by(Fact.id)
        .with_for_update()
    ).all()
    seed = select(QuestionFact.question_id.label("id")).where(
        _among(QuestionFact.fact_id, fact_ids)
    )
    if digests:
        # The questions a rerun left with no fact, named only by their stamp,
        # which the same delete takes: locked in the same line.
        seed = seed.union(
            select(Question.id).where(
                Question.source_digests.op("&&")(_array(digests, CHAR(64)))
            )
        )
    session.execute(
        select(Question.id)
        .where(Question.id == any_(_array(_thread(session, seed))))
        .order_by(Question.id)
        .with_for_update()
    ).all()


def _array(ids: Any, kind: Any = BigInteger):
    """A list as one array parameter, whose size psycopg does not count against its limit."""
    return literal(list(ids), ARRAY(kind))


def _among(column, ids: Any):
    """`column` among some ids: a select of them, or a list sent as one array parameter."""
    if isinstance(ids, list | tuple | set):
        return column == any_(_array(ids))
    return column.in_(ids)


def _thread(session, seed) -> list[int]:
    """The seed questions with every other question of their threads, root to last follow-up, by id.

    Walked in SQL, so no id is sent back as a parameter of its own: a corpus
    of a hundred thousand questions is one statement, not one parameter each.
    """
    reached = seed.subquery()
    up = select(reached.c.id).cte("up", recursive=True)
    up = up.union(
        select(Question.follows_id).where(
            Question.id == up.c.id, Question.follows_id.is_not(None)
        )
    )
    down = select(up.c.id).cte("down", recursive=True)
    down = down.union(select(Question.id).where(Question.follows_id == down.c.id))
    return sorted(set(session.scalars(select(down.c.id))))


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
