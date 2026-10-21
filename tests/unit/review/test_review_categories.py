"""export-3: the review record carries the categories a question was written as."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

pytest.importorskip("argilla")

from review import datasets
from review.records import ReviewRepository

QUERY = {
    "categorization": "Phrasing",
    "category": "short-search-query",
    "form": "query",
}
PLAIN = {"categorization": "Premise", "category": "direct", "form": "question"}


def stored(categories):
    """A stored question as the repository reads it."""
    link = SimpleNamespace(fact=SimpleNamespace(statement="s", evidence_text="e"))
    return SimpleNamespace(
        id=7,
        question_text="Rückgabe Frist Bank",
        target_answer="a",
        answerable=True,
        difficulty="easy",
        question_type="factoid",
        language="de",
        status="accepted",
        rejected_reason=None,
        answer_explanation=None,
        confidence=None,
        kind="single",
        follows_id=None,
        thread_position=1,
        categories=categories,
        fact_links=[link],
    )


def test_the_categories_reach_the_record_and_a_query_says_so() -> None:
    """A reviewer reads each category, and which of them is a search query."""
    rec = datasets.question_record(ReviewRepository._question(stored([PLAIN, QUERY])))

    shown = rec.fields["categories"]
    assert "Premise=direct" in shown
    assert "Phrasing=short-search-query (query)" in shown
    assert "(query)" not in shown.split("\n")[0]


def test_a_question_with_no_categories_sends_no_field() -> None:
    """Argilla refuses an empty field, and nothing was told it."""
    rec = datasets.question_record(ReviewRepository._question(stored(None)))

    assert "categories" not in rec.fields


def test_the_guideline_judges_a_query_as_a_query() -> None:
    """A keyword query is not a malformed question."""
    source = inspect.getsource(datasets.question_settings)
    assert "search" in source and "not a malformed question" in source
    assert 'name="categories"' in source
