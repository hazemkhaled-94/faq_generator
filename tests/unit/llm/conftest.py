"""What every llm test runs under."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def no_store_to_read(monkeypatch) -> None:
    """The doctor reads the stored settings, and a unit test has no database.

    A test that wants a store replaces this with one of its own.
    """

    def down():
        raise RuntimeError("a unit test has no settings store")

    monkeypatch.setattr("settings.store.snapshot", down)
