"""A single-database restore puts back the bare (pre-prefix) keys this database's rows name, and says so when it cannot."""

from __future__ import annotations

import pytest
from seed import digest, document
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def test_a_restore_of_one_database_after_a_lost_store_reads_its_legacy_document(
    engine, database, buckets, tmp_path
) -> None:
    """After a lost store the restore brings the legacy document back and verifies it."""
    from archive import backup
    from blob_store.s3 import DocumentsBucket, s3_client

    sha = digest("legacy-bank-terms")
    key = DocumentsBucket.key_for(sha, "application/pdf")
    client = s3_client()
    # An object stored before keys carried the database: the bare key.
    client.put_object(Bucket="documents", Key=key, Body=b"%PDF-1.7 legacy")
    with Session(engine) as session:
        session.add(document(sha))
        session.commit()
    assert DocumentsBucket().find(key) == b"%PDF-1.7 legacy"

    (tmp_path / "db").mkdir()
    assert backup.main(["--backup", str(tmp_path)]) == 0

    # The store is lost.
    for page in client.get_paginator("list_objects_v2").paginate(Bucket="documents"):
        for held in page.get("Contents", []):
            client.delete_object(Bucket="documents", Key=held["Key"])

    rc = backup.main(["--restore", str(tmp_path)])
    found = DocumentsBucket().find(key)
    assert rc == 0
    assert found == b"%PDF-1.7 legacy", "the document is unreadable after the restore"


def test_another_databases_legacy_object_is_left_alone(
    engine, database, buckets, tmp_path
) -> None:
    """A bare object no row of this database names is not this restore's to put back."""
    from archive import backup
    from blob_store.s3 import DocumentsBucket, s3_client

    theirs = DocumentsBucket.key_for(digest("someone-elses"), "application/pdf")
    s3_client().put_object(Bucket="documents", Key=theirs, Body=b"%PDF theirs")
    (tmp_path / "db").mkdir()
    assert backup.main(["--backup", str(tmp_path)]) == 0
    s3_client().delete_object(Bucket="documents", Key=theirs)

    assert backup.main(["--restore", str(tmp_path)]) == 0
    assert DocumentsBucket().find(theirs) is None
