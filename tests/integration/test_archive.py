"""What a deletion leaves behind, and the second deletion that takes it.

The trigger is the whole mechanism, so the tests here delete through the
paths a person actually uses - the removal service, a cascade, a raw
statement - and read `archived_rows` afterwards. A test that inserted into
it directly would pass against no trigger at all.
"""

from __future__ import annotations

import pytest
from seed import digest, document, fact, link, membership, passage, question
from sqlalchemy import text
from sqlalchemy.orm import Session

from archive.store import Archive, Purged
from database.qa_generator import Base
from ingestion.factory import build_removal

pytestmark = pytest.mark.integration

PDF = b"%PDF-1.7\nnot really a document\n"


@pytest.fixture
def archive(database, buckets) -> Archive:
    """The archive, over the container's database and object store."""
    return Archive()


@pytest.fixture
def held(engine, buckets) -> str:
    """A document with a file, a converted form and everything under it."""
    from blob_store.s3 import DocumentsBucket, ParsedBucket

    sha = digest()
    source, parsed = DocumentsBucket(), ParsedBucket()
    source.put(
        source.key_for(sha, "application/pdf"), PDF, content_type="application/pdf"
    )
    parsed.put(parsed.key_for(sha), b"{}", content_type="application/json")

    with Session(engine) as session:
        session.add(document(sha, chunk_status="chunked"))
        session.flush()
        first = passage(sha, ordinal=1)
        session.add(first)
        session.flush()
        drawn = fact(first.id)
        session.add(drawn)
        session.flush()
        asked = question()
        session.add(asked)
        session.flush()
        session.add(link(asked.id, drawn.id))
        session.commit()
    return sha


def archived(engine) -> dict[str, int]:
    """How many rows of each table the archive holds."""
    with engine.connect() as connection:
        return dict(
            connection.execute(
                text(
                    "SELECT table_name, count(*) FROM archived_rows GROUP BY table_name"
                )
            ).all()
        )


def test_deleting_a_document_archives_everything_it_cascaded_to(
    archive, held, engine
) -> None:
    """One command, six tables, and a copy of each row it took."""
    build_removal().delete(held)

    assert archived(engine) == {
        "documents": 1,
        "passages": 1,
        "facts": 1,
        "fact_passages": 1,
        "questions": 1,
        "question_facts": 1,
    }


def test_the_archived_row_is_the_whole_row(archive, held, engine) -> None:
    """Every column by name, so a person can read what was deleted."""
    build_removal().delete(held)

    with engine.connect() as connection:
        payload = connection.execute(
            text("SELECT payload FROM archived_rows WHERE table_name = 'questions'")
        ).scalar_one()

    assert payload["question_text"] == "What does the device weigh?"
    assert payload["language"] == "en"
    assert payload["id"] > 0, "the key is kept, so the row can be put back by hand"
    assert "embedding" not in payload, "a vector is ten times the rest of the row"


def test_the_objects_move_to_the_archive_bucket(archive, held) -> None:
    """The uploaded file is readable again from where the deletion put it."""
    from blob_store.s3 import ArchiveBucket, DocumentsBucket

    build_removal().delete(held)

    bucket, source = ArchiveBucket(), DocumentsBucket()
    uploaded = source.key_for(held, "application/pdf")

    (archived,) = [
        key
        for key, _ in bucket.held()
        if key.startswith(bucket.key_for(source.name, uploaded))
    ]
    assert bucket.find(archived) == PDF
    assert source.find(uploaded) is None, "moved, not copied"


def test_a_key_archived_twice_keeps_both_copies(buckets) -> None:
    """A refit's model deleted after the first fit's was deleted."""
    from blob_store.s3 import ArchiveBucket, ModelsBucket

    bucket, models = ArchiveBucket(), ModelsBucket()
    key = models.topic_model_key("en")
    for fit in (b"first fit", b"second fit"):
        models.put(key, fit, content_type=models.TOPIC_MODEL_TYPE)
        assert bucket.take(models.name, key)

    assert sorted(bucket.get(held) for held, _ in bucket.held()) == [
        b"first fit",
        b"second fit",
    ]
    assert bucket.give_back(models.name, key)
    assert models.find(key) == b"second fit", "the newest copy"


def test_a_copy_archived_under_the_old_layout_is_still_found(archive) -> None:
    """Keyed `{origin}/{key}`, before each copy was stamped."""
    from blob_store.s3 import ArchiveBucket, ModelsBucket

    bucket, models = ArchiveBucket(), ModelsBucket()
    key = models.topic_model_key("en")
    bucket.put(f"{models.name}/{key}", b"old", content_type=models.TOPIC_MODEL_TYPE)

    assert bucket.give_back(models.name, key)
    assert models.find(key) == b"old"
    assert archive.purge(older_than_days=0).objects == 1


def test_a_statement_nothing_in_python_ran_is_archived_too(
    archive, held, engine
) -> None:
    """The reason this is a trigger: psql and Adminer delete rows as well."""
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM questions"))

    assert archived(engine) == {"questions": 1, "question_facts": 1}


def test_every_table_archives_its_deletions(archive, engine) -> None:
    """A table added without a trigger is a table that deletes for good."""
    with engine.connect() as connection:
        attached = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT c.relname FROM pg_trigger t JOIN pg_class c "
                    "ON c.oid = t.tgrelid WHERE NOT t.tgisinternal "
                    "AND t.tgname LIKE '%_archive_deleted_row'"
                )
            ).all()
        }

    assert attached == set(Base.metadata.tables) - {"archived_rows"}


def test_the_archive_is_not_archived(archive, held, engine) -> None:
    """Otherwise purging it would write one row for every row it took."""
    build_removal().delete(held)

    archive.purge(table="questions")

    assert "archived_rows" not in archived(engine)


def test_purging_one_table_leaves_the_others(archive, held, engine) -> None:
    """A table is named to purge the questions and keep the document."""
    build_removal().delete(held)

    purged = archive.purge(table="questions")

    assert purged.rows == 1
    assert purged.objects == 0, "an object belongs to no table"
    assert "questions" not in archived(engine)
    assert archived(engine)["documents"] == 1


def test_purging_by_age_keeps_what_is_newer(archive, held) -> None:
    """The row is seconds old, so a day's cutoff must not reach it."""
    build_removal().delete(held)

    assert archive.purge(older_than_days=1).rows == 0
    assert archive.purge(older_than_days=0).rows == 6, (
        "measured by the clock that wrote the row, not the one asking"
    )


def test_a_purge_by_age_cuts_rows_and_objects_at_one_moment(
    archive, held, monkeypatch
) -> None:
    """The database's clock for both, so a host clock running slow keeps nothing."""
    from datetime import datetime

    from archive import store

    class Behind(datetime):
        """A host clock a quarter of a century slow."""

        @classmethod
        def now(cls, tz=None):
            """Answers the first of January 2000."""
            return cls(2000, 1, 1, tzinfo=tz)

    monkeypatch.setattr(store, "datetime", Behind)
    build_removal().delete(held)

    assert archive.purge(older_than_days=0) == Purged(rows=6, objects=2)


def test_purging_everything_takes_the_objects_with_it(archive, held) -> None:
    """Naming no table means the whole archive, bucket included."""
    build_removal().delete(held)

    purged = archive.purge()

    assert purged.rows == 6
    assert purged.objects == 2, "the uploaded file and the converted form"
    assert archive.objects() == (0, 0)


def test_the_status_report_says_what_is_held(archive, held, engine) -> None:
    """What `make archive` prints, heaviest table first."""
    build_removal().delete(held)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM documents"))

    held_rows = archive.rows()

    assert {one.table_name for one in held_rows} >= {"documents", "questions"}
    assert all(one.bytes > 0 for one in held_rows)
    assert all(one.oldest <= one.newest for one in held_rows)
    assert archive.objects() == (2, len(PDF) + len(b"{}"))


def test_a_topic_membership_is_archived_with_its_passage(archive, held, engine) -> None:
    """`topics` has no foreign key to a document; the membership does."""
    from seed import fitted

    with Session(engine) as session:
        subject = fitted()
        session.add(subject)
        session.flush()
        first = session.execute(text("SELECT id FROM passages LIMIT 1")).scalar_one()
        session.add(membership(first, subject.id))
        session.commit()

    build_removal().delete(held)

    assert archived(engine)["passage_topics"] == 1
    assert "topics" not in archived(engine), "a fit is over the corpus, not a file"


def fill(engine, count: int) -> None:
    """`count` archived rows of one table, as the trigger would have left them."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO archived_rows (table_name, payload) "
                "SELECT 'questions', jsonb_build_object('id', n) "
                "FROM generate_series(1, :count) AS n"
            ),
            {"count": count},
        )


def test_a_purge_commits_in_batches_not_in_one_delete(
    archive, engine, monkeypatch
) -> None:
    """A purge of a table the size of a corpus held one lock and one log record."""
    from sqlalchemy import event

    from archive import store

    fill(engine, 25)
    monkeypatch.setattr(store, "BATCH", 10)
    commits: list[int] = []
    bind = archive._session.kw["bind"]
    event.listen(bind, "commit", lambda connection: commits.append(1))

    purged = archive.purge(older_than_days=0)

    assert purged.rows == 25
    assert archived(engine) == {}
    assert len(commits) >= 3, "ten rows at a time, not one transaction for all"


def test_a_full_purge_leaves_the_rows_archived_after_it_started(
    archive, engine, monkeypatch
) -> None:
    """A re-extraction running beside a purge keeps its second chance."""
    from sqlalchemy import event

    from archive import store

    fill(engine, 25)
    monkeypatch.setattr(store, "BATCH", 10)
    commits: list[int] = []

    def arrive(connection) -> None:
        """After the first batch has committed, one more row is archived."""
        commits.append(1)
        if len(commits) == 2:
            with engine.begin() as other:
                other.execute(
                    text(
                        "INSERT INTO archived_rows (table_name, payload) "
                        "VALUES ('facts', '{\"id\": 1}')"
                    )
                )

    event.listen(archive._session.kw["bind"], "commit", arrive)

    purged = archive.purge()

    assert purged.rows == 25
    assert archived(engine) == {"facts": 1}, "the row that arrived was purged too"


def test_the_archive_size_is_estimated_without_counting_it(archive, engine) -> None:
    """What `make doctor` prints: the planner's row count and the table's size."""
    fill(engine, 25)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("ANALYZE archived_rows"))

    rows, size = archive.estimate()

    assert rows == 25
    assert size > 0
