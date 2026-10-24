"""The `released` filter, as the three question reads parse it.

The routes are imported inside the fixture, never at module scope: see
tests/unit/api/test_params.py for why.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from question_generation.models import QuestionQuality
from question_generation.queue import NeverAsked

#: The reads that take the listing's filter.
READS = ("/questions", "/questions/quality", "/questions/export")


class _Catalog:
    """A question catalogue that records the filter each read was given."""

    def __init__(self) -> None:
        """Holds nothing and has been asked nothing."""
        self.asked: dict[str, dict] = {}

    @contextmanager
    def snapshot(self):
        """The one moment `export` reads in; the reads here take no session."""
        yield None

    def page(self, *args, **where):
        """The listing, as `questions` and `export` call it."""
        self.asked["page"] = {"given": args, **where}
        return 0, []

    def citations(self, **where):
        """No citations."""
        self.asked["citations"] = where
        return []

    def quality(self, *args, **where):
        """A report of nothing."""
        self.asked["quality"] = {"given": args, **where}
        return QuestionQuality(
            *[0] * 9, *[{}] * 9, cognitive_level_checked=0, planned_met=0
        )


class _Queue:
    """A question queue that has no database to ask what no question reaches."""

    @staticmethod
    def never_asked() -> NeverAsked:
        """Every document has been asked."""
        return NeverAsked((), 0)


class _NoJudgements:
    """An assessment catalogue nobody has judged anything in."""

    def verdicts_for(self, kind: str, ids: list[int]) -> dict:
        """Nothing has been judged."""
        del kind, ids
        return {}


@pytest.fixture
def held(monkeypatch) -> tuple[TestClient, _Catalog]:
    """The questions router, in front of a recording catalogue."""
    from api.routes import questions

    catalog = _Catalog()
    monkeypatch.setattr(questions, "question_catalog", catalog)
    monkeypatch.setattr(questions, "assessment_catalog", _NoJudgements())
    monkeypatch.setattr(questions, "questions_queue", _Queue())
    app = FastAPI()
    app.include_router(questions.router)
    return TestClient(app), catalog


@pytest.mark.parametrize("path", READS)
@pytest.mark.parametrize(
    ("given", "released"),
    [("true", True), ("True", True), ("false", False), (None, None)],
)
def test_released_reaches_the_catalogue(held, path, given, released) -> None:
    """True is the release, false is everything outside it, absent is no filter."""
    client, catalog = held
    params = {"status": "accepted"} | ({} if given is None else {"released": given})

    assert client.get(path, params=params).status_code == 200
    assert catalog.asked
    for read, where in catalog.asked.items():
        assert where["released"] is released, read
        assert "accepted" in (*where.get("given", ()), *where.values()), read


@pytest.mark.parametrize("path", READS)
def test_a_released_value_that_is_not_a_boolean_is_refused(held, path) -> None:
    """Refused rather than read as no filter."""
    client, catalog = held

    assert client.get(path, params={"released": "maybe"}).status_code == 422
    assert not catalog.asked
