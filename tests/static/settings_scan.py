"""The settings a module reads, found by literal name in its syntax."""

from __future__ import annotations

import ast

import settings

#: The readers backend/settings exports, then a stage's own readers, which
#: take the setting's name first and hand it on through a variable.
READERS = (frozenset(settings.__all__) - {"Source"}) | {
    "_kinds",
    "_weights",
    "_bounds",
    "_span",
}


def read_by(source: str) -> set[str]:
    """Finds the settings one module reads, by literal name."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and node.args:
            called = node.func
            name = (
                called.id
                if isinstance(called, ast.Name)
                else getattr(called, "attr", None)
            )
            first = node.args[0]
            if (
                name in READERS
                and isinstance(first, ast.Constant)
                and isinstance(first.value, str)
            ):
                found.add(first.value)
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
            and node.slice.value.isupper()
            and "environ" in ast.dump(node.value)
        ):
            found.add(node.slice.value)
    return found
