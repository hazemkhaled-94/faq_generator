"""A backup comes back as it was, and says so when it does not."""

from __future__ import annotations

import json

import pytest
from seed import digest, document
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


@pytest.fixture
def stored(engine, database, buckets):
    """A document row, and an object in each of three buckets."""
    from blob_store.s3 import DocumentsBucket, ExportBucket, ParsedBucket

    sha = digest("bank")
    source, parsed, export = DocumentsBucket(), ParsedBucket(), ExportBucket()
    source.put(
        source.key_for(sha, "application/pdf"),
        b"%PDF-1.7 a",
        content_type="application/pdf",
    )
    parsed.put(parsed.key_for(sha), b"{}", content_type="application/json")
    export.put("topics/x/de.html", "<p>Grüße</p>".encode(), content_type="text/html")
    with Session(engine) as session:
        session.add(document(sha))
        session.commit()
    return sha


def empty(buckets_named=("documents", "parsed", "export")) -> None:
    """Deletes every object, as a lost store would."""
    from blob_store.s3 import s3_client

    client = s3_client()
    for bucket in buckets_named:
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            for held in page.get("Contents", []):
                client.delete_object(Bucket=bucket, Key=held["Key"])


def test_a_backup_restores_every_object_and_matches_its_manifest(
    stored, tmp_path
) -> None:
    """Back up, lose the store, restore, verify."""
    from archive import backup

    (tmp_path / "db").mkdir()
    (tmp_path / "db" / "qa_generator.dump").write_bytes(b"PGDMP not really")

    assert backup.main(["--backup", str(tmp_path)]) == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert len(manifest["objects"]) == 3 and manifest["rows"]["documents"] == 1
    assert "qa_generator.dump" in manifest["dumps"]

    empty()
    assert backup.main(["--verify", str(tmp_path)]) == 1
    assert backup.main(["--restore", str(tmp_path)]) == 0


def test_a_backup_never_overwrites_another(stored, tmp_path) -> None:
    """A directory that holds one is refused."""
    from archive import backup

    assert backup.main(["--backup", str(tmp_path)]) == 0
    assert backup.main(["--backup", str(tmp_path)]) == 2


def test_a_changed_object_dump_or_row_count_fails_the_verification(
    stored, tmp_path
) -> None:
    """Each of the three kinds of difference is named."""
    from archive import backup
    from blob_store.s3 import DocumentsBucket, s3_client

    (tmp_path / "db").mkdir()
    (tmp_path / "db" / "qa_generator.dump").write_bytes(b"PGDMP")
    backup.main(["--backup", str(tmp_path)])
    key = DocumentsBucket.scoped(DocumentsBucket.key_for(stored, "application/pdf"))
    s3_client().put_object(Bucket="documents", Key=key, Body=b"changed")
    (tmp_path / "db" / "qa_generator.dump").write_bytes(b"other")
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["rows"]["documents"] = 7
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))

    wrong = backup.verify(tmp_path)

    assert len(wrong) == 3, wrong
    assert any("dump" in line for line in wrong)
    assert any("documents/" in line and "differs" in line for line in wrong)
    assert any("documents holds 1 row" in line for line in wrong)
