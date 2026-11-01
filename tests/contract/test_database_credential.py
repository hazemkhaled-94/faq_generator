"""What every database credential adapter does, run against each one there is.

The connection is the seam, not the SQL: Postgres stays the database. A
credential answers a password for each new connection, so a token that
expires (Entra ID on Azure Database for PostgreSQL) is asked for again and a
pooled connection never carries a stale one. TLS travels in the DSN's query.
"""

from __future__ import annotations

import importlib
import itertools
from unittest.mock import MagicMock

import pytest

# The package's `engine` is the function; the module has the same name.
module = importlib.import_module("database.qa_generator.engine")

DSN = "postgresql+psycopg://app:from-the-url@db.example/qa?sslmode=verify-full&sslrootcert=/ca/root.pem"


class Rotating:
    """A credential whose password changes on every ask, as a token does."""

    def __init__(self) -> None:
        """Starts the count."""
        self.count = itertools.count(1)

    def password(self) -> str | None:
        """A fresh password."""
        return f"token-{next(self.count)}"


CREDENTIALS = {"url": module.UrlCredential, "rotating": Rotating}


@pytest.fixture(params=CREDENTIALS)
def credential(request):
    """Each adapter in turn."""
    return CREDENTIALS[request.param]()


def connects(monkeypatch, credential, count: int = 1) -> list[dict]:
    """Opens `count` connections on an engine built with the credential, returns the parameters each got."""
    seen: list[dict] = []

    def fake_connect(self, *cargs, **cparams):
        seen.append(cparams)
        return MagicMock()

    monkeypatch.setenv("DATABASE_URL", DSN)
    monkeypatch.setattr(
        type(module.create_engine(DSN).dialect), "connect", fake_connect
    )
    built = module.build(credential)
    for _ in range(count):
        built.pool._creator(None)  # what the pool calls for a new connection
    return seen


def test_a_credential_answers_a_password_or_leaves_the_one_in_the_url(
    credential,
) -> None:
    """The port: str to override, None to leave the DSN's."""
    answer = credential.password()

    assert answer is None or isinstance(answer, str)


def test_the_url_adapter_leaves_the_password_in_the_dsn(monkeypatch) -> None:
    """Today's behaviour, unchanged by default."""
    (params,) = connects(monkeypatch, module.UrlCredential())

    assert params["password"] == "from-the-url"


def test_a_rotating_credential_is_asked_on_each_new_connection(monkeypatch) -> None:
    """Two connections, two tokens: nothing is cached in the engine."""
    first, second = connects(monkeypatch, Rotating(), count=2)

    assert (first["password"], second["password"]) == ("token-1", "token-2")


def test_tls_in_the_dsn_reaches_the_connect_parameters(monkeypatch, credential) -> None:
    """Sslmode and sslrootcert travel in the query, whichever credential is used."""
    (params,) = connects(monkeypatch, credential)

    assert params["sslmode"] == "verify-full"
    assert params["sslrootcert"] == "/ca/root.pem"


def test_database_auth_names_the_adapter(monkeypatch) -> None:
    """DATABASE_AUTH selects it; `url` is the default and an unknown name is refused."""
    monkeypatch.delenv("DATABASE_AUTH", raising=False)
    assert isinstance(module.credential(), module.UrlCredential)

    monkeypatch.setenv("DATABASE_AUTH", "entra")
    with pytest.raises(ValueError, match="DATABASE_AUTH"):
        module.credential()
