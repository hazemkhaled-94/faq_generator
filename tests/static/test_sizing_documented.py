"""The sizing guide names every rate `make estimate` multiplies by.

A rate that moved in `stages/estimate.py` and not in the guide is a guide that
tells an operator one thing and a command another.
"""

from __future__ import annotations

import re
from pathlib import Path

from stages import estimate

ROOT = Path(__file__).resolve().parents[2]


def _section() -> str:
    text = (ROOT / "docs/operations.md").read_text()
    found = re.search(
        r"^## Sizing a corpus\n(.*?)(?=^## )", text, re.MULTILINE | re.DOTALL
    )
    assert found, "docs/operations.md has no 'Sizing a corpus' section"
    return found[1]


def test_the_guide_gives_every_stage_its_measured_rate() -> None:
    """Seconds and dollars a row, as the command holds them."""
    section = _section()
    for rate in estimate.RATES:
        row = next(
            (line for line in section.splitlines() if f"| {rate.stage} " in line), None
        )
        assert row, f"the sizing guide has no row for {rate.stage}"
        cells = [cell.strip() for cell in row.split("|")]
        assert float(cells[3]) == rate.seconds, (rate.stage, row)
        assert float(cells[4]) == rate.usd, (rate.stage, row)


def test_the_guide_works_the_ten_times_example_and_names_the_command() -> None:
    """The go-live corpus, in hours and dollars, and how to ask for one's own."""
    section = _section()

    assert "make estimate" in section
    assert re.search(r"300 (documents|PDFs)", section)
    assert re.search(r"20,000 passages", section)


def test_the_target_exists_and_is_documented() -> None:
    """Listed with the targets that never run a stage."""
    assert re.search(r"^estimate:", (ROOT / "Makefile").read_text(), re.MULTILINE)
    assert "`make estimate`" in (ROOT / "docs/make.md").read_text()
