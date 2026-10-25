"""How Alembic reaches the database and what it compares against.

The target is `Base.metadata`, which holds every model the package imports,
so `alembic revision --autogenerate` diffs the models against the live
schema. The URL comes from the environment, like every other setting.
"""

from __future__ import annotations

import os

from alembic import context
from pgvector.sqlalchemy import Vector
from sqlalchemy import engine_from_config, pool

from database.qa_generator import Base

config = context.config

# Not in alembic.ini: the URL is a credential, and .env is where those live.
# `%` doubled, because the config parser reads one as the start of an
# interpolation and a percent-encoded password is a ValueError without it.
config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"].replace("%", "%%"))

target_metadata = Base.metadata


def _render_item(type_, obj, autogen_context) -> bool:
    """Adds the import a rendered type needs."""
    if type_ == "type" and isinstance(obj, Vector):
        # Rendered as pgvector.sqlalchemy.vector.VECTOR, which is a
        # NameError in the revision without this.
        autogen_context.imports.add("import pgvector.sqlalchemy")
    return False


#: Autogenerate reads these off the models, so a changed type, server
#: default or column comment produces a revision instead of being skipped.
#: A changed CHECK constraint does not; test_schema.py compares those.
_COMPARE = {
    "compare_type": True,
    "compare_server_default": True,
    "render_item": _render_item,
}


#: What a revision may wait for a lock, and take to run one statement. A DDL
#: statement queues behind any open transaction on its table, and every query
#: that arrives after it queues behind the DDL: a revision that cannot get its
#: lock in seconds fails with a message and is run again, rather than holding
#: the application still. A backfill that needs longer is batched outside the
#: DDL transaction (database/README.md, Migrations).
LOCK_TIMEOUT = "5s"
STATEMENT_TIMEOUT = "10min"


def run_migrations_offline() -> None:
    """Emits the migrations as SQL, without connecting.

    For a deployment where the person applying the change is not the person
    who wrote it.
    """
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_COMPARE,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Applies the migrations against the live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={
            "options": f"-c lock_timeout={LOCK_TIMEOUT} "
            f"-c statement_timeout={STATEMENT_TIMEOUT}"
        },
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            transaction_per_migration=True,
            **_COMPARE,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
