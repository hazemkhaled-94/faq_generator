"""A question a re-chunk left with no fact goes with the last document: no wipe leaves one behind."""

from __future__ import annotations

import uuid

import pytest
from seed import digest, document, fact, link, passage, question
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

#: A passage's text before and after a re-chunk, in each configured language, and a shop one.
CASES = [
    ("de", "Die Kontoführung kostet 5 EUR.", "Die Kontoführung kostet 6 EUR."),
    ("en", "Account fees are 5 EUR.", "Account fees are 6 EUR."),
    ("en", "Returns are free within 30 days.", "Returns are free within 14 days."),
]


def orphaned(engine, sha: str, language: str, before: str, after: str) -> None:
    """Seeds a released question on one fact, then re-chunks its passage so the fact goes."""
    from preprocessing.chunking.models import Chunk, Chunking
    from preprocessing.chunking.repository import ChunkQueue

    with Session(engine) as session:
        session.add(document(sha, language=language, parse_status="parsed"))
        session.flush()
        cut = passage(sha, ordinal=1, language=language, text=before)
        session.add(cut)
        session.flush()
        claim = fact(cut.id, statement=before)
        session.add(claim)
        session.flush()
        asked = question(status="accepted", release_id=uuid.uuid4(), language=language)
        session.add(asked)
        session.flush()
        session.add(link(asked.id, claim.id))
        session.commit()
    chunk = Chunk(
        ordinal=1,
        text=after,
        page_from=1,
        page_to=1,
        section_path=None,
        block_type=None,
    )
    ChunkQueue().replace(sha, Chunking(passages=[chunk], oversized=0))
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM questions WHERE status='rejected'")
            ).scalar_one()
            == 1
        )


def questions(engine) -> int:
    """How many questions are held."""
    with engine.connect() as connection:
        return connection.execute(text("SELECT count(*) FROM questions")).scalar_one()


@pytest.mark.parametrize(("language", "before", "after"), CASES)
def test_a_wipe_after_a_rechunk_leaves_no_question(
    engine, database, language, before, after
) -> None:
    """The wipe takes the orphaned question."""
    from ingestion.repository import DocumentRepository

    sha = digest(f"wipe-{language}-{before}")
    orphaned(engine, sha, language, before, after)

    DocumentRepository().delete_all([sha])

    assert questions(engine) == 0


@pytest.mark.parametrize(("language", "before", "after"), CASES)
def test_deleting_the_only_document_after_a_rechunk_leaves_no_question(
    engine, database, language, before, after
) -> None:
    """So does deleting the last document."""
    from ingestion.repository import DocumentRepository

    sha = digest(f"one-{language}-{before}")
    orphaned(engine, sha, language, before, after)

    DocumentRepository().delete(sha)

    assert questions(engine) == 0


def test_deleting_what_was_derived_from_the_only_document_leaves_no_question(
    engine, database
) -> None:
    """And dropping what the last document derived."""
    from ingestion.repository import DocumentRepository

    sha = digest("derived-only")
    orphaned(engine, sha, "en", "Fees are 5 EUR.", "Fees are 6 EUR.")

    DocumentRepository().delete_derived(sha)

    assert questions(engine) == 0


def test_a_question_orphaned_beside_another_document_stays_when_one_is_deleted(
    engine, database
) -> None:
    """Nothing links a fact-less question to its document, so with others present it waits for the wipe."""
    from ingestion.repository import DocumentRepository

    sha, other = digest("beside-a"), digest("beside-b")
    orphaned(engine, sha, "en", "Fees are 5 EUR.", "Fees are 6 EUR.")
    with Session(engine) as session:
        session.add(document(other, parse_status="parsed"))
        session.commit()

    DocumentRepository().delete(other)
    assert questions(engine) == 1
    DocumentRepository().delete(sha)
    assert questions(engine) == 0
