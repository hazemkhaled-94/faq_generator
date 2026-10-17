"""What a topic PATCH asks the catalogue to change, without a database.

What the catalogue then writes is tested against a real one in
`tests/integration/api/test_topics.py`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from topic_modelling.repository import KEEP


class Catalog:
    """A topic catalogue that records what it was asked to write."""

    def __init__(self) -> None:
        """Starts having been asked nothing."""
        self.asked: list[dict] = []

    def describe(self, topic_id: int, **changes):
        """Records the change and answers no topic, so the route says 404."""
        self.asked.append(changes)


@pytest.fixture
def described(monkeypatch):
    """PATCH /topics/1 with a body, and what the catalogue was asked."""
    from api.main import app
    from api.routes import topics

    catalog = Catalog()
    monkeypatch.setattr(topics, "topic_catalog", catalog)
    client = TestClient(app, base_url="http://localhost:8000")

    def send(body: dict) -> dict:
        client.patch("/topics/1", json=body)
        (asked,) = catalog.asked
        return asked

    return send


def test_a_body_without_a_label_leaves_the_label(described) -> None:
    """Taking a topic out of coverage does not erase a person's name for it."""
    asked = described({"include_in_coverage": False})

    assert asked == {"label": KEEP, "include_in_coverage": False}


def test_a_body_without_coverage_leaves_coverage(described) -> None:
    """Naming a topic does not put an excluded one back in."""
    asked = described({"label": "Fees"})

    assert asked == {"label": "Fees", "include_in_coverage": None}


def test_a_label_of_null_still_clears_it(described) -> None:
    """Named and empty is how a person takes a name away."""
    asked = described({"label": None})

    assert asked == {"label": None, "include_in_coverage": None}
