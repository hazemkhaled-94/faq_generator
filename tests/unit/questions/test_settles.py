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


def test_the_prompt_says_which_mistake_costs_more() -> None:
    """A question the material settles marks a correct chatbot wrong.

    That costs more than losing one test question, and the prompt says so.
    Nothing in it tells the model `silent` is the safe verdict: those anchors
    held it to "silent" on questions its own passages answer.
    """
    client = Client()

    Verifier(client).settles("When are refunds paid to visitors?", ["Text."])

    system = " ".join(client.asked[-1][0].split())
    assert "does not decide this case is `silent`" in system
    assert "marked WRONG for a correct reply" in system
    for anchor in ("throws away a sound test", "A correct answer whenever it is true"):
        assert anchor not in system


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


def test_a_yes_no_question_its_passage_states_is_answerable_after_all() -> None:
    """Asked with no question word, the statement said back is the yes."""
    from database.qa_generator import QuestionRejection

    client = Gating(CITED, Settling.ANSWERS)

    result = checked(client, question="Are refunds only paid to account holders?")

    assert result.rejected_reason == QuestionRejection.ANSWERABLE_AFTER_ALL
    assert len(client.systems) == 1, "the corpus is not asked once it is settled"


@pytest.mark.parametrize(
    ("question", "quote", "language", "verdict"),
    [
        ("May a card be used abroad?", "A card may be used abroad.", "en", "answers"),
        ("Ist das Gerät wasserdicht?", "Das Gerät ist wasserdicht.", "de", "answers"),
        (
            "When may a card be used abroad?",
            "A card may be used abroad.",
            "en",
            "silent",
        ),
        (
            "Wann ist das Gerät wasserdicht?",
            "Das Gerät ist wasserdicht.",
            "de",
            "silent",
        ),
    ],
)
def test_only_a_question_word_turns_its_statement_said_back_silent(
    question: str, quote: str, language: str, verdict: str
) -> None:
    """A yes or no is answered by the statement; a `when` is not."""
    from question_generation.checker import heard
    from question_generation.verifier import Settled

    settled = heard(Settled(verdict=Settling.ANSWERS, quote=quote), question, language)

    assert settled.verdict == verdict


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


class _Says:
    """A verifier settling every question with one quote."""

    def __init__(self, verdict: str, quote: str) -> None:
        """Initialises the stand-in with the verdict and quote it gives."""
        self.verdict, self.quote = verdict, quote

    def settles(self, question: str, passages):
        """Settles whatever it is asked, with its quote."""
        from question_generation.verifier import Settled

        return Settled(verdict=self.verdict, quote=self.quote)


def test_a_quote_the_passages_do_not_hold_settles_nothing(caplog) -> None:
    """A verdict resting on words no passage shown carries came from somewhere else.

    A model that knows a famous rulebook can settle a question from memory,
    and the passages a chatbot will read leave it open.
    """
    from question_generation.checker import settle

    with caplog.at_level("INFO", logger="question_generation.checker"):
        failed, opinions = settle(
            _Says(Settling.RULE, "Refunds are only paid to account holders."),
            "When are refunds paid to visitors?",
            "en",
            ["Standard requests are answered within 48 hours."],
            None,
        )

    assert failed is None
    assert opinions[0].value == 1.0
    assert "not in the passages" in caplog.text


@pytest.mark.parametrize(
    "passage",
    [
        "Refunds are only paid to\naccount holders.",
        "REFUNDS are only paid to account holders.",
        "Refunds are only paid to ‘account holders’.",
    ],
)
def test_a_quote_the_passages_hold_however_spaced_still_settles(passage) -> None:
    """A line break, a capital or a curly quote does not make a quote invented."""
    from database.qa_generator import QuestionRejection
    from question_generation.checker import settle

    quote = (
        "Refunds are only paid to 'account holders'."
        if "‘" in passage
        else "Refunds are only paid to account holders."
    )
    failed, _ = settle(
        _Says(Settling.RULE, quote),
        "When are refunds paid to visitors?",
        "en",
        [passage],
        None,
    )

    assert failed is not None
    assert failed[0] == QuestionRejection.ANSWERABLE_AFTER_ALL


def _settled_by(quote: str, passages: list[str], language: str = "en"):
    """What `settle` makes of a `rule` quoting these words, with no probe."""
    from question_generation.checker import settle

    failed, _ = settle(
        _Says(Settling.RULE, quote),
        "When is the fee charged?",
        language,
        passages,
        None,
    )
    return failed


@pytest.mark.parametrize(
    ("quote", "passage"),
    [
        (
            "Fees for the current account: Debit card: 10 EUR per year",
            (
                "Fees for the current account:\n"
                "- Account management: 4.90 EUR per month\n"
                "- Debit card: 10 EUR per year"
            ),
        ),
        (
            "1. Account management 4.90 EUR per month 2. Debit card 10 EUR per year",
            "1. Account management 4.90 EUR per month\n2. Debit card 10 EUR per year",
        ),
    ],
    ids=["two bullets of one list", "a numbered list said back on one line"],
)
def test_a_quote_stitched_from_the_lines_of_one_list_settles(quote, passage) -> None:
    """A verifier quoting a list joins its items; the passage holds each one."""
    from database.qa_generator import QuestionRejection

    failed = _settled_by(quote, ["Opening hours are 9:00 to 18:00.", passage])

    assert failed is not None
    assert failed[0] == QuestionRejection.ANSWERABLE_AFTER_ALL


def test_a_quote_stitched_from_the_cells_of_one_table_row_settles() -> None:
    """A row read as `item | value` skips the cells between."""
    from database.qa_generator import QuestionRejection

    table = (
        "| Artikel | Preis | Lieferzeit |\n"
        "| --- | --- | --- |\n"
        "| Kaffeemaschine | 89 EUR | 3 Werktage |\n"
        "| Wasserkocher | 29 EUR | 2 Werktage |"
    )

    failed = _settled_by("Kaffeemaschine | 3 Werktage", [table], "de")

    assert failed is not None
    assert failed[0] == QuestionRejection.ANSWERABLE_AFTER_ALL


@pytest.mark.parametrize(
    "quote",
    ["Refunds: within 14 days", "Refunds ... within 14 days"],
    ids=["joined at a colon", "joined at an ellipsis"],
)
def test_a_word_of_one_passage_beside_a_piece_of_another_settles_nothing(
    quote,
) -> None:
    """One word proves nothing away from the passage the rest is quoted from.

    `Refunds:` heads one passage and `within 14 days` is a delivery time in
    another, so neither says how long a refund takes.
    """
    failed = _settled_by(
        quote,
        [
            "Refunds:\nA gift card is paid back to the card it was bought with.",
            "Orders are delivered within 14 days.",
        ],
    )

    assert failed is None


@pytest.mark.parametrize(
    ("quote", "passage", "language"),
    [
        ("Ja", "Die Jahresgebühr der Kreditkarte beträgt 30 EUR.", "de"),
        ("No", "Cash withdrawals abroad are normally not free.", "en"),
        (
            "Fees: card",
            "Fees: cardholders pay 2 % on withdrawals abroad.",
            "en",
        ),
    ],
)
def test_a_quote_piece_inside_a_longer_word_settles_nothing(
    quote, passage, language
) -> None:
    """`Ja` is not in `Jahresgebühr`, nor `card` in `cardholders`."""
    assert _settled_by(quote, [passage], language) is None


def test_a_verdict_is_recorded_with_the_prompt_it_was_given_under() -> None:
    """So a rewritten prompt's rejudge can tell its verdicts from the old ones."""
    from question_generation.verifier import Settled

    recorded = (
        Settled(verdict=Settling.SILENT, quote=None).reading("settles").recorded()
    )

    assert recorded["version"] == PROMPT_VERSION


# ── Whether two released questions want one answer ─────────────────────────


class _Twins:
    """A served model that says whether two questions want one answer."""

    model = "fake/verifier"

    def __init__(self, same: bool) -> None:
        """Initialises the model with the verdict it gives."""
        self.same = same
        self.asked: list[tuple[str, str]] = []

    def answer(self, *, system: str, user: str, shape, prompt_version=None):
        """Records the call and answers in the shape asked for."""
        self.asked.append((system, user))
        return shape(same=self.same)


def test_two_questions_are_put_to_the_judge_with_their_keys() -> None:
    """One correct reply serving both is what makes two questions one test."""
    client = _Twins(same=True)

    same = Verifier(client).same_answer(
        ("How fast is an urgent request answered?", "within 4 hours"),
        ("Within what time must an urgent request be answered?", "4 hours"),
    )

    system, user = client.asked[-1]
    assert same is True
    assert "How fast is an urgent request answered?" in user
    assert "within 4 hours" in user and "4 hours" in user
    assert re.search(r"same answer", system, re.IGNORECASE)


def test_a_question_written_to_have_no_answer_is_put_with_none() -> None:
    """Two unanswerable questions are twins when they ask after one gap."""
    client = _Twins(same=False)

    Verifier(client).same_answer(("Q one?", None), ("Q two?", None))

    assert "not in the material" in client.asked[-1][1]
