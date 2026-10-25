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
OPINED = "f7bba722de8e"
UNFOLDED = "3c5a9d2e7b14"
FLOORED = "7d4e1f2a9c63"
KEPT = "8f759a3a3848"
KINDED = "a41c9e3d7b52"
BRIDGED = "c3a9e1470b5d"
THREADED = "d5b2f8a60c14"
JUDGED = "733a3eadef7c"
CATEGORIZED = "626a5b07ae34"
COMMENTS_CORRECTED = "20e31b1656f7"
LANGUAGED = "860d56b11032"
TWINNED = "7a41c9d2e8b0"
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
    OPINED,
    UNFOLDED,
    FLOORED,
    KEPT,
    KINDED,
    BRIDGED,
    THREADED,
    JUDGED,
    CATEGORIZED,
    COMMENTS_CORRECTED,
    LANGUAGED,
    TWINNED,
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


def test_a_question_s_categories_are_added_empty_and_taken_back_out(spare: str) -> None:
    """NULL on every question already there, and the question intact without it."""
    from alembic import command

    config = alembic(spare)
    command.upgrade(config, THREADED)
    sql(
        spare,
        "INSERT INTO questions (id, question_text, answerable, language, status) "
        "VALUES (1, 'Q?', true, 'en', 'accepted')",
    )
    held = sql(spare, "SELECT * FROM questions")

    command.upgrade(config, CATEGORIZED)
    assert sql(spare, "SELECT * FROM questions") == [(*held[0], None)]
    sql(
        spare,
        'UPDATE questions SET categories = \'[{"categorization": "Phrasing", '
        '"category": "concise-and-natural", "description": "short."}]\'',
    )

    command.downgrade(config, THREADED)
    assert sql(spare, "SELECT * FROM questions") == held

    command.upgrade(config, CATEGORIZED)
    assert sql(spare, "SELECT * FROM questions") == [(*held[0], None)]


def _column_comments(url: str) -> dict[tuple[str, str], str]:
    """The comment of the four columns the corrected revision rewrites."""
    return {
        (table, column): sql(
            url,
            "SELECT col_description(CAST(:table AS regclass), a.attnum) "
            "FROM pg_attribute a WHERE a.attrelid = CAST(:table AS regclass) "
            "AND a.attname = :column",
            table=table,
            column=column,
        )[0][0]
        for table, column in (
            ("questions", "categories"),
            ("topics", "top_terms"),
            ("topics", "embedding"),
            ("facts", "bridge"),
        )
    }


def test_the_corrected_comments_are_written_and_the_old_ones_put_back(
    spare: str,
) -> None:
    """Comment only: the comments read as the models say, and no data moves."""
    from alembic import command

    from database.qa_generator import Fact, Question, Topic

    config = alembic(spare)
    command.upgrade(config, CATEGORIZED)
    before = _column_comments(spare)

    command.upgrade(config, COMMENTS_CORRECTED)
    now = _column_comments(spare)
    assert now[("questions", "categories")] == (
        "The categories QUESTIONS_CATEGORIZATIONS dealt this question, each as its "
        "writer was told it, one JSON object per categorization. NULL where none "
        "was rendered."
    )
    assert now == {
        ("questions", "categories"): Question.__table__.c.categories.comment,
        ("topics", "top_terms"): Topic.__table__.c.top_terms.comment,
        ("topics", "embedding"): Topic.__table__.c.embedding.comment,
        ("facts", "bridge"): Fact.__table__.c.bridge.comment,
    }
    assert "(head)" in now[("facts", "bridge")]
    assert "only signature" not in now[("topics", "top_terms")]
    assert "nothing reads it" not in now[("topics", "embedding")]

    command.downgrade(config, CATEGORIZED)
    assert _column_comments(spare) == before


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
    # The three model columns, NULL on every question already there, the
    # kind, single on each of these: none of them has a passage scope, and
    # the categories, NULL.
    assert at_head["questions"] == [
        (*row, None, None, None, "single", None) for row in before["questions"]
    ]

    for _ in LATER:
        command.downgrade(config, "-1")
    assert version(spare) == PREVIOUS_HEAD
    assert held() == before

    command.upgrade(config, "head")
    assert version(spare) == LATER[-1]
    assert held() == at_head


def test_a_question_kind_is_backfilled_from_its_passage_scope(spare: str) -> None:
    """needs_both where it cited several passages, single otherwise, and checked."""
    from alembic import command
    from sqlalchemy.exc import IntegrityError

    config = alembic(spare)
    command.upgrade(config, KEPT)
    sql(
        spare,
        "INSERT INTO questions (id, question_text, answerable, language, status, "
        "passage_scope) VALUES "
        "(1, 'One?', true, 'en', 'accepted', 'multi_passage'), "
        "(2, 'Two?', true, 'en', 'accepted', 'single_passage'), "
        "(3, 'Three?', true, 'en', 'accepted', NULL)",
    )

    command.upgrade(config, KINDED)
    assert sql(spare, "SELECT id, kind FROM questions ORDER BY id") == [
        (1, "needs_both"),
        (2, "single"),
        (3, "single"),
    ]
    with pytest.raises(IntegrityError, match="questions_kind_valid"):
        sql(spare, "UPDATE questions SET kind = 'other' WHERE id = 1")
    sql(
        spare,
        "INSERT INTO questions (id, question_text, answerable, language, status) "
        "VALUES (4, 'Four?', true, 'en', 'draft')",
    )
    assert sql(spare, "SELECT kind FROM questions WHERE id = 4") == [("single",)]

    command.downgrade(config, KEPT)
    assert "kind" not in {
        row[0]
        for row in sql(
            spare,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'questions'",
        )
    }
    command.upgrade(config, KINDED)
    assert sql(spare, "SELECT id, kind FROM questions WHERE id < 4 ORDER BY id") == [
        (1, "needs_both"),
        (2, "single"),
        (3, "single"),
    ]


def test_a_question_archived_before_the_kind_column_restores_with_a_kind(
    spare: str,
) -> None:
    """The archive is backfilled by the same rule, and the key goes on downgrade."""
    from alembic import command

    config = alembic(spare)
    command.upgrade(config, KEPT)
    sql(
        spare,
        "INSERT INTO archived_rows (table_name, payload) VALUES "
        '(\'questions\', \'{"id": 7, "passage_scope": "multi_passage"}\'), '
        '(\'questions\', \'{"id": 8, "passage_scope": "single_passage"}\'), '
        "('questions', '{\"id\": 9, \"passage_scope\": null}'), "
        "('facts', '{\"id\": 1}')",
    )

    command.upgrade(config, KINDED)
    held = "SELECT table_name, payload->>'id', payload->>'kind' FROM archived_rows"
    assert sorted(sql(spare, held + " ORDER BY 1, 2")) == [
        ("facts", "1", None),
        ("questions", "7", "needs_both"),
        ("questions", "8", "single"),
        ("questions", "9", "single"),
    ]
    # What a restore does: the payload populates a row, and the column is NOT NULL.
    sql(
        spare,
        "INSERT INTO questions SELECT * FROM jsonb_populate_record(NULL::questions, "
        '(SELECT payload || \'{"question_text": "Q?", "answerable": true, '
        '"language": "en", "status": "draft", "thread_position": 1, '
        '"attempt": 1, "created_at": "2026-01-01T00:00:00Z", '
        '"status_changed_at": "2026-01-01T00:00:00Z"}\'::jsonb FROM archived_rows '
        "WHERE payload->>'id' = '7'))",
    )
    assert sql(spare, "SELECT kind FROM questions WHERE id = 7") == [("needs_both",)]

    command.downgrade(config, KEPT)
    assert sql(spare, "SELECT count(*) FROM archived_rows WHERE payload ? 'kind'") == [
        (0,)
    ]


def test_a_bridge_reading_is_added_empty_and_taken_back_out(spare: str) -> None:
    """NULL on every fact already there, constrained to a bridge, and the facts intact without it."""
    from alembic import command
    from sqlalchemy.exc import IntegrityError

    config = alembic(spare)
    command.upgrade(config, KEPT)
    for statement in CORPUS[:3]:
        sql(spare, statement)
    held = sql(spare, "SELECT * FROM facts ORDER BY id")

    command.upgrade(config, "head")
    assert sql(spare, "SELECT bridge FROM facts") == [(None,)] * 9
    sql(
        spare,
        "UPDATE facts SET kind = 'bridge', bridge = "
        '\'{"relation": "defines", "question": "q", "answer": "a"}\' WHERE id = 1',
    )
    with pytest.raises(IntegrityError):
        sql(spare, 'UPDATE facts SET bridge = \'{"relation": "defines"}\' WHERE id = 2')

    command.downgrade(config, KEPT)
    assert sql(spare, "SELECT * FROM facts ORDER BY id")[1:] == held[1:]

    command.upgrade(config, "head")
    assert sql(spare, "SELECT bridge FROM facts") == [(None,)] * 9


def test_a_thread_already_split_is_whole_after_the_revision(spare: str) -> None:
    """Released follow-ups under a rejected or draft root lose their release.

    A bank thread in German and a shop thread in English, written before the
    trigger existed; a third thread whose root is accepted stays released.
    """
    from alembic import command

    config = alembic(spare)
    command.upgrade(config, BRIDGED)
    sql(
        spare,
        "INSERT INTO questions (id, question_text, answerable, language, status, "
        "release_id, follows_id, thread_position) VALUES "
        "(11, 'Was kostet die Karte?', true, 'de', 'rejected', NULL, NULL, 1), "
        "(12, 'Und wann wird sie abgebucht?', true, 'de', 'accepted', "
        "'00000000-0000-0000-0000-000000000001', 11, 2), "
        "(13, 'Can goods be returned?', true, 'en', 'draft', NULL, NULL, 1), "
        "(14, 'And how long do refunds take?', true, 'en', 'accepted', "
        "'00000000-0000-0000-0000-000000000001', 13, 2), "
        "(15, 'And where does the money go?', true, 'en', 'accepted', "
        "'00000000-0000-0000-0000-000000000001', 14, 3), "
        "(16, 'Is delivery free?', true, 'en', 'accepted', "
        "'00000000-0000-0000-0000-000000000001', NULL, 1), "
        "(17, 'And for returns?', true, 'en', 'accepted', "
        "'00000000-0000-0000-0000-000000000001', 16, 2)",
    )
    released = "SELECT id FROM questions WHERE release_id IS NOT NULL ORDER BY id"
    assert sql(spare, released) == [(12,), (14,), (15,), (16,), (17,)]

    command.upgrade(config, THREADED)

    assert sql(spare, released) == [(16,), (17,)]


def test_the_papers_scores_are_kept_and_taken_back_out(spare: str) -> None:
    """A rubric row lands at head; stepping down deletes it and keeps the rest.

    The narrower CHECK refuses the six `rubric_` names, so the downgrade
    deletes their rows before it puts the CHECK back, and every other metric
    row of the same assessment stays.
    """
    from alembic import command
    from sqlalchemy.exc import IntegrityError

    config = alembic(spare)
    command.upgrade(config, "head")
    sql(
        spare,
        "INSERT INTO questions (id, question_text, answerable, language) "
        "VALUES (1, 'One?', true, 'en')",
        "INSERT INTO assessments (id, artifact_kind, question_id) "
        "VALUES (1, 'question', 1)",
        "INSERT INTO assessment_metrics (assessment_id, metric, label, score, "
        "approved) VALUES (1, 'relevance', 'relevant', 1.0, true), "
        "(1, 'rubric_fluency', '3', 1.0, true), "
        "(1, 'rubric_answerability', '2', 0.5, false)",
    )
    held = "SELECT metric FROM assessment_metrics ORDER BY metric"

    command.downgrade(config, THREADED)
    assert sql(spare, held) == [("relevance",)]
    with pytest.raises(IntegrityError, match="assessment_metrics_metric_valid"):
        sql(
            spare,
            "INSERT INTO assessment_metrics (assessment_id, metric, label, score, "
            "approved) VALUES (1, 'rubric_clarity', '3', 1.0, true)",
        )

    command.upgrade(config, JUDGED)
    sql(
        spare,
        "INSERT INTO assessment_metrics (assessment_id, metric, label, score, "
        "approved) VALUES (1, 'rubric_clarity', '3', 1.0, true)",
    )
    assert sql(spare, held) == [("relevance",), ("rubric_clarity",)]


def test_a_fact_takes_the_language_of_its_first_citation(spare: str) -> None:
    """The passage's own, the document's where it has none, and NULL where neither.

    A German bank passage, an English shop passage of a document that names
    its language, a passage too short to tell in a French document, and a
    fact whose citation names no language at all.
    """
    from alembic import command

    config = alembic(spare)
    command.upgrade(config, COMMENTS_CORRECTED)
    sql(
        spare,
        "INSERT INTO documents (sha256, mime_type, language) VALUES "
        "(repeat('a', 64), 'application/pdf', 'en'), "
        "(repeat('b', 64), 'application/pdf', 'fr'), "
        "(repeat('c', 64), 'application/pdf', NULL)",
        "INSERT INTO passages (id, doc_sha256, ordinal, text, doc_item_refs, "
        "language) VALUES "
        "(1, repeat('a', 64), 1, 'Die Karte kostet 25 Euro.', '{}', 'de'), "
        "(2, repeat('a', 64), 2, 'Orders can be returned.', '{}', 'en'), "
        "(3, repeat('b', 64), 1, 'Ok.', '{}', NULL), "
        "(4, repeat('c', 64), 1, 'Ok.', '{}', NULL)",
        "INSERT INTO facts (id, statement, evidence_text, extraction_method, "
        "units_statement, units_added, unresolved_references, validated) "
        "SELECT n, 'Claim.', 'Claim.', 'llm', '{}', '{}', '{}', true "
        "FROM generate_series(1, 5) n",
        "INSERT INTO fact_passages (fact_id, passage_id, position) VALUES "
        "(1, 1, 0), (2, 2, 0), (3, 3, 0), (4, 4, 0), (5, 1, 0), (5, 2, 1)",
    )

    command.upgrade(config, LANGUAGED)

    assert sql(spare, "SELECT id, language FROM facts ORDER BY id") == [
        (1, "de"),
        (2, "en"),
        (3, "fr"),
        (4, None),
        (5, "de"),
    ]

    command.downgrade(config, COMMENTS_CORRECTED)
    assert "language" not in {
        row[0]
        for row in sql(
            spare,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'facts'",
        )
    }


def test_the_language_backfill_leaves_the_planner_statistics_current(
    spare: str,
) -> None:
    """ANALYZE ran after it, so the probe's first plan is not a sequential scan.

    A freshly upgraded database has no statistics on the new column until
    autovacuum visits the table, and the probe planned without them read every
    fact: 142 ms against 31 ms once analysed, on this build.
    """
    from alembic import command

    config = alembic(spare)
    command.upgrade(config, COMMENTS_CORRECTED)
    sql(
        spare,
        "INSERT INTO facts (id, statement, evidence_text, extraction_method, "
        "units_statement, units_added, unresolved_references, validated) "
        "SELECT n, 'Claim.', 'Claim.', 'llm', '{}', '{}', '{}', true "
        "FROM generate_series(1, 5) n",
    )
    held = (
        "SELECT count(*) FROM pg_stats WHERE tablename = 'facts' "
        "AND attname = 'language'"
    )

    command.upgrade(config, LANGUAGED)

    assert sql(spare, held) == [(1,)]


def test_a_fact_s_twin_is_indexed_and_the_index_taken_back_out(spare: str) -> None:
    """Deleting a fact looks up the refusals pointing at it, so twin_id has an index."""
    from alembic import command

    config = alembic(spare)
    command.upgrade(config, "head")
    held = (
        "SELECT indexdef FROM pg_indexes "
        "WHERE tablename = 'facts' AND indexname = 'ix_facts_twin_id'"
    )
    assert len(sql(spare, held)) == 1

    command.downgrade(config, COMMENTS_CORRECTED)
    assert sql(spare, held) == []

    command.upgrade(config, "head")
    assert len(sql(spare, held)) == 1
