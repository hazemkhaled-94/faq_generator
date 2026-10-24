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


def test_a_stage_holding_rows_made_before_a_setting_moved_is_listed_with_the_fix() -> (
    None
):
    """After a change, `make settings` says what is still made under the old one."""
    said = behind(
        "extraction",
        "ab12",
        count=lambda stage, version: {"EXTRACTION_DIGEST_MIN_CHARS": 252},
    )

    (line,) = said
    assert "252 stored fact(s)" in line and "EXTRACTION_DIGEST_MIN_CHARS" in line
    assert "make extract-digests" in line
    assert "make extract-rerun" not in line, "a digest-only change is no rerun"
    assert "make extract-revalidate" not in line


def test_a_setting_with_no_cheaper_rebuild_names_the_rerun_alone() -> None:
    """The rerun redoes what every cheaper command would."""
    said = behind(
        "extraction",
        "ab12",
        count=lambda stage, version: {
            "EXTRACTION_DIGEST_MIN_CHARS": 10,
            "EXTRACTION_KINDS": 12,
        },
    )

    (line,) = said
    assert "make extract-rerun" in line
    assert "make extract-digests" not in line


def test_the_topics_stage_names_its_refit_for_a_topic_setting() -> None:
    """A setting of a stage with no cheaper rebuild."""
    (line,) = behind("topics", "ab12", count=lambda stage, version: {"TOPIC_PASSES": 3})

    assert "make topics-discover" in line and "3 stored topic(s)" in line


def test_nothing_is_listed_where_no_staling_setting_moved_after_the_rows() -> None:
    """No setting that stales the stage has a change newer than a row: no line."""
    assert behind("extraction", "ab12", count=lambda stage, version: {}) == []


def test_a_stage_that_records_no_configuration_is_not_asked() -> None:
    """Parsing and chunking keep no version on what they write."""

    def refused(stage: str, version: str) -> dict[str, int]:
        """Fails the test if it is asked."""
        raise AssertionError(f"{stage} was asked")

    assert behind("parsing", "ab12", count=refused) == []
    assert behind("platform", "ab12", count=refused) == []
