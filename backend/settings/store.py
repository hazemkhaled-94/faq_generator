"""The settings a deployment changed, and the source a stage reads.

`resolved` is the environment overlaid with every stored row, bar a row for
a name given on a `make` command line, which beats it. Resolution ignores
the service column: names are unique across the table, and a stage reads
its own settings and the platform's.

`version` names a configuration by its content, as a digest of every
catalogued setting's resolved value bar the fixed platform ones no stage's
output depends on. It changes when one of the rest changes: an env file, a
command line, a stored row, deletions included.

Importing this reaches the database.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, text

from database.qa_generator.engine import sessions
from database.qa_generator.service_settings import ServiceSetting
from settings import catalog

log = logging.getLogger(__name__)

#: How much of the digest is kept.
_VERSION_CHARS = 12

#: Settings that were renamed or dropped, by their old name, with what replaced
#: them ("" for nothing). A row stored under one is refused at the build, naming
#: the replacement, because nothing reads it any more and the value it holds was
#: somebody's decision. None so far; a release that renames a setting adds it.
RETIRED: dict[str, str] = {}


class StoredRefused(ValueError):
    """A stored row the catalogue no longer accepts, so a service will not build on it."""


#: The names a `make` command line gave, space-separated. Written by the
#: Makefile's OVERRIDE beside the values themselves.
COMMAND_LINE = "QA_COMMAND_LINE"


#: What the deployment owns and no stage's output depends on: the cap, the
#: poll interval, the pool sizes, the addresses. Moving one changes no row a
#: stage wrote, so it is no new configuration.
_OUTSIDE = frozenset(
    one.name
    for one in catalog.SETTINGS
    if one.fixed and one.service == "platform" and not one.invalidates
)


def version(source: Mapping[str, str]) -> str:
    """Names one configuration by its content: each catalogued setting in it.

    Sorted before hashing, so the name does not depend on row order. The
    fixed platform settings no stage's output depends on are left out.
    """
    named = {
        name: source[name]
        for name in sorted(catalog.BY_NAME)
        if name in source and name not in _OUTSIDE
    }
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


def audit(
    rows: Iterable[Any],
    file: Mapping[str, str],
    given: Iterable[str] | None = None,
    service: str | None = None,
) -> None:
    """Checks every stored row against the catalogue as it stands now.

    One warning per row that overrides the file, naming the stored value, the
    file's and when it was written. A row the catalogue would now refuse, or one
    stored under a retired name, refuses the build of a stage that reads it, so
    the worker waits as it does for any setting it cannot build on, and so does a
    row for a model id whose commit is pinned, which moves only with its pin. A
    row for another name the deployment owns or nothing configures is warned
    about and left: `make settings-unset` cannot delete one, so it must not stop
    a build.

    Args:
        rows: What the table holds: a name, a value and `updated_at` each.
        file: What the files and the environment say, by name.
        given: Names a `make` command line gave, whose rows are not applied.
        service: The stage building, whose own rows and the platform's are
            the ones it refuses; another stage's refused row is warned about
            and left for that stage. None refuses every one, as the doctor
            asks.

    Raises:
        StoredRefused: On a row the catalogue refuses or a retired name.
    """
    given = set(given or ())
    for row in rows:
        if row.name in given:
            continue
        stored = f"{row.name}={row.value!r} (written {row.updated_at:%Y-%m-%d %H:%M})"
        setting = catalog.BY_NAME.get(row.name)
        if row.name in RETIRED:
            replacement = RETIRED[row.name]
            _refuse(
                f"{stored} is stored under a retired setting"
                + (f"; {replacement} replaces it" if replacement else "")
                + f": delete the row (DELETE FROM service_settings WHERE name = '{row.name}')",
                _owner(catalog.BY_NAME.get(replacement), row),
                service,
            )
            continue
        if setting is not None and (pin := f"{row.name}_REVISION") in catalog.BY_NAME:
            # Its commit is the file's, so a stored id would load another
            # repository at that commit, or fail at its first load mid-run.
            _refuse(
                f"{stored} is refused: {row.name} moves only with its pinned "
                f"commit {pin}, both set in configs/env/backend.env; delete the "
                f"row (DELETE FROM service_settings WHERE name = '{row.name}')",
                setting.service,
                service,
            )
            continue
        if setting is None or setting.fixed:
            log.warning(
                "%s is ignored: %s",
                stored,
                "the deployment owns it" if setting else "nothing configures it",
            )
            continue
        if (found := catalog.refusal(setting, row.value)) is not None:
            _refuse(
                f"{stored} is refused now: {found[1]} Set a value the catalogue "
                f"accepts, or return it to the file with make settings-unset {row.name}",
                setting.service,
                service,
            )
            continue
        if row.value != file.get(row.name, ""):
            log.warning(
                "%s overrides the file's %r",
                stored,
                file.get(row.name),
            )


def _owner(setting: catalog.Setting | None, row: Any) -> str:
    """The service a row configures: its setting's, else the one it was stored under."""
    return setting.service if setting is not None else getattr(row, "service", "")


def _refuse(said: str, owner: str, service: str | None) -> None:
    """Refuses the build of `service` over a row of `owner`'s, or warns for another stage's."""
    if service is None or owner in (service, "platform"):
        raise StoredRefused(said)
    log.warning("%s; it stops the %s stage, not this one", said, owner)


def snapshot(service: str | None = None) -> tuple[dict[str, str], str]:
    """The source to read settings from, and the name of that configuration.

    Both from one read of the table, so a row cannot be stamped with a
    configuration it was not produced under. The rows are audited first, for
    the stage `service` names: every stage builds on this, parsing and chunking
    included, so a refused row of its own stops each one alike.

    Raises:
        StoredRefused: If a stored row the stage reads is one the catalogue
            now refuses.
    """
    rows = Settings().rows()
    audit(rows, os.environ, os.environ.get(COMMAND_LINE, "").split(), service)
    source = _source(_applicable(rows))
    return source, version(source)


class Stale(Exception):
    """The stored settings are no longer at the version a change expected."""

    def __init__(self, current: str) -> None:
        """Records the version they are at."""
        super().__init__(current)
        self.current = current


def _applicable(rows: Iterable[Any]) -> dict[str, str]:
    """The rows the catalogue lets a deployment write, by name.

    A row stored before its setting was fixed, or for one since retired, is
    one `clear` refuses and so must not apply.
    """
    return {
        row.name: row.value
        for row in rows
        if row.name in catalog.BY_NAME and not catalog.BY_NAME[row.name].fixed
    }


def _overrides(session: Any) -> dict[str, str]:
    """Every stored setting the catalogue lets a deployment write, by name."""
    return _applicable(session.scalars(select(ServiceSetting)).all())


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

    def rows(self) -> list[ServiceSetting]:
        """Every stored row, applicable or not, as `audit` reads them."""
        with self._session() as session:
            return list(session.scalars(select(ServiceSetting)).all())

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

    def clear(self, name: str) -> bool:
        """Deletes one override, saying whether there was one.

        Returns the setting to whatever the environment says. There is no
        stored copy of a default to restore.

        Raises:
            KeyError: If nothing is configurable under that name.
            ValueError: If the deployment owns the setting.
        """
        return bool(self.change({}, [name]))
