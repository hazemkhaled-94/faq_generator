"""A wipe over a corpus the size of go-live deletes it, within a bound near what it cost before the lock."""

from __future__ import annotations

import time

import pytest
from seed import digest
from sqlalchemy import text

pytestmark = pytest.mark.integration

#: Seconds: origin/main took 2.65 for this corpus, and the lock must stay of that order.
BOUND = 15


def seed(
    engine,
    sha: str,
    passages: int,
    facts_per: int,
    questions_per: int = 1,
    threads: bool = True,
) -> None:
    """One document; `passages` passages; `facts_per` atomic facts on each; `questions_per` questions per fact.

    With threads, every second question of a fact follows the one before it.
    """
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO documents (sha256, mime_type) VALUES (:s, 'application/pdf')"
            ),
            {"s": sha},
        )
        c.execute(
            text(
                "INSERT INTO passages (doc_sha256, ordinal, text, doc_item_refs, language, sentences) "
                "SELECT :s, g, 'Gebühr ' || g || ' beträgt 5 EUR.', ARRAY[]::text[], 'de', "
                '\'[{"i": 0, "start": 0, "end": 20, "predicates": 1}]\'::jsonb '
                "FROM generate_series(1, :n) g"
            ),
            {"s": sha, "n": passages},
        )
        c.execute(
            text(
                "CREATE TEMP TABLE x3_f ON COMMIT DROP AS "
                "SELECT p.id AS passage_id, k FROM passages p, generate_series(1, :k) k WHERE p.doc_sha256 = :s"
            ),
            {"s": sha, "k": facts_per},
        )
        c.execute(
            text(
                "ALTER TABLE x3_f ADD COLUMN fact_id bigint; "
                "UPDATE x3_f SET fact_id = nextval(pg_get_serial_sequence('facts', 'id'))"
            )
        )
        c.execute(
            text(
                "INSERT INTO facts (id, kind, statement, evidence_text, extraction_method, validated, "
                "statement_predicates, evidence_predicates, units_statement, units_added, unresolved_references) "
                "SELECT fact_id, 'atomic', 'Fact ' || fact_id, 'Fact ' || fact_id, 'llm', true, 1, 1, '{}', '{}', '{}' FROM x3_f"
            )
        )
        c.execute(
            text(
                "INSERT INTO fact_passages (fact_id, passage_id, position, sentence_ids, evidence_start, evidence_end) "
                "SELECT fact_id, passage_id, 0, ARRAY[0], 0, 5 FROM x3_f"
            )
        )
        c.execute(
            text(
                "CREATE TEMP TABLE x3_q ON COMMIT DROP AS "
                "SELECT fact_id, n, nextval(pg_get_serial_sequence('questions', 'id')) AS qid "
                "FROM x3_f, generate_series(1, :m) n"
            ),
            {"m": questions_per},
        )
        c.execute(
            text(
                "INSERT INTO questions (id, question_text, answerable, language, status, release_id, "
                "reviewed_verdict, reviewed_at, follows_id, thread_position) "
                "SELECT q.qid, 'Q?', true, 'de', 'accepted', '00000000-0000-0000-0000-000000000001', "
                "'accepted', now(), "
                "CASE WHEN :threads AND n % 2 = 0 THEN (SELECT p.qid FROM x3_q p WHERE p.fact_id = q.fact_id AND p.n = q.n - 1) END, "
                "CASE WHEN :threads AND n % 2 = 0 THEN 2 ELSE 1 END "
                "FROM x3_q q ORDER BY q.fact_id, q.n"
            ),
            {"threads": threads},
        )
        c.execute(
            text(
                "INSERT INTO question_facts (question_id, fact_id) SELECT qid, fact_id FROM x3_q"
            )
        )
        c.execute(text("ANALYZE"))


def test_a_wipe_over_seventy_thousand_questions_deletes_them_within_the_bound(
    engine, database
) -> None:
    """The ids of the locked questions went one parameter each, and psycopg stops at 65,535."""
    from ingestion.repository import DocumentRepository

    sha = digest("scale-70k")
    seed(engine, sha, passages=1000, facts_per=7, questions_per=10, threads=False)
    started = time.monotonic()

    DocumentRepository().delete_all([sha])

    assert time.monotonic() - started < BOUND
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM questions")).scalar_one() == 0
        )
        assert (
            connection.execute(text("SELECT count(*) FROM documents")).scalar_one() == 0
        )


def test_a_document_of_threads_deletes_within_the_bound(engine, database) -> None:
    """Threads add the parent and follow-up walks to the lock."""
    from ingestion.repository import DocumentRepository

    sha = digest("scale-threads")
    seed(engine, sha, passages=2000, facts_per=5)
    started = time.monotonic()

    DocumentRepository().delete(sha)

    assert time.monotonic() - started < BOUND
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM questions")).scalar_one() == 0
        )
