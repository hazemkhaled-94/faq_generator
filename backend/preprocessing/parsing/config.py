"""Configuration for the parsing service."""

from __future__ import annotations

import os
from dataclasses import dataclass

from settings import Source, boolean, decimal, integer, optional, required


@dataclass(frozen=True)
class Settings:
    """Runtime configuration, read from the environment.

    Attributes:
        ocr_char_threshold: Characters per page below which a document counts
            as scanned.
        min_confidence: Lowest confidence a conversion may carry and still be
            kept.
        table_mode: TableFormer mode, `fast` or `accurate`.
        heading_hierarchy: Whether the converter rebuilds the heading tree.
        document_timeout_seconds: Longest one conversion may run.
        max_pages: Longest document the worker converts, in pages; 0 for any.
        artifacts_path: Where the converter's model weights are, or None to
            let it download them.
    """

    ocr_char_threshold: int
    min_confidence: float
    table_mode: str
    heading_hierarchy: bool
    document_timeout_seconds: float | None
    max_pages: int
    artifacts_path: str | None

    @classmethod
    def load(cls, source: Source = None) -> Settings:
        """Reads the settings from the environment, or from an override.

        Args:
            source: Where to read them, or None for the process environment.

        Returns:
            The loaded settings.

        Raises:
            KeyError: If any required setting is missing.
            ValueError: If a numeric setting is not a number.
        """
        # Docling reads an empty path as the working directory, so a value that
        # is set and empty is a mistake and not an absence.
        given = (os.environ if source is None else source).get("DOCLING_ARTIFACTS_PATH")
        if given is not None and not given.strip():
            raise ValueError(
                "DOCLING_ARTIFACTS_PATH is set but empty, which Docling reads as "
                "the working directory: name the folder holding its weights, or "
                "leave the setting out"
            )
        return cls(
            ocr_char_threshold=integer("PARSING_OCR_CHAR_THRESHOLD", source),
            min_confidence=decimal("PARSING_MIN_CONFIDENCE", source),
            table_mode=required("PARSING_TABLE_MODE", source),
            heading_hierarchy=boolean("PARSING_HEADING_HIERARCHY", source),
            document_timeout_seconds=decimal("PARSING_TIMEOUT_SECONDS", source),
            max_pages=integer("PARSING_MAX_PAGES", source),
            artifacts_path=optional("DOCLING_ARTIFACTS_PATH", source),
        )
