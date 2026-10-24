"""Copies the objects a store holds from before keys were prefixed under a database's prefix.

Run once per database that was using the store, with that database's
DATABASE_URL. Copies, never moves: another database may still be reading the
bare key, which `get` falls back to.
"""

from __future__ import annotations

import logging
import re
import sys

from blob_store.s3.bucket import Bucket
from blob_store.s3.client import s3_client

log = logging.getLogger(__name__)

#: A content-addressed key: two hex fanout directories, then the digest.
_FANOUT = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{2}/")

#: The buckets an archived copy's key can name as its origin.
_ORIGINS = ("documents", "parsed", "models", "export")


def is_bare(bucket: str, key: str, database: str) -> bool:
    """Whether a key is one of this database's from before keys were prefixed.

    A fanout key belongs to every database that holds the digest. A topic
    key names its database, so only the one named is copied. In the archive,
    an origin bucket's name leads the key.
    """
    if bucket == "archive":
        origin, _, rest = key.partition("/")
        return origin in _ORIGINS and is_bare(origin, rest, database)
    if bucket in ("models", "export"):
        return key.startswith(f"topics/{database}/")
    return bool(_FANOUT.match(key))


def main() -> int:
    """Copies every bare key of this database under its prefix, and reports the count."""
    database = Bucket.database_name()
    client = s3_client()
    copied = 0
    for bucket in ("documents", "parsed", "models", "export", "archive"):
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            for entry in page.get("Contents", []):
                key = entry["Key"]
                if not is_bare(bucket, key, database):
                    continue
                client.copy_object(
                    Bucket=bucket,
                    Key=f"{database}/{key}",
                    CopySource={"Bucket": bucket, "Key": key},
                )
                copied += 1
    log.info("copied %d object(s) under %s/", copied, database)
    print(f"copied {copied} object(s) under {database}/ (the bare keys stay)")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
