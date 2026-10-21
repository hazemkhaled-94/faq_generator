"""What the round trip's read says about a question besides its answer.

`read` is the one call every answerable question asked cold gets, so what it
says of the question itself costs no call of its own. The model is stood in
for: what is covered is what it is asked, and what the checker does with
what it said.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from factories import candidate, group, source
from test_verification import _BANK, PerHalf, Recording, _compound, build

from database.qa_generator import QuestionRejection, QuestionStatus
from question_generation.verifier import Reading, Verifier

pytestmark = pytest.mark.nlp


class Client:
    """A served model that answers the read as scripted and records the asks."""

    model = "fake/verifier"

    def __init__(self, **fields) -> None:
        """Initialises the model with the fields it answers with."""
        self.fields = fields
        self.asked: list[tuple[str, str]] = []

    def answer(self, *, system: str, user: str, shape, prompt_version=None):
        """Records the call and answers in the shape asked for."""
        self.asked.append((system, user))
        return shape(
            **{k: v for k, v in self.fields.items() if k in shape.model_fields}
        )


class Reads(Recording):
    """A verifier whose read also says what it made of the question."""

    def __init__(
        self, *, asks_one: bool = True, reason_given: bool = True, **kwargs
    ) -> None:
        """Initialises with what the read says beside the answer."""
        super().__init__(**kwargs)
        self.asks_one = asks_one
        self.reason_given = reason_given

    def read(self, question: str, passages, thread=()) -> Reading:
        """Answers with the scripted reading, and counts the ask."""
        self.verified += 1
        return Reading(
            recovered=self.recovers,
            asks_one=self.asks_one,
            reason_given=self.reason_given,
        )


#: Two things asked under one question word, each with an answer of its own:
#: the passages and the welded question, by language.
_WELDED = {
    "de": (
        (
            "Bei einem Verbraucherkredit beträgt die Widerrufsfrist 14 Tage, bei "
            "einem Immobiliendarlehen ebenfalls 14 Tage ab Vertragsschluss."
        ),
        (
            "Wie lange gilt die Widerrufsfrist bei einem Verbraucherkredit und "
            "bei einem Immobiliendarlehen?"
        ),
        "14 Tage",
    ),
    "en": (
        (
            "A refund for a late delivery is paid within 14 days, and a refund "
            "for a wrong item within 14 days of its return."
        ),
        "How long does a refund take for a late delivery and for a wrong item?",
        "within 14 days",
    ),
}


def _welded(language: str):
    """The welded question, written from its own passage."""
    passage, question, key = _WELDED[language]
    return candidate(
        question_text=question,
        target_answer=key,
        facts=group(source(statement=passage, language=language)),
    )


# ── One thing asked ────────────────────────────────────────────────────────


def test_the_read_says_whether_the_question_asks_one_thing() -> None:
    """A field of the read's own shape, carried onto the reading."""
    client = Client(in_passage=True, answer="14 days", asks_one=False)

    got = Verifier(client).read(_WELDED["en"][1], [_WELDED["en"][0]])

    assert got.asks_one is False
    assert "asks_one" in client.asked[-1][0]


def test_a_read_that_says_nothing_of_it_reads_as_one_thing() -> None:
    """A reply missing the field refuses nothing."""
    client = Client(in_passage=True, answer="14 days")

    assert Verifier(client).read("What does it cost?", ["It costs 5 EUR."]).asks_one


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_question_the_read_finds_asking_two_things_is_refused_compound(
    language: str,
) -> None:
    """One question word over two asks is still two questions."""
    verifier = Reads(asks_one=False, recovers=_WELDED[language][2])

    result = build(verifier).check(_welded(language))

    assert result.rejected_reason == QuestionRejection.COMPOUND
    assert "round_trip" in result.gates_ran


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_question_the_read_finds_asking_one_thing_is_kept(language: str) -> None:
    """The same question and passage, read as one ask, is accepted."""
    verifier = Reads(asks_one=True, recovers=_WELDED[language][2])

    result = build(verifier).check(_welded(language))

    assert result.status == QuestionStatus.ACCEPTED


class Halves(PerHalf):
    """A verifier answering each half alone, and reading each as two asks."""

    def read(self, question: str, passages, thread=()) -> Reading:
        """Answers by the question, saying it asks two things."""
        return replace(super().read(question, passages, thread), asks_one=False)


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_compound_question_is_never_refused_for_asking_two_things(
    language: str,
) -> None:
    """It asks two on purpose, and its halves are read one at a time."""
    _, _, _, parts = _BANK[language]

    result = build(Halves({part[1]: part[2] for part in parts})).check(
        _compound(language)
    )

    assert result.rejected_reason is None


# ── A reason the passages give ─────────────────────────────────────────────

#: A why keyed with its own rule said again with "because": the passage, the
#: question and the key, by language.
_CIRCULAR = {
    "de": (
        "Die Bank nimmt eine Kündigung des Girokontos nur in Schriftform an.",
        "Warum muss eine Kündigung des Girokontos schriftlich erfolgen?",
        "Weil die Bank eine Kündigung nur in Schriftform annimmt.",
    ),
    "en": (
        "The shop only accepts returns that were announced before sending.",
        "Why must a return be announced before the parcel is sent?",
        "Because the shop only accepts returns that were announced before sending.",
    ),
}


def _why(language: str, question_type: str = "reason"):
    """The circular why, written from its own passage."""
    passage, question, key = _CIRCULAR[language]
    return candidate(
        question_text=question,
        target_answer=key,
        question_type=question_type,
        facts=group(source(statement=passage, language=language)),
    )


def test_the_read_says_whether_the_passages_give_a_reason() -> None:
    """A field of the read's own shape, carried onto the reading."""
    client = Client(in_passage=True, answer="because", reason_given=False)

    got = Verifier(client).read(_CIRCULAR["en"][1], [_CIRCULAR["en"][0]])

    assert got.reason_given is False
    assert "reason_given" in client.asked[-1][0]


def test_a_read_that_says_nothing_of_a_reason_reads_as_one_given() -> None:
    """A reply missing the field refuses nothing."""
    client = Client(in_passage=True, answer="because")

    assert Verifier(client).read("Why?", ["Because."]).reason_given


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_why_whose_passages_give_no_reason_beyond_the_rule_is_refused(
    language: str,
) -> None:
    """The key restates the rule in the passage's words, which no overlap sees."""
    verifier = Reads(reason_given=False, recovers=_CIRCULAR[language][2])

    result = build(verifier).check(_why(language))

    assert result.rejected_reason == QuestionRejection.NOT_RECOVERABLE


@pytest.mark.parametrize("language", ["de", "en"])
def test_a_why_whose_passages_give_a_reason_is_kept(language: str) -> None:
    """The same question and key, where the read finds a reason."""
    verifier = Reads(reason_given=True, recovers=_CIRCULAR[language][2])

    result = build(verifier).check(_why(language))

    assert result.status == QuestionStatus.ACCEPTED


def test_a_question_not_asking_why_is_not_held_to_a_reason() -> None:
    """The field speaks of a why; another type is read for its answer alone."""
    verifier = Reads(reason_given=False, recovers=_WELDED["en"][2])

    result = build(verifier).check(_welded("en"))

    assert result.status == QuestionStatus.ACCEPTED
