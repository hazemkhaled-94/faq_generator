"""Filling a prompt template, where a value may carry a placeholder too."""

from __future__ import annotations

from llm.prompt import fill


def test_a_value_carrying_a_placeholder_is_left_as_written() -> None:
    """A label naming `{{excerpts}}` must not pull the excerpts in after it."""
    filled = fill(
        "Taken: {{taken}}\nExcerpts: {{excerpts}}",
        {"{{taken}}": "the {{excerpts}} label", "{{excerpts}}": "- a passage"},
    )

    assert filled == "Taken: the {{excerpts}} label\nExcerpts: - a passage"


def test_a_placeholder_nothing_names_is_left_in_place() -> None:
    """So the static check that every placeholder is filled can see it."""
    assert fill("{{a}} {{b}}", {"{{a}}": "x"}) == "x {{b}}"
