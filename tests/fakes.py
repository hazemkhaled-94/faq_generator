"""In-memory stand-ins for the components behind a port, shared by the contract suites.

Each fake keeps to the port's own words, so a suite written against the port
runs unchanged against it and against today's adapter. `FakeS3Client` is the
one that is not a port's fake: it stands in for boto3's client, so the real
`S3Store` can be run without a container.
"""

from __future__ import annotations

import io
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from botocore.exceptions import ClientError

from blob_store.store import Entry


class FakeObjectStore:
    """The `ObjectStore` port over a dict.

    `buckets` is what the store holds; a bucket that is not in it is absent.
    The port has no account-wide bucket list, so nothing here offers one.
    """

    def __init__(
        self, buckets: Mapping[str, Mapping[str, bytes]] | None = None
    ) -> None:
        self.buckets: dict[str, dict[str, bytes]] = {
            name: dict(held) for name, held in (buckets or {}).items()
        }
        self.metadata: dict[tuple[str, str], dict[str, str]] = {}
        self._clock = datetime(2026, 1, 1, tzinfo=UTC)
        self._written: dict[tuple[str, str], datetime] = {}

    def _held(self, bucket: str) -> dict[str, bytes]:
        """Held."""
        if bucket not in self.buckets:
            raise ClientError({"Error": {"Code": "NoSuchBucket"}}, "Op")
        return self.buckets[bucket]

    def _stamp(self, bucket: str, key: str) -> None:
        """Stamp."""
        self._clock += timedelta(seconds=1)
        self._written[(bucket, key)] = self._clock

    def put(self, bucket, key, data, *, content_type, metadata=None) -> None:
        """See `ObjectStore.put`."""
        self._held(bucket)[key] = data
        self.metadata[(bucket, key)] = dict(metadata or {})
        self._stamp(bucket, key)

    def get(self, bucket, key):
        """See `ObjectStore.get`."""
        return self._held(bucket).get(key)

    def exists(self, bucket, key) -> bool:
        """See `ObjectStore.exists`."""
        return key in self._held(bucket)

    def delete(self, bucket, key) -> None:
        """See `ObjectStore.delete`."""
        self._held(bucket).pop(key, None)

    def copy(self, bucket, key, to_bucket, to_key) -> bool:
        """See `ObjectStore.copy`."""
        data = self._held(bucket).get(key)
        if data is None:
            return False
        self._held(to_bucket)[to_key] = data
        self._stamp(to_bucket, to_key)
        return True

    def listed(self, bucket, prefix=""):
        """See `ObjectStore.listed`."""
        return [
            Entry(key, len(data), self._written.get((bucket, key), self._clock))
            for key, data in sorted(self._held(bucket).items())
            if key.startswith(prefix)
        ]

    def delete_many(self, bucket, keys) -> None:
        """See `ObjectStore.delete_many`."""
        for key in keys:
            self._held(bucket).pop(key, None)

    def has_bucket(self, bucket) -> bool:
        """See `ObjectStore.has_bucket`."""
        return bucket in self.buckets


class FakeS3Client:
    """The part of boto3's S3 client `S3Store` calls, over a dict.

    `list_buckets` is refused, as it is to a credential scoped to one bucket,
    so a caller that lists the account's buckets fails here as it does there.
    """

    def __init__(
        self, buckets: Mapping[str, Mapping[str, bytes]] | None = None
    ) -> None:
        self._inner = FakeObjectStore(buckets)

    @staticmethod
    def _error(code: str, operation: str) -> ClientError:
        """Error."""
        return ClientError({"Error": {"Code": code}}, operation)

    def list_buckets(self):
        """See `ObjectStore.list_buckets`."""
        raise self._error("AccessDenied", "ListBuckets")

    def head_bucket(self, Bucket):
        """See `ObjectStore.head_bucket`."""
        if not self._inner.has_bucket(Bucket):
            raise self._error("404", "HeadBucket")

    def put_object(self, Bucket, Key, Body, ContentType, Metadata):
        """See `ObjectStore.put_object`."""
        self._inner.put(Bucket, Key, Body, content_type=ContentType, metadata=Metadata)

    def get_object(self, Bucket, Key):
        """See `ObjectStore.get_object`."""
        data = self._inner.get(Bucket, Key)
        if data is None:
            raise self._error("NoSuchKey", "GetObject")
        return {"Body": io.BytesIO(data)}

    def head_object(self, Bucket, Key):
        """See `ObjectStore.head_object`."""
        if not self._inner.exists(Bucket, Key):
            raise self._error("404", "HeadObject")

    def delete_object(self, Bucket, Key):
        """See `ObjectStore.delete_object`."""
        self._inner.delete(Bucket, Key)

    def copy_object(self, Bucket, Key, CopySource):
        """See `ObjectStore.copy_object`."""
        if not self._inner.copy(CopySource["Bucket"], CopySource["Key"], Bucket, Key):
            raise self._error("NoSuchKey", "CopyObject")

    def delete_objects(self, Bucket, Delete):
        """See `ObjectStore.delete_objects`."""
        self._inner.delete_many(Bucket, [one["Key"] for one in Delete["Objects"]])
        return {}

    def get_paginator(self, name):
        """See `ObjectStore.get_paginator`."""
        assert name == "list_objects_v2"
        inner = self._inner

        class Pages:
            """Pages."""

            def paginate(self, Bucket, Prefix=""):
                """See `ObjectStore.paginate`."""
                entries = inner.listed(Bucket, Prefix)
                half = max(1, len(entries) // 2)
                for start in range(0, max(len(entries), 1), half):
                    yield {
                        "Contents": [
                            {"Key": e.key, "Size": e.size, "LastModified": e.modified}
                            for e in entries[start : start + half]
                        ]
                    }

        return Pages()
