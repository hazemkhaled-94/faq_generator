"""The chunker and the furniture pass read a document through one set of helpers."""

from __future__ import annotations

import ast
import re
from pathlib import Path

CHUNKING = Path(__file__).resolve().parents[2] / "backend/preprocessing/chunking"


def _defined(name: str, module: str) -> bool:
    """Whether a module's top level assigns or defines the name."""
    return any(
        (isinstance(node, ast.FunctionDef) and node.name == name)
        or (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
        )
        for node in ast.parse((CHUNKING / module).read_text()).body
    )


def test_passages_reads_references_and_prose_labels_from_furniture() -> None:
    """A second copy of `_PROSE` or of the reference lookup would drift from the first."""
    assert _defined("_PROSE", "furniture.py") and _defined("_resolved", "furniture.py")
    assert not _defined("_PROSE", "passages.py")
    assert not _defined("_node", "passages.py")
    assert not re.search(
        r'model_validate\(\{"\$ref"[^}]*\}\)\.resolve',
        (CHUNKING / "passages.py").read_text(),
    )
