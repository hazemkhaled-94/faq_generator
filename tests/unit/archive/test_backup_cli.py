"""The backup command line says how it went, to an operator who ran it."""

from __future__ import annotations

import logging

import pytest

from archive import backup


@pytest.mark.parametrize("wrong", [[], ["dump x differs from the manifest"]])
def test_the_result_is_logged_without_a_formatting_error(
    wrong, monkeypatch, tmp_path, caplog
) -> None:
    """A format string with no placeholder raised a logging TypeError under INFO."""
    monkeypatch.setattr(backup.telemetry, "configure", lambda *_: None)
    monkeypatch.setattr(backup, "verify", lambda *_: wrong)
    caplog.set_level(logging.INFO)

    code = backup.main(["--verify", str(tmp_path)])

    assert code == (1 if wrong else 0)
    assert caplog.records[-1].getMessage() == (
        "1 difference(s)" if wrong else "the backup matches"
    )


def test_the_command_sets_up_logging_so_the_operator_sees_the_result(
    monkeypatch, tmp_path
) -> None:
    """Without it make backup and make restore-backup printed no success line."""
    configured: list[str] = []
    monkeypatch.setattr(backup.telemetry, "configure", configured.append)
    monkeypatch.setattr(backup, "verify", lambda *_: [])

    backup.main(["--verify", str(tmp_path)])

    assert configured == ["backup"]
