"""Two answers a review must not turn into writes.

A topic record whose name was cleared and whose coverage question was left
unanswered is no vote on either, so a pull writes nothing for it. A push
whose every row already has an answer in the tool sends nothing and says so,
rather than asking somebody to judge a row twice.
"""

from __future__ import annotations

import logging

import pytest

pytest.importorskip("argilla", reason="the observability group is not installed")

from test_service import Record, asking, row, submitted, wired

from review import datasets
from review.config import Settings
from review.service import pull, push

SETTINGS = Settings(
    api_url="http://argilla:6900", api_key="key", workspace="qa_generator", sample=10
)


def test_a_topic_with_a_blank_name_and_no_coverage_answer_writes_nothing(
    monkeypatch,
) -> None:
    """Neither the label nor the coverage moves."""
    catalogs = wired(
        monkeypatch, [Record({"topic_id": 3}, [submitted("corrected_label", "  ")])]
    )

    assert pull(datasets.TOPIC_LABELS, SETTINGS, catalogs) == 0
    assert catalogs.topics.described == []
    assert catalogs.facts.covered == []


def test_a_push_with_every_row_answered_sends_nothing_and_says_so(
    monkeypatch, caplog
) -> None:
    """The tool holds an answer to each, so nothing is logged to it."""
    catalogs, dataset = asking(
        monkeypatch,
        [Record({"question_id": 7}, [submitted("verdict", "accepted")], id="7")],
        [row(7)],
    )

    with caplog.at_level(logging.INFO):
        assert push(datasets.QUESTIONS, SETTINGS, catalogs) == 0

    assert dataset.records.logged == []
    assert "nothing left to review" in caplog.text
