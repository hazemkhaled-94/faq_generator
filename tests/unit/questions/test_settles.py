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


def test_the_prompt_says_a_rule_that_does_not_decide_the_case_is_silent() -> None:
    """Both ways of being wrong, and no word on what either verdict costs.

    A prompt that only warns against keeping an answered question teaches
    the model to settle open ones; one that says which verdict keeps the
    question tells it what the caller wants to hear.
    """
    client = Client()

    Verifier(client).settles("When are refunds paid to visitors?", ["Text."])

    system = " ".join(client.asked[-1][0].split())
    assert "does not decide this case is `silent`" in system
    assert "keeps the question" not in system


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


# ── What the checker makes of the verdict ─────────────────────────────────


class Gating:
    """The verifier's model: settles where it is shown one text.

    Answers every shape the checker asks with, so a test reads what was
    asked as well as what came of it.
    """

    model = "fake/verifier"

    def __init__(self, settled_by: str | None = None, verdict=Settling.REFUTES):
        """Initialises with the passage that settles it, and how."""
        self.settled_by = settled_by
        self.verdict = verdict
        self.systems: list[str] = []
        self.shapes: list[str] = []

    def answer(self, *, system, user, shape, prompt_version=None):
        """Records the ask; settles only where the text it names was shown."""
        self.systems.append(system)
        self.shapes.append(shape.__name__)
        if "in_passage" in shape.model_fields:
            return shape(in_passage=False, answer="")
        if "supported" in shape.model_fields:
            return shape(supported=False)
        if self.settled_by and self.settled_by in user:
            return shape(verdict=self.verdict, quote=self.settled_by)
        return shape(verdict=Settling.SILENT, quote="")


CITED = "Refunds are only paid to account holders."
UNCITED = "A visitor is refunded at the front desk."


def checked(
    client: Gating,
    probe: bool = True,
    question: str = "When is a refund paid to an account holder's visitor?",
):
    """One unanswerable question through the real checker and verifier."""
    from factories import candidate, group, source
    from unit.questions.test_verification import Recording

    from question_generation.checker import QuestionChecker

    stand_in = Recording(recovers=None)
    return QuestionChecker(
        embedder=stand_in,
        verifier=Verifier(client),
        nearest=lambda embedding, **_: None,
        threshold=0.93,
        phrasing=stand_in,
        elsewhere=lambda *a, **k: [UNCITED],
        elsewhere_passages=4 if probe else 0,
    ).check(
        candidate(
            question_text=question,
            target_answer=None,
            answerable=False,
            facts=group(source(1, statement=CITED, passage_text=CITED)),
        )
    )


def test_the_unanswerable_gate_asks_whether_the_passages_refute_or_settle_it() -> None:
    """Of the cited passages and of the probe, and never `read`'s question."""
    client = Gating()

    result = checked(client)

    assert result.accepted
    assert client.shapes == ["_Settled", "_Settled"]
    for system in client.systems:
        assert re.search(r"premise|refut", system, re.IGNORECASE)
        assert re.search(r"general rule", system, re.IGNORECASE)


@pytest.mark.parametrize("verdict", [Settling.REFUTES, Settling.RULE])
def test_settled_by_its_own_passages_is_answerable_after_all(verdict: str) -> None:
    """Refuted or covered by a rule: a chatbot saying so is right.

    However much of the question its quote repeats: that quote is the rule.
    """
    from database.qa_generator import QuestionRejection

    client = Gating(CITED, verdict)

    result = checked(client)

    assert result.rejected_reason == QuestionRejection.ANSWERABLE_AFTER_ALL
    assert len(client.systems) == 1, "the corpus is not asked once it is settled"


def test_stated_by_its_own_passages_is_answerable_after_all() -> None:
    """An `answers` whose quote adds what the question asked for."""
    from database.qa_generator import QuestionRejection

    client = Gating(CITED, Settling.ANSWERS)

    result = checked(client, question="Who are refunds paid to?")

    assert result.rejected_reason == QuestionRejection.ANSWERABLE_AFTER_ALL
    assert len(client.systems) == 1, "the corpus is not asked once it is settled"


def test_an_answers_that_only_says_the_question_back_settles_nothing() -> None:
    """Its quote is the question restated, so the passages are silent."""
    client = Gating(CITED, Settling.ANSWERS)

    result = checked(client)

    assert result.accepted
    assert {one.gate: one.value for one in result.readings}["settles"] == 1.0
    assert len(client.systems) == 2, "the probe is asked, as after any silence"


@pytest.mark.parametrize("verdict", [Settling.ANSWERS, Settling.REFUTES, Settling.RULE])
def test_settled_by_a_passage_it_does_not_cite_is_answerable_elsewhere(
    verdict: str,
) -> None:
    """The probe's verdict, read the same way."""
    from database.qa_generator import QuestionRejection

    result = checked(Gating(UNCITED, verdict))

    assert result.rejected_reason == QuestionRejection.ANSWERABLE_ELSEWHERE


def test_the_verdict_is_stored_as_a_reading() -> None:
    """Beside the gate list, as the measuring gates' readings are."""
    kept = {one.gate: one.value for one in checked(Gating()).readings}
    refused = {one.gate: one.value for one in checked(Gating(UNCITED)).readings}

    assert kept["settles"] == 1.0 and kept["settles_elsewhere"] == 1.0
    assert refused["settles"] == 1.0 and refused["settles_elsewhere"] == 0.0


def test_the_verdict_is_an_opinion_and_moves_no_confidence() -> None:
    """A model said silent; that is not a margin of 1.0 on anything."""
    from confidence import confidence

    judged = checked(Gating())
    settled = [one for one in judged.readings if one.gate.startswith("settles")]

    assert settled and all(one.opinion for one in settled)
    assert confidence(judged.readings) == confidence(
        [one for one in judged.readings if not one.opinion]
    )


def test_no_probe_leaves_the_cited_passages_as_the_whole_judgement() -> None:
    """QUESTIONS_ELSEWHERE_PASSAGES=0, as before."""
    client = Gating(UNCITED)

    result = checked(client, probe=False)

    assert result.accepted
    assert len(client.systems) == 1
