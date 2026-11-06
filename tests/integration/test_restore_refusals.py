"""A restore that is named wrongly refuses before it puts anything back."""

from __future__ import annotations

import pytest
from seed import digest, document, fact, passage
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def seed_and_delete(engine) -> str:
    """A shop document with a passage and a fact, deleted; returns its AT."""
    with Session(engine) as session:
        sha = digest("returns-policy")
        session.add(document(sha, parse_status="parsed", chunk_status="chunked"))
        session.flush()
        cut = passage(sha, ordinal=1, text="Returns are accepted within 30 days.")
        session.add(cut)
        session.flush()
        session.add(fact(cut.id, statement="Returns are accepted within 30 days."))
        session.commit()
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM documents"))
    with engine.connect() as connection:
        return (
            connection.execute(
                text(
                    "SELECT max(archived_at) FROM archived_rows "
                    "WHERE table_name = 'documents'"
                )
            )
            .scalar_one()
            .isoformat()
        )


def documents(engine) -> int:
    """How many documents the live table holds."""
    with engine.connect() as connection:
        return connection.execute(text("SELECT count(*) FROM documents")).scalar_one()


def restore(monkeypatch, **environment: str) -> int:
    """Runs the restore with the given environment."""
    from archive import restore as module

    for name in ("SINCE", "AT", "TABLES"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    return module.main()


def test_a_time_with_nothing_archived_refuses_and_restores_nothing(
    engine, database, buckets, monkeypatch, capsys
) -> None:
    """A mistyped AT beside a real one must not restore the real one alone."""
    at = seed_and_delete(engine)

    assert restore(monkeypatch, AT=f"{at},2001-02-03T04:05:06+00:00") == 1

    assert "Nothing was archived at 2001-02-03" in capsys.readouterr().out
    assert documents(engine) == 0


def test_a_table_name_no_table_holds_refuses_and_restores_nothing(
    engine, database, buckets, monkeypatch, capsys
) -> None:
    """A typo in TABLES is named, not read as "every default table"."""
    at = seed_and_delete(engine)

    assert restore(monkeypatch, AT=at, TABLES="documents,documnets") == 1

    assert "TABLES names no table: documnets" in capsys.readouterr().out
    assert documents(engine) == 0
