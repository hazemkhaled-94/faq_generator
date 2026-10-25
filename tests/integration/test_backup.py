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


def _as(monkeypatch, postgres: str, name: str) -> None:
    """Points this process at another database name (the key prefix follows DATABASE_URL)."""
    from sqlalchemy.engine import make_url

    monkeypatch.setenv(
        "DATABASE_URL",
        make_url(postgres).set(database=name).render_as_string(hide_password=False),
    )


def _two_databases(postgres, monkeypatch, tmp_path):
    """A backup taken as qa_a while qa_b holds an object; qa_b then rewrites it and qa_a loses its own."""
    from archive import backup
    from blob_store.s3 import ParsedBucket

    key = ParsedBucket.key_for("12" * 32)
    mine = ParsedBucket.key_for("34" * 32)
    _as(monkeypatch, postgres, "qa_b")
    ParsedBucket().put(key, b"B-v1", content_type="application/json")
    _as(monkeypatch, postgres, "qa_a")
    ParsedBucket().put(mine, b"A-v1", content_type="application/json")
    monkeypatch.setattr(backup, "_counts", dict)
    (tmp_path / "db").mkdir()
    backup.backup(tmp_path)
    _as(monkeypatch, postgres, "qa_b")
    ParsedBucket().put(key, b"B-v2", content_type="application/json")
    _as(monkeypatch, postgres, "qa_a")
    ParsedBucket().put(mine, b"A-v2", content_type="application/json")
    return backup, key, mine


def test_a_restore_of_one_database_puts_back_only_its_own_objects(
    postgres, buckets, monkeypatch, tmp_path
) -> None:
    """Another database on the stack keeps the bytes it wrote after the backup."""
    from blob_store.s3 import ParsedBucket

    backup, key, mine = _two_databases(postgres, monkeypatch, tmp_path)

    backup.restore(tmp_path)

    assert ParsedBucket().get(mine) == b"A-v1"
    _as(monkeypatch, postgres, "qa_b")
    assert ParsedBucket().get(key) == b"B-v2", "qa_b's object was rolled back"


def test_a_restore_of_the_stack_puts_back_every_database(
    postgres, buckets, monkeypatch, tmp_path
) -> None:
    """The whole-stack restore is the one that rolls the others back."""
    from blob_store.s3 import ParsedBucket

    backup, key, _ = _two_databases(postgres, monkeypatch, tmp_path)

    backup.restore(tmp_path, stack=True)

    _as(monkeypatch, postgres, "qa_b")
    assert ParsedBucket().get(key) == b"B-v1"


def test_a_scoped_verification_ignores_another_databases_objects(
    postgres, buckets, monkeypatch, tmp_path
) -> None:
    """After qa_a's restore, qa_b's newer object is not a difference."""
    backup, *_ = _two_databases(postgres, monkeypatch, tmp_path)
    backup.restore(tmp_path)

    assert backup.verify(tmp_path) == []
    assert backup.verify(tmp_path, stack=True) != []
