"""Two databases on one object store never read, delete or purge each other's objects."""

from __future__ import annotations

import pytest
from seed import digest

pytestmark = pytest.mark.integration

PDF = b"%PDF-1.7\none shared document\n"
PARSED = b'{"pages": []}'


def use(monkeypatch, database: str) -> None:
    """Makes this process run against `database`, as another one would."""
    monkeypatch.setenv("DATABASE_URL", f"postgresql+psycopg://u:p@localhost/{database}")


@pytest.fixture
def both(buckets, monkeypatch):
    """Two databases that each hold the same PDF and its parsed form."""
    from blob_store.s3 import DocumentsBucket, ParsedBucket

    documents, parsed = DocumentsBucket(), ParsedBucket()
    sha = digest()
    key = documents.key_for(sha, "application/pdf")
    for database in ("qa_one", "qa_two"):
        use(monkeypatch, database)
        documents.put(key, PDF, content_type="application/pdf")
        parsed.put(parsed.key_for(sha), PARSED, content_type="application/json")
    return documents, parsed, key, sha


def test_a_delete_in_one_database_leaves_the_other_readable(both, monkeypatch) -> None:
    """The objects are two, not one shared by digest."""
    from blob_store.s3 import ArchiveBucket

    documents, parsed, key, sha = both
    use(monkeypatch, "qa_one")
    archive = ArchiveBucket()
    assert archive.take(documents.name, key)
    assert archive.take(parsed.name, parsed.key_for(sha))
    assert documents.find(key) is None

    use(monkeypatch, "qa_two")
    assert documents.get(key) == PDF
    assert parsed.get(parsed.key_for(sha)) == PARSED


def test_a_reparse_in_one_database_leaves_the_other_untouched(
    both, monkeypatch
) -> None:
    """A rewrite lands under the writer's own prefix."""
    _, parsed, _, sha = both
    use(monkeypatch, "qa_one")
    parsed.put(parsed.key_for(sha), b'{"pages": [1]}', content_type="application/json")

    use(monkeypatch, "qa_two")
    assert parsed.get(parsed.key_for(sha)) == PARSED


def test_an_archive_purge_in_one_database_keeps_the_others_copies(
    both, monkeypatch
) -> None:
    """Held and purged are listed under the database's prefix alone."""
    from blob_store.s3 import ArchiveBucket

    documents, _, key, _ = both
    archive = ArchiveBucket()
    for database in ("qa_one", "qa_two"):
        use(monkeypatch, database)
        assert archive.take(documents.name, key)
    use(monkeypatch, "qa_one")
    assert len(archive.held()) == 1
    assert archive.purge() == 1

    use(monkeypatch, "qa_two")
    assert len(archive.held()) == 1
    assert archive.give_back(documents.name, key)
    assert documents.get(key) == PDF


def test_an_unprefixed_object_is_read_but_never_written_or_deleted(
    buckets, monkeypatch
) -> None:
    """What a store holds from before the prefix stays readable, by every database."""
    from blob_store.s3 import ArchiveBucket, DocumentsBucket, s3_client

    documents = DocumentsBucket()
    key = documents.key_for(digest("c"), "application/pdf")
    s3_client().put_object(Bucket=documents.name, Key=key, Body=PDF)

    use(monkeypatch, "qa_one")
    assert documents.get(key) == PDF
    assert documents.find(key) == PDF
    assert not documents.remove(key), "only its own prefix is deleted"
    assert ArchiveBucket().take(documents.name, key), "copied to the archive"
    s3_client().head_object(Bucket=documents.name, Key=key)


def test_a_purge_raises_when_the_store_refuses_a_delete(buckets, monkeypatch) -> None:
    """DeleteObjects answers 200 with an Errors list; that is not a purge."""
    from blob_store.s3 import ArchiveBucket
    from blob_store.s3 import archive as module

    use(monkeypatch, "qa_one")
    archive = ArchiveBucket()
    archive.put("documents/ab/cd/x.pdf", b"x", content_type="application/pdf")

    real = module.s3_client()

    class Refusing:
        def get_paginator(self, name):
            return real.get_paginator(name)

        def delete_objects(self, **_):
            return {
                "Errors": [
                    {"Key": "qa_one/documents/ab/cd/x.pdf", "Code": "AccessDenied"}
                ]
            }

    monkeypatch.setattr(module, "s3_client", Refusing)
    with pytest.raises(RuntimeError, match="AccessDenied"):
        archive.purge()


def test_the_one_off_copy_puts_bare_keys_under_the_prefix_and_keeps_them(
    engine, database, buckets
) -> None:
    """Copy, never move: the other database still reads the bare key."""
    from seed import document
    from sqlalchemy.orm import Session

    from blob_store.s3 import DocumentsBucket, s3_client
    from blob_store.s3.rekey import main

    documents = DocumentsBucket()
    key = documents.key_for(digest("d"), "application/pdf")
    s3_client().put_object(Bucket=documents.name, Key=key, Body=PDF)
    with Session(engine) as session:
        session.add(document(digest("d")))
        session.commit()

    assert main() == 0

    s3_client().head_object(
        Bucket=documents.name, Key=f"{documents.database_name()}/{key}"
    )
    s3_client().head_object(Bucket=documents.name, Key=key)
    assert documents.remove(key)
    assert documents.get(key) == PDF, "the bare key is still there to fall back to"
