"""Each revision, applied, taken back out and applied again, one at a time.

`test_migration_rollback` compares table names after a round trip to base.
A downgrade that restores the wrong comment, forgets a trigger or a CHECK,
or an upgrade that writes something different the second time, keeps every
table name. This compares the whole catalogue - columns, defaults,
constraints, indexes, triggers, functions and comments - one revision at a
time, so a broken step names itself.

Run against a database of its own, created and dropped here.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]

#: What one database's schema is, as rows that compare by value.
CATALOGUE = {
    "columns": """
        SELECT table_name, column_name, data_type, udt_name, is_nullable,
               coalesce(column_default, ''), coalesce(character_maximum_length, 0)
        FROM information_schema.columns WHERE table_schema = 'public'
    """,
    "constraints": """
        SELECT c.conrelid::regclass::text, c.conname, pg_get_constraintdef(c.oid)
        FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace
        WHERE n.nspname = 'public'
    """,
    "indexes": "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'",
    "triggers": """
        SELECT tgrelid::regclass::text, tgname, pg_get_triggerdef(oid)
        FROM pg_trigger WHERE NOT tgisinternal
    """,
    "functions": """
        SELECT p.proname, pg_get_function_identity_arguments(p.oid), md5(p.prosrc)
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.prokind = 'f'
          AND NOT EXISTS (SELECT 1 FROM pg_depend d
                          WHERE d.objid = p.oid AND d.deptype = 'e')
    """,
    "table comments": """
        SELECT c.relname, coalesce(obj_description(c.oid, 'pg_class'), '')
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'v', 'm')
    """,
    "column comments": """
        SELECT c.relname, a.attname, coalesce(col_description(c.oid, a.attnum), '')
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid
        WHERE n.nspname = 'public' AND c.relkind = 'r' AND a.attnum > 0
          AND NOT a.attisdropped
    """,
}


@pytest.fixture
def spare(postgres: str) -> Iterator[str]:
    """A database of its own, dropped when the test is done."""
    name = f"steps_{uuid.uuid4().hex[:12]}"
    admin = create_engine(postgres, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    url = postgres.rsplit("/", 1)[0] + "/" + name
    previous = os.environ.get("DATABASE_URL")
    try:
        yield url
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _config(url: str):
    from alembic.config import Config

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend/database/migrations"))
    os.environ["DATABASE_URL"] = url
    return config


def _catalogue(url: str) -> dict[str, set[tuple]]:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return {
                # alembic's own table comes with the first upgrade and stays.
                part: {
                    tuple(row)
                    for row in connection.execute(text(query))
                    if row[0] != "alembic_version"
                }
                for part, query in CATALOGUE.items()
            }
    finally:
        engine.dispose()


def _difference(
    before: dict[str, set[tuple]], after: dict[str, set[tuple]]
) -> list[str]:
    return [
        f"{part}: lost {sorted(before[part] - after[part])[:3]}, "
        f"gained {sorted(after[part] - before[part])[:3]}"
        for part in CATALOGUE
        if before[part] != after[part]
    ]


def test_each_revision_round_trips_the_whole_catalogue(spare: str) -> None:
    """From base up, one revision at a time: up, down, up, comparing each side.

    Down must give back exactly the catalogue before the step, which is what
    catches a downgrade that puts back the wrong comment or forgets a CHECK;
    up again must give exactly the catalogue after it.
    """
    from alembic import command
    from alembic.script import ScriptDirectory

    config = _config(spare)
    chain = [
        one.revision for one in ScriptDirectory.from_config(config).walk_revisions()
    ]
    chain.reverse()

    broken = []
    below = _catalogue(spare)
    for revision in chain:
        command.upgrade(config, revision)
        above = _catalogue(spare)
        command.downgrade(config, "-1")
        if moved := _difference(below, _catalogue(spare)):
            broken.append(f"{revision} down: {'; '.join(moved)}")
        command.upgrade(config, revision)
        if moved := _difference(above, _catalogue(spare)):
            broken.append(f"{revision} up again: {'; '.join(moved)}")
        below = above

    assert len(chain) > 20 and below["triggers"] and below["column comments"]
    assert not broken, "\n".join(broken)


def test_a_migration_waiting_for_a_lock_fails_instead_of_hanging(spare: str) -> None:
    """Another session's transaction on `questions` stops the upgrade, with a message.

    Without a lock timeout, the ALTER waits behind that transaction, and every
    query that arrives behind the ALTER waits behind it in turn.
    """
    import time

    from alembic import command
    from alembic.config import Config

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend/database/migrations"))
    os.environ["DATABASE_URL"] = spare
    command.upgrade(config, "head")
    # Two back: the newest revision only writes comments, which wait for no one.
    command.downgrade(config, "-2")

    holder = create_engine(spare).connect()
    holder.execute(text("BEGIN"))
    holder.execute(text("SELECT 1 FROM questions LIMIT 1"))
    started = time.monotonic()
    try:
        with pytest.raises(Exception, match="lock timeout|canceling statement"):
            command.upgrade(config, "head")
    finally:
        holder.close()

    assert time.monotonic() - started < 30
