"""Which archived copy a restore of a chosen deletion puts back.

An object deleted, written again and deleted again has two archived copies, each
stamped with when it was taken. A restore names deletions by `archived_at`, and
must put back the copy that deletion archived, not the newest one.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fakes import FakeObjectStore

from archive import restore
from blob_store import store
from blob_store.s3 import (
    ArchiveBucket,
    DocumentsBucket,
    ExportBucket,
    ModelsBucket,
    ParsedBucket,
)

FIRST = datetime(2026, 11, 1, 10, 0, 0, 250000, tzinfo=UTC)
SECOND = datetime(2026, 11, 3, 9, 30, 0, 125000, tzinfo=UTC)
SHA = "ab12" + "c" * 60


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def scalars(self):
        return [row[0] for row in self._rows]


class _Archive:
    """The two reads `_objects` makes of archived_rows, answered as one table."""

    def __init__(self, topics=(), documents=()) -> None:
        self._topics = list(topics)
        self._documents = list(documents)

    def execute(self, statement, parameters):
        text = str(statement)
        if "table_name = 'topics'" in text:
            return _Rows(self._topics)
        return _Rows(self._documents)


@pytest.fixture
def fake(monkeypatch):
    """Every bucket empty, the archive's keys as `take` writes them."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/qa_shop")
    buckets = (ArchiveBucket, ExportBucket, ModelsBucket, DocumentsBucket, ParsedBucket)
    for bucket in buckets:
        monkeypatch.setattr(bucket, "name", bucket.__name__.lower())
    one = FakeObjectStore({bucket.name: {} for bucket in buckets})
    monkeypatch.setattr(store, "object_store", lambda: one)
    return one


def _restored(archive: _Archive, chosen: list[datetime]) -> list[tuple[str, str]]:
    """What `restore._objects` could not put back."""
    return restore._objects(archive, chosen)  # type: ignore[arg-type]


def _archived(origin: str, key: str, data: bytes, at: datetime) -> None:
    """Writes one copy as `take` would have, stamped `at`."""
    stamp = at.strftime("%Y%m%dT%H%M%S.%fZ")
    ArchiveBucket().put(
        f"{origin}/{key}@{stamp}", data, content_type="application/octet-stream"
    )


@pytest.mark.parametrize("language", ["de", "en", "fr", "el"])
@pytest.mark.parametrize(("chosen", "fit"), [(FIRST, b"fit one"), (SECOND, b"fit two")])
def test_a_restore_puts_back_the_copy_its_own_deletion_archived(
    fake, language, chosen, fit
) -> None:
    """Topics deleted twice: AT names one of the deletions, and gets its fit."""
    model = ModelsBucket.topic_model_key(language)
    figure = ExportBucket.topic_visualisation_key(language)
    for data, at in ((b"fit one", FIRST), (b"fit two", SECOND)):
        _archived(ModelsBucket.name, model, data, at)
        _archived(ExportBucket.name, figure, data, at)

    assert _restored(_Archive(topics=[(language, chosen)]), [chosen]) == []

    assert ModelsBucket().get(model) == fit
    assert ExportBucket().get(figure) == fit


def test_a_restore_of_a_document_puts_back_the_copy_of_its_deletion(fake) -> None:
    """A document deleted, uploaded again and deleted again, then the first restored."""
    key = DocumentsBucket.key_for(SHA, "application/pdf")
    parsed = ParsedBucket.key_for(SHA)
    for data, at in ((b"%PDF Preisliste v1", FIRST), (b"%PDF Preisliste v2", SECOND)):
        _archived(DocumentsBucket.name, key, data, at)
        _archived(ParsedBucket.name, parsed, data + b" parsed", at)

    rows = [(SHA, "application/pdf", FIRST)]
    assert _restored(_Archive(documents=rows), [FIRST]) == []

    assert DocumentsBucket().get(key) == b"%PDF Preisliste v1"
    assert ParsedBucket().get(parsed) == b"%PDF Preisliste v1 parsed"


def test_two_chosen_deletions_of_one_key_put_back_the_later_copy(fake) -> None:
    """Both deletions restored: the rows of both are back, and the latest object."""
    model = ModelsBucket.topic_model_key("pl")
    _archived(ModelsBucket.name, model, b"fit one", FIRST)
    _archived(ModelsBucket.name, model, b"fit two", SECOND)

    rows = [("pl", FIRST), ("pl", SECOND)]
    _restored(_Archive(topics=rows), [FIRST, SECOND])

    assert ModelsBucket().get(model) == b"fit two"


def test_a_copy_from_before_stamping_is_used_only_where_none_is_stamped(
    fake,
) -> None:
    """The old layout keyed a copy by its prefix alone."""
    model = ModelsBucket.topic_model_key("en")
    ArchiveBucket().put(
        f"{ModelsBucket.name}/{model}", b"old", content_type="application/octet-stream"
    )
    assert ArchiveBucket().give_back(ModelsBucket.name, model, near=FIRST)
    assert ModelsBucket().get(model) == b"old"

    fake.delete(ModelsBucket.name, ModelsBucket.scoped(model))
    _archived(ModelsBucket.name, model, b"stamped", SECOND)
    assert ArchiveBucket().give_back(ModelsBucket.name, model, near=FIRST)
    assert ModelsBucket().get(model) == b"stamped"


def test_a_rollback_without_a_time_still_takes_the_newest_copy(fake) -> None:
    """`RemovalService` rolls a failed delete back with no time."""
    model = ModelsBucket.topic_model_key("en")
    _archived(ModelsBucket.name, model, b"fit one", FIRST)
    _archived(ModelsBucket.name, model, b"fit two", SECOND)

    assert ArchiveBucket().give_back(ModelsBucket.name, model)

    assert ModelsBucket().get(model) == b"fit two"
