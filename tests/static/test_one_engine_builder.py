"""Only the database package builds an engine, so the credential seam is not routed around.

import-linter squashes an external package to its top name, so it cannot single
out `create_engine`; this reads the calls instead. The two places that may are
`database/qa_generator/engine.py`, and `database/migrations/env.py`, which
needs a pool of its own and asks the same credential.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {
    "backend/database/qa_generator/engine.py",
    "backend/database/migrations/env.py",
}
BUILDERS = {"create_engine", "engine_from_config"}
TREES = (
    "backend",
    "frontend",
    "telemetry",
    "review",
    "evaluation",
    "orchestration",
    "scripts",
)


def _callers() -> set[str]:
    found = set()
    for tree in TREES:
        for path in (ROOT / tree).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Call):
                    named = getattr(node.func, "id", None) or getattr(
                        node.func, "attr", None
                    )
                    if named in BUILDERS:
                        found.add(str(path.relative_to(ROOT)))
    return found


def test_only_the_engine_module_and_the_migrations_build_an_engine() -> None:
    """A second builder would connect without asking the credential."""
    assert _callers() == ALLOWED


def test_the_migrations_ask_the_same_credential() -> None:
    """env.py wraps its engine in `authenticated`."""
    assert "authenticated(" in (ROOT / "backend/database/migrations/env.py").read_text()
