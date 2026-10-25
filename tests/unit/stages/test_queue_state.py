"""What a status read costs.

A page polls `/status` every few seconds. The digest of each status (which rows,
asked by which run) is what Dagster compares between ticks; hashing every row
of a queue for a page that only shows counts is linear in the corpus, so it is
asked for by name.
"""

from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql

from preprocessing.chunking.repository import ChunkQueue


class Recorded:
    """A session that keeps the statement it was given and answers no rows."""

    def __init__(self) -> None:
        """Starts with nothing recorded."""
        self.sql: list[str] = []

    def __call__(self):
        """Stands in for the session factory."""
        return self

    def __enter__(self):
        """Opens."""
        return self

    def __exit__(self, *_):
        """Closes."""
        return False

    def execute(self, statement):
        """Records the statement as Postgres would read it."""
        self.sql.append(str(statement.compile(dialect=postgresql.dialect())))

        class Rows:
            @staticmethod
            def all():
                return []

        return Rows


def _asked(monkeypatch, **flags) -> str:
    """The SQL one `queue_state` sends."""
    queue = ChunkQueue()
    session = Recorded()
    monkeypatch.setattr(queue, "_session", session)
    queue.queue_state(**flags)
    (sql,) = session.sql
    return sql


def test_the_default_status_hashes_no_row(monkeypatch) -> None:
    """A plain count per status, with no string aggregate to sort the table."""
    sql = _asked(monkeypatch)

    assert "string_agg" not in sql
    assert "md5" not in sql
    assert "count(*)" in sql


def test_the_digests_are_asked_for_by_name(monkeypatch) -> None:
    """What Dagster compares between ticks."""
    sql = _asked(monkeypatch, digests=True)

    assert "string_agg" in sql and "md5" in sql


@pytest.mark.parametrize("asked", [False, True])
def test_a_queue_with_no_rows_reports_none_either_way(monkeypatch, asked) -> None:
    """Empty, in any corpus: no counts and no digests."""
    queue = ChunkQueue()
    monkeypatch.setattr(queue, "_session", Recorded())

    state = queue.queue_state(digests=asked)

    assert state.rows == {} and state.digests == {} and state.working is False
