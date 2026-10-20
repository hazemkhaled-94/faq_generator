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
    """A stored question row as the repository reads it."""
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
    """The kind a question was written as is in the Argilla record."""
    rec = datasets.question_record(
        ReviewRepository._question(stored(language, text, "compound"))
    )
    blob = " ".join(map(str, rec.metadata.values())) + " ".join(
        map(str, rec.fields.values())
    )
    assert "compound" in blob, f"metadata keys {sorted(rec.metadata)}: no kind"


def test_the_guideline_says_a_compound_question_asks_two_things_on_purpose() -> None:
    """The reviewer guideline names the compound kind and judges it by halves."""
    # Settings need a live client to build, so read the declaration itself.
    source = inspect.getsource(datasets.question_settings)
    assert "compound" in source and "one half at a time" in source
