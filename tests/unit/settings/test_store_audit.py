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


@pytest.fixture(autouse=True)
def _unwarned(monkeypatch):
    """A process that has warned about nothing yet."""
    monkeypatch.setattr(store, "_warned", set())


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


# ── Which stage a refused row stops ────────────────────────────────────────


def test_a_stage_refuses_a_refused_row_of_its_own(caplog) -> None:
    """Parsing will not build on a confidence above one."""
    with pytest.raises(store.StoredRefused, match="PARSING_MIN_CONFIDENCE"):
        store.audit([row("PARSING_MIN_CONFIDENCE", "2")], {}, service="parsing")


def test_another_stage_s_refused_row_is_warned_about_and_left(caplog) -> None:
    """Chunking reads no parsing setting, so a parsing row does not stop it."""
    with caplog.at_level(logging.WARNING):
        store.audit([row("PARSING_MIN_CONFIDENCE", "2")], {}, service="chunking")

    (said,) = [r.getMessage() for r in caplog.records]
    assert "PARSING_MIN_CONFIDENCE" in said and "parsing stage" in said


@pytest.mark.parametrize(
    "service",
    ["parsing", "chunking", "extraction", "topics", "questions", "assessment"],
)
def test_a_refused_platform_row_stops_every_stage(service: str) -> None:
    """EMBEDDING_MAX_TOKENS below its floor of 64 cuts passages in chunking."""
    with pytest.raises(store.StoredRefused, match="EMBEDDING_MAX_TOKENS"):
        store.audit([row("EMBEDDING_MAX_TOKENS", "4")], {}, service=service)


def test_the_doctor_refuses_every_refused_row() -> None:
    """No stage named: whatever any stage would refuse."""
    with pytest.raises(store.StoredRefused, match="QUESTIONS_PER_TOPIC"):
        store.audit([row("QUESTIONS_PER_TOPIC", "0")], {})


class _Stored:
    """The table, holding the item's own example: EMBEDDING_MAX_TOKENS=4."""

    def rows(self):
        """One row under the floor of 64."""
        return [row("EMBEDDING_MAX_TOKENS", "4")]


@pytest.mark.parametrize(
    "module", ["preprocessing.parsing.run", "preprocessing.chunking.run"]
)
def test_parse_and_chunk_build_on_audited_settings(monkeypatch, module: str) -> None:
    """They built on resolved(), unaudited, so chunking cut passages to 4 tokens."""
    import importlib

    run = importlib.import_module(module)
    monkeypatch.setattr(store, "Settings", _Stored)
    monkeypatch.delenv("QA_COMMAND_LINE", raising=False)
    built: dict = {}
    monkeypatch.setattr(run, "queue_main", lambda **kwargs: built.update(kwargs) or 0)

    run.main([])

    with pytest.raises(store.StoredRefused, match="EMBEDDING_MAX_TOKENS"):
        built["build_service"]()


# ── A worker waits on a refused row ────────────────────────────────────────


class _Waited(Exception):
    """Raised by the first wait, so a worker that waits ends the test."""


def _refused(*_args) -> tuple[dict[str, str], str]:
    raise store.StoredRefused("EMBEDDING_MAX_TOKENS='4' is refused now")


def _wait_once(monkeypatch) -> None:
    from stages import cli

    def slept(_seconds: float) -> None:
        raise _Waited

    monkeypatch.setattr(cli.time, "sleep", slept)


def test_the_assessment_worker_waits_on_a_refused_row(monkeypatch) -> None:
    """Its first read was outside the wait, so the container restarted in a loop."""
    from assessment import run

    monkeypatch.setattr(run, "snapshot", _refused)
    _wait_once(monkeypatch)

    with pytest.raises(_Waited):
        run.main(["--watch"])


def test_a_one_off_assessment_says_so_and_exits_1(monkeypatch) -> None:
    """A person holds the exit code."""
    from assessment import run

    monkeypatch.setattr(run, "snapshot", _refused)

    assert run.main([]) == 1


def test_the_topic_worker_waits_on_a_refused_row(monkeypatch) -> None:
    """Its first build was outside the wait, so the container restarted in a loop."""
    from topic_modelling import run

    monkeypatch.setattr(run, "snapshot", _refused)
    monkeypatch.setattr(run, "carry", lambda _ledger: None)
    monkeypatch.setattr(run.telemetry, "configure", lambda *a, **k: None)
    _wait_once(monkeypatch)

    with pytest.raises(_Waited):
        run.main(["--watch"])


# ── A model id moves with its pinned commit ────────────────────────────────


@pytest.mark.parametrize(
    ("name", "service"),
    [
        ("QA_MODEL", "questions"),
        ("NLI_MODEL", "questions"),
        ("EMBEDDING_MODEL", "chunking"),
    ],
)
def test_a_stored_encoder_row_is_refused_before_any_load(
    name: str, service: str
) -> None:
    """QA_MODEL stored with no QA_MODEL_REVISION failed at its first load, mid-run."""
    with pytest.raises(store.StoredRefused) as refused:
        store.audit([row(name, "org-c/reader")], {}, service=service)

    said = str(refused.value)
    assert name in said and f"{name}_REVISION" in said and "DELETE FROM" in said


# ── Said once, not at every poll ───────────────────────────────────────────


def test_an_override_is_warned_about_once_per_value(caplog) -> None:
    """A worker reads its settings every poll; the log is not to fill with one row."""
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            store.audit([row("QUESTIONS_PER_TOPIC", "6")], {"QUESTIONS_PER_TOPIC": "4"})
        store.audit([row("QUESTIONS_PER_TOPIC", "7")], {"QUESTIONS_PER_TOPIC": "4"})

    said = [r.getMessage() for r in caplog.records]
    assert len(said) == 2
    assert "'6'" in said[0] and "'7'" in said[1]


def test_a_row_left_alone_is_warned_about_once(caplog) -> None:
    """A row for a setting the deployment owns, read at every poll."""
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            store.audit([row("SPEND_CAP", "5")], {})

    assert len(caplog.records) == 1
