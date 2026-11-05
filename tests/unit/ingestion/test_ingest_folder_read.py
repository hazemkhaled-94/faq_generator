"""`make ingest DIR=` holds a file to the size limit before it reads it whole.

The api reads at most the limit plus one byte of an upload and refuses the rest
unread. A folder an operator downloaded may hold a multi-gigabyte file named
`.pdf`, which the host command must not load into memory to refuse it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion import run
from ingestion.models import IngestResult


class _Service:
    """Refuses everything as too large, as the real one does past its limit."""

    max_file_size_bytes = 1024

    def __init__(self) -> None:
        self.sizes: list[int] = []

    def ingest(self, upload) -> IngestResult:
        self.sizes.append(upload.size_bytes)
        return IngestResult("too_large", None, "over the limit")


@pytest.mark.parametrize(
    "name",
    ["Kontoauszug-2026.pdf", "Relevé-de-compte.pdf", "Πληρωμή.pdf", "Wyciąg.pdf"],
)
def test_a_file_past_the_limit_is_read_to_one_byte_past_it(
    tmp_path: Path, name: str
) -> None:
    """A 64 KiB file under a 1 KiB limit reaches the service as 1025 bytes."""
    (tmp_path / name).write_bytes(b"%PDF-1.7\n" + b"0" * 64 * 1024)
    service = _Service()

    assert run._add(tmp_path, service) == 1  # type: ignore[arg-type]

    assert service.sizes == [service.max_file_size_bytes + 1]


def test_a_file_within_the_limit_is_read_whole(tmp_path: Path) -> None:
    """The limit is the service's to apply, so nothing short of it is cut."""
    (tmp_path / "Tarif.pdf").write_bytes(b"%PDF-1.7\n" + b"0" * 100)
    service = _Service()

    run._add(tmp_path, service)  # type: ignore[arg-type]

    assert service.sizes == [109]
