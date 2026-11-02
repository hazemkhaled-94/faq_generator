"""A passage's nearest twin in another document, stored rather than probed for.

The furniture filter compared every candidate passage with the passages of
every other document, once per candidate and again for every topic. The score
is the same each time, so extraction writes it when a passage is embedded and
the filter reads the column.
"""

from __future__ import annotations

import math

import pytest
from seed import digest, document, passage
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from database.qa_generator import Document, Passage
from extraction.repository import FactCatalog, PassageQueue
from ingestion.repository import DocumentRepository
from preprocessing.chunking.repository import PassageCatalog
from question_generation.queue import repeated_across_documents

pytestmark = pytest.mark.integration


def _turned(angle: float) -> list[float]:
    """A unit vector at `angle` radians from the first axis, in the first two."""
    return [math.cos(angle), math.sin(angle)] + [0.0] * 1022


def _write(engine, *rows: tuple[str, str, float]) -> list[int]:
    """Passages of (document letter, language, angle), embedded as extraction does."""
    with Session(engine) as session:
        for sha in {digest(letter) for letter, _, _ in rows}:
            if session.get(Document, sha) is None:
                session.add(document(sha))
        session.flush()
        written = []
        for at, (letter, language, angle) in enumerate(rows, 1):
            held = passage(
                digest(letter), ordinal=at, text=f"Notice {at}.", language=language
            )
            session.add(held)
            session.flush()
            written.append((held.id, _turned(angle)))
        session.commit()
    FactCatalog().embed_passages(written)
    return [row for row, _ in written]


def _scores(engine) -> dict[int, float | None]:
    """The column, by passage id."""
    with engine.connect() as connection:
        return dict(
            connection.execute(
                text("SELECT id, nearest_foreign_cosine FROM passages")
            ).all()
        )


def test_the_column_is_the_exact_cosine_to_the_nearest_foreign_passage(
    engine, database
) -> None:
    """Two documents sharing a notice: each holds the cosine to the other's."""
    ids = _write(engine, ("a", "en", 0.0), ("b", "en", 0.1))

    scores = _scores(engine)

    for one in ids:
        assert scores[one] == pytest.approx(math.cos(0.1), abs=1e-6)


def test_a_third_document_raises_the_scores_it_is_closer_to(engine, database) -> None:
    """Adding a document refreshes the older passages it exceeds."""
    first, second = _write(engine, ("a", "en", 0.0), ("b", "en", 0.5))
    assert _scores(engine)[first] == pytest.approx(math.cos(0.5), abs=1e-6)

    (third,) = _write(engine, ("c", "en", 0.02))
    scores = _scores(engine)

    assert scores[first] == pytest.approx(math.cos(0.02), abs=1e-6)
    assert scores[second] == pytest.approx(math.cos(0.48), abs=1e-6)
    assert scores[third] == pytest.approx(math.cos(0.02), abs=1e-6)


def test_another_language_or_one_document_leaves_the_column_empty(
    engine, database
) -> None:
    """Abstains, for any language code: a translation is not a twin."""
    ids = _write(
        engine,
        ("a", "de", 0.0),
        ("b", "fr", 0.0),
        ("c", "el", 0.0),
        ("c", "el", 0.0),
    )

    scores = _scores(engine)

    assert all(scores[one] is None for one in ids)


def test_the_filter_excludes_the_shared_passage_and_reads_no_other_table(
    engine, database
) -> None:
    """The predicate is a comparison on the passage row."""
    a, b = _write(engine, ("a", "en", 0.0), ("b", "en", 0.01))
    (far,) = _write(engine, ("c", "en", 1.2))

    predicate = repeated_across_documents(0.95)

    with Session(engine) as session:
        furniture = set(session.scalars(select(Passage.id).where(predicate)))

    assert furniture == {a, b}
    assert far not in furniture
    assert "FROM passages" not in str(predicate)


def _furniture(engine) -> set[int]:
    """The passages the furniture filter reads as the corpus's own."""
    with Session(engine) as session:
        return set(
            session.scalars(select(Passage.id).where(repeated_across_documents(0.95)))
        )


def _held(engine, language: str, *letters: str) -> list[int]:
    """One notice passage in each of these documents, not yet embedded."""
    ids = []
    with Session(engine) as session:
        for letter in letters:
            session.add(document(digest(letter + language)))
        session.flush()
        for at, letter in enumerate(letters, 1):
            held = passage(
                digest(letter + language), ordinal=at, text="Notice.", language=language
            )
            session.add(held)
            session.flush()
            ids.append(held.id)
        session.commit()
    return ids


@pytest.mark.parametrize("language", ["de", "en", "fr", "el"])
def test_a_notice_stored_by_the_extract_worker_is_furniture(
    engine, database, language
) -> None:
    """The worker writes the vector through `PassageQueue.store`, which scores it."""
    ids = _held(engine, language, "a", "b")
    queue = PassageQueue()
    for one, angle in zip(ids, (0.0, 0.01), strict=True):
        queue.store(one, [], embedding=_turned(angle))

    assert _furniture(engine) == set(ids)


@pytest.mark.parametrize("language", ["de", "en", "fr", "el"])
def test_a_passage_whose_twin_document_was_deleted_is_offered_again(
    engine, database, language
) -> None:
    """The score falls with the document it came from."""
    kept, _ = _write(engine, ("a", language, 0.0), ("b", language, 0.01))

    DocumentRepository().delete(digest("b"))

    assert kept not in _furniture(engine)
    assert _scores(engine)[kept] is None


def test_a_deleted_twin_leaves_the_next_closest_document(engine, database) -> None:
    """Three documents share a notice: deleting one still leaves it furniture."""
    first, *_ = _write(engine, ("a", "en", 0.0), ("b", "en", 0.01), ("c", "en", 0.02))

    DocumentRepository().delete(digest("b"))

    assert _scores(engine)[first] == pytest.approx(math.cos(0.02), abs=1e-6)
    assert first in _furniture(engine)


def test_dropping_a_documents_passages_rescores_the_ones_that_took_from_it(
    engine, database
) -> None:
    """`delete_derived`, which a re-chunk of the document also is, from its side."""
    kept, _ = _write(engine, ("a", "de", 0.0), ("b", "de", 0.01))

    DocumentRepository().delete_derived(digest("b"))

    assert kept not in _furniture(engine)


def test_a_passage_that_changes_language_is_scored_among_its_new_one(
    engine, database
) -> None:
    """`revocabulary` moves a passage out of one language's twins and into another's."""
    a, b, c = _write(engine, ("a", "de", 0.0), ("b", "de", 0.01), ("c", "en", 0.0))
    assert _furniture(engine) == {a, b}

    PassageCatalog().revocabulary([(b, "en", ["notice"])])

    assert _furniture(engine) == {b, c}
    assert _scores(engine)[a] is None
