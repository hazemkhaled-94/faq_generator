"""A queue verb for a model stage says what drains it on the go-live profile.

With HOST_RUNNER=1 no worker drains a model stage, so a verb that queues its
rows still answers 202 and names the host command that will.
"""

from __future__ import annotations

import pytest


@pytest.mark.parametrize("stage", ["extraction", "topics", "questions", "assessment"])
@pytest.mark.parametrize("verb", ["start", "retry", "rerun", "reclaim"])
def test_a_verb_for_a_model_stage_names_the_command_that_drains_it(
    monkeypatch, stage, verb
) -> None:
    """Queued, and told that no worker will take it."""
    from api.routes.stage import answered

    monkeypatch.setenv("HOST_RUNNER", "1")

    said = answered(stage, verb, 3)

    assert said.rows == 3
    assert "make corpus-hosted" in said.detail


@pytest.mark.parametrize("stage", ["parsing", "chunking"])
def test_a_verb_for_a_stage_that_calls_no_model_says_nothing_of_the_runner(
    monkeypatch, stage
) -> None:
    """Its workers run on the go-live profile."""
    from api.routes.stage import answered

    monkeypatch.setenv("HOST_RUNNER", "1")

    assert "corpus-hosted" not in answered(stage, "start", 3).detail


def test_without_the_host_runner_a_verb_reads_as_it_did(monkeypatch) -> None:
    """The container worker drains it."""
    from api.routes.stage import answered

    monkeypatch.delenv("HOST_RUNNER", raising=False)

    assert answered("extraction", "start", 3).detail == (
        "3 row(s) queued; the worker will pick them up."
    )


def test_a_stop_names_no_runner(monkeypatch) -> None:
    """Taking rows back needs no drain."""
    from api.routes.stage import answered

    monkeypatch.setenv("HOST_RUNNER", "1")

    assert "corpus-hosted" not in answered("extraction", "stop", 3).detail
