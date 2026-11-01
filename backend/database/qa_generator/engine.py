"""Connection to the qa_generator database.

The only module that builds an engine or knows where the database lives.

Postgres stays the database; the seam is the connection. A `Credential` is
asked for a password each time the pool opens a connection, so one that
expires is renewed and a pooled connection never carries a stale one.
`DATABASE_AUTH` names the adapter, and `url` (the password inside
`DATABASE_URL`, today's behaviour) is the only one there is. TLS is not
here: `sslmode` and `sslrootcert` travel in the URL's query.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Protocol

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker


def _pool(name: str, fallback: int) -> int:
    """Reads a pool size, falling back so a worker needs no new setting."""
    value = os.environ.get(name, "").strip()
    return int(value) if value else fallback


class Credential(Protocol):
    """Where a connection's password comes from."""

    def password(self) -> str | None:
        """A password for the connection about to be opened, or None to keep the URL's."""
        ...


class UrlCredential:
    """The password inside `DATABASE_URL`."""

    def password(self) -> str | None:
        """None: the URL already carries it."""
        return None


def credential() -> Credential:
    """The adapter DATABASE_AUTH names.

    Raises:
        ValueError: If it names none that exists.
    """
    adapter = os.environ.get("DATABASE_AUTH", "url")
    if adapter == "url":
        return UrlCredential()
    raise ValueError(
        f"DATABASE_AUTH={adapter!r} names no adapter; the one there is is url"
    )


def authenticated(built: Engine, using: Credential | None = None) -> Engine:
    """Makes an engine ask its credential for the password of every new connection."""
    asked = using or credential()

    @event.listens_for(built, "do_connect")
    def _ask(dialect, record, cargs, cparams) -> None:
        password = asked.password()
        if password is not None:
            cparams["password"] = password

    return built


def build(using: Credential | None = None) -> Engine:
    """Builds an engine from DATABASE_URL, authenticated by the credential."""
    return authenticated(
        create_engine(
            os.environ["DATABASE_URL"],
            # pool_pre_ping: a connection dropped by a restarted database is
            # replaced rather than surfacing as an error in the caller.
            pool_pre_ping=True,
            pool_size=_pool("DATABASE_POOL_SIZE", 5),
            max_overflow=_pool("DATABASE_POOL_OVERFLOW", 5),
            pool_recycle=1800,
        ),
        using,
    )


@lru_cache(maxsize=1)
def engine() -> Engine:
    """Builds the engine, once per process."""
    return build()


@lru_cache(maxsize=1)
def sessions() -> sessionmaker:
    """Builds the session factory, once per process."""
    # expire_on_commit off: callers read values out of a closing session.
    return sessionmaker(engine(), expire_on_commit=False)
