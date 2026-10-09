"""The topic modelling service's surface, pinned.

The routes it serves, that every setting it names is catalogued, and its
README.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "backend/topic_modelling"

#: One of this service's settings named in a string, refusals included.
_NAMED = re.compile(r"TOPIC_[A-Z][A-Z0-9_]*")

#: Every route under /topics, as (method, path).
ROUTES = frozenset(
    {
        ("GET", "/topics/status"),
        ("GET", "/topics"),
        ("GET", "/topics/fit"),
        ("GET", "/topics/visualisation/{language}"),
        ("PATCH", "/topics/{topic_id}"),
        ("POST", "/topics/discover"),
        ("POST", "/topics/stop"),
        ("POST", "/topics/retry"),
        ("DELETE", "/topics"),
    }
)


def test_every_setting_the_service_names_is_catalogued() -> None:
    """A new setting is a new thing to configure, document and default.

    Over every string the service holds, not only the ones it passes to a
    reader, so a name that appears in a refusal is checked too - one of them
    was wrong on the Topics page for a while.
    """
    from settings.catalog import BY_NAME

    found: set[str] = set()
    for path in SERVICE.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found |= set(_NAMED.findall(node.value))

    assert found <= set(BY_NAME), f"not catalogued: {sorted(found - set(BY_NAME))}"


def test_the_service_serves_exactly_the_routes_named_here() -> None:
    """The frontend and the Makefile both address these by hand."""
    from api.routes.topics import router

    found = {
        (method, route.path)
        for route in router.routes
        for method in getattr(route, "methods", ())
        if method != "HEAD"
    }

    assert found == ROUTES, (
        f"added: {sorted(found - ROUTES)}, gone: {sorted(ROUTES - found)}"
    )


def test_the_service_documents_itself() -> None:
    """The README is the service's description, so it has to be there."""
    readme = SERVICE / "README.md"

    assert readme.exists(), f"{readme} is missing"
    written = readme.read_text()
    for heading in ("## What it does", "## Configuration", "## Tests"):
        assert heading in written, f"the README has no {heading!r} section"
