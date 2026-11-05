"""What every object store adapter does, run against each one there is.

The adapters are `S3Store` over a stand-in for boto3's client (today's, with
no container) and an in-memory fake. An Azure Blob Storage adapter joins the
list by being added to `STORES`. The port-level cases also run against a real
SeaweedFS gateway, marked `integration`; the bucket classes are covered against
it by `tests/integration/blob`.
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


@pytest.fixture(
    params=["fake", "s3", pytest.param("gateway", marks=pytest.mark.integration)]
)
def objects(request):
    """The port's objects: two with no container, and the real gateway where there is one.

    The gateway runs the same cases over `S3Store` and a SeaweedFS the
    integration fixtures start, in the buckets that gateway has; CI runs it
    with the other integration tests and a unit run leaves it out.
    """
    if request.param == "gateway":
        request.getfixturevalue("buckets")
        from blob_store.s3.client import s3_client

        return S3Store(s3_client())
    return STORES[request.param]()


@pytest.fixture
def names(request) -> tuple[str, str]:
    """The two buckets the port-level cases use: the gateway's own, or the stand-ins'."""
    if request.node.callspec.params.get("objects") == "gateway":
        return ("documents", "archive")
    return ("statements", "archive-eu")


@pytest.fixture(params=sorted(STORES))
def local(request):
    """The stores that need no container, for the cases that name buckets of their own."""
    return STORES[request.param]()


@pytest.fixture
def bound(local, monkeypatch):
    """The buckets bound to the store under test, under a database named `qa_a`."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/qa_a")
    monkeypatch.setattr(store, "object_store", lambda: local)
    monkeypatch.setattr(bucket_module, "_COUNTS", {})
    return local


class Statements(DocumentsBucket):
    """A documents bucket a deployment renamed."""

    name = "statements"


class Retained(ArchiveBucket):
    """The archive bucket a deployment renamed."""

    name = "archive-eu"


def test_a_put_is_read_back_and_a_missing_key_is_none(objects, names) -> None:
    """A put is read back and a missing key is none."""
    main, _ = names
    objects.put(main, "a/b", b"Kontoauszug", content_type="text/plain")

    assert objects.get(main, "a/b") == b"Kontoauszug"
    assert objects.get(main, "a/c") is None
    assert objects.exists(main, "a/b")
    assert not objects.exists(main, "a/c")


def test_a_delete_is_silent_about_a_key_that_is_not_there(objects, names) -> None:
    """A delete is silent about a key that is not there."""
    main, _ = names
    objects.put(main, "k", b"x", content_type="text/plain")

    objects.delete(main, "k")
    objects.delete(main, "k")

    assert not objects.exists(main, "k")


def test_a_copy_reports_a_missing_source_and_keeps_the_original(objects, names) -> None:
    """A copy reports a missing source and keeps the original."""
    main, other = names
    objects.put(main, "k", "relevé".encode(), content_type="text/plain")

    assert objects.copy(main, "k", other, "k@1") is True
    assert objects.copy(main, "gone", other, "gone@1") is False
    assert objects.get(other, "k@1") == "relevé".encode()
    assert objects.get(main, "k") == "relevé".encode()


def test_a_listing_takes_the_prefix_and_every_page(objects, names) -> None:
    """A listing takes the prefix and every page."""
    main, _ = names
    for number in range(5):
        objects.put(main, f"qa_a/{number}", b"x", content_type="text/plain")
    objects.put(main, "qa_b/0", b"yy", content_type="text/plain")

    held = objects.listed(main, "qa_a/")

    assert [one.key for one in held] == [f"qa_a/{n}" for n in range(5)]
    assert {one.size for one in held} == {1}
    assert len(objects.listed(main)) == 6


def test_delete_many_removes_what_it_names(objects, names) -> None:
    """Delete many removes what it names."""
    main, _ = names
    # Under a prefix of their own: SeaweedFS keeps the directory `a` another
    # case's `a/b` leaves, and refuses a file `a` there with an InternalError
    for key in ("many/a", "many/b", "many/c"):
        objects.put(main, key, b"x", content_type="text/plain")

    objects.delete_many(main, ["many/a", "many/c"])

    assert [one.key for one in objects.listed(main)] == ["many/b"]


def test_a_bucket_is_asked_of_by_name_and_never_by_listing_the_account(
    objects, names
) -> None:
    """The stand-in refuses ListBuckets, as it is refused to a bucket-scoped credential."""
    main, _ = names
    assert objects.has_bucket(main) is True
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


@pytest.mark.parametrize(
    ("given", "roles", "bucket"),
    [
        (
            "documents=bank-faq,parsed=bank-faq,archive=bank-faq",
            "documents",
            "bank-faq",
        ),
        ("documents=shop, archive=shop", "documents", "shop"),
        ("parsed=archive", "parsed", "archive"),  # clashes with a default name
        ("archive=Amt für Soziales,models=Amt für Soziales", "archive", "Amt für"),
    ],
)
def test_two_roles_on_one_bucket_are_refused_naming_both_and_the_bucket(
    given, roles, bucket
) -> None:
    """A bucket shared with a live role is refused.

    An archive purge deletes every key of the database in the archive's bucket,
    live documents included.
    """
    with pytest.raises(ValueError, match="each role needs its own") as caught:
        store.bucket_names({"S3_BUCKETS": given})

    assert roles in str(caught.value)
    assert bucket in str(caught.value)


@pytest.mark.parametrize("given", [None, ""])
def test_unset_or_empty_names_the_s3_adapter(monkeypatch, given) -> None:
    """Compose hands an unset name over empty, and both read as `s3`."""
    from blob_store.s3 import client as s3_module

    if given is None:
        monkeypatch.delenv("OBJECT_STORE", raising=False)
    else:
        monkeypatch.setenv("OBJECT_STORE", given)
    monkeypatch.setattr(s3_module, "s3_client", lambda: "client")
    monkeypatch.setattr(s3_module, "S3Store", lambda client: ("s3", client))

    assert store.object_store() == ("s3", "client")


def test_an_unknown_adapter_is_refused(monkeypatch) -> None:
    """An unknown adapter is refused."""
    monkeypatch.setenv("OBJECT_STORE", "elsewhere")

    with pytest.raises(ValueError, match="OBJECT_STORE"):
        store.object_store()


def test_a_backup_restored_into_another_store_gives_the_manifests_keys_and_digests(
    monkeypatch, tmp_path
) -> None:
    """Backup and restore go through the port, so they work against any store."""
    import hashlib

    from archive import backup

    source = FakeObjectStore(BUCKETS)
    source.put("statements", "qa_a/ab", b"Kontoauszug", content_type="text/plain")
    source.put("archive-eu", "qa_a/statements/ab@1", b"x", content_type="text/plain")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/qa_a")
    monkeypatch.setattr(store, "object_store", lambda: source)
    monkeypatch.setattr(backup, "_counts", dict)
    monkeypatch.setattr(
        backup,
        "bucket_names",
        lambda: {"documents": "statements", "archive": "archive-eu"},
    )

    manifest = backup.backup(tmp_path)

    assert {(o["bucket"], o["key"]) for o in manifest["objects"]} == {
        ("statements", "qa_a/ab"),
        ("archive-eu", "qa_a/statements/ab@1"),
    }
    assert {o["sha256"] for o in manifest["objects"]} >= {
        hashlib.sha256(b"Kontoauszug").hexdigest()
    }

    target = FakeObjectStore(BUCKETS)
    monkeypatch.setattr(store, "object_store", lambda: target)
    backup.restore(tmp_path, stack=True)

    assert backup.verify(tmp_path, stack=True) == []
    assert target.get("statements", "qa_a/ab") == b"Kontoauszug"
