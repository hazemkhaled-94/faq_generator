"""A path given to make reaches the command as one argument.

The checkout itself lives under "Projects - Code" on OneDrive, so a path
with a space in it is the ordinary case here, not an odd one. Read through
`make -n`, which runs nothing.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

_SPACED = "/tmp/Projects - Code/release.xlsx"


def _command(*arguments: str) -> list[str]:
    """The last command `make -n` prints, split as the shell splits it."""
    inherited = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("MAKE") and name != "MFLAGS"
    }
    printed = subprocess.run(
        ["make", "-n", "--no-print-directory", *arguments],
        cwd=ROOT,
        env=inherited,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return shlex.split(printed[-1])


def _after(words: list[str], flag: str) -> str:
    return words[words.index(flag) + 1]


def test_a_path_without_a_space_reaches_the_command_whole() -> None:
    """The baseline the two below are measured against."""
    words = _command("questions-export", "OUT=/tmp/release.xlsx")

    assert _after(words, "--out") == "/tmp/release.xlsx"


@pytest.mark.parametrize(
    ("target", "given", "flag"),
    [
        ("questions-export", "OUT", "--out"),
        ("diversity", "FILE", "--file"),
        ("diversity", "AGAINST", "--against"),
    ],
)
def test_a_path_with_a_space_reaches_the_command_whole(
    target: str, given: str, flag: str
) -> None:
    """One argument, exactly as typed."""
    words = _command(target, "FILE=/tmp/a.xlsx", f"{given}={_SPACED}")

    assert _after(words, flag) == _SPACED
