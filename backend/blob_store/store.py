"""The object store as the rest of the backend sees it.

One port, `ObjectStore`, in terms of a bucket name, a key and bytes. Nothing
above it knows an SDK, an endpoint or a status code: an Azure Blob Storage
adapter, one container per bucket, replaces `blob_store.s3.client.S3Store`
and nothing else. `OBJECT_STORE` names the adapter, and `s3` is the only one
there is.

What stays above the port: the database's key prefix, the fall back to a bare
key from before keys were prefixed, and the encoding of metadata. They are
the buckets' own rules and do not change with the provider.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

#: What each bucket is for. The names these roles go by are `bucket_names`.
ROLES = ("documents", "parsed", "models", "export", "archive")


@dataclass(frozen=True)
class Entry:
    """One object a listing returned."""

    key: str
    size: int
    modified: datetime


class ObjectStore(Protocol):
    """What a bucket does with its store.

    A missing object is an answer, not an error: `get` returns None, `exists`
    False, `copy` False. Being unreachable or refused is an exception.
    """

    def put(
        self,
        bucket: str,
        key: str,
        data: bytes,
        *,
        content_type: str,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Stores an object, replacing one of the same key."""
        ...

    def get(self, bucket: str, key: str) -> bytes | None:
        """Reads an object, or None when there is none."""
        ...

    def exists(self, bucket: str, key: str) -> bool:
        """Whether an object is there."""
        ...

    def delete(self, bucket: str, key: str) -> None:
        """Deletes an object. Silent about one that is not there."""
        ...

    def copy(self, bucket: str, key: str, to_bucket: str, to_key: str) -> bool:
        """Copies an object, and returns False when the source is not there."""
        ...

    def listed(self, bucket: str, prefix: str = "") -> list[Entry]:
        """Every object whose key starts with the prefix, whatever the page size."""
        ...

    def delete_many(self, bucket: str, keys: list[str]) -> None:
        """Deletes the keys.

        Raises:
            RuntimeError: If the store refused any of them.
        """
        ...

    def has_bucket(self, bucket: str) -> bool:
        """Whether the named bucket is there, asked of that name alone.

        Never by listing the account's buckets: a credential scoped to one
        bucket is refused the listing.
        """
        ...


def bucket_names(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """The bucket each role is stored in, read from S3_BUCKETS.

    The value is a comma list. An entry is `role=bucket`, or a bare name that
    stands for the role of that name, which is what the file has always held.
    A role not named keeps its own name.

    Raises:
        ValueError: If an entry is empty on either side of its `=`, or has two.
    """
    given: dict[str, str] = {}
    for entry in (
        (os.environ if source is None else source).get("S3_BUCKETS", "").split(",")
    ):
        entry = entry.strip()
        if not entry:
            continue
        role, _, bucket = entry.partition("=")
        if "=" in bucket or not role.strip() or (entry != role and not bucket.strip()):
            raise ValueError(f"S3_BUCKETS entry {entry!r} is not name or role=bucket")
        given[role.strip()] = bucket.strip() or role.strip()
    return {role: given.get(role, role) for role in ROLES}


def bucket_name(role: str) -> str:
    """The configured name of one bucket role."""
    return bucket_names()[role]


def object_store() -> ObjectStore:
    """The adapter OBJECT_STORE names.

    Raises:
        ValueError: If it names none that exists.
    """
    # Empty is unset: compose hands an unset name over as "".
    adapter = os.environ.get("OBJECT_STORE", "").strip() or "s3"
    if adapter == "s3":
        from blob_store.s3.client import S3Store, s3_client

        return S3Store(s3_client())
    raise ValueError(
        f"OBJECT_STORE={adapter!r} names no adapter; the one there is is s3"
    )
