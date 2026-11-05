"""A re-read of passages deleted since they were read writes nothing for them.

The re-read takes the passages' text, works on it outside any transaction,
and writes the language and lemmas back. A document deleted meanwhile took
its passages with it: those ids are skipped, the living ones are written, and
nothing raises.
"""

from __future__ import annotations

import pytest
from seed import digest, document, passage
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.qa_generator import Status
from preprocessing.chunking.repository import PassageCatalog

pytestmark = pytest.mark.integration


def held(engine) -> list[int]:
    """Two passages of a German price list, by id."""
    with Session(engine) as session:
        sha = digest("preisverzeichnis")
        session.add(document(sha, language="de", chunk_status=Status.CHUNKED))
        session.flush()
        made = [
            passage(
                sha, ordinal=1, text="Die Kontoführung kostet 4 Euro.", language="de"
            ),
            passage(sha, ordinal=2, text="Die Karte ist kostenlos.", language="de"),
        ]
        session.add_all(made)
        session.commit()
        return [one.id for one in made]


def test_only_deleted_passages_write_nothing(engine, database) -> None:
    """Every id gone: no row written, no error."""
    ids = held(engine)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM documents"))

    assert PassageCatalog().revocabulary([(ids[0], "de", ["kontoführung"])]) == 0


def test_a_batch_holding_a_deleted_passage_writes_the_living_one(
    engine, database
) -> None:
    """The deleted id is skipped; its neighbour gets its lemmas."""
    ids = held(engine)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM passages WHERE id = :id"), {"id": ids[0]})

    written = PassageCatalog().revocabulary(
        [(ids[0], "de", ["kontoführung"]), (ids[1], "de", ["karte"])]
    )

    assert written == 1
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT lemmas FROM passages WHERE id = :id"), {"id": ids[1]}
        ).scalar_one() == ["karte"]
