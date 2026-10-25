"""Removing a document, or only what the pipeline built from it."""

from __future__ import annotations

import logging

from ingestion.models import Removal
from ingestion.repository import DocumentRepository
from ingestion.stores import ArchiveStore, DocumentStore, ParsedStore

log = logging.getLogger(__name__)


class RemovalService:
    """Deletes a document, its file, its converted form and its derived rows.

    Nothing is atomic across two stores, so the order is fixed: the rows are
    deleted inside a transaction, the objects are moved while it is open, and
    it commits only after every move succeeded. A move that fails rolls the
    rows back and gives back the objects already moved, so a document is
    never left as a row with no file.

    Nothing is destroyed. The objects are moved to the archive bucket and
    the rows are copied into `archived_rows` by the trigger on each table,
    so this is the first of two deletions and `make archive-purge` is the
    second.
    """

    def __init__(
        self,
        *,
        repository: DocumentRepository,
        store: DocumentStore,
        parsed: ParsedStore,
        archive: ArchiveStore,
    ) -> None:
        """Initialises the service with its collaborators.

        Args:
            repository: Where the document and passage rows are.
            store: Where the uploaded file is.
            parsed: Where the converted document is.
            archive: Where both of those go instead of being deleted.
        """
        self._repository = repository
        self._store = store
        self._parsed = parsed
        self._archive = archive

    def delete(self, sha256: str) -> Removal | None:
        """Removes a document completely: its rows, its file, its parsed form.

        Args:
            sha256: The document's digest.

        Returns:
            What was removed, or None if no document has that digest.
        """
        media_type = self._repository.media_type(sha256)
        if media_type is None:
            return None
        taken: list[tuple[str, str]] = []
        found: dict[str, tuple[bool, bool]] = {}

        def move() -> None:
            found[sha256] = self._take_objects(sha256, media_type, taken)

        passages, twinless = self._guarded(
            taken, lambda: self._repository.delete(sha256, move)
        )
        return self._removed(sha256, passages, *found[sha256], twinless=twinless)

    def _guarded(self, taken: list[tuple[str, str]], delete):
        """Runs a deletion, giving back the objects already moved if it fails."""
        try:
            return delete()
        except BaseException:
            for origin, key in taken:
                try:
                    self._archive.give_back(origin, key)
                except Exception:
                    log.exception("could not give back %s/%s", origin, key)
            raise

    def _take_objects(
        self, sha256: str, media_type: str, taken: list[tuple[str, str]]
    ) -> tuple[bool, bool]:
        """Moves a document's file and converted form to the archive.

        Args:
            sha256: The document's digest.
            media_type: Its detected media type.
            taken: Appended with each (bucket, key) moved, so a failure after
                the first can put it back.

        Returns:
            Whether each was there.
        """
        moved = []
        for bucket, key in (
            (self._store.name, self._store.key_for(sha256, media_type)),
            (self._parsed.name, self._parsed.key_for(sha256)),
        ):
            there = self._archive.take(bucket, key)
            if there:
                taken.append((bucket, key))
            moved.append(there)
        return moved[0], moved[1]

    def _removed(
        self,
        sha256: str,
        passages: int,
        file_gone: bool,
        parsed_gone: bool,
        twinless: int = 0,
    ) -> Removal:
        """Logs and describes one document's removal."""
        log.info(
            "deleted %s: %d passage(s) archived, file=%s parsed=%s",
            sha256,
            passages,
            file_gone,
            parsed_gone,
        )
        return Removal(
            sha256=sha256,
            document=True,
            passages=passages,
            file=file_gone,
            parsed=parsed_gone,
            twinless=twinless,
        )

    def delete_every(self) -> list[Removal]:
        """Removes every document, its file, its converted form and its rows.

        What a document's deletion cascades to is everything drawn from it:
        its passages, their topic memberships, the facts on them, and by the
        orphan trigger the questions resting on those facts. What it does not
        reach is `topics`, which has no foreign key to a document because a
        fit is over the corpus rather than over a file. Emptying the corpus
        is therefore two commands, and `make wipe` is the one that runs both
        in the order that leaves nothing: documents, then topics.

        The upload history goes too. It survives a single deletion on purpose
        - it records what was attempted rather than what is held - but an
        empty corpus reporting upload attempts is a status panel describing
        documents nothing has. It goes last, so a move that fails leaves
        every document with the name and date it was uploaded under.

        Every object is moved first and every row then goes in one
        statement, so a question resting on two documents is deleted whole
        rather than rejected when the first of them goes.

        Returns:
            What was removed, one entry per document.
        """
        media_types = {
            digest: media
            for digest in self._repository.digests()
            if (media := self._repository.media_type(digest)) is not None
        }
        taken: list[tuple[str, str]] = []
        found: dict[str, tuple[bool, bool]] = {}

        def move() -> None:
            for digest, media in media_types.items():
                found[digest] = self._take_objects(digest, media, taken)

        passages = self._guarded(
            taken, lambda: self._repository.delete_all(list(media_types), move)
        )
        events = self._repository.forget_uploads()
        removed = [
            self._removed(digest, passages.get(digest, 0), *objects)
            for digest, objects in found.items()
        ]
        log.info(
            "deleted %d document(s) and %d upload record(s); topics are not a "
            "document's and are deleted separately",
            len(removed),
            events,
        )
        return removed

    def delete_derived(self, sha256: str) -> Removal | None:
        """Drops what the pipeline built from a document, keeping the document.

        The file and the converted form stay, and chunking returns to `new`.

        Args:
            sha256: The document's digest.

        Returns:
            What was removed, or None if no document has that digest.
        """
        if self._repository.media_type(sha256) is None:
            return None
        passages, twinless = self._repository.delete_derived(sha256)
        log.info("dropped derived data for %s: %d passage(s)", sha256, passages)
        return Removal(
            sha256=sha256,
            document=False,
            passages=passages,
            file=False,
            parsed=False,
            twinless=twinless,
        )
