"""The upload route builds ingestion on the stored settings as every stage builds: audited.

Ingestion has no worker, so the API is where its settings are read, and a row
the catalogue now refuses must stop an upload as it stops a stage, naming the
row, rather than be applied.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest


class _Table:
    """The table, holding an upload limit under the catalogue's floor of 1."""

    def rows(self):
        """One refused row."""
        return [
            SimpleNamespace(
                name="MAX_FILE_SIZE_MB",
                value="0",
                updated_at=datetime(2026, 9, 1, 10, 30),
                service="ingestion",
            )
        ]

    def resolved(self):
        """What the store resolved to before the audit reached uploads."""
        from settings import store

        return store._source({"MAX_FILE_SIZE_MB": "0"})


def test_a_refused_stored_upload_setting_answers_naming_the_row(monkeypatch) -> None:
    """503, with the row, its value and how to put it right."""
    from api import dependencies
    from api.errors import ApiError
    from settings import store

    monkeypatch.setattr(store, "Settings", _Table)
    monkeypatch.delenv("QA_COMMAND_LINE", raising=False)

    with pytest.raises(ApiError) as refused:
        dependencies.ingesting()

    assert refused.value.status == 503
    assert refused.value.body.code == "stored_setting_refused"
    assert "MAX_FILE_SIZE_MB" in refused.value.body.detail
