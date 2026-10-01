"""What the settings page is handed, read against a store that moves."""

from __future__ import annotations


def test_the_version_handed_out_predates_the_values_beside_it(monkeypatch) -> None:
    """A write landing mid-read makes the page's PATCH conflict, not win."""
    from api.routes import settings as route

    read: list[str] = []
    monkeypatch.setattr(
        route.store, "version", lambda: "after" if "values" in read else "before"
    )
    monkeypatch.setattr(route.store, "resolved", lambda: read.append("values") or {})
    monkeypatch.setattr(route.store, "overrides", dict)
    monkeypatch.setattr(route.store, "changed_at", dict)

    described, _ = route._described("questions")

    assert described.version == "before"
