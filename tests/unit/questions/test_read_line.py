"""What `Verifier.read` hands back from the model's reply, where its mutants survived.

The read is the one call every answerable question asked cold gets, and the
checker reads `recovered` None as NOT IN PASSAGE. So an empty or padded
answer, an answer beside `in_passage` false, and the conversation a
follow-up is read in are each pinned here. The model is stood in for.
"""

from __future__ import annotations

from question_generation.verifier import Verifier


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


_PASSAGES = ["A replacement debit card costs 10 EUR."]


def test_an_answer_of_blanks_is_not_in_passage() -> None:
    """`in_passage` true with nothing in `answer` gives the checker nothing to compare."""
    read = Verifier(Client(in_passage=True, answer="   ")).read("What?", _PASSAGES)

    assert read.recovered is None


def test_the_answer_is_handed_back_without_its_padding() -> None:
    """The recovery is compared as words; the spaces around it are the model's."""
    read = Verifier(Client(in_passage=True, answer="  10 EUR \n")).read(
        "What does a replacement card cost?", _PASSAGES
    )

    assert read.recovered == "10 EUR"


def test_an_answer_beside_in_passage_false_is_not_taken() -> None:
    """NOT IN PASSAGE is the verdict, whatever the model wrote beside it."""
    read = Verifier(Client(in_passage=False, answer="10 EUR")).read(
        "What does a replacement card cost?", _PASSAGES
    )

    assert read.recovered is None


def test_a_follow_up_is_read_in_its_conversation() -> None:
    """Each earlier turn is shown with its answer, an unanswered one as not in the material."""
    client = Client(in_passage=True, answer="15 EUR")

    Verifier(client).read(
        "And an express one?",
        _PASSAGES,
        (("What does a replacement card cost?", "10 EUR"), ("Can it be sent abroad?", None)),
    )

    user = client.asked[-1][1]
    assert user.endswith(
        "Q: What does a replacement card cost?\nA: 10 EUR\n"
        "Q: Can it be sent abroad?\nA: not in the material\n"
        "Q: And an express one?"
    )
    assert "Question:" not in user


def test_a_question_asked_cold_is_read_alone() -> None:
    """No conversation, no turns: the question under its own label."""
    client = Client(in_passage=True, answer="10 EUR")

    Verifier(client).read("What does a replacement card cost?", _PASSAGES)

    assert client.asked[-1][1].endswith(
        "[1] A replacement debit card costs 10 EUR.\n\n"
        "Question: What does a replacement card cost?"
    )
