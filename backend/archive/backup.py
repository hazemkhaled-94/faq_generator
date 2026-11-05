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
import os
import stat
import sys
from pathlib import Path

from sqlalchemy import text

import telemetry
from blob_store import store
from blob_store.s3 import Bucket, rekey
from blob_store.store import bucket_names
from database.qa_generator import Base, engine

log = logging.getLogger(__name__)

MANIFEST = "manifest.json"

#: What a backup's folders and files may be read by: their owner alone. A
#: backup holds every customer document, its parse and the archive, whatever
#: umask the operator's shell has.
_PRIVATE = 0o077


def _sha256(data: bytes) -> str:
    """The hex digest of some bytes."""
    return hashlib.sha256(data).hexdigest()


def _buckets() -> list[str]:
    """The configured buckets the store holds, each asked of by its own name."""
    objects = store.object_store()
    return [one for one in bucket_names().values() if objects.has_bucket(one)]


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


def _local(directory: Path, bucket: str, key: str) -> Path | None:
    """Where an object lives in the backup, or None when its key leads out of it.

    A key is whatever wrote it to the store, and the manifest is a file: an
    empty, `.` or `..` part, or a leading `/`, would name a file anywhere the
    operator can write or read, or alias another object's file. The folder
    allowed is built from the directory the operator named, unresolved, so a
    `s3` entry that is a symlink does not move it.
    """
    parts = key.split("/")
    if bucket in ("", ".", "..") or "/" in bucket or "\\" in bucket:
        return None
    if any(part in ("", ".", "..") for part in parts):
        return None
    allowed = directory.resolve() / "s3" / bucket
    path = allowed.joinpath(*parts)
    try:
        return path if path.resolve().is_relative_to(allowed) else None
    except (OSError, ValueError):  # a NUL, a loop of links, a name too long
        return None


def _read(path: Path) -> bytes | None:
    """A backup file's bytes, or None for a link, a non-regular file or a hard link.

    Opened without following a link, so a file swapped for one after the check
    is not read.
    """
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except (OSError, ValueError):
        return None
    with os.fdopen(descriptor, "rb") as handle:
        found = os.fstat(handle.fileno())
        if not stat.S_ISREG(found.st_mode) or found.st_nlink > 1:
            return None
        return handle.read()


def _layout(directory: Path) -> str | None:
    """What is wrong with the folders of a backup, or None.

    `s3` and each bucket folder in it must be real folders inside the
    directory: a link would move where the objects are written or read.
    """
    folder = directory / "s3"
    if not folder.exists() and not folder.is_symlink():
        return None
    for one in (folder, *(sorted(folder.iterdir()) if folder.is_dir() else ())):
        if one.is_symlink() or not one.is_dir():
            return f"{one} is a link or not a folder"
    return None


def _in_scope(bucket: str, key: str, stack: bool, held: set[str]) -> bool:
    """Whether a key is one this restore may touch: this database's own, or any on a stack restore.

    A bare key from before keys carried the database is touched too when this
    database's rows name it, by the ownership `make s3-prefix` uses: a
    content-addressed key is the same bytes whoever wrote it, and a topic key
    names its database. Another database's bare keys are only a stack
    restore's.
    """
    database = Bucket.database_name()
    return (
        stack
        or key.startswith(f"{database}/")
        or (rekey.is_bare(bucket, key, database) and rekey.named(bucket, key, held))
    )


def backup(directory: Path) -> dict:
    """Copies every object of every bucket under the directory, and writes the manifest.

    Returns:
        The manifest, naming under `left_out` any object it could not copy.
    """
    source = store.object_store()
    objects = []
    left_out = []
    for bucket in _buckets():
        for held in source.listed(bucket):
            data = source.get(bucket, held.key)
            if data is None:
                continue
            target = _local(directory, bucket, held.key)
            if target is None:
                log.error(
                    "not backed up: %s/%s leads out of the backup", bucket, held.key
                )
                left_out.append(f"{bucket}/{held.key}")
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            except (OSError, ValueError) as refused:
                # A NUL in a key, a file and a folder on one path, a name too long.
                log.error("not backed up: %s/%s: %s", bucket, held.key, refused)
                left_out.append(f"{bucket}/{held.key}")
                continue
            objects.append(
                {
                    "bucket": bucket,
                    "key": held.key,
                    "bytes": len(data),
                    "sha256": _sha256(data),
                }
            )
    manifest = {
        "rows": _counts(),
        "objects": objects,
        "dumps": _dumps(directory),
    }
    if left_out:
        manifest["left_out"] = left_out
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
    target = store.object_store()
    owned = set() if stack else rekey.digests()
    for held in json.loads((directory / MANIFEST).read_text())["objects"]:
        if not _in_scope(held["bucket"], held["key"], stack, owned):
            continue
        path = _local(directory, held["bucket"], held["key"])
        if path is None:
            log.error(
                "not restored: %s/%s leads out of the backup",
                held["bucket"],
                held["key"],
            )
            continue
        data = _read(path)
        if data is None:
            log.error(
                "not restored: %s/%s is not a plain file of the backup",
                held["bucket"],
                held["key"],
            )
            continue
        target.put(
            held["bucket"],
            held["key"],
            data,
            content_type="application/octet-stream",
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
    source = store.object_store()
    owned = set() if stack else rekey.digests()
    for held in manifest["objects"]:
        if not _in_scope(held["bucket"], held["key"], stack, owned):
            continue
        if _local(directory, held["bucket"], held["key"]) is None:
            wrong.append(f"{held['bucket']}/{held['key']} leads out of the backup")
            continue
        data = source.get(held["bucket"], held["key"])
        if data is None:
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
        0, 1 when a restore or verification found a difference or a backup left
        an object out, or 2 when the directory cannot be backed up into or read
        as a backup (`s3` or a bucket folder in it is a link or not a folder).
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
    telemetry.configure("backup")
    chosen = Path(args.backup or args.restore or args.verify)
    if (wrong_layout := _layout(chosen)) is not None:
        log.error(
            "%s cannot be %s: %s",
            chosen,
            "backed up into" if args.backup else "read as a backup",
            wrong_layout,
        )
        return 2

    if args.backup:
        directory = Path(args.backup)
        if (directory / MANIFEST).exists():
            log.error("%s already holds a backup; use an empty directory", directory)
            return 2
        before = os.umask(_PRIVATE)
        try:
            for folder in (directory, directory / "db"):
                folder.mkdir(parents=True, exist_ok=True)
                folder.chmod(0o700)
            made = backup(directory)
        finally:
            os.umask(before)
        if made.get("left_out"):
            log.error("%d object(s) left out of the backup", len(made["left_out"]))
            return 1
        return 0
    directory = Path(args.restore or args.verify)
    if args.restore:
        restore(directory, args.stack)
    wrong = verify(directory, args.stack)
    for line in wrong:
        log.error("%s", line)
    if wrong:
        log.info("%d difference(s)", len(wrong))
    else:
        log.info("the backup matches")
    return 1 if wrong else 0


if __name__ == "__main__":
    raise SystemExit(main())
