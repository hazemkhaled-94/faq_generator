"""The go-live runbook names the commands and the settings it depends on.

The runbook in docs/operations.md is what a fresh clone follows, so it has to
say the host runner, the spend cap and the split's variables, in the order they
are used.
"""

from __future__ import annotations

import re
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
        "make install",
        "make docling-weights HOST=1",
        "make schema",
        "make ingest DIR=",
        "make corpus-hosted",
        "SPEND_CAP",
        "HOST_RUNNER",
        "LLM_REASONING_EFFORT",
        "seven role models",
        "make doctor",
        "make up",
    ):
        assert needle in runbook, needle


#: The runbook's steps as a fresh clone runs them, each by its number and the
#: command it opens with: the host environment and the containers' weights
#: before the stack, the schema before the first document, the documents
#: before the run.
STEPS = (
    ("1.", "Clone outside"),
    ("2.", "`cp .env.example .env`"),
    ("3.", "`make install`"),
    ("4.", "`make up`"),
    ("5.", "`make schema`"),
    ("6.", "`make doctor`"),
    ("7.", "`make ingest DIR="),
    ("8.", "`make corpus-hosted"),
    ("9.", "`make questions-export"),
)


def _steps() -> list[str]:
    """Each numbered step of the runbook, joined to one line."""
    text = (ROOT / "docs/operations.md").read_text()
    body = text.split("### The runbook", 1)[1].split("\n### ", 1)[0]
    found = re.split(r"^(\d+\.) ", body, flags=re.MULTILINE)
    return [
        f"{number} " + " ".join(step.split())
        for number, step in zip(found[1::2], found[2::2], strict=True)
    ]


def test_the_runbook_runs_its_steps_in_the_order_they_are_used() -> None:
    """Clone, configure, install, up, schema, doctor, load, run, export."""
    steps = _steps()

    assert len(steps) == len(STEPS), steps
    for step, (number, opening) in zip(steps, STEPS, strict=True):
        assert step.startswith(f"{number} {opening}"), (number, opening, step[:80])


def test_the_installed_steps_come_before_what_needs_them() -> None:
    """The virtualenv before the doctor, the volume's weights before a parse."""
    steps = _steps()

    def opening(command: str) -> int:
        return next(
            at for at, s in enumerate(steps) if s.split(" ", 1)[1].startswith(command)
        )

    install = opening("`make install`")
    assert "make docling-weights HOST=1" in steps[install], steps[install]
    for later in ("`make doctor`", "`make ingest DIR=", "`make corpus-hosted"):
        assert install < opening(later), later


def test_a_corpus_is_loaded_through_the_host_and_a_few_files_through_the_page() -> None:
    """The Upload page refuses more than 20 files at once."""
    load = next(step for step in _steps() if "`make ingest DIR=" in step)

    assert "Upload page" in load and "20 files" in load, load


def test_every_command_the_runbook_names_is_a_target() -> None:
    """A target that does not exist is a step nobody can follow."""
    targets = set(
        re.findall(
            r"^([a-z][a-z0-9-]*):", (ROOT / "Makefile").read_text(), re.MULTILINE
        )
    )
    named = set(re.findall(r"`make ([a-z][a-z0-9-]*)", " ".join(_steps())))

    assert named, "the runbook names no make target"
    assert named <= targets, sorted(named - targets)


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
