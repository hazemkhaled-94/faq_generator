"""The thread a reviewer is shown: the turns a follow-up follows, whatever the stored graph is."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("argilla")

from hypothesis import given
from hypothesis import strategies as st

from database.qa_generator import Question
from review.records import ReviewRepository


def _rows(parents: dict[int, int | None]):
    return {
        at: SimpleNamespace(id=at, question_text=f"turn {at}", follows_id=parent)
        for at, parent in parents.items()
    }


def _walk(rows, start):
    asked: list[object] = []

    def get(model, key):
        asked.append(model)
        return rows.get(key)

    return ReviewRepository._before(SimpleNamespace(get=get), rows[start]), asked


@given(
    st.integers(1, 8).flatmap(
        lambda n: st.tuples(
            st.just(n),
            st.lists(st.one_of(st.none(), st.integers(1, n)), min_size=n, max_size=n),
        )
    )
)
def test_the_walk_ends_on_any_follows_graph_and_never_repeats_a_turn(case) -> None:
    """A tree, a chain, a self-reference or a loop: each ancestor once, oldest first."""
    n, parents = case
    rows = _rows(dict(zip(range(1, n + 1), parents, strict=True)))

    for start in rows:
        got, _ = _walk(rows, start)
        assert len(got) == len(set(got))
        assert f"turn {start}" not in got
        chain, at, seen = [], rows[start].follows_id, {start}
        while at is not None and at not in seen:
            seen.add(at)
            chain.insert(0, f"turn {at}")
            at = rows[at].follows_id
        assert got == chain


def test_a_chain_lists_every_turn_oldest_first_and_asks_the_question_table() -> None:
    """Three turns above the fourth, in the order they were asked."""
    rows = _rows({1: None, 2: 1, 3: 2, 4: 3})

    got, asked = _walk(rows, 4)

    assert got == ["turn 1", "turn 2", "turn 3"]
    assert set(asked) == {Question}


def test_a_root_has_no_turn_before_it() -> None:
    """Nothing to walk."""
    assert _walk(_rows({1: None}), 1)[0] == []


def test_a_parent_that_is_gone_ends_the_walk_with_what_was_found() -> None:
    """The turns found so far are kept."""
    rows = _rows({2: 1, 3: 2})

    assert _walk(rows, 3)[0] == ["turn 2"]


def test_a_stored_question_is_read_field_by_field() -> None:
    """Every column reaches the row under its own name."""
    link = SimpleNamespace(fact=SimpleNamespace(statement="s1", evidence_text="e1"))
    one = SimpleNamespace(
        id=11,
        question_text="Was kostet die Karte?",
        target_answer="30 EUR",
        answerable=False,
        difficulty="hard",
        question_type="reason",
        language="de",
        status="rejected",
        rejected_reason="not_recoverable",
        answer_explanation="weil",
        confidence=0.25,
        kind="needs_both",
        follows_id=4,
        thread_position=3,
        fact_links=[link],
    )

    row = ReviewRepository._question(one, ["a", "b"])

    assert (row.id, row.question_text, row.target_answer) == (
        11,
        "Was kostet die Karte?",
        "30 EUR",
    )
    assert (row.answerable, row.difficulty, row.question_type) == (
        False,
        "hard",
        "reason",
    )
    assert (row.language, row.status, row.rejected_reason) == (
        "de",
        "rejected",
        "not_recoverable",
    )
    assert (row.answer_explanation, row.confidence, row.kind) == (
        "weil",
        0.25,
        "needs_both",
    )
    assert (row.turn, row.before, row.evidence) == (3, ["a", "b"], ["e1"])


def _row(**kwargs):
    from review.records import QuestionRow

    base: dict = dict(  # noqa: C408
        id=5,
        question_text="Und bei Filialen?",
        target_answer="ja",
        answerable=True,
        difficulty="medium",
        question_type="factoid",
        language="de",
        status="accepted",
        rejected_reason=None,
        facts=["f1", "f2"],
        evidence=["e1", "e2"],
        answer_explanation="weil",
        confidence=0.5,
        kind="needs_both",
        turn=3,
        before=["Was kostet es?", "Und online?"],
    )
    base.update(kwargs)
    return QuestionRow(**base)


def test_a_follow_up_record_carries_each_field_and_the_thread_numbered_from_one() -> (
    None
):
    """Every field and metadata term, under its own name."""
    from review import datasets

    rec = datasets.question_record(_row())

    assert rec.fields["question"] == "Und bei Filialen?"
    assert rec.fields["answer"] == "ja"
    assert rec.fields["facts"] == "- f1\n- f2"
    assert rec.fields["evidence"] == "- e1\n- e2"
    assert rec.fields["explanation"] == "weil"
    assert rec.fields["judge"] == datasets.UNJUDGED.detail
    assert rec.fields["thread"] == "1. Was kostet es?\n2. Und online?"
    expected = {
        "difficulty": "medium",
        "question_type": "factoid",
        "kind": "needs_both",
        "turn": 3,
        "language": "de",
        "answerable": "true",
        "gate": "accepted",
        "question_id": 5,
        "confidence": 0.5,
    }
    assert {k: v for k, v in rec.metadata.items() if k in expected} == expected


def test_a_bare_root_record_says_what_is_missing() -> None:
    """Defaults for the empty columns, no thread, no confidence."""
    from review import datasets

    rec = datasets.question_record(
        _row(
            target_answer=None,
            answerable=False,
            difficulty=None,
            question_type=None,
            kind=None,
            facts=[],
            evidence=[],
            answer_explanation=None,
            confidence=None,
            turn=1,
            before=[],
            rejected_reason="not_recoverable",
            status="rejected",
        )
    )

    assert rec.fields["answer"] == "(deliberately unanswerable)"
    assert rec.fields["facts"] == "(none recorded)"
    assert rec.fields["evidence"] == "(none recorded)"
    assert rec.fields["explanation"] == "(none written)"
    assert "thread" not in rec.fields
    assert rec.metadata["difficulty"] == "unbanded"
    assert rec.metadata["question_type"] == "untyped"
    assert rec.metadata["kind"] == "single"
    assert rec.metadata["gate"] == "not_recoverable"
    assert rec.metadata["answerable"] == "false"
    assert "confidence" not in rec.metadata
