"""The settings a deployment changed, and the source a stage reads.

`resolved` is the environment overlaid with every stored row, bar a row for
a name given on a `make` command line, which beats it. Resolution ignores
the service column: names are unique across the table, and a stage reads
its own settings and the platform's.

`version` names a configuration by its content, as a digest of every
catalogued setting's resolved value. It changes when anything changes: an
env file, a command line, a stored row, deletions included.

Importing this reaches the database.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, text

from database.qa_generator.engine import sessions
from database.qa_generator.service_settings import ServiceSetting
from settings import catalog

log = logging.getLogger(__name__)

#: How much of the digest is kept.
_VERSION_CHARS = 12

#: The names a `make` command line gave, space-separated. Written by the
#: Makefile's OVERRIDE beside the values themselves.
COMMAND_LINE = "QA_COMMAND_LINE"


def version(source: Mapping[str, str]) -> str:
    """Names one configuration by its content: each catalogued setting in it.

    Sorted before hashing, so the name does not depend on row order.
    """
    named = {name: source[name] for name in sorted(catalog.BY_NAME) if name in source}
    written = json.dumps(named, separators=(",", ":"))
    return hashlib.sha256(written.encode()).hexdigest()[:_VERSION_CHARS]


def _source(overrides: Mapping[str, str]) -> dict[str, str]:
    """The environment overlaid with the stored rows, bar the command line's."""
    given = set(os.environ.get(COMMAND_LINE, "").split())
    return {
        **os.environ,
        **{name: value for name, value in overrides.items() if name not in given},
    }


def resolved() -> dict[str, str]:
    """The environment overlaid with what a deployment changed.

    Built when called rather than held, so a process reaches the database
    only when it needs a setting.
    """
    return Settings().resolved()


def current() -> str:
    """Names the configuration running now."""
    return Settings().version()


def snapshot() -> tuple[dict[str, str], str]:
    """The source to read settings from, and the name of that configuration.

    Both from one read of the table, so a row cannot be stamped with a
    configuration it was not produced under.
    """
    source = _source(Settings().overrides())
    return source, version(source)


class Stale(Exception):
    """The stored settings are no longer at the version a change expected."""

    def __init__(self, current: str) -> None:
        """Records the version they are at."""
        super().__init__(current)
        self.current = current


def _overrides(session: Any) -> dict[str, str]:
    """Every stored setting the catalogue lets a deployment write, by name.

    A row stored before its setting was fixed, or for one since retired, is
    one `clear` refuses and so must not apply.
    """
    return {
        row.name: row.value
        for row in session.scalars(select(ServiceSetting)).all()
        if row.name in catalog.BY_NAME and not catalog.BY_NAME[row.name].fixed
    }


def _write(session: Any, name: str, value: str) -> None:
    """Stores one setting in an open transaction."""
    setting = catalog.writable(name)
    value = value.strip()
    if not value and not setting.optional:
        raise ValueError(
            f"{name} must carry a value. Empty is how a setting whose "
            f"absence means something is turned off, and {name} is not "
            f"one of those; delete the override to return it to what "
            f"configs/env/backend.env says."
        )
    stored = session.scalar(select(ServiceSetting).where(ServiceSetting.name == name))
    if stored is None:
        session.add(ServiceSetting(service=setting.service, name=name, value=value))
    else:
        stored.value = value
        # Rewritten in case the setting moved service.
        stored.service = setting.service


def _clear(session: Any, name: str) -> bool:
    """Deletes one override in an open transaction, saying whether there was one."""
    catalog.writable(name)
    return bool(
        session.execute(
            delete(ServiceSetting).where(ServiceSetting.name == name)
        ).rowcount
    )


class Settings:
    """The stored overrides, read, and written one change at a time."""

    def __init__(self) -> None:
        """Binds to the session factory."""
        self._session = sessions()

    def overrides(self) -> dict[str, str]:
        """Every setting a deployment changed, by name."""
        with self._session() as session:
            return _overrides(session)

    def changed_at(self) -> dict[str, datetime]:
        """When each stored setting was last written, by name."""
        with self._session() as session:
            return {
                row.name: row.updated_at
                for row in session.scalars(select(ServiceSetting)).all()
            }

    def resolved(self) -> dict[str, str]:
        """The environment, overlaid with what a deployment changed.

        A copy, not a view: it must not change while a row is worked.
        """
        return _source(self.overrides())

    def version(self) -> str:
        """Names the configuration running now."""
        return version(self.resolved())

    def change(
        self,
        writes: Mapping[str, str],
        clears: list[str],
        expected: str | None = None,
    ) -> list[str]:
        """Writes and clears settings in one transaction, so a change lands whole.

        The table is locked first, so the version checked against `expected`
        is the one written over. Checks only what the catalogue says of each
        setting. What a value has to parse as is the stage's own
        `Settings.load`, which a caller runs first.

        Returns:
            The cleared names that had a row.

        Raises:
            KeyError: If nothing is configurable under a name.
            ValueError: If the deployment owns a setting, or a value is empty
                and its absence means nothing.
            Stale: If the stored settings are no longer at `expected`.
        """
        with self._session.begin() as session:
            session.execute(
                text("LOCK TABLE service_settings IN SHARE ROW EXCLUSIVE MODE")
            )
            if expected is not None:
                at = version(_source(_overrides(session)))
                if at != expected:
                    raise Stale(at)
            for name, value in writes.items():
                _write(session, name, value)
            cleared = [name for name in clears if _clear(session, name)]

        for name, value in writes.items():
            log.info("%s set to %r", name, value.strip())
        for name in cleared:
            log.info("%s returned to the environment", name)
        return cleared

    def write(self, name: str, value: str) -> str:
        """Stores one setting, and returns the version it produced.

        Raises:
            KeyError: If nothing is configurable under that name.
            ValueError: If the deployment owns the setting, or the value is
                empty and its absence means nothing.
        """
        self.change({name: value}, [])
        return self.version()

    def clear(self, name: str) -> bool:
        """Deletes one override, saying whether there was one.

        Returns the setting to whatever the environment says. There is no
        stored copy of a default to restore.

        Raises:
            KeyError: If nothing is configurable under that name.
            ValueError: If the deployment owns the setting.
        """
        return bool(self.change({}, [name]))
