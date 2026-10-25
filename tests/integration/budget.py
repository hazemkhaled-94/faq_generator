"""How much a route asks of the database, counted.

A page that is right on three rows can issue a statement per row, or one
statement over every row eighteen times, and nothing in a functional test
notices until the corpus is large. This counts what the application's own
engine executes, so a budget is a test like any other.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from sqlalchemy import event
from sqlalchemy.engine import Engine


@dataclass
class Spent:
    """What a block of code asked of the database."""

    statements: list[str] = field(default_factory=list)
    rows: int = 0

    def __len__(self) -> int:
        """How many statements were executed."""
        return len(self.statements)

    def describe(self) -> str:
        """The statements, shortened, for a failure to show."""
        return "\n".join(f"{at}: {one[:140]}" for at, one in enumerate(self.statements))


@contextmanager
def counted() -> Iterator[Spent]:
    """Counts the statements and the rows any engine handles inside the block.

    Every engine, because a repository keeps the session factory it was built
    with, and so is bound to an engine older than the one `engine()` now names.
    """
    spent = Spent()
    watched = Engine

    def before(connection, cursor, statement, parameters, context, many):
        """Records one statement."""
        spent.statements.append(" ".join(statement.split()))

    def after(connection, cursor, statement, parameters, context, many):
        """Adds the rows it returned."""
        spent.rows += max(cursor.rowcount, 0)

    event.listen(watched, "before_cursor_execute", before)
    event.listen(watched, "after_cursor_execute", after)
    try:
        yield spent
    finally:
        event.remove(watched, "before_cursor_execute", before)
        event.remove(watched, "after_cursor_execute", after)
