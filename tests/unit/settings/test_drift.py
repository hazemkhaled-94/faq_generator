"""Whether the api serves the settings this checkout catalogues."""

from __future__ import annotations

from settings import catalog, drift


def _served() -> dict[str, set[str]]:
    """What an api built from this checkout serves, by service."""
    served: dict[str, set[str]] = {}
    for one in catalog.SETTINGS:
        served.setdefault(one.service, set()).add(one.name)
    return served


def test_a_served_catalog_missing_a_setting_is_named() -> None:
    """An image built before a setting was added serves the rest without it."""
    served = _served()
    served["questions"].discard("QUESTIONS_MEETS_SHARE")

    assert drift.missing(served) == {"questions": ({"QUESTIONS_MEETS_SHARE"}, set())}


def test_an_identical_catalog_reports_nothing() -> None:
    """The api runs this checkout's build."""
    assert drift.missing(_served()) == {}


def test_an_unset_address_is_a_warning_not_a_failure(monkeypatch) -> None:
    """The doctor goes on to its other checks, as it does when the api is down."""
    monkeypatch.setattr(drift.telemetry, "configure", lambda *_, **__: None)
    monkeypatch.delenv("BACKEND_URL", raising=False)

    assert drift.main([]) == 0
