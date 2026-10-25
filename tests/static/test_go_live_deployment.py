"""The go-live deployment section carries every condition the gate still relies on.

The final review's go-live gate (2026-10-22) listed what a deployment has to
hold for its open items to stay out of the way. After v0.5.2 these still hold,
each with the setting or the rule an operator acts on, and docs/operations.md
says each one with the item it comes from. A condition that leaves the list
leaves it here too, with its fix named in the upgrade notes.

C-026's lock was measured with two extraction drains side by side and no more,
so nothing a deployment reads scales `extract-worker` past two.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

#: Each condition that still holds after v0.5.2, and the setting or rule its
#: row in the operations guide has to name.
HOLDING = {
    "C-026": "--scale extract-worker=2",
    "C-029": "QUESTIONS_RELEASE_DIFFICULTY",
    "C-031": "distant-from-document",
    "C-052": "space-grouped",
    "C-054": "make extract-dedup",
    "C-056": "image-only",
    "C-082": "two model drains",
    "C-083": "OCR",
    "C-085": "127.0.0.1",
    "C-106": "authored or controls",
    "C-140": "qa_cal_shop",
    "C-162": "v0.4.2",
    "C-186": "unknown type",
    "C-200": "nightly schedule",
    "C-245": "EXTRACTION_DUPLICATE_COSINE",
    "C-266": "contact",
    "C-278": "EMBEDDING_MAX_TOKENS",
    "C-297": "digests",
    "C-366": "LLM_BASE_URL",
    "C-419": "tracked-change",
    "C-424": "QA_MODEL",
}

#: The conditions v0.5.2's fixes lift: no longer in the list, named once in
#: the upgrade notes with the fix.
LIFTED = (
    "C-058",
    "C-059",
    "C-066",
    "C-072",
    "C-075",
    "C-076",
    "C-078",
    "C-079",
    "C-080",
    "C-086",
    "C-088",
    "C-102",
    "C-103",
    "C-107",
    "C-110",
    "C-112",
    "C-114",
    "C-117",
    "C-118",
    "C-119",
    "C-123",
    "C-201",
    "C-219",
    "C-253",
    "C-295",
    "C-299",
    "C-416",
)

_SCALED = re.compile(r"--scale[ =]extract-worker=(\d+)")


def _operations() -> str:
    return (ROOT / "docs/operations.md").read_text()


def _section(text: str, heading: str) -> str:
    """One section, from its heading to the next of the same depth or higher."""
    depth = len(heading) - len(heading.lstrip("#"))
    found = re.search(rf"^{re.escape(heading)}$", text, re.MULTILINE)
    assert found, f"docs/operations.md has no {heading!r}"
    rest = text[found.end() :]
    ends = [
        one.start()
        for one in re.finditer(r"^(#+) ", rest, re.MULTILINE)
        if len(one.group(1)) <= depth
    ]
    return rest[: ends[0]] if ends else rest


def _row(section: str, item: str) -> str:
    """The table row a section gives one item, or an empty string."""
    rows = [line for line in section.splitlines() if line.startswith(f"| {item} |")]
    assert len(rows) <= 1, f"{item} has {len(rows)} rows"
    return rows[0] if rows else ""


def test_the_lists_are_the_gates_forty_eight() -> None:
    """Every condition of the gate is either still holding or lifted, never both."""
    assert not set(HOLDING) & set(LIFTED)
    assert len(HOLDING) + len(LIFTED) == 48


@pytest.mark.parametrize(("item", "rule"), sorted(HOLDING.items()))
def test_every_condition_that_holds_is_in_the_go_live_section(
    item: str, rule: str
) -> None:
    """Its row names the item and the setting or rule an operator follows."""
    row = _row(_section(_operations(), "## Go-live deployment"), item)

    assert row, f"docs/operations.md's Go-live deployment has no row for {item}"
    assert rule in row, f"{item}'s row does not name {rule!r}: {row}"


@pytest.mark.parametrize("item", LIFTED)
def test_a_lifted_condition_is_named_once_in_the_upgrade_notes(item: str) -> None:
    """With its fix, and no longer among the conditions that hold."""
    text = _operations()
    upgrade = _section(text, "## Upgrading to v0.5.2")

    assert _row(upgrade, item), f"Upgrading to v0.5.2 does not name {item}"
    assert not _row(_section(text, "## Go-live deployment"), item), item


def _deployed() -> list[Path]:
    """Every tracked page and compose.yaml: what an operator reads to scale."""
    listed = subprocess.run(
        ["git", "ls-files", "*.md", "compose.yaml"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [ROOT / one for one in listed]


def test_nothing_scales_extract_worker_past_two() -> None:
    """Two drains is what C-026's lock was measured with; more is unmeasured."""
    pages = _deployed()
    assert ROOT / "docs/operations.md" in pages

    scaled = [
        (str(path.relative_to(ROOT)), int(count))
        for path in pages
        for count in _SCALED.findall(path.read_text())
        if int(count) > 2
    ]

    assert not scaled, scaled


def test_compose_runs_no_more_than_two_extract_workers() -> None:
    """Neither a replica count nor a scale in the service itself."""
    service = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"][
        "extract-worker"
    ]

    assert int(service.get("deploy", {}).get("replicas", 1)) <= 2
    assert int(service.get("scale", 1)) <= 2
