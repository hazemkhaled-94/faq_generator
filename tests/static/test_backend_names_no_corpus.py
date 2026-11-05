"""No backend source line is worked out of a corpus the project was calibrated on.

`test_prompts_name_no_domain` keeps the corpora's words out of what a model
is sent; this keeps the football corpus's out of backend source. A comment or a docstring is read by the next person fitting a gate,
and a worked example in one is how a corpus's vocabulary gets into a rule: the
example is the case the rule was fitted to. So its words are held out of
every backend source line, and an example is taken from banking or retail.

A failure names the file, the line and the word.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: The football corpus's words, German and English. Lower-case, matched as a
#: substring: a German compound is the leak whatever it is joined to. A
#: regression guard, as the prompt guard's list is, and not a definition of a
#: domain. The software-testing, regulatory and shop words of that list also
#: stand in backend comments; they are not held here yet.
CORPUS_WORDS = (
    "football",
    "fussball",
    "fußball",
    "elfmeter",
    "torhüter",
    "schiedsrichter",
    "referee",
    "offside",
    "spielfeld",
    "ball-im-spiel",
    "anspucken",
    "verwarnung",
    "goal kick",
    "free kick",
    "freistoss",
)

SOURCES = sorted(
    path
    for path in (ROOT / "backend").rglob("*.py")
    if "migrations" not in path.parts and "__pycache__" not in path.parts
)


def test_there_is_backend_source_to_read() -> None:
    """A moved directory would otherwise pass as nothing to say."""
    assert len(SOURCES) > 100


@pytest.mark.parametrize("word", CORPUS_WORDS)
def test_no_backend_line_carries_a_word_of_a_calibration_corpus(word: str) -> None:
    """Code, comments and docstrings alike."""
    found = [
        f"{path.relative_to(ROOT)}:{number}"
        for path in SOURCES
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        )
        if word in line.lower()
    ]

    assert not found, f"{word!r}: {found[:5]}"
