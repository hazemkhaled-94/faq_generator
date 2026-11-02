"""What a rerun of a topic is told about the questions it already holds, against the database.

A topic's own questions are the ones it wrote. A multi-topic question another
topic wrote from this topic's bridge passage is that topic's, so it neither
makes this topic's first run a rerun nor marks the bridge fact as refused.
"""

from __future__ import annotations

import pytest
from seed import digest, document, fact, fitted, membership, passage, question
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.qa_generator import QuestionFact
from question_generation.queue import QuestionQueue

pytestmark = pytest.mark.integration


def _topics(engine):
    """Topic A over one passage, topic B over another and over A's as a bridge."""
    with Session(engine) as session:
        sha = digest("a")
        session.add(document(sha))
        a, b = fitted(0), fitted(1)
        session.add_all([a, b])
        session.flush()
        pa = passage(sha, ordinal=1, text="The device weighs 4 kg.", language="en")
        pb = passage(sha, ordinal=2, text="The case weighs 1 kg.", language="en")
        session.add_all([pa, pb])
        session.flush()
        session.add_all(
            [
                membership(pa.id, a.id, 0.9),
                membership(pa.id, b.id, 0.3),
                membership(pb.id, b.id, 0.9),
            ]
        )
        fa = fact(pa.id, statement="The device weighs 4 kg.")
        fb = fact(pb.id, statement="The case weighs 1 kg.")
        session.add_all([fa, fb])
        session.flush()
        session.commit()
        return a.id, b.id, fa.id, fb.id


def _asked(engine, fact_ids, status, reason, ran=("structural",)):
    """One question resting on these facts, as a draft a run stored."""
    with Session(engine) as session:
        drawn = question(
            status=status,
            rejected_reason=reason,
            gates_ran=list(ran),
            topic_scope="multi_topic" if len(fact_ids) > 1 else "single_topic",
        )
        session.add(drawn)
        session.flush()
        session.add_all(
            QuestionFact(question_id=drawn.id, fact_id=one) for one in fact_ids
        )
        session.commit()


def _claim(engine, topic_id):
    """Claims one topic, the others taken out of the queue first."""
    with engine.begin() as connection:
        connection.execute(text("UPDATE topics SET question_status = 'generated'"))
        connection.execute(
            text("UPDATE topics SET question_status = 'pending' WHERE id = :id"),
            {"id": topic_id},
        )
    claimed = QuestionQueue().claim()
    assert claimed is not None and claimed.id == topic_id
    return claimed


@pytest.mark.parametrize(
    ("status", "reason"), [("accepted", None), ("rejected", "malformed")]
)
def test_another_topics_bridge_question_makes_no_rerun_of_a_first_run(
    engine, database, status, reason
) -> None:
    """Topic B wrote a question from its own fact and A's bridge fact: A has still never run."""
    a, _, fa, fb = _topics(engine)
    _asked(engine, [fb, fa], status, reason)

    claimed = _claim(engine, a)

    assert claimed.asked == 0
    # An accepted bridge question keeps the fact out of the deal, as it always did.
    assert {one.id: one.refused for one in QuestionQueue().facts(a)} == (
        {} if status == "accepted" else {fa: False}
    )


def test_a_topics_own_refused_draft_counts_and_flags_its_fact(engine, database) -> None:
    """The rerun is told it holds a question, and deals the refused fact last."""
    a, _, fa, _ = _topics(engine)
    _asked(engine, [fa], "rejected", "malformed")

    claimed = _claim(engine, a)

    assert claimed.asked == 1
    assert {one.id: one.refused for one in QuestionQueue().facts(a)} == {fa: True}


@pytest.mark.parametrize(
    ("ran", "flagged"),
    [(("structural",), True), (("structural", "phrasing"), False)],
    ids=["the title quote, no model", "the phrasing judge's"],
)
def test_leaks_source_flags_a_fact_only_where_no_model_gave_it(
    engine, database, ran, flagged
) -> None:
    """The half of the gate that runs in `structural` recurs on a fact; the judge's does not."""
    a, _, fa, _ = _topics(engine)
    _asked(engine, [fa], "rejected", "leaks_source", ran)

    _claim(engine, a)

    assert {one.id: one.refused for one in QuestionQueue().facts(a)} == {fa: flagged}
