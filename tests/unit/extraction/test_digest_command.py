"""What `extraction.run --digests` does where there is no digest to give."""

from __future__ import annotations

import pytest

from extraction import run

#: The extraction settings a source must hold; the kinds are the test's.
_ELSE = {
    "EXTRACTION_DIGEST_MAX_SHARE": "0.3",
    "EXTRACTION_DIGEST_MIN_CHARS": "500",
    "EXTRACTION_MIN_OTHER_SHARE": "0.1",
    "EXTRACTION_BRIDGES_PER_TOPIC": "5",
    "EXTRACTION_BRIDGE_PASSAGES": "3",
    "EXTRACTION_DUPLICATE_COSINE": "0.95",
    "EXTRACTION_DUPLICATE_FLOOR": "0.8",
    "EMBEDDING_MODEL": "test/embedder",
    "EMBEDDING_MAX_TOKENS": "256",
}


def _configured(monkeypatch, kinds: str) -> None:
    """Has the settings store answer with these kinds, and no model behind it."""
    from llm import config

    # Not the process's real logging, which a test must not replace.
    monkeypatch.setattr(run.telemetry, "configure", lambda *a, **k: None)
    monkeypatch.setattr(
        run,
        "snapshot",
        lambda: ({**_ELSE, "EXTRACTION_KINDS": kinds, "LLM_MODEL": "x"}, "v1"),
    )
    monkeypatch.setattr(
        config.Settings, "load", classmethod(lambda cls, source=None: _MODEL)
    )


def _model():
    """The model settings the stage is built with, never called."""
    from llm.config import Settings

    return Settings(
        model="azure/test",
        base_url="http://model.invalid",
        structured_mode="JSON_SCHEMA",
        temperature=0.0,
        timeout_seconds=1.0,
        max_attempts=1,
        num_ctx=None,
        reasoning_effort="off",
    )


_MODEL = _model()


@pytest.mark.parametrize(
    "kinds",
    [
        "atomic,bridge",  # a deployment that writes no digest
        "atomic",
    ],
)
def test_no_digest_to_give_is_a_run_with_nothing_to_do(
    monkeypatch, caplog, kinds: str
) -> None:
    """The corpus build goes on to topics, bridges and questions."""
    _configured(monkeypatch, kinds)

    with caplog.at_level("INFO"):
        assert run.main(["--digests"]) == 0

    assert "nothing to give" in caplog.text


@pytest.mark.parametrize("kinds", ["atomic,bridge", "atomic"])
def test_the_nothing_to_give_line_is_logged_once_logging_is_configured(
    monkeypatch, kinds: str
) -> None:
    """Before that the line goes to a handler nobody set, and is never printed."""
    _configured(monkeypatch, kinds)
    seen: list[str] = []
    monkeypatch.setattr(run.telemetry, "configure", lambda *a, **k: seen.append("on"))
    monkeypatch.setattr(
        run.log, "info", lambda message, *args: seen.append(message % args)
    )

    assert run.main(["--digests"]) == 0

    assert seen[0] == "on" and "nothing to give" in seen[-1], seen


def test_digests_with_other_flags_is_still_refused(monkeypatch) -> None:
    """Misuse stays an error, whatever the kinds."""
    _configured(monkeypatch, "atomic,bridge")

    with pytest.raises(SystemExit, match="takes only --watch"):
        run.main(["--digests", "--retry"])
