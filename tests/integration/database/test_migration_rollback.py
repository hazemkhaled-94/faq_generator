"""Every revision, applied and taken back out.

Run against a database of its own, created and dropped here, because
downgrading to base empties the one every other test shares.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]

#: The head the revisions below are applied on top of.
PREVIOUS_HEAD = "5d1c7e2a9b40"
RELEASED = "3fe4226da3b6"
REJECTED = "04419594a51e"
DIGEST = "8213be66d5ba"
DECIDED = "1ff74784a860"
MODELLED = "bf8f2e65c149"
LOCKED = "14432e9fd5c9"
BOUNDED = "ad14bed603d4"
COMMENTED = "a739b57cffae"
BUDGETED = "2871990b2443"
RESOLVED = "6c1d0e4b9a27"
UNREAD = "9e2b7c41d058"
REFITTED = "f6f7b1880b23"
#: Every revision after the previous head, oldest first.
LATER = (
    RELEASED,
    REJECTED,
    DIGEST,
    DECIDED,
    MODELLED,
    LOCKED,
    BOUNDED,
    COMMENTED,
    BUDGETED,
    RESOLVED,
    UNREAD,
    REFITTED,
)

#: Three documents, four passages, nine facts and five questions on them.
#: Question 1 rests on documents a and b, 3 is already rejected, and 5
#: rests on two passages of document c.
CORPUS = (
    (
        "INSERT INTO documents (sha256, mime_type) SELECT repeat(d, 64), "
        "'application/pdf' FROM unnest(ARRAY['a', 'b', 'c']) d"
    ),
    (
        "INSERT INTO passages (id, doc_sha256, ordinal, text, doc_item_refs) VALUES "
        "(1, repeat('a', 64), 1, 'One.', '{}'), (2, repeat('b', 64), 1, 'Two.', '{}'), "
        "(3, repeat('c', 64), 1, 'Three.', '{}'), (4, repeat('c', 64), 2, 'Four.', '{}')"
    ),
    (
        "INSERT INTO facts (id, statement, evidence_text, extraction_method, "
        "units_statement, units_added, unresolved_references, validated) "
        "SELECT n, 'Claim.', 'Claim.', 'llm', '{}', '{}', '{}', true "
        "FROM generate_series(1, 9) n"
    ),
    (
        "INSERT INTO fact_passages (fact_id, passage_id, position) VALUES "
        "(1, 1, 0), (2, 2, 0), (3, 1, 0), (4, 1, 0), (5, 2, 0), (6, 2, 0), "
        "(7, 2, 0), (8, 3, 0), (9, 4, 0)"
    ),
    (
        "INSERT INTO questions (id, question_text, answerable, language, status, "
        "rejected_reason, release_id, reviewed_verdict, reviewed_at, "
        "status_changed_at) VALUES "
        "(1, 'One?', true, 'en', 'accepted', NULL, gen_random_uuid(), 'accepted', "
        "now(), now() - interval '1 day'), "
        "(2, 'Two?', true, 'en', 'accepted', NULL, NULL, NULL, NULL, NULL), "
        "(3, 'Three?', true, 'en', 'rejected', 'duplicate', NULL, NULL, NULL, "
        "'2026-01-01T00:00:00Z'), "
        "(4, 'Four?', true, 'en', 'accepted', NULL, NULL, NULL, NULL, NULL), "
        "(5, 'Five?', true, 'en', 'accepted', NULL, gen_random_uuid(), NULL, NULL, "
        "NULL)"
    ),
    (
        "INSERT INTO question_facts (question_id, fact_id) VALUES "
        "(1, 1), (1, 2), (2, 3), (3, 4), (3, 5), (4, 6), (4, 7), (5, 8), (5, 9)"
    ),
)

#: Every question, whole.
QUESTIONS = "SELECT * FROM questions ORDER BY id"


@pytest.fixture
def spare(postgres: str) -> Iterator[str]:
    """A database of its own, dropped when the test is done."""
    name = f"rollback_{uuid.uuid4().hex[:12]}"
    admin = create_engine(postgres, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    url = postgres.rsplit("/", 1)[0] + "/" + name

    try:
        yield url
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def alembic(url: str):
    """An alembic config pointed at one database."""
    from alembic.config import Config

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend/database/migrations"))
    os.environ["DATABASE_URL"] = url
    return config


def tables(url: str) -> set[str]:
    """The tables one database holds."""
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def sql(url: str, *statements: str, **params) -> list:
    """Runs the statements in one transaction, and returns the last one's rows."""
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            for statement in statements:
                result = connection.execute(text(statement), params)
            return [tuple(row) for row in result] if result.returns_rows else []
    finally:
        engine.dispose()


def version(url: str) -> str:
    """The revision one database is at."""
    return sql(url, "SELECT version_num FROM alembic_version")[0][0]


def test_the_revisions_apply_to_an_empty_database(spare: str) -> None:
    """What a new deployment runs."""
    from alembic import command

    command.upgrade(alembic(spare), "head")

    assert "documents" in tables(spare)


def test_every_revision_can_be_taken_back_out(spare: str) -> None:
    """Down to base leaves nothing but alembic's own bookkeeping."""
    from alembic import command

    config = alembic(spare)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    assert tables(spare) <= {"alembic_version"}


def test_the_schema_survives_a_round_trip(spare: str) -> None:
    """Up, down and up again builds the same tables it did the first time.

    A downgrade that drops more than its upgrade created, or an upgrade that
    cannot run twice, shows up here.
    """
    from alembic import command

    config = alembic(spare)
    command.upgrade(config, "head")
    first = tables(spare)

    command.downgrade(config, "base")
    command.upgrade(config, "head")

    assert tables(spare) == first


def test_the_models_still_match_after_a_round_trip(spare: str) -> None:
    """The second upgrade builds the schema the models describe."""
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from database.qa_generator import Base

    config = alembic(spare)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = create_engine(spare)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={"compare_type": True, "compare_server_default": True},
            )
            difference = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert not difference, "\n".join(str(item) for item in difference)


def test_stepping_down_one_revision_at_a_time_reaches_base(spare: str) -> None:
    """Each downgrade in turn, rather than one jump, so a broken one names itself."""
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = alembic(spare)
    command.upgrade(config, "head")

    scripts = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    for _ in scripts.walk_revisions():
        command.downgrade(config, "-1")

    assert tables(spare) <= {"alembic_version"}


def test_a_released_question_has_to_stay_accepted(spare: str) -> None:
    """Refused once the revision is on, allowed again once it is taken off."""
    from alembic import command
    from sqlalchemy.exc import IntegrityError

    config = alembic(spare)
    command.upgrade(config, PREVIOUS_HEAD)
    sql(
        spare,
        "INSERT INTO questions (id, question_text, answerable, language, status, "
        "release_id) VALUES (1, 'Q?', true, 'en', 'accepted', gen_random_uuid())",
    )
    command.upgrade(config, RELEASED)

    with pytest.raises(IntegrityError, match="questions_released_is_accepted"):
        sql(spare, "UPDATE questions SET status = 'rejected' WHERE id = 1")

    command.downgrade(config, PREVIOUS_HEAD)
    sql(spare, "UPDATE questions SET status = 'rejected' WHERE id = 1")
    held = "SELECT status, release_id IS NOT NULL FROM questions"
    assert sql(spare, held) == [("rejected", True)]

    with pytest.raises(IntegrityError, match="questions_released_is_accepted"):
        command.upgrade(config, RELEASED)
    assert version(spare) == PREVIOUS_HEAD

    sql(spare, "UPDATE questions SET status = 'accepted' WHERE id = 1")
    command.upgrade(config, RELEASED)
    assert sql(spare, held) == [("accepted", True)]


@pytest.fixture
def corpus(spare: str):
    """The corpus above, written before the rejection revision."""
    from alembic import command

    config = alembic(spare)
    command.upgrade(config, RELEASED)
    sql(spare, *CORPUS)
    return config


def test_a_question_that_loses_one_of_its_facts_is_rejected(spare: str, corpus) -> None:
    """Rejected while a fact is left, deleted when none is, alone when gone."""
    from alembic import command

    command.upgrade(corpus, REJECTED)
    asked = (
        "SELECT status, rejected_reason, release_id IS NULL, "
        "status_changed_at > now() - interval '1 hour', reviewed_verdict "
        "FROM questions WHERE id = :id"
    )
    archived = (
        "SELECT payload->>'status', payload->>'release_id' IS NOT NULL "
        "FROM archived_rows WHERE table_name = 'questions' "
        "AND payload->>'id' = :id"
    )

    sql(spare, "DELETE FROM facts WHERE id = 1")
    assert sql(spare, asked, id=1) == [
        ("rejected", "source_changed", True, True, "accepted")
    ]
    assert sql(spare, "SELECT fact_id FROM question_facts WHERE question_id = 1") == [
        (2,)
    ]

    sql(spare, "DELETE FROM facts WHERE id = 3")
    assert sql(spare, asked, id=2) == []
    assert sql(spare, archived, id="2") == [("accepted", False)]

    sql(spare, "DELETE FROM facts WHERE id = 4")
    assert sql(
        spare,
        "SELECT status, rejected_reason, status_changed_at = '2026-01-01T00:00:00Z' "
        "FROM questions WHERE id = 3",
    ) == [("rejected", "duplicate", True)]

    sql(spare, "DELETE FROM questions WHERE id = 4")
    assert sql(spare, archived, id="4") == [("accepted", False)]
    assert sql(spare, "SELECT count(*) FROM facts WHERE id IN (6, 7)") == [(2,)]

    sql(spare, "DELETE FROM documents WHERE sha256 = repeat('c', 64)")
    assert sql(spare, asked, id=5) == []
    assert sql(spare, archived, id="5") == [("accepted", True)]


def test_taking_the_rejection_back_out_keeps_every_question(spare: str, corpus) -> None:
    """The old trigger is back and the rows are as they were, both ways."""
    from alembic import command

    command.upgrade(corpus, REJECTED)
    sql(spare, "DELETE FROM facts WHERE id = 1")
    held = sql(spare, QUESTIONS)

    command.downgrade(corpus, RELEASED)
    assert sql(spare, QUESTIONS) == held

    sql(spare, "DELETE FROM facts WHERE id = 6")
    assert sql(spare, "SELECT status FROM questions WHERE id = 4") == [("accepted",)]
    sql(spare, "DELETE FROM facts WHERE id = 3")
    assert sql(spare, "SELECT count(*) FROM questions WHERE id = 2") == [(0,)]

    held = sql(spare, QUESTIONS)
    command.upgrade(corpus, REJECTED)
    assert sql(spare, QUESTIONS) == held


def test_an_upload_record_keeps_its_digest_when_its_document_goes(spare: str) -> None:
    """Kept after the revision; nulled, as the key did, when it is taken off."""
    from alembic import command
    from sqlalchemy.exc import IntegrityError

    config = alembic(spare)
    command.upgrade(config, REJECTED)
    sql(
        spare,
        "INSERT INTO documents (sha256, mime_type) SELECT repeat(d, 64), "
        "'application/pdf' FROM unnest(ARRAY['a', 'b']) d",
        "INSERT INTO ingest_events (id, submitted_filename, size_bytes, sha256, "
        "outcome) VALUES (1, 'a.pdf', 1, repeat('a', 64), 'stored'), "
        "(2, 'b.pdf', 1, repeat('b', 64), 'stored'), "
        "(3, 'big.pdf', 9, NULL, 'too_large')",
    )
    events = "SELECT id, left(sha256, 1) FROM ingest_events ORDER BY id"
    command.upgrade(config, DIGEST)

    sql(spare, "DELETE FROM documents WHERE sha256 = repeat('a', 64)")
    assert sql(spare, events) == [(1, "a"), (2, "b"), (3, None)]

    command.downgrade(config, REJECTED)
    assert sql(spare, events) == [(1, None), (2, "b"), (3, None)]
    sql(spare, "DELETE FROM documents WHERE sha256 = repeat('b', 64)")
    assert sql(spare, events) == [(1, None), (2, None), (3, None)]
    with pytest.raises(IntegrityError):
        sql(
            spare,
            "INSERT INTO ingest_events (submitted_filename, size_bytes, sha256, "
            "outcome) VALUES ('c.pdf', 1, repeat('c', 64), 'stored')",
        )

    command.upgrade(config, DIGEST)
    assert sql(spare, events) == [(1, None), (2, None), (3, None)]


def test_a_topic_decision_time_is_added_empty_and_taken_back_out(spare: str) -> None:
    """NULL on every topic already there, and the topic intact without it."""
    from alembic import command

    config = alembic(spare)
    command.upgrade(config, DIGEST)
    sql(
        spare,
        "INSERT INTO topics (id, language, topic_index, top_terms, label, "
        "labelled_by, status, fitted_at) VALUES (1, 'en', 0, '{fee,charge}', "
        "'Fees', 'person', 'modelled', '2026-09-01T00:00:00Z')",
    )
    held = sql(spare, "SELECT * FROM topics")

    command.upgrade(config, DECIDED)
    assert sql(spare, "SELECT * FROM topics") == [(*held[0], None)]
    sql(spare, "UPDATE topics SET decided_at = '2026-10-01T09:00:00Z'")

    command.downgrade(config, DIGEST)
    assert sql(spare, "SELECT * FROM topics") == held

    command.upgrade(config, DECIDED)
    assert sql(spare, "SELECT * FROM topics") == [(*held[0], None)]


def test_a_citation_naming_sentences_needs_both_bounds(spare: str) -> None:
    """Refused once the revision is on; an upgrade over such a row names the check."""
    from alembic import command
    from sqlalchemy.exc import IntegrityError

    config = alembic(spare)
    command.upgrade(config, LOCKED)
    unbounded = (
        "INSERT INTO fact_passages (fact_id, passage_id, position, sentence_ids) "
        "VALUES (:fact, 1, 0, '{0}')"
    )
    sql(spare, *CORPUS[:3])
    sql(spare, unbounded, fact=1)

    with pytest.raises(IntegrityError, match="fact_passages_citation_complete"):
        command.upgrade(config, BOUNDED)
    assert version(spare) == LOCKED

    sql(spare, "UPDATE fact_passages SET evidence_start = 0, evidence_end = 0")
    command.upgrade(config, BOUNDED)
    with pytest.raises(IntegrityError, match="fact_passages_citation_complete"):
        sql(spare, unbounded, fact=2)

    command.downgrade(config, LOCKED)
    sql(spare, unbounded, fact=2)


#: Every table the chain below compares, row for row.
EVERY = (
    "documents",
    "passages",
    "facts",
    "fact_passages",
    "questions",
    "question_facts",
    "topics",
    "ingest_events",
    "archived_rows",
)


def test_the_later_revisions_step_down_and_back_up_over_a_corpus(spare: str) -> None:
    """Head to the previous head one revision at a time, and back, losing nothing."""
    from alembic import command

    config = alembic(spare)
    command.upgrade(config, PREVIOUS_HEAD)
    sql(
        spare,
        *CORPUS,
        "INSERT INTO ingest_events (submitted_filename, size_bytes, sha256, outcome) "
        "VALUES ('a.pdf', 1, repeat('a', 64), 'stored'), "
        "('big.pdf', 9, NULL, 'too_large')",
        "INSERT INTO topics (language, topic_index, top_terms, label, labelled_by, "
        "status, fitted_at) VALUES ('en', 0, '{fee}', 'Fees', 'person', "
        "'modelled', now())",
        "DELETE FROM facts WHERE id = 3",
    )

    def held() -> dict[str, list]:
        return {
            table: sql(spare, "SELECT * FROM " + table + " t ORDER BY t::text")
            for table in EVERY
        }

    before = held()
    command.upgrade(config, "head")
    at_head = held()
    # The three model columns, NULL on every question already there.
    assert at_head["questions"] == [
        (*row, None, None, None) for row in before["questions"]
    ]

    for _ in LATER:
        command.downgrade(config, "-1")
    assert version(spare) == PREVIOUS_HEAD
    assert held() == before

    command.upgrade(config, "head")
    assert version(spare) == LATER[-1]
    assert held() == at_head
