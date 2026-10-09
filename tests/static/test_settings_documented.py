"""Every setting the code reads is named in a file that declares it.

There are no defaults in code: a missing variable stops the service at
start-up. This is that failure moved to the pull request, where the fix is
one line in a file rather than a container that will not come up.

Only names written as literals are checked. A setting read through a
variable - the pool sizes in database/qa_generator/engine.py, LOG_DIR in
telemetry/logs.py - is invisible here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.static.settings_scan import read_by

ROOT = Path(__file__).resolve().parents[2]

#: Where a setting may be declared: how the pipeline behaves, then where
#: this deployment put things, then the credentials and the model.
DECLARING = (
    "configs/env/backend.env",
    "configs/env/deployment.env",
    "configs/env/orchestration.env",
    "configs/env/review.env",
    "configs/env/evaluation.env",
    ".env.example",
)

#: Directories holding the code that runs in a container.
SOURCES = (
    "backend",
    "frontend",
    "telemetry",
    "orchestration",
    "review",
    "evaluation",
)

#: A declaration, commented out or not: an optional setting is documented by
#: a commented line rather than by a value.
_DECLARATION = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)\s*=", re.MULTILINE)


def _readers() -> dict[Path, set[str]]:
    """Every module that reads a setting, and which ones it reads."""
    found = {}
    for source in SOURCES:
        for path in sorted((ROOT / source).glob("**/*.py")):
            if "__pycache__" in path.parts:
                continue
            names = read_by(path.read_text())
            if names:
                found[path] = names
    return found


READS = _readers()


def test_the_scan_finds_the_settings_it_is_meant_to_guard() -> None:
    """A refactor that moved the readers would otherwise pass silently."""
    every = {name for names in READS.values() for name in names}

    assert "NLP_MODELS" in every, every
    assert "DATABASE_URL" in every, every
    assert "QUESTIONS_TYPE_MIX" in every, "the mapping reader is scanned here"
    assert len(every) > 25, sorted(every)


@pytest.mark.parametrize("path", READS, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_setting_a_module_reads_is_declared(path: Path) -> None:
    """Named in configs/env/backend.env or in .env.example."""
    declared = {
        name
        for file in DECLARING
        for name in _DECLARATION.findall((ROOT / file).read_text())
    }
    undeclared = READS[path] - declared

    assert not undeclared, (
        f"{', '.join(sorted(undeclared))} is read here but declared in neither "
        f"{' nor '.join(DECLARING)}"
    )
