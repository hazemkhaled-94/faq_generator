"""A restore puts back the deletions chosen, and nothing archived beside them."""

from __future__ import annotations

import pytest
from seed import digest, document, fact, fitted, link, passage, question
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.qa_generator import ServiceSetting

pytestmark = pytest.mark.integration


def seed(engine, *names: str) -> dict[str, int]:
    """One chunked document per name, with a passage and a fact each."""
    from blob_store.s3 import DocumentsBucket, ParsedBucket

    made = {}
    with Session(engine) as session:
        for name in names:
            sha = digest(name)
            source, parsed = DocumentsBucket(), ParsedBucket()
            source.put(
                source.key_for(sha, "application/pdf"),
                b"%PDF-1.7",
                content_type="application/pdf",
            )
            parsed.put(parsed.key_for(sha), b"{}", content_type="application/json")
            session.add(document(sha, parse_status="parsed", chunk_status="chunked"))
            session.flush()
            cut = passage(sha, ordinal=1, text=f"{name} text")
            session.add(cut)
            session.flush()
            drawn = fact(cut.id, statement=f"{name} fact")
            session.add(drawn)
            session.flush()
            made[name] = drawn.id
        session.commit()
    return made


def run(engine, statement: str) -> None:
    """One transaction, so its deletions share an `archived_at`."""
    with engine.begin() as connection:
        connection.execute(text(statement))


def deleted_at(engine, table: str) -> str:
    """When the newest deletion from `table` happened, as restore names it."""
    with engine.connect() as connection:
        return (
            connection.execute(
                text(
                    "SELECT max(archived_at) FROM archived_rows WHERE table_name = :t"
                ),
                {"t": table},
            )
            .scalar_one()
            .isoformat()
        )


def count(engine, sql: str) -> int:
    """A count, read off the live tables."""
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar_one()


def restore(monkeypatch, **environment: str) -> int:
    """Runs the restore with the given environment."""
    from archive import restore as module

    for name in ("SINCE", "AT", "TABLES"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    return module.main()


def test_one_deletion_is_restored_and_a_later_replacement_stays(
    engine, database, buckets, monkeypatch
) -> None:
    """Delete A, re-extract B, clear a setting, restore A's deletion only."""
    ids = seed(engine, "a", "b")
    with Session(engine) as session:
        session.add(ServiceSetting(service="platform", name="LLM_BASE_URL", value="x"))
        session.commit()

    run(engine, f"DELETE FROM documents WHERE sha256 = '{digest('a')}'")
    at = deleted_at(engine, "documents")
    run(engine, f"DELETE FROM facts WHERE id = {ids['b']}")
    with Session(engine) as session:
        cut = session.execute(
            text("SELECT id FROM passages WHERE doc_sha256 = :s"), {"s": digest("b")}
        ).scalar_one()
        session.add(fact(cut, statement="b fact, second generation"))
        session.commit()
    run(engine, "DELETE FROM service_settings")

    assert restore(monkeypatch, AT=at) == 0

    assert (
        count(engine, f"SELECT count(*) FROM documents WHERE sha256 = '{digest('a')}'")
        == 1
    )
    assert (
        count(engine, "SELECT count(*) FROM facts WHERE statement LIKE 'a fact'") == 1
    )
    assert (
        count(engine, "SELECT count(*) FROM facts WHERE statement LIKE 'b fact%'") == 1
    ), "B keeps one generation of facts"
    assert count(engine, "SELECT count(*) FROM service_settings") == 0


def test_since_only_lists_what_was_deleted(
    engine, database, buckets, monkeypatch, capsys
) -> None:
    """Naming a time restores nothing: it lists, by deleting transaction."""
    seed(engine, "a")
    run(engine, "DELETE FROM documents")

    assert restore(monkeypatch, SINCE="2000-01-01") == 2

    assert count(engine, "SELECT count(*) FROM documents") == 0
    shown = capsys.readouterr().out
    assert "documents" in shown and "AT=" in shown


def test_settings_and_prompts_come_back_only_when_named(
    engine, database, buckets, monkeypatch
) -> None:
    """One transaction took a document and a setting; the setting is skipped."""
    seed(engine, "a")
    with Session(engine) as session:
        session.add(ServiceSetting(service="platform", name="LLM_BASE_URL", value="x"))
        session.commit()
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM documents"))
        connection.execute(text("DELETE FROM service_settings"))
    at = deleted_at(engine, "documents")

    assert restore(monkeypatch, AT=at) == 0
    assert count(engine, "SELECT count(*) FROM documents") == 1
    assert count(engine, "SELECT count(*) FROM service_settings") == 0

    assert restore(monkeypatch, AT=at, TABLES="service_settings") == 0
    assert count(engine, "SELECT count(*) FROM service_settings") == 1


def test_a_refit_is_listed_as_not_restorable(
    engine, database, buckets, monkeypatch, capsys
) -> None:
    """Its topics were replaced under their unique key; offering them is a trap."""
    with Session(engine) as session:
        session.add(fitted(0, language="de", label="Lieferzeiten"))
        session.commit()
    run(engine, "DELETE FROM topics")
    at = deleted_at(engine, "topics")
    with Session(engine) as session:
        session.add(fitted(0, language="de", label="Neu"))
        session.commit()

    assert restore(monkeypatch, SINCE="2000-01-01") == 2
    assert "not restorable" in capsys.readouterr().out

    assert restore(monkeypatch, AT=at) == 1
    assert count(engine, "SELECT count(*) FROM topics") == 1
    assert count(engine, "SELECT count(*) FROM topics WHERE label = 'Neu'") == 1


def test_a_restored_document_with_passages_is_marked_chunked(
    engine, database, buckets, monkeypatch
) -> None:
    """The delete-derived left it `new`; its passages are back."""
    seed(engine, "a")
    run(engine, "DELETE FROM passages")
    run(engine, "UPDATE documents SET chunk_status = 'new'")
    at = deleted_at(engine, "passages")

    assert restore(monkeypatch, AT=at) == 0

    assert count(engine, "SELECT count(*) FROM passages") == 1
    assert (
        count(engine, "SELECT count(*) FROM documents WHERE chunk_status = 'chunked'")
        == 1
    )


def test_a_column_added_since_is_filled_from_its_default(
    engine, database, buckets, monkeypatch
) -> None:
    """The archived payload lacks a key: its default, or a refusal naming it."""
    seed(engine, "a")
    run(engine, "DELETE FROM facts")
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE archived_rows SET payload = payload - 'statement_predicates' "
                "WHERE table_name = 'facts'"
            )
        )
    at = deleted_at(engine, "facts")

    assert restore(monkeypatch, AT=at) == 0
    assert (
        count(engine, "SELECT count(*) FROM facts WHERE statement_predicates = 0") == 1
    )


def test_a_missing_key_with_no_default_refuses_naming_the_column(
    engine, database, buckets, monkeypatch, capsys
) -> None:
    """Rolled back whole, as a NOT NULL violation did, but saying which column."""
    seed(engine, "a")
    run(engine, "DELETE FROM facts")
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE archived_rows SET payload = payload - 'statement' "
                "WHERE table_name = 'facts'"
            )
        )
    at = deleted_at(engine, "facts")

    assert restore(monkeypatch, AT=at) == 1
    assert "statement" in capsys.readouterr().out
    assert count(engine, "SELECT count(*) FROM facts") == 0


def test_questions_whose_facts_are_back_are_listed_for_reverification(
    engine, database, buckets, monkeypatch, capsys
) -> None:
    """Rejected source_changed when the fact went; the fact is back, the verdict stays."""
    ids = seed(engine, "a")
    with Session(engine) as session:
        asked = question()
        session.add(asked)
        session.flush()
        session.add(link(asked.id, ids["a"]))
        session.commit()
        asked_id = asked.id
    run(engine, f"DELETE FROM facts WHERE id = {ids['a']}")
    assert (
        count(
            engine,
            "SELECT count(*) FROM questions WHERE rejected_reason = 'source_changed'",
        )
        == 1
    )
    at = deleted_at(engine, "facts")

    assert restore(monkeypatch, AT=at) == 0

    shown = capsys.readouterr().out
    assert str(asked_id) in shown
    # reverify skips every rejected question: the printed remedy must be what reopens one.
    assert "make questions-reverify" not in shown and "PATCH /questions/" in shown
