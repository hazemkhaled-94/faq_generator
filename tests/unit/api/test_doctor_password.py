"""A database password that breaks the URL built from it is refused where it is read.

The connection string is built out of APP_DB_USER and APP_DB_PASSWORD by the
Makefile and by compose, and neither percent-encodes: a password holding a
character a URL reads as structure connects to another host or none, with an
error that names the database and never the password.
"""

from __future__ import annotations

import pytest

from api.doctor import database_url_problem, preflight


@pytest.mark.parametrize("password", ["Xy7@pq/2", "a:b", "pa#ss", "what?", "50%off"])
def test_a_password_with_a_url_character_is_refused_naming_the_setting(
    password: str,
) -> None:
    """Each of `@ / : # ? %`."""
    said = database_url_problem({"APP_DB_PASSWORD": password})

    assert said is not None and "APP_DB_PASSWORD" in said


@pytest.mark.parametrize("password", ["Xy7@pq/2", "a:b", "pa#ss", "what?", "50%off"])
def test_the_refusal_says_nothing_of_the_password(password: str) -> None:
    """The same words whichever characters it holds, so a log reader learns none of them."""
    said = database_url_problem({"APP_DB_PASSWORD": password})

    assert said == database_url_problem({"APP_DB_PASSWORD": "@"})
    assert password not in (said or "")


@pytest.mark.parametrize(
    "password", ["9f3c1e7a2b", "Plain-Words_and.digits-42", "x" * 64]
)
def test_a_password_of_letters_digits_and_dashes_passes(password: str) -> None:
    """What `make setup` generates, and more."""
    assert database_url_problem({"APP_DB_PASSWORD": password}) is None


def test_an_unset_password_is_not_this_checks_to_say() -> None:
    """Compose refuses it already."""
    assert database_url_problem({}) is None


def test_the_host_runner_refuses_to_start_on_such_a_password(
    monkeypatch, caplog
) -> None:
    """Before a drain opens a connection with it."""
    import logging

    monkeypatch.setenv("APP_DB_PASSWORD", "Xy7@pq/2")
    monkeypatch.setenv("HOST_RUNNER", "0")

    with caplog.at_level(logging.ERROR):
        assert preflight() == 1

    assert any("APP_DB_PASSWORD" in r.getMessage() for r in caplog.records)
    assert not any("Xy7@pq/2" in r.getMessage() for r in caplog.records)


def test_a_percent_in_the_url_reaches_the_engine_unchanged(monkeypatch) -> None:
    """env.py hands alembic the URL escaped for its config parser, which reads `%`."""
    import contextlib
    import runpy
    import types
    from pathlib import Path

    import alembic
    from alembic.config import Config

    seen: dict = {}
    fake = types.ModuleType("alembic.context")
    fake.config = Config()  # type: ignore[attr-defined]
    fake.is_offline_mode = lambda: True  # type: ignore[attr-defined]
    fake.configure = lambda **kwargs: seen.update(kwargs)  # type: ignore[attr-defined]
    fake.begin_transaction = contextlib.nullcontext  # type: ignore[attr-defined]
    fake.run_migrations = lambda: None  # type: ignore[attr-defined]
    monkeypatch.setattr(alembic, "context", fake, raising=False)
    url = "postgresql+psycopg://app:p%40ss@localhost/db"
    monkeypatch.setenv("DATABASE_URL", url)
    env = Path(__file__).resolve().parents[3] / "backend/database/migrations/env.py"

    runpy.run_path(str(env))

    assert seen["url"] == url
