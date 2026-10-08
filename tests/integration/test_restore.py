"""Putting back what a wipe took, from the archive it left.

The corpus is deleted the way `make wipe` deletes it, so the triggers and
the removal paths fill the archive and nothing here writes to it directly.
"""

from __future__ import annotations

import pytest
from seed import (
    digest,
    document,
    event,
    fact,
    fitted,
    link,
    membership,
    passage,
    question,
)
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from database.qa_generator import Assessment, AssessmentMetric, Base

pytestmark = pytest.mark.integration

PDF = b"%PDF-1.7\nnot really a document\n"

#: Every table the triggers archive.
TABLES = sorted(set(Base.metadata.tables) - {"archived_rows"})


@pytest.fixture
def corpus(engine, database, buckets) -> str:
    """A document and everything a run and a person built on it."""
    from blob_store.s3 import DocumentsBucket, ExportBucket, ModelsBucket, ParsedBucket

    sha = digest()
    source, parsed = DocumentsBucket(), ParsedBucket()
    source.put(
        source.key_for(sha, "application/pdf"), PDF, content_type="application/pdf"
    )
    parsed.put(parsed.key_for(sha), b"{}", content_type="application/json")
    figure, model = ExportBucket(), ModelsBucket()
    figure.put(
        figure.topic_visualisation_key("de"),
        b"<html>de</html>",
        content_type=figure.TOPIC_VISUALISATION_TYPE,
    )
    model.put(model.topic_model_key("de"), b"npz", content_type=model.TOPIC_MODEL_TYPE)

    with Session(engine) as session:
        session.add(document(sha, parse_status="parsed", chunk_status="chunked"))
        session.add(event(sha256=sha))
        session.flush()
        cut = passage(sha, ordinal=1)
        session.add(cut)
        session.flush()
        drawn = fact(cut.id, reviewed_verdict="accepted", reviewed_at=func.now())
        session.add(drawn)
        subject = fitted(0, language="de", label="Lieferzeiten", labelled_by="person")
        session.add(subject)
        session.flush()
        session.add(membership(cut.id, subject.id))
        asked = question()
        session.add(asked)
        session.flush()
        followed = question(follows_id=asked.id, thread_position=2)
        session.add(followed)
        session.flush()
        session.add_all([link(asked.id, drawn.id), link(followed.id, drawn.id)])
        session.add(
            Assessment(
                artifact_kind="topic",
                topic_id=subject.id,
                assess_status="assessed",
                approved=True,
                assessed_at=func.now(),
                metrics=[
                    AssessmentMetric(
                        metric="relevance", label="relevant", score=1.0, approved=True
                    )
                ],
            )
        )
        replaced = fact(cut.id, statement="The device weighs 5 kg.")
        session.add(replaced)
        session.commit()
        replaced_id = replaced.id

    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM facts WHERE id = :id"), {"id": replaced_id}
        )
    return sha


def rows(engine) -> dict[str, list[str]]:
    """Every live row of every archived table, as text, minus its vector."""
    with engine.connect() as connection:
        return {
            table: sorted(
                connection.execute(
                    text(f"SELECT (to_jsonb(t) - 'embedding')::text FROM {table} t")
                ).scalars()
            )
            for table in TABLES
        }


def objects() -> dict[str, dict[str, bytes]]:
    """Every object in every bucket, by key."""
    from blob_store.s3 import s3_client

    client = s3_client()
    return {
        bucket: {
            held["Key"]: client.get_object(Bucket=bucket, Key=held["Key"])[
                "Body"
            ].read()
            for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket)
            for held in page.get("Contents", [])
        }
        for bucket in ("documents", "parsed", "export", "models", "archive")
    }


def archived(engine) -> int:
    """How many rows the archive holds."""
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT count(*) FROM archived_rows")
        ).scalar_one()


def now(engine) -> str:
    """The database's clock, which is the one `archived_at` is written by."""
    with engine.connect() as connection:
        return connection.execute(text("SELECT now()")).scalar_one().isoformat()


def wipe() -> None:
    """The two deletions `make wipe` starts with."""
    from ingestion.run import main as ingestion
    from topic_modelling.run import main as topics

    assert ingestion(["--delete-all"]) == 0
    assert topics(["--delete"]) == 0


def test_a_wipe_comes_back_as_it_was_and_only_once(corpus, engine, monkeypatch) -> None:
    """Rows and objects back, the archive untouched, a second run a no-op."""
    from archive import restore

    before, stored, since = rows(engine), objects(), now(engine)

    wipe()

    gone = rows(engine)
    assert not any(gone.values()), {t: len(r) for t, r in gone.items() if r}
    kept, held = archived(engine), objects()["archive"]

    monkeypatch.setenv("SINCE", since)
    assert restore.main() == 0

    after = rows(engine)
    assert after == before, {t: after[t] for t in TABLES if after[t] != before[t]}
    assert "Lieferzeiten" in after["topics"][0], "the label a person gave"
    assert {k: v for k, v in objects().items() if k != "archive"} == {
        k: v for k, v in stored.items() if k != "archive"
    }
    assert archived(engine) == kept, "a restore is a copy, not a move"
    assert objects()["archive"] == held

    assert restore.main() == 0

    assert rows(engine) == before
    assert archived(engine) == kept
    assert objects()["archive"] == held


def test_an_object_written_since_is_left_alone(corpus, engine, monkeypatch) -> None:
    """A fit after the wipe drew its own figure; the archived one stays archived."""
    from archive import restore
    from blob_store.s3 import ExportBucket

    since = now(engine)
    wipe()
    key = ExportBucket.topic_visualisation_key("de")
    ExportBucket().put(
        key, b"<html>refit</html>", content_type=ExportBucket.TOPIC_VISUALISATION_TYPE
    )

    monkeypatch.setenv("SINCE", since)
    assert restore.main() == 0

    assert ExportBucket().find(key) == b"<html>refit</html>"


def test_the_newest_copy_of_a_row_is_the_one_restored(
    corpus, engine, monkeypatch
) -> None:
    """A document deleted, uploaded again and deleted again is archived twice."""
    from archive import restore
    from ingestion.factory import build_removal

    since = now(engine)
    build_removal().delete(corpus)
    with Session(engine) as session:
        session.add(document(corpus, title="Uploaded again"))
        session.commit()
    build_removal().delete(corpus)

    monkeypatch.setenv("SINCE", since)
    assert restore.main() == 0

    with engine.connect() as connection:
        title = connection.execute(text("SELECT title FROM documents")).scalar_one()
    assert title == "Uploaded again"


def test_a_row_whose_parent_was_replaced_restores_nothing(
    corpus, engine, monkeypatch
) -> None:
    """A re-chunk since the wipe holds the passage's key, so its facts have none."""
    from archive import restore

    since = now(engine)
    wipe()
    with Session(engine) as session:
        session.add(document(corpus))
        session.flush()
        session.add(passage(corpus, ordinal=1, text="Chunked again."))
        session.commit()
    rebuilt = rows(engine)

    monkeypatch.setenv("SINCE", since)
    assert restore.main() == 1

    assert rows(engine) == rebuilt


def test_without_a_time_nothing_is_restored(corpus, engine, monkeypatch) -> None:
    """The archive holds every deletion ever made, reruns included."""
    from archive import restore

    wipe()
    monkeypatch.delenv("SINCE", raising=False)

    assert restore.main() == 2

    assert not any(rows(engine).values())


def test_a_question_resting_on_two_documents_comes_back_accepted(
    engine, database, buckets, monkeypatch
) -> None:
    """A wipe takes every document at once, so no question is rejected on the way."""
    from archive import restore
    from blob_store.s3 import DocumentsBucket

    source = DocumentsBucket()
    with Session(engine) as session:
        facts = []
        for seed in ("one", "two"):
            sha = digest(seed)
            source.put(
                source.key_for(sha, "application/pdf"),
                PDF,
                content_type="application/pdf",
            )
            session.add(document(sha, parse_status="parsed", chunk_status="chunked"))
            session.flush()
            cut = passage(sha, ordinal=1)
            session.add(cut)
            session.flush()
            drawn = fact(cut.id)
            session.add(drawn)
            session.flush()
            facts.append(drawn.id)
        asked = question(status="accepted")
        session.add(asked)
        session.flush()
        session.add_all([link(asked.id, one) for one in facts])
        session.commit()
        asked_id = asked.id
    since = now(engine)

    wipe()
    monkeypatch.setenv("SINCE", since)
    assert restore.main() == 0

    with engine.connect() as connection:
        status = connection.execute(
            text("SELECT status::text FROM questions WHERE id = :id"), {"id": asked_id}
        ).scalar_one()
    assert status == "accepted"
