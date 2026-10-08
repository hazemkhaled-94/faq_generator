"""Which revision the database is at, and which the code carries."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection

#: The revisions the code carries, beside the models.
_MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


@lru_cache(maxsize=1)
def heads() -> frozenset[str]:
    """The newest revisions the code carries."""
    return frozenset(ScriptDirectory(str(_MIGRATIONS)).get_heads())


def applied(connection: Connection) -> frozenset[str]:
    """The revisions the database records."""
    return frozenset(MigrationContext.configure(connection).get_current_heads())
