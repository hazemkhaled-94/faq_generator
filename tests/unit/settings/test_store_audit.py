"""A stored row is re-checked against the catalogue whenever a service is built.

A row is an override written once and read for months. The catalogue moves
under it: a floor is raised, a choice dropped, a name retired. The build says
so, naming the row, instead of a worker starting on a value nobody would write
today, or quietly dropping one.
"""

from __future__ import annotations

import logging
from datetime import datetime
from types import SimpleNamespace

import pytest

from settings import store

WHEN = datetime(2026, 9, 1, 10, 30)


def row(name: str, value: str) -> SimpleNamespace:
    """One stored row."""
    return SimpleNamespace(name=name, value=value, updated_at=WHEN)


def test_a_stored_value_below_the_catalogue_floor_refuses_the_build() -> None:
    """Named, with the value and when it was written."""
    with pytest.raises(store.StoredRefused) as refused:
        store.audit([row("TOPIC_MIN_WEIGHT", "-1")], {})

    said = str(refused.value)
    assert "TOPIC_MIN_WEIGHT" in said and "'-1'" in said and "2026-09-01" in said


def test_a_stored_flag_spelled_wrong_refuses_the_build() -> None:
    """Read it is off; stored it is a typo that switched something off."""
    with pytest.raises(store.StoredRefused, match="CHUNKING_MERGE_PEERS"):
        store.audit([row("CHUNKING_MERGE_PEERS", "ture")], {})


def test_a_row_that_still_passes_is_quiet_when_it_matches_the_file(caplog) -> None:
    """No warning for what changes nothing."""
    with caplog.at_level(logging.WARNING):
        store.audit([row("TOPIC_MIN_WEIGHT", "0.2")], {"TOPIC_MIN_WEIGHT": "0.2"})

    assert caplog.records == []


def test_a_row_that_differs_from_the_file_is_one_warning_naming_both(caplog) -> None:
    """The stored value, the file's, and when the row was written."""
    with caplog.at_level(logging.WARNING):
        store.audit([row("TOPIC_MIN_WEIGHT", "0.3")], {"TOPIC_MIN_WEIGHT": "0.2"})

    (said,) = [r.getMessage() for r in caplog.records]
    assert "TOPIC_MIN_WEIGHT" in said
    assert "'0.3'" in said and "'0.2'" in said and "2026-09-01" in said


def test_a_retired_name_refuses_the_build_naming_its_replacement(monkeypatch) -> None:
    """The settings that were renamed are listed, with what replaced them."""
    monkeypatch.setitem(store.RETIRED, "OLD_WEIGHT_FLOOR", "TOPIC_MIN_WEIGHT")

    with pytest.raises(store.StoredRefused) as refused:
        store.audit([row("OLD_WEIGHT_FLOOR", "0.1")], {})

    assert "TOPIC_MIN_WEIGHT" in str(refused.value)
    assert "OLD_WEIGHT_FLOOR" in str(refused.value)


def test_a_row_for_a_setting_the_deployment_now_owns_is_ignored_with_a_warning(
    caplog,
) -> None:
    """It could not be deleted through `make settings-unset`, so it must not stop a build."""
    with caplog.at_level(logging.WARNING):
        store.audit([row("SPEND_CAP", "5")], {})

    assert any("SPEND_CAP" in r.getMessage() for r in caplog.records)


def test_a_name_the_command_line_gave_is_not_audited() -> None:
    """The row is not applied, so what it holds does not matter."""
    store.audit([row("TOPIC_MIN_WEIGHT", "-1")], {}, given={"TOPIC_MIN_WEIGHT"})


def test_a_snapshot_is_refused_when_a_stored_row_is(monkeypatch) -> None:
    """Every service build reads the settings through it."""

    class Table:
        def rows(self):
            return [row("TOPIC_MIN_WEIGHT", "-1")]

    monkeypatch.setattr(store, "Settings", Table)

    with pytest.raises(store.StoredRefused, match="TOPIC_MIN_WEIGHT"):
        store.snapshot()


def test_a_snapshot_of_good_rows_is_the_environment_over_them(monkeypatch) -> None:
    """Unchanged: the store's rows over the environment."""

    class Table:
        def rows(self):
            return [row("TOPIC_MIN_WEIGHT", "0.3")]

    monkeypatch.setattr(store, "Settings", Table)
    monkeypatch.delenv("QA_COMMAND_LINE", raising=False)

    source, version = store.snapshot()

    assert source["TOPIC_MIN_WEIGHT"] == "0.3"
    assert version == store.version(source)
