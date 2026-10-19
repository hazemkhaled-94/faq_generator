"""Which model writes a question, and which one checks it.

Two gates may only be applied by a model that did not write the answer: the
phrasing opinion, which can reject, and the entailment pass, which can only
accept. A writer running either over its own work waves through whatever its
own recall missed.

What decides is whether the two models came out different, not whether a
setting was set. Once the writer can be overridden too, those are different
questions: naming one model in both settings is the same problem as naming
neither, and naming only the writer leaves a verifier that is independent
without QUESTIONS_VERIFIER_MODEL saying so.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from llm.config import Settings as ModelSettings
from question_generation.factory import models

SHARED = ModelSettings(
    model="ollama/shared",
    base_url=None,
    structured_mode="JSON_SCHEMA",
    temperature=0.0,
    timeout_seconds=900.0,
    max_attempts=3,
    num_ctx=None,
    reasoning_effort=None,
)


def settings(writer: str | None, verifier: str | None):
    """Question settings naming these two models and nothing else of note."""
    from question_generation.config import Settings

    loaded = Settings.load()
    return replace(loaded, model=writer, verifier_model=verifier)


@pytest.mark.parametrize(
    ("writer", "verifier", "writes", "checks", "independent"),
    [
        # Neither named: one model does both, which is the state the worker
        # warns about on every start.
        (None, None, "ollama/shared", "ollama/shared", False),
        # Only the verifier named, which is how this worked before a writer
        # could be overridden at all.
        (None, "ollama/checker", "ollama/shared", "ollama/checker", True),
        # Only the writer named. The verifier is still the shared model, and
        # it is still a different one, so the gates apply.
        ("ollama/writer", None, "ollama/writer", "ollama/shared", True),
        # Both named, differently: the arrangement this is all for.
        ("ollama/writer", "ollama/checker", "ollama/writer", "ollama/checker", True),
        # Both named the same. A setting was set, twice, and there is still
        # only one model marking its own work.
        ("ollama/same", "ollama/same", "ollama/same", "ollama/same", False),
        # The writer overridden to the shared model by name, and no verifier.
        ("ollama/shared", None, "ollama/shared", "ollama/shared", False),
    ],
)
def test_which_model_writes_and_which_checks(
    writer, verifier, writes, checks, independent
) -> None:
    """Every combination of the two settings, and what it comes out as."""
    written, checked, _ = models(settings(writer, verifier), SHARED)

    assert written.model == writes
    assert checked.model == checks
    assert (written.model != checked.model) is independent


def test_both_models_are_served_where_the_deployment_says() -> None:
    """A stage names a model, not an address: one runtime serves both."""
    written, checked, _ = models(
        settings("ollama/writer", "ollama/checker"),
        replace(SHARED, base_url="http://served:11434"),
    )

    assert written.base_url == "http://served:11434"
    assert checked.base_url == "http://served:11434"


def test_both_models_are_held_to_the_same_patience() -> None:
    """One stage naming its own model may not also change how patient it is."""
    written, checked, _ = models(settings("ollama/writer", "ollama/checker"), SHARED)

    assert written.timeout_seconds == SHARED.timeout_seconds
    assert checked.max_attempts == SHARED.max_attempts


# ── What a question's citations make it ───────────────────────────────────
#
# The three scopes, and the band they add up to, are read off every passage
# the cited facts rest on, so a real second citation spreads a question. The
# fold a duplicate refusal used to add is data, not something this reading
# can tell apart: tests/integration/database/test_question_queue.py follows
# one from `make extract-dedup` through to the band.


def test_a_second_passage_counts_through_a_real_citation() -> None:
    """A bridge rests on both its passages, and a question on it spans them."""
    from factories import bridge, resting

    from database.qa_generator import DocumentScope, PassageScope, TopicScope
    from question_generation.models import FactGroup

    spans = bridge(resting(8, topic_id=8), passage_id=3, topic_id=3)

    read = FactGroup((spans,)).criteria(answer_chars=len("4 kg"))

    assert (read.passage_scope, read.document_scope, read.topic_scope) == (
        PassageScope.MULTI,
        DocumentScope.CROSS,
        TopicScope.MULTI,
    )


def _read(kind: str = "single", **scopes):
    from question_generation.models import criteria_of

    return criteria_of(
        **{"passages": 1, "documents": 1, "topics": 1, "answer_chars": 20} | scopes,
        kind=kind,
    )


def test_a_needs_both_question_is_banded_by_points_as_before() -> None:
    """Its need for both passages is not verified, so the spread bands it."""
    assert _read("needs_both", passages=2).difficulty == "easy"
    assert _read("needs_both", passages=2, topics=2).difficulty == "medium"


def test_a_kind_that_fixes_a_band_decides_the_band(monkeypatch) -> None:
    """Compound and false-premise kinds fix medium: their entry says so."""
    from dataclasses import replace

    from question_generation import kinds

    monkeypatch.setitem(
        kinds.KINDS,
        "compound",
        replace(kinds.KINDS["needs_both"], name="compound", band="medium"),
    )

    read = _read("compound", passages=2, documents=2, topics=2)

    assert read.difficulty == "medium"


def test_a_single_question_is_banded_by_points_as_before() -> None:
    """The default kind leaves the points rule alone, in every band."""
    assert _read(passages=1).difficulty == "easy"
    assert _read(passages=2).difficulty == "easy"
    assert _read(passages=2, topics=2).difficulty == "medium"
    assert _read(passages=2, documents=2, topics=2).difficulty == "hard"
