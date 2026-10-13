"""What `make questions-rejudge` does with the accepted unanswerable questions.

Each was accepted when the verifier, asked for an answer stated outright,
found none. The re-judge asks whether the passages settle it - stated,
refuted, or covered by a list or a rule - over what it cites and then over
the corpus probe, and rejects what they settle. The verifier is the real one
over a stand-in client; the catalogue answers from memory.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from unit.questions.test_question_service import SETTINGS

from database.qa_generator import QuestionRejection, ReviewVerdict
from question_generation.models import Unanswered
from question_generation.service import rejudge
from question_generation.verifier import Settling, Verifier

pytestmark = pytest.mark.nlp

CITED = "Refunds are only paid to account holders."
PROBED = "A visitor is refunded at the front desk."


class Client:
    """A served model that settles a question when it is shown one text."""

    model = "fake/verifier"

    def __init__(self, settled_by: str | None, verdict: str = Settling.REFUTES):
        """Initialises with the passage that settles, and how it does."""
        self.settled_by = settled_by
        self.verdict = verdict
        self.shown: list[str] = []

    def answer(self, *, system, user, shape, prompt_version=None):
        """Settles where the passage it was told about is in the message."""
        self.shown.append(user)
        if self.settled_by and self.settled_by in user:
            return shape(verdict=self.verdict, quote=self.settled_by)
        return shape(verdict=Settling.SILENT, quote="")


class Catalog:
    """The accepted unanswerable questions, the probe, and what was rejected."""

    def __init__(self, *questions: Unanswered) -> None:
        """Holds the questions; nothing probed or rejected yet."""
        self.questions = list(questions)
        self.probed: list[tuple] = []
        self.rejected: list[tuple[int, str]] = []

    def unanswered(self, within=None):
        """Every accepted question written to have no answer."""
        return list(self.questions)

    def elsewhere(self, lemmas, language, skip, limit, embedding=None):
        """The uncited passages the probe hands the verifier."""
        self.probed.append((tuple(skip), limit, embedding))
        return [PROBED]

    def reject(self, verdicts):
        """Records the rejections."""
        self.rejected.extend(verdicts)
        return len(verdicts)


def unanswered(**columns) -> Unanswered:
    """One accepted unanswerable question citing one passage."""
    return Unanswered(
        **{
            "id": 7,
            "question_text": "When is a visitor refunded?",
            "language": "en",
            "reviewed_verdict": None,
            "embedding": [1.0, 0.0],
            "passage_ids": (3,),
            "passages": (CITED,),
            **columns,
        }
    )


def test_a_question_its_own_passages_settle_is_answerable_after_all() -> None:
    """The premise refuted by the passage it cites: a visitor is never paid."""
    catalog = Catalog(unanswered())
    settings = replace(SETTINGS, elsewhere_passages=10)

    rejected = rejudge(catalog, settings, Verifier(Client(CITED)))

    assert rejected == 1
    assert catalog.rejected == [(7, QuestionRejection.ANSWERABLE_AFTER_ALL)]
    assert catalog.probed == [], "settled before the corpus was asked"


def test_a_question_an_uncited_passage_settles_is_answerable_elsewhere() -> None:
    """Probed past its own passages, with what the checker probes with."""
    catalog = Catalog(unanswered())
    settings = replace(SETTINGS, elsewhere_passages=10)

    rejudge(catalog, settings, Verifier(Client(PROBED, Settling.ANSWERS)))

    assert catalog.rejected == [(7, QuestionRejection.ANSWERABLE_ELSEWHERE)]
    assert catalog.probed == [((3,), 10, [1.0, 0.0])]


def test_a_question_nothing_settles_is_kept() -> None:
    """Silent twice, which is what a question with no answer is."""
    catalog = Catalog(unanswered())
    client = Client(None)

    rejected = rejudge(
        catalog, replace(SETTINGS, elsewhere_passages=10), Verifier(client)
    )

    assert rejected == 0
    assert catalog.rejected == []
    assert len(client.shown) == 2, "its own passages, then the probe"


def test_no_probe_is_asked_where_none_is_configured() -> None:
    """QUESTIONS_ELSEWHERE_PASSAGES=0 judges one against its own passages."""
    catalog = Catalog(unanswered())
    client = Client(PROBED)

    rejudge(catalog, replace(SETTINGS, elsewhere_passages=0), Verifier(client))

    assert catalog.probed == []
    assert len(client.shown) == 1


def test_a_question_a_person_accepted_is_left_alone() -> None:
    """No gate here overrules the person, as in a re-check."""
    catalog = Catalog(unanswered(reviewed_verdict=ReviewVerdict.ACCEPTED))
    client = Client(CITED)

    rejudge(catalog, SETTINGS, Verifier(client))

    assert catalog.rejected == []
    assert client.shown == [], "nobody's decision was worth a call to second-guess"


@pytest.mark.parametrize("verdict", [Settling.ANSWERS, Settling.REFUTES, Settling.RULE])
def test_every_way_of_settling_it_rejects_it(verdict: str) -> None:
    """Stated, refuted or covered: a chatbot that says so is right."""
    catalog = Catalog(unanswered())

    rejudge(catalog, SETTINGS, Verifier(Client(CITED, verdict)))

    assert catalog.rejected == [(7, QuestionRejection.ANSWERABLE_AFTER_ALL)]


#: A rule, and a `why` it gives no reason for: quoted back, it restates it.
RULE = "A senior officer must sign a transfer before it is released."
WHY = "Why must a senior officer sign a transfer before it is released?"


@pytest.mark.parametrize(
    ("verdict", "rejected"),
    [
        (Settling.ANSWERS, []),
        (Settling.REFUTES, [(7, QuestionRejection.ANSWERABLE_AFTER_ALL)]),
        (Settling.RULE, [(7, QuestionRejection.ANSWERABLE_AFTER_ALL)]),
    ],
)
def test_a_quote_that_only_says_the_question_back_is_read_as_the_checker_reads_it(
    verdict: str, rejected: list
) -> None:
    """An `answers` that restates the question is silent; a rule is not."""
    catalog = Catalog(unanswered(question_text=WHY, passages=(RULE,)))

    rejudge(catalog, SETTINGS, Verifier(Client(RULE, verdict)))

    assert catalog.rejected == rejected
