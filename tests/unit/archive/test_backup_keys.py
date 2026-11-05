"""A key that leads out of `DIR/s3/<bucket>` is refused by backup, restore and verify.

The key comes from the store's listing, or from the manifest file: whoever can
write a key into a bucket, or edit a backup, would otherwise choose a path on
the operator's host, which `make backup` and `make restore-backup` run on as
the operator.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fakes import FakeObjectStore

from archive import backup

#: Keys that climb out of the bucket's folder, or name a path of their own.
_CLIMBING = [
    "qa_bank/../../../../planted.sh",
    "qa_bank/../../../../Überweisung.txt",
    "../../Πληρωμή.txt",
    "qa_bank/ab/../../../../../../planted-pl.txt",
]

#: Keys whose parts pathlib would drop or fold into another object's path.
_ALIASING = [
    "qa_bank/ab/ab12.pdf/.",
    "qa_bank/ab/ab12.pdf/",
    "qa_bank/..",
    "qa_bank//x",
]

GOOD = "qa_bank/ab/ab12.pdf"


def _held(key: str) -> dict:
    """One good document and one planted object, in a bucket."""
    return {"documents": {GOOD: b"%PDF-1.7 Kontoauszug", key: b"planted"}}


def _backup(monkeypatch, tmp_path: Path, held: dict) -> Path:
    monkeypatch.setattr(backup.telemetry, "configure", lambda *_: None)
    monkeypatch.setattr(backup.store, "object_store", lambda: FakeObjectStore(held))
    monkeypatch.setattr(backup, "_buckets", lambda: list(held))
    monkeypatch.setattr(backup, "_counts", dict)
    target = tmp_path / "backup"
    assert backup.main(["--backup", str(target)]) == 0
    return target


def _outside(tmp_path: Path, target: Path) -> list[str]:
    """Every file under tmp_path that is not inside the backup."""
    return sorted(
        str(one.relative_to(tmp_path))
        for one in tmp_path.rglob("*")
        if one.is_file() and not one.resolve().is_relative_to(target.resolve())
    )


def _keys(target: Path) -> list[str]:
    manifest = json.loads((target / "manifest.json").read_text())
    return [one["key"] for one in manifest["objects"]]


@pytest.mark.parametrize("key", _CLIMBING)
def test_a_backup_writes_no_object_outside_its_folder(
    monkeypatch, tmp_path: Path, key: str, caplog
) -> None:
    """The planted object is left out and named; the good one is copied."""
    target = _backup(monkeypatch, tmp_path / "work", _held(key))

    assert _outside(tmp_path / "work", target) == []
    assert _keys(target) == [GOOD]
    assert key in caplog.text


@pytest.mark.parametrize("key", _ALIASING)
def test_a_backup_refuses_a_key_with_an_empty_dot_or_dot_dot_part(
    monkeypatch, tmp_path: Path, key: str
) -> None:
    """Pathlib would drop the part, and the planted object would overwrite the good one."""
    target = _backup(monkeypatch, tmp_path, _held(key))

    assert _keys(target) == [GOOD]
    assert (target / "s3/documents" / GOOD).read_bytes() == b"%PDF-1.7 Kontoauszug"


def test_a_backup_refuses_an_absolute_key(monkeypatch, tmp_path: Path) -> None:
    """An absolute key would replace the whole path."""
    outside = tmp_path / "elsewhere" / "planted.txt"
    held = {"export": {str(outside): b"<p>Tarif</p>"}}

    target = _backup(monkeypatch, tmp_path, held)

    assert not outside.exists(), f"{outside} was written outside {target}"


def test_a_backup_into_a_folder_whose_s3_is_a_symlink_writes_nothing_outside(
    monkeypatch, tmp_path: Path
) -> None:
    """The folder allowed is the one the operator named, not where a link leads."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    folder = tmp_path / "backup"
    (folder / "db").mkdir(parents=True)
    (folder / "s3").symlink_to(elsewhere, target_is_directory=True)
    monkeypatch.setattr(backup.telemetry, "configure", lambda *_: None)
    held = {"documents": {GOOD: b"%PDF-1.7"}}
    monkeypatch.setattr(backup.store, "object_store", lambda: FakeObjectStore(held))
    monkeypatch.setattr(backup, "_buckets", lambda: list(held))
    monkeypatch.setattr(backup, "_counts", dict)

    assert backup.main(["--backup", str(folder)]) == 0

    assert [one for one in elsewhere.rglob("*") if one.is_file()] == []


@pytest.fixture
def tampered(monkeypatch, tmp_path: Path):
    """A backup whose manifest names a file outside it, and the store restoring it."""

    def build(key: str, *, linked: bool = False, bucket: str = "documents"):
        secret = tmp_path / "secret.txt"
        secret.write_bytes(b"the operator's private file")
        folder = tmp_path / "backup"
        if linked:
            # What a backup copied in from elsewhere may hold: s3 a symlink.
            home = tmp_path / "home"
            (home / bucket / "qa_bank").mkdir(parents=True)
            (home / bucket / "qa_bank" / "id_rsa").write_bytes(b"PRIVATE KEY")
            folder.mkdir()
            (folder / "s3").symlink_to(home, target_is_directory=True)
        else:
            (folder / "s3" / "documents").mkdir(parents=True)
        entry = {"bucket": bucket, "key": key, "bytes": 1, "sha256": "0" * 64}
        manifest = {"rows": {}, "dumps": {}, "objects": [entry]}
        (folder / "manifest.json").write_text(json.dumps(manifest))
        one = FakeObjectStore({"documents": {}})
        monkeypatch.setattr(backup.store, "object_store", lambda: one)
        monkeypatch.setattr(backup, "_counts", dict)
        monkeypatch.setattr(backup.rekey, "digests", set)
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/qa_bank")
        return folder, one

    return build


def test_a_restore_reads_no_file_outside_the_backup(tampered) -> None:
    """The manifest key climbs to a file the backup does not hold: nothing is uploaded."""
    folder, store = tampered("../../../secret.txt")

    backup.restore(folder, stack=True)

    assert store.buckets["documents"] == {}, "the operator's file was uploaded"


@pytest.mark.parametrize("stack", [False, True])
def test_a_restore_through_a_symlinked_s3_folder_uploads_nothing(
    tampered, stack: bool
) -> None:
    """A host file reached through a linked s3 entry is not uploaded."""
    folder, store = tampered("qa_bank/id_rsa", linked=True)

    backup.restore(folder, stack=stack)

    assert store.buckets["documents"] == {}, store.buckets


def test_a_verify_through_a_symlinked_s3_folder_reports_it(tampered) -> None:
    """A difference, not a pass."""
    folder, _ = tampered("qa_bank/id_rsa", linked=True)

    assert backup.verify(folder, stack=True) == [
        "documents/qa_bank/id_rsa leads out of the backup"
    ]


@pytest.mark.parametrize("bucket", ["..", "a/b", "../home", ".", ""])
def test_a_manifest_bucket_that_is_not_one_plain_segment_is_refused(
    tampered, bucket: str
) -> None:
    """The bucket is part of the path too."""
    folder, store = tampered("qa_bank/id_rsa", bucket=bucket)

    backup.restore(folder, stack=True)

    assert store.buckets["documents"] == {}


def test_a_verify_names_the_key_that_leads_out(tampered) -> None:
    """A difference, not a pass, and not a read of the path."""
    folder, _ = tampered("../../../secret.txt")

    assert backup.verify(folder, stack=True) == [
        "documents/../../../secret.txt leads out of the backup"
    ]


def test_an_ordinary_backup_restores_and_verifies(monkeypatch, tmp_path: Path) -> None:
    """The check refuses nothing a store holds in the ordinary way."""
    one = FakeObjectStore({"documents": {GOOD: b"%PDF-1.7 Kontoauszug"}})
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/qa_bank")
    monkeypatch.setattr(backup.telemetry, "configure", lambda *_: None)
    monkeypatch.setattr(backup.store, "object_store", lambda: one)
    monkeypatch.setattr(backup, "_buckets", lambda: ["documents"])
    monkeypatch.setattr(backup, "_counts", dict)
    monkeypatch.setattr(backup.rekey, "digests", set)
    folder = tmp_path / "backup"
    assert backup.main(["--backup", str(folder)]) == 0
    one.buckets["documents"].clear()

    backup.restore(folder)

    assert one.buckets["documents"] == {GOOD: b"%PDF-1.7 Kontoauszug"}
    assert backup.verify(folder) == []
