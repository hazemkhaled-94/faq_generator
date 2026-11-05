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


def _held(key: str) -> dict:
    """One good document and one planted object, in a bucket."""
    return {"documents": {"qa_bank/ab/ab12.pdf": b"%PDF-1.7 Kontoauszug", key: b"x"}}


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


@pytest.mark.parametrize("key", _CLIMBING)
def test_a_backup_writes_no_object_outside_its_folder(
    monkeypatch, tmp_path: Path, key: str, caplog
) -> None:
    """The planted object is left out and named; the good one is copied."""
    target = _backup(monkeypatch, tmp_path / "work", _held(key))

    assert _outside(tmp_path / "work", target) == []
    keys = [
        one["key"]
        for one in json.loads((target / "manifest.json").read_text())["objects"]
    ]
    assert keys == ["qa_bank/ab/ab12.pdf"]
    assert key in caplog.text


def test_a_backup_refuses_an_absolute_key(monkeypatch, tmp_path: Path) -> None:
    """An absolute key would replace the whole path."""
    outside = tmp_path / "elsewhere" / "planted.txt"
    held = {"export": {str(outside): b"<p>Tarif</p>"}}

    target = _backup(monkeypatch, tmp_path, held)

    assert not outside.exists(), f"{outside} was written outside {target}"


@pytest.fixture
def tampered(monkeypatch, tmp_path: Path):
    """A backup whose manifest names a file outside it, and the store restoring it."""
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"the operator's private file")
    folder = tmp_path / "backup"
    (folder / "s3" / "documents").mkdir(parents=True)
    manifest = {
        "rows": {},
        "dumps": {},
        "objects": [
            {
                "bucket": "documents",
                "key": "../../../secret.txt",
                "bytes": 1,
                "sha256": "0" * 64,
            }
        ],
    }
    (folder / "manifest.json").write_text(json.dumps(manifest))
    held: dict = {"documents": {}}
    store = FakeObjectStore(held)
    monkeypatch.setattr(backup.store, "object_store", lambda: store)
    monkeypatch.setattr(backup, "_counts", dict)
    return folder, held


def test_a_restore_reads_no_file_outside_the_backup(tampered) -> None:
    """The manifest key climbs to a file the backup does not hold: nothing is uploaded."""
    folder, held = tampered

    backup.restore(folder, stack=True)

    assert held["documents"] == {}, "the operator's file was uploaded to the store"


def test_a_verify_names_the_key_that_leads_out(tampered) -> None:
    """A difference, not a pass, and not a read of the path."""
    folder, _ = tampered

    assert backup.verify(folder, stack=True) == [
        "documents/../../../secret.txt leads out of the backup"
    ]
