"""Writers of the nearest-twin score racing each other, in every language.

A store, a delete and a re-chunk each read and write scores that depend on what
the others have written. They take one lock per language, before any row they
write, so the one that comes second reads what the first committed: a delete
that overlapped a store left the store's passage scored against a document that
was gone, and nothing read it again. Each case runs for German, English, an
unconfigured Latin-script language (French) and Greek.
"""

from __future__ import annotations

import math
import threading
import time

import pytest
from seed import digest, document, passage
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from database.qa_generator import Document, Passage, furniture
from extraction.repository import FactCatalog, PassageQueue
from ingestion.repository import DocumentRepository
from preprocessing.chunking.models import Chunk, Chunking
from preprocessing.chunking.repository import ChunkQueue, PassageCatalog
from question_generation.queue import repeated_across_documents

pytestmark = pytest.mark.integration

#: German, English, French (configured nowhere) and Greek (another script).
LANGS = ["de", "en", "fr", "el"]


def _turned(angle: float) -> list[float]:
    return [math.cos(angle), math.sin(angle)] + [0.0] * 1022


def _held(engine, language, *letters, text_="Notice."):
    ids = []
    with Session(engine) as session:
        for letter in letters:
            if session.get(Document, digest(letter + language)) is None:
                session.add(document(digest(letter + language)))
        session.flush()
        for at, letter in enumerate(letters, 1):
            held = passage(
                digest(letter + language), ordinal=at, text=text_, language=language
            )
            session.add(held)
            session.flush()
            ids.append(held.id)
        session.commit()
    return ids


def _rows(engine):
    with engine.connect() as c:
        return {
            r[0]: (r[1], r[2])
            for r in c.execute(
                text(
                    "SELECT id, nearest_foreign_cosine, nearest_foreign_doc FROM passages"
                )
            )
        }


def _furniture(engine):
    with Session(engine) as session:
        return set(
            session.scalars(select(Passage.id).where(repeated_across_documents(0.95)))
        )


def _run(*jobs):
    errors = []

    def wrap(job, delay):
        try:
            time.sleep(delay)
            job()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=wrap, args=job) for job in jobs]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not errors, errors


def _slow_score(monkeypatch, hold=1.0):
    real = furniture.score

    def slow(session, ids):
        real(session, ids)
        time.sleep(hold)  # the transaction stays open after scoring

    monkeypatch.setattr(furniture, "score", slow)


@pytest.mark.parametrize("language", LANGS)
def test_two_workers_storing_a_twin_pair_at_once_both_score(
    engine, database, monkeypatch, language
):
    """Each worker waits for the other's vector, so both halves are scored."""
    a, b = _held(engine, language, "a", "b")
    _slow_score(monkeypatch)
    _run(
        (lambda: PassageQueue().store(a, [], embedding=_turned(0.0)), 0.0),
        (lambda: PassageQueue().store(b, [], embedding=_turned(0.01)), 0.3),
    )
    assert _furniture(engine) == {a, b}


@pytest.mark.parametrize("language", LANGS)
def test_two_workers_on_different_languages_do_not_wait(
    engine, database, monkeypatch, language
):
    """One lock to a language: a drain in another language is not held up."""
    a, _ = _held(engine, language, "a", "b")
    c, _ = _held(engine, "xx" if language != "en" else "pl", "c", "d")
    _slow_score(monkeypatch, hold=1.5)
    started = time.monotonic()
    _run(
        (lambda: PassageQueue().store(a, [], embedding=_turned(0.0)), 0.0),
        (lambda: PassageQueue().store(c, [], embedding=_turned(0.0)), 0.1),
    )
    assert time.monotonic() - started < 2.8


@pytest.mark.parametrize("language", LANGS)
def test_a_delete_racing_a_store_leaves_no_score_from_the_deleted_document(
    engine, database, language
):
    """D deletes Y (its twin) and holds its transaction for the object move; a worker stores x meanwhile."""
    (y,) = _held(engine, language, "y")
    (z,) = _held(engine, language, "z")
    FactCatalog().embed_passages([(y, _turned(0.0)), (z, _turned(0.5))])
    (x,) = _held(engine, language, "x")

    _run(
        (
            lambda: DocumentRepository().delete(
                digest("y" + language), lambda: time.sleep(1.5)
            ),
            0.0,
        ),
        (lambda: PassageQueue().store(x, [], embedding=_turned(0.01)), 0.5),
    )
    rows = _rows(engine)
    assert rows[x][1] != digest("y" + language), rows
    assert x not in _furniture(engine), rows


@pytest.mark.parametrize("language", LANGS)
def test_two_deletes_at_once_leave_no_score_from_a_deleted_document(
    engine, database, language
):
    """Each rescores in a snapshot that still holds the other's document, unless it waits."""
    (x,) = _held(engine, language, "x")
    (y,) = _held(engine, language, "y")
    (z,) = _held(engine, language, "z")
    (w,) = _held(engine, language, "w")
    FactCatalog().embed_passages(
        [(x, _turned(0.0)), (y, _turned(0.01)), (z, _turned(-0.02)), (w, _turned(1.0))]
    )
    assert _rows(engine)[x][1] == digest("y" + language)

    _run(
        (
            lambda: DocumentRepository().delete(
                digest("y" + language), lambda: time.sleep(1.5)
            ),
            0.0,
        ),
        (lambda: DocumentRepository().delete(digest("z" + language)), 0.5),
    )
    rows = _rows(engine)
    assert rows[x][1] == digest("w" + language), rows
    assert x not in _furniture(engine), rows


def _chunk(text_, language):
    return Chunk(
        ordinal=1,
        text=text_,
        page_from=1,
        page_to=1,
        section_path=None,
        block_type="text",
        language=language,
    )


@pytest.mark.parametrize(("old", "new"), [("de", "en"), ("en", "fr"), ("de", "el")])
def test_a_rechunk_that_keeps_a_passage_but_moves_its_language_rescores_it(
    engine, database, old, new
):
    """ChunkQueue.replace keeps a passage whose text, trail, sentences and cells are the same, and writes its language."""
    a, b = _held(engine, old, "a", "b")
    FactCatalog().embed_passages([(a, _turned(0.0)), (b, _turned(0.01))])
    assert _furniture(engine) == {a, b}

    ChunkQueue().replace(
        digest("a" + old), Chunking(passages=[_chunk("Notice.", new)], oversized=0)
    )

    with engine.connect() as c:
        kept = c.execute(
            text(
                "SELECT id, language, embedding IS NOT NULL FROM passages WHERE doc_sha256 = :d"
            ),
            {"d": digest("a" + old)},
        ).one()
    assert kept[0] == a and kept[1] == new and kept[2]
    assert _furniture(engine) == set(), _rows(engine)


@pytest.mark.parametrize("language", LANGS)
def test_a_rechunk_that_drops_the_twin_rescores_the_other_document(
    engine, database, language
):
    """The passage that took its score from the dropped one is offered again."""
    a, b = _held(engine, language, "a", "b")
    FactCatalog().embed_passages([(a, _turned(0.0)), (b, _turned(0.01))])
    ChunkQueue().replace(
        digest("b" + language),
        Chunking(passages=[_chunk("Revised notice.", language)], oversized=0),
    )
    assert a not in _furniture(engine), _rows(engine)


@pytest.mark.parametrize("language", LANGS)
def test_delete_all_rescores(engine, database, language):
    """Deleting several documents at once reads the scores they gave again."""
    a, b = _held(engine, language, "a", "b")
    FactCatalog().embed_passages([(a, _turned(0.0)), (b, _turned(0.01))])
    (c,) = _held(engine, language, "c")
    FactCatalog().embed_passages([(c, _turned(1.0))])
    DocumentRepository().delete_all([digest("b" + language)])
    assert _furniture(engine) == set(), _rows(engine)


@pytest.mark.parametrize(("old", "new"), [("de", "fr"), ("en", "el"), ("el", None)])
def test_revocabulary_moves_language(engine, database, old, new):
    """A passage moved to another language, or to none, leaves no furniture behind."""
    a, b = _held(engine, old, "a", "b")
    FactCatalog().embed_passages([(a, _turned(0.0)), (b, _turned(0.01))])
    PassageCatalog().revocabulary([(b, new, ["x"])])
    rows = _rows(engine)
    assert _furniture(engine) == set(), rows
    assert rows[a] == (None, None) or rows[a][0] is None, rows


@pytest.mark.parametrize("language", LANGS)
def test_rescore_of_a_passage_without_vector_leaves_no_doc(engine, database, language):
    """A passage whose nearest doc is deleted but which itself has no embedding (cleared by hand)."""
    a, b, c = _held(engine, language, "a", "b", "c")
    FactCatalog().embed_passages(
        [(a, _turned(0.0)), (b, _turned(0.01)), (c, _turned(1.0))]
    )
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE passages SET embedding = NULL WHERE id = :a"), {"a": a}
        )
    DocumentRepository().delete(digest("b" + language))
    rows = _rows(engine)
    assert rows[a] == (None, None), rows


def test_a_revocabulary_pass_skips_a_passage_deleted_since_it_was_read(
    engine, database
) -> None:
    """The pass reads for minutes and writes at the end; a document may go between."""
    a, b = _held(engine, "de", "a", "b")
    FactCatalog().embed_passages([(a, _turned(0.0)), (b, _turned(0.01))])
    DocumentRepository().delete(digest("b" + "de"))

    assert PassageCatalog().revocabulary([(a, "de", ["x"]), (b, "en", ["y"])]) == 1


def test_a_revocabulary_pass_and_a_store_do_not_deadlock(engine, database) -> None:
    """Both take the language locks before they write a row."""
    p, q, x = _held(engine, "de", "p", "q", "x")
    FactCatalog().embed_passages([(p, _turned(0.5)), (q, _turned(1.0))])
    _run(
        (lambda: PassageQueue().store(x, [], embedding=_turned(0.51)), 0.0),
        (
            lambda: PassageCatalog().revocabulary([(q, "de", ["a"]), (p, "en", ["b"])]),
            0.2,
        ),
    )
