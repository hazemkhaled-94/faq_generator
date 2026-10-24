"""The build context is an allowlist of what the images copy.

Every image builds from the repository root, so whatever the root holds is sent
to the engine as context. A denylist grows a hole every time a folder is added:
`client-assessments/` and `resources/` went to the daemon with every build, a
customer's workbooks among them. The file starts by excluding everything and
names what the Dockerfiles copy.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILES = (
    "backend/api/Dockerfile",
    "frontend/Dockerfile",
    "orchestration/Dockerfile",
)


def _rules() -> list[tuple[bool, re.Pattern[str]]]:
    """The rules of .dockerignore, in order, as (negated, matcher)."""
    rules = []
    for line in (ROOT / ".dockerignore").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        pattern = line.lstrip("!").rstrip("/")
        regex = re.escape(pattern)
        regex = regex.replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*")
        regex = regex.replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
        regex = regex.replace(r"\[", "[").replace(r"\]", "]")
        rules.append((negated, re.compile(regex)))
    return rules


def ignored(path: str) -> bool:
    """Whether the engine leaves a path out: the last rule matching it or a parent."""
    parts = path.split("/")
    candidates = ["/".join(parts[: n + 1]) for n in range(len(parts))]
    out = False
    for negated, matcher in _rules():
        if any(matcher.fullmatch(one) for one in candidates):
            out = not negated
    return out


def test_the_file_starts_by_excluding_everything() -> None:
    """An allowlist, not a list of what to leave out."""
    first = next(
        line
        for line in (ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    )

    assert first == "*"


@pytest.mark.parametrize(
    "path",
    [
        "client-assessments/acme/report.xlsx",
        "resources/corpus/handbook.pdf",
        "review/app.py",
        "evaluation/run.py",
        "docs/operations.md",
        "tests/unit/test_x.py",
        ".git/config",
        ".env",
        "certs/ca.key",
        "logs/app.log",
        "poetry.lock",
        "configs/env/provider.env",
    ],
)
def test_what_no_image_copies_stays_out_of_the_context(path: str) -> None:
    """The customer's files, the secrets and the history."""
    assert ignored(path), path


@pytest.mark.parametrize(
    "path", ["backend/api/__pycache__/x.pyc", "backend/a/b.pyc", "frontend/.DS_Store"]
)
def test_build_litter_inside_what_is_copied_stays_out(path: str) -> None:
    """A copied folder is not a licence to send its caches."""
    assert ignored(path), path


def _copied() -> list[str]:
    """Every source a Dockerfile COPY names."""
    found = []
    for dockerfile in DOCKERFILES:
        for line in (ROOT / dockerfile).read_text().splitlines():
            parts = line.split()
            if parts[:1] == ["COPY"] and not any(p.startswith("--from") for p in parts):
                found += [one for one in parts[1:-1] if not one.startswith("--")]
    return found


def test_the_scan_finds_what_the_images_copy() -> None:
    """Not a vacuous list."""
    assert {
        "backend/api/",
        "frontend/",
        "orchestration/",
        "telemetry/",
        "pyproject.toml",
    } <= set(_copied())


@pytest.mark.parametrize("source", sorted(set(_copied())))
def test_everything_a_dockerfile_copies_is_in_the_context(source: str) -> None:
    """Else the build fails with a missing file, a long way from the cause."""
    probe = source if not source.endswith("/") else source + "x.py"

    assert not ignored(probe), source
