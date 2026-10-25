"""A confirmed Redo over questions people reviewed asks again before it passes force."""

from __future__ import annotations

import pytest
import requests
from pages import Answers, answers

pytestmark = pytest.mark.frontend

#: What the API says when released or reviewed questions rest on what a rerun replaces.
REFUSAL = (
    "7 question(s) rest on what this rerun replaces (3 released, 2 accepted, "
    "2 reviewed). They would be rejected as source_changed and leave their "
    "release; nothing is deleted. Go on with force=true."
)


def refused() -> requests.exceptions.HTTPError:
    """The 409 the API answers a rerun with."""
    response = requests.Response()
    response.status_code = 409
    response._content = (
        b'{"code": "questions_rest_on_it", "detail": "' + REFUSAL.encode() + b'"}'
    )
    return requests.exceptions.HTTPError("409 Client Error", response=response)


def redo(forced: bool):
    """A stage_action that refuses a rerun unless force is sent."""

    def act(stage, action, scope=None, **kwargs):
        if action == "rerun" and not kwargs.get("force"):
            raise refused()
        return {"detail": "1 row(s) queued.", "rows": 1}

    return act


@pytest.mark.parametrize("view", ["facts", "passages"])
def test_a_refused_redo_shows_the_count_and_sends_force_only_once_confirmed(
    open_view, view
) -> None:
    """The first confirmation sends none; the refusal is shown; the second sends force."""
    client = Answers(**answers(stage_action=redo(False)))
    drawn = open_view(view, client).press("Redo all").press("Yes, redo")

    assert [one[1][1:2] for one in client.calls("stage_action")] == [("rerun",)]
    assert "force" not in client.calls("stage_action")[0][2]
    assert "7 question(s)" in drawn.text()
    assert "nothing is deleted" in drawn.text()

    drawn = drawn.press("Yes, reject them and redo")

    last = client.calls("stage_action")[-1]
    assert last[1][1] == "rerun" and last[2].get("force") is True


@pytest.mark.parametrize("view", ["facts", "passages"])
def test_the_redo_warning_says_questions_are_rejected_not_deleted(
    open_view, view
) -> None:
    """The sentence a person confirms must be true."""
    client = Answers(**answers())
    drawn = open_view(view, client).press("Redo all")

    assert "nothing is deleted" in drawn.text()
    assert "go, bridges apart, and with them the questions" not in drawn.text()
