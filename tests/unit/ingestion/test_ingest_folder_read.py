"""`make ingest DIR=` holds a file to the size limit before it reads it whole.

The api reads at most the limit plus one byte of an upload and refuses the rest
unread. A folder an operator downloaded may hold a multi-gigabyte file named
`.pdf`, which the host command must not load into memory to refuse it.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest

from ingestion import run
from ingestion.models import IngestResult


class _Service:
    """Refuses everything as too large, as the real one does past its limit."""

    max_file_size_bytes = 1024

    def __init__(self) -> None:
        self.sizes: list[int] = []
        self.refused: list[tuple[str, int]] = []

    def ingest(self, upload) -> IngestResult:
        self.sizes.append(upload.size_bytes)
        return IngestResult("too_large", None, "over the limit")

    def refuse_oversized(self, filename: str, size_bytes: int) -> IngestResult:
        self.refused.append((filename, size_bytes))
        return IngestResult("too_large", None, "over the limit")


@pytest.mark.parametrize(
    "name",
    ["Kontoauszug-2026.pdf", "Relevé-de-compte.pdf", "Πληρωμή.pdf", "Wyciąg.pdf"],
)
def test_a_file_past_the_limit_is_refused_with_its_own_size_and_not_read(
    tmp_path: Path, name: str, monkeypatch
) -> None:
    """A 64 KiB file under a 1 KiB limit is refused on its size; its bytes stay unread."""
    path = tmp_path / name
    path.write_bytes(b"%PDF-1.7\n" + b"0" * 64 * 1024)
    service = _Service()
    monkeypatch.setattr(
        Path, "read_bytes", lambda self: pytest.fail("read the whole file")
    )

    assert run._add(tmp_path, service) == 1  # type: ignore[arg-type]

    assert service.refused == [(name, path.stat().st_size)]
    assert service.sizes == [], "the service was handed no bytes"


class _Grown:
    """A file of 10 bytes at the stat that holds 64 KiB when it is read."""

    name = "Tarif.pdf"
    suffix = ".pdf"

    def is_file(self) -> bool:
        return True

    def read_bytes(self) -> bytes:
        return b"0" * 64 * 1024

    def stat(self) -> os.stat_result:
        return os.stat_result((0, 0, 0, 0, 0, 0, 10, 0, 0, 0))

    def open(self, mode: str = "rb") -> io.BytesIO:
        return io.BytesIO(b"0" * 64 * 1024)


class _Folder:
    def is_dir(self) -> bool:
        return True

    def iterdir(self) -> list[_Grown]:
        return [_Grown()]


def test_a_file_that_grew_past_the_limit_is_read_to_one_byte_past_it() -> None:
    """Within the limit at the stat, over it at the read: still bounded."""
    service = _Service()

    run._add(_Folder(), service)  # type: ignore[arg-type]

    assert service.sizes == [service.max_file_size_bytes + 1]


def test_a_file_within_the_limit_is_read_whole(tmp_path: Path) -> None:
    """The limit is the service's to apply, so nothing short of it is cut."""
    (tmp_path / "Tarif.pdf").write_bytes(b"%PDF-1.7\n" + b"0" * 100)
    service = _Service()

    run._add(tmp_path, service)  # type: ignore[arg-type]

    assert service.sizes == [109]
