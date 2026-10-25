"""A backup of the object store and a manifest of what the databases held.

`make backup DIR=<dir>` dumps the five databases (Makefile, through the
postgres container, into `<dir>/db`) and then runs this, which copies every
object of every bucket under `<dir>/s3` and writes `<dir>/manifest.json`: the
row count of each table of the application database, and the key, size and
sha256 of every object and every dump. `make restore-backup DIR=<dir>` puts
the application database's dump back and then runs this with `--restore`,
which uploads the objects under this database's prefix and checks them
against the manifest. The buckets, the SeaweedFS filer, Phoenix, Dagster and
Argilla are shared by every database on the stack, so a restore of one
database leaves them alone; `make restore-backup-stack` puts the whole stack
back (`--stack`).

Nothing but databases and objects is copied. `.env`, `provider.env` and the
certificate keys are not in the store, and nothing here reads them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

from sqlalchemy import text

from blob_store.s3 import (
    ArchiveBucket,
    DocumentsBucket,
    ExportBucket,
    ModelsBucket,
    ParsedBucket,
    bucket_names,
    s3_client,
)
from blob_store.s3.bucket import Bucket
from database.qa_generator import Base, engine

log = logging.getLogger(__name__)

MANIFEST = "manifest.json"

#: The buckets this project keeps, by the classes that own them.
_NAMED = [
    bucket.name
    for bucket in (
        DocumentsBucket,
        ParsedBucket,
        ModelsBucket,
        ExportBucket,
        ArchiveBucket,
    )
]


def _sha256(data: bytes) -> str:
    """The hex digest of some bytes."""
    return hashlib.sha256(data).hexdigest()


def _buckets() -> list[str]:
    """The five buckets of this project that the store holds."""
    held = bucket_names()
    return [one for one in _NAMED if one in held]


def _counts() -> dict[str, int]:
    """The rows in each table of the application database."""
    with engine().connect() as connection:
        return {
            table: connection.execute(
                text(f'SELECT count(*) FROM "{table}"')
            ).scalar_one()
            for table in sorted(Base.metadata.tables)
        }


def _dumps(directory: Path) -> dict[str, dict]:
    """The size and sha256 of each database dump in `<dir>/db`."""
    return {
        dump.name: {
            "bytes": dump.stat().st_size,
            "sha256": _sha256(dump.read_bytes()),
        }
        for dump in sorted((directory / "db").glob("*.dump"))
    }


def _in_scope(key: str, stack: bool) -> bool:
    """Whether a key is one this restore may touch: this database's own, or any on a stack restore.

    A bare key from before keys carried the database is shared, so only a
    stack restore puts it back.
    """
    return stack or key.startswith(f"{Bucket.database_name()}/")


def backup(directory: Path) -> dict:
    """Copies every object of every bucket under the directory, and writes the manifest.

    Returns:
        The manifest.
    """
    client = s3_client()
    objects = []
    for bucket in _buckets():
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            for held in page.get("Contents", []):
                data = client.get_object(Bucket=bucket, Key=held["Key"])["Body"].read()
                target = directory / "s3" / bucket / held["Key"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                objects.append(
                    {
                        "bucket": bucket,
                        "key": held["Key"],
                        "bytes": len(data),
                        "sha256": _sha256(data),
                    }
                )
    manifest = {
        "rows": _counts(),
        "objects": objects,
        "dumps": _dumps(directory),
    }
    (directory / MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True))
    log.info(
        "backed up %d object(s), %d dump(s) and the row counts of %d table(s)",
        len(objects),
        len(manifest["dumps"]),
        len(manifest["rows"]),
    )
    return manifest


def restore(directory: Path, stack: bool = False) -> None:
    """Uploads the objects of a backup under their own keys.

    Args:
        directory: A backup.
        stack: Put back every database's objects, not only this database's.
    """
    client = s3_client()
    for held in json.loads((directory / MANIFEST).read_text())["objects"]:
        if not _in_scope(held["key"], stack):
            continue
        client.put_object(
            Bucket=held["bucket"],
            Key=held["key"],
            Body=(directory / "s3" / held["bucket"] / held["key"]).read_bytes(),
        )


def verify(directory: Path, stack: bool = False) -> list[str]:
    """Compares the dumps, the objects and the row counts with the manifest.

    Only this database's objects, unless `stack`: another database's object
    may have been rewritten since the backup, rightly.

    Returns:
        What does not match, empty when everything does.
    """
    manifest = json.loads((directory / MANIFEST).read_text())
    wrong = []
    for name, held in manifest["dumps"].items():
        dump = directory / "db" / name
        if not dump.exists() or _sha256(dump.read_bytes()) != held["sha256"]:
            wrong.append(f"dump {name} differs from the manifest")
    client = s3_client()
    for held in manifest["objects"]:
        if not _in_scope(held["key"], stack):
            continue
        try:
            data = client.get_object(Bucket=held["bucket"], Key=held["key"])[
                "Body"
            ].read()
        except client.exceptions.ClientError:
            wrong.append(f"{held['bucket']}/{held['key']} is missing")
            continue
        if _sha256(data) != held["sha256"]:
            wrong.append(f"{held['bucket']}/{held['key']} differs from the manifest")
    now = _counts()
    for table, rows in manifest["rows"].items():
        if now.get(table) != rows:
            wrong.append(f"{table} holds {now.get(table)} row(s), the manifest {rows}")
    return wrong


def main(argv: list[str] | None = None) -> int:
    """Runs the command line.

    Returns:
        0, 1 when a restore or verification found a difference, or 2 when the
        directory cannot be backed up into.
    """
    built = argparse.ArgumentParser(prog="python -m archive.backup")
    group = built.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--backup", metavar="DIR", help="copy the objects, write the manifest"
    )
    group.add_argument(
        "--restore", metavar="DIR", help="upload the objects, then verify"
    )
    group.add_argument("--verify", metavar="DIR", help="compare with the manifest only")
    built.add_argument(
        "--stack",
        action="store_true",
        help="with --restore or --verify: every database's objects, not only this one's",
    )
    args = built.parse_args(sys.argv[1:] if argv is None else argv)

    if args.backup:
        directory = Path(args.backup)
        if (directory / MANIFEST).exists():
            log.error("%s already holds a backup; use an empty directory", directory)
            return 2
        backup(directory)
        return 0
    directory = Path(args.restore or args.verify)
    if args.restore:
        restore(directory, args.stack)
    wrong = verify(directory, args.stack)
    for line in wrong:
        log.error("%s", line)
    log.info("the backup matches" if not wrong else "%d difference(s)", len(wrong))
    return 1 if wrong else 0


if __name__ == "__main__":
    raise SystemExit(main())
