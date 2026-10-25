"""Command-line entry point for the ingestion service.

The same operations are on the API under /documents. Run with --help for the
flags.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

import telemetry
from database.qa_generator import engine
from ingestion.config import Settings
from ingestion.factory import build_removal, build_service
from ingestion.models import UploadedFile
from settings.runs import run_id
from settings.store import resolved

log = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    """Builds the argument parser. The flags are mutually exclusive."""
    built = argparse.ArgumentParser(prog="python -m ingestion.run")
    group = built.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="list every document")
    group.add_argument(
        "--add",
        metavar="DIR",
        type=Path,
        help="ingest every PDF in a directory, through the service the upload "
        "route uses: one line per file, duplicates by digest reported",
    )
    group.add_argument(
        "--delete",
        metavar="SHA256",
        help="remove a document, its file and everything derived from it",
    )
    group.add_argument(
        "--delete-derived",
        metavar="SHA256",
        help="drop only the passages and facts, keeping the document",
    )
    group.add_argument(
        "--delete-all",
        action="store_true",
        help="remove every document, its files and the upload history. Topics "
        "are not a document's and go separately; `make wipe` runs both",
    )
    return built


def _add(folder: Path, service) -> int:
    """Ingests every PDF directly in a folder, and says what became of each.

    Args:
        folder: Where the PDFs are. Not searched below, and a file whose name
            does not end in `.pdf` is left alone.
        service: The ingest service.

    Returns:
        0, or 1 when the folder is missing or the service refused a file.
        A duplicate is not a refusal: the document is held already.
    """
    if not folder.is_dir():
        log.error("%s is not a directory", folder)
        return 1
    outcomes: Counter[str] = Counter()
    for path in sorted(folder.iterdir()):
        if not (path.is_file() and path.suffix.lower() == ".pdf"):
            continue
        result = service.ingest(UploadedFile(path.name, path.read_bytes()))
        outcomes[result.outcome] += 1
        log.info(
            "%s: %s%s",
            path.name,
            result.outcome,
            f" ({result.detail})" if result.detail else "",
        )
    refused = outcomes["too_large"] + outcomes["unsupported_type"]
    log.info(
        "%d stored, %d duplicate, %d refused",
        outcomes["stored"],
        outcomes["duplicate_bytes"],
        refused,
    )
    return 1 if refused else 0


def main(argv: list[str] | None = None) -> int:
    """Lists stored documents, or deletes one.

    A digest is taken in full rather than as a prefix.

    Args:
        argv: Arguments to parse, defaulting to the process's own.

    Returns:
        0, or 1 when no document has the given digest.
    """
    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)

    settings = Settings.load()
    telemetry.configure("ingestion", run=run_id())
    telemetry.trace_engine(engine())

    if args.list:
        total, documents = build_service(settings).documents(limit=1000)
        for document in documents:
            log.info(
                "%s  %-9s %s",
                document.sha256,
                document.parse_status,
                document.filename or "-",
            )
        if total > len(documents):
            log.warning(
                "listed %d of %d documents, the newest first", len(documents), total
            )
        return 0

    if args.add:
        # The limits the Upload page applies, a value stored there included,
        # so a file the page refuses is refused here too.
        return _add(args.add, build_service(Settings.load(resolved())))

    removal = build_removal()
    if args.delete_all:
        for gone in removal.delete_every():
            log.info("%s: %d passage(s) removed", gone.sha256, gone.passages)
        return 0

    digest, remove = (
        (args.delete, removal.delete)
        if args.delete
        else (args.delete_derived, removal.delete_derived)
    )
    removed = remove(digest)
    if removed is None:
        log.error("no document with digest %s", digest)
        return 1
    log.info(
        "%s: %d passage(s) removed, document=%s file=%s parsed=%s",
        removed.sha256,
        removed.passages,
        removed.document,
        removed.file,
        removed.parsed,
    )
    log.info(
        "%d duplicate refusal(s) lost the fact they repeated: the extraction "
        "worker re-decides them when its queue is empty, or `make extract-dedup` "
        "where none runs",
        removed.twinless,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
