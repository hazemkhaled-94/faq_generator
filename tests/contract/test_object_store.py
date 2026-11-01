"""What every object store adapter does, run against each one there is.

The adapters are `S3Store` over a stand-in for boto3's client (today's, with
no container) and an in-memory fake. An Azure Blob Storage adapter joins the
list by being added to `STORES`. The gateway itself is covered by
`tests/integration/blob`, which runs the buckets against SeaweedFS.
"""

from __future__ import annotations

import pytest
from fakes import FakeObjectStore, FakeS3Client

from blob_store import store
from blob_store.s3 import ArchiveBucket, DocumentsBucket
from blob_store.s3 import bucket as bucket_module
from blob_store.s3.client import S3Store

#: The buckets every store below holds, by the names a deployment would give them.
BUCKETS = {"statements": {}, "archive-eu": {}}


def _fake() -> FakeObjectStore:
    """Fake."""
    return FakeObjectStore(BUCKETS)


def _s3() -> S3Store:
    """S3."""
    return S3Store(FakeS3Client(BUCKETS))


STORES = {"fake": _fake, "s3": _s3}


@pytest.fixture(params=STORES)
def objects(request):
    """The port's objects."""
    return STORES[request.param]()


@pytest.fixture
def bound(objects, monkeypatch):
    """The buckets bound to the store under test, under a database named `qa_a`."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/qa_a")
    monkeypatch.setattr(store, "object_store", lambda: objects)
    monkeypatch.setattr(bucket_module, "_COUNTS", {})
    return objects


class Statements(DocumentsBucket):
    """A documents bucket a deployment renamed."""

    name = "statements"


class Retained(ArchiveBucket):
    """The archive bucket a deployment renamed."""

    name = "archive-eu"


def test_a_put_is_read_back_and_a_missing_key_is_none(objects) -> None:
    """A put is read back and a missing key is none."""
    objects.put("statements", "a/b", b"Kontoauszug", content_type="text/plain")

    assert objects.get("statements", "a/b") == b"Kontoauszug"
    assert objects.get("statements", "a/c") is None
    assert objects.exists("statements", "a/b")
    assert not objects.exists("statements", "a/c")


def test_a_delete_is_silent_about_a_key_that_is_not_there(objects) -> None:
    """A delete is silent about a key that is not there."""
    objects.put("statements", "k", b"x", content_type="text/plain")

    objects.delete("statements", "k")
    objects.delete("statements", "k")

    assert not objects.exists("statements", "k")


def test_a_copy_reports_a_missing_source_and_keeps_the_original(objects) -> None:
    """A copy reports a missing source and keeps the original."""
    objects.put("statements", "k", "relevé".encode(), content_type="text/plain")

    assert objects.copy("statements", "k", "archive-eu", "k@1") is True
    assert objects.copy("statements", "gone", "archive-eu", "gone@1") is False
    assert objects.get("archive-eu", "k@1") == "relevé".encode()
    assert objects.get("statements", "k") == "relevé".encode()


def test_a_listing_takes_the_prefix_and_every_page(objects) -> None:
    """A listing takes the prefix and every page."""
    for number in range(5):
        objects.put("statements", f"qa_a/{number}", b"x", content_type="text/plain")
    objects.put("statements", "qa_b/0", b"yy", content_type="text/plain")

    held = objects.listed("statements", "qa_a/")

    assert [one.key for one in held] == [f"qa_a/{n}" for n in range(5)]
    assert {one.size for one in held} == {1}
    assert len(objects.listed("statements")) == 6


def test_delete_many_removes_what_it_names(objects) -> None:
    """Delete many removes what it names."""
    for key in ("a", "b", "c"):
        objects.put("statements", key, b"x", content_type="text/plain")

    objects.delete_many("statements", ["a", "c"])

    assert [one.key for one in objects.listed("statements")] == ["b"]


def test_a_bucket_is_asked_of_by_name_and_never_by_listing_the_account(objects) -> None:
    """The stand-in refuses ListBuckets, as it is refused to a bucket-scoped credential."""
    assert objects.has_bucket("statements") is True
    assert objects.has_bucket("never-made") is False


def test_a_refused_bulk_delete_is_raised() -> None:
    """A refused bulk delete is raised."""
    client = FakeS3Client(BUCKETS)
    client.delete_objects = lambda **_: {
        "Errors": [{"Key": "k", "Code": "AccessDenied"}]
    }  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="AccessDenied"):
        S3Store(client).delete_many("statements", ["k"])


def test_a_put_goes_to_the_configured_bucket_under_the_databases_prefix(bound) -> None:
    """A put goes to the configured bucket under the databases prefix."""
    key = Statements.key_for("ab" * 32, "application/pdf")

    Statements().put(key, b"%PDF", content_type="application/pdf")

    assert bound.get("statements", f"qa_a/{key}") == b"%PDF"
    assert Statements().get(key) == b"%PDF"
    assert Statements().count() == 1


def test_a_bare_key_from_before_prefixes_is_read_and_never_deleted(bound) -> None:
    """A bare key from before prefixes is read and never deleted."""
    key = Statements.key_for("cd" * 32, "application/pdf")
    bound.put("statements", key, b"old", content_type="application/pdf")

    assert Statements().find(key) == b"old"
    assert Statements().remove(key) is False
    assert bound.exists("statements", key)
    with pytest.raises(FileNotFoundError):
        Statements().get(key + "x")


def test_the_archive_takes_holds_gives_back_and_purges(bound) -> None:
    """The archive takes holds gives back and purges."""
    key = Statements.key_for("ef" * 32, "application/pdf")
    Statements().put(key, b"%PDF", content_type="application/pdf")
    archive = Retained()

    assert archive.take("statements", key) is True
    assert Statements().find(key) is None
    assert [name.split("@")[0] for name, _ in archive.held()] == [f"statements/{key}"]

    assert archive.give_back("statements", key) is True
    assert Statements().get(key) == b"%PDF"

    assert archive.purge() == 1
    assert archive.held() == []


def test_status_finds_the_configured_buckets_without_listing_the_account(
    bound, monkeypatch
) -> None:
    """Status finds the configured buckets without listing the account."""
    from api import status

    monkeypatch.setattr(status, "_REQUIRED_BUCKETS", (Statements, Retained))

    found = status.StatusService._object_store()

    assert found.ok is True, found.detail
    assert found.metrics == {"statements": 0, "archive-eu": 0}


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("", {"documents": "documents", "archive": "archive"}),
        ("documents,parsed,models,export,archive", {"documents": "documents"}),
        (
            "documents=acme-docs, archive=acme-held",
            {"documents": "acme-docs", "archive": "acme-held", "parsed": "parsed"},
        ),
    ],
)
def test_s3_buckets_names_each_role_and_an_unnamed_role_keeps_its_own(
    given, expected
) -> None:
    """S3 buckets names each role and an unnamed role keeps its own."""
    names = store.bucket_names({"S3_BUCKETS": given})

    assert set(names) == set(store.ROLES)
    assert expected.items() <= names.items()


@pytest.mark.parametrize("given", ["documents=", "=docs", "documents=a=b"])
def test_a_malformed_s3_buckets_entry_is_refused(given) -> None:
    """A malformed s3 buckets entry is refused."""
    with pytest.raises(ValueError, match="S3_BUCKETS"):
        store.bucket_names({"S3_BUCKETS": given})


def test_an_unknown_adapter_is_refused(monkeypatch) -> None:
    """An unknown adapter is refused."""
    monkeypatch.setenv("OBJECT_STORE", "elsewhere")

    with pytest.raises(ValueError, match="OBJECT_STORE"):
        store.object_store()
