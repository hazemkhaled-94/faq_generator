"""The archive bucket."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

from blob_store.s3.bucket import Bucket
from blob_store.s3.client import s3_client

#: How many keys one delete request carries. The S3 limit.
_BATCH = 1000


class ArchiveBucket(Bucket):
    """What a deletion took out of another bucket, until somebody purges it.

    One bucket for all four rather than an archive beside each, because
    the retention is the same wherever the object came from: it is held
    until a person says otherwise. A key carries the bucket it came out of,
    so the origin is not lost by being kept here, and when it was taken, so
    a second deletion of the same key keeps a second copy.
    """

    name: ClassVar[str] = "archive"

    @classmethod
    def key_for(cls, origin: str, key: str) -> str:
        """Builds the prefix every archived copy of an object out of `origin` has.

        A copy taken before copies were stamped is keyed by the prefix alone.
        """
        return f"{origin}/{key}"

    def take(self, origin: str, key: str) -> bool:
        """Moves an object out of `origin` and into the archive.

        Copied and then deleted, in that order: a failure between the two
        leaves the object in both places, which is recoverable, and the
        other order loses it.

        Args:
            origin: The bucket the object is in.
            key: Its key there.

        Returns:
            Whether there was an object to move.

        Raises:
            botocore.exceptions.ClientError: If the store answered with
                anything other than "no such key".
        """
        client = s3_client()
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        target = self.scoped(f"{self.key_for(origin, key)}@{stamp}")
        # The database's own object is moved. A bare key from before keys were
        # prefixed is only copied, because another database may be reading it,
        # unless it names this database (`topics/<database>/...`): then it is
        # this database's alone and moves, or a deleted fit's figure would go
        # on being served from it.
        own = key.startswith(f"topics/{self.database_name()}/")
        for source, move in ((self.scoped(key), True), (key, own)):
            try:
                client.copy_object(
                    Bucket=self.name,
                    Key=target,
                    CopySource={"Bucket": origin, "Key": source},
                )
            except client.exceptions.ClientError as exc:
                if not self._absent(exc):
                    raise
                continue
            if move:
                client.delete_object(Bucket=origin, Key=source)
            return True
        return False

    def give_back(self, origin: str, key: str) -> bool:
        """Copies an archived object back into `origin`, unless one is there.

        The newest copy, by when the store wrote it and then by its stamp.
        The archived copies stay.

        Args:
            origin: The bucket the object was taken from.
            key: Its key there.

        Returns:
            Whether `origin` holds the object now.

        Raises:
            botocore.exceptions.ClientError: If the store answered with
                anything other than "no such key".
        """
        client = s3_client()
        try:
            client.head_object(Bucket=origin, Key=self.scoped(key))
            return True
        except client.exceptions.ClientError as exc:
            if not self._absent(exc):
                raise
        prefix = self.scoped(self.key_for(origin, key))
        copies = [
            entry
            for page in client.get_paginator("list_objects_v2").paginate(
                Bucket=self.name, Prefix=prefix
            )
            for entry in page.get("Contents", [])
            if entry["Key"] == prefix or entry["Key"].startswith(f"{prefix}@")
        ]
        if not copies:
            return False
        newest = max(copies, key=lambda entry: (entry["LastModified"], entry["Key"]))
        try:
            client.copy_object(
                Bucket=origin,
                Key=self.scoped(key),
                CopySource={"Bucket": self.name, "Key": newest["Key"]},
            )
        except client.exceptions.ClientError as exc:
            if self._absent(exc):
                return False
            raise
        return True

    def held(self, *, before: datetime | None = None) -> list[tuple[str, int]]:
        """Lists what the database's part of the archive holds, as (key, bytes).

        The keys are as `get` takes them, without the database's prefix.

        Args:
            before: Only objects last written before this, or all of them.
        """
        prefix = self.scoped("")
        return [
            (entry["Key"].removeprefix(prefix), entry["Size"])
            for page in s3_client()
            .get_paginator("list_objects_v2")
            .paginate(Bucket=self.name, Prefix=prefix)
            for entry in page.get("Contents", [])
            if before is None or entry["LastModified"] < before
        ]

    def purge(self, *, before: datetime | None = None) -> int:
        """Deletes what the database's part of the archive holds. Irreversible.

        Only this database's prefix: another database's copies are its own
        second deletion to make.

        Args:
            before: Only objects last written before this, or all of them.

        Returns:
            How many objects were deleted.

        Raises:
            RuntimeError: If the store refused to delete any of them, which
                it reports in the body of a successful answer.
        """
        keys = [key for key, _ in self.held(before=before)]
        client = s3_client()
        for start in range(0, len(keys), _BATCH):
            answer = client.delete_objects(
                Bucket=self.name,
                Delete={
                    "Objects": [
                        {"Key": self.scoped(key)}
                        for key in keys[start : start + _BATCH]
                    ]
                },
            )
            if errors := answer.get("Errors"):
                raise RuntimeError(
                    f"the store refused to delete {len(errors)} archived object(s), "
                    f"first {errors[0].get('Key')}: {errors[0].get('Code')}"
                )
        return len(keys)
