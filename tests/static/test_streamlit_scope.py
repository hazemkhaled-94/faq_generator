"""The frontend container names its database, without the URL that holds the password."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def streamlit_block() -> str:
    """The streamlit service of compose.yaml, up to the next service."""
    text = (ROOT / "compose.yaml").read_text()
    start = text.index("\n  streamlit:\n")
    following = re.search(r"\n  [a-z][a-z0-9-]*:\n", text[start + 1 :])
    return text[start : start + 1 + following.start()] if following else text[start:]


def test_the_streamlit_service_names_its_database_by_name_only() -> None:
    """The lineage panel scopes the Argilla dataset by it; the URL would carry the password."""
    block = streamlit_block()

    assert "APP_DB_NAME: ${APP_DB_NAME}" in block
    assert "DATABASE_URL" not in block
