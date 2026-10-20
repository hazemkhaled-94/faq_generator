"""Red tests: a thread leaves the release whole (a root leaving accepted, by any path)."""

from __future__ import annotations

import uuid

import pytest
from seed import digest, document, fact, link, passage, question
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

CASES = [
    (
        "de",
        "Die Karte kostet 30 EUR im Jahr.",
        "Die Gebühr wird jährlich abgebucht.",
        "Und wie lange dauert das?",
    ),
    (
        "en",
        "Goods may be returned within 30 days.",
        "Refunds are paid within 14 days.",
        "And where does the money go?",
    ),
]


def _thread(engine, lang, s1, s2, follow_text):
    drawn, sha = uuid.uuid4(), digest(f"thread-{lang}")
    with Session(engine) as session:
        session.add(document(sha))
        session.flush()
        pa = passage(sha, ordinal=1, language=lang, text=s1)
        pb = passage(sha, ordinal=2, language=lang, text=s2)
        session.add_all([pa, pb])
        session.flush()
        f1, f2, f3 = (
            fact(pa.id, statement=s1),
            fact(pb.id, statement=s2),
            fact(pb.id, statement=s2 + " Ja."),
        )
        session.add_all([f1, f2, f3])
        session.flush()
        root = question(
            status="accepted", release_id=drawn, kind="needs_both", language=lang
        )
        session.add(root)
        session.flush()
        follow = question(
            status="accepted",
            release_id=drawn,
            follows_id=root.id,
            thread_position=2,
            question_text=follow_text,
            language=lang,
        )
        session.add(follow)
        session.flush()
        session.add_all(
            [link(root.id, f1.id), link(root.id, f2.id), link(follow.id, f3.id)]
        )
        session.commit()
        return root.id, follow.id, pa.id


def _released(engine):
    with engine.connect() as c:
        return [
            r[0]
            for r in c.execute(
                text(
                    "SELECT id FROM questions WHERE release_id IS NOT NULL ORDER BY id"
                )
            )
        ]


@pytest.mark.parametrize("lang,s1,s2,ft", CASES)
def test_trigger_rejecting_a_root_takes_its_follow_up_out_of_the_release(
    engine, database, lang, s1, s2, ft
):
    """The trigger that rejects a root losing a fact."""
    root, follow, pa = _thread(engine, lang, s1, s2, ft)
    with engine.begin() as c:
        c.execute(text("DELETE FROM passages WHERE id = :i"), {"i": pa})
    assert _released(engine) == [], f"follow-up {follow} released without root {root}"


@pytest.mark.parametrize("lang,s1,s2,ft", CASES)
def test_decide_rejecting_a_root_takes_its_follow_up_out_of_the_release(
    engine, database, lang, s1, s2, ft
):
    """A person rejecting a released root."""
    from question_generation.catalog import QuestionCatalog

    root, follow, _ = _thread(engine, lang, s1, s2, ft)
    QuestionCatalog().decide(root, "rejected")
    assert _released(engine) == [], f"follow-up {follow} released without root {root}"


@pytest.mark.parametrize("lang,s1,s2,ft", CASES)
def test_reject_of_a_root_by_a_recheck_takes_its_follow_up_out_of_the_release(
    engine, database, lang, s1, s2, ft
):
    """A re-check rejecting a released root."""
    from question_generation.catalog import QuestionCatalog

    root, follow, _ = _thread(engine, lang, s1, s2, ft)
    QuestionCatalog().reject([(root, "source_changed")])
    assert _released(engine) == [], f"follow-up {follow} released without root {root}"


@pytest.mark.parametrize("lang,s1,s2,ft", CASES)
def test_back_to_draft_and_a_second_follow_up_leave_the_release_too(
    engine, database, lang, s1, s2, ft
):
    """Back to draft clears every descendant, not only the first."""
    from question_generation.catalog import QuestionCatalog

    root, follow, _ = _thread(engine, lang, s1, s2, ft)
    with engine.begin() as c:
        second = c.execute(
            text(
                "INSERT INTO questions (question_text, target_answer, status, release_id, "
                "follows_id, thread_position, language, kind, question_type, answerable) "
                "SELECT question_text, target_answer, status, release_id, :f, 3, language, "
                "kind, question_type, answerable FROM questions WHERE id = :f RETURNING id"
            ),
            {"f": follow},
        ).scalar_one()
    QuestionCatalog().decide(root, "draft")
    assert _released(engine) == [], f"descendant {second} of {root} still released"
