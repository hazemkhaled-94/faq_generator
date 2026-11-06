"""A passage stored as read for want of a language is queued once the language is configured.

Chunking stores a passage in a language `NLP_MODELS` does not name as already
extracted, with nothing found. Once that language is configured, the nlp
README's steps are `make chunk-revocabulary` and `make chunk-rerun`. Both
keep the passage's row, so both must also put it back to new, or
`make extract-start`, which takes new passages only, never reads it. A passage
that a fact already cites, one that stays in no language, and one that was
read in its language all keep their status.
"""

from __future__ import annotations

import pytest
from seed import digest, document, fact
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.qa_generator import Status

pytestmark = pytest.mark.integration

#: (document language, the foreign passage, its language once configured)
FOREIGN = {
    "fr": (
        "de",
        "Les frais de dossier sont remboursés si la demande est rejetée.",
        "fr",
    ),
    "el": (
        "en",
        "Τα τέλη φακέλου επιστρέφονται αν η αίτηση απορριφθεί.",
        "el",
    ),
}

#: A passage read in its own language, stored as extracted by a finished run.
READ = {
    "de": ("de", "Die Gebühr wird bei Ablehnung des Antrags erstattet."),
    "en": ("en", "The fee is refunded if the application is rejected."),
}


def _chunking(passage_text: str, language: str | None):
    """One passage, as chunking cuts it, in `language` or in none."""
    from preprocessing.chunking.models import Chunk, Chunking

    return Chunking(
        passages=[
            Chunk(
                ordinal=1,
                text=passage_text,
                page_from=1,
                page_to=1,
                section_path=None,
                block_type="text",
                language=language,
                extractable=language is not None,
                sentences=[
                    {
                        "i": 0,
                        "start": 0,
                        "end": len(passage_text),
                        "predicates": 1,
                    }
                ],
            )
        ],
        oversized=0,
    )


def _state(engine) -> list[tuple]:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT language, extract_status FROM passages")
        ).all()


def _claimed(engine, sha: str) -> None:
    """The document as a chunk worker holds it."""
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE documents SET chunk_status = 'in_progress' WHERE sha256 = :s"),
            {"s": sha},
        )


def _stored(engine, sha: str, language: str, passage_text: str, read_in) -> int:
    """A document with one passage chunked in `read_in`; the passage's id."""
    from preprocessing.chunking.repository import ChunkQueue

    with Session(engine) as session:
        session.add(document(sha, language=language, chunk_status=Status.IN_PROGRESS))
        session.commit()
    ChunkQueue().replace(sha, _chunking(passage_text, read_in))
    with engine.connect() as connection:
        return connection.execute(text("SELECT id FROM passages")).scalar_one()


def _extracted(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("UPDATE passages SET extract_status = 'extracted'"))


@pytest.mark.parametrize("case", sorted(FOREIGN))
def test_a_rechunk_after_the_language_is_configured_queues_the_passage(
    engine, database, case
) -> None:
    """The re-chunk reads it in its language now: extraction must be able to start it."""
    from preprocessing.chunking.repository import ChunkQueue

    language, passage_text, configured = FOREIGN[case]
    sha = digest(case)
    _stored(engine, sha, language, passage_text, None)
    assert _state(engine) == [(None, "extracted")]

    _claimed(engine, sha)
    ChunkQueue().replace(sha, _chunking(passage_text, configured))

    assert _state(engine) == [(configured, "new")]


@pytest.mark.parametrize("case", sorted(FOREIGN))
def test_a_reread_after_the_language_is_configured_queues_the_passage(
    engine, database, case
) -> None:
    """`chunk-revocabulary` moves the language; the passage must not stay read."""
    from preprocessing.chunking.repository import PassageCatalog

    language, passage_text, configured = FOREIGN[case]
    passage_id = _stored(engine, digest(case), language, passage_text, None)

    PassageCatalog().revocabulary([(passage_id, configured, ["frais"])])

    assert _state(engine) == [(configured, "new")]


@pytest.mark.parametrize("case", sorted(READ))
def test_a_rechunk_keeps_the_status_of_a_passage_read_in_its_language(
    engine, database, case
) -> None:
    """The language did not move from none, so nothing is queued again."""
    from preprocessing.chunking.repository import ChunkQueue

    language, passage_text = READ[case]
    sha = digest(case)
    _stored(engine, sha, language, passage_text, language)
    _extracted(engine)

    _claimed(engine, sha)
    ChunkQueue().replace(sha, _chunking(passage_text, language))

    assert _state(engine) == [(language, "extracted")]


@pytest.mark.parametrize("case", sorted(READ))
def test_a_reread_keeps_the_status_of_a_passage_read_in_its_language(
    engine, database, case
) -> None:
    """A passage that had a language keeps its status when the re-read keeps it."""
    from preprocessing.chunking.repository import PassageCatalog

    language, passage_text = READ[case]
    passage_id = _stored(engine, digest(case), language, passage_text, language)
    _extracted(engine)

    PassageCatalog().revocabulary([(passage_id, language, ["gebuehr"])])

    assert _state(engine) == [(language, "extracted")]


@pytest.mark.parametrize("case", sorted(FOREIGN))
def test_a_passage_still_in_no_language_stays_read(engine, database, case) -> None:
    """Nothing was configured: re-chunk and re-read leave it extracted."""
    from preprocessing.chunking.repository import ChunkQueue, PassageCatalog

    language, passage_text, _ = FOREIGN[case]
    sha = digest(case)
    passage_id = _stored(engine, sha, language, passage_text, None)

    _claimed(engine, sha)
    ChunkQueue().replace(sha, _chunking(passage_text, None))
    PassageCatalog().revocabulary([(passage_id, None, [])])

    assert _state(engine) == [(None, "extracted")]


@pytest.mark.parametrize("case", sorted(FOREIGN))
def test_a_passage_a_fact_cites_stays_read(engine, database, case) -> None:
    """A fact came from a reading of it: neither path queues it again."""
    from preprocessing.chunking.repository import ChunkQueue, PassageCatalog

    language, passage_text, configured = FOREIGN[case]
    sha = digest(case)
    passage_id = _stored(engine, sha, language, passage_text, None)
    with Session(engine) as session:
        session.add(fact(passage_id, statement=passage_text))
        session.commit()

    _claimed(engine, sha)
    ChunkQueue().replace(sha, _chunking(passage_text, configured))
    assert _state(engine) == [(configured, "extracted")]

    PassageCatalog().revocabulary([(passage_id, configured, ["frais"])])
    assert _state(engine) == [(configured, "extracted")]
