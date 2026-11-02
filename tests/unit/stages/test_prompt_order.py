"""The prompts listing puts the newest version first, by its leading number.

A version is a number, and a capped prompt carries a suffix after it (`12+cap4`).
Sorted by length and then text, `12+cap4` came before `13` and `100`. The order
is by the digits the version opens with, then the whole version, then the name.
The database itself is exercised in tests/integration/database/test_prompt_store.py.
"""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy.dialects import postgresql

from stages import prompts


class _Reading:
    """A session that keeps the statement it is asked to run."""

    def __init__(self) -> None:
        """Starts with nothing asked."""
        self.statement = None

    @contextmanager
    def begin(self):
        """Hands over itself, as a transaction does."""
        yield self

    def scalars(self, statement):
        """Records the statement, and finds no row."""
        self.statement = statement
        return []

    def expunge_all(self) -> None:
        """Nothing is attached."""


def test_the_listing_orders_by_the_leading_number_of_the_version(monkeypatch) -> None:
    """Number first, so 13 and 100 stand before 12+cap4, and 9 after it."""
    reading = _Reading()
    monkeypatch.setattr(prompts, "sessions", lambda: reading)

    prompts.stored()

    ordered = str(reading.statement.compile(dialect=postgresql.dialect())).split(
        "ORDER BY"
    )[1]
    assert "CAST(SUBSTRING(prompts.version FROM" in ordered
    assert "AS INTEGER) DESC" in ordered
    assert ordered.index("AS INTEGER) DESC") < ordered.index("prompts.version DESC")
    assert "length" not in ordered
