"""The archive's size flag only reads.

`--size` is what an operator runs before deciding on a purge, so it must
report and leave every row and object where it is.
"""

from __future__ import annotations

import logging


class Sized:
    """An archive that reports a size and records any purge."""

    def __init__(self) -> None:
        self.purges: list[dict] = []

    def estimate(self) -> tuple[int, int]:
        """Rows and bytes, as the planner would report them."""
        return 12_000, 3 * 1024 * 1024

    def purge(self, **named) -> None:
        """Records one purge."""
        self.purges.append(named)


def test_size_reports_the_estimate_and_purges_nothing(monkeypatch, caplog) -> None:
    """Rows and the largest unit above one, and no purge."""
    from archive import run as module

    archive = Sized()
    monkeypatch.setattr(module.telemetry, "configure", lambda *_, **__: None)
    monkeypatch.setattr(module.telemetry, "trace_engine", lambda *_: None)
    monkeypatch.setattr(module, "engine", lambda: None)
    monkeypatch.setattr(module, "Archive", lambda: archive)

    with caplog.at_level(logging.INFO):
        assert module.main(["--size"]) == 0

    assert archive.purges == []
    assert "about 12000 row(s)" in caplog.text
    assert module._sized(3 * 1024 * 1024) in caplog.text
