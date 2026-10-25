"""A question a re-chunk left with no fact goes with the document it was written from, whatever else is held."""

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
    ("xx", "Lorem ipsum dolor 30.", "Lorem ipsum dolor 31."),
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
            >= 1
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


def hold_another(engine, name: str = "other") -> str:
    """A second document with a question of its own that keeps its fact."""
    sha = digest(name)
    with Session(engine) as session:
        session.add(document(sha, parse_status="parsed"))
        session.flush()
        cut = passage(sha, ordinal=1, text="Delivery takes 3 days.")
        session.add(cut)
        session.flush()
        claim = fact(cut.id, statement="Delivery takes 3 days.")
        session.add(claim)
        session.flush()
        asked = question(status="accepted")
        session.add(asked)
        session.flush()
        session.add(link(asked.id, claim.id))
        session.commit()
    return sha


@pytest.mark.parametrize(("language", "before", "after"), CASES)
def test_deleting_one_document_deletes_its_orphaned_question_beside_another(
    engine, database, language, before, after
) -> None:
    """The other document and its question stay."""
    from ingestion.repository import DocumentRepository

    sha = digest(f"beside-{language}-{before}")
    orphaned(engine, sha, language, before, after)
    hold_another(engine)

    DocumentRepository().delete(sha)

    assert questions(engine) == 1


@pytest.mark.parametrize(("language", "before", "after"), CASES)
def test_deleting_what_was_derived_deletes_its_orphaned_question_beside_another(
    engine, database, language, before, after
) -> None:
    """Dropping a document's passages takes the question it was left with none from."""
    from ingestion.repository import DocumentRepository

    sha = digest(f"derived-{language}-{before}")
    orphaned(engine, sha, language, before, after)
    hold_another(engine)

    DocumentRepository().delete_derived(sha)

    assert questions(engine) == 1


def test_deleting_some_documents_deletes_the_orphans_of_those_only(
    engine, database
) -> None:
    """delete_all over a subset."""
    from ingestion.repository import DocumentRepository

    a, b = digest("subset-a"), digest("subset-b")
    orphaned(engine, a, "en", "Fees are 5 EUR.", "Fees are 6 EUR.")
    orphaned(engine, b, "de", "Die Gebühr beträgt 5 EUR.", "Die Gebühr beträgt 6 EUR.")

    DocumentRepository().delete_all([a])

    assert questions(engine) == 1


def test_a_question_on_two_documents_goes_with_either(engine, database) -> None:
    """It cannot stand on half its sources: one document's fact is replaced, then that document goes."""
    from ingestion.repository import DocumentRepository

    a, b = digest("two-a"), digest("two-b")
    with Session(engine) as session:
        ids = {}
        for sha, body in ((a, "Fees are 5 EUR."), (b, "Returns take 14 days.")):
            session.add(document(sha, parse_status="parsed"))
            session.flush()
            cut = passage(sha, ordinal=1, text=body)
            session.add(cut)
            session.flush()
            claim = fact(cut.id, statement=body)
            session.add(claim)
            session.flush()
            ids[sha] = (cut.id, claim.id)
        asked = question(status="accepted", release_id=uuid.uuid4())
        session.add(asked)
        session.flush()
        for _, claim_id in ids.values():
            session.add(link(asked.id, claim_id))
        session.commit()
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM passages WHERE id = :p"), {"p": ids[a][0]})
    assert questions(engine) == 1

    DocumentRepository().delete(a)

    assert questions(engine) == 0


def test_a_question_that_keeps_its_facts_is_not_stamped(engine, database) -> None:
    """The stamp is for questions that lost a source: NULL for the rest."""
    sha = hold_another(engine, "unstamped")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM questions WHERE source_digests IS NOT NULL")
            ).scalar_one()
            == 0
        )
    assert sha


@pytest.mark.parametrize(
    ("language", "body_a", "body_b"),
    [
        ("de", "Die Karte kostet 30 EUR.", "Die Rückgabe dauert 14 Tage."),
        ("en", "The card costs 30 EUR.", "Returns take 14 days."),
    ],
)
@pytest.mark.parametrize("gone", ["a", "b"])
@pytest.mark.parametrize("how", ["delete", "delete_all", "delete_derived"])
def test_a_live_question_on_two_documents_goes_with_either(
    engine, database, language, body_a, body_b, gone, how
) -> None:
    """Never stamped, both facts alive: it holds text derived from the deleted document."""
    from ingestion.repository import DocumentRepository

    shas = {"a": digest(f"live-a-{language}"), "b": digest(f"live-b-{language}")}
    bodies = {"a": body_a, "b": body_b}
    with Session(engine) as session:
        claims = []
        for key in ("a", "b"):
            session.add(document(shas[key], language=language, parse_status="parsed"))
            session.flush()
            cut = passage(shas[key], ordinal=1, language=language, text=bodies[key])
            session.add(cut)
            session.flush()
            claim = fact(cut.id, statement=bodies[key])
            session.add(claim)
            session.flush()
            claims.append(claim)
        asked = question(status="accepted", release_id=uuid.uuid4(), language=language)
        session.add(asked)
        session.flush()
        for claim in claims:
            session.add(link(asked.id, claim.id))
        session.commit()
    other = hold_another(engine, f"alone-{language}-{gone}-{how}")

    repo = DocumentRepository()
    if how == "delete":
        repo.delete(shas[gone])
    elif how == "delete_all":
        repo.delete_all([shas[gone]])
    else:
        repo.delete_derived(shas[gone])

    # Only the question on the other document alone stays.
    assert questions(engine) == 1
    assert other
