"""The engine refuses a DATABASE_URL that names no database."""

import importlib

import pytest

engine_module = importlib.import_module("database.qa_generator.engine")


@pytest.fixture(autouse=True)
def fresh_engine():
    """The engine is cached once per process."""
    engine_module.engine.cache_clear()
    yield
    engine_module.engine.cache_clear()


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@localhost:5432/",
        "postgresql+psycopg://u:p@localhost:5432",
        "postgresql+psycopg://u:p@localhost:5432/?sslmode=require",
    ],
)
def test_a_url_naming_no_database_is_refused(monkeypatch, url):
    """A URL with no database connects to the one named like the user, the main one."""
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(ValueError, match="names no database"):
        engine_module.engine()


def test_a_url_naming_a_database_builds_the_engine(monkeypatch):
    """The control: a named database still builds."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/ledger")
    assert engine_module.engine().url.database == "ledger"


def test_the_migrations_read_the_url_through_the_same_refusal():
    """Alembic must not read the environment around the refusal."""
    from pathlib import Path

    text = (
        Path(engine_module.__file__).parents[1] / "migrations" / "env.py"
    ).read_text()
    assert 'os.environ["DATABASE_URL"]' not in text and "database_url()" in text
