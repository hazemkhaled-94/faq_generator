"""Every caller of the api's writes is handed the secret it asks for."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_every_make_target_that_writes_to_the_api_sends_the_secret() -> None:
    """A curl with -X, against the backend, carries X-API-Token."""
    sent = [
        line
        for line in (ROOT / "Makefile").read_text().splitlines()
        if "curl" in line and "$$BACKEND_URL" in line and re.search(r"-X \w+", line)
    ]

    assert sent
    assert all("X-API-Token: $$API_TOKEN" in line for line in sent), sent


def test_the_example_env_names_a_secret_make_setup_generates() -> None:
    """A change_me_ placeholder is what `make setup` replaces."""
    example = (ROOT / ".env.example").read_text()

    assert re.search(r"^API_TOKEN=change_me_\w+$", example, re.MULTILINE)


def test_compose_hands_the_secret_to_the_api_and_to_both_callers() -> None:
    """The api checks it; the frontend and the orchestrator send it."""
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    services = compose["services"]

    for name in ("api", "streamlit", "dagster-webserver", "dagster-daemon"):
        environment = services[name].get("environment", {})
        assert "API_TOKEN" in environment, name


def _curls(text: str) -> list[str]:
    """Every curl command a document shows, its continued lines joined."""
    joined = re.sub(r"\\\n\s*", " ", text)
    return [line.strip() for line in joined.splitlines() if "curl " in line]


def test_every_documented_curl_the_api_refuses_without_the_secret_sends_it() -> None:
    """A write, an upload or any /settings read, as the README and the guides show them.

    Copied as written, one without the header answers 401. The bug log is
    history and is not read.
    """
    documents = [
        ROOT / "README.md",
        *(ROOT / "docs").glob("*.md"),
        *(ROOT / "backend").glob("*/README.md"),
        *(ROOT / "frontend").glob("README.md"),
    ]
    refused = [
        f"{path.relative_to(ROOT)}: {curl}"
        for path in documents
        if path.name != "bugs.md"
        for curl in _curls(path.read_text())
        if (
            re.search(r"-X (POST|PATCH|PUT|DELETE)\b| -[Fd] ", curl)
            or "/settings" in curl
        )
        and "X-API-Token: $API_TOKEN" not in curl
    ]

    assert not refused, refused
