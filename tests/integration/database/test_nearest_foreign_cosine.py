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
from extraction.repository import FactCatalog
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
