"""What the settings command line prints after a change."""

from __future__ import annotations

import os

from settings.run import change


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
