"""Ingestion, parsing and chunking: what holds across the three.

The parsing registry dispatches exactly the types ingestion may accept, and
each stage describes itself in a README beside its code: they share one
story - a file becomes a document becomes passages - and they are three
packages with three queues and three command lines.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: The three packages, by stage.
SERVICES = {
    "ingestion": ROOT / "backend/ingestion",
    "parsing": ROOT / "backend/preprocessing/parsing",
    "chunking": ROOT / "backend/preprocessing/chunking",
}

#: The headings every service README carries, as in test_topics_pinned.py
#: and test_facts_pinned.py.
HEADINGS = ("## What it does", "## Configuration", "## Tests")


def test_the_registry_dispatches_exactly_the_types_the_allowlist_may_name() -> None:
    """A type ingestion accepts and no pipeline handles fails at parsing."""
    from ingestion.models import DETECTABLE
    from preprocessing.parsing.pipelines import PdfPipeline

    assert PdfPipeline.media_types == tuple(sorted(DETECTABLE))


@pytest.mark.parametrize("service", sorted(SERVICES))
def test_each_stage_documents_itself(service: str) -> None:
    """The README is the stage's description, so it has to be there."""
    readme = SERVICES[service] / "README.md"

    assert readme.exists(), f"{readme} is missing"
    written = readme.read_text()
    for heading in HEADINGS:
        assert heading in written, f"{service} has no {heading!r} section"
