"""The archive bucket."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

from blob_store import store
from blob_store.s3.bucket import Bucket
from blob_store.store import bucket_name

#: How a copy's key says when it was taken.
_STAMP = "%Y%m%dT%H%M%S.%fZ"


def _stamp(suffix: str) -> datetime | None:
    """When a copy was taken, read from the `@stamp` of its key, or None."""
    try:
        return datetime.strptime(suffix.removeprefix("@"), _STAMP).replace(tzinfo=UTC)
    except ValueError:
        return None


class ArchiveBucket(Bucket):
    """What a deletion took out of another bucket, until somebody purges it.

    One bucket for all four rather than an archive beside each, because
    the retention is the same wherever the object came from: it is held
    until a person says otherwise. A key carries the bucket it came out of,
    so the origin is not lost by being kept here, and when it was taken, so
    a second deletion of the same key keeps a second copy.
    """

    name: ClassVar[str] = bucket_name("archive")

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
            Exception: Whatever the store raises for anything other than "no
                such key".
        """
        objects = store.object_store()
        stamp = datetime.now(UTC).strftime(_STAMP)
        target = self.scoped(f"{self.key_for(origin, key)}@{stamp}")
        # The database's own object is moved. A bare key from before keys were
        # prefixed is only copied, because another database may be reading it,
        # unless it names this database (`topics/<database>/...`): then it is
        # this database's alone and moves, or a deleted fit's figure would go
        # on being served from it.
        own = key.startswith(f"topics/{self.database_name()}/")
        for source, move in ((self.scoped(key), True), (key, own)):
            if not objects.copy(origin, source, self.name, target):
                continue
            if move:
                objects.delete(origin, source)
            return True
        return False

    def give_back(self, origin: str, key: str, near: datetime | None = None) -> bool:
        """Copies an archived object back into `origin`, unless one is there.

        The newest copy, by when the store wrote it and then by its stamp, which
        is what a rollback of a failed delete wants. With `near`, the copy
        stamped nearest that time, which is what a restore of a chosen deletion
        wants: a later deletion of the same key archived a later copy. A copy
        taken before copies were stamped is chosen only where none is stamped.
        The archived copies stay.

        Args:
            origin: The bucket the object was taken from.
            key: Its key there.
            near: When the deletion to put back archived it, or None for the
                newest copy.

        Returns:
            Whether `origin` holds the object now.

        Raises:
            Exception: Whatever the store raises for anything other than "no
                such key".
        """
        objects = store.object_store()
        if objects.exists(origin, self.scoped(key)):
            return True
        prefix = self.scoped(self.key_for(origin, key))
        copies = [
            entry
            for entry in objects.listed(self.name, prefix)
            if entry.key == prefix or entry.key.startswith(f"{prefix}@")
        ]
        if not copies:
            return False
        chosen = max(copies, key=lambda entry: (entry.modified, entry.key))
        if near is not None:
            stamped = [
                (taken, entry)
                for entry in copies
                if (taken := _stamp(entry.key.removeprefix(prefix))) is not None
            ]
            if stamped:
                chosen = min(stamped, key=lambda one: (abs(one[0] - near), one[1].key))[
                    1
                ]
        return objects.copy(self.name, chosen.key, origin, self.scoped(key))

    def held(self, *, before: datetime | None = None) -> list[tuple[str, int]]:
        """Lists what the database's part of the archive holds, as (key, bytes).

        The keys are as `get` takes them, without the database's prefix.

        Args:
            before: Only objects last written before this, or all of them.
        """
        prefix = self.scoped("")
        return [
            (entry.key.removeprefix(prefix), entry.size)
            for entry in store.object_store().listed(self.name, prefix)
            if before is None or entry.modified < before
        ]

    def purge(
        self,
        *,
        before: datetime | None = None,
        held: list[tuple[str, int]] | None = None,
    ) -> int:
        """Deletes what the database's part of the archive holds. Irreversible.

        Only this database's prefix: another database's copies are its own
        second deletion to make.

        Args:
            before: Only objects last written before this, or all of them.
            held: A listing taken earlier, as `held` returns it, to delete
                exactly those and not what was archived since. The store's
                modification times are whole seconds, so a moment cannot
                tell an object written just after it from one written just
                before.

        Returns:
            How many objects were deleted.

        Raises:
            RuntimeError: If the store refused to delete any of them.
        """
        keys = [key for key, _ in (self.held(before=before) if held is None else held)]
        store.object_store().delete_many(self.name, [self.scoped(key) for key in keys])
        return len(keys)
