"""Every Hugging Face model the backend loads is pinned to one revision.

A repository id alone resolves to whatever its default branch holds on the
day a worker first downloads it: only parse-worker runs with HF_HUB_OFFLINE
(compose.yaml), and the tokenizer chunking sizes passages with is one of
these.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: The calls that fetch from the hub by repository id.
_LOADERS = {"from_pretrained", "SentenceTransformer", "pipeline"}


def _loads() -> list[tuple[str, ast.Call]]:
    found = []
    for path in sorted((ROOT / "backend").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            # transformers' pipeline takes model=; spaCy's own pipeline() does not.
            if name == "pipeline" and not any(k.arg == "model" for k in node.keywords):
                continue
            if name in _LOADERS:
                found.append((f"{path.relative_to(ROOT)}:{node.lineno}", node))
    return found


def test_the_scan_finds_the_four_hub_loads() -> None:
    """The embedder, the chunker's tokenizer, the NLI and QA encoders."""
    sites = [site for site, _ in _loads()]

    assert any("nlp/embedding.py" in site for site in sites), sites
    assert any("chunking/passages.py" in site for site in sites), sites
    assert any("nlp/entailment.py" in site for site in sites), sites
    assert any("nlp/qa.py" in site for site in sites), sites


@pytest.mark.xfail(
    strict=True,
    reason="QA-security-3: EMBEDDING_MODEL, NLI_MODEL, QA_MODEL and the "
    "chunking tokenizer load by bare hub id with no revision, so a push to "
    "the repository changes passages and scores under the same settings",
)
def test_every_hub_load_names_a_revision() -> None:
    """A `revision=` at every call, or nothing reaches the hub at run time."""
    unpinned = [
        site
        for site, call in _loads()
        if not any(keyword.arg == "revision" for keyword in call.keywords)
    ]

    assert unpinned == []
