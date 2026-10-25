"""The go-live runbook names the commands and the settings it depends on.

The runbook in docs/operations.md is what a fresh clone follows, so it has to
say the host runner, the spend cap and the split's variables, in the order they
are used.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _runbook() -> str:
    text = (ROOT / "docs/operations.md").read_text()
    return " ".join(
        text.split("### The runbook", 1)[1].split("### After a stop", 1)[0].split()
    )


def test_the_runbook_names_the_host_runner_the_cap_and_the_split() -> None:
    """Every command and setting a fresh clone needs, by name."""
    runbook = _runbook()

    for needle in (
        "make corpus-hosted",
        "SPEND_CAP",
        "HOST_RUNNER",
        "LLM_REASONING_EFFORT",
        "seven role models",
        "make doctor",
        "make up",
    ):
        assert needle in runbook, needle


def test_the_runbook_runs_its_steps_in_the_order_they_are_used() -> None:
    """Clone, configure, up, doctor, upload, run, export."""
    runbook = _runbook()
    steps = [
        "Clone outside",
        "cp .env.example .env",
        "3. `make up`",
        "4. `make doctor`",
        "5. Upload the documents",
        "6. `make corpus-hosted",
        "questions-export",
    ]

    at = [runbook.index(one) for one in steps]
    assert at == sorted(at), at


def test_the_runbook_says_how_to_resume_after_a_stop() -> None:
    """The next section, which the runbook points at."""
    text = " ".join((ROOT / "docs/operations.md").read_text().split())

    assert "make corpus-hosted` after a stop" in text


def test_after_a_stop_says_how_to_get_past_rows_that_fail_every_time() -> None:
    """A resume retries every failed row, so one that always fails stops every resume."""
    text = (ROOT / "docs/operations.md").read_text()
    section = " ".join(
        text.split("### After a stop", 1)[1].split("\n## ", 1)[0].split()
    )

    for needle in (
        "the same stage",
        "logs/corpus-hosted.log",
        "make delete SHA=",
        "-retry",
        "RESET=1",
    ):
        assert needle in section, needle
