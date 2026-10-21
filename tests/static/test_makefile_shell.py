"""The shell the Makefile's recipes run in, read through `make -n`.

`SHELL := /bin/bash`, and on macOS /bin/bash is 3.2, where a bash 4 feature
is a syntax error at the moment a target runs. Every recipe is printed by
`make -n`, which runs nothing, and parsed by `/bin/bash -n`, which runs
nothing either. The one exception is `spend`, run whole against a file that
does not exist: it reads a log and nothing else.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: Values the targets that need one refuse without, so `make -n` prints the
#: recipe rather than the usage line. None of them is read here.
NEEDED = ("SHA=abc", "SERVICE=topics", "SET=TOPIC_PASSES=20", "UNSET=TOPIC_PASSES")


def _environment() -> dict[str, str]:
    return {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("MAKE") and name != "MFLAGS"
    }


def _printed(*arguments: str) -> str:
    return subprocess.run(
        ["make", "-n", "--no-print-directory", *arguments],
        cwd=ROOT,
        env=_environment(),
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _parses(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", "-n"],
        input=script,
        capture_output=True,
        text=True,
        check=False,
    )


TARGETS = sorted(
    set(
        re.findall(
            r"^([a-z][a-zA-Z0-9_-]*):(?!=)",
            (ROOT / "Makefile").read_text(),
            re.MULTILINE,
        )
    )
)


def test_the_targets_are_found() -> None:
    """A Makefile the pattern no longer reads would pass every case below."""
    assert {"corpus", "wipe", "schema-reset", "audit", "help"} <= set(TARGETS)
    assert len(TARGETS) > 120, len(TARGETS)


#: What bash 3.2 parses but fails on when the line runs: expansions and
#: builtins that arrived in bash 4.
_BASH4 = re.compile(
    r"\$\{[^}]*(,,|\^\^|@[QEPAa])\}|\b(mapfile|readarray|coproc)\b"
    r"|declare -[aA]*A|local -n|wait -n|globstar|\$EPOCH"
)


@pytest.mark.parametrize("target", TARGETS)
def test_every_recipe_runs_in_the_bash_a_mac_ships(target: str) -> None:
    """Parsed by bash 3.2, and free of what it parses but fails on when run."""
    printed = _printed(target, *NEEDED)
    parsed = _parses(printed)

    assert parsed.returncode == 0, parsed.stderr
    assert not _BASH4.findall(printed), _BASH4.findall(printed)


@pytest.mark.xfail(
    strict=True,
    reason="make spend and spend-by-shape exit 0 printing 'no priced calls in the log' when LOG names no readable file",
)
@pytest.mark.parametrize("target", ["spend", "spend-by-shape"])
def test_a_log_that_cannot_be_read_fails_the_cost_targets(
    target: str, tmp_path: Path
) -> None:
    """The comment above SPENT says why: "no priced calls" reads as "it cost nothing".

    LOG was made required so that the targets would stop saying that about
    a log they never read. A mistyped LOG still gets it, and exit status 0.
    """
    ran = subprocess.run(
        ["make", "--no-print-directory", target, f"LOG={tmp_path / 'missing.log'}"],
        cwd=ROOT,
        env=_environment(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert ran.returncode != 0, ran.stdout


def test_a_path_with_shell_characters_reaches_the_command_whole() -> None:
    """questions-export quotes its OUT; the export of it in LOADENV does not.

    Make escapes only the spaces in MAKEOVERRIDES, so `export OUT=...` in
    every LOADENV target re-parses whatever else the value holds.
    """
    printed = _printed("questions-export", "OUT=/tmp/Q&A (final).xlsx")

    parsed = _parses(printed)

    assert parsed.returncode == 0, parsed.stderr


def test_the_command_line_names_only_what_was_given() -> None:
    """QA_COMMAND_LINE is the list of names the stored settings give way to."""
    printed = _printed("questions-export", "OUT=/tmp/Projects - Code/r.xlsx")

    assert 'QA_COMMAND_LINE="OUT"' in printed, printed
