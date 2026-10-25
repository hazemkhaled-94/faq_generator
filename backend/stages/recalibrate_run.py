"""Command-line entry point for recalibrating the stored confidences."""

from __future__ import annotations

import logging
import sys

from settings import decimal
from settings.store import StoredRefused, snapshot
from stages.cli import REFUSED
from stages.recalibrate import main

log = logging.getLogger(__name__)


def run() -> int:
    """Recalibrates both tables from the floors the settings name.

    Read with the stored overrides applied, as the workers read them, and
    through the audit each of the two stages builds through: a stored row
    either refuses stops it with 3, naming the row, before a row is rewritten.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        questions, _ = snapshot("questions")
        facts, _ = snapshot("extraction")
    except StoredRefused as refused:
        log.error("%s", refused)
        return REFUSED
    written = main(
        questions_floor=decimal("QUESTIONS_DUPLICATE_FLOOR", questions),
        facts_floor=decimal("EXTRACTION_DUPLICATE_FLOOR", facts),
    )
    log.info("recalibrated %d row(s) in total", written)
    return 0


if __name__ == "__main__":
    sys.exit(run())
