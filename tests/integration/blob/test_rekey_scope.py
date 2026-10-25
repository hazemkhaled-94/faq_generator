"""make s3-prefix copies what this database's rows name, and never replaces an object it already holds."""

from __future__ import annotations

import pytest
from seed import digest, document
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def test_rekey_keeps_a_newer_object_the_database_wrote_since(
    engine, database, buckets
) -> None:
    """A re-parse done since the upgrade survives the one-off copy of the bare object."""
    from blob_store.s3 import ParsedBucket, rekey, s3_client

    sha = digest("rekey-newer")
    key = ParsedBucket.key_for(sha)
    with Session(engine) as session:
        session.add(document(sha, parse_status="parsed"))
        session.commit()
    s3_client().put_object(Bucket="parsed", Key=key, Body=b"OLD-shared-parse")
    ParsedBucket().put(key, b"NEW-own-parse", content_type="application/json")

    assert rekey.main() == 0

    assert ParsedBucket().get(key) == b"NEW-own-parse"


def test_rekey_copies_only_the_objects_this_databases_rows_name(
    engine, database, buckets
) -> None:
    """A bare document, parse or archived copy of another database's digest stays out of the prefix."""
    from blob_store.s3 import (
        ArchiveBucket,
        DocumentsBucket,
        ParsedBucket,
        rekey,
        s3_client,
    )
    from blob_store.s3.bucket import _COUNTS

    mine, theirs = digest("rekey-mine"), digest("rekey-theirs")
    with Session(engine) as session:
        session.add(document(mine, parse_status="parsed"))
        session.commit()
    client = s3_client()
    for sha in (mine, theirs):
        client.put_object(
            Bucket="documents",
            Key=DocumentsBucket.key_for(sha, "application/pdf"),
            Body=b"%PDF",
        )
        client.put_object(Bucket="parsed", Key=ParsedBucket.key_for(sha), Body=b"{}")
        client.put_object(
            Bucket="archive",
            Key=f"documents/{DocumentsBucket.key_for(sha, 'application/pdf')}@20261001T000000.000000Z",
            Body=b"%PDF",
        )

    rekey.main()

    _COUNTS.clear()
    assert DocumentsBucket().count() == 1
    assert ParsedBucket().count() == 1
    assert ArchiveBucket().held() != [] and len(ArchiveBucket().held()) == 1
    assert ParsedBucket().find(ParsedBucket.key_for(mine)) == b"{}"


def test_rekey_names_an_archived_document_by_its_archived_row(
    engine, database, buckets
) -> None:
    """A document deleted before the one-off copy still has its archived file copied."""
    from sqlalchemy import text

    from blob_store.s3 import ArchiveBucket, DocumentsBucket, rekey, s3_client

    sha = digest("rekey-archived")
    with Session(engine) as session:
        session.add(document(sha))
        session.commit()
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM documents WHERE sha256 = :sha"), {"sha": sha}
        )
    s3_client().put_object(
        Bucket="archive",
        Key=f"documents/{DocumentsBucket.key_for(sha, 'application/pdf')}@20261001T000000.000000Z",
        Body=b"%PDF",
    )

    rekey.main()

    assert len(ArchiveBucket().held()) == 1
