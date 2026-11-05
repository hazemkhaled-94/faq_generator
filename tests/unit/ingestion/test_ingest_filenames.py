"""A file whose name no text column can hold is refused, and the batch goes on.

A name that is not valid UTF-8, a Latin-1 or cp1252 or ISO-8859-7 name unpacked
from an old archive, reads back from a directory listing with a lone
surrogate. It cannot be stored or put in object metadata, so the upload that
carried it stopped every later file of the folder. The check the api made for
itself belongs to the service both callers share.
"""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
import pytest

from ingestion import run
from ingestion.models import UploadedFile
from ingestion.service import IngestService


def _pdf(text: str) -> bytes:
    """A one-page PDF saying `text`."""
    book = pymupdf.open()
    book.new_page().insert_text((72, 80), text)
    return book.tobytes()


class _File:
    """A directory entry as `iterdir` returns it on a host with a UTF-8 locale."""

    def __init__(self, name: str, data: bytes) -> None:
        """Holds a name and the bytes it reads."""
        self.name, self._data = name, data
        self.suffix = Path(name).suffix

    def is_file(self) -> bool:
        """Every entry is a file."""
        return True

    def open(self, mode: str = "rb") -> io.BytesIO:
        """The file's bytes, opened for reading."""
        return io.BytesIO(self._data)

    def __lt__(self, other: _File) -> bool:
        """Listed by name."""
        return self.name < other.name


class _Folder:
    """A directory holding these entries."""

    def __init__(self, files: list[_File]) -> None:
        """Holds the entries."""
        self._files = files

    def is_dir(self) -> bool:
        """It exists."""
        return True

    def iterdir(self):
        """The entries."""
        return iter(self._files)


class _Repository:
    """What the service writes, kept."""

    def __init__(self) -> None:
        """Starts empty."""
        self.events: list[tuple[str, str]] = []
        self.stored: list[str] = []

    def exists(self, sha256: str) -> bool:
        """Nothing is held yet."""
        return False

    def record_attempt(
        self, filename, size_bytes, outcome, detail=None, sha256=None
    ) -> None:
        """Keeps the attempt."""
        filename.encode()  # the column would refuse what this refuses
        self.events.append((filename, outcome))

    def store(self, upload, facts) -> str:
        """Keeps the stored name."""
        upload.filename.encode()
        self.stored.append(upload.filename)
        return "stored"


class _Store:
    """An object store that, like the real one, cannot take a lone surrogate."""

    name = "documents"

    def key_for(self, sha256: str, media_type: str) -> str:
        """A key."""
        return sha256

    def put(self, key, data, *, content_type, metadata) -> None:
        """Refuses what percent-encoding the metadata refuses."""
        for value in metadata.values():
            value.encode()


def _service(repository: _Repository) -> IngestService:
    """A service over the stand-ins."""
    return IngestService(
        repository=repository,  # type: ignore[arg-type]
        store=_Store(),  # type: ignore[arg-type]
        max_file_size_bytes=10 * 1024 * 1024,
        allowed_media_types=("application/pdf",),
        pipeline_version="test",
    )


@pytest.mark.parametrize(
    "name",
    [
        "Geb\udcfchren.pdf",  # de: Latin-1 ü
        "Fees \udc96 2026.pdf",  # en: a cp1252 en dash
        "Fr\udce9quence.pdf",  # fr: Latin-1 é
        "\udcd4\udce9\udcec\udcde.pdf",  # el: ISO-8859-7
        "nul\x00name.pdf",
    ],
)
def test_one_unstorable_filename_does_not_stop_the_batch(name: str, caplog) -> None:
    """Both good files around it are ingested; the folder is reported refused."""
    repository = _Repository()
    folder = _Folder(
        [
            _File("a-first.pdf", _pdf("Price list")),
            _File(name, _pdf("Preisliste")),
            _File("zz-last.pdf", _pdf("Tarif")),
        ]
    )

    code = run._add(folder, _service(repository))  # type: ignore[arg-type]

    assert repository.stored == ["a-first.pdf", "zz-last.pdf"]
    assert code == 1
    assert name not in [event[0] for event in repository.events]


def test_the_refusal_says_why() -> None:
    """The result names the filename as the reason, in the api's own words."""
    result = _service(_Repository()).ingest(
        UploadedFile("Geb\udcfchren.pdf", _pdf("x"))
    )

    assert result.outcome == "invalid_value"
    assert "filename" in (result.detail or "")
