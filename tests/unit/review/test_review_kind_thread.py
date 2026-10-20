"""frontend-review-3 and -7: the review record carries the kind and the thread."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

pytest.importorskip("argilla")

from review import datasets
from review.records import ReviewRepository

CASES = [
    (
        "de",
        "Wie hoch ist die Kontoführungsgebühr, und bis wann muss ein Widerspruch eingehen?",
        "Und wie lange dauert das?",
    ),
    (
        "en",
        "What does the express parcel cost, and how long is the return window?",
        "And how long does that take?",
    ),
]


def stored(language, text, kind, follows_id=None, position=1):
    """A stored question as the repository reads it."""
    link = SimpleNamespace(fact=SimpleNamespace(statement="s", evidence_text="e"))
    return SimpleNamespace(
        id=7,
        question_text=text,
        target_answer="a",
        answerable=True,
        difficulty="easy",
        question_type="factoid",
        language=language,
        status="accepted",
        rejected_reason=None,
        answer_explanation=None,
        confidence=None,
        kind=kind,
        follows_id=follows_id,
        thread_position=position,
        fact_links=[link],
    )


@pytest.mark.parametrize("language,text,_f", CASES)
def test_compound_kind_reaches_the_record(language, text, _f) -> None:
    """The record carries the kind in its metadata."""
    rec = datasets.question_record(
        ReviewRepository._question(stored(language, text, "compound"))
    )
    blob = " ".join(map(str, rec.metadata.values())) + " ".join(
        map(str, rec.fields.values())
    )
    assert "compound" in blob, f"metadata keys {sorted(rec.metadata)}: no kind"


def test_the_guideline_says_a_compound_question_asks_two_things_on_purpose() -> None:
    """The guideline does not tell a reviewer to reject a compound question."""
    # Settings need a live client to build, so read the declaration itself.
    source = inspect.getsource(datasets.question_settings)
    assert "compound" in source and "one half at a time" in source


@pytest.mark.parametrize("language,_t,follow", CASES)
def test_follow_up_record_shows_the_turn_it_follows(language, _t, follow) -> None:
    """A follow-up record names its place in a thread."""
    rec = datasets.question_record(
        ReviewRepository._question(
            stored(language, follow, "single", follows_id=3, position=2)
        )
    )
    keys = {k.lower() for k in list(rec.fields) + list(rec.metadata)}
    assert keys & {"thread", "turn", "follows", "follows_id", "thread_position"}, (
        f"fields {sorted(rec.fields)} metadata {sorted(rec.metadata)}: nothing says it is a follow-up"
    )


@pytest.mark.parametrize("language,text,follow", CASES)
def test_the_record_carries_the_questions_before_it_in_order(
    language, text, follow
) -> None:
    """The thread field lists the earlier turns, oldest first."""
    row = ReviewRepository._question(
        stored(language, follow, "single", follows_id=3, position=3),
        before=["first turn", text],
    )
    rec = datasets.question_record(row)
    assert rec.fields["thread"].index("first turn") < rec.fields["thread"].index(text)
    assert rec.metadata["turn"] == 3


def test_a_root_question_carries_no_thread() -> None:
    """A root question has turn 1 and no thread field."""
    rec = datasets.question_record(
        ReviewRepository._question(stored("en", "Q?", "single"))
    )
    assert "thread" not in rec.fields and rec.metadata["turn"] == 1


def test_a_thread_that_closes_into_a_loop_lists_each_earlier_turn_once() -> None:
    """Two questions following each other end the walk instead of hanging it."""
    rows = {
        1: SimpleNamespace(
            id=1, question_text="Wie hoch ist die Gebühr?", follows_id=2
        ),
        2: SimpleNamespace(
            id=2, question_text="And how long does that take?", follows_id=1
        ),
    }
    session = SimpleNamespace(get=lambda _model, key: rows[key])

    assert ReviewRepository._before(session, rows[1]) == [
        "And how long does that take?"
    ]
