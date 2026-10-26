"""A command a page shows for a target that destroys data runs as written.

Every such target refuses unless CONFIRM on the command line names what it
acts on (the database, `stack` or `all-volumes`), so an example that leaves it
out is one an operator copies and is refused by. An example is a line of a
code block, or an inline command given arguments; a target named in prose is
not one.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: The targets that refuse without CONFIRM, as the Makefile guards them. An
#: unnarrowed rerun is among them; one narrowed by SHA, PASSAGE, TOPIC or ONLY
#: is not.
_DESTRUCTIVE = (
    "parse-rerun|chunk-rerun|extract-rerun|questions-rerun|assess-rerun|"
    "delete|delete-derived|wipe|wipe-all|topics-delete|archive-purge|"
    "schema-reset|schema-down|phoenix-purge|review-delete|logs-wipe|"
    "dagster-wipe|down-volumes|restore-backup|restore-backup-stack"
)
_COMMAND = re.compile(rf"make ({_DESTRUCTIVE})(?![\w-])([^`\n#]*)")
_NARROWED = ("SHA=", "PASSAGE=", "TOPIC=", "ONLY=")


def _examples() -> list[tuple[str, int, str]]:
    """(page, line, command) for every example of a destructive target."""
    pages = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    found = []
    for page in pages:
        fenced = False
        for number, line in enumerate((ROOT / page).read_text().splitlines(), 1):
            if line.strip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                commands = [m for m in _COMMAND.finditer(line.split(" #", 1)[0])]
            else:
                commands = [
                    m
                    for span in re.findall(r"`([^`]*)`", line)
                    for m in _COMMAND.finditer(span)
                    if m.group(2).strip()
                ]
            found += [(page, number, m.group(0).strip()) for m in commands]
    return found


def test_the_scan_finds_the_examples() -> None:
    """So the check below cannot pass by reading nothing."""
    pages = {page for page, _, _ in _examples()}

    assert "docs/operations.md" in pages and "docs/make.md" in pages, pages


def test_every_destructive_example_carries_its_confirm() -> None:
    """A rerun narrowed to one item needs none, and is left out."""
    missing = [
        f"{page}:{line}: {command}"
        for page, line, command in _examples()
        if "CONFIRM=" not in command
        and not ("-rerun" in command and any(one in command for one in _NARROWED))
    ]

    assert not missing, "\n".join(missing)
