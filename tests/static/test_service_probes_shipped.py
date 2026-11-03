"""`deployment.env` ships the System health list as data, and it is the code's own.

The catalogue in `api/services.py` is the fallback and carries the purposes.
A name added to one and not the other is a page that disagrees with the stack.
"""

from __future__ import annotations

import re
from pathlib import Path

from api import services

ROOT = Path(__file__).resolve().parents[2]


def test_deployment_env_lists_the_services_compose_runs() -> None:
    """Every name and port, in the order the page shows them."""
    shipped = re.search(
        r"^SERVICE_PROBES=(.*)$",
        (ROOT / "configs/env/deployment.env").read_text(),
        re.MULTILINE,
    )
    assert shipped, "deployment.env no longer ships SERVICE_PROBES"

    listed = [(one.name, one.port) for one in _parsed(shipped.group(1))]

    assert listed == [(one.name, one.port) for one in services.CATALOGUE]


def _parsed(raw: str) -> tuple[services.Service, ...]:
    import os

    os.environ["SERVICE_PROBES"] = raw
    try:
        return services.probes()
    finally:
        del os.environ["SERVICE_PROBES"]
