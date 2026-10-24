"""What the settings command line prints after a change."""

from __future__ import annotations

import os

from settings.run import behind, change


class Recording:
    """A store holding no override over the test environment, keeping writes."""

    def __init__(self) -> None:
        """Holds nothing yet."""
        self.written: dict[str, str] = {}

    def resolved(self) -> dict[str, str]:
        """The environment, as nothing stored leaves it."""
        return dict(os.environ)

    def version(self) -> str:
        """The version of an empty store."""
        return "environment"

    def change(self, writes, clears, expected=None) -> list[str]:
        """Keeps the writes; clears nothing."""
        self.written.update(writes)
        return []


def test_a_cheaper_rebuild_is_the_only_one_named() -> None:
    """A new release size is a redraw; a line saying rerun the stage contradicts it."""
    said = change("questions", {"QUESTIONS_RELEASE_SIZE": "50"}, Recording())

    assert any("make questions-balance" in line for line in said), said
    assert not any("rerun" in line for line in said), said


def test_a_lowered_digest_floor_is_met_by_the_digest_pass_and_not_a_rerun() -> None:
    """The cheaper command is the one named, over a re-extraction."""
    said = change("extraction", {"EXTRACTION_DIGEST_MIN_CHARS": "400"}, Recording())

    assert any("make extract-digests" in line for line in said), said


def test_a_stage_holding_rows_of_another_configuration_is_listed_with_the_fix() -> None:
    """After a change, `make settings` says what is still made under the old one."""
    said = behind("extraction", "ab12", count=lambda stage, version: 252)

    (line,) = said
    assert "252 stored fact(s)" in line and "ab12" in line
    assert "make extract-digests" in line and "make extract-revalidate" in line


def test_nothing_is_listed_where_every_row_is_current() -> None:
    """No rows behind, no line."""
    assert behind("extraction", "ab12", count=lambda stage, version: 0) == []


def test_a_stage_that_records_no_configuration_is_not_asked() -> None:
    """Parsing and chunking keep no version on what they write."""

    def refused(stage: str, version: str) -> int:
        """Fails the test if it is asked."""
        raise AssertionError(f"{stage} was asked")

    assert behind("parsing", "ab12", count=refused) == []
    assert behind("platform", "ab12", count=refused) == []
