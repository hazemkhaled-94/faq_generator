"""What this package needs from object storage."""

from __future__ import annotations

from typing import ClassVar, Protocol


class DocumentStore(Protocol):
    """The store holding source documents, exactly as uploaded."""

    name: ClassVar[str]
    """What the store is called, which the archive keys an object by.

    A ClassVar, because a bucket declares its name on the class and a
    protocol asking for an instance attribute does not match one.
    """

    def key_for(self, sha256: str, media_type: str) -> str:
        """Returns the key a document of this type is stored under."""
        ...

    def get(self, key: str) -> bytes:
        """Reads an object."""
        ...

    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str,
        metadata: dict[str, str],
    ) -> None:
        """Stores an object under `key`."""
        ...


class ParsedStore(Protocol):
    """The store holding converted documents, by name and key."""

    name: ClassVar[str]
    """What the store is called, which the archive keys an object by.

    A ClassVar, because a bucket declares its name on the class and a
    protocol asking for an instance attribute does not match one.
    """

    def key_for(self, sha256: str) -> str:
        """Returns the key a converted document is stored under."""
        ...


class ArchiveStore(Protocol):
    """Where an object goes instead of being deleted."""

    def take(self, origin: str, key: str) -> bool:
        """Moves an object out of `origin`, reporting whether one was there."""
        ...
