"""The sentence naming a language in an extraction message, and its absence."""

from __future__ import annotations

import pytest
from drivers import group, passage

from extraction.extractors.bridge import BridgeExtractor
from extraction.extractors.digest import DigestExtractor
from extraction.extractors.llm import _REPAIR_USER, LlmExtractor
from nlp.models import with_language


def sent(language: str | None) -> list[str]:
    """The four messages one extractor family renders for a passage in `language`."""
    one = passage("Les remboursements sont émis sous dix jours.", language=language)
    pair = group("Returns need a receipt.", "Urgent requests take 4 hours.")
    for each in pair:
        object.__setattr__(each, "language", language)
    return [
        LlmExtractor._prompt(one),
        LlmExtractor._prompt(one, _REPAIR_USER, {"{{refused}}": "none"}),
        DigestExtractor._prompt(one),
        BridgeExtractor._prompt(pair, None, {}),
    ]


@pytest.mark.parametrize(
    ("language", "name"), [("de", "German"), ("en", "English"), ("fr", "fr"), ("el", "el")]
)
def test_a_language_is_named_in_every_message(language: str, name: str) -> None:
    """A language the table does not know is named by its code."""
    for user in sent(language):
        assert f" in {name}." in user, user


def test_no_language_leaves_no_sentence_and_no_dangling_in() -> None:
    """The model was told to write in an empty name."""
    for user in sent(None):
        assert "in ." not in user and "{{language}}" not in user, user
        assert "Write every statement" not in user
        assert "Write the summary" not in user


def test_the_sentence_is_dropped_only_where_it_is() -> None:
    """A template with no language placeholder is returned as it was."""
    assert with_language("Excerpt:\n{{excerpt}}", None) == "Excerpt:\n{{excerpt}}"
    assert with_language("A\n\nWrite it in {{language}}.", "de") == "A\n\nWrite it in {{language}}."
    assert with_language("A\n\nWrite it in {{language}}.", None) == "A"
