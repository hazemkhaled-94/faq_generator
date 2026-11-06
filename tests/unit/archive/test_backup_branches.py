"""A backup taken while the corpus changes under it still verifies.

An object deleted between the listing and its read is gone from the store,
so the manifest must not promise it: a later verify would report it missing
and a restore would fail reading a file that was never written.
"""

from __future__ import annotations

import json
from pathlib import Path

from fakes import FakeObjectStore

from archive import backup
from blob_store.store import Entry


class Vanishing(FakeObjectStore):
    """A store whose listing still names one key a deletion already took."""

    def __init__(self, buckets, gone: tuple[str, str]) -> None:
        super().__init__(buckets)
        self.gone = gone

    def listed(self, bucket, prefix=""):
        """The keys held, and the one already deleted."""
        entries = super().listed(bucket, prefix)
        if bucket == self.gone[0]:
            entries.append(Entry(self.gone[1], 9, entries[0].modified))
        return entries


def test_an_object_deleted_mid_backup_is_left_out_and_the_backup_verifies(
    monkeypatch, tmp_path: Path
) -> None:
    """The manifest holds what was read; verify then finds nothing wrong."""
    held = {
        "documents": {
            "qa_x/ab12.pdf": b"%PDF-1.7 Kontoauszug",
            "qa_x/cd34.pdf": b"%PDF-1.7 Account statement",
        }
    }
    source = Vanishing(held, ("documents", "qa_x/ef56.pdf"))
    monkeypatch.setattr(backup.telemetry, "configure", lambda *_: None)
    monkeypatch.setattr(backup.store, "object_store", lambda: source)
    monkeypatch.setattr(backup, "_buckets", lambda: ["documents"])
    monkeypatch.setattr(backup, "_counts", lambda: {"documents": 2})
    target = tmp_path / "backup"

    assert backup.main(["--backup", str(target)]) == 0

    manifest = json.loads((target / backup.MANIFEST).read_text())
    assert sorted(one["key"] for one in manifest["objects"]) == [
        "qa_x/ab12.pdf",
        "qa_x/cd34.pdf",
    ]
    assert not (target / "s3" / "documents" / "qa_x" / "ef56.pdf").exists()
    assert backup.verify(target, stack=True) == []
