"""Copies the objects a store holds from before keys were prefixed under a database's prefix.

Run once per database that was using the store, with that database's
DATABASE_URL. Copies, never moves: another database may still be reading the
bare key, which `get` falls back to. Copies only the objects this database's
rows name, and never over an object it already holds under its prefix: a
re-parse written since the upgrade is newer than the bare copy.
"""

from __future__ import annotations

import logging
import re
import sys

from sqlalchemy import text

from blob_store import store
from blob_store.s3.bucket import Bucket
from blob_store.store import bucket_names
from database.qa_generator import engine

log = logging.getLogger(__name__)

#: A content-addressed key: two hex fanout directories, then the digest.
_FANOUT = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{2}/")

#: The digest in a content-addressed key.
_DIGEST = re.compile(r"[0-9a-f]{64}")

#: The buckets an archived copy's key can name as its origin.
_ORIGINS = ("documents", "parsed", "models", "export")


def _role(bucket: str) -> str:
    """The role of a bucket by its configured name, or the name when it has none."""
    return next((r for r, name in bucket_names().items() if name == bucket), bucket)


def is_bare(bucket: str, key: str, database: str) -> bool:
    """Whether a key is one of this database's from before keys were prefixed.

    A fanout key belongs to every database that holds the digest, which
    `named` then narrows to this database's. A topic key names its database,
    so only the one named is copied. In the archive, an origin bucket's name
    leads the key.
    """
    bucket = _role(bucket)
    if bucket == "archive":
        origin, _, rest = key.partition("/")
        return _role(origin) in _ORIGINS and is_bare(origin, rest, database)
    if bucket in ("models", "export"):
        return key.startswith(f"topics/{database}/")
    return bool(_FANOUT.match(key))


def digests() -> set[str]:
    """The digests of the documents this database holds or has archived."""
    with engine().connect() as connection:
        return set(
            connection.execute(
                text(
                    "SELECT sha256 FROM documents UNION "
                    "SELECT payload->>'sha256' FROM archived_rows "
                    "WHERE table_name = 'documents'"
                )
            ).scalars()
        )


def named(bucket: str, key: str, held: set[str]) -> bool:
    """Whether this database's rows name the object: a topic key names its own database, a digest key a held digest."""
    bucket = _role(bucket)
    if bucket in ("models", "export") or (
        bucket == "archive" and _role(key.partition("/")[0]) in ("models", "export")
    ):
        return True
    found = _DIGEST.search(key)
    return found is not None and found.group() in held


def main() -> int:
    """Copies this database's bare keys under its prefix where it holds none, and reports the count."""
    database = Bucket.database_name()
    objects = store.object_store()
    held = digests()
    copied = 0
    for bucket in bucket_names().values():
        for entry in objects.listed(bucket):
            key = entry.key
            if not is_bare(bucket, key, database) or not named(bucket, key, held):
                continue
            if objects.exists(bucket, f"{database}/{key}"):
                continue
            objects.copy(bucket, key, bucket, f"{database}/{key}")
            copied += 1
    log.info("copied %d object(s) under %s/", copied, database)
    print(f"copied {copied} object(s) under {database}/ (the bare keys stay)")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
