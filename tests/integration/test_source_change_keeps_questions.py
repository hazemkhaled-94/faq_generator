"""A source that changes rejects the questions resting on it; it never deletes them.

Re-chunking with a changed chunker, or re-extracting, replaces the passages
and facts under questions that were accepted, reviewed and released. Those
questions are evidence (the drop-rate record, a person's verdict, a shipped
release), so a replaced source rejects them as `source_changed`, clears their
release and leaves every row and id where it was. Only a person's explicit
deletion of a document, or of what was derived from it, deletes questions.
"""

from __future__ import annotations

import uuid

import pytest
from seed import digest, document, fact, link, passage, question
from sqlalchemy import text
from sqlalchemy.orm import Session

from ingestion.repository import DocumentRepository
from preprocessing.chunking.models import Chunk, Chunking
from preprocessing.chunking.repository import ChunkQueue

pytestmark = pytest.mark.integration

#: Two passages and a follow-up, in two languages and two domains.
CASES = [
    (
        "de",
        "Die Karte kostet 30 EUR im Jahr.",
        "Die Gebühr wird jährlich abgebucht.",
        "Und wann wird sie abgebucht?",
    ),
    (
        "en",
        "Goods may be returned within 30 days.",
        "Refunds are paid within 14 days.",
        "And where does the money go?",
    ),
]


def _chunk(ordinal: int, body: str) -> Chunk:
    """A passage as the chunker cut it, with no sentences and no grid."""
    return Chunk(
        ordinal=ordinal,
        text=body,
        page_from=1,
        page_to=1,
        section_path=None,
        block_type=None,
    )


def _thread(engine, seed, lang, s1, s2, follow_text):
    """A released, reviewed root with a released follow-up, on two passages."""
    drawn, sha = uuid.uuid4(), digest(seed)
    with Session(engine) as session:
        session.add(document(sha, language=lang, parse_status="parsed"))
        session.flush()
        pa = passage(sha, ordinal=1, language=lang, text=s1)
        pb = passage(sha, ordinal=2, language=lang, text=s2)
        session.add_all([pa, pb])
        session.flush()
        fa, fb = fact(pa.id, statement=s1), fact(pb.id, statement=s2)
        session.add_all([fa, fb])
        session.flush()
        root = question(
            status="accepted",
            release_id=drawn,
            kind="needs_both",
            language=lang,
            reviewed_verdict="accepted",
            reviewed_at=text("now()"),
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
        session.add_all([link(root.id, fa.id), link(root.id, fb.id)])
        session.add(link(follow.id, fb.id))
        session.commit()
        return sha, root.id, follow.id, (pa.id, pb.id), (fa.id, fb.id)


def _rows(engine, table, columns="id"):
    with engine.connect() as connection:
        return connection.execute(
            text(f"SELECT {columns} FROM {table} ORDER BY id")
        ).all()


@pytest.mark.parametrize("lang,s1,s2,ft", CASES)
def test_a_changed_chunker_rejects_released_questions_and_deletes_none(
    engine, database, lang, s1, s2, ft
) -> None:
    """The root's passage comes back different: the thread stays, the root rejected."""
    sha, root, follow, _, _ = _thread(engine, "changed-" + lang, lang, s1, s2, ft)

    ChunkQueue().replace(
        sha,
        Chunking(
            passages=[_chunk(1, s1 + " (revised)"), _chunk(2, s2)],
            oversized=0,
        ),
    )

    held = {
        row.id: row
        for row in _rows(
            engine,
            "questions",
            "id, status, rejected_reason, release_id, reviewed_verdict",
        )
    }
    assert set(held) == {root, follow}, "a question was deleted"
    assert held[root].status == "rejected"
    assert held[root].rejected_reason == "source_changed"
    assert held[root].release_id is None
    assert held[root].reviewed_verdict == "accepted", "the verdict is kept"
    assert held[follow].release_id is None, "a follow-up stays released"
    assert held[follow].status == "accepted", "the follow-up keeps its own status"


@pytest.mark.parametrize("lang,s1,s2,ft", CASES)
def test_a_changed_passage_rejects_a_root_resting_on_it_alone_and_keeps_it(
    engine, database, lang, s1, s2, ft
) -> None:
    """The blocker's case: every fact of a released question goes with its one passage.

    Before the change the trigger deleted the root, and its follow-up with it.
    """
    sha, root, follow, _, (_, fact_b) = _thread(
        engine, "alone-" + lang, lang, s1, s2, ft
    )
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM question_facts WHERE question_id = :q AND fact_id = :f"),
            {"q": root, "f": fact_b},
        )

    ChunkQueue().replace(
        sha,
        Chunking(
            passages=[_chunk(1, s1 + " (revised)"), _chunk(2, s2)],
            oversized=0,
        ),
    )

    held = {
        row.id: row
        for row in _rows(engine, "questions", "id, status, rejected_reason, release_id")
    }
    assert set(held) == {root, follow}, "the root, or its follow-up, was deleted"
    assert held[root].status == "rejected"
    assert held[root].rejected_reason == "source_changed"
    assert held[root].release_id is None
    assert held[follow].release_id is None, "the follow-up stays out of the release"


@pytest.mark.parametrize("lang,s1,s2,ft", CASES)
def test_a_rechunk_that_changes_nothing_changes_no_id(
    engine, database, lang, s1, s2, ft
) -> None:
    """The same chunking again: passages, facts, questions and links stay."""
    sha, *_ = _thread(engine, "same-" + lang, lang, s1, s2, ft)
    before_ids = {
        table: [row[0] for row in _rows(engine, table)]
        for table in ("passages", "facts", "questions")
    }
    with engine.connect() as connection:
        links = connection.execute(
            text("SELECT question_id, fact_id FROM question_facts ORDER BY 1, 2")
        ).all()

    ChunkQueue().replace(
        sha, Chunking(passages=[_chunk(1, s1), _chunk(2, s2)], oversized=0)
    )

    for table, ids in before_ids.items():
        assert [row[0] for row in _rows(engine, table)] == ids, table
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT question_id, fact_id FROM question_facts ORDER BY 1, 2")
            ).all()
            == links
        )
    assert [r.status for r in _rows(engine, "questions", "status")] == [
        "accepted",
        "accepted",
    ]
    assert all(
        r.release_id is not None for r in _rows(engine, "questions", "release_id")
    )


@pytest.mark.parametrize("lang,s1,s2,ft", CASES)
def test_deleting_the_last_fact_of_a_question_rejects_it(
    engine, database, lang, s1, s2, ft
) -> None:
    """The trigger no longer deletes a question left with no fact."""
    _, root, follow, _, _ = _thread(engine, "last-" + lang, lang, s1, s2, ft)

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM facts"))

    assert [r.id for r in _rows(engine, "questions")] == [root, follow]
    assert {r.status for r in _rows(engine, "questions", "status")} == {"rejected"}
    assert {r.release_id for r in _rows(engine, "questions", "release_id")} == {None}


@pytest.mark.parametrize("lang,s1,s2,ft", CASES)
@pytest.mark.parametrize("how", ["delete", "delete_all", "delete_derived"])
def test_an_explicit_deletion_deletes_the_questions_resting_only_on_it(
    engine, database, lang, s1, s2, ft, how
) -> None:
    """What a person asked to delete goes with its questions, as it always did."""
    sha, *_ = _thread(engine, "explicit-" + lang + how, lang, s1, s2, ft)

    repository = DocumentRepository()
    if how == "delete_all":
        repository.delete_all([sha])
    else:
        getattr(repository, how)(sha)

    assert _rows(engine, "questions") == []
    assert _rows(engine, "facts") == []


def test_a_question_resting_on_two_documents_is_deleted_with_either(
    engine, database
) -> None:
    """It cannot stand on half its sources: deleted, though the other document still holds a fact."""
    one, two = digest("one"), digest("two")
    with Session(engine) as session:
        session.add_all([document(one), document(two)])
        session.flush()
        pa, pb = passage(one, text="Eine Aussage."), passage(two, text="A claim.")
        session.add_all([pa, pb])
        session.flush()
        fa, fb = (
            fact(pa.id, statement="Eine Aussage."),
            fact(pb.id, statement="A claim."),
        )
        session.add_all([fa, fb])
        session.flush()
        asked = question(status="accepted", release_id=uuid.uuid4())
        session.add(asked)
        session.flush()
        session.add_all([link(asked.id, fa.id), link(asked.id, fb.id)])
        session.commit()

    DocumentRepository().delete(one)

    assert _rows(engine, "questions") == []
