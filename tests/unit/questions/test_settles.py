"""Whether the passages settle a question written to have no answer.

`read` asks for an answer the passages state outright, and a question whose
premise they refute, or whose case a closed list or a general rule in them
already covers, came back "not in the passages" and was kept as having no
answer. `settles` asks the question an unanswerable one has to survive.

The model is stood in for: what is covered is what it is asked and what is
made of its answer.
"""

from __future__ import annotations

import re

import pytest

from question_generation.verifier import PROMPT_VERSION, Settling, Verifier


class Client:
    """A served model that answers one verdict and records the asks."""

    model = "fake/verifier"

    def __init__(self, verdict: str = Settling.SILENT, quote: str = "") -> None:
        """Initialises the model with the verdict it gives."""
        self.verdict = verdict
        self.quote = quote
        self.asked: list[tuple[str, str, str | None]] = []

    def answer(self, *, system: str, user: str, shape, prompt_version=None):
        """Records the call and answers in the shape asked for."""
        self.asked.append((system, user, prompt_version))
        return shape(verdict=self.verdict, quote=self.quote)


def test_the_prompt_asks_whether_the_passages_refute_or_settle_it() -> None:
    """Stated outright is one way to be answered of four."""
    client = Client()

    Verifier(client).settles("When are refunds paid to visitors?", ["Text."])

    system = client.asked[-1][0]
    for asked in (r"premise", r"refut", r"closed list", r"general rule"):
        assert re.search(asked, system, re.IGNORECASE), asked


@pytest.mark.parametrize("verdict", list(Settling))
def test_each_verdict_comes_back_as_the_model_gave_it(verdict: str) -> None:
    """With what the passages said, unless they said nothing."""
    client = Client(verdict, quote="Only account holders are refunded.")

    settled = Verifier(client).settles("When are refunds paid to visitors?", ["T."])

    assert settled.verdict == verdict
    if verdict == Settling.SILENT:
        assert settled.quote is None
    else:
        assert settled.quote == "Only account holders are refunded."


def test_the_model_is_shown_every_passage_numbered_and_the_question() -> None:
    """And the call is recorded under this module's prompt version."""
    client = Client()

    Verifier(client).settles(
        "When are refunds paid to visitors?",
        ["Refunds take 14 days.", "Only account holders are refunded."],
    )

    _, user, version = client.asked[-1]
    assert "[1] Refunds take 14 days." in user
    assert "[2] Only account holders are refunded." in user
    assert "Question: When are refunds paid to visitors?" in user
    assert version == PROMPT_VERSION
