"""The statements the topic repository sends, read as Postgres is asked them."""

from __future__ import annotations

from contextlib import nullcontext

from sqlalchemy.dialects import postgresql

from topic_modelling import repository
from topic_modelling.repository import TopicQueue


class _Result(list):
    """No rows, and no row counted."""

    rowcount = 0


class _Session:
    """Records what it is asked, and answers as an empty database does."""

    def __init__(self) -> None:
        self.asked: list[tuple[object, object]] = []

    def __call__(self):
        return nullcontext(self)

    def scalar(self, statement, params=None):
        self.asked.append((statement, params))
        return False

    def execute(self, statement, params=None):
        self.asked.append((statement, params))
        return _Result()


def test_the_fit_reads_its_passages_in_document_order_not_in_id_order() -> None:
    """Inserted in another order, the same passages feed the fit in the same one."""
    queue = TopicQueue.__new__(TopicQueue)
    queue._session = session = _Session()  # type: ignore[attr-defined]

    list(queue.passages("de"))

    sql = str(session.asked[-1][0].compile(dialect=postgresql.dialect()))
    assert sql.endswith("ORDER BY passages.doc_sha256, passages.ordinal"), sql


def test_the_centroids_are_placed_for_the_fitted_languages_only() -> None:
    """A refit of one language leaves every other's centroids where they are."""
    session = _Session()

    repository._place(session, ["de"])

    statement, params = session.asked[0]
    assert "t.language = ANY(:languages)" in str(statement)
    assert params == {"languages": ["de"]}
