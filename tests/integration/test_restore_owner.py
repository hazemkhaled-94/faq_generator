"""A restore as the superuser leaves the application role able to read its tables."""

from __future__ import annotations

import pytest
from seed import digest
from sqlalchemy import text

pytestmark = pytest.mark.integration

#: The flags the Makefile's restore targets run pg_restore with (a static test holds them equal).
FLAGS = "--clean --if-exists --single-transaction"


def test_the_application_role_reads_its_tables_after_a_restore_by_the_superuser(
    runtime, own_postgres
) -> None:
    """The dump and the restore run as POSTGRES_USER; the application connects as APP_DB_USER, the owner."""
    from sqlalchemy import create_engine
    from testcontainers.community.postgres import PostgresContainer

    container = own_postgres.started(
        lambda: PostgresContainer(own_postgres.image, driver="psycopg")
    )
    try:
        superuser = container.get_connection_url()
        root = create_engine(superuser, isolation_level="AUTOCOMMIT")
        with root.connect() as connection:
            connection.execute(text("CREATE ROLE qa_app LOGIN PASSWORD 'qa_app'"))
            connection.execute(text("CREATE DATABASE qa_x OWNER qa_app"))
        root.dispose()
        base = superuser.rsplit("/", 1)[0]
        on_x = create_engine(base + "/qa_x", isolation_level="AUTOCOMMIT")
        with on_x.connect() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            connection.execute(text("GRANT ALL ON SCHEMA public TO qa_app"))
        on_x.dispose()
        app_url = base.replace("test:test@", "qa_app:qa_app@") + "/qa_x"
        own_postgres.migrate(app_url)
        app = create_engine(app_url)
        with app.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO documents (sha256, mime_type) VALUES (:s, 'application/pdf')"
                ),
                {"s": digest("restore-owner")},
            )
        code, out = container.exec(
            ["sh", "-c", "pg_dump -Fc -U test -d qa_x | cat > /tmp/qa_x.dump"]
        )
        assert code == 0, out
        with app.begin() as connection:
            connection.execute(text("DELETE FROM documents"))
        app.dispose()

        code, out = container.exec(
            [
                "sh",
                "-c",
                f"cat /tmp/qa_x.dump | pg_restore {FLAGS} -U test -d qa_x",
            ]
        )
        assert code == 0, out
        app = create_engine(app_url)
        try:
            with app.connect() as connection:
                counted = connection.execute(
                    text("SELECT count(*) FROM documents")
                ).scalar_one()
        finally:
            app.dispose()
        assert counted == 1
    finally:
        container.stop()
