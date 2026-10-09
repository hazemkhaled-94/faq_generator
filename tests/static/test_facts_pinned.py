"""The facts service's surface: what its callers and readers rely on.

The routes it serves, which checks each kind of fact faces and in what
order, that every setting it names is catalogued, and that its README
describes every kind and every refusal.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "backend/extraction"

#: One of this service's settings named in a string, refusals included.
_NAMED = re.compile(r"EXTRACTION_[A-Z][A-Z0-9_]*")

#: The queue routes, as (method, path). The four verbs come twice: once for
#: the whole queue and once for the part of it a scope names.
QUEUE_ROUTES = frozenset(
    {
        ("GET", "/extraction/status"),
        ("POST", "/extraction/{action}"),
        ("GET", "/extraction/{scope}/{value}/status"),
        ("POST", "/extraction/{scope}/{value}/{action}"),
    }
)

#: The routes that read back what the service produced.
FACT_ROUTES = frozenset(
    {
        ("GET", "/facts"),
        ("GET", "/facts/quality"),
        ("GET", "/facts/{fact_id}/passages"),
    }
)

#: Which checks each kind faces, in the order they are applied. This is the
#: whole of what "kind" means, so it is pinned rather than described.
CHECKS = {
    "atomic": ("_copied", "_asserts", "_atomic", "_supported", "_self_contained"),
    "summary": ("_asserts", "_supported", "_condensed"),
    "outline": ("_listed", "_supported", "_condensed"),
    "bridge": ("_asserts", "_atomic", "_supported", "_self_contained", "_bridging"),
}


def test_every_setting_the_service_names_is_catalogued() -> None:
    """A new setting is a new thing to configure, document and default."""
    from settings.catalog import BY_NAME

    found: set[str] = set()
    for path in (*SERVICE.glob("*.py"), *(SERVICE / "extractors").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found |= set(_NAMED.findall(node.value))

    assert found <= set(BY_NAME), f"not catalogued: {sorted(found - set(BY_NAME))}"


@pytest.mark.parametrize(
    ("module", "attribute", "pinned"),
    [
        ("api.routes.extraction", "router", QUEUE_ROUTES),
        ("api.routes.facts", "router", FACT_ROUTES),
    ],
)
def test_the_service_serves_exactly_the_routes_named_here(
    module, attribute, pinned
) -> None:
    """The frontend and the Makefile both address these by hand."""
    from importlib import import_module

    router = getattr(import_module(module), attribute)
    found = {
        (method, route.path)
        for route in router.routes
        for method in getattr(route, "methods", ())
        if method != "HEAD"
    }

    assert found == pinned, (
        f"added: {sorted(found - pinned)}, gone: {sorted(pinned - found)}"
    )


def test_each_kind_faces_exactly_the_checks_named_here() -> None:
    """Which checks a kind faces is the whole of what its kind means."""
    from database.qa_generator import FactKind
    from extraction.validation import FactChecker

    applied = {
        kind: tuple(
            getattr(check, "func", check).__name__
            for check in FactChecker(0.6)._by_kind[kind]
        )
        for kind in FactKind
    }

    assert applied == CHECKS


def test_a_statement_nobody_wrote_faces_one_check() -> None:
    """A grid is neither written nor a sentence, so nothing else applies."""
    from extraction.validation import _COMPOSED

    assert tuple(check.__name__ for check in _COMPOSED) == ("_copied",)


def test_the_service_documents_itself() -> None:
    """The README is the service's description, so it has to be there."""
    readme = SERVICE / "README.md"

    assert readme.exists(), f"{readme} is missing"
    written = readme.read_text()
    for heading in ("## What it does", "## Configuration", "## Tests"):
        assert heading in written, f"the README has no {heading!r} section"


def test_the_readme_describes_every_kind_and_every_refusal() -> None:
    """A vocabulary the reader cannot look up is a vocabulary nobody uses."""
    from database.qa_generator import FactKind, Rejection

    written = (SERVICE / "README.md").read_text()

    missing = [name for name in (*FactKind, *Rejection) if name not in written]
    assert not missing, f"undocumented: {sorted(missing)}"
