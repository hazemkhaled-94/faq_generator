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
        """Holds the questions; nothing probed, judged or rejected yet."""
        self.questions = list(questions)
        self.probed: list[tuple] = []
        self.rejected: list[tuple[int, str]] = []
        self.opined: dict[int, list] = {}
        #: Whether writing a rejection fails, as a write the database refuses
        #: does: the whole of that write, verdicts included, is lost.
        self.failing = False

    def unanswered(self, within=None):
        """Every accepted question written to have no answer, as stored now."""
        return [
            replace(one, judged=one.judged or one.id in self.opined)
            for one in self.questions
            if one.id not in {qid for qid, _ in self.rejected}
        ]

    def opine(self, question_id, opinions, rejected=None):
        """Records the verdicts and the rejection, both or neither."""
        if rejected and self.failing:
            raise RuntimeError("the rejection could not be written")
        self.opined.setdefault(question_id, []).extend(opinions)
        if rejected:
            self.rejected.append((question_id, rejected))
        return bool(rejected)

    def elsewhere(self, lemmas, language, skip, limit, embedding=None):
        """The uncited passages the probe hands the verifier."""
        self.probed.append((tuple(skip), limit, embedding))
        return [PROBED]


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


def test_each_verdict_is_written_to_the_row_as_an_opinion() -> None:
    """What the verifier made of it, kept on the row, rejected or not."""
    catalog = Catalog(unanswered(), unanswered(id=8))
    settings = replace(SETTINGS, elsewhere_passages=10)

    rejudge(catalog, settings, Verifier(Client(PROBED)))

    for qid in (7, 8):
        written = catalog.opined[qid]
        assert [one.gate for one in written] == ["settles", "settles_elsewhere"]
        assert [one.value for one in written] == [1.0, 0.0]
        assert all(one.opinion for one in written)


def test_a_second_run_asks_nothing_about_what_a_first_judged() -> None:
    """Silent ones included.

    A re-run, or one after an interruption, costs only what no run has
    paid for yet.
    """
    catalog = Catalog(unanswered(), unanswered(id=8))
    client = Client(None)
    settings = replace(SETTINGS, elsewhere_passages=10)
    rejudge(catalog, settings, Verifier(client))
    asked = len(client.shown)
    assert asked == 4, "both kept, each asked of its passages and the probe"

    again = rejudge(catalog, settings, Verifier(client))

    assert again == 0
    assert len(client.shown) == asked, "a judged question was asked again"


def test_a_rejection_that_fails_leaves_the_question_to_be_asked_again() -> None:
    """The verdict and the rejection are one write.

    Written apart, a run dying between them left a settled verdict on an
    accepted row, and every later run skipped it as judged.
    """
    catalog = Catalog(unanswered())
    catalog.failing = True
    client = Client(CITED)

    with pytest.raises(RuntimeError):
        rejudge(catalog, SETTINGS, Verifier(client))

    assert catalog.opined == {}
    assert not catalog.unanswered()[0].judged
    catalog.failing = False

    rejudge(catalog, SETTINGS, Verifier(client))

    assert len(client.shown) == 2, "asked again on the second run"
    assert catalog.rejected == [(7, QuestionRejection.ANSWERABLE_AFTER_ALL)]


def test_a_question_the_checker_already_judged_is_not_asked_again() -> None:
    """Written since `settles` gated generation, it carries the verdict."""
    catalog = Catalog(unanswered(judged=True))
    client = Client(CITED)

    rejudge(catalog, SETTINGS, Verifier(client))

    assert client.shown == []
    assert catalog.rejected == []


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


def test_a_quote_read_as_silent_is_logged_with_the_question(caplog) -> None:
    """The row keeps only the silence, so the quote it overrode is logged."""
    catalog = Catalog(unanswered(question_text=WHY, passages=(RULE,)))

    with caplog.at_level("INFO", logger="question_generation.checker"):
        rejudge(catalog, SETTINGS, Verifier(Client(RULE, Settling.ANSWERS)))

    (line,) = [one for one in caplog.messages if "as silent" in one]
    assert "question 7" in line and RULE in line


@pytest.mark.parametrize(
    ("settled_by", "rejection"),
    [
        (CITED, QuestionRejection.ANSWERABLE_AFTER_ALL),
        (PROBED, QuestionRejection.ANSWERABLE_ELSEWHERE),
    ],
)
def test_the_rejudge_settles_a_question_as_the_checker_does(
    caplog, settled_by: str, rejection: str
) -> None:
    """One sequence for both, so the two give one reason for one verdict."""
    from factories import candidate, group, source
    from unit.questions.test_verification import Recording

    from question_generation.checker import QuestionChecker

    stand_in = Recording(recovers=None)
    checked = QuestionChecker(
        embedder=stand_in,
        verifier=Verifier(Client(settled_by)),
        nearest=lambda embedding, **_: None,
        threshold=0.93,
        phrasing=stand_in,
        elsewhere=lambda *a, **k: [PROBED],
        elsewhere_passages=10,
    )
    with caplog.at_level("INFO", logger="question_generation.checker"):
        written = checked.check(
            candidate(
                question_text="When is a visitor refunded?",
                target_answer=None,
                answerable=False,
                facts=group(source(1, statement=CITED, passage_text=CITED)),
            )
        )
    with caplog.at_level("INFO", logger="question_generation.service"):
        rejudge(
            Catalog(unanswered()),
            replace(SETTINGS, elsewhere_passages=10),
            Verifier(Client(settled_by)),
        )

    assert written.rejected_reason == rejection
    by_checker = [one for one in caplog.messages if one.startswith("rejected ")]
    by_rejudge = [one for one in caplog.messages if one.startswith("rejecting ")]
    assert by_checker[-1].split(": ", 1)[1] == by_rejudge[-1].split(": ", 1)[1]


class Refusing(Client):
    """A served model that will not answer about one question, as a filter does."""

    def __init__(self, refused: str, settled_by: str | None = CITED) -> None:
        """Initialises with the question it refuses, and what settles the rest."""
        super().__init__(settled_by)
        self.refused = refused

    def answer(self, *, system, user, shape, prompt_version=None):
        """Raises for the refused question; settles the others as before."""
        if self.refused in user:
            from llm.client import ModelUnavailable

            raise ModelUnavailable("the content filter refused the request")
        return super().answer(
            system=system, user=user, shape=shape, prompt_version=prompt_version
        )


def test_a_question_the_model_will_not_answer_is_left_for_the_next_run(
    caplog,
) -> None:
    """The others are judged; that one is written nothing, so it is asked again."""
    refused = "When is a guest refunded?"
    catalog = Catalog(unanswered(question_text=refused), unanswered(id=8))

    with caplog.at_level("INFO", logger="question_generation.service"):
        rejected = rejudge(catalog, SETTINGS, Verifier(Refusing(refused)))

    assert rejected == 1
    assert catalog.rejected == [(8, QuestionRejection.ANSWERABLE_AFTER_ALL)]
    assert 7 not in catalog.opined
    assert not next(one for one in catalog.unanswered() if one.id == 7).judged
    assert any("question 7" in one for one in caplog.messages)
    assert "1 the model would not answer" in caplog.messages[-1]


class Dead(Client):
    """A served model that answers nothing: bad credentials, an unknown model."""

    def __init__(self) -> None:
        """Initialises with no call made."""
        super().__init__(None)
        self.calls = 0

    def answer(self, *, system, user, shape, prompt_version=None):
        """Raises as the client does for every failure, whatever its cause."""
        from llm.client import ModelUnavailable

        self.calls += 1
        raise ModelUnavailable("AuthenticationError: the key was refused")


def test_a_verifier_that_never_answers_stops_the_run() -> None:
    """Five refusals in a row is a dead model, not a filter: the run fails."""
    from llm.client import ModelUnavailable

    catalog = Catalog(*(unanswered(id=qid) for qid in range(1, 21)))
    client = Dead()

    with pytest.raises(ModelUnavailable, match="the key was refused"):
        rejudge(catalog, SETTINGS, Verifier(client))

    assert client.calls == 5
    assert catalog.opined == {}


def test_an_answered_question_between_refusals_keeps_the_run_going() -> None:
    """Only refusals in a row count, so a filter on a few ids stops nothing."""
    refused = "When is a guest refunded?"
    catalog = Catalog(
        *(unanswered(id=qid, question_text=refused) for qid in range(1, 5)),
        unanswered(id=5),
        *(unanswered(id=qid, question_text=refused) for qid in range(6, 10)),
    )

    rejected = rejudge(catalog, SETTINGS, Verifier(Refusing(refused)))

    assert rejected == 1
    assert catalog.rejected == [(5, QuestionRejection.ANSWERABLE_AFTER_ALL)]
