"""The Questions page, run against a scripted backend.

What only this page has: a confidence built out of several readings on
different scales, and an explainer for the service that produced them. The
rules it shares with every other page are in test_views.py.
"""

from __future__ import annotations

import pandas as pd
import pytest
from pages import QUESTION, QUESTION_SOURCE, Answers, answers, changed

pytestmark = pytest.mark.frontend

#: The view this module is about. `page` in conftest.py reads it.
VIEW = "questions"

#: A question scored since the margins were calibrated, which is what a row
#: written by a current run looks like.
CALIBRATED = changed(
    QUESTION,
    confidence=0.28,
    gate_scores=[
        {
            "gate": "near_duplicate",
            "value": 0.88,
            "threshold": 0.93,
            "margin": 0.2778,
            "high_is_safe": False,
            "safe_end": 0.75,
        },
        {
            "gate": "recall",
            "value": 0.83,
            "threshold": 0.6,
            "margin": 0.575,
            "high_is_safe": True,
            "safe_end": 1.0,
        },
    ],
)


def said(view) -> str:
    """Every caption the page drew, as one string to look in."""
    return " ".join(view.captions())


# ── The explainer ─────────────────────────────────────────────────────────


def test_the_service_explains_itself_in_one_fold(page) -> None:
    """One, not three: a page opening with five collapsed sections floods."""
    folds = [one for one in page().folds() if one.startswith("How ")]

    assert folds == ["How question generation works"]


def test_every_gate_is_listed_whether_or_not_it_fired(page) -> None:
    """A gate missing from a reference is one nobody can look up.

    The page's own list is what the Analysis fold counts against, so a gate
    described here and absent there would be a rejection code with no name.
    """
    listed = page().table_with("Rejected as")

    assert "not_recoverable" in list(listed["Rejected as"])
    assert "source_changed" in list(listed["Rejected as"])


def test_a_gate_says_what_kind_of_thing_it_is(page) -> None:
    """A rule, a measurement and an opinion carry different weight.

    Only a measurement has a margin behind it, which is the whole reason
    the confidence panel is absent on some questions.
    """
    listed = page().table_with("Rejected as")
    kinds = dict(zip(listed["Rejected as"], listed["Kind"], strict=True))

    assert kinds["malformed"] == "rule"
    assert "measurement" in kinds["duplicate"]


def test_the_phase_is_carried_beside_the_code(page) -> None:
    """The two vocabularies reconciled, which is why this table exists.

    A trace records `structural`; the table records `malformed`. Nothing
    told a reader those were the same event until this column did.
    """
    listed = page().table_with("Rejected as")
    phases = dict(zip(listed["Rejected as"], listed["In phase"], strict=True))

    assert phases["malformed"] == "structural"
    assert phases["compound"] == "structural"
    assert phases["duplicate"] == "near_duplicate"


# ── The confidence ────────────────────────────────────────────────────────


def test_the_confidence_names_the_gate_that_was_weakest(page) -> None:
    """The number alone cannot be read: it is the smallest of several.

    Which reading it came from is most of what it says, so a panel showing
    only the figure is showing the least useful half of it.
    """
    opened = page(question=_detail(CALIBRATED), questions=_one(CALIBRATED)).select()

    assert "near_duplicate" in said(opened)
    assert "0.28" in said(opened)


def test_a_reading_says_which_way_its_gate_runs(page) -> None:
    """0.88 is comfortable under one gate and refusing under another."""
    opened = page(question=_detail(CALIBRATED), questions=_one(CALIBRATED)).select()
    table = opened.table_with("Safe when")
    direction = dict(zip(table["Gate"], table["Safe when"], strict=True))

    assert direction["near_duplicate"] == "lower is safer"
    assert direction["recall"] == "higher is safer"


def test_a_legacy_reading_is_not_read_as_the_safe_direction(page) -> None:
    """The fixture carries no direction, as every row written before did.

    Defaulting those to `higher is safer` would tell a reader that a
    question sitting on the duplicate ceiling was as far from refusal as a
    question can get - the exact inversion the column exists to prevent.
    """
    opened = page().select()
    table = opened.table_with("Safe when")
    direction = dict(zip(table["Gate"], table["Safe when"], strict=True))

    assert direction["near_duplicate"] == "lower is safer"


def test_an_uncalibrated_row_says_its_confidence_reads_low(page) -> None:
    """A row scored before the calibration is not a bad question.

    Saying nothing would leave a reader comparing a 0.04 written under one
    arithmetic against a 0.28 written under another.
    """
    opened = page().select()

    assert "calibrated" in said(opened)


def test_a_calibrated_row_carries_no_such_warning(page) -> None:
    """The note is about the row, not about the page."""
    opened = page(question=_detail(CALIBRATED), questions=_one(CALIBRATED)).select()

    assert "before the margins were" not in said(opened)


def test_a_question_nothing_measured_says_so_rather_than_scoring_zero(page) -> None:
    """No confidence is not a low one, and a row of dashes reads as one."""
    unmeasured = changed(QUESTION, confidence=None, gate_scores=[])
    opened = page(question=_detail(unmeasured), questions=_one(unmeasured)).select()

    assert "no confidence" in said(opened)
    assert "not a low one" in said(opened)


#: An unanswerable question kept: one measurement, and the verifier's two
#: `settles` verdicts recorded beside it as opinions with no margin.
SETTLED = changed(
    QUESTION,
    answerable=False,
    target_answer=None,
    confidence=0.05,
    gate_scores=[
        {
            "gate": "off_topic",
            "value": 0.33,
            "threshold": 0.3,
            "margin": 0.0476,
            "high_is_safe": True,
            "safe_end": 1.0,
        },
        {
            "gate": "settles",
            "value": 1.0,
            "threshold": 0.5,
            "margin": None,
            "high_is_safe": True,
            "safe_end": 1.0,
            "opinion": True,
        },
        {
            "gate": "settles_elsewhere",
            "value": 1.0,
            "threshold": 0.5,
            "margin": None,
            "high_is_safe": True,
            "safe_end": 1.0,
            "opinion": True,
        },
    ],
)


def test_a_settles_verdict_says_what_it_is_and_is_never_the_weakest(page) -> None:
    """An opinion beside the readings: described, and given no margin."""
    opened = page(question=_detail(SETTLED), questions=_one(SETTLED)).select()
    table = opened.table_with("Reads")
    reads = dict(zip(table["Gate"], table["Reads"], strict=True))

    assert opened.raised == []
    assert "settle" in reads["settles"]
    assert "settle" in reads["settles_elsewhere"]
    assert "off_topic" in said(opened)
    assert "1 measured reading(s)" in said(opened)
    assert "not part of the confidence" in said(opened)


#: An accepted question carrying a gate measured before it gates anything,
#: read below the bar it will one day refuse at.
SHADOWED = changed(
    CALIBRATED,
    gate_scores=[
        *CALIBRATED["gate_scores"],
        {
            "gate": "coverage",
            "value": 0.25,
            "threshold": 0.4,
            "margin": None,
            "high_is_safe": True,
            "safe_end": 1.0,
            "shadow": True,
        },
    ],
)


def test_a_shadow_reading_refuses_nothing(page) -> None:
    """Below its bar and accepted, which read as a gate that should have fired.

    And counted among the verdicts a model gave, which it is not either.
    """
    opened = page(question=_detail(SHADOWED), questions=_one(SHADOWED)).select()
    table = opened.table_with("Refuses at")
    refuses = dict(zip(table["Gate"], table["Refuses at"], strict=True))
    safe = dict(zip(table["Gate"], table["Safe when"], strict=True))

    assert pd.isna(refuses["coverage"]), refuses
    assert "refuses nothing" in safe["coverage"]
    assert "verdicts a model gave" not in said(opened)
    assert "in shadow" in said(opened)


# ── A verdict ─────────────────────────────────────────────────────────────


def test_a_verdict_does_not_slide_the_panel_onto_the_next_question(
    open_view,
) -> None:
    """Accepting the first of two rejected rows takes it out of the filter.

    The selection is a position, so without a reset the panel would open on
    the second question with Accept live where the first one's was.
    """
    first = changed(QUESTION, id=101, status="rejected")
    second = changed(QUESTION, id=102, status="rejected")
    decided: list[tuple] = []
    client = Answers(
        **answers(
            questions=lambda **_: {
                "total": 2 - len(decided),
                "questions": [second] if decided else [first, second],
            },
            question=lambda one: _detail(first if one == 101 else second),
            decide_question=lambda *asked: decided.append(asked) or first,
        )
    )
    opened = open_view("questions", client).select(0)
    assert "Question 101" in opened.panels()

    after = opened.press("Accept")

    assert decided == [(101, "accepted")]
    assert "Question 102" not in after.panels()
    assert "accept-102" not in after.control_keys()


def test_the_verdict_tooltips_say_what_a_verdict_does(page) -> None:
    """Reject leaves the release; Accept only makes a question drawable."""
    draft = changed(QUESTION, status="draft")
    opened = page(question=_detail(draft), questions=_one(draft)).select()

    assert "out of the release" in opened.button("Reject").help
    assert "next release" in opened.button("Accept").help
    assert "gate" not in opened.button("Accept").help


# ── The release ───────────────────────────────────────────────────────────


def test_the_release_is_a_filter_the_rows_figures_and_workbook_share(
    open_view,
) -> None:
    """Released narrows the table, the Overview and the workbook alike."""
    client = Answers(**answers(question_workbook=b"PK\x03\x04 a workbook"))
    opened = open_view("questions", client)
    assert opened.options("questions-released") == ["All questions", "Released"]
    assert client.calls("questions")[-1][2].get("released") is None

    narrowed = (
        opened.choose("questions-status", "accepted")
        .choose("questions-released", "Released")
        .press("Build a workbook")
    )

    assert narrowed.raised == []
    for method in ("questions", "question_quality", "question_workbook"):
        asked = client.calls(method)[-1][2]
        assert asked["released"] is True, method
        assert asked["status"] == "accepted", method


# ── The prompt that wrote it ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("fields", "name"),
    [
        ({"answerable": False}, "perturb"),
        ({"follows_id": 7}, "follow"),
        ({"planned_difficulty": "medium"}, "factoid (spans)"),
        ({}, "factoid"),
    ],
)
def test_the_prompt_is_read_under_the_name_it_was_sent_as(
    open_view, fields, name
) -> None:
    """Unanswerable, follow-up and spanning questions each had their own."""
    question = changed(QUESTION, **fields)
    client = Answers(
        **answers(
            questions=_one(question),
            question=_detail(question),
            prompts=lambda **asked: [_recorded(asked["name"])],
        )
    )

    opened = open_view("questions", client).select(0)

    assert client.calls("prompts")[-1][2]["name"] == name
    assert f"The prompt that wrote this · {name} v8" in opened.folds()


def test_a_type_with_no_spanning_prompt_falls_back_to_its_own(open_view) -> None:
    """Recorded once where the spanning text is the plain one."""
    question = changed(QUESTION, planned_difficulty="medium")
    client = Answers(
        **answers(
            questions=_one(question),
            question=_detail(question),
            prompts=lambda **asked: (
                [] if asked["name"].endswith("(spans)") else [_recorded(asked["name"])]
            ),
        )
    )

    opened = open_view("questions", client).select(0)

    assert [one[2]["name"] for one in client.calls("prompts")][-2:] == [
        "factoid (spans)",
        "factoid",
    ]
    assert "The prompt that wrote this · factoid v8" in opened.folds()


def _recorded(name: str) -> dict:
    """One prompt as /prompts answers it."""
    return {
        "name": name,
        "digest": "0123456789abcdef",
        "first_seen_at": "2026-09-14T10:00:00",
        "text": f"The system prompt {name} was sent.",
        "user_text": "{{sample}}",
    }


def _one(question: dict) -> dict:
    """One page of questions holding exactly this one."""
    return {"total": 1, "questions": [question]}


def _detail(question: dict) -> dict:
    """What the detail route answers for it, which the panel needs whole."""
    return {"question": question, "sources": [QUESTION_SOURCE], "thread": []}
