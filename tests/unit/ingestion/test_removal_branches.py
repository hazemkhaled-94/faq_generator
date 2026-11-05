"""A deletion that fails part-way surfaces its own error, whatever the give-back does.

The rows roll back and the objects already moved are given back. A give-back
that fails too is logged with the object it left in the archive, the other
objects are still given back, and the error that stopped the deletion is the
one raised, so the operator sees why it stopped and what to move by hand.
"""

from __future__ import annotations

import logging

import pytest

from ingestion.removal import RemovalService


class Bucket:
    """A bucket that names its keys by digest."""

    def __init__(self, name: str) -> None:
        self.name = name

    def key_for(self, sha256: str, media_type: str | None = None) -> str:
        return f"qa_x/{sha256}"


class Archive:
    """An archive whose second take fails, and whose first give-back fails."""

    def __init__(self) -> None:
        self.takes = 0
        self.given_back: list[tuple[str, str]] = []

    def take(self, bucket: str, key: str) -> bool:
        self.takes += 1
        if self.takes == 3:
            raise TimeoutError("the move of the second file timed out")
        return True

    def give_back(self, bucket: str, key: str) -> None:
        if not self.given_back and bucket == "documents" and key == "qa_x/a1":
            self.given_back.append(("failed", key))
            raise ConnectionError("object store unreachable")
        self.given_back.append((bucket, key))


class Repository:
    """Two documents whose rows are deleted inside a transaction that runs the move."""

    def digests(self) -> list[str]:
        return ["a1", "b2"]

    def media_type(self, sha256: str) -> str:
        return "application/pdf"

    def delete_all(self, digests, move):
        move()
        return {digest: 1 for digest in digests}

    def forget_uploads(self) -> int:
        raise AssertionError("the uploads are forgotten only after every move")


def test_a_failed_give_back_is_logged_and_the_deletions_own_error_is_raised(
    caplog,
) -> None:
    """The move that failed is the error; the stuck object is named in the log."""
    archive = Archive()
    service = RemovalService(
        repository=Repository(),
        store=Bucket("documents"),
        parsed=Bucket("parsed"),
        archive=archive,
    )

    with caplog.at_level(logging.ERROR), pytest.raises(TimeoutError, match="second file"):
        service.delete_every()

    assert "could not give back documents/qa_x/a1" in caplog.text
    assert ("parsed", "qa_x/a1") in archive.given_back, (
        "the next object is still given back"
    )
