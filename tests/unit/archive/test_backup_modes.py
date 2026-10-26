"""Everything a backup writes is readable by its owner alone.

A backup holds every customer document, its parse and the archive, so a
folder the docs suggest as /backups/<date> must not be readable by every
account on the host, whatever umask the operator's shell has.
"""

from __future__ import annotations

import io
import os
import stat
from pathlib import Path

import pytest

from archive import backup

#: A German and an English document, a parse and a figure, as the buckets hold them.
_HELD = {
    "documents": {
        "qa_x/ab12.pdf": b"%PDF-1.7 Preisverzeichnis",
        "qa_x/cd34.pdf": b"%PDF-1.7 Price list",
    },
    "parsed": {"qa_x/ab12.json": b"{}"},
    "export": {"topics/qa_x/de.html": "<p>Gebühren</p>".encode()},
}


class _Client:
    """A stand-in S3 client holding _HELD."""

    def get_paginator(self, _name: str):
        class _Pages:
            def paginate(self, Bucket: str):
                return [{"Contents": [{"Key": key} for key in _HELD[Bucket]]}]

        return _Pages()

    def get_object(self, Bucket: str, Key: str):
        return {"Body": io.BytesIO(_HELD[Bucket][Key])}


@pytest.fixture
def loose_umask():
    """The usual shell umask, under which a file is world-readable by default."""
    before = os.umask(0o022)
    yield
    os.umask(before)


def test_every_file_and_folder_the_backup_writes_is_its_owners_alone(
    monkeypatch, tmp_path: Path, loose_umask
) -> None:
    """The objects, the manifest and the folders, under a shell's 022."""
    monkeypatch.setattr(backup.telemetry, "configure", lambda *_: None)
    monkeypatch.setattr(backup, "s3_client", _Client)
    monkeypatch.setattr(backup, "_buckets", lambda: list(_HELD))
    monkeypatch.setattr(backup, "_counts", lambda: {"documents": 2})
    target = tmp_path / "backup"

    assert backup.main(["--backup", str(target)]) == 0

    written = [target, *target.rglob("*")]
    assert any(one.name == backup.MANIFEST for one in written)
    assert len([one for one in written if one.is_file()]) == 5
    loose = {
        str(one.relative_to(tmp_path)): oct(stat.S_IMODE(one.stat().st_mode))
        for one in written
        if stat.S_IMODE(one.stat().st_mode) & 0o077
    }
    assert not loose, loose


def test_a_folder_that_already_exists_is_closed_to_everyone_else(
    monkeypatch, tmp_path: Path, loose_umask
) -> None:
    """The folder `make backup` made for the dumps is closed before the objects go in."""
    monkeypatch.setattr(backup.telemetry, "configure", lambda *_: None)
    monkeypatch.setattr(backup, "s3_client", _Client)
    monkeypatch.setattr(backup, "_buckets", lambda: ["parsed"])
    monkeypatch.setattr(backup, "_counts", dict)
    target = tmp_path / "backup"
    (target / "db").mkdir(parents=True, mode=0o755)
    (target / "db").chmod(0o755)
    target.chmod(0o755)

    backup.main(["--backup", str(target)])

    assert stat.S_IMODE(target.stat().st_mode) == 0o700
    assert stat.S_IMODE((target / "db").stat().st_mode) == 0o700
