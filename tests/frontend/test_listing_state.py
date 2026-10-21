"""The listing pages' row pick follows the row's id, not its position."""

from __future__ import annotations

import pytest
import requests
from pages import QUESTION, QUESTION_SOURCE, Answers, answers, changed, status

pytestmark = pytest.mark.frontend


def _detail(question):
    return {"question": question, "sources": [QUESTION_SOURCE], "thread": []}


def _rows(ids):
    return [changed(QUESTION, id=i, status="draft") for i in ids]


def test_changing_page_does_not_open_another_rows_panel(open_view) -> None:
    """Row 3 picked on page 1; moving to page 2 must not open page 2's row 3."""
    everything = _rows(range(8000, 8060))

    def questions(**asked):
        off = asked.get("offset", 0)
        return {"total": 60, "questions": everything[off : off + 25]}

    client = Answers(
        **answers(
            questions=questions,
            question=lambda i: _detail(changed(QUESTION, id=i, status="draft")),
        )
    )
    opened = open_view("questions", client).select(2)
    assert "Question 8002" in opened.panels()

    # The browser keeps the table's stored selection under its key, so the
    # same position is still selected over page 2's rows; nothing is clicked.
    opened.numbers()["Page of 3"].set_value(2)
    after = opened._rerun()
    panels = [
        p for p in after.panels() if p.startswith("Question ") and p[9:].isdigit()
    ]
    assert panels == [], f"nobody picked a row on page 2, yet the page opened {panels}"
    # True whether or not anything was pressed: here nothing was.
    assert (
        "Row 8002 is no longer in this list; anything pressed for it was not done."
        in after.captions()
    )


def test_a_press_for_a_row_that_left_the_page_says_so(open_view) -> None:
    """The pressed row left the list: nothing is sent for its neighbour, and it says why.

    By the row's id: a colleague, the gates or a release moved it, and a
    reviewer told only that some row changed could not tell which verdict
    was not recorded.
    """
    gone = {"yes": False}
    decided: list[tuple] = []

    def questions(**_):
        ids = [8034, 8037] if gone["yes"] else [8034, 8036, 8037]
        return {"total": len(ids), "questions": _rows(ids)}

    client = Answers(
        **answers(
            questions=questions,
            question=lambda i: _detail(changed(QUESTION, id=i, status="draft")),
            decide_question=lambda *a: decided.append(a) or QUESTION,
        )
    )
    opened = open_view("questions", client).select(1)
    assert "Question 8036" in opened.panels()
    gone["yes"] = True
    after = opened.press("Reject")

    assert decided == []
    assert (
        "Row 8036 is no longer in this list; anything pressed for it was not done."
        in after.captions()
    )
    assert not any(
        p.startswith("Question ") and p[9:].isdigit() for p in after.panels()
    )


def test_a_filter_change_does_not_open_another_rows_panel(open_view) -> None:
    """The pick of a draft question is dropped when a filter swaps the rows."""
    state = {"rows": _rows([1, 2, 3])}

    def questions(**_):
        return {"total": 3, "questions": state["rows"]}

    client = Answers(
        **answers(
            questions=questions,
            question=lambda i: _detail(changed(QUESTION, id=i, status="draft")),
        )
    )
    opened = open_view("questions", client).select(1)
    assert "Question 2" in opened.panels()
    state["rows"] = _rows([7, 8, 9])
    after = opened._rerun()
    assert not any(
        p.startswith("Question ") and p[9:].isdigit() for p in after.panels()
    )


def test_a_verdict_press_survives_a_row_leaving_above(open_view) -> None:
    """Reject pressed for 8036 while 8035 leaves: 8036 is rejected, not 8037."""
    gone = {"yes": False}
    decided: list[tuple] = []

    def questions(**_):
        ids = [8034, 8036, 8037] if gone["yes"] else [8034, 8035, 8036, 8037]
        return {"total": len(ids), "questions": _rows(ids)}

    client = Answers(
        **answers(
            questions=questions,
            question=lambda i: _detail(changed(QUESTION, id=i, status="draft")),
            decide_question=lambda *a: decided.append(a) or QUESTION,
        )
    )
    opened = open_view("questions", client).select(2)
    assert "Question 8036" in opened.panels()
    gone["yes"] = True
    opened.press("Reject")

    assert decided == [(8036, "rejected")]


@pytest.mark.parametrize(
    "reason",
    ["500 Server Error: Konten-Store nicht erreichbar", "503 Shop image store down"],
)
def test_a_failed_topic_map_leaves_the_topics_table(open_view, reason) -> None:
    """The map fetch failing is said in its own place; table and Delete stay."""

    def fail(*_a, **_k):
        raise requests.HTTPError(reason)

    opened = open_view(
        "topics",
        topic_visualisation=fail,
        stage_status=lambda *a, **k: status(modelled=1),
    )
    assert "topics-search" in opened.widget_keys()
    assert "danger-topics-all" in opened.control_keys()
    assert not opened.errors()
    assert any(reason in c for c in opened.captions())
