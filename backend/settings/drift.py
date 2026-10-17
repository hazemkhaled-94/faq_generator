"""Whether the api serves the settings this checkout catalogues.

The api and the six workers run the image they were built from, and a
checkout moves on without them. An image older than a setting serves every
other one, and nothing said so: the only sign was a Configuration page one
control short.

    python -m settings.drift <compose>     # which is what `make doctor` runs

`<compose>` is the compose command, and only names the rebuild.

Compared by name, so a build that changed code and added no setting is not
found. The values are not compared: the api reads the containers' files and
this reads the host's, and the two differ on purpose.
"""

from __future__ import annotations

import logging
import sys

import requests

import telemetry
from settings import catalog
from settings.env import required

log = logging.getLogger(__name__)

#: Long enough for a busy api on this machine, short enough that a hung one
#: does not hold up the doctor.
TIMEOUT_SECONDS = 10.0

#: What the api answers for a service its build does not have, which serves
#: no setting rather than meaning the api is unwell.
_UNKNOWN_SERVICE = (404, 422)


def _services() -> list[str]:
    """Every catalogued service, in declaration order."""
    return list(dict.fromkeys(one.service for one in catalog.SETTINGS))


def missing(served: dict[str, set[str]]) -> dict[str, tuple[set[str], set[str]]]:
    """Compares the setting names the api serves with this checkout's.

    Args:
        served: The names the api serves, by service. A service absent here
            serves none.

    Returns:
        Each service that differs, with the names it lacks and the names it
        serves that this checkout does not catalogue. Empty when they agree.
    """
    differs: dict[str, tuple[set[str], set[str]]] = {}
    for service in _services():
        wanted = {one.name for one in catalog.of(service)}
        has = served.get(service, set())
        if has != wanted:
            differs[service] = (wanted - has, has - wanted)
    return differs


def served(url: str) -> dict[str, set[str]]:
    """Reads the setting names the api at `url` serves, by service.

    Raises:
        requests.RequestException: If the api did not answer, or answered
            with an error that is not an unknown service.
    """
    found: dict[str, set[str]] = {}
    for service in _services():
        answer = requests.get(f"{url}/settings/{service}", timeout=TIMEOUT_SECONDS)
        if answer.status_code in _UNKNOWN_SERVICE:
            found[service] = set()
            continue
        answer.raise_for_status()
        found[service] = {one["name"] for one in answer.json()["settings"]}
    return found


def main(argv: list[str] | None = None) -> int:
    """Asks the api what it serves, and says what differs from this checkout.

    Args:
        argv: The compose command, or None to read it from sys.argv.

    Returns:
        The process exit code: 1 if the api serves another catalogue, and 0
        if it serves this one or is not answering.
    """
    telemetry.configure("doctor")

    compose = " ".join(sys.argv[1:] if argv is None else argv) or "podman compose"
    url = required("BACKEND_URL").rstrip("/")
    try:
        differs = missing(served(url))
    except requests.RequestException as unanswered:
        log.warning(
            "the api at %s did not serve its settings, so they were not compared: %s",
            url,
            unanswered,
        )
        return 0

    if not differs:
        log.info("the api serves this checkout's settings")
        return 0

    for service, (absent, extra) in differs.items():
        if absent:
            log.error(
                "the api serves an older build: its %s settings lack %s",
                service,
                ", ".join(sorted(absent)),
            )
        if extra:
            log.error(
                "the api serves another build: its %s settings have %s, which "
                "this checkout does not",
                service,
                ", ".join(sorted(extra)),
            )
    log.error("rebuild it: %s build api && make up", compose)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
