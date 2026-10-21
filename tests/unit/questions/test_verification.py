"""Every gate, and the order they are applied in.

The order is not a detail. Each gate that fires saves the cost of the ones
behind it, and the only expensive one is last, so a test that lets a
malformed question reach the verifier is a test of a bill.
"""

from __future__ import annotations

import inspect
from dataclasses import replace

import pytest
from factories import candidate, group, source

from database.qa_generator import (
    AnswerForm,
    FactKind,
    QuestionRejection,
    QuestionStatus,
    QuestionType,
)
from llm.client import ModelRefused, ModelUnavailable
from question_generation.checker import QuestionChecker
from question_generation.config import Settings
from question_generation.gates import (
    OVERLAP,
    _folded,
    adds_up,
    agrees,
    anchored,
    asked_as,
    asks_for_an_agent,
    asserted,
    compares,
    enumerates,
    explains,
    fitting,
    incomplete,
    moves_on,
    names_parties,
    near_verdict,
    on_topic,
    periods,
    recalled,
    restates,
    same_material,
    structural,
    unnamed,
)
from question_generation.models import Neighbour
from question_generation.verifier import (
    STATED_VERSION,
    Part,
    Reading,
    Settled,
    Settling,
    Verifier,
)

pytestmark = pytest.mark.nlp


def code(failed) -> str | None:
    """The gate's code out of a verdict, or None when it passed."""
    return failed[0] if failed else None


#: What each form is held to unless a test says otherwise. The value floor is
#: 1, as the setting ships.
BOUNDS = {"value": (1, 80), "list": (3, 300), "explanation": (20, 600)}


def checked(**kwargs):
    """Runs the free gates over one candidate's fields.

    Takes `form` singular and hands back the verdict alone. `structural`
    takes every form a type will accept and reports which one the answer
    turned out to fit; these tests are about the gates rather than about
    that choice, so they pin one form and read the verdict. What happens
    when a type allows several is covered in `test_fitting` below.
    """
    fields = {
        "question_text": "What does the device weigh?",
        "target_answer": "4 kg",
        "answerable": True,
        "language": "en",
        "statements": (),
        "form": AnswerForm.VALUE,
        "bounds": BOUNDS,
        "titles": (),
        **kwargs,
    }
    failed, _ = structural(forms=(fields.pop("form"),), **fields)
    return failed


# ── The free gates ─────────────────────────────────────────────────────────


def test_a_well_formed_question_passes() -> None:
    """The case every rejection below is measured against."""
    assert checked() is None


@pytest.mark.parametrize(
    ("why", "fields"),
    [
        ("nothing at all", {"question_text": "   "}),
        ("not a question", {"question_text": "The device weighs 4 kg."}),
        ("no target answer", {"target_answer": None}),
        ("a blank target answer", {"target_answer": "  "}),
        (
            "an unanswerable one with an answer",
            {"answerable": False, "target_answer": "4 kg"},
        ),
    ],
)
def test_what_counts_as_malformed(why: str, fields: dict) -> None:
    """Five ways of being unusable, under one code."""
    assert code(checked(**fields)) == QuestionRejection.MALFORMED, why


def test_a_query_needs_no_question_mark() -> None:
    """Keywords typed into a search box end where the keywords do."""
    asked = {
        "question_text": "transfer abroad fee debit card",
        "target_answer": "5 euros",
        "answerable": True,
        "language": "en",
    }

    assert structural(**asked, query=True)[0] is None
    assert structural(**asked, query=False)[0] == (
        QuestionRejection.MALFORMED,
        "it does not end in a question mark",
    )


def test_a_query_still_asks_one_thing() -> None:
    """Only the end-'?' rule is lifted: two question marks are two asks."""
    failed, _ = structural(
        question_text="Going abroad? Which fee applies to a card payment?",
        target_answer="a flat fee of 5 euros",
        answerable=True,
        language="en",
        query=True,
    )

    assert code(failed) == QuestionRejection.MALFORMED


def test_a_fact_handed_straight_back_is_not_a_question() -> None:
    """The laziest thing a model can do with the prompt."""
    failed = checked(
        question_text="The device weighs 4 kg?",
        statements=("The device weighs 4 kg.",),
    )

    assert code(failed) == QuestionRejection.MALFORMED


def test_an_unanswerable_question_needs_no_target_answer() -> None:
    """It is scored on behaviour, which is what the table's CHECK says."""
    assert checked(answerable=False, target_answer=None) is None


def test_a_question_in_the_wrong_language_is_refused() -> None:
    """A German corpus answering English questions measures a translator."""
    failed = checked(
        question_text=(
            "Within how many hours is a standard support request answered "
            "on an ordinary working day?"
        ),
        target_answer="within 48 hours of the request being raised",
        language="de",
    )

    assert code(failed) == QuestionRejection.MALFORMED


def test_a_question_too_short_to_read_is_not_called_the_wrong_language() -> None:
    """Lingua answers nothing below forty characters of prose.

    Most questions are shorter than that, so a gate that treated `cannot
    tell` as `wrong` would reject almost everything.
    """
    assert (
        checked(question_text="Wie schwer?", target_answer="4 kg", language="de")
        is None
    )


# ── The probe ──────────────────────────────────────────────────────────────


def test_nothing_near_enough_is_not_a_duplicate() -> None:
    """The threshold is what makes the gate a gate."""
    near = Neighbour("Something else entirely?", answerable=True, similarity=0.5)

    assert near_verdict(near, answerable=True, threshold=0.93) is None


def test_an_empty_corpus_of_questions_rejects_nothing() -> None:
    """The first question of a run has nothing to be a duplicate of."""
    assert near_verdict(None, answerable=True, threshold=0.93) is None


def test_a_near_twin_of_an_accepted_question_is_a_duplicate() -> None:
    """A benchmark that asks the same thing twice weights it twice."""
    near = Neighbour("What is the weight?", answerable=True, similarity=0.97)

    assert code(near_verdict(near, answerable=True, threshold=0.93)) == (
        QuestionRejection.DUPLICATE
    )


def test_a_near_twin_asking_with_the_same_word_is_a_duplicate() -> None:
    """The veto needs the question words to differ."""
    near = Neighbour(
        "Why must a request be confirmed in writing?",
        answerable=True,
        similarity=0.95,
        passage_ids=frozenset({1}),
    )

    assert code(
        near_verdict(
            near,
            answerable=True,
            threshold=0.93,
            question="Why does a request have to be confirmed in writing?",
            language="en",
            passages=(1,),
        )
    ) == (QuestionRejection.DUPLICATE)


def _twin(similarity: float, **cited) -> tuple[str, str] | None:
    """A neighbour asking with the same word, against what the two cite.

    `cited` takes `facts` and `passages`, which the candidate and the
    neighbour both cite: the candidate fact 1 and passage 1 besides.
    """
    facts, passages = cited.get("facts", ()), cited.get("passages", ())
    near = Neighbour(
        "What does the device weigh?",
        answerable=True,
        similarity=similarity,
        fact_ids=frozenset(facts),
        passage_ids=frozenset(passages),
    )
    return near_verdict(
        near,
        answerable=True,
        threshold=0.93,
        shared_threshold=0.88,
        question="What is the weight of the device?",
        language="en",
        facts=(9, *facts),
        passages=(9, *passages),
    )


def test_two_questions_on_one_fact_are_twins_at_the_lower_bar() -> None:
    """Resting on the same fact is the strongest sign two ask the same thing."""
    assert code(_twin(0.90, facts=(1,), passages=(1,))) == QuestionRejection.DUPLICATE
    assert _twin(0.87, facts=(1,), passages=(1,)) is None


def test_a_shared_passage_alone_holds_a_pair_to_the_duplicate_bar() -> None:
    """A passage carries several claims, so sharing one says less."""
    assert _twin(0.90, passages=(1,)) is None
    assert code(_twin(0.94, passages=(1,))) == QuestionRejection.DUPLICATE


def test_two_questions_citing_nothing_in_common_are_twins_only_near_identical() -> None:
    """The cosine is the only evidence, so only a restatement is refused.

    The path a question rewritten from another passage or another document
    takes, which fact dedup leaves to this gate.
    """
    assert _twin(0.95) is None
    assert code(_twin(0.97)) == QuestionRejection.DUPLICATE


def test_a_different_question_word_lifts_even_a_shared_fact_to_the_highest_bar() -> (
    None
):
    """`When` and then `why` about one fact is what a thread is."""
    near = Neighbour(
        "When must a request be confirmed in writing?",
        answerable=True,
        similarity=0.95,
        fact_ids=frozenset({1}),
    )

    got = near_verdict(
        near,
        answerable=True,
        threshold=0.93,
        shared_threshold=0.88,
        question="Why must a request be confirmed in writing?",
        language="en",
        facts=(1,),
    )

    assert got is None


def test_a_twin_asking_another_thing_is_a_duplicate_above_the_higher_bar() -> None:
    """Past halfway from the threshold to identical, the words do not matter."""
    near = Neighbour(
        "Which requests have to be confirmed in writing?",
        answerable=True,
        similarity=0.97,
    )

    assert code(
        near_verdict(
            near,
            answerable=True,
            threshold=0.93,
            question="Why does a request have to be confirmed in writing?",
            language="en",
        )
    ) == (QuestionRejection.DUPLICATE)


def test_an_unanswerable_twin_of_an_answered_question_is_answerable_after_all() -> None:
    """One probe, two gates.

    If the corpus already answers a question this close, resting on the
    same fact, this one is not unanswerable, whatever the perturbation
    prompt intended.
    """
    near = Neighbour(
        "What does the device weigh?",
        answerable=True,
        similarity=0.96,
        fact_ids=frozenset({1}),
    )

    assert code(near_verdict(near, answerable=False, threshold=0.93, facts=(1,))) == (
        QuestionRejection.ANSWERABLE_AFTER_ALL
    )


def test_nearness_alone_to_an_answered_question_is_not_an_answer() -> None:
    """A perturbation sits near the question about its own fact by design.

    `What does the device weigh on the moon?` is written by moving `4 kg`
    just out of reach, so it is close to `What does the device weigh?`
    whatever the material says about the moon. Only a neighbour resting on
    the same fact says the corpus answers it; any other is left to the
    passage read.
    """
    near = Neighbour(
        "What does the device weigh?",
        answerable=True,
        similarity=0.96,
        fact_ids=frozenset({2}),
    )

    assert near_verdict(near, answerable=False, threshold=0.93, facts=(1,)) is None


def test_an_answerable_question_is_never_a_duplicate_of_an_unanswerable_one() -> None:
    """Refusing it would keep the claim that there is no answer, and drop the answer.

    The two are different items whatever their vectors say: one asks a
    chatbot for a value, the other asks it to decline. Whether the
    unanswerable one is wrong is for the unanswerable checks to say.
    """
    near = Neighbour(
        "What does the device weigh on the moon?",
        answerable=False,
        similarity=0.96,
        fact_ids=frozenset({1}),
    )

    assert near_verdict(near, answerable=True, threshold=0.93, facts=(1,)) is None


def test_a_question_in_another_language_is_not_a_twin() -> None:
    """A bilingual set asks each language its own questions.

    A question and its translation are one item each, so the gate compares
    a question only with the accepted questions of its own language.
    """
    near = Neighbour(
        "Wie schwer ist das Gerät?", answerable=True, similarity=0.99, language="de"
    )

    assert near_verdict(near, answerable=True, threshold=0.93, language="en") is None


def test_two_unanswerable_near_twins_are_only_duplicates() -> None:
    """Neither of them is evidence the corpus answers anything."""
    near = Neighbour(
        "What about on Mars?",
        answerable=False,
        similarity=0.96,
        passage_ids=frozenset({1}),
    )

    assert code(
        near_verdict(near, answerable=False, threshold=0.93, passages=(1,))
    ) == (QuestionRejection.DUPLICATE)


# ── Agreement between the verifier and the target ──────────────────────────


def test_the_verifier_agrees_when_it_recovered_every_unit_of_the_target() -> None:
    """Wording is free to differ; the numbers and names are not."""
    assert agrees("48 hours", "within 48 hours", "en")


def test_the_verifier_disagrees_on_a_different_number() -> None:
    """The failure an embedding comparison lets through.

    `4 hours` and `48 hours` are close in every vector space and are not the
    same answer.
    """
    assert not agrees("4 hours", "48 hours", "en")


# Every pair below is one the verifier really produced. The four marked SAME
# were all refused by the string containment this replaced.


@pytest.mark.parametrize(
    ("recovered", "target"),
    [
        (
            "Die Darstellung der zukünftigen Entwicklung und der Risiken.",
            "zukünftige Entwicklung und Risiken",
        ),
        (
            (
                "kapitalbildende Lebensversicherungen, die einen angemessenen "
                "Kundennutzen aufweisen."
            ),
            "kapitalbildend und einen angemessenen Kundennutzen",
        ),
        (
            "Digitalisierung, Nachhaltigkeit, geopolitische Umbrüche",
            "Digitalisierung und Nachhaltigkeit",
        ),
    ],
)
def test_an_inflection_is_not_a_disagreement(recovered, target) -> None:
    """German declines, and a declension is not a different answer.

    Compared on content lemmas for that reason. Containment refused all
    three, and a person reading either column calls them the same.
    """
    assert agrees(recovered, target, "de")


@pytest.mark.parametrize(
    ("recovered", "target"),
    [
        ("die qualitative Aufsicht in Deutschland", "Regelungsrahmen"),
        (
            "Konditionen- und Strukturbeitrag im Zinsbuch",
            "Abgrenzung der Erfolgsquellen",
        ),
        (
            "die Art der vergebenen Kredite und die Kreditvergabepraxis der Fonds",
            "langer Anlagehorizont",
        ),
        (
            (
                "einfacheren Verschuldungsquote und deutlich über dem "
                "Basel-III-Mindestwert von 3 Prozent"
            ),
            "kleinere und nicht-komplexe Banken",
        ),
    ],
)
def test_a_different_answer_is_still_refused(recovered, target) -> None:
    """Loosening the comparison must not accept a wrong answer.

    These are the pairs where the verifier answered something else, and none
    of them may pass: a question scored against an answer the material does
    not give marks a chatbot wrong for being right.
    """
    assert not agrees(recovered, target, "de")


def test_an_answer_claiming_more_than_was_found_is_refused() -> None:
    """Five things asked for and three recovered is not agreement."""
    assert not agrees(
        "Genauigkeit, Stabilität und Konsistenz der Verfahren",
        "die Qualität der Modellergebnisse, die Genauigkeit, die Stabilität, "
        "die Konsistenz und die Erklärbarkeit",
        "de",
    )


def test_a_lemma_the_pipeline_gets_wrong_is_a_known_miss() -> None:
    """`de_core_news_md` leaves `Umbrüchen` alone and lemmatises `Umbrüche`.

    So these two, which are the same answer, do not meet. Recorded rather
    than fixed: stemming would close it and would open false accepts.
    """
    assert not agrees(
        "geopolitische Umbrüchen und fortschreitender Digitalisierung",
        "geopolitische Umbrüche und fortschreitende Digitalisierung",
        "de",
    )


def test_a_target_with_no_content_word_falls_back_to_containment() -> None:
    """A bare yes has no lemma to compare, so containment is all there is."""
    assert agrees("ja, das ist zulässig", "ja", "de")
    assert not agrees("nein", "ja", "de")


# ── The gates in order ─────────────────────────────────────────────────────


class Recording:
    """An embedder and a verifier that count how often they were asked."""

    def __init__(
        self,
        vector: list[float] | None = None,
        recovers: str | None = "4 kg",
        stands_alone: bool = True,
        names_its_source: bool = False,
        backs: bool = False,
        self_contained: bool = True,
    ):
        """Initialises with what to answer, and nothing asked yet."""
        self.vector = vector or [1.0] + [0.0] * 1023
        self.recovers = recovers
        self.stands_alone = stands_alone
        #: What the phrasing judge answers, for the residue a rule leaves.
        #: Named apart from the methods that serve them, which the checker
        #: calls and which count the ask.
        self.names_source = names_its_source
        self.contained = self_contained
        self.phrased = 0
        #: What the entailment pass answers. False by default, so a test
        #: about recall measures recall: the pass can only ever rescue, and
        #: one that always said yes would hide every rejection below it.
        self.backs = backs
        self.threaded: tuple = ()
        self.embedded = 0
        self.verified = 0
        self.supported = 0
        self.stated_asked = 0

    def embed(self, text: str) -> list[float]:
        """Answers with the one vector, and counts the ask."""
        self.embedded += 1
        return self.vector

    def read(self, question: str, passages, thread=()) -> Reading:
        """Answers with the scripted reading, and counts the ask."""
        self.verified += 1
        self.threaded = tuple(thread)
        return Reading(recovered=self.recovers)

    def settles(self, question: str, passages) -> Settled:
        """Settles an unanswerable question wherever it would recover one."""
        self.verified += 1
        if self.recovers is None:
            return Settled(verdict=Settling.SILENT, quote=None)
        return Settled(verdict=Settling.ANSWERS, quote=self.recovers)

    def names_its_source(self, question: str) -> bool:
        """The residue judgement, for a question no rule settled."""
        self.phrased += 1
        return self.names_source

    def names_something(self, question: str) -> bool:
        """Whether a question the parse called thin names anything."""
        self.phrased += 1
        return self.stands_alone

    def self_contained(self, question: str, pointers) -> bool:
        """Whether the pointers a parse found land inside the question."""
        self.phrased += 1
        return self.contained

    def supports(self, question: str, answer: str, passages, thread=()) -> bool:
        """Answers the entailment pass, and counts the ask."""
        self.supported += 1
        return self.backs

    def computes(self, question: str, answer: str, passages, thread=()) -> bool:
        """Answers the derived-answer pass, and counts the ask."""
        self.supported += 1
        return self.backs

    def stated(self, question: str, key: str, passages, thread=()) -> tuple[Part, ...]:
        """Quotes no part, and counts the ask."""
        self.stated_asked += 1
        return ()


def build(recording: Recording, near: Neighbour | None = None) -> QuestionChecker:
    """A checker over a scripted probe and a scripted pair of models."""
    return QuestionChecker(
        embedder=recording,
        verifier=recording,
        nearest=lambda embedding, **_: near,
        threshold=0.93,
        phrasing=recording,
    )


def test_a_question_that_clears_every_gate_is_accepted() -> None:
    """With its embedding kept, so a later run can probe against it."""
    recording = Recording(recovers="4 kg")

    result = build(recording).check(candidate())

    assert result.accepted
    assert result.status == QuestionStatus.ACCEPTED
    assert result.embedding == recording.vector


def test_a_malformed_question_never_reaches_the_embedder_or_the_verifier() -> None:
    """The free gate is first because the two behind it are not free."""
    recording = Recording()

    result = build(recording).check(candidate(question_text="not a question"))

    assert result.rejected_reason == QuestionRejection.MALFORMED
    assert (recording.embedded, recording.verified) == (0, 0)


def test_the_duplicate_reading_is_taken_against_the_bar_that_applied() -> None:
    """A pair on one fact is held to the lower bar, and the margin says so.

    Read against QUESTIONS_DUPLICATE_COSINE instead, a question refused at
    the lower bar would carry a reading below its own threshold, and a
    reader of the row could not see why it went.
    """
    recording = Recording()
    near = Neighbour(
        "What is the weight?",
        answerable=True,
        similarity=0.90,
        fact_ids=frozenset({1}),
    )
    checker = QuestionChecker(
        embedder=recording,
        verifier=recording,
        nearest=lambda embedding, **_: near,
        threshold=0.93,
        shared_threshold=0.88,
        phrasing=recording,
    )

    result = checker.check(candidate(question_text="What is the weight of the device?"))

    assert result.rejected_reason == QuestionRejection.DUPLICATE
    assert [
        one.threshold for one in result.readings if one.gate == "near_duplicate"
    ] == [0.88]


class _Probe:
    """A stored-question probe that honours the filters it is asked with."""

    def __init__(self, *stored: Neighbour) -> None:
        self.stored = stored

    def __call__(self, embedding, language=None, answerable=None) -> Neighbour | None:
        """The nearest stored question of this language and answerability."""
        fitting = [
            one
            for one in self.stored
            if language in (None, one.language) and answerable in (None, one.answerable)
        ]
        return max(fitting, key=lambda one: one.similarity, default=None)


def _probed(probe: _Probe, **asked) -> str | None:
    """What the checker makes of a candidate against this probe."""
    recording = Recording()
    checker = QuestionChecker(
        embedder=recording,
        verifier=recording,
        nearest=probe,
        threshold=0.93,
        shared_threshold=0.88,
        phrasing=recording,
    )
    seen = asked.pop("seen", ())
    return checker.check(candidate(**asked), seen=seen).rejected_reason


#: Stored in English, resting on the candidate's fact and asking with its word.
_TWIN = Neighbour(
    "How heavy is the device?",
    answerable=True,
    similarity=0.95,
    fact_ids=frozenset({1}),
    language="en",
)


def test_a_twin_behind_a_closer_question_in_another_language_is_found() -> None:
    """A question in another language cannot refuse this one, so it hides nothing."""
    probe = _Probe(
        _TWIN,
        Neighbour(
            "Wie schwer ist das Gerät?", answerable=True, similarity=0.99, language="de"
        ),
    )

    assert _probed(probe) == QuestionRejection.DUPLICATE


def test_a_twin_behind_a_closer_unanswerable_question_is_found() -> None:
    """An answerable question is never the twin of an unanswerable one."""
    probe = _Probe(
        _TWIN,
        Neighbour(
            "How heavy is the device on the moon?",
            answerable=False,
            similarity=0.99,
            fact_ids=frozenset({1}),
            language="en",
        ),
    )

    assert _probed(probe) == QuestionRejection.DUPLICATE


def test_an_unanswerable_twin_behind_a_closer_answered_question_is_found() -> None:
    """An unanswerable question is probed among both kinds, each for its gate.

    The answered neighbour rests on another fact, so it does not answer this
    one; the unanswerable one beside it cites the same passage and asks the
    same thing.
    """
    probe = _Probe(
        Neighbour(
            "How heavy is the device?",
            answerable=True,
            similarity=0.99,
            fact_ids=frozenset({2}),
            language="en",
        ),
        Neighbour(
            "How heavy is the device on Mars?",
            answerable=False,
            similarity=0.95,
            passage_ids=frozenset({1}),
            language="en",
        ),
    )

    got = _probed(
        probe,
        question_text="How heavy is the device on the moon?",
        target_answer=None,
        answerable=False,
    )

    assert got == QuestionRejection.DUPLICATE


def test_a_question_this_run_wrote_in_another_language_hides_no_twin() -> None:
    """The run's own questions are read by the same filters as the stored ones."""
    from question_generation.models import CheckedQuestion, Criteria

    german = CheckedQuestion(
        question_text="Wie schwer ist das Gerät?",
        target_answer="4 kg",
        answerable=True,
        criteria=Criteria(
            passage_scope="single_passage",
            document_scope="single_document",
            topic_scope="single_topic",
            answer_chars=4,
            difficulty="easy",
        ),
        language="de",
        status="accepted",
        rejected_reason=None,
        fact_ids=(1,),
        embedding=[1.0] + [0.0] * 1023,
    )

    assert _probed(_Probe(_TWIN), seen=(german,)) == QuestionRejection.DUPLICATE


def test_a_twin_this_run_wrote_behind_a_closer_question_on_another_fact_is_found() -> (
    None
):
    """Every earlier question that could refuse it is read, not only the closest.

    The closer one rests on another fact and is held to the near-identity
    bar, which it does not reach; the farther one rests on this one's fact
    and is over the bar a shared fact sets.
    """
    from math import sqrt

    from question_generation.models import CheckedQuestion, Criteria

    def written(text: str, fact: int, alike: float, axis: int) -> CheckedQuestion:
        """An accepted question of this run, this alike to the candidate."""
        vector = [0.0] * 1024
        vector[0], vector[axis] = alike, sqrt(1.0 - alike * alike)
        return CheckedQuestion(
            question_text=text,
            target_answer="4 kg",
            answerable=True,
            criteria=Criteria(
                passage_scope="single_passage",
                document_scope="single_document",
                topic_scope="single_topic",
                answer_chars=4,
                difficulty="easy",
            ),
            language="en",
            status="accepted",
            rejected_reason=None,
            fact_ids=(fact,),
            embedding=vector,
        )

    closer = written("How heavy is the frame of the device?", 2, 0.95, 1)
    twin = written("How heavy is the device from Hamburg?", 1, 0.90, 2)

    assert _probed(_Probe(), seen=(closer, twin)) == QuestionRejection.DUPLICATE


def test_a_duplicate_never_reaches_the_verifier() -> None:
    """An index probe is cheap and a model call is not."""
    recording = Recording()
    near = Neighbour("What is the weight?", answerable=True, similarity=0.99)

    result = build(recording, near).check(candidate())

    assert result.rejected_reason == QuestionRejection.DUPLICATE
    assert recording.verified == 0


def test_an_answer_the_passages_do_not_give_is_not_recoverable() -> None:
    """The gate no similarity measure makes."""
    recording = Recording(recovers=None)

    result = build(recording).check(candidate())

    assert result.rejected_reason == QuestionRejection.NOT_RECOVERABLE


def test_an_answer_that_contradicts_the_target_is_not_recoverable() -> None:
    """Recovering something is not recovering the right thing."""
    recording = Recording(recovers="12 hours")

    result = build(recording).check(candidate(target_answer="4 kg"))

    assert result.rejected_reason == QuestionRejection.NOT_RECOVERABLE


def test_an_unanswerable_question_the_passages_answer_is_rejected() -> None:
    """The round trip run the other way round."""
    recording = Recording(recovers="4 kg")

    result = build(recording).check(
        candidate(
            question_text="What does the device weigh?",
            target_answer=None,
            answerable=False,
        )
    )

    assert result.rejected_reason == QuestionRejection.ANSWERABLE_AFTER_ALL


def test_an_unanswerable_question_the_passages_do_not_answer_is_accepted() -> None:
    """Which is the one this whole kind of question exists for."""
    recording = Recording(recovers=None)

    result = build(recording).check(
        candidate(
            question_text="What does the device weigh on Mars?",
            target_answer=None,
            answerable=False,
        )
    )

    assert result.accepted


@pytest.mark.parametrize(
    "recovered",
    [
        "A senior officer must sign a transfer before it is released.",
        "A transfer is not released until a senior officer signs it.",
    ],
)
def test_a_quote_that_only_restates_the_question_is_not_an_answer(
    recovered: str,
) -> None:
    """A `why` the passage gives no reason for, quoted back as the rule itself.

    `settles` says `answers` with what the question already said, so the
    passages did not answer it, and a chatbot declining it is right. Its
    `not` is no answer either: a `why` is not asked yes or no. The verdict
    is kept as the silence it is.
    """
    recording = Recording(recovers=recovered)

    result = build(recording).check(
        candidate(
            question_text=(
                "Why must a senior officer sign a transfer before it is released?"
            ),
            target_answer=None,
            answerable=False,
            question_type=QuestionType.REASON,
        )
    )

    assert "round_trip" in result.gates_ran
    assert result.rejected_reason != QuestionRejection.ANSWERABLE_AFTER_ALL
    assert {one.gate: one.value for one in result.readings}["settles"] == 1.0


def test_a_quote_giving_the_reason_still_answers_it() -> None:
    """The same `why` and the same `answers`, with the reason it asked for."""
    reason = "So that no one person can move money alone."
    recording = Recording(recovers=reason)
    passage = f"A senior officer signs every transfer. {reason}"

    result = build(recording).check(
        candidate(
            question_text=(
                "Why must a senior officer sign a transfer before it is released?"
            ),
            target_answer=None,
            answerable=False,
            question_type=QuestionType.REASON,
            facts=group(source(1, statement=passage, passage_text=passage)),
        )
    )

    assert result.rejected_reason == QuestionRejection.ANSWERABLE_AFTER_ALL
    assert {one.gate: one.value for one in result.readings}["settles"] == 0.0


def test_a_duplicate_of_something_written_earlier_in_the_same_run_is_caught() -> None:
    """Nothing is stored until the topic is finished.

    Without this a topic would write the same question ten times and the
    database probe would see none of them.
    """
    recording = Recording()
    checker = build(recording)
    first = checker.check(candidate())

    second = checker.check(
        candidate(question_text="What is the device's weight?"), [first]
    )

    assert first.accepted
    assert second.rejected_reason == QuestionRejection.DUPLICATE


def test_the_verifier_is_shown_the_cited_passages_and_nothing_else() -> None:
    """The dataset is what is being measured, not a retriever."""
    seen: list = []

    class Watching(Recording):
        """Records what the verifier was shown."""

        def read(self, question: str, passages, thread=()) -> Reading:
            """Keeps the passages and answers as scripted."""
            seen.append(list(passages))
            return super().read(question, passages, thread)

    pair = group(
        source(1, document="a", passage_id=1, statement="The device weighs 4 kg."),
        source(2, document="b", passage_id=2, statement="The device ships in March."),
    )
    build(Watching()).check(candidate(facts=pair))

    assert len(seen[0]) == 2, "one passage per distinct citation"


def test_the_difficulty_is_read_off_the_group_rather_than_judged() -> None:
    """Two readers cannot disagree about it, which is the point."""
    pair = group(
        source(1, document="a", passage_id=1), source(2, document="b", passage_id=2)
    )

    result = build(Recording()).check(candidate(facts=pair))

    assert result.criteria.document_scope == "cross_document"
    assert result.fact_ids == (1, 2)


# ── The gates that judge it as a question ──────────────────────────────────
#
# Every example below is a row this stage actually wrote, before the prompt
# was given the passage and these gates were added.


# ── Why there is no gate for "the question is its own fact" ───────────────
#
# One was written and removed. These keep the finding, because the idea is an
# appealing one and the next person to have it should be able to see what it
# costs before writing it again.


@pytest.mark.parametrize(
    ("question", "answer", "fact"),
    [
        (
            "Wie hoch war die Arbeitslosenquote im August 2025?",
            "6,4 Prozent",
            "Die Arbeitslosenquote liegt im August 2025 bei 6,4 Prozent.",
        ),
        (
            "Wie viele Banken in Deutschland könnten sich qualifizieren?",
            "Etwa 1.000 Banken",
            "Etwa 1.000 Banken in Deutschland könnten sich qualifizieren.",
        ),
        (
            "Wie oft muss die Angemessenheit der Verfahren überprüft werden?",
            "jährlich",
            "Die Angemessenheit der Verfahren ist zumindest jährlich zu prüfen.",
        ),
    ],
)
def test_a_good_question_is_its_fact_minus_the_answer(question, answer, fact) -> None:
    """Which is why no lexical gate can refuse one for being that.

    For a single atomic fact, asking about it IS reproducing it without its
    answer. Every question here does exactly that and every one is as good
    as a benchmark question gets; a gate refusing the shape refused all
    three.
    """
    assert (
        checked(
            question_text=question,
            target_answer=answer,
            language="de",
            statements=(fact,),
        )
        is None
    )


def test_a_vague_question_has_the_same_shape_and_is_not_refused_here() -> None:
    """The one the removed gate was written for, kept to show the problem.

    It has the same overlap with its fact as the three above. What makes it
    worse is that its answer is not determinate - and that is not lexical
    either. So the verifier judges it, under `not_recoverable`, where it
    can be judged.
    """
    assert (
        checked(
            question_text="Was schüren geopolitische Konflikte?",
            target_answer="Unsicherheit",
            language="de",
            statements=("Geopolitische Konflikte schüren Unsicherheit.",),
        )
        is None
    )


def test_a_fact_handed_back_with_a_question_mark_is_still_refused() -> None:
    """The exact-match check stays: that one is not a judgement call."""
    failed = checked(
        question_text="Geopolitische Konflikte schüren Unsicherheit?",
        target_answer="Unsicherheit",
        language="de",
        statements=("Geopolitische Konflikte schüren Unsicherheit.",),
    )

    assert code(failed) == QuestionRejection.MALFORMED


@pytest.mark.parametrize(
    "answer",
    [
        "Verwarnungen aussprechen",
        "nachvollziehbar zu begründen",
        "nahmen Produkte vom Markt",
    ],
)
def test_an_answer_that_describes_an_action_is_refused_for_a_value(answer) -> None:
    """Three real target answers, none of them a thing anyone asked for.

    Any verb and not only a finite one: two of these are infinitives, so
    they make no claim and are still not answers.

    Only where a value was asked for. The same rule applied to every answer
    is what made `why` and `how` unwritable: their answers are supposed to
    carry a verb.
    """
    failed = checked(
        question_text="Welche Maßnahme hat die Bafin 2025 ergriffen?",
        target_answer=answer,
        language="de",
        form=AnswerForm.VALUE,
        statements=("Die Bafin sprach Verwarnungen aus.",),
    )

    assert code(failed) == QuestionRejection.WRONG_FORM


@pytest.mark.parametrize(
    "answer",
    ["48 Stunden", "2025", "1.033", "der Vorstand", "vierteljährlich", "Hamburg"],
)
def test_an_answer_that_names_a_thing_is_kept(answer) -> None:
    """A value, a date, an amount, a name, a period, a place."""
    failed = checked(
        question_text="Welchen Wert nennt die Gebührenverordnung der Bafin?",
        target_answer=answer,
        language="de",
        statements=("Die Verordnung nennt einen Wert.",),
    )

    assert failed is None


def test_two_sentences_each_ending_in_a_question_mark_are_malformed() -> None:
    """The shape a question mark counts. `compound` catches the other one."""
    failed = checked(
        question_text="Wie hoch ist die Gebühr? Und wer erhebt sie?",
        target_answer="1.033 Euro",
        language="de",
    )

    assert code(failed) == QuestionRejection.MALFORMED


def test_a_question_nobody_could_have_asked_cold_is_refused() -> None:
    """Two holders agreeing: the parse calls it thin and the judge agrees.

    A question can be perfectly answerable by the passages it cites and
    still be one nobody would type. The parse only says the question is thin
    enough for the judgement to be worth asking for.
    """
    recording = Recording(recovers="4 kg", stands_alone=False)

    result = build(recording).check(
        candidate(question_text="What specific components are included?")
    )

    assert result.rejected_reason == QuestionRejection.UNANCHORED
    assert recording.verified == 0, "the passages are never read for this"


def test_an_unanchored_unanswerable_question_is_refused_too() -> None:
    """A chatbot declining a question nobody would ask proves nothing."""
    recording = Recording(recovers=None, stands_alone=False)

    result = build(recording).check(
        candidate(
            question_text="What specific components are included?",
            target_answer=None,
            answerable=False,
        )
    )

    assert result.rejected_reason == QuestionRejection.UNANCHORED


def test_a_writer_marking_its_own_work_cannot_reject_on_phrasing() -> None:
    """The only gate here that is an opinion, and opinions need a holder.

    A 4B model judging its own questions rejected `According to the ECB and
    NCAs, who conducts the due diligence check for an outsourcing
    arrangement?` for naming nothing. A gate losing questions that good is
    worse than no gate, so without an independent verifier the question is
    kept - and the judgement is not asked for at all, because an opinion
    that may not reject is a call per question buying a log line.
    """
    recording = Recording(recovers="4 kg", stands_alone=False)
    checker = QuestionChecker(
        embedder=recording,
        verifier=recording,
        nearest=lambda embedding, **_: None,
        threshold=0.93,
        judge_phrasing=False,
        phrasing=recording,
    )

    result = checker.check(candidate())

    assert result.accepted, "a self-judged opinion rejected a question"
    assert recording.phrased == 0, "paid for a judgement that could not gate"


def test_recoverability_is_judged_even_when_phrasing_is_not() -> None:
    """One is an opinion; the other is checkable against the passage.

    Turning the subjective gate off must not turn off the gate that reads
    the evidence, which is the one that matters most.
    """
    recording = Recording(recovers=None, stands_alone=False)
    checker = QuestionChecker(
        embedder=recording,
        verifier=recording,
        nearest=lambda embedding, **_: None,
        threshold=0.93,
        judge_phrasing=False,
    )

    result = checker.check(candidate())

    assert result.rejected_reason == QuestionRejection.NOT_RECOVERABLE


def test_the_free_gates_are_unaffected_by_who_is_verifying() -> None:
    """A measurement does not need a second opinion to be worth making."""
    recording = Recording()
    checker = QuestionChecker(
        embedder=recording,
        verifier=recording,
        nearest=lambda embedding, **_: None,
        threshold=0.93,
        judge_phrasing=False,
    )

    result = checker.check(
        candidate(
            question_text="Geopolitische Konflikte schüren Unsicherheit?",
            target_answer="Unsicherheit",
            facts=group(
                source(
                    1,
                    statement="Geopolitische Konflikte schüren Unsicherheit.",
                    language="de",
                ),
            ),
        )
    )

    assert result.rejected_reason == QuestionRejection.MALFORMED


# ── The answer floor, and the criteria the gates read off ──────────────────


@pytest.mark.parametrize("answer", ["7", "8%", "Nein", "70%", "2025"])
def test_an_answer_under_the_floor_is_refused(answer) -> None:
    """A blunt measure, chosen deliberately.

    At fifteen characters it refuses `70%` and `2025` as well as `7` and
    `Nein`. QUESTIONS_MIN_ANSWER_CHARS is where that is decided.
    """
    failed = checked(target_answer=answer, bounds={**BOUNDS, "value": (15, 80)})

    assert code(failed) == QuestionRejection.ANSWER_TOO_SHORT


@pytest.mark.parametrize(
    "answer", ["European Supervisory Authorities", "29 January 2027", "Article 4(1)(1)"]
)
def test_an_answer_over_the_floor_is_kept(answer) -> None:
    """A name, a date and a citation, all of them scoreable."""
    assert checked(target_answer=answer, bounds={**BOUNDS, "value": (15, 80)}) is None


def test_a_floor_of_zero_refuses_nothing_for_length() -> None:
    """Which is what keeps the bare values a corpus of numbers needs."""
    assert checked(target_answer="70%", bounds=BOUNDS) is None


def test_an_unanswerable_question_is_never_too_short() -> None:
    """It has no answer to measure, and is scored on behaviour."""
    assert (
        checked(
            answerable=False, target_answer=None, bounds={**BOUNDS, "value": (15, 80)}
        )
        is None
    )


def test_a_follow_up_is_not_judged_on_standing_alone() -> None:
    """`And for an urgent one?` names nothing, and is the point.

    Leaning on the thread is what makes a follow-up a follow-up, so judging
    one as though it had been asked cold would reject every one of them.
    """
    recording = Recording(recovers="4 hours", stands_alone=False)

    result = build(recording).check(
        candidate(
            question_text="And for an urgent one?",
            target_answer="4 hours",
            thread=(("How long for a standard one?", "48 hours"),),
        )
    )

    assert result.accepted
    assert result.thread_position == 2


def test_the_verifier_is_shown_the_thread_when_it_reads_a_follow_up() -> None:
    """Read alone, a follow-up has no answer in any passage."""
    recording = Recording(recovers="4 kg")

    build(recording).check(
        candidate(
            question_text="And for an urgent one?",
            target_answer="4 hours",
            thread=(("How long for a standard one?", "48 hours"),),
        )
    )

    assert recording.threaded == (("How long for a standard one?", "48 hours"),)


def test_the_three_criteria_are_read_off_the_facts_the_question_cites() -> None:
    """Each says something different about what a chatbot has to do."""
    across = group(
        source(1, document="a", passage_id=1, topic_id=7),
        source(2, document="b", passage_id=2, topic_id=8),
    )

    result = build(Recording()).check(candidate(facts=across))

    assert result.criteria.passage_scope == "multi_passage"
    assert result.criteria.document_scope == "cross_document"
    assert result.criteria.topic_scope == "multi_topic"
    assert result.criteria.difficulty == "hard", "three of the five"
    assert result.criteria.score == 3


def test_a_follow_up_counts_towards_its_own_difficulty() -> None:
    """Carrying a thread is one of the things that makes answering harder.

    Measured on the score rather than on the band: one point does not
    always cross a boundary, and the score is what the band is read from.
    """
    alone = build(Recording()).check(candidate())
    followed = build(Recording()).check(
        candidate(thread=(("How long for a standard one?", "48 hours"),))
    )

    assert followed.criteria.score == alone.criteria.score + 1
    assert followed.criteria.follows and not alone.criteria.follows


# ── Naming the source, which is the one thing a question must not do ───────
#
# Every question below is a row this stage really wrote, under a prompt that
# asked it to name what it was asking about.


@pytest.mark.parametrize(
    "question",
    [
        "Laut den 'Risiken im Fokus 2026', wie viele Risiken werden genannt?",
        "Welche Themen werden in den 'Risiken im Fokus 2026' beschrieben?",
        "In Risiken im Fokus 2026, welcher Anteil entfiel auf Phishing?",
    ],
)
def test_a_question_quoting_its_own_document_title_is_refused(question) -> None:
    """The free half of the gate, and it runs before any model call.

    The titles are rows in this corpus's documents table, and the writer
    echoed them straight back.
    """
    failed = checked(
        question_text=question,
        target_answer="drei",
        language="de",
        titles=("Risiken im Fokus 2026",),
    )

    assert code(failed) == QuestionRejection.LEAKS_SOURCE


def test_a_title_too_short_to_be_a_name_is_not_matched() -> None:
    """`Contents` and `March 2018` are titles in this corpus.

    A question may contain either by accident, so matching on them would
    refuse questions that cite nothing.
    """
    assert (
        checked(
            question_text="What are the contents of a risk report?",
            target_answer="the exposures and the limits",
            titles=("Contents", "March 2018"),
        )
        is None
    )


def test_a_question_naming_no_title_passes_the_free_half() -> None:
    """Naming a party or a period is not naming a source."""
    assert (
        checked(
            question_text="Wie viele Cybervorfälle wurden der Bafin 2025 gemeldet?",
            target_answer="dreihundert",
            language="de",
            titles=("Risiken im Fokus 2026", "Druckversion - Jahresbericht 2025"),
        )
        is None
    )


@pytest.mark.parametrize(
    ("question", "answer", "language", "title", "statement"),
    [
        (
            "Welche Gebühr fällt für Kreditkarten im Ausland an?",
            "1,5 Prozent",
            "de",
            "Kreditkarten",
            "Für Zahlungen mit Kreditkarten im Ausland berechnet die Bank 1,5 Prozent.",
        ),
        (
            "Wie lange gilt das Rückgaberecht für Rücksendungen?",
            "14 Tage",
            "de",
            "Rücksendungen",
            "Rücksendungen sind innerhalb von 14 Tagen nach der Lieferung möglich.",
        ),
        (
            "What fee applies when mortgage loans are repaid early?",
            "1 percent",
            "en",
            "Mortgage loans",
            "Mortgage loans repaid early carry a fee of 1 percent of the amount repaid.",
        ),
        (
            "Which items are excluded from the right of withdrawal?",
            "digital content",
            "en",
            "Right of withdrawal",
            "Digital content is excluded from the right of withdrawal once downloaded.",
        ),
    ],
)
def test_a_title_that_is_the_subject_is_not_a_source(
    question, answer, language, title, statement
) -> None:
    """A page titled by its subject is asked about by that name, as its facts are."""
    assert (
        checked(
            question_text=question,
            target_answer=answer,
            language=language,
            statements=(statement,),
            titles=(title,),
        )
        is None
    )


@pytest.mark.parametrize(
    ("question", "answer", "language", "title"),
    [
        (
            "Was sagt das Preis- und Leistungsverzeichnis zur Auslandsgebühr?",
            "1,5 Prozent",
            "de",
            "Preis- und Leistungsverzeichnis",
        ),
        (
            "Was steht im Jahresbericht 2025 über die Zinsen?",
            "sinkende Zinsen",
            "de",
            "Jahresbericht 2025",
        ),
        (
            "What does the Price and Service Schedule say about card fees abroad?",
            "1.5 percent",
            "en",
            "Price and Service Schedule",
        ),
    ],
)
def test_a_title_its_material_never_writes_is_a_source(
    question, answer, language, title
) -> None:
    """A name the facts do not use is where the answer is."""
    statement = {
        "de": "Für Kartenzahlungen im Ausland berechnet die Bank 1,5 Prozent.",
        "en": "Card payments abroad cost 1.5 percent of the amount.",
    }[language]
    failed = checked(
        question_text=question,
        target_answer=answer,
        language=language,
        statements=(statement,),
        titles=(title,),
    )

    assert code(failed) == QuestionRejection.LEAKS_SOURCE


@pytest.mark.parametrize(
    ("question", "answer", "language", "title"),
    [
        ("Wie hoch ist die Kontoführungsgebühr?", "4,90 EUR", "de", "Kontoführung"),
        (
            "Which reinsurance products are excluded from the rules?",
            "none",
            "en",
            "Insurance products",
        ),
    ],
)
def test_a_title_inside_a_longer_word_is_not_quoted(
    question, answer, language, title
) -> None:
    """A title is matched as whole words, not as letters inside one."""
    assert (
        checked(
            question_text=question,
            target_answer=answer,
            language=language,
            titles=(title,),
        )
        is None
    )


def test_the_verifier_catches_a_source_it_named_without_quoting() -> None:
    """`Laut dem Jahresbericht 2025` is not `Druckversion - Jahresbericht 2025`.

    The free half matches a title verbatim, so a paraphrase gets past it.
    `cites_source` catches the patterns, and the model is the residue.
    """
    recording = Recording(recovers="4 kg", names_its_source=True)

    result = build(recording).check(candidate())

    assert result.rejected_reason == QuestionRejection.LEAKS_SOURCE
    assert recording.verified == 0, "the passages are never read for this"


def test_a_follow_up_may_not_name_its_source_either() -> None:
    """Leaning on the conversation is allowed; naming the file is not.

    The two exemptions are different: a follow-up is excused from naming a
    subject, never from hiding its source.
    """
    recording = Recording(recovers="4 hours", names_its_source=True)

    result = build(recording).check(
        candidate(
            question_text="And in the annual report, what about urgent ones?",
            target_answer="4 hours",
            thread=(("How long for a standard one?", "48 hours"),),
        )
    )

    assert result.rejected_reason == QuestionRejection.LEAKS_SOURCE


def test_naming_a_subject_and_naming_a_source_are_judged_separately() -> None:
    """The conflation this gate exists to undo.

    A question that names its subject and no source is what is wanted, and
    for a while the phrasing gate asked for the opposite.
    """
    recording = Recording(recovers="4 kg", stands_alone=True, names_its_source=False)

    result = build(recording).check(candidate())

    assert result.accepted


def test_a_self_judged_verifier_cannot_reject_for_naming_a_source() -> None:
    """The same rule as the phrasing gate: an opinion needs a holder."""
    recording = Recording(recovers="4 kg", names_its_source=True)
    checker = QuestionChecker(
        embedder=recording,
        verifier=recording,
        nearest=lambda embedding, **_: None,
        threshold=0.93,
        phrasing=recording,
        judge_phrasing=False,
    )

    result = checker.check(candidate())

    assert result.accepted


def test_the_free_half_of_the_gate_runs_without_a_verifier_at_all() -> None:
    """A measurement needs no second opinion.

    Quoting a title is not a matter of taste, so it is refused whoever is
    verifying - or whether anything is.
    """
    recording = Recording()
    checker = QuestionChecker(
        embedder=recording,
        verifier=recording,
        nearest=lambda embedding, **_: None,
        threshold=0.93,
        judge_phrasing=False,
    )

    result = checker.check(
        candidate(
            question_text="Laut den 'Risiken im Fokus 2026', wie viele Risiken?",
            facts=group(
                source(
                    1,
                    statement="Es werden drei Risiken genannt.",
                    language="de",
                    document_title="Risiken im Fokus 2026",
                )
            ),
        )
    )

    assert result.rejected_reason == QuestionRejection.LEAKS_SOURCE
    assert recording.verified == 0, "it must not need a call"


@pytest.mark.parametrize("answer", ["dreihundert", "erstmals", "angespannt"])
def test_a_one_word_answer_is_never_read_as_an_action(answer) -> None:
    """A single word is a thing, whatever the tagger calls it.

    `de_core_news_md` tags `dreihundert` as a verb, so checking a one-word
    answer refuses a good one to catch a rare bad one. Every real failure
    this gate was written for was several words long.
    """
    assert checked(target_answer=answer, language="de") is None


def test_a_shared_number_is_not_agreement_on_its_own() -> None:
    """`4 kg` answered a question whose target was `4 hours`, and passed.

    The units check ran first and returned on its own, so a recovered answer
    sharing one number with the target was accepted whatever else it said.
    Both halves have to pass now.
    """
    assert not agrees("4 kg", "4 hours", "en")
    assert agrees("4 hours", "4 hours", "en")


@pytest.mark.parametrize(
    ("recovered", "target"),
    [("die Gebühr ist 1.033 Euro", "1033 Euro"), ("0,3 Prozent", "0.3 Prozent")],
)
def test_a_number_is_the_same_number_in_either_locale(recovered, target) -> None:
    """This corpus writes `0,3` and the verifier answers `0.3`.

    Folded only when comparing one number against another, so `4` is still
    not `48`. A group of three after a German point is thousands.
    """
    assert agrees(recovered, target, "de")


@pytest.mark.parametrize(
    ("language", "question", "target", "recovered"),
    [
        (
            "de",
            "Wie lange dauert die Bearbeitung eines Kreditantrags?",
            "8–10 Werktage",
            "Die Bearbeitung eines Kreditantrags dauert mindestens 8 und höchstens 10 Werktage.",
        ),
        (
            "en",
            "How long does the bank take to process a loan application?",
            "8–10 business days",
            "Processing a loan application takes between 8 and 10 business days.",
        ),
        (
            "de",
            "Wie breit ist der Versandkarton des Shops?",
            "30–50 cm",
            "Der Versandkarton ist zwischen 30 cm und 50 cm breit.",
        ),
        (
            "en",
            "How wide is the shop's shipping box?",
            "30–50 cm",
            "The shipping box is between 30 cm and 50 cm wide.",
        ),
    ],
)
def test_a_range_comes_back_end_by_end(language, question, target, recovered) -> None:
    """`100–110` is one figure token, so a reply `100 m ... 110 m` never held it.

    A range a dash joins asserts both ends; the round trip finds it back when
    the recovery gives each end, however it writes them.
    """
    assert agrees(
        recovered,
        target,
        language,
        AnswerForm.VALUE,
        question=question,
        passages=(recovered,),
    )


@pytest.mark.parametrize(
    ("language", "question", "target", "recovered"),
    [
        (
            "en",
            "How long does the bank take to process a loan application?",
            "8–10 business days",
            "Processing a loan application takes between 8 and 12 business days.",
        ),
        (
            "de",
            "Wie lange dauert die Bearbeitung eines Kreditantrags?",
            "8–10 Werktage",
            "Die Bearbeitung dauert mindestens 8 Werktage.",
        ),
        (
            "de",
            "Wie schwer darf ein Paket des Shops sein?",
            "30–50 cm",
            "Ein Paket darf zwischen 30 und 50 kg wiegen.",
        ),
        (
            "en",
            "How heavy may a parcel be?",
            "30–50 cm",
            "A parcel may weigh between 30 kg and 50 kg.",
        ),
    ],
)
def test_a_range_still_needs_both_ends_and_its_unit(
    language, question, target, recovered
) -> None:
    """Reading a range as two ends must not let one end, or another unit, through."""
    assert not agrees(
        recovered,
        target,
        language,
        AnswerForm.VALUE,
        question=question,
        passages=(recovered,),
    )


@pytest.mark.parametrize(
    ("language", "question", "target", "recovered"),
    [
        (
            "en",
            "What is the maximum length of the pitch?",
            "110 m",
            "The pitch is 100–110 m long.",
        ),
        ("en", "Which fee does the bank charge?", "8 euros", "The fee is 8–10 euros."),
        (
            "de",
            "Wie lang darf das Feld höchstens sein?",
            "110 m",
            "Das Feld ist 100–110 m lang.",
        ),
        (
            "de",
            "Welche Gebühr erhebt der Shop?",
            "8 Euro",
            "Die Gebühr beträgt 8–10 Euro.",
        ),
    ],
)
def test_one_end_of_a_range_is_not_the_range(
    language, question, target, recovered
) -> None:
    """A key holding one figure is not what a recovery holding a range says.

    The ends of a recovery's range count only against a key that holds a range.
    """
    assert not agrees(
        recovered,
        target,
        language,
        AnswerForm.VALUE,
        question=question,
        passages=(recovered,),
    )


@pytest.mark.parametrize(
    ("language", "target", "recovered"),
    [
        ("en", "1–3 cm", "between 1 and 3 cm"),
        ("en", "8–13 kg", "A parcel weighs between 8 and 13 kg."),
        ("en", "8–13 hours", "Processing takes between 8 and 13 hours."),
        ("en", "3–63 days", "3 to 63 days"),
        ("en", "29–30 cm", "from 29 cm to 30 cm"),
        ("de", "1–3 cm", "zwischen 1 und 3 cm"),
        ("de", "8–13 kg", "Ein Paket wiegt 8 bis 13 kg."),
        ("de", "8–13 Stunden", "Die Bearbeitung dauert zwischen 8 und 13 Stunden."),
    ],
)
def test_a_range_unit_comes_back_whatever_the_tagger_calls_it(
    language, target, recovered
) -> None:
    """`cm` is a number to the tagger in one sentence and a noun in the other.

    The unit of a range is compared by its surface form and lemma, not by the
    part of speech either side gave it.
    """
    assert agrees(recovered, target, language)


def test_a_hyphen_range_with_its_unit_comes_back_end_by_end() -> None:
    """The tokenizer splits `5-9` into two figures, so the en dash is the only range form."""
    recovered = "Between 5 and 9 days."
    assert agrees(
        recovered,
        "5-9 days",
        "en",
        AnswerForm.VALUE,
        question="How long?",
        passages=(recovered,),
    )
    assert not agrees(
        recovered,
        "5-12 days",
        "en",
        AnswerForm.VALUE,
        question="How long?",
        passages=(recovered,),
    )


def test_a_three_decimal_rate_is_not_its_digits() -> None:
    """`0,125 %` is an eighth of a percent, which `125 %` is not."""
    assert not agrees("0,125 %", "125 %", "de")
    assert not asserted("125 %", ["Der Zinssatz beträgt 0,125 % pro Jahr."], "de")


@pytest.mark.parametrize(
    ("recovered", "target", "language", "same"),
    [
        ("Der Sollzins beträgt 1,234 Prozent.", "1234 Prozent", "de", False),
        ("Annual fee 1,234 EUR", "1234 EUR", "en", True),
    ],
    ids=["a German decimal", "an English thousands group"],
)
def test_a_group_of_three_is_read_by_the_languages_decimal_mark(
    recovered, target, language, same
) -> None:
    """German `1,234` is a rate and English `1,234` a count."""
    assert agrees(recovered, target, language) is same


@pytest.mark.parametrize(
    ("recovered", "target", "language"),
    [
        ("Das Tageslimit beträgt 1,000 EUR.", "1.000 EUR", "de"),
        ("EUR 1.000", "1,000 EUR", "en"),
    ],
    ids=["a German key", "an English key"],
)
def test_a_key_in_the_other_convention_still_agrees(
    recovered, target, language
) -> None:
    """A model writes either convention, whatever the language it writes."""
    assert agrees(recovered, target, language)


def test_a_key_in_the_other_convention_is_still_asserted() -> None:
    """`1,000 EUR` is the `1.000 EUR` a German passage states, read as thousands."""
    assert asserted("1,000 EUR", ["Das Tageslimit beträgt 1.000 EUR."], "de")


@pytest.mark.parametrize(
    ("recovered", "target"),
    [
        ("125 Anlagen wurden geprüft", "12,5 Prozent"),
        ("15 Anlagen wurden geprüft", "1,5 Millionen"),
    ],
)
def test_a_decimal_comma_is_not_the_digits_run_together(recovered, target) -> None:
    """The fold deleted the separator, so `12,5` and `125` were one value.

    That is the common shape in a German corpus, not an exotic one, and it
    ran through the one guard no opinion may overrule: every number the
    target asserts has to occur in what came back. An answer claiming
    `1,5 Millionen` was confirmed by a passage that merely said `15`.
    """
    assert not agrees(recovered, target, "de")


@pytest.mark.parametrize("token", ["U.S.A.", "1.2.3"])
def test_a_word_keeps_its_punctuation(token) -> None:
    """What the fold's own docstring always claimed and it never did.

    It dropped every dot and comma from every token it was handed, units
    and vocabulary alike, so `U.S.A.` was `USA` and a version was a number.
    """
    assert _folded(token, "en") == token


# ── The form each type's answer takes, which decides who reads it how ──────


@pytest.mark.parametrize(
    "answer",
    [
        "weil die Risiken im Bankensektor gestiegen sind",
        "because risks in the banking sector increased",
        "by notifying the authority within four hours through the portal",
    ],
)
def test_an_explanation_carrying_a_verb_is_kept(answer) -> None:
    """The questions the one verb rule made unwritable."""
    german = answer.startswith("weil")
    assert (
        checked(
            question_text=(
                "Warum wurde die Anforderung angehoben?"
                if german
                else "Why was the requirement raised?"
            ),
            target_answer=answer,
            language="de" if german else "en",
            form=AnswerForm.EXPLANATION,
        )
        is None
    )


def test_an_explanation_that_explains_nothing_is_refused() -> None:
    """A why answered with a noun phrase has not been answered."""
    failed = checked(
        question_text="Why was the requirement raised?",
        target_answer="the capital requirement of the banking sector",
        form=AnswerForm.EXPLANATION,
    )

    assert code(failed) == QuestionRejection.WRONG_FORM


def test_a_list_is_held_to_neither_verb_rule() -> None:
    """Items may be actions or things, and both are a list."""
    assert (
        checked(
            question_text="Which ways can a request be raised?",
            target_answer="by phone, through the web form and by email",
            form=AnswerForm.LIST,
        )
        is None
    )


def test_an_answer_over_the_ceiling_of_its_form_is_refused() -> None:
    """A value answered with a paragraph is the too-broad question again."""
    failed = checked(
        target_answer="4 kg, " * 30,
        form=AnswerForm.VALUE,
    )

    assert code(failed) == QuestionRejection.ANSWER_TOO_LONG


def test_the_same_answer_passes_for_one_form_and_fails_for_another() -> None:
    """Which is the whole point of the column: one rule fitted neither."""
    prose = "it is raised through the web form and confirmed by email"

    assert code(checked(target_answer=prose, form=AnswerForm.VALUE)) == (
        QuestionRejection.WRONG_FORM
    )
    assert checked(target_answer=prose, form=AnswerForm.EXPLANATION) is None


# ── Agreeing about an answer that is longer than a value ──────────────────


def test_a_paraphrased_explanation_is_recovered() -> None:
    """Demanding every word of prose survives a paraphrase refuses answers.

    The verifier plainly found this one; requiring a subset of lemmas, which
    is right for a value, threw it away.
    """
    assert agrees(
        "raised through the web form and confirmed by email",
        "it is raised through the web form, and confirmed by email before work begins",
        "en",
        AnswerForm.EXPLANATION,
        0.6,
    )


def test_an_explanation_about_something_else_is_not_recovered() -> None:
    """The floor still has to reject an answer that shares a few words."""
    assert not agrees(
        "the office is open on working days",
        "because the risk of a cyber incident rose sharply during the period",
        "en",
        AnswerForm.EXPLANATION,
        0.6,
    )


def test_a_number_still_has_to_match_exactly_whatever_the_form() -> None:
    """`4 hours` for `48 hours` is the failure the gate exists for."""
    assert not agrees(
        "answered within 4 hours on working days",
        "answered within 48 hours on working days",
        "en",
        AnswerForm.EXPLANATION,
        0.6,
    )


def test_a_value_is_still_compared_whole() -> None:
    """Every word of a value is the answer, so a share of it is not."""
    assert not agrees(
        "the supervisory authority", "the federal supervisory authority", "en"
    )


def test_a_value_naming_the_passages_verb_as_a_noun_agrees() -> None:
    """The verifier answers in the passage's words, and those say `reported`.

    A value is compared on its verbs' lemmas as well as its nouns', so `a
    report` meets `must be reported`. The figures stay exact: `4 hours` is
    still not `48 hours`.
    """
    recovered = (
        "Any delivery in which more than one parcel is damaged must be reported "
        "to the insurer within 48 hours"
    )

    assert agrees(recovered, "a report to the insurer", "en", AnswerForm.VALUE)
    assert not agrees(
        recovered, "a report to the insurer within 4 hours", "en", AnswerForm.VALUE
    )


@pytest.mark.parametrize(
    ("recovered", "target", "language"),
    [
        ("two conditions", "2 conditions", "en"),
        ("2 conditions", "two conditions", "en"),
        ("ten seconds", "10 seconds", "en"),
        ("zehn Sekunden", "10 Sekunden", "de"),
        ("10 Sekunden", "zehn Sekunden", "de"),
    ],
)
def test_a_count_written_out_is_the_count_in_digits(
    recovered: str, target: str, language: str
) -> None:
    """`two` and `2` are one number written two ways, as `0,3` and `0.3` are."""
    assert agrees(recovered, target, language, AnswerForm.VALUE)


@pytest.mark.parametrize(
    ("recovered", "target"),
    [
        ("Diese Frist bleibt außer Acht.", "8 Fristen"),
        ("Die Elf des Gastgebers hält die Frist ein.", "11 Fristen"),
    ],
    ids=["außer Acht", "die Elf"],
)
def test_a_word_spelled_like_a_count_is_not_one(recovered: str, target: str) -> None:
    """`außer Acht` is a phrase and `die Elf` a team: neither is tagged NUM."""
    assert not agrees(recovered, target, "de", AnswerForm.VALUE)


@pytest.mark.parametrize(
    ("passages", "target", "language"),
    [
        (["Es gelten zwei Fristen."], "2 Fristen", "de"),
        (["Two deadlines apply."], "2 deadlines", "en"),
    ],
)
def test_a_count_written_out_in_the_passages_is_its_figure(
    passages: list[str], target: str, language: str
) -> None:
    """The entailment guard reads the passages' counts as `agrees` does."""
    assert asserted(target, passages, language)


@pytest.mark.parametrize(
    ("passages", "target", "language"),
    [
        (["Der Vorgang dauert höchstens 6 Sekunden."], "zehn Sekunden", "de"),
        (["The process takes at most 6 seconds."], "ten seconds", "en"),
    ],
)
def test_a_count_the_key_writes_out_is_a_number_the_passages_must_carry(
    passages: list[str], target: str, language: str
) -> None:
    """`de_core_news_md` gives `zehn` no `like_num`, so the guard reads it too."""
    assert not asserted(target, passages, language)


@pytest.mark.parametrize(
    "passages",
    [["Der Vorgang dauert höchstens zehn Sekunden."], ["Er dauert 10 Sekunden."]],
)
def test_a_count_the_key_writes_out_passes_where_the_passages_state_it(
    passages: list[str],
) -> None:
    """In words or in digits."""
    assert asserted("zehn Sekunden", passages, "de")


def test_a_key_time_the_passages_do_not_give_is_not_asserted() -> None:
    """A time is a figure the key asserts, though `like_num` does not mark it."""
    assert not asserted("08:00", ["Die Filiale öffnet um 09:00 Uhr."], "de")
    assert asserted("08:00", ["Die Filiale öffnet um 08:00 Uhr."], "de")


def test_a_time_with_or_without_its_leading_zero_is_one_time() -> None:
    """`08:00` is `8:00` and the `8 Uhr` a reply may say, and still not `09:00`."""
    assert asserted("08:00 Uhr", ["Die Filiale öffnet um 8:00 Uhr."], "de")
    assert agrees("Die Filiale öffnet um 8:00 Uhr.", "08:00 Uhr", "de")
    assert agrees("um 8 Uhr", "08:00 Uhr", "de")
    assert not agrees("um 9:00 Uhr", "08:00 Uhr", "de")


def test_a_count_written_out_is_still_a_different_number_from_another() -> None:
    """`de_core_news_md` gives `zehn` no `like_num`, so it is read as a count."""
    assert not agrees("11 Sekunden", "zehn Sekunden", "de", AnswerForm.VALUE)


@pytest.mark.parametrize(
    ("recovered", "target", "language"),
    [
        ("1 replacement card", "one replacement card", "en"),
        ("one replacement card", "1 replacement card", "en"),
    ],
)
def test_one_written_out_is_the_figure_1(
    recovered: str, target: str, language: str
) -> None:
    """The gates read the same cardinals the fact dedup does, from zero up."""
    assert agrees(recovered, target, language, AnswerForm.VALUE)


# ── What the reader is given ───────────────────────────────────────────────

#: A clause the verifier is shown, with no name of the product it is about:
#: the heading above it carries that.
_DEBIT = (
    "A direct debit is a payment that the payee collects from the account of the payer."
)


def test_a_name_the_question_gives_need_not_come_back() -> None:
    """The reader of the question already has the name it asks about.

    The verifier answers what a `SEPA direct debit` is without saying `SEPA`
    again, which is how anybody answers a question that names its subject.
    """
    assert agrees(
        "a payment that the payee collects from the account of the payer",
        (
            "A SEPA direct debit is a payment that the payee collects from the "
            "account of the payer."
        ),
        "en",
        AnswerForm.EXPLANATION,
        question="What is a SEPA direct debit?",
    )


@pytest.mark.parametrize(
    ("given", "expected"),
    [("Payments > SEPA", True), ("Payments > Direct debits", False)],
    ids=["the heading names it", "nothing names it"],
)
def test_a_name_only_the_heading_carries_need_not_come_back(
    given: str, expected: bool
) -> None:
    """The writer is shown the heading trail and the verifier is not.

    So a name the clause never repeats is one the verifier cannot give back,
    however right the key is to carry it. Where neither the question nor the
    heading gives it, the key asserts a name the passages do not.
    """
    assert (
        agrees(
            "a payment that the payee collects from the account of the payer",
            (
                "A SEPA direct debit is a payment that the payee collects from "
                "the account of the payer."
            ),
            "en",
            AnswerForm.EXPLANATION,
            question="What is a direct debit?",
            given=given,
            passages=(_DEBIT,),
        )
        is expected
    )


def test_a_question_name_is_not_excused_when_the_recovery_names_another() -> None:
    """A recovery naming a name the key lacks answers for something else.

    Both cards are in the question, so `Visa` would count as given; the
    verifier came back with Mastercard's fee, and that is a weld.
    """
    assert not agrees(
        "Mastercard charges a foreign withdrawal fee of 2 percent of the amount.",
        "Visa charges a foreign withdrawal fee of 2 percent of the amount.",
        "en",
        AnswerForm.EXPLANATION,
        question="How do Visa and Mastercard handle foreign withdrawal fees?",
        given="Cards > Fees abroad",
        passages=(
            (
                "Mastercard charges a foreign withdrawal fee of 2 percent of the "
                "amount. Visa charges 1 percent."
            ),
        ),
    )


@pytest.mark.parametrize(
    ("question", "key", "recovered", "given", "passages", "language"),
    [
        (
            "Was kostet die Kontoführung im Monat?",
            "beim Premiumkonto 4,90 Euro",
            "4,90 Euro im Monat",
            "Konten > Premiumkonto\nKonten > Basiskonto",
            (
                "Die Kontoführung kostet 9,90 Euro im Monat.",
                "Die Kontoführung kostet 4,90 Euro im Monat.",
            ),
            "de",
        ),
        (
            "Was kostet die Kontoführung im Monat?",
            "Das Premiumkonto kostet 4,90 Euro im Monat.",
            "Das Basiskonto kostet 4,90 Euro im Monat.",
            "Konten > Premiumkonto\nKonten > Basiskonto",
            (
                "Die Kontoführung kostet 9,90 Euro im Monat.",
                "Das Basiskonto kostet 4,90 Euro im Monat.",
            ),
            "de",
        ),
        (
            "What is the annual fee for the card?",
            "Visa Gold: 40 euros a year",
            "40 euros a year",
            "Cards > Visa Gold\nCards > Mastercard Classic",
            ("The annual fee is 90 euros.", "The annual fee is 40 euros."),
            "en",
        ),
        (
            "What does standard delivery cost?",
            "free in Austria",
            "Standard delivery is free.",
            "Delivery > Germany\nDelivery > Austria",
            ("Standard delivery is free.", "Standard delivery costs 4.95 euros."),
            "en",
        ),
    ],
    ids=["Premiumkonto", "Premiumkonto for Basiskonto", "Visa Gold", "Austria"],
)
def test_a_name_one_heading_of_two_carries_is_not_given_to_a_key_about_the_other(
    question: str,
    key: str,
    recovered: str,
    given: str,
    passages: tuple[str, ...],
    language: str,
) -> None:
    """Two passages under two products' headings: which one came back?

    The figure may be the other product's, so only what every trail carries
    is given, `Konten` and not `Premiumkonto`.
    """
    assert not agrees(
        recovered,
        key,
        language,
        AnswerForm.VALUE,
        question=question,
        given=given,
        passages=passages,
    )


def test_a_name_every_heading_carries_need_not_come_back() -> None:
    """Two clauses under one product's headings are both about it."""
    assert agrees(
        "a payment that the payee collects from the account of the payer",
        (
            "A SEPA direct debit is a payment that the payee collects from the "
            "account of the payer."
        ),
        "en",
        AnswerForm.EXPLANATION,
        question="What is a direct debit?",
        given="Payments > SEPA > Core\nPayments > SEPA > Mandates",
        passages=(_DEBIT, "A mandate authorises the payee to collect."),
    )


@pytest.mark.parametrize(
    ("question", "key", "recovered", "given", "passage", "language"),
    [
        (
            "How soon is the purchase price refunded after the returned item arrives?",
            "within 30 days",
            "within 14 days",
            "Returns > 30-Day Return Policy",
            (
                "Items may be returned within 30 days of delivery. The purchase "
                "price is refunded within 14 days of receiving the return."
            ),
            "en",
        ),
        (
            (
                "Innerhalb welcher Frist erstattet der Händler den Kaufpreis nach "
                "Eingang der Rücksendung?"
            ),
            "innerhalb von 30 Tagen",
            "innerhalb von 14 Tagen",
            "Rückgabe > 30 Tage Rückgaberecht",
            (
                "Waren können innerhalb von 30 Tagen zurückgegeben werden. Der "
                "Kaufpreis wird innerhalb von 14 Tagen nach Eingang der "
                "Rücksendung erstattet."
            ),
            "de",
        ),
        (
            (
                "Wie lange hat der Kunde Zeit, Einwendungen gegen einen "
                "Rechnungsabschluss zu erheben?"
            ),
            "sieben Wochen",
            "sechs Wochen",
            "AGB-Banken > 7 Rechnungsabschlüsse",
            (
                "Einwendungen wegen Unrichtigkeit oder Unvollständigkeit eines "
                "Rechnungsabschlusses hat der Kunde spätestens vor Ablauf von "
                "sechs Wochen nach dessen Zugang zu erheben."
            ),
            "de",
        ),
    ],
    ids=["30-Day Return Policy", "30 Tage Rückgaberecht", "clause 7"],
)
def test_a_number_the_heading_gives_still_has_to_come_back(
    question: str, key: str, recovered: str, given: str, passage: str, language: str
) -> None:
    """A heading's number is the one a wrong key copies.

    `30-Day Return Policy` over a refund made within 14 days, and a clause
    numbered 7 over a deadline of six weeks: a name may be given, a number
    never is, because `4 hours` must not pass for `48 hours`.
    """
    assert not agrees(
        recovered,
        key,
        language,
        AnswerForm.VALUE,
        question=question,
        given=given,
        passages=(passage,),
    )


@pytest.mark.parametrize(
    ("question", "key", "recovered", "language"),
    [
        (
            (
                "Unarranged overdrafts cost 12 percent a year; what interest rate "
                "applies to an arranged overdraft?"
            ),
            "12 percent a year",
            "8 percent a year",
            "en",
        ),
        (
            (
                "Für eine geduldete Überziehung berechnet die Bank 12 Prozent im "
                "Jahr. Welcher Zinssatz gilt für eine eingeräumte Überziehung?"
            ),
            "12 Prozent im Jahr",
            "8 Prozent im Jahr",
            "de",
        ),
    ],
    ids=["en", "de"],
)
def test_a_number_the_question_gives_still_has_to_come_back(
    question: str, key: str, recovered: str, language: str
) -> None:
    """A key copying the question's figure answers the other half of it."""
    assert not agrees(recovered, key, language, AnswerForm.VALUE, question=question)


@pytest.mark.parametrize(
    ("question", "key", "recovered"),
    [
        (
            "How long does the shop take to send a replacement card?",
            "one week",
            "a replacement is sent within two weeks",
        ),
        (
            "How long does the shop take to send a replacement card?",
            "one week",
            "within a few weeks",
        ),
        (
            "How many debit cards does a joint account come with?",
            "one debit card",
            "a debit card for each account holder",
        ),
        (
            "How many free cash withdrawals a month does the account include?",
            "one free withdrawal",
            "a free withdrawal every week",
        ),
        (
            "How many reminders does the bank send before it terminates the loan?",
            "one reminder",
            "a reminder after every missed payment",
        ),
        (
            "How long is the notice period for an employee account?",
            "1 month",
            "a month for each year of membership",
        ),
    ],
    ids=["elsewhere", "a few", "each", "every week", "every payment", "each year"],
)
def test_an_article_does_not_stand_for_one(
    question: str, key: str, recovered: str
) -> None:
    """`a debit card for each account holder` is not `one debit card`.

    An article counts one per holder, per week or per payment as readily as
    it counts one, and `a few` is several; a key's `one` has to come back
    as a figure.
    """
    assert not agrees(recovered, key, "en", AnswerForm.VALUE, question=question)


def test_a_lemma_back_under_another_part_of_speech_counts() -> None:
    """`de_core_news_md` tags a predicative adjective an adverb.

    So `kostenlose Überweisungen` met `Überweisungen sind kostenlos` on no
    lemma it compared, though the two say the same.
    """
    assert agrees(
        "Überweisungen sind kostenlos",
        "kostenlose Überweisungen",
        "de",
        AnswerForm.LIST,
        question="Welche Überweisungen führt die Bank aus?",
    )


@pytest.mark.parametrize(
    ("question", "key", "recovered"),
    [
        (
            "Welche Überweisungen sind im Girokonto enthalten?",
            "kostenlose Überweisungen",
            "Überweisungen sind nicht kostenlos.",
        ),
        (
            "Wie wird die Kontoführungsgebühr berechnet?",
            "monatliche Kontoführungsgebühr",
            "Die Kontoführungsgebühr wird nicht monatlich, sondern jährlich berechnet.",
        ),
    ],
    ids=["nicht kostenlos", "nicht monatlich"],
)
def test_a_negated_adjective_does_not_bring_the_keys_adjective_back(
    question: str, key: str, recovered: str
) -> None:
    """`Überweisungen sind nicht kostenlos` denies what the key asserts."""
    assert not agrees(recovered, key, "de", AnswerForm.VALUE, question=question)


def test_a_verb_does_not_bring_back_the_keys_noun() -> None:
    """`das Verpacken` is not `verpackt`.

    Counting it would pass a key whose second item, the receipt, never came
    back.
    """
    assert not agrees(
        "der Kunde verpackt die Ware",
        "das Verpacken der Ware und ein Beleg",
        "de",
        AnswerForm.LIST,
        question="Was gehört zur Rücksendung?",
    )


@pytest.mark.parametrize(
    ("question", "key", "recovered", "given", "passage", "language", "form"),
    [
        (
            "What is the annual fee for the card?",
            "Visa Gold: 40 euros a year",
            "40 euros a year",
            "Cards > Visa Gold\nCards > Mastercard Classic",
            (
                "The Mastercard Classic costs 40 euros a year. The Visa Gold "
                "costs 90 euros a year."
            ),
            "en",
            AnswerForm.VALUE,
        ),
        (
            "Was erhält der Kunde bei einer Rücksendung ohne Beleg?",
            "eine Gutschrift",
            (
                "Der Kunde kann die Ware nur gutschreiben lassen, wenn er einen "
                "Beleg vorlegt; sonst erhält er nichts."
            ),
            "Rückgabe > Beleg",
            "Ohne Beleg erhält der Kunde nichts.",
            "de",
            AnswerForm.VALUE,
        ),
        (
            "What must a customer do to cancel a standing order?",
            "a written cancellation and a signed form",
            "the customer can cancel online and must sign nothing",
            "Standing orders > Cancellation",
            "A standing order can be cancelled online; no signature is required.",
            "en",
            AnswerForm.LIST,
        ),
        (
            "Which cards does the Premium tariff include?",
            "a Visa card and a Mastercard",
            "a debit card and a Mastercard",
            "Tariffs > Premium > Visa",
            "The tariff includes a debit card and a Mastercard.",
            "en",
            AnswerForm.LIST,
        ),
        (
            "Welche Karten enthält der Tarif Premium?",
            "Visa und Mastercard",
            "Debitkarte und Mastercard",
            "Tarife > Premium > Visa",
            "Der Tarif enthält eine Debitkarte und eine Mastercard.",
            "de",
            AnswerForm.LIST,
        ),
        (
            "Was kostet die Kontoführung im Monat?",
            "beim Premiumkonto 4,90 Euro",
            "4,90 Euro im Monat",
            "\nKonten > Premiumkonto",
            "Die Kontoführung kostet 4,90 Euro im Monat.",
            "de",
            AnswerForm.VALUE,
        ),
    ],
    ids=[
        "the heading's other card",
        "gutschreiben",
        "cancel and sign",
        "the heading's card for a debit card",
        "die Karte der Überschrift für die Debitkarte",
        "a heading one of two passages carries",
    ],
)
def test_what_the_reader_is_given_lets_no_wrong_key_through(
    question: str,
    key: str,
    recovered: str,
    given: str,
    passage: str,
    language: str,
    form: str,
) -> None:
    """Keys the passages contradict, with the heading and question to hand."""
    assert not agrees(
        recovered,
        key,
        language,
        form,
        question=question,
        given=given,
        passages=(passage,),
    )


def test_recalled_reads_what_agrees_reads() -> None:
    """The recorded share and the verdict come off one reading."""
    asked = {
        "language": "en",
        "form": AnswerForm.EXPLANATION,
        "question": "What is a direct debit?",
        "given": "Payments > SEPA",
        "passages": (_DEBIT,),
    }
    recovered = "a payment that the payee collects from the account of the payer"
    key = (
        "A SEPA direct debit is a payment that the payee collects from the "
        "account of the payer."
    )

    assert recalled(recovered, key, **asked) == 1.0
    assert agrees(recovered, key, **asked)


def test_the_round_trip_reads_the_heading_trail_the_writer_was_shown() -> None:
    """The checker hands the cited passages' section paths to the round trip."""
    result = build(
        Recording(
            recovers="a payment that the payee collects from the account of the payer"
        )
    ).check(
        candidate(
            question_text="What is a direct debit at this bank?",
            target_answer=(
                "A SEPA direct debit is a payment that the payee collects from "
                "the account of the payer."
            ),
            question_type=QuestionType.DEFINITION,
            facts=group(
                source(
                    statement="A direct debit is collected by the payee.",
                    passage_text=_DEBIT,
                    section_path="Payments > SEPA",
                )
            ),
        )
    )

    assert result.rejected_reason is None, result.rejected_reason


def test_an_ordinal_is_not_read_as_a_count_of_the_facts_cited() -> None:
    """`second half` names which half; it counts nothing, two facts cited or not."""
    assert (
        checked(
            question_text="Which half of the billing year does the fee apply to?",
            target_answer="second half",
            statements=_DEVICE_FACTS,
        )
        is None
    )


def test_a_refused_value_records_the_whole_it_was_held_to() -> None:
    """A value is compared whole, so its recall reading is held to all of it.

    Read against the share a list is held to, a value two-thirds recovered
    read as passing on a row the gate had refused.
    """
    recording = Recording(recovers="a notice to the tenant")

    result = build(recording).check(
        candidate(
            question_text="What must the landlord send before a rent increase?",
            target_answer="a formal notice to the tenant",
        )
    )

    recall = next(one for one in result.readings if one.gate == "recall")
    assert result.rejected_reason == QuestionRejection.NOT_RECOVERABLE
    assert recall.value < recall.threshold == 1.0


def test_a_value_recovered_whole_records_no_recall_margin() -> None:
    """A whole comparison holds or refuses, so there is no room to record.

    Its margin against all of itself is 0, and a row's confidence - the
    weakest margin it has - would then be 0 for every value key accepted.
    """
    result = build(Recording(recovers="4 kg")).check(candidate())

    assert result.accepted
    assert "recall" not in {one.gate for one in result.readings}


# ── The kind of question it was asked to be ───────────────────────────────


def test_no_gate_asks_the_verifier_what_kind_of_question_it_is_reading() -> None:
    """It was asked, and answered `true` for a question of the wrong kind.

    `wrong_form` carries the structural half, and `question_type` records
    what was asked for.
    """
    recording = Recording(recovers="because the plant was rebuilt in March")

    build(recording).check(
        candidate(
            question_text="Why was the device rebuilt at the Hamburg plant?",
            target_answer="because the plant was rebuilt in March",
            question_type="reason",
        )
    )

    assert list(inspect.signature(Verifier.read).parameters) == [
        "self",
        "question",
        "passages",
        "thread",
    ]


def test_the_type_and_the_form_are_stored_on_the_question() -> None:
    """A set cannot be filtered to its reasons unless each row says so."""
    result = build(Recording(recovers="4 kg")).check(candidate())

    assert result.question_type == "factoid"
    assert result.answer_form == "value"
    assert result.planned_difficulty == "easy"


@pytest.mark.parametrize(
    ("question", "key", "listing", "other", "language"),
    [
        (
            "Wie viele Gebühren berechnet die Bank für ein Girokonto insgesamt?",
            "3",
            (
                "Die Bank berechnet eine Kontoführungsgebühr, eine Kartengebühr und eine "
                "Gebühr für Auslandsüberweisungen."
            ),
            "Für ein Tagesgeldkonto fallen keine Gebühren an.",
            "de",
        ),
        (
            "How many payment methods does the shop accept in total?",
            "3",
            "The shop accepts card payments, invoices and bank transfers.",
            "Orders are shipped within two working days.",
            "en",
        ),
    ],
)
def test_a_count_of_one_facts_own_list_is_stored_as_a_lookup(
    question, key, listing, other, language
) -> None:
    """One fact listing the items states their count; nothing was added up."""
    result = build(Recording(recovers=key, backs=True)).check(
        candidate(
            question_text=question,
            target_answer=key,
            question_type=QuestionType.AGGREGATION,
            facts=group(
                source(1, passage_id=1, statement=listing, language=language),
                source(2, passage_id=2, statement=other, language=language),
            ),
        )
    )

    assert result.accepted, result.rejected_reason
    assert result.question_type == QuestionType.FACTOID


def test_a_count_no_one_fact_lists_stays_a_count() -> None:
    """Items listed across two facts are counted, which is the aggregation."""
    result = build(Recording(recovers="3", backs=True)).check(
        candidate(
            question_text="How many payment methods do the two shops accept in total?",
            target_answer="3",
            question_type=QuestionType.AGGREGATION,
            facts=group(
                source(
                    1, passage_id=1, statement="The first shop accepts card payments."
                ),
                source(
                    2,
                    passage_id=2,
                    statement="The second shop accepts invoices and bank transfers.",
                ),
            ),
        )
    )

    assert result.accepted, result.rejected_reason
    assert result.question_type == QuestionType.AGGREGATION


def test_the_categories_it_was_written_as_are_carried_to_the_row() -> None:
    """What the writer was told, beside what the gates made of it."""
    from dataclasses import replace

    from question_generation.models import Category

    told = (Category("Phrasing", "concise-and-natural", "short.", 0.5),)

    result = build(Recording(recovers="4 kg")).check(
        replace(candidate(), categories=told)
    )

    assert result.categories == told


def test_a_query_category_is_checked_as_a_query() -> None:
    """Its form decides whether the end-'?' rule reads it; nothing else does."""
    from dataclasses import replace

    from question_generation.models import Category

    keywords = replace(candidate(), question_text="device weight Hamburg plant")
    query = Category("Phrasing", "short-search-query", "keywords.", 0.25, form="query")
    asked = Category("Phrasing", "concise-and-natural", "short.", 0.25)

    typed = build(Recording(recovers="4 kg")).check(
        replace(keywords, categories=(query,))
    )
    written = build(Recording(recovers="4 kg")).check(
        replace(keywords, categories=(asked,))
    )

    assert typed.rejected_reason != QuestionRejection.MALFORMED
    assert written.rejected_reason == QuestionRejection.MALFORMED


def test_an_unanswerable_question_carries_no_answer_form() -> None:
    """It has no answer, so there is no shape for one to take."""
    result = build(Recording(recovers=None)).check(
        candidate(target_answer=None, answerable=False)
    )

    assert result.question_type == "factoid"
    assert result.answer_form is None


def test_the_verifier_is_told_to_answer_in_the_language_of_the_passages() -> None:
    """A translated answer agrees with nothing.

    An 8B verifier answered a German question with `to extract confidential
    information from the training data` where the target was `Extraktion
    vertraulicher Informationen`. The two say the same thing and share not
    one lemma, so a correct question was rejected as not_recoverable.
    """
    from question_generation.verifier import _VERIFY

    assert "language" in _VERIFY


# ── Two questions welded with a conjunction ───────────────────────────────


@pytest.mark.parametrize(
    "question",
    [
        (
            "Welche Vorschriften gelten für das Kreditgeschäft und wie hoch ist "
            "die Gebühr für das inländische Investmentwesen?"
        ),
        (
            "Warum hat sich die Lage der Pensionskassen entspannt und wie wird "
            "die Kreditentwicklung eingeschätzt?"
        ),
        "What fee applies to a licence and who approves the shift plan?",
    ],
)
def test_a_question_asking_two_things_is_refused(question) -> None:
    """Real rows, all of them written into a wide sample.

    Told to use both passages of a pair with no single question between them,
    the writer welds two together. A chatbot answering one of them is neither
    right nor wrong, and nobody types this.
    """
    failed = checked(
        question_text=question,
        target_answer=(
            "etwas und etwas anderes"
            if question.startswith(("Welche", "Warum"))
            else "a fee and a manager"
        ),
        language="de" if question.startswith(("Welche", "Warum")) else "en",
        form=AnswerForm.LIST,
    )

    assert code(failed) == QuestionRejection.COMPOUND


@pytest.mark.parametrize(
    ("question", "language"),
    [
        ("Welche Arten von Kryptowerten gelten als reguliert?", "de"),
        (
            (
                "Wie viele Meldungen gab es insgesamt in den Jahren 2025 und "
                "2024 zusammen?"
            ),
            "de",
        ),
        ("How do the reply times for standard and urgent requests differ?", "en"),
        ("How is a support request raised and confirmed?", "en"),
        ("Wodurch unterscheiden sich Tagesgeld und Festgeld?", "de"),
    ],
)
def test_one_question_about_two_things_is_kept(question, language) -> None:
    """A conjunction is not two questions.

    A finite-verb count does not separate these: `Welche Arten von Kryptowerten
    gelten als reguliert?` carries two verbs and is one question, and a
    comparison names both sides by construction.
    """
    assert (
        checked(
            question_text=question,
            target_answer="two things, and another",
            language=language,
            form=AnswerForm.LIST,
        )
        is None
    )


@pytest.mark.parametrize(
    ("question", "language"),
    [
        (
            (
                "How do card payments and bank transfers differ in where the "
                "money is held?"
            ),
            "en",
        ),
        ("What is the rule on who may approve a refund?", "en"),
        ("Wovon hängt ab, wann ein Konto gesperrt wird?", "de"),
        ("Wie unterscheiden sich Mahnung und Sperre darin, wen sie betreffen?", "de"),
    ],
)
def test_a_question_word_opening_a_clause_is_not_a_second_question(
    question: str, language: str
) -> None:
    """`where the money is held` is what is asked about, not a second ask."""
    assert (
        checked(
            question_text=question,
            target_answer=(
                "two things, and another"
                if language == "en"
                else "zwei Dinge, und eins"
            ),
            language=language,
            form=AnswerForm.LIST,
        )
        is None
    )


@pytest.mark.parametrize(
    ("question", "language"),
    [
        ("When is a card blocked and when is it unblocked?", "en"),
        ("Wann wird ein Konto gesperrt und wann wird es wieder freigegeben?", "de"),
        ("What does a transfer cost and for how long is it held?", "en"),
        (
            "Worauf muss der Kunde bei der Rücksendung achten und wer trägt die Kosten?",
            "de",
        ),
        (
            "Woran erkennt der Kunde eine gefälschte E-Mail, und was soll er tun?",
            "de",
        ),
    ],
)
def test_a_question_word_after_a_conjunction_is_a_second_question(
    question: str, language: str
) -> None:
    """A conjunction, a preposition at most between, and a second ask."""
    assert (
        code(
            checked(
                question_text=question,
                target_answer="two things, and another",
                language=language,
                form=AnswerForm.LIST,
            )
        )
        == QuestionRejection.COMPOUND
    )


def test_the_target_answer_may_restate_the_question_without_disagreeing() -> None:
    """A real rejection, and a false one.

    The writer answered `Die Regionen, in die chinesische Produkte exportiert
    werden, umfassen Südostasien und Afrika`; the verifier answered
    `Südostasien, Afrika und Europa`. They agree about everything the answer
    carries and share two lemmas of seven, so counting the question's own
    words threw a good question away.
    """
    question = "In welche Regionen werden chinesische Produkte exportiert?"
    target = (
        "Die Regionen, in die chinesische Produkte exportiert werden, "
        "umfassen Südostasien und Afrika."
    )

    assert not agrees("Südostasien, Afrika und Europa", target, "de", AnswerForm.LIST)
    assert agrees(
        "Südostasien, Afrika und Europa",
        target,
        "de",
        AnswerForm.LIST,
        OVERLAP,
        question,
    )
    assert (
        recalled(
            "Südostasien, Afrika und Europa", target, "de", AnswerForm.LIST, question
        )
        >= OVERLAP
    ), "the recorded recall reads the key as the verdict did"


# ── The measurement behind the phrasing opinion ───────────────────────────


@pytest.mark.parametrize(
    ("question", "language"),
    [
        ("What specific components are included?", "en"),
        ("For which models do the requirements apply?", "en"),
        ("Which criteria are used?", "en"),
        ("Welche spezifischen Komponenten sind enthalten?", "de"),
    ],
)
def test_a_question_naming_nothing_is_thin_enough_to_reject(question, language) -> None:
    """The two the gate exists for, and two of the same shape."""
    assert not anchored(question, language)


@pytest.mark.parametrize(
    ("question", "language"),
    [
        (
            (
                "Wann wurde die Erlaubnis des Versicherers nach Eröffnung "
                "des endgültigen Insolvenzverfahrens widerrufen?"
            ),
            "de",
        ),
        ("Für welche Ziele setzt sich die Bafin ein?", "de"),
        ("Wozu nutzt die BaFin das DORA-Informationsregister?", "de"),
        ("What fee applies to a banking licence application?", "en"),
        ("Wie hoch war der Anteil der überschuldeten Verbraucher?", "de"),
    ],
)
def test_a_question_naming_something_is_never_called_unanchored(
    question, language
) -> None:
    """Real rows the verifier called unanchored, every one of them anchored.

    A name, a number, or three things. The first names five, the second and
    third name a party, and the gate may not overrule that.
    """
    assert anchored(question, language)


@pytest.mark.parametrize(
    "query", ["girokonto kündigungsfrist gebühr", "rücksendung frist online bestellung"]
)
def test_a_lower_cased_german_query_is_anchored_as_its_capitalised_twin(query) -> None:
    """Typed all in lower case, a German query's case says nothing about its nouns."""
    assert anchored(query.title(), "de")
    assert anchored(query, "de")


def test_a_lower_cased_german_query_is_held_to_what_the_passages_are_about() -> None:
    """`about` measures it, rather than abstaining as for a query naming nothing."""
    from question_generation.gates import ENTAILMENT_OVERLAP, about

    passage = (
        "Für Lieferungen ins Ausland berechnet der Shop eine Versandpauschale von 9,95 EUR.",
    )
    assert not about(
        "Girokonto Kündigungsfrist Gebühr", passage, "de", ENTAILMENT_OVERLAP
    )
    assert not about(
        "girokonto kündigungsfrist gebühr", passage, "de", ENTAILMENT_OVERLAP
    )


def test_the_verifier_cannot_reject_a_question_that_names_something() -> None:
    """An opinion needs a measurement behind it, not only a second model."""
    recording = Recording(recovers="4 kg", stands_alone=False)

    result = build(recording).check(
        candidate(question_text="What fee applies to a banking licence application?")
    )

    assert result.accepted, "the verifier overruled the question's own subjects"


# ── The forms a type will take ─────────────────────────────────────────────


def test_a_type_takes_the_form_its_answer_actually_has() -> None:
    """A factoid answered with three tools is not a malformed factoid.

    The material decides what shape an answer has, not the question. Held to
    the one form its type asked for, `Welche Werkzeuge werden empfohlen?` ->
    `statische Analysatoren, Linter und Formatierer` was refused for the form
    it arrived in, and then held to a value's stricter comparison on the way
    out.
    """
    form, failed = fitting(
        "unterschiedliche Fähigkeiten, Kompetenzen, Rollen und Verantwortung",
        (AnswerForm.VALUE, AnswerForm.LIST),
        BOUNDS,
        "de",
    )

    assert failed is None
    assert form == AnswerForm.LIST


def test_a_condition_answered_with_a_value_is_kept() -> None:
    """`immer` is the condition, and it is one word."""
    form, failed = fitting("immer", (AnswerForm.LIST, AnswerForm.VALUE), BOUNDS, "de")

    assert failed is None
    assert form == AnswerForm.VALUE


def test_a_form_the_type_does_not_allow_is_still_refused() -> None:
    """The point is a wider set of forms, not no check at all."""
    _, failed = fitting(
        "die Testbarkeit des Systems", (AnswerForm.EXPLANATION,), BOUNDS, "de"
    )

    assert code(failed) == QuestionRejection.WRONG_FORM


def test_two_items_are_not_a_list() -> None:
    """`Berlin, 2025` is a value with a comma in it, not a set of two."""
    form, failed = fitting(
        "Berlin, 2025", (AnswerForm.VALUE, AnswerForm.LIST), BOUNDS, "en"
    )

    assert failed is None
    assert form == AnswerForm.VALUE


def test_two_items_are_a_list_where_the_type_asked_for_one() -> None:
    """A `condition` asks for a list first, so its two conditions are one.

    Neither carries a verb, so the shape hint alone reads it as a value.
    """
    form, failed = fitting(
        "for card fraud, and for unpaid fees",
        (AnswerForm.LIST, AnswerForm.VALUE),
        BOUNDS,
        "en",
    )

    assert failed is None
    assert form == AnswerForm.LIST


@pytest.mark.parametrize(
    ("answer", "forms"),
    [
        ("ab einem Bestellwert von 49,90 €", (AnswerForm.LIST, AnswerForm.VALUE)),
        ("von 6,4 % auf 6,1 %", (AnswerForm.VALUE, AnswerForm.LIST)),
    ],
)
def test_a_decimal_comma_separates_no_items(answer: str, forms) -> None:
    """`49,90 €` is one amount, where a type asked for a list first as well."""
    form, failed = fitting(answer, forms, BOUNDS, "de")

    assert failed is None
    assert form == AnswerForm.VALUE


def test_two_clauses_carrying_verbs_stay_an_explanation_where_one_is_allowed() -> None:
    """A `comparison` takes an explanation, and two clauses with verbs are one."""
    form, failed = fitting(
        "card payments settle at once, bank transfers take a working day",
        (AnswerForm.LIST, AnswerForm.EXPLANATION),
        BOUNDS,
        "en",
    )

    assert failed is None
    assert form == AnswerForm.EXPLANATION


def test_two_clauses_carrying_verbs_are_a_list_where_no_explanation_is_allowed() -> (
    None
):
    """A `condition` takes no explanation, so its two conditions stay a list."""
    form, failed = fitting(
        "if the login fails, or if the card expires",
        (AnswerForm.LIST, AnswerForm.VALUE),
        BOUNDS,
        "en",
    )

    assert failed is None
    assert form == AnswerForm.LIST


def test_the_complaint_reported_is_the_asked_for_forms() -> None:
    """That is the form the writer was told to produce, so it is the one to show."""
    form, failed = fitting("x" * 700, (AnswerForm.VALUE, AnswerForm.LIST), BOUNDS, "en")

    assert form == AnswerForm.VALUE
    assert code(failed) == QuestionRejection.ANSWER_TOO_LONG


# ── The gates an unanswerable question faces ───────────────────────────────


def test_a_question_about_the_material_is_on_topic() -> None:
    """A perturbation keeps the subject and moves one detail out of reach."""
    assert on_topic(
        "How long is allowed for a standard request on a public holiday?",
        "en",
        frozenset({"standard", "request", "holiday", "hour"}),
        0.3,
    )


def test_a_question_about_nothing_the_material_mentions_is_off_topic() -> None:
    """Any chatbot declines it, so declining it proves nothing."""
    assert not on_topic(
        "What is the top speed of a swallow?",
        "en",
        frozenset({"standard", "request", "holiday", "hour"}),
        0.3,
    )


def test_a_passage_with_no_lemmas_refuses_nothing() -> None:
    """A measurement with nothing to measure against is not evidence."""
    assert on_topic("What is the top speed of a swallow?", "en", frozenset(), 0.3)


def test_a_floor_of_zero_turns_the_gate_off() -> None:
    """One setting, and 0 is how a deployment declines to hold the opinion."""
    assert on_topic("What is the top speed of a swallow?", "en", frozenset({"a"}), 0.0)


def test_the_shipped_setting_refuses_no_perturbation_as_off_topic() -> None:
    """QUESTIONS_OFF_TOPIC_OVERLAP ships at 0, so the gate abstains.

    A perturbation moves a fact out of reach by design, so it carries words
    its one cited passage lacks - and that one passage was the whole
    vocabulary it was measured against.
    """
    shipped = Settings.load().off_topic_overlap
    recording = Recording(recovers=None)
    checker = QuestionChecker(
        embedder=recording,
        verifier=recording,
        nearest=lambda embedding, **_: None,
        threshold=0.93,
        off_topic_overlap=shipped,
    )

    result = checker.check(
        candidate(
            question_text=(
                "How much does the device weigh with its winter battery pack fitted?"
            ),
            target_answer=None,
            answerable=False,
            facts=group(source(lemmas=("device", "weight", "kg"))),
        )
    )

    assert result.rejected_reason != QuestionRejection.OFF_TOPIC
    assert "off_topic" not in {reading.gate for reading in result.readings}
    assert shipped == 0


def test_an_unanswerable_question_no_other_passage_answers_stands() -> None:
    """The one claim here that is about the corpus and not about two passages.

    A question wrongly carrying "nothing here answers this" marks a correct
    chatbot wrong, which is the failure every gate exists to stop.
    """
    recording = Recording(recovers=None)
    checker = QuestionChecker(
        embedder=recording,
        verifier=recording,
        nearest=lambda embedding, **_: None,
        threshold=0.93,
        bounds=BOUNDS,
        elsewhere=lambda lemmas, language, skip, limit, embedding=None: [
            "It is 48 hours."
        ],
        elsewhere_passages=4,
    )

    # The corpus probe re-reads with the same stub, which recovers nothing on
    # the first pass; scripting it to recover is what the second pass reads.
    recording.recovers = None
    result = checker.check(
        candidate(
            question_text="How long is allowed for a request on a holiday?",
            target_answer=None,
            answerable=False,
        )
    )

    # Nothing was found anywhere, so it stands.
    assert result.status == "accepted"


_WRITING = (
    "A transfer above the daily limit must be confirmed in writing, so that "
    "the agreed release time can be evidenced later."
)


@pytest.mark.parametrize(
    ("recovered", "key", "refused"),
    [
        (
            "A transfer above the daily limit must be confirmed in writing.",
            "because written confirmation is required for transfers above the limit",
            True,
        ),
        (
            "so that the agreed release time can be evidenced later",
            "so that the agreed release time can be evidenced later",
            False,
        ),
    ],
    ids=["the rule said back", "the reason"],
)
def test_a_why_whose_recovery_only_says_the_rule_back_has_no_reason(
    recovered: str, key: str, refused: bool
) -> None:
    """The verifier read the passages for a reason and came back with the rule.

    A key restating the rule in other words is entailed by the passages, so
    the entailment pass would accept the circle.
    """
    result = build(Recording(recovers=recovered, backs=True)).check(
        candidate(
            question_text="Why must a transfer above the daily limit be confirmed in writing?",
            target_answer=key,
            question_type=QuestionType.REASON,
            facts=group(source(statement=_WRITING, passage_text=_WRITING)),
        )
    )

    assert (result.rejected_reason == QuestionRejection.NOT_RECOVERABLE) is refused, (
        result.rejected_reason
    )


# ── The entailment pass ────────────────────────────────────────────────────


def test_recall_missing_an_answer_the_passages_support_is_rescued() -> None:
    """Recalling an answer cold is a harder task than checking one."""
    recording = Recording(recovers="It ships from Hamburg.", backs=True)

    result = build(recording).check(candidate(target_answer="4 kg"))

    assert result.status == "accepted"
    assert recording.supported == 1


def test_the_entailment_pass_can_only_accept() -> None:
    """A question reaching it was already being refused."""
    recording = Recording(recovers="It ships from Hamburg.", backs=False)

    result = build(recording).check(candidate(target_answer="4 kg"))

    assert result.rejected_reason == QuestionRejection.NOT_RECOVERABLE
    assert recording.supported == 1


def test_a_key_the_verifier_could_not_find_is_not_rescued() -> None:
    """The verifier read the question against the passages and found nothing.

    The rescue scores the bare key against each passage, without the
    question, so a fragment the passages happen to contain is entailed
    whatever was asked. The verifier's NOT IN PASSAGE is the one reading
    that saw the question, and no rescue overrides it.
    """
    recording = Recording(recovers=None, backs=True)

    result = build(recording).check(candidate(target_answer="4 kg"))

    assert result.rejected_reason == QuestionRejection.NOT_RECOVERABLE
    assert recording.supported == 0, "the entailment pass was asked"


def test_a_why_the_verifier_found_nothing_for_has_no_reason(caplog) -> None:
    """Asked for a reason, the verifier found none in the passages."""
    recording = Recording(recovers=None, backs=True)

    with caplog.at_level("INFO", logger="question_generation.checker"):
        result = build(recording).check(
            candidate(
                question_text="Why must a request be confirmed in writing?",
                target_answer="so that the agreed time can be evidenced later",
                question_type=QuestionType.REASON,
                facts=group(
                    source(
                        passage_text=(
                            "Requests are confirmed in writing so the agreed "
                            "time can be evidenced later."
                        )
                    )
                ),
            )
        )

    assert result.rejected_reason == QuestionRejection.NOT_RECOVERABLE
    assert "no reason" in caplog.text, caplog.text
    assert recording.supported == 0


def test_an_answer_to_a_different_question_is_not_rescued() -> None:
    """The LMT case, which the rescue pass used to wave through.

    `Was ist ein Liquiditätsmanagementtool?` answered `eine einjährige
    Rückgabefrist` clears the numbers guard, because that phrase is lifted
    straight out of the passage, and any judge asked "do these passages say
    what this answer says" agrees - they do say it. What they never mention
    is a Liquiditätsmanagementtool, so the answer is supported and answers
    something else.
    """
    recording = Recording(
        recovers=(
            "Die Verwaltungsgesellschaft veröffentlicht die Frist im Verkaufsprospekt."
        ),
        backs=True,
    )

    result = build(recording).check(
        candidate(
            question_text="Was ist ein Liquiditätsmanagementtool?",
            target_answer="eine einjährige Rückgabefrist",
            facts=group(
                source(
                    1,
                    statement="Für den Fonds gilt eine einjährige Rückgabefrist.",
                    language="de",
                    passage_text=(
                        "Für den Fonds gilt eine einjährige Rückgabefrist. Die "
                        "Verwaltungsgesellschaft veröffentlicht die Frist im "
                        "Verkaufsprospekt."
                    ),
                )
            ),
        )
    )

    assert result.rejected_reason == QuestionRejection.NOT_RECOVERABLE
    assert recording.supported == 0, "the judgement is never reached"


class Reader:
    """An extractive reader answering with one span, or with none."""

    def __init__(self, text: str | None) -> None:
        self.text = text
        self.asked = 0

    def answer(self, question: str, passages, confidence: float):
        """The scripted span, and a count of the asks."""
        from nlp.qa import Span

        self.asked += 1
        if self.text is None:
            return None
        return Span(self.text, 0.95)


def _with_reader(recording: Recording, reader: Reader) -> QuestionChecker:
    """A checker whose recall half asks the encoder first."""
    return QuestionChecker(
        embedder=recording,
        verifier=recording,
        nearest=lambda embedding, **_: None,
        threshold=0.93,
        phrasing=recording,
        extractive=reader,
    )


def test_a_confident_span_answers_recall_without_a_call() -> None:
    """The easy case, answered locally."""
    recording = Recording(recovers="4 kg")
    reader = Reader("4 kg")

    result = _with_reader(recording, reader).check(candidate(target_answer="4 kg"))

    assert result.accepted
    assert reader.asked == 1
    assert recording.verified == 0, "the served model was not needed"


def test_no_span_falls_through_to_something_that_can_read() -> None:
    """Every span it gives is contiguous and inside one passage.

    The verifier is allowed to put an answer together from two sentences,
    so a reader that found nothing must not be read as a refusal.
    """
    recording = Recording(recovers="4 kg")
    reader = Reader(None)

    result = _with_reader(recording, reader).check(candidate(target_answer="4 kg"))

    assert result.accepted
    assert reader.asked == 1
    assert recording.verified == 1, "the served model answered instead"


def test_a_follow_up_never_reaches_the_extractive_reader() -> None:
    """`And for an urgent one?` is answered in a conversation.

    An extractive model has nowhere to put one, so it would answer the
    question as if it had been asked cold.
    """
    recording = Recording(recovers="4 hours")
    reader = Reader("4 kg")

    _with_reader(recording, reader).check(
        candidate(
            question_text="How long is allowed for answering an urgent request?",
            target_answer="4 hours",
            thread=(("How long for a standard support request?", "48 hours"),),
        )
    )

    assert reader.asked == 0
    assert recording.verified == 1


def test_an_encoder_answers_the_pass_where_one_is_configured() -> None:
    """The served model is not asked when an NLI model is to hand."""

    class Encoder:
        """One verdict, and a count of the pairs it was handed."""

        def __init__(self, entailment: float) -> None:
            self.entailment = entailment
            self.pairs: list[tuple[str, str]] = []

        def judge_all(self, pairs):
            from nlp.entailment import Verdict

            self.pairs.extend(pairs)
            return [Verdict(self.entailment, 1 - self.entailment, 0.0) for _ in pairs]

    recording = Recording(recovers="It ships from Hamburg.", backs=False)
    encoder = Encoder(entailment=0.9)
    checker = QuestionChecker(
        embedder=recording,
        verifier=recording,
        nearest=lambda embedding, **_: None,
        threshold=0.93,
        phrasing=recording,
        entailment=encoder,
        entailment_threshold=0.5,
    )

    result = checker.check(candidate(target_answer="4 kg"))

    assert result.accepted, "the encoder said the passages entail it"
    assert recording.supported == 0, "no served model was asked"
    assert encoder.pairs, "the encoder was handed a premise and a hypothesis"


def test_the_encoder_is_asked_one_passage_at_a_time() -> None:
    """One premise, one hypothesis, which is what an NLI model was trained on.

    A premise of several passages joined is both a worse question than the
    one being asked and longer than some heads accept.
    """

    class Encoder:
        """Refuses everything, and remembers what it was shown."""

        def __init__(self) -> None:
            self.pairs: list[tuple[str, str]] = []

        def judge_all(self, pairs):
            from nlp.entailment import Verdict

            self.pairs.extend(pairs)
            return [Verdict(0.0, 1.0, 0.0) for _ in pairs]

    recording = Recording(recovers="It ships from Hamburg.", backs=False)
    encoder = Encoder()
    checker = QuestionChecker(
        embedder=recording,
        verifier=recording,
        nearest=lambda embedding, **_: None,
        threshold=0.93,
        phrasing=recording,
        entailment=encoder,
    )

    checker.check(candidate(target_answer="4 kg"))

    assert len(encoder.pairs) == 1, "one pair per passage, and there is one"
    assert "\n\n" not in encoder.pairs[0][0], "the passages were joined"


def test_a_number_the_passages_never_gave_is_not_rescued() -> None:
    """The one error that must not get through, whatever the model says.

    `4 hours` confirmed against a passage that says 48 puts a question in
    the benchmark whose answer the material does not give, which marks a
    correct chatbot wrong.
    """
    recording = Recording(recovers="within 4 hours", backs=True)

    result = build(recording).check(
        candidate(
            question_text="How long is allowed for a standard request?",
            target_answer="48 hours",
            facts=group(
                source(passage_text="A standard request is answered within 4 hours.")
            ),
        )
    )

    assert result.rejected_reason == QuestionRejection.NOT_RECOVERABLE
    # Refused before the model was asked, because the guard is free.
    assert recording.supported == 0


def test_a_target_asserting_nothing_numeric_reaches_the_pass() -> None:
    """The guard is about numbers and names; prose has none to check."""
    recording = Recording(recovers="for evidence", backs=True)

    result = build(recording).check(
        candidate(
            question_text="Why must a request be confirmed in writing?",
            target_answer="so that the agreed time can be evidenced later",
            question_type=QuestionType.REASON,
            facts=group(
                source(
                    passage_text=(
                        "Requests are confirmed in writing so the agreed time "
                        "can be evidenced later."
                    )
                )
            ),
        )
    )

    assert result.status == "accepted"
    assert recording.supported == 1


# ── Pointing at what the asker cannot see ─────────────────────────────────


def test_a_question_pointing_outside_itself_is_refused() -> None:
    """The failure that shipped: correct arithmetic, unanswerable question.

    `Wie groß ist der Unterschied ... zwischen diesen beiden Lehrplänen?` was
    accepted over two facts that do differ by the answer it gives. Nobody can
    answer it, because nothing says which two.
    """
    recording = Recording(recovers="2.5 hours", self_contained=False)

    result = build(recording).check(
        candidate(question_text="How long is the gap between these two editions?")
    )

    assert result.rejected_reason == QuestionRejection.UNANCHORED


def test_a_question_that_sets_its_own_case_up_is_kept() -> None:
    """The measurement over-fires and may only veto, so the verifier decides.

    A question carrying a pointer may name what it points at first. Those
    are the `application` type working as designed, and a rule reading the
    pointer alone would throw every one of them out.
    """
    recording = Recording(recovers="4 kg", self_contained=True)

    result = build(recording).check(
        candidate(
            question_text=(
                "If a system meets its target by editing the stored score, "
                "how is this behaviour classified?"
            )
        )
    )

    assert result.status == QuestionStatus.ACCEPTED


def test_a_follow_up_may_point_at_the_conversation() -> None:
    """Leaning on the thread is what a follow-up is for."""
    recording = Recording(recovers="4 kg", self_contained=False)

    result = build(recording).check(
        candidate(
            question_text="And how long does that one take?",
            thread=(("What does the device weigh?", "4 kg"),),
        )
    )

    assert result.rejected_reason != QuestionRejection.UNANCHORED


def test_a_reader_finding_no_span_elsewhere_still_lets_the_probe_settle_it() -> None:
    """A refutation or a general rule is not a span.

    The extractive reader answers "where is the answer" and nothing else, so
    its finding nothing in the probe says nothing about whether a passage
    there refutes the question's premise. The verifier is asked regardless.
    """
    recording = Recording(recovers=None)
    reader = Reader(None)

    def settles(question, passages):
        recording.verified += 1
        if any("Only account holders" in passage for passage in passages):
            return Settled(verdict=Settling.REFUTES, quote="Only account holders")
        return Settled(verdict=Settling.SILENT, quote=None)

    recording.settles = settles  # type: ignore[method-assign]
    checker = QuestionChecker(
        embedder=recording,
        verifier=recording,
        nearest=lambda embedding, **_: None,
        threshold=0.93,
        phrasing=recording,
        elsewhere=lambda *a, **k: ["Only account holders are refunded."],
        elsewhere_passages=2,
        extractive=reader,
    )

    result = checker.check(candidate(target_answer=None, answerable=False))

    assert result.rejected_reason == QuestionRejection.ANSWERABLE_ELSEWHERE
    assert recording.verified == 2, "its own passages, then the probe"


def test_a_span_in_its_own_passages_does_not_reject_an_unanswerable_question() -> None:
    """The same verdict as the gate above, so the same rule applies.

    `answerable_after_all` says the cited passages answer a question
    written to have none, which marks a correct chatbot wrong. The reader
    was deciding that alone, where one passage further on it may only ask.
    """
    recording = Recording(recovers=None)
    reader = Reader("4 kg")

    result = _with_reader(recording, reader).check(
        candidate(target_answer=None, answerable=False)
    )

    assert result.accepted
    assert reader.asked == 0, "the recall half of an unanswerable one is the verifier's"
    assert recording.verified == 1


def test_the_verifier_still_rejects_an_unanswerable_question_it_can_answer() -> None:
    """Removing the reader from this path must not remove the gate."""
    recording = Recording(recovers="4 kg")

    result = _with_reader(recording, Reader("4 kg")).check(
        candidate(target_answer=None, answerable=False)
    )

    assert result.rejected_reason == QuestionRejection.ANSWERABLE_AFTER_ALL


# ── The long answer ────────────────────────────────────────────────────────


#: A passage holding every figure the explanations below assert, so a test
#: about length or restatement is not stopped by `asserted`.
_PASSAGES = (
    (
        "A standard support request is answered within 48 hours. An urgent "
        "request is answered within 4 hours, and only on working days."
    ),
)


def _reads(text: str) -> bool:
    """Whether one explanation of the 48-hour answer is usable."""
    return explains(text, "48 hours", _PASSAGES, "en")


def test_no_explanation_at_all_is_not_a_failure() -> None:
    """The column is nullable, and a row written before it has none."""
    assert _reads("")
    assert explains("", "48 hours", _PASSAGES, "en")


@pytest.mark.parametrize(
    ("question", "key", "passage", "language"),
    [
        (
            "Wie hoch ist die monatliche Kontoführungsgebühr für ein Girokonto?",
            "4,90 EUR",
            "Die Kontoführungsgebühr für ein Girokonto beträgt 4,90 EUR im Monat.",
            "de",
        ),
        (
            "How much is the monthly fee for a current account?",
            "4.90 EUR",
            "The monthly fee for a current account is 4.90 EUR.",
            "en",
        ),
    ],
)
def test_an_answerable_question_written_without_its_explanation_is_refused(
    question, key, passage, language
) -> None:
    """Every answerable question carries its second answer; a stored row may not."""
    result = build(Recording(recovers=key)).check(
        candidate(
            question_text=question,
            target_answer=key,
            facts=group(
                source(1, statement=passage, passage_text=passage, language=language)
            ),
            answer_explanation=None,  # what the writer stores for an empty one
        )
    )

    assert result.rejected_reason == QuestionRejection.EXPLANATION_UNUSABLE


def test_an_explanation_too_short_to_be_a_reading_is_refused() -> None:
    """This is the failure the column was added for: the key said twice."""
    assert not _reads("It is 48 hours.")


def test_an_explanation_past_its_ceiling_is_refused() -> None:
    """An explanation that long has become the passage."""
    assert not explains("word " * 400, "48 hours", _PASSAGES, "en", (150, 900))


def test_an_explanation_asserting_a_figure_the_passages_lack_is_refused() -> None:
    """The one failure here that can put a wrong claim before a reader.

    Everything else this gate catches is a bad read. A number the material
    never gave is the defect `asserted` exists for, and 72 is not in the
    passages.
    """
    assert not _reads(
        "A standard support request has to be answered within 72 hours. That "
        "is the ordinary service level and the slower of the two the material "
        "sets, because an urgent request is answered far sooner than a "
        "standard one ever is."
    )


def test_an_explanation_that_only_restates_the_key_is_refused() -> None:
    """Padding the key to length is not explaining it."""
    assert not explains(
        "48 hours. 48 hours. 48 hours. 48 hours. 48 hours. 48 hours. 48 "
        "hours. 48 hours. 48 hours. 48 hours. 48 hours. 48 hours. 48 hours.",
        "48 hours",
        _PASSAGES,
        "en",
    )


def test_an_explanation_that_reads_and_rests_on_the_passages_passes() -> None:
    """What the column is for."""
    assert _reads(
        "A standard support request has to be answered within 48 hours. That "
        "is the ordinary service level, and it is the slower of the two the "
        "material sets: a request marked urgent is answered within 4 hours "
        "instead. The hours are the time allowed for the answer rather than "
        "for resolving what was asked about."
    )


@pytest.mark.parametrize(
    ("explanation", "key", "passage", "language"),
    [
        (
            (
                "Ein Kunde kann sein Girokonto jederzeit kündigen. Laut Herrn Becker von der "
                "Filiale reicht dafür ein formloses Schreiben, das per Post oder online "
                "eingereicht wird. Die Bank bestätigt die Kündigung schriftlich."
            ),
            "durch ein formloses Schreiben",
            (
                "Ein Girokonto kann jederzeit durch ein formloses Schreiben gekündigt werden. "
                "Die Bank bestätigt die Kündigung schriftlich."
            ),
            "de",
        ),
        (
            (
                "A customer can return an unused item within 14 days of delivery. Suzanne's "
                "fact is about a late delivery, so the return period is the one that applies "
                "here. The shop refunds the price to the card used."
            ),
            "within 14 days of delivery",
            (
                "Unused items can be returned within 14 days of delivery. The price is "
                "refunded to the card used."
            ),
            "en",
        ),
    ],
)
def test_an_explanation_naming_a_person_its_passages_never_name_is_refused(
    explanation, key, passage, language
) -> None:
    """A name from another passage of the sample is one the reader never sees."""
    assert not explains(explanation, key, (passage,), language)


@pytest.mark.parametrize(
    ("explanation", "language"),
    [
        (
            (
                "A standard support request has to be answered within 48 hours. The "
                "passage sets that as the ordinary service level, and a request marked "
                "urgent is answered within 4 hours instead, on working days only."
            ),
            "en",
        ),
        (
            (
                "A standard support request has to be answered within 48 hours. Together "
                "these facts make that the ordinary service level, and a request marked "
                "urgent is answered within 4 hours instead, on working days only."
            ),
            "en",
        ),
        (
            (
                "Eine normale Supportanfrage wird innerhalb von 48 Stunden beantwortet. "
                "Laut den Fakten ist das die übliche Frist, während eine dringende Anfrage "
                "innerhalb von 4 Stunden beantwortet wird, und zwar nur an Werktagen."
            ),
            "de",
        ),
    ],
)
def test_an_explanation_speaking_of_its_own_inputs_is_refused(
    explanation, language
) -> None:
    """The writer's labels for what it was handed mean nothing to a reader."""
    passages = {
        "de": (
            (
                "Eine normale Supportanfrage wird innerhalb von 48 Stunden beantwortet. "
                "Eine dringende Anfrage wird innerhalb von 4 Stunden beantwortet, und "
                "zwar nur an Werktagen."
            ),
        ),
        "en": _PASSAGES,
    }[language]
    assert not explains(explanation, "48 hours", passages, language)


def test_an_explanation_using_the_word_in_its_own_sense_passes() -> None:
    """`In fact` and `the fact that ...` say nothing of the writer's inputs."""
    assert _reads(
        "A standard support request has to be answered within 48 hours. In fact, "
        "that is the ordinary service level, and the fact that an urgent request is "
        "answered within 4 hours shows how far apart the two levels are."
    )


@pytest.mark.parametrize(
    ("question", "key", "passage", "language", "refused"),
    [
        (
            "Which fee did Paolo pay for a basic account abroad?",
            "3 EUR a month",
            "A basic account abroad costs 3 EUR a month.",
            "en",
            True,
        ),
        (
            "Welche Gebühr zahlte Herr Becker für ein Basiskonto im Ausland?",
            "3 EUR im Monat",
            "Ein Basiskonto im Ausland kostet 3 EUR im Monat.",
            "de",
            True,
        ),
        (
            "Which fee did Paolo pay for a basic account abroad?",
            "3 EUR a month",
            "Paolo pays 3 EUR a month for a basic account abroad.",
            "en",
            False,
        ),
        (
            "Welche Gebühr zahlt Olivia für ein Basiskonto im Ausland?",
            "3 EUR im Monat",
            "Olivias Basiskonto im Ausland kostet 3 EUR im Monat.",
            "de",
            False,
        ),
    ],
)
def test_a_question_naming_a_person_its_passages_never_name_is_refused(
    question, key, passage, language, refused
) -> None:
    """A person brought in from another passage of the sample is never found."""
    recording = Recording(recovers=key)

    result = build(recording).check(
        candidate(
            question_text=question,
            target_answer=key,
            facts=group(
                source(1, statement=passage, passage_text=passage, language=language)
            ),
        )
    )

    if refused:
        assert result.rejected_reason == QuestionRejection.NOT_RECOVERABLE
        assert recording.embedded == 0, "a free rule, ahead of the embedding"
    else:
        assert result.accepted, result.rejected_reason


def test_a_keyword_typed_in_lower_case_is_no_person() -> None:
    """The tagger reads names into a lower-case query; a name has a capital."""
    from question_generation.gates import strangers

    passage = ("Der Strafstoß wird vom Elfmeterpunkt ausgeführt.",)
    assert strangers("strafschuss richterteam standorte", passage, "de") == ()


# ── The kind a question turned out to be ───────────────────────────────────


def test_an_entity_question_asking_who_names_a_party() -> None:
    """The interrogative settles it without reading the answer."""
    assert asks_for_an_agent("Who signs off a change to the shift plan?", "", "en")


def test_an_entity_question_whose_answer_names_an_organisation_passes() -> None:
    """The other way to pass: the party is in the answer, not the question."""
    assert asks_for_an_agent(
        "Which body accredits a training provider?", "the Standards Council", "en"
    )


def test_an_entity_question_asking_after_no_party_is_refused() -> None:
    """An entity question asking after no party is refused."""
    assert not asks_for_an_agent(
        "Womit können Test-Chartas erstellt werden?",
        "mit Flipcharts und Tabellenkalkulationen",
        "de",
    )


def test_an_enumeration_answering_with_one_thing_is_refused() -> None:
    """Its own directive says so, and nothing enforced it."""
    assert not enumerates("a written examination", "en")


def test_an_enumeration_answering_with_a_set_passes() -> None:
    """Counted on noun phrases, so the punctuation does not decide."""
    assert enumerates("by phone, through the web form and by email", "en")


@pytest.mark.parametrize(
    ("answer", "language"),
    [
        ("political, religious and personal", "en"),
        ("domestic and international", "en"),
        ("politische, religiöse und persönliche", "de"),
        ("religiös und persönlich", "de"),
    ],
)
def test_an_enumeration_of_adjectives_is_a_set(answer, language) -> None:
    """Coordinated kinds hold no noun phrase, and are a set all the same."""
    assert enumerates(answer, language)


@pytest.mark.parametrize(
    ("answer", "language"),
    [
        ("complete and signed", "en"),
        ("signed and complete", "en"),
        ("opened and used", "en"),
        ("vollständig und unterschrieben", "de"),
        ("geöffnet oder benutzt", "de"),
        ("gilt weltweit und schützt den Kunden", "de"),
    ],
)
def test_coordinated_predicates_are_not_a_set(answer, language) -> None:
    """`complete and signed` says two things of one document and names none."""
    assert not enumerates(answer, language)


@pytest.mark.parametrize(
    ("answer", "language"),
    [("within one or two days", "en"), ("zwei oder drei Werktage", "de")],
)
def test_coordinated_numbers_are_one_range_not_a_set(answer, language) -> None:
    """`one or two days` is how long something takes, said loosely."""
    assert not enumerates(answer, language)


def test_an_enumeration_key_adding_an_adjective_the_passage_lacks_is_refused() -> None:
    """`kostenlos und schnell` asserts more than the `kostenlos` that came back.

    `de_core_news_md` tags a predicative adjective an adverb, which is no
    content lemma, so the two are compared as strings, and a key holding its
    recovery is not held by it.
    """
    text = "Echtzeitüberweisungen sind kostenlos."
    result = build(Recording(recovers="kostenlos")).check(
        candidate(
            question_text="Was bietet die Echtzeitüberweisung?",
            target_answer="kostenlos und schnell",
            question_type=QuestionType.ENUMERATION,
            facts=group(
                source(
                    statement=text,
                    passage_text=text,
                    language="de",
                    section_path="Zahlungen > Echtzeit",
                )
            ),
        )
    )

    assert result.rejected_reason == QuestionRejection.NOT_RECOVERABLE, result.status


# ── A follow-up, read on its facts rather than its words ───────────────────


def test_a_follow_up_citing_only_its_root_asks_nothing_new() -> None:
    """A follow-up citing only its root asks nothing new."""
    assert not moves_on(cited=(1, 2), root=(1, 2, 3))


def test_a_follow_up_reaching_one_new_fact_moves_on() -> None:
    """One is enough: the thread went somewhere."""
    assert moves_on(cited=(2, 4), root=(1, 2))


#: A fact stating what a whole section covers, several claims in one.
_COVERS = (
    "The guide covers the fees for cards, for transfers abroad and for cash "
    "withdrawals at other banks' machines."
)


@pytest.mark.parametrize(
    ("kind", "key", "refused"),
    [
        (FactKind.SUMMARY, "a flat fee for each transfer abroad", False),
        (FactKind.OUTLINE, "a flat fee for each transfer abroad", False),
        (FactKind.ATOMIC, "a flat fee for each transfer abroad", True),
        (FactKind.SUMMARY, "the card fees", True),
    ],
    ids=["summary, new key", "outline, new key", "atomic", "summary, key said before"],
)
def test_a_follow_up_on_a_summary_moves_on_when_its_key_says_something_new(
    kind: str, key: str, refused: bool
) -> None:
    """A summary holds several claims; asking it again can reach another one."""
    result = build(Recording(recovers=key)).check(
        candidate(
            question_text="And what does a transfer abroad cost?",
            target_answer=key,
            thread=(("Which fees does the guide cover?", "the card fees"),),
            root_facts=(1,),
            facts=group(source(1, statement=_COVERS, kind=kind)),
        )
    )

    assert (result.rejected_reason == QuestionRejection.ASKS_NOTHING_NEW) is refused


def test_a_follow_up_sharing_a_passage_stays_on_thread() -> None:
    """What makes it the next turn rather than another question."""
    assert same_material(cited=(7, 8), parent=(8, 9))


def test_a_follow_up_sharing_no_passage_has_changed_the_subject() -> None:
    """`Warum wurde TTA-2.6.1 entfernt?` after a question about test design."""
    assert not same_material(cited=(7,), parent=(8, 9))


def test_a_turn_resting_on_nothing_is_left_to_the_orphan_trigger() -> None:
    """A measurement with nothing to measure is not evidence."""
    assert same_material(cited=(), parent=(8,))
    assert same_material(cited=(8,), parent=())


# ── The answer that only says the question again ───────────────────────────


def test_an_answer_adding_no_content_word_restates_the_question() -> None:
    """An answer adding no content word restates the question."""
    assert restates(
        "Wofür sind statische Analysen bei statischen Wartbarkeitstests geeignet?",
        "für statische Wartbarkeitstests",
        "de",
    )


def test_an_answer_adding_one_word_in_six_restates_the_question() -> None:
    """`challenging` is the one lemma the question did not carry."""
    assert restates(
        "Why can accurate test metrics be hard to determine for exploratory "
        "testing sessions?",
        "accurate test metrics for exploratory testing sessions can be "
        "challenging to determine",
        "en",
    )


def test_a_comparison_naming_both_sides_again_is_not_a_restatement() -> None:
    """A comparison names both of its subjects by construction."""
    recording = Recording(recovers="higher demands in Agile")

    result = build(recording).check(
        candidate(
            question_text=(
                "How do Agile and sequential development models differ in their "
                "demands on social skills?"
            ),
            target_answer=(
                "higher social-skill demands in Agile and lower demands in "
                "sequential development models"
            ),
            question_type=QuestionType.COMPARISON,
        )
    )

    assert result.rejected_reason != QuestionRejection.RESTATES_QUESTION


def test_an_answer_that_adds_something_does_not_restate() -> None:
    """The gate is full containment, not a share."""
    assert not restates(
        "Why does a request have to be confirmed in writing?",
        "so that the agreed response time can be evidenced later",
        "en",
    )


def test_an_answer_asserting_a_number_is_exempt() -> None:
    """`content` drops numerals, so the answer would score as contained.

    `zwei` IS the answer, and a value carrying a figure is the most
    scoreable kind there is.
    """
    assert not restates(
        "In wie viele Kategorien werden Schlüsselwörter eingeteilt?",
        "zwei Kategorien",
        "de",
    )


def test_an_answer_whose_verb_decides_it_does_not_restate() -> None:
    """`cancelled` is the answer, and it is a verb the question lacks."""
    assert not restates(
        "What does the bank do if a customer refuses to confirm a transfer?",
        "The transfer must be cancelled.",
        "en",
    )


def test_a_predicative_adjective_tagged_as_an_adverb_is_new() -> None:
    """`de_core_news_md` tags a predicative `rechtwinklig` ADV, and it is the answer."""
    assert not restates(
        "Wie verlaufen die beiden Kanten des Gehäuses zur Grundplatte?",
        "rechtwinklig zur Grundplatte",
        "de",
    )


@pytest.mark.parametrize(
    ("question", "answer", "language"),
    [
        ("Is the device waterproof?", "No, the device is not waterproof.", "en"),
        ("Ist das Gerät wasserdicht?", "Ja, das Gerät ist wasserdicht.", "de"),
    ],
)
def test_a_yes_or_no_answer_does_not_restate(
    question: str, answer: str, language: str
) -> None:
    """Its polarity is the answer, and every other word was in the question."""
    assert not restates(question, answer, language)


def test_a_polarity_the_question_already_had_is_still_an_echo() -> None:
    """`not` asked and `not` answered adds nothing."""
    assert restates(
        "Why is the device not waterproof?", "the device is not waterproof", "en"
    )


def test_a_polarity_answering_a_question_word_is_still_an_echo() -> None:
    """Only a question asked yes or no is answered by a `not`."""
    assert restates(
        "Why must a senior officer sign a transfer before it is released?",
        "A transfer is not released until a senior officer signs it.",
        "en",
    )


# ── The key that names less than the passages gave ─────────────────────────


def test_a_key_naming_one_of_many_is_incomplete() -> None:
    """The `mit Entwicklern` case, read off the recovery already paid for."""
    assert incomplete(
        recovered=(
            "developers, architects, operations engineers, product owners, "
            "local support, technical experts and the service desk"
        ),
        target="developers",
        language="en",
        form=AnswerForm.LIST,
    )


def test_a_key_naming_most_of_what_came_back_is_complete() -> None:
    """A verifier is wordier than a key, and that alone is not a fault."""
    assert not incomplete(
        recovered="by phone, through the web form and by email",
        target="by phone, through the web form and by email",
        language="en",
        form=AnswerForm.LIST,
    )


_TERSE = [
    (
        "de",
        "Wann erstattet die Bank die Kontoführungsgebühr für das Girokonto?",
        "bei Kündigung in der Probezeit und bei Umzug ins Ausland",
        "Die Bank erstattet die monatliche Kontoführungsgebühr für das Girokonto, wenn der Kunde das Girokonto in der Probezeit kündigt oder ins Ausland umzieht, und zwar rückwirkend ab dem ersten Monat.",
    ),
    (
        "en",
        "When does the bank refund the monthly account fee on a current account?",
        "on closure during the trial period, and on a move abroad",
        "The bank refunds the monthly account fee on a current account if the customer closes the current account during the trial period or moves abroad, backdated to the first month of the contract.",
    ),
    (
        "de",
        "Wann darf ein Kunde die Ware im Onlineshop zurückgeben?",
        "innerhalb von 30 Tagen und in der Originalverpackung",
        "Ein Kunde darf die Ware im Onlineshop zurückgeben, wenn er sie innerhalb von 30 Tagen nach der Lieferung in der unbeschädigten Originalverpackung an das zentrale Lager des Onlineshops schickt.",
    ),
    (
        "en",
        "When may a customer return goods bought in the online shop?",
        "within 30 days, and in the original packaging",
        "A customer may return goods bought in the online shop if they send them within 30 days of delivery in the undamaged original packaging to the central warehouse of the online shop.",
    ),
]


@pytest.mark.parametrize(("language", "question", "target", "recovered"), _TERSE)
def test_a_terse_key_naming_every_item_is_not_incomplete(
    language, question, target, recovered
) -> None:
    """A full-sentence recovery restates the question, which is not more items.

    The share alone read it as a fraction of the answer: 39 of the 43 usable
    keys the gate refused on a rebuild were complete. It now also needs an
    item the recovery names that neither the key nor the question carries.
    """
    assert not incomplete(
        recovered, target, language, AnswerForm.LIST, question=question
    )


def test_a_terse_complete_key_is_accepted_through_the_checker() -> None:
    """The checker hands the gate the question, which the unit rows above need."""
    _, question, target, recovered = _TERSE[3]
    result = build(Recording(recovers=recovered)).check(
        candidate(
            question_text=question,
            target_answer=target,
            question_type=QuestionType.CONDITION,
        )
    )

    assert result.answer_form == AnswerForm.LIST
    assert result.rejected_reason is None


@pytest.mark.parametrize(
    ("language", "question", "target", "recovered"),
    [
        (
            "de",
            "Mit wem arbeitet die Kundenberaterin der Bank zusammen?",
            "mit der Kreditabteilung",
            "Die Kundenberaterin arbeitet mit der Kreditabteilung, der Rechtsabteilung, dem Wertpapierhandel, der Filialleitung und dem Kundenservice zusammen.",
        ),
        (
            "en",
            "Who does the bank's customer adviser work with?",
            "with the credit department",
            "The customer adviser works with the credit department, the legal department, securities trading, branch management and customer service.",
        ),
        (
            "de",
            "Welche Zahlungsarten akzeptiert der Onlineshop?",
            "Kreditkarte",
            "Der Onlineshop akzeptiert Kreditkarte, Lastschrift, PayPal, Überweisung, Gutscheine und Rechnung.",
        ),
        (
            "en",
            "Which payment methods does the shop accept?",
            "credit card",
            "The shop accepts credit card, debit card, PayPal, bank transfer, gift vouchers and invoice payment.",
        ),
        (
            "de",
            "Welche Karten bietet die Bank an?",
            "die goldene Kreditkarte",
            "Die Bank bietet die goldene Kreditkarte, die silberne Kreditkarte und die schwarze Kreditkarte für Privatkunden und Geschäftskunden an.",
        ),
    ],
)
def test_a_key_naming_one_of_many_is_still_incomplete_with_its_question(
    language, question, target, recovered
) -> None:
    """An item the key and the question lack is what the gate was written to catch."""
    assert incomplete(recovered, target, language, AnswerForm.LIST, question=question)


@pytest.mark.parametrize(
    ("language", "question", "target", "recovered"),
    [
        (
            "en",
            "What are the notice periods?",
            "30 days and 14 days",
            "The notice periods are 30 days, 14 days and 7 days.",
        ),
        (
            "de",
            "Welche Fristen gelten für Rücksendungen im Onlineshop?",
            "30 Tage und 14 Tage",
            "Für Rücksendungen im Onlineshop gelten Fristen von 30 Tagen, 14 Tagen und 7 Tagen.",
        ),
        (
            "en",
            "Which two conditions must a customer meet to return goods?",
            "a receipt",
            "The customer must present a receipt and return the original packaging.",
        ),
        (
            "de",
            "Welche zwei Bedingungen muss ein Kunde erfüllen?",
            "einen Beleg",
            "Der Kunde muss einen Beleg vorlegen und die Originalverpackung zurückgeben.",
        ),
    ],
)
def test_a_figure_or_a_verb_phrase_the_key_lacks_is_still_an_item_it_lacks(
    language, question, target, recovered
) -> None:
    """The extra item is a figure, or a coordinated verb phrase with nouns of its own."""
    assert incomplete(recovered, target, language, AnswerForm.LIST, question=question)


@pytest.mark.parametrize("marker", ["1.", "1)", "a)", "-", "•"])
@pytest.mark.parametrize(
    ("language", "first", "second", "target", "question"),
    [
        (
            "en",
            "card fraud",
            "unpaid fees",
            "card fraud and unpaid fees",
            "When is a card blocked?",
        ),
        (
            "de",
            "Kartenbetrug",
            "offene Gebühren",
            "Kartenbetrug und offene Gebühren",
            "Wann wird eine Karte gesperrt?",
        ),
        (
            "en",
            "a receipt",
            "the original packaging",
            "a receipt and the original packaging",
            "What must a customer return goods with?",
        ),
        (
            "de",
            "ein Beleg",
            "die Originalverpackung",
            "ein Beleg und die Originalverpackung",
            "Was muss ein Kunde bei der Rückgabe vorlegen?",
        ),
    ],
)
def test_a_list_marker_is_not_a_figure_the_key_lacks(
    language, first, second, target, question, marker
) -> None:
    """`1.` and `2)` number the items of a recovery; they are not figures it states."""
    second_marker = {"1.": "2.", "1)": "2)", "a)": "b)"}.get(marker, marker)
    recovered = f"{marker} {first}\n{second_marker} {second}"
    assert unnamed(recovered, target, language, question) == ()


@pytest.mark.parametrize(
    ("language", "recovered", "target", "question"),
    [
        (
            "en",
            "1. Withdrawals\n2. Withdrawals over 500 EUR",
            "Withdrawals",
            "Which payments need approval?",
        ),
        (
            "de",
            "1) Abhebungen\n2) Abhebungen über 500 EUR",
            "Abhebungen",
            "Welche Zahlungen brauchen eine Freigabe?",
        ),
    ],
)
def test_a_figure_inside_a_list_item_still_counts(
    language, recovered, target, question
) -> None:
    """Only the marker is dropped; the 500 inside the item is a figure the key lacks."""
    assert "500.0" in unnamed(recovered, target, language, question)


#: Everything the passage says blocks a card, as a verifier reading it
#: writes it back.
_BLOCKED = (
    "A card is blocked for card fraud, unpaid fees, a court order, a theft "
    "report, a closed account, a fraud alert or a changed address."
)


@pytest.mark.parametrize(
    ("recovered", "rejected"),
    [
        (_BLOCKED, QuestionRejection.ANSWER_INCOMPLETE),
        ("for card fraud or for unpaid fees", None),
    ],
    ids=["two of six", "both of two"],
)
def test_a_two_item_key_to_a_list_first_type_is_checked_for_completeness(
    recovered: str, rejected: str | None
) -> None:
    """Read as the list its type asked for, it reaches `answer_incomplete`."""
    result = build(Recording(recovers=recovered)).check(
        candidate(
            question_text="When is a card blocked?",
            target_answer="for card fraud, and for unpaid fees",
            question_type=QuestionType.CONDITION,
        )
    )

    assert result.rejected_reason == rejected
    assert result.answer_form == AnswerForm.LIST


def test_a_key_the_entailment_pass_rescued_is_still_held_to_completeness() -> None:
    """The rescue says the key is true, not that it is the whole answer."""
    passage = (
        "A card is blocked when the bank detects card fraud, when fees stay "
        "unpaid, under a court order, after a theft report, when the account "
        "closes, on a fraud alert or after an address change."
    )
    result = build(
        Recording(
            recovers=(
                "after a theft report, under a court order, when the account "
                "closes, on a fraud alert or after an address change"
            ),
            backs=True,
        )
    ).check(
        candidate(
            question_text="When is a card blocked?",
            target_answer="for card fraud, and for unpaid fees",
            question_type=QuestionType.CONDITION,
            facts=group(
                source(statement="A card is blocked for fraud.", passage_text=passage)
            ),
        )
    )

    assert result.rejected_reason == QuestionRejection.ANSWER_INCOMPLETE


def test_an_explanation_key_is_read_for_completeness_and_refused_nothing() -> None:
    """Shadow mode: the share is stored, so a bar can be set on rebuilt keys."""
    passage = (
        "A card block stops every payment with the card until the bank lifts "
        "it. The bank blocks a card for fraud, for unpaid fees, under a court "
        "order, after a theft report or on a fraud alert, and it tells the "
        "holder by letter within two days."
    )
    result = build(Recording(recovers=passage)).check(
        candidate(
            question_text="What is a card block?",
            target_answer=(
                "A card block stops every payment with the card until the bank lifts it."
            ),
            question_type=QuestionType.DEFINITION,
            facts=group(
                source(statement="A card block stops payments.", passage_text=passage)
            ),
        )
    )

    shadow = [one for one in result.readings if one.gate == "coverage"]
    assert result.answer_form == AnswerForm.EXPLANATION, result.answer_form
    assert result.rejected_reason != QuestionRejection.ANSWER_INCOMPLETE
    assert len(shadow) == 1 and shadow[0].shadow, result.readings
    assert shadow[0].value < 0.5, shadow[0]


def test_a_recovery_no_longer_than_the_key_is_stored_as_full_coverage() -> None:
    """A key holds all of a recovery that says no more than it does."""
    key = "A card block stops every payment with the card until the bank lifts it."
    result = build(Recording(recovers=key)).check(
        candidate(
            question_text="What is a card block?",
            target_answer=key,
            question_type=QuestionType.DEFINITION,
            facts=group(
                source(statement="A card block stops payments.", passage_text=key)
            ),
        )
    )

    shadow = [one for one in result.readings if one.gate == "coverage"]
    assert result.status == QuestionStatus.ACCEPTED, result.rejected_reason
    assert len(shadow) == 1 and shadow[0].shadow, result.readings
    assert shadow[0].value == 1.0, shadow[0]


def test_the_coverage_reading_moves_no_verdict() -> None:
    """Stored on a key the round trip refuses too, which it still refuses."""
    passage = (
        "A card block stops every payment with the card until the bank lifts "
        "it. The bank tells the holder by letter within two days."
    )
    result = build(
        Recording(recovers="The bank tells the holder by letter within two days.")
    ).check(
        candidate(
            question_text="What is a card block?",
            target_answer=(
                "A card block stops every payment with the card until the bank lifts it."
            ),
            question_type=QuestionType.DEFINITION,
            facts=group(
                source(statement="A card block stops payments.", passage_text=passage)
            ),
        )
    )

    shadow = [one for one in result.readings if one.gate == "coverage"]
    assert result.rejected_reason == QuestionRejection.NOT_RECOVERABLE
    assert len(shadow) == 1 and shadow[0].shadow, result.readings


@pytest.mark.parametrize("form", [AnswerForm.VALUE, AnswerForm.EXPLANATION])
def test_only_a_list_claims_to_name_a_set(form: str) -> None:
    """A value is short because its answer is one thing."""
    assert not incomplete(
        recovered=(
            "developers, architects, operations engineers, product owners, "
            "local support, technical experts and the service desk"
        ),
        target="developers",
        language="en",
        form=form,
    )


_QUESTION_NAMES_THEM = [
    (
        "en",
        "Which of PayPal, debit card and invoice does the online shop accept for orders over 100 euros?",
        "invoice",
        "The online shop accepts PayPal, debit card and invoice for orders over 100 euros.",
    ),
    (
        "de",
        "Welche der Zahlungsarten Lastschrift, PayPal und Rechnung akzeptiert der Onlineshop bei Bestellungen über 100 Euro?",
        "Rechnung",
        "Der Onlineshop akzeptiert bei Bestellungen über 100 Euro Lastschrift, PayPal und Rechnung.",
    ),
    (
        "en",
        "Which accounts does the bank's customer adviser open: current accounts, savings accounts or loan accounts?",
        "savings accounts",
        "The bank's customer adviser opens current accounts, savings accounts and loan accounts.",
    ),
    (
        "de",
        "Welche Konten eröffnet die Kundenberaterin der Bank: Girokonten, Sparkonten oder Kreditkonten?",
        "Sparkonten",
        "Die Kundenberaterin der Bank eröffnet Girokonten, Sparkonten und Kreditkonten.",
    ),
]


@pytest.mark.parametrize(
    ("language", "question", "target", "recovered"), _QUESTION_NAMES_THEM
)
def test_items_the_question_names_are_not_items_the_key_lacks(
    language, question, target, recovered
) -> None:
    """A recovery listing what the question listed adds nothing the key missed."""
    assert unnamed(recovered, target, language, question) == ()
    assert unnamed(recovered, target, language)
    assert not incomplete(
        recovered, target, language, AnswerForm.LIST, question=question
    )
    assert incomplete(recovered, target, language, AnswerForm.LIST)


@pytest.mark.parametrize(
    ("language", "recovered", "target", "coverage", "expected"),
    [
        (
            "en",
            "The bank offers credit cards and gift vouchers.",
            "credit cards",
            0.4,
            False,
        ),
        (
            "en",
            "The bank offers current accounts and savings accounts.",
            "current accounts",
            0.5,
            False,
        ),
        (
            "en",
            "The bank offers current accounts and savings accounts.",
            "current accounts",
            0.6,
            True,
        ),
        ("de", "Girokonten, Sparkonten", "Girokonten", 0.5, False),
        ("de", "Girokonten, Sparkonten", "Girokonten", 0.6, True),
    ],
)
def test_a_key_holding_exactly_the_share_asked_is_not_incomplete(
    language, recovered, target, coverage, expected
) -> None:
    """The share is a floor: a key at it passes, one below it with a missing item fails."""
    assert (
        incomplete(recovered, target, language, AnswerForm.LIST, coverage=coverage)
        is expected
    )


@pytest.mark.parametrize(
    ("language", "recovered", "target", "question", "expected"),
    [
        (
            "en",
            "- card fraud\n- unpaid fees\n- a court order",
            "card fraud",
            "When is a card blocked?",
            ("unpaid fees", "a court order"),
        ),
        (
            "en",
            "card fraud; unpaid fees",
            "card fraud",
            "When is a card blocked?",
            ("unpaid fees",),
        ),
        (
            "de",
            "- Kartenbetrug\n- offene Gebühren\n- ein Gerichtsbeschluss",
            "Kartenbetrug",
            "Wann wird eine Karte gesperrt?",
            ("offene Gebühren", "ein Gerichtsbeschluss"),
        ),
        (
            "de",
            "Kartenbetrug; offene Gebühren",
            "Kartenbetrug",
            "Wann wird eine Karte gesperrt?",
            ("offene Gebühren",),
        ),
        (
            "en",
            "a) card fraud\nb) unpaid fees",
            "card fraud",
            "When is a card blocked?",
            ("unpaid fees",),
        ),
        ("en", "card fraud; ", "card fraud", "When is a card blocked?", ()),
        ("en", "- unpaid fees", "card fraud", "When is a card blocked?", ()),
        (
            "de",
            "- offene Gebühren",
            "Kartenbetrug",
            "Wann wird eine Karte gesperrt?",
            (),
        ),
    ],
)
def test_the_items_a_layout_sets_apart_are_each_read_against_the_key(
    language, recovered, target, question, expected
) -> None:
    """Marked lines, else `;` parts; two make a list, and one thing is not one."""
    assert unnamed(recovered, target, language, question) == expected


@pytest.mark.parametrize(
    ("language", "recovered", "target", "question", "expected"),
    [
        (
            "de",
            "Der Shop verkauft Kaffee und Tee.",
            "Kaffee",
            "Was verkauft der Shop?",
            ("Tee",),
        ),
        (
            "de",
            "Der Shop akzeptiert Kreditkarte und Gutschein.",
            "Kreditkarte",
            "Welche Zahlung akzeptiert der Shop?",
            ("Gutschein",),
        ),
        (
            "en",
            "The shop sells coffee and tea.",
            "coffee",
            "What is on offer at the shop?",
            ("tea",),
        ),
        (
            "en",
            "The shop sells the coffee and the tea.",
            "coffee",
            "What can customers buy?",
            ("tea",),
        ),
        (
            "de",
            "Der Shop verkauft den Kaffee und den Tee.",
            "Kaffee",
            "Was kann man kaufen?",
            ("Tee",),
        ),
        (
            "en",
            "The shop delivers quickly and reliably.",
            "quickly",
            "How does the shop deliver?",
            ("reliably",),
        ),
        (
            "de",
            "Der Shop liefert schnell und zuverlässig.",
            "schnell",
            "Wie liefert der Shop?",
            ("zuverlässig",),
        ),
    ],
)
def test_a_known_item_is_not_named_again_for_the_item_joined_to_it(
    language, recovered, target, question, expected
) -> None:
    """Only the conjunct the key lacks is named, not the one it already holds."""
    assert unnamed(recovered, target, language, question) == expected


@pytest.mark.parametrize(
    ("language", "recovered", "target", "question"),
    [
        (
            "en",
            "The customer must present a receipt and return the goods promptly to the online shop.",
            "present a receipt",
            "What must a customer do to return goods to the online shop?",
        ),
        (
            "de",
            "Der Kunde muss einen Beleg vorlegen und die Ware umgehend an den Onlineshop zurückschicken.",
            "einen Beleg vorlegen",
            "Was muss ein Kunde tun, um Ware an den Onlineshop zurückzusenden?",
        ),
    ],
)
def test_a_joined_verb_phrase_is_judged_by_its_object_not_by_its_modifiers(
    language, recovered, target, question
) -> None:
    """The goods are the question's; `promptly` is a modifier of the sentence."""
    assert unnamed(recovered, target, language, question) == ()


@pytest.mark.parametrize(
    ("language", "recovered", "target", "question", "expected"),
    [
        (
            "de",
            "Die Bank bietet Karte und Konto an.",
            "Karten und Konten",
            "Welche Produkte bietet die Bank an?",
            (),
        ),
        (
            "de",
            "Die Bank bietet Karte und Konto an.",
            "Karten",
            "Welche Karten und Konten bietet die Bank an?",
            (),
        ),
        (
            "de",
            "- Karten\n- Konten",
            "Karte und Konto",
            "Welche Produkte bietet die Bank an?",
            (),
        ),
    ],
)
def test_an_item_is_known_by_its_lemma_in_the_language_of_the_text(
    language, recovered, target, question, expected
) -> None:
    """`Karte` is `Karten`: the German lemma, which an English reading would not give."""
    assert unnamed(recovered, target, language, question) == expected


@pytest.mark.parametrize(
    ("language", "recovered", "target", "question", "expected"),
    [
        (
            "de",
            "innerhalb von 7 Tagen und von 14 Tagen",
            "innerhalb von sieben Tagen und von 14 Tagen",
            "Welche Fristen gelten?",
            (),
        ),
        (
            "en",
            "within 7 days and within 14 days",
            "within seven days and within 14 days",
            "Which periods apply?",
            (),
        ),
        (
            "de",
            "30 Tage, 14 Tage und sieben Tage",
            "30 Tage und 14 Tage",
            "Welche Fristen gelten?",
            ("7.0",),
        ),
        (
            "en",
            "30 days, 14 days and seven days",
            "30 days and 14 days",
            "Which periods apply?",
            ("7.0",),
        ),
    ],
)
def test_a_count_written_out_is_the_figure_it_is_on_either_side(
    language, recovered, target, question, expected
) -> None:
    """`sieben` in the key is the 7 the recovery writes, and in the recovery is a 7 the key lacks."""
    assert unnamed(recovered, target, language, question) == expected


@pytest.mark.parametrize(
    ("language", "question", "target", "recovered"),
    [
        (
            "de",
            "Wie lange dauert die Bearbeitung eines Kreditantrags?",
            "8–10 Werktage",
            "Die Bearbeitung eines Kreditantrags dauert 8–10 Werktage.",
        ),
        (
            "en",
            "How long does the bank take to process a loan application?",
            "8–10 business days",
            "Processing a loan application takes 8–10 business days.",
        ),
        (
            "de",
            "Wie lange dauert die Bearbeitung eines Kreditantrags?",
            "8–10 Werktage",
            "Die Bearbeitung eines Kreditantrags dauert mindestens 8 und höchstens 10 Werktagen.",
        ),
        (
            "de",
            "Wie lange dauert die Bearbeitung eines Kreditantrags?",
            "8–10 Werktage, je nach Konto",
            "Je nach Konto dauert die Bearbeitung eines Kreditantrags zwischen 8 und 10 Werktage.",
        ),
        (
            "de",
            "Wie hoch ist der Zinssatz des Girokontos?",
            "2,5–3,5 %",
            "Der Zinssatz des Girokontos liegt zwischen 2,5 und 3,5 Prozent.",
        ),
        (
            "en",
            "How high is the discount in the online shop?",
            "8–10 %",
            "The discount in the online shop is between 8 and 10 percent.",
        ),
        (
            "en",
            "How long does the bank take to process a loan application?",
            "8–10 business days, depending on the account",
            "Depending on the account, processing a loan application takes between 8 and 10 business days.",
        ),
    ],
)
def test_a_range_comes_back_as_the_same_range_or_in_another_form_of_its_words(
    language, question, target, recovered
) -> None:
    """A range for a range, its unit in any inflection, and its punctuation not asked back."""
    assert agrees(
        recovered,
        target,
        language,
        AnswerForm.VALUE,
        question=question,
        passages=(recovered,),
    )


@pytest.mark.parametrize(
    ("language", "question", "target", "recovered"),
    [
        (
            "de",
            "Wie lange dauert die Bearbeitung eines Kreditantrags?",
            "8–10 Werktage",
            "Die Bearbeitung eines Kreditantrags dauert 8–12 Werktage.",
        ),
        (
            "en",
            "How long does the bank take to process a loan application?",
            "8–10 business days",
            "Processing a loan application takes 8–12 business days.",
        ),
    ],
)
def test_a_range_the_recovery_writes_is_held_to_both_of_the_keys_ends(
    language, question, target, recovered
) -> None:
    """The ends of the recovery's own range count, so `8–12` is not `8–10`."""
    assert not agrees(
        recovered,
        target,
        language,
        AnswerForm.VALUE,
        question=question,
        passages=(recovered,),
    )


# ── Two more types a rule can settle ───────────────────────────────────────


def test_a_comparison_naming_one_thing_is_refused() -> None:
    """`Wie unterscheiden sich die beschriebenen Umgebungen?` compares nothing."""
    assert not compares(
        "Wie unterscheiden sich die beschriebenen Umgebungen?",
        "eine Zielumgebung",
        "de",
    )


def test_a_comparison_naming_both_sides_passes() -> None:
    """Both in the question, both in the answer."""
    assert compares(
        "How do the reply times for standard and urgent requests differ?",
        "48 hours for a standard request and 4 hours for an urgent one",
        "en",
    )


def test_a_comparison_answering_with_two_definitions_is_refused() -> None:
    """The weld: one fragment per side, and no difference between them."""
    assert not compares(
        "How does algorithmic bias differ from area under curve (AUC)?",
        "a type of bias caused by the ML algorithm, a measure of how well a "
        "classifier can distinguish between two classes",
        "en",
    )


def test_a_comparison_saying_which_side_is_more_passes() -> None:
    """A comparative is a difference stated outright."""
    assert compares(
        "How do internal reports and external reports differ in formality?",
        "internal reports may be less formal, external reports are more formal",
        "en",
    )


def test_a_comparison_answered_in_one_piece_is_refused() -> None:
    """No seam is no two sides: this says what one thing does."""
    assert not compares(
        "What can the status light show when the update has finished on the device?",
        "that the update has been installed on the device",
        "en",
    )


def test_a_comparison_naming_one_side_is_refused_whatever_the_sides_share() -> None:
    """A definition welded to another names one subject; `device` is incidental."""
    assert not compares(
        "How do the charging area and a sleeve differ?",
        "a marked area on desks for staff devices, part of a device's kit worn "
        "over its back cover",
        "en",
    )


def test_a_comparison_is_split_between_its_subjects_not_at_a_subordinate_comma() -> (
    None
):
    """The `und` divides the two payments; the comma opens the `wenn` clause."""
    assert compares(
        "Wodurch unterscheiden sich Überweisung und Lastschrift, wenn das Konto "
        "gesperrt wird?",
        "Rückbuchung der Zahlung bei der Überweisung und Rückbuchung der "
        "Lastschrift, wenn das Konto gedeckt ist",
        "de",
    )


@pytest.mark.parametrize(
    "answer",
    [
        "Card payments take one day while bank transfers take three days",
        "Card payments take one day, while bank transfers take three days",
        "Card payments take one day whereas bank transfers take three days",
    ],
    ids=["while", "comma while", "whereas"],
)
def test_a_comparison_joined_by_a_subordinator_is_split_there(answer: str) -> None:
    """`while` opens the second side with or without a comma before it."""
    assert compares(
        "How do card payments and bank transfers differ in speed?", answer, "en"
    )


def test_a_comparison_is_split_at_its_and_not_at_a_relative_which() -> None:
    """`en_core_web_md` marks `which` WDT and gives it no `PronType=Rel`."""
    assert compares(
        "How do card payments and bank transfers differ?",
        "a refund within a day for card payments and a refund within a week, "
        "which bank transfers allow",
        "en",
    )


@pytest.mark.parametrize(
    "answer",
    [
        (
            "a savings plan sets aside a fixed sum every month, an overdraft is "
            "borrowing more than the account holds"
        ),
        (
            "an overdraft is borrowing more than the account holds, a savings "
            "plan sets aside a fixed sum every month"
        ),
    ],
    ids=["comparative second", "comparative first"],
)
def test_a_comparative_inside_one_side_is_not_a_difference(answer: str) -> None:
    """`more than the account holds` defines an overdraft and compares nothing.

    In either order: with the definition carrying it first, the second
    subject lies past the comma, outside the comparative's own stretch.
    """
    assert not compares("How do a savings plan and an overdraft differ?", answer, "en")


@pytest.mark.parametrize(
    ("question", "answer", "language"),
    [
        (
            "How do card payments and bank transfers differ in speed?",
            "Card payments settle faster than bank transfers",
            "en",
        ),
        (
            "Wie unterscheiden sich Überweisung und Lastschrift in der Dauer?",
            "Eine Überweisung dauert länger als eine Lastschrift.",
            "de",
        ),
        (
            "How do card payments and bank transfers differ in speed?",
            "Card payments are faster, while bank transfers take a day",
            "en",
        ),
        (
            "Wie unterscheiden sich Kartenzahlungen und Überweisungen in der Dauer?",
            "Kartenzahlungen sind schneller, während Überweisungen einen Tag dauern",
            "de",
        ),
        (
            "How do card payments and bank transfers differ in speed?",
            "Card payments settle faster than bank transfers, which take a day",
            "en",
        ),
        (
            "How do card payments and bank transfers differ in speed?",
            "Card payments settle faster than bank transfers and cost less",
            "en",
        ),
        (
            "How do card payments and bank transfers differ in speed?",
            "Card payments settle faster than bank transfers, usually within seconds",
            "en",
        ),
        (
            "Wie unterscheiden sich Überweisung und Lastschrift in der Dauer?",
            "Eine Überweisung dauert länger als eine Lastschrift, die einen Tag braucht.",
            "de",
        ),
    ],
)
def test_a_comparative_standing_between_the_two_subjects_passes(
    question: str, answer: str, language: str
) -> None:
    """One subject before the comparative and the other after it.

    `than` and `als` are prepositions to the tagger, so the first two have
    no seam at all; the next two name the second subject in a `while` clause
    that carries no comparative of its own; and the last four go on past a
    seam once both subjects are said. The German sentences keep their full
    stop: without one `de_core_news_md` chunks `eine Lastschrift` into no
    noun phrase, and `compares` counts phrases before it reads anything.
    """
    assert compares(question, answer, language)


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="Each side gives its own subject's value on the axis the question "
    "names, so the sides share no lemma the question lacks. That is the "
    "question-subtraction rule in gates._contrasts, deferred until it is "
    "measured on the split this test now gets; remove this marker then.",
)
@pytest.mark.parametrize(
    ("question", "answer", "language"),
    [
        (
            (
                "Worin unterscheidet sich die Rolle des Anlageberaters von der "
                "des Kunden bei Anlageentscheidungen?"
            ),
            "beratende Rolle des Anlageberaters und endgültige Entscheidung des Kunden",
            "de",
        ),
        (
            "How do card payments and bank transfers differ in settlement time?",
            "within seconds, on the next working day",
            "en",
        ),
    ],
)
def test_a_comparison_whose_axis_is_in_the_question_passes(
    question: str, answer: str, language: str
) -> None:
    """A sound A-against-B answer names its axis in the question, not twice."""
    assert compares(question, answer, language)


def test_a_why_question_written_for_a_procedure_is_typed_as_a_reason() -> None:
    """The type is read off the question word, not refused for the slot's."""
    recording = Recording(recovers="4 kg")

    result = build(recording).check(
        candidate(
            question_text="Why is the device built at the Hamburg plant?",
            target_answer="because the plant holds the press line",
            question_type=QuestionType.PROCEDURE,
        )
    )

    assert result.question_type == QuestionType.REASON, result.question_type
    assert result.rejected_reason != QuestionRejection.WRONG_TYPE


def test_a_why_question_typed_as_a_reason_is_asked_as_it_was_planned() -> None:
    """The family a question word names holds the type that answers it."""
    assert asked_as("Why is the device built at the Hamburg plant?", "reason", "en")
    assert not asked_as("Wie viele Werke bauen das Gerät?", "definition", "de")


def test_a_question_word_naming_no_family_leaves_the_type_alone() -> None:
    """`Which` asks for any kind of thing."""
    assert asked_as("Which plant builds the device?", "enumeration", "en")


def test_a_total_is_found_past_a_sum_of_two_years() -> None:
    """2010 + 2015 also make 4025; the desks and rooms are the total."""
    assert adds_up(
        "4025",
        ["Founded in 2010, revised in 2015.", "The site has 4000 desks and 25 rooms."],
    )


_TWO_FACTS = (
    "ATDD is a test-first approach.",
    "In BDD, the When part of a scenario triggers the behaviour.",
)


def test_a_count_equal_to_the_facts_cited_is_malformed() -> None:
    """The question counts the offer, not anything in the corpus."""
    assert (
        code(
            checked(
                question_text=(
                    "How many sections are identified across ATDD's approach type "
                    "and the BDD scenario part that triggers behavior?"
                ),
                target_answer="2 sections",
                statements=_TWO_FACTS,
            )
        )
        == QuestionRejection.MALFORMED
    )


@pytest.mark.parametrize(
    ("question", "answer", "language"),
    [
        (
            (
                "How many sections are identified across ATDD's approach type "
                "and the BDD scenario part that triggers behavior?"
            ),
            "two sections",
            "en",
        ),
        (
            "Wie viele Abschnitte nennen die Angaben zu ATDD und BDD zusammen?",
            "Zwei Abschnitte",
            "de",
        ),
    ],
)
def test_a_count_written_out_equal_to_the_facts_cited_is_malformed(
    question: str, answer: str, language: str
) -> None:
    """`two` and `zwei` count the offer as surely as `2` does."""
    assert (
        code(
            checked(
                question_text=question,
                target_answer=answer,
                language=language,
                statements=_TWO_FACTS,
            )
        )
        == QuestionRejection.MALFORMED
    )


def test_a_count_the_facts_cited_do_not_equal_is_left_alone() -> None:
    """Three steps out of two facts is a count of something else."""
    assert (
        checked(
            question_text="How many steps does the review process take?",
            target_answer="3 steps",
            statements=_TWO_FACTS,
        )
        is None
    )


@pytest.mark.parametrize(
    ("question", "answer", "statements", "language"),
    [
        (
            "How many copies of each backup does the device keep?",
            "two copies",
            (
                "The device keeps two copies of each backup.",
                "A backup is written every night.",
            ),
            "en",
        ),
        (
            "Wie viele Kopien jeder Sicherung behält das Gerät?",
            "zwei Kopien",
            (
                "Das Gerät behält zwei Kopien jeder Sicherung.",
                "Eine Sicherung wird jede Nacht geschrieben.",
            ),
            "de",
        ),
    ],
)
def test_a_count_a_cited_fact_states_is_not_the_prompt_counted(
    question: str, answer: str, statements: tuple[str, ...], language: str
) -> None:
    """The fact says two, so two is what the material holds.

    German `zwei` is not `like_num` to `de_core_news_md`, so the statement is
    read for the count in words as well as in digits.
    """
    assert (
        checked(
            question_text=question,
            target_answer=answer,
            language=language,
            statements=statements,
        )
        is None
    )


#: Seven facts about a device that say how many of nothing.
_SEVEN_SETTINGS = tuple(
    f"Das Gerät sperrt die Einstellung {name} nach einem Update."
    for name in ("Netz", "Anzeige", "Ton", "Sprache", "Zeit", "Ort", "Konto")
)


@pytest.mark.parametrize(
    ("eighth", "expected"),
    [
        (
            "Die Einstellung Akku lässt das Gerät außer Acht.",
            QuestionRejection.MALFORMED,
        ),
        ("Das Gerät sperrt nach einem Update acht Einstellungen.", None),
    ],
    ids=["außer Acht", "acht Einstellungen"],
)
def test_a_word_spelled_like_a_count_states_no_count(
    eighth: str, expected: str | None
) -> None:
    """`außer Acht` is a phrase, so it does not state the eight this counts."""
    assert (
        code(
            checked(
                question_text="Wie viele Einstellungen sperrt das Gerät?",
                target_answer="acht Einstellungen",
                language="de",
                statements=(*_SEVEN_SETTINGS, eighth),
            )
        )
        == expected
    )


#: Two facts about a device, neither of which says how many of anything.
_DEVICE_FACTS = (
    "The device locks its network settings after a failed update.",
    "The device locks its display settings after a failed update.",
)


@pytest.mark.parametrize(
    ("question", "answer", "language"),
    [
        ("Which two settings does the device lock after a failed update?", "two", "en"),
        (
            "Welche Folgen hat ein fehlgeschlagenes Update für das Gerät?",
            "zwei Fälle",
            "de",
        ),
    ],
)
def test_a_bare_count_of_the_facts_cited_is_malformed_whatever_it_asks(
    question: str, answer: str, language: str
) -> None:
    """A key that is the count and nothing else counts the offer, however asked."""
    assert (
        code(
            checked(
                question_text=question,
                target_answer=answer,
                language=language,
                statements=_DEVICE_FACTS,
            )
        )
        == QuestionRejection.MALFORMED
    )


def test_a_count_asked_in_the_dative_is_malformed() -> None:
    """`In wie vielen Fällen` asks how many as surely as `Wie viele` does."""
    assert (
        code(
            checked(
                question_text="In wie vielen Fällen sperrt die Bank ein Konto?",
                target_answer="zwei verschiedene Fälle",
                language="de",
                statements=(
                    "Die Bank sperrt ein Konto bei einem Betrugsverdacht.",
                    "Die Bank sperrt ein Konto bei einer Pfändung.",
                ),
            )
        )
        == QuestionRejection.MALFORMED
    )


def test_a_language_with_no_count_words_keeps_the_opening_rule() -> None:
    """A bare count is read for German and English only; elsewhere as before.

    Short enough that the detector, which knows only the configured
    languages, abstains rather than calling it English.
    """
    assert (
        checked(
            question_text="Quels deux réglages ?",
            target_answer="2 réglages",
            language="fr",
            statements=_DEVICE_FACTS,
        )
        is None
    )


def test_a_temporal_answer_needs_two_periods() -> None:
    """`How did it change from 2024 to 2025?` is answered with both years."""
    assert periods("from 72 hours in 2024 to 48 hours in 2025", "en")
    assert not periods("72 hours", "en")


def test_a_count_is_not_a_period() -> None:
    """Two units are not two periods; a quantity is a unit too."""
    assert not periods("40 people and 25 people", "en")


# ── The corpus's other furniture ───────────────────────────────────────────


def test_a_page_of_names_is_read_as_a_credits_page() -> None:
    """Acknowledgements are a page of names."""
    assert names_parties(
        "Graham Bath, Judy McKay, Tauhida Parveen, Mike Smith, Erik van "
        "Veenendaal, Rex Black, Kari Kakkonen, Leo van der Aalst",
        "en",
    )


def test_subject_matter_is_not_a_credits_page() -> None:
    """Subject matter names no people."""
    assert not names_parties(
        "A standard support request is answered within 48 hours on working "
        "days, and an urgent request within four hours of being raised.",
        "en",
    )


def test_a_density_of_zero_turns_the_reading_off() -> None:
    """Zero excludes nothing; the default and QUESTIONS_PARTY_DENSITY are 0.25."""
    assert not names_parties("Graham Bath, Judy McKay, Rex Black", "en", 0.0)


# ── What a question got past ───────────────────────────────────────────────


def test_an_accepted_question_records_every_gate_that_read_it() -> None:
    """`rejected_reason` can only ever say what STOPPED one.

    The checker returns on the first failure, so a question refused at
    the round trip and one refused at the first rule were the same shape
    of record: a code and nothing about how far it got.
    """
    result = build(Recording(recovers="4 kg")).check(candidate())

    assert result.accepted
    assert result.gates_ran == (
        "structural",
        "kind_and_thread",
        "near_duplicate",
        "phrasing",
        "round_trip",
    )


def test_a_question_stopped_early_names_only_what_ran() -> None:
    """The expensive gates are not in the list because they never ran."""
    result = build(Recording()).check(candidate(question_text="   "))

    assert result.rejected_reason == QuestionRejection.MALFORMED
    assert result.gates_ran == ("structural",)


def test_the_gate_only_an_unanswerable_question_faces_is_not_claimed() -> None:
    """Why this is recorded rather than derived from a fixed order.

    `off_topic` runs for an unanswerable question and for no other, so
    the sequence cannot be read off the verdict and a list of gate names.
    """
    answerable = build(Recording(recovers="4 kg")).check(candidate())
    unanswerable = build(Recording(recovers="4 kg")).check(
        candidate(answerable=False, target_answer=None)
    )

    assert "off_topic" not in answerable.gates_ran
    assert "off_topic" in unanswerable.gates_ran


# ── What Phoenix is told about each gate ───────────────────────────────────


def _verdicts(checked):
    """The annotations one judged question produces, by name."""
    from question_generation.service import QuestionGenerationService

    built = QuestionGenerationService.__new__(QuestionGenerationService)
    return {one.name: one for one in built._verdicts("0123456789abcdef", checked)}


def test_each_gate_that_ran_is_its_own_annotation() -> None:
    """One column per gate, so its mean over a project IS its pass rate."""
    accepted = build(Recording(recovers="4 kg")).check(candidate())

    named = _verdicts(accepted)

    assert named["gate"].label == "accepted"
    assert named["gate 1: structural"].label == "passed"
    assert named["gate 6: round_trip"].label == "passed"
    assert all(one.score == 1.0 for one in named.values())


def test_the_gate_that_stopped_it_is_the_one_scored_zero() -> None:
    """The last that ran is the one that refused, which is what `check` gives."""
    refused = build(Recording()).check(candidate(question_text="   "))

    named = _verdicts(refused)

    assert named["gate 1: structural"].label == "refused"
    assert named["gate 1: structural"].score == 0.0
    assert named["gate 1: structural"].explanation
    assert named["gate"].label == QuestionRejection.MALFORMED


def test_a_gate_that_never_ran_is_absent_rather_than_scored() -> None:
    """Its mean is over the questions that REACHED it.

    Scoring an unreached gate either way would be untrue, and would move
    a rate nobody changed: a run refusing everything at the first rule
    would read as a round trip that passed everything.
    """
    named = _verdicts(build(Recording()).check(candidate(question_text="   ")))

    assert "gate 6: round_trip" not in named
    assert "gate 5: phrasing" not in named


def test_the_position_orders_them_as_the_pipeline_runs_them() -> None:
    """Phoenix sorts its columns by name, and the gates are not alphabetical.

    The numbered ones only. `gate` and `confidence` are summaries of the
    whole check rather than one gate's verdict, and neither has a position.
    """
    named = _verdicts(build(Recording(recovers="4 kg")).check(candidate()))
    gates = sorted(name for name in named if name.startswith("gate "))

    assert gates == [
        "gate 1: structural",
        "gate 3: kind_and_thread",
        "gate 4: near_duplicate",
        "gate 5: phrasing",
        "gate 6: round_trip",
    ]


def test_every_verdict_carries_what_a_run_is_compared_on() -> None:
    """A gate's rate is only comparable within a run and a prompt."""
    named = _verdicts(build(Recording(recovers="4 kg")).check(candidate()))

    for one in named.values():
        assert one.metadata["run_id"]
        assert one.metadata["prompt_version"]


def test_the_values_a_text_asserts_are_one_reading_each() -> None:
    """Read by the language's mark, as the review's replays read them.

    Both readings of an ambiguous figure belong to the comparison alone.
    """
    from question_generation.gates import _numbers

    assert _numbers("Das Limit beträgt 1.000 EUR.", "de") == frozenset({"1000.0"})
    assert _numbers("The limit is 1,000 EUR.", "en") == frozenset({"1000.0"})


# ── The checks a kind gets ─────────────────────────────────────────────────


def _pair():
    return group(
        source(1, document="a", passage_id=1, statement="The device weighs 4 kg."),
        source(2, document="b", passage_id=2, statement="The device ships in March."),
    )


def test_a_question_citing_two_passages_is_stored_with_the_kind_it_was_dealt() -> None:
    """And one narrowed to a single passage is stored single."""
    both = build(Recording()).check(candidate(facts=_pair(), kind="needs_both"))
    alone = build(Recording()).check(
        candidate(facts=group(source(1, passage_id=1)), kind="needs_both")
    )

    assert (both.kind, alone.kind) == ("needs_both", "single")


class _Kinded(QuestionChecker):
    """A checker with the two named checks a kind may run, recording each."""

    def __init__(self, *args, refuse=None, **kwargs):
        """Initialises with which check, if any, refuses."""
        super().__init__(*args, **kwargs)
        self.refuse = refuse
        self.ran: list[str] = []

    def _first(self, candidate, readings):
        self.ran.append("first")
        if self.refuse == "first":
            return ("first_code", "refused before")
        return replace(candidate, target_answer="4 kg")

    def _second(self, candidate, form, readings):
        self.ran.append("second")
        if self.refuse == "second":
            return ("second_code", "refused after")
        return candidate


def _kind_checker(monkeypatch, recording, **spec):
    from question_generation import kinds

    monkeypatch.setitem(
        kinds.KINDS,
        "compound",
        kinds.KindSpec("compound", 2, "", kinds._Answered, **spec),
    )
    return _Kinded(
        embedder=recording,
        verifier=recording,
        nearest=lambda embedding, **_: None,
        threshold=0.93,
        phrasing=recording,
    )


def test_a_kind_check_before_the_gates_can_refuse_the_draft(monkeypatch) -> None:
    """The refusal is the verdict and nothing after it is paid for."""
    recording = Recording()
    checker = _kind_checker(monkeypatch, recording, before="_first", after="_second")
    checker.refuse = "first"

    result = checker.check(candidate(facts=_pair(), kind="compound"))

    assert result.rejected_reason == "first_code"
    assert checker.ran == ["first"]
    assert recording.embedded == 0


def test_a_kind_check_after_the_round_trip_can_refuse_it(monkeypatch) -> None:
    """Run once everything else passed."""
    recording = Recording()
    checker = _kind_checker(monkeypatch, recording, before="_first", after="_second")
    checker.refuse = "second"

    result = checker.check(candidate(facts=_pair(), kind="compound"))

    assert result.rejected_reason == "second_code"
    assert checker.ran == ["first", "second"]
    assert recording.verified == 1


def test_a_kind_that_recovers_for_itself_skips_the_round_trip(monkeypatch) -> None:
    """Its own check reads the passages, so the shared one does not."""
    recording = Recording()
    checker = _kind_checker(monkeypatch, recording, after="_second", round_trip=False)

    result = checker.check(candidate(facts=_pair(), kind="compound"))

    assert result.rejected_reason is None
    assert recording.verified == 0
    assert "round_trip" not in result.gates_ran
    assert result.kind == "compound"


def test_a_kind_check_that_returns_a_candidate_replaces_the_draft(monkeypatch) -> None:
    """What follows reads the replacement."""
    recording = Recording(recovers="4 kg")
    checker = _kind_checker(monkeypatch, recording, before="_first")

    result = checker.check(
        candidate(facts=_pair(), kind="compound", target_answer="4 kilograms")
    )

    assert result.target_answer == "4 kg"


def test_the_verdict_bands_a_question_by_the_kind_it_is_stored_as(monkeypatch) -> None:
    """The kind reaches `criteria_of`: a kind fixing a band decides the question's."""
    from database.qa_generator import Difficulty
    from question_generation import kinds

    monkeypatch.setitem(
        kinds.KINDS,
        "needs_both",
        replace(kinds.KINDS["needs_both"], band=Difficulty.HARD),
    )
    pair = group(source(1, passage_id=1), source(2, passage_id=2))

    checked = QuestionChecker._verdict(
        candidate(facts=pair, kind="needs_both"), None, None
    )

    assert checked.kind == "needs_both"
    assert checked.criteria.difficulty == Difficulty.HARD


# ── A needs_both question one passage states whole is cited from it ───────


class ByParts(Recording):
    """A verifier that lists the parts of a key as scripted, and what it was shown."""

    def __init__(self, parts: tuple[Part, ...], **kwargs) -> None:
        """Initialises with the parts it lists."""
        super().__init__(**kwargs)
        self.parts = parts
        self.shown: list[str] = []

    def stated(self, question: str, key: str, passages, thread=()) -> tuple[Part, ...]:
        """Lists the scripted parts, and records the passages it was shown."""
        self.stated_asked += 1
        self.shown = list(passages)
        return self.parts


def _two(first: str, second: str, language: str = "en"):
    """Two facts on two passages of two topics, as a question cites them."""
    return group(
        source(1, statement=first, passage_id=1, topic_id=1, language=language),
        source(2, statement=second, passage_id=2, topic_id=2, language=language),
    )


def _needs_both(result) -> list[tuple[float, bool]]:
    return [
        (one.value, one.opinion) for one in result.readings if one.gate == "needs_both"
    ]


def _ask(parts, first, second, question, key, language="en", **kwargs):
    """Checks a needs_both question over two passages, the verifier listing `parts`."""
    recording = ByParts(parts, recovers=key)
    result = build(recording).check(
        candidate(
            question_text=question,
            target_answer=key,
            facts=_two(first, second, language),
            kind="needs_both",
            **kwargs,
        )
    )
    return recording, result


#: (first passage, second passage, question, key, the second's wording of the part)
_STATED_ONE = {
    "en": (
        "Returns are accepted within 30 days of delivery.",
        "A return is accepted within 30 days of delivery and refunded to the card used.",
        "Within how many days can a purchase be returned?",
        "within 30 days of delivery",
        "A return is accepted within 30 days of delivery",
    ),
    "de": (
        "Rücksendungen werden innerhalb von 30 Tagen nach Lieferung angenommen.",
        "Eine Rücksendung wird innerhalb von 30 Tagen nach Lieferung angenommen und auf die verwendete Karte erstattet.",
        "Innerhalb wie vieler Tage kann ein Kauf zurückgegeben werden?",
        "innerhalb von 30 Tagen nach Lieferung",
        "Eine Rücksendung wird innerhalb von 30 Tagen nach Lieferung angenommen",
    ),
}


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_needs_both_question_one_passage_states_whole_is_cited_from_it(
    language: str,
) -> None:
    """Both passages state the one part asked: the first is the only citation."""
    first, second, question, key, again = _STATED_ONE[language]
    parts = (Part("the return period", (first, again)),)

    recording, result = _ask(parts, first, second, question, key, language)

    assert result.accepted
    assert result.fact_ids == (1,)
    assert result.passage_ids == (1,)
    assert result.criteria.passage_scope == "single_passage"
    assert result.kind == "single"
    assert _needs_both(result) == [(0.0, True)]
    assert [one.version for one in result.readings if one.gate == "needs_both"] == [
        STATED_VERSION
    ]
    assert recording.stated_asked == 1


_SHIPPING = {
    "en": (
        "Orders over 50 EUR are shipped free of charge.",
        "Gift cards cannot be exchanged for cash.",
        "From what order value is shipping free?",
        "over 50 EUR",
        0,
    ),
    "de": (
        "Geschenkkarten können nicht in Bargeld umgetauscht werden.",
        "Bestellungen über 50 EUR werden versandkostenfrei geliefert.",
        "Ab welchem Bestellwert ist der Versand kostenlos?",
        "über 50 EUR",
        1,
    ),
}


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_second_passage_holding_no_part_is_dropped(language: str) -> None:
    """The passage that holds the part is the citation, whichever is first."""
    first, second, question, key, at = _SHIPPING[language]
    texts = (first, second)

    _, result = _ask(
        (Part("the order value", (texts[at],)),),
        first,
        second,
        question,
        key,
        language,
    )

    assert result.passage_ids == (at + 1,)
    assert result.fact_ids == (at + 1,)


_DORMANT = {
    "en": (
        "An account with no payment for 24 months is dormant.",
        "A dormant account is charged 30 EUR a year.",
        "What does an account cost a year after 24 months without a payment?",
        "30 EUR a year",
    ),
    "de": (
        "Ein Konto ohne Zahlung während 24 Monaten gilt als ruhend.",
        "Für ein ruhendes Konto werden 30 EUR im Jahr berechnet.",
        "Was kostet ein Konto im Jahr nach 24 Monaten ohne Zahlung?",
        "30 EUR im Jahr",
    ),
}


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_needs_both_question_each_passage_states_a_part_of_stays_two_passage(
    language: str,
) -> None:
    """One passage ties the situation to the rule, the other gives the figure."""
    first, second, question, key = _DORMANT[language]
    parts = (
        Part("the account counts as dormant", (first,)),
        Part("the charge", (second,)),
    )

    _, result = _ask(parts, first, second, question, key, language)

    assert result.passage_ids == (1, 2)
    assert result.kind == "needs_both"
    assert _needs_both(result) == [(1.0, True)]


_CASES = {
    "en": (
        "A standing order can be changed in online banking until the day before it is executed.",
        "A direct debit can be stopped in online banking until the day before it is debited.",
        "Until when can a standing order be changed and a direct debit be stopped?",
        "until the day before",
    ),
    "de": (
        "Ein Dauerauftrag kann im Online-Banking bis zum Vortag der Ausführung geändert werden.",
        "Eine Lastschrift kann im Online-Banking bis zum Vortag der Belastung gestoppt werden.",
        "Bis wann kann ein Dauerauftrag geändert und eine Lastschrift gestoppt werden?",
        "bis zum Vortag",
    ),
}


@pytest.mark.parametrize("language", ["en", "de"])
def test_two_cases_sharing_one_answer_stay_two_passage(language: str) -> None:
    """Each case the question names is a part of its own."""
    first, second, question, key = _CASES[language]
    parts = (Part("the standing order", (first,)), Part("the direct debit", (second,)))

    _, result = _ask(parts, first, second, question, key, language)

    assert result.passage_ids == (1, 2)
    assert _needs_both(result) == [(1.0, True)]


def test_a_quote_no_cited_passage_holds_counts_for_none() -> None:
    """The invented part holds nowhere, so the first passage carries what is held."""
    first, second, question, key = _DORMANT["en"]
    parts = (
        Part("dormant", (first,)),
        Part("closing", ("Dormant accounts are closed after five years.",)),
    )

    _, result = _ask(parts, first, second, question, key)

    assert result.passage_ids == (1,)
    assert _needs_both(result) == [(0.0, True)]


def test_a_quote_both_passages_hold_counts_for_both() -> None:
    """Whichever passage the model meant, a shared clause needs neither more."""
    first = "Returns are accepted within 30 days of delivery."
    second = "Returns are accepted within 30 days of delivery. Refunds take 5 days."

    _, result = _ask(
        (Part("the return period", (first,)),),
        first,
        second,
        "Within how many days can a purchase be returned?",
        "within 30 days of delivery",
    )

    assert result.passage_ids == (1,)


_TIE = {
    "en": (
        "If a standing order fails, the bank tries again the next working day.",
        "If a direct debit fails, the bank tries again the next working day.",
        "What happens when a standing order or a direct debit fails?",
        "the bank tries again the next working day",
    ),
    "de": (
        "Schlägt ein Dauerauftrag fehl, versucht die Bank es am nächsten Werktag erneut.",
        "Schlägt eine Lastschrift fehl, versucht die Bank es am nächsten Werktag erneut.",
        "Was passiert, wenn ein Dauerauftrag oder eine Lastschrift fehlschlägt?",
        "die Bank versucht es am nächsten Werktag erneut",
    ),
}


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_tie_on_a_question_joining_two_cases_stays_two_passage(
    language: str,
) -> None:
    """Each passage may give the same rule for its own case."""
    first, second, question, key = _TIE[language]
    parts = (Part("the retry", (first, second)),)

    _, result = _ask(parts, first, second, question, key, language)

    assert result.passage_ids == (1, 2)
    assert result.kind == "needs_both"
    assert _needs_both(result) == [(1.0, True)]


@pytest.mark.parametrize("language", ["en", "de"])
def test_coordinates_reads_a_conjunction(language: str) -> None:
    """Universal POS, so no word list per language."""
    from question_generation.gates import coordinates

    no = {
        "en": "Within how many days can a purchase be returned?",
        "de": "Ab welchem Bestellwert ist der Versand kostenlos?",
    }[language]

    assert coordinates(_TIE[language][2], language)
    assert not coordinates(no, language)


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_tie_with_no_conjunction_is_still_cited_from_the_first(
    language: str,
) -> None:
    """Both passages state the one thing asked: a duplicate, not two cases."""
    first, second, question, key, again = _STATED_ONE[language]

    _, result = _ask(
        (Part("the return period", (first, again)),),
        first,
        second,
        question,
        key,
        language,
    )

    assert result.passage_ids == (1,)


_ITEMS = {
    "en": (
        "For orders over 50 EUR, shipping and returns are free.",
        "Gift cards cannot be exchanged for cash.",
        "What do shipping and returns cost for orders over 50 EUR?",
        "nothing",
    ),
    "de": (
        "Bei Bestellungen über 50 EUR sind Versand und Rücksendung kostenlos.",
        "Geschenkkarten können nicht in Bargeld umgetauscht werden.",
        "Was kosten Versand und Rücksendung bei Bestellungen über 50 EUR?",
        "nichts",
    ),
}


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_subset_on_a_question_joining_two_items_is_still_narrowed(
    language: str,
) -> None:
    """Only a tie keeps both: here one passage holds every part."""
    first, second, question, key = _ITEMS[language]
    parts = (Part("shipping", (first,)), Part("returns", (first,)))

    _, result = _ask(parts, first, second, question, key, language)

    assert result.passage_ids == (1,)


def test_a_tie_on_two_items_both_passages_repeat_keeps_both() -> None:
    """Pins the shortcut: a conjunction keeps both even for a plain duplicate."""
    first = "Members pay nothing for shipping and returns."
    second = "Shipping and returns are free for members."

    _, result = _ask(
        (Part("the cost", (first, second)),),
        first,
        second,
        "What do members pay for shipping and returns?",
        "nothing",
    )

    assert result.passage_ids == (1, 2)


class _Down(ByParts):
    """A verifier whose parts reading cannot be had."""

    def __init__(self, error: Exception, **kwargs) -> None:
        """Initialises with what the reading raises."""
        super().__init__((), **kwargs)
        self.error = error

    def stated(self, question: str, key: str, passages, thread=()):
        """Raises, as an outage or a provider's refusal does."""
        raise self.error


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("error", [ModelUnavailable, ModelRefused])
@pytest.mark.parametrize("pair", [_DORMANT, _STATED_ONE], ids=["bank", "shop"])
def test_a_parts_reading_that_cannot_be_had_keeps_both_and_loses_nothing(
    language: str, error, pair
) -> None:
    """The check is an opinion about the citation: the accepted question stays."""
    first, second, question, key = pair[language][:4]
    recording = _Down(error("down"), recovers=key)

    result = build(recording).check(
        candidate(
            question_text=question,
            target_answer=key,
            facts=_two(first, second, language),
            kind="needs_both",
        )
    )

    assert result.accepted
    assert result.passage_ids == (1, 2)
    assert result.kind == "needs_both"
    assert _needs_both(result) == []


def test_no_part_quoted_from_any_passage_keeps_both_and_reads_nothing() -> None:
    """Nothing located is nothing decided."""
    first, second, question, key, _ = _SHIPPING["en"]
    parts = (Part("free shipping", ("Shipping is free above 50 EUR.",)), Part("x", ()))

    _, result = _ask(parts, first, second, question, key)

    assert result.passage_ids == (1, 2)
    assert _needs_both(result) == []


def test_a_bridge_one_passage_states_whole_keeps_both_with_the_reading() -> None:
    """A bridge cited alone has no fact resting on one passage to cite."""
    from factories import bridge, resting

    one = "Gift cards bought in a store can be redeemed in the online shop."
    two = "In the online shop a gift card cannot be combined with a discount code."
    fact = bridge(
        resting(2, text=two, topic_id=2),
        statement=(
            "A gift card bought in a store can be redeemed in the online shop, "
            "where it cannot be combined with a discount code."
        ),
        passage_text=one,
        topic_id=1,
        fact_id=7,
    )
    recording = ByParts((Part("where", (one,)),), recovers="in the online shop")

    result = build(recording).check(
        candidate(
            question_text="Where can a gift card bought in a store be redeemed besides the store?",
            target_answer="in the online shop",
            facts=group(fact),
            kind="needs_both",
        )
    )

    assert result.accepted
    assert result.passage_ids == (1, 2)
    assert _needs_both(result) == [(0.0, True)]


def test_a_follow_up_whose_narrowed_citation_asks_nothing_new_keeps_both() -> None:
    """Narrowed to the root's fact, the turn would ask one fact twice."""
    first = "Eine Auslandsüberweisung kostet pauschal 5 Euro."
    second = "Auslandsüberweisungen über 10.000 Euro werden zusätzlich manuell geprüft."
    _, result = _ask(
        (Part("der Preis", (first,)),),
        first,
        second,
        "Gilt der Preis auch über 10.000 Euro?",
        "ja, pauschal 5 Euro",
        "de",
        thread=(("Was kostet eine Auslandsüberweisung?", "5 Euro"),),
        root_facts=(1,),
        parent_passages=(1,),
    )

    assert result.accepted
    assert result.fact_ids == (1, 2)
    assert _needs_both(result) == [(0.0, True)]


def test_a_compound_question_is_never_read_for_its_parts() -> None:
    """Its own check reads each half."""
    recording = ByParts(())

    build(recording).check(
        candidate(
            facts=_pair(),
            kind="compound",
            target_answer="4 kilograms",
        )
    )

    assert recording.stated_asked == 0


def test_a_derived_type_or_a_one_passage_question_is_never_read_for_its_parts() -> None:
    """No call for what has no two passages to tell apart."""
    from database.qa_generator import QuestionType

    facts = _two("Standard delivery costs 5 euros.", "Express delivery costs 9 euros.")
    derived = ByParts(())
    build(derived).check(
        candidate(
            question_text="What do one standard and one express delivery cost together?",
            target_answer="14 euros",
            facts=facts,
            question_type=QuestionType.AGGREGATION,
            kind="needs_both",
        )
    )
    one = ByParts(())
    build(one).check(candidate(facts=group(source(1, passage_id=1)), kind="needs_both"))

    assert (derived.stated_asked, one.stated_asked) == (0, 0)


def _holding(parts, texts):
    from question_generation.checker import needed

    return needed(
        tuple(Part(f"part {at}", tuple(one)) for at, one in enumerate(parts)), texts
    )


_NEEDED = [
    (
        "returns en",
        _STATED_ONE["en"][:2],
        [[_STATED_ONE["en"][0], _STATED_ONE["en"][4]]],
        (0,),
    ),
    (
        "returns de",
        _STATED_ONE["de"][:2],
        [[_STATED_ONE["de"][0], _STATED_ONE["de"][4]]],
        (0,),
    ),
    ("shipping en", _SHIPPING["en"][:2], [[_SHIPPING["en"][0]]], (0,)),
    ("shipping de", _SHIPPING["de"][:2], [[_SHIPPING["de"][1]]], (1,)),
    (
        "dormant en",
        _DORMANT["en"][:2],
        [[_DORMANT["en"][0]], [_DORMANT["en"][1]]],
        (0, 1),
    ),
    (
        "dormant de",
        _DORMANT["de"][:2],
        [[_DORMANT["de"][0]], [_DORMANT["de"][1]]],
        (0, 1),
    ),
    ("cases en", _CASES["en"][:2], [[_CASES["en"][0]], [_CASES["en"][1]]], (0, 1)),
    ("cases de", _CASES["de"][:2], [[_CASES["de"][0]], [_CASES["de"][1]]], (0, 1)),
    (
        "unheld quote",
        _DORMANT["en"][:2],
        [[_DORMANT["en"][0]], ["Dormant accounts are closed after five years."]],
        (0,),
    ),
    (
        "shared verbatim",
        (
            "Returns are accepted within 30 days of delivery.",
            "Returns are accepted within 30 days of delivery. Refunds take 5 days.",
        ),
        [["Returns are accepted within 30 days of delivery."]],
        (0,),
    ),
    (
        "nothing held",
        _SHIPPING["en"][:2],
        [["Shipping is free above 50 EUR."], []],
        None,
    ),
    (
        "three passages, two hold a part",
        (
            _DORMANT["en"][1],
            _DORMANT["en"][0],
            "Gift cards cannot be exchanged for cash.",
        ),
        [[_DORMANT["en"][1]], [_DORMANT["en"][0]]],
        (0, 1),
    ),
    (
        "three passages, a part only two others share en",
        (
            "The account fee is 4.90 EUR a month.",
            "Statements are sent free of charge every quarter.",
            "Statements are sent free of charge every quarter by post.",
        ),
        [
            ["The account fee is 4.90 EUR a month."],
            ["Statements are sent free of charge every quarter"],
        ],
        (0, 1),
    ),
    (
        "three passages, a part only two others share de",
        (
            "Rücksendungen sind innerhalb von 14 Tagen kostenlos.",
            "Der Versand ins Ausland kostet 9,95 EUR.",
            "Der Versand ins Ausland kostet 9,95 EUR pro Paket.",
        ),
        [
            ["Rücksendungen sind innerhalb von 14 Tagen kostenlos."],
            ["Der Versand ins Ausland kostet 9,95 EUR"],
        ],
        (0, 1),
    ),
    (
        "three passages, none with a part of its own",
        (
            "Cards are blocked after three wrong PINs. A new card costs 10 EUR.",
            "A new card costs 10 EUR. Cards are sent by post.",
            "Cards are blocked after three wrong PINs. Cards are sent by post.",
        ),
        [
            ["Cards are blocked after three wrong PINs."],
            ["A new card costs 10 EUR."],
            ["Cards are sent by post."],
        ],
        (0, 1),
    ),
]


@pytest.mark.parametrize(
    ("texts", "parts", "want"),
    [one[1:] for one in _NEEDED],
    ids=[one[0] for one in _NEEDED],
)
def test_needed_reads_the_passages_holding_a_part_of_their_own(
    texts, parts, want
) -> None:
    """A part counts for a passage only through a quote the passage holds."""
    assert _holding(parts, list(texts)) == want


class StatedClient:
    """A served model answering the parts reading, recording the ask."""

    model = "fake/verifier"

    def __init__(self, parts) -> None:
        """Initialises with the parts it lists."""
        self.parts = parts
        self.asked: list[tuple[str, str, str | None]] = []

    def answer(self, *, system: str, user: str, shape, prompt_version=None):
        """Records the call and answers in the shape asked for."""
        self.asked.append((system, user, prompt_version))
        return shape(parts=self.parts)


def test_the_verifier_lists_parts_over_numbered_passages() -> None:
    """One call: the passages numbered, the conversation, the question and the key."""
    from question_generation import verifier as module

    client = StatedClient(
        [
            module._Quoted(
                part=" the return period ",
                quotes=[" Returns are accepted within 30 days. ", "  "],
            )
        ]
    )

    got = Verifier(client).stated(
        "Within how many days?",
        "within 30 days",
        ["Returns are accepted within 30 days.", "Gift cards cannot be exchanged."],
        thread=(("Can I return a purchase?", "yes"),),
    )

    assert got == (
        Part("the return period", ("Returns are accepted within 30 days.",)),
    )
    system, user, version = client.asked[0]
    assert system == module._STATED
    assert version == STATED_VERSION
    for text in (
        "[1] Returns are accepted within 30 days.",
        "[2] Gift cards cannot be exchanged.",
        "Q: Can I return a purchase?\nA: yes",
        "Key: within 30 days",
    ):
        assert text in user


# ── A compound question: one half from each passage ───────────────────────

_BANK = {
    "en": (
        "The daily cash limit at a cash machine is 1,000 euros.",
        "An account is closed by a signed letter to the branch.",
        "What is the daily cash limit at a cash machine, and how is an account closed?",
        (
            (1, "What is the daily cash limit at a cash machine?", "1,000 euros"),
            (2, "How is an account closed?", "by a signed letter to the branch"),
        ),
    ),
    "de": (
        "Das tägliche Bargeldlimit am Automaten beträgt 1.000 Euro.",
        "Ein Konto wird durch einen unterschriebenen Brief an die Filiale geschlossen.",
        (
            "Wie hoch ist das tägliche Bargeldlimit am Automaten, und wie wird ein "
            "Konto geschlossen?"
        ),
        (
            (1, "Wie hoch ist das tägliche Bargeldlimit am Automaten?", "1.000 Euro"),
            (
                2,
                "Wie wird ein Konto geschlossen?",
                "durch einen unterschriebenen Brief an die Filiale",
            ),
        ),
    ),
}


class PerHalf(Recording):
    """A verifier answering each half asked alone from the passage it is shown."""

    def __init__(self, answers: dict[str, str | None]) -> None:
        """Initialises with what each half's question is answered with."""
        super().__init__()
        self.answers = answers
        self.asked: list[tuple[str, tuple[str, ...]]] = []

    def read(self, question: str, passages, thread=()) -> Reading:
        """Answers by the question and records what it was shown."""
        self.asked.append((question, tuple(passages)))
        return Reading(recovered=self.answers.get(question))


def _compound(language: str, question: str | None = None, **kwargs):
    one, two, asked, parts = _BANK[language]
    return candidate(
        question_text=question or asked,
        target_answer=kwargs.pop("target_answer", "; ".join(p[2] for p in parts)),
        facts=group(
            source(1, document="a", passage_id=1, statement=one, language=language),
            source(2, document="b", passage_id=2, statement=two, language=language),
        ),
        kind="compound",
        parts=kwargs.pop("parts", parts),
        **kwargs,
    )


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_compound_question_one_half_per_passage_is_accepted(language: str) -> None:
    """Each half is recovered from its own passage, and the merged question is not."""
    one, two, _, parts = _BANK[language]
    recording = PerHalf({part[1]: part[2] for part in parts})

    result = build(recording).check(_compound(language))

    assert result.rejected_reason is None
    assert result.kind == "compound"
    assert result.fact_ids == (1, 2)
    assert [(q, len(p)) for q, p in recording.asked] == [
        (parts[0][1], 1),
        (parts[1][1], 1),
    ]
    assert recording.asked[0][1][0].startswith(one)
    assert recording.asked[1][1][0].startswith(two)
    assert "round_trip" not in result.gates_ran


@pytest.mark.parametrize(
    ("language", "question"),
    [
        ("en", "How do the voucher expiry and the exchange period differ?"),
        (
            "de",
            (
                "Wie unterscheiden sich die Gültigkeit eines Gutscheins und die "
                "Umtauschfrist?"
            ),
        ),
    ],
)
def test_a_compound_question_claiming_a_relation_is_refused(
    language: str, question: str
) -> None:
    """Shop: the halves are unrelated on purpose, and one that says otherwise is another kind."""
    recording = PerHalf({})

    result = build(recording).check(_compound(language, question))

    assert result.rejected_reason == QuestionRejection.WRONG_TYPE
    assert recording.asked == []


def test_a_compound_key_is_its_halves_answers_whatever_their_closing_marks() -> None:
    """A half's answer may end in the full stop of its sentence and the key not.

    Written as a sentence copied from the passage, the first half's answer
    ends in `.`; joined, the key reads `...; ...`, which is the same key.
    """
    _, _, _, parts = _BANK["en"]
    stopped = (
        (parts[0][0], parts[0][1], parts[0][2] + "."),
        (parts[1][0], parts[1][1], parts[1][2] + "."),
    )
    recording = PerHalf({part[1]: part[2] for part in parts})

    result = build(recording).check(_compound("en", parts=stopped))

    assert result.rejected_reason is None


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_compound_half_its_passage_does_not_answer_is_refused(language: str) -> None:
    """NOT IN PASSAGE for half two, and the reason names the half."""
    _, _, _, parts = _BANK[language]
    recording = PerHalf({parts[0][1]: parts[0][2], parts[1][1]: None})

    checker = build(recording)

    result = checker.check(_compound(language))
    refused = checker._parts(_compound(language), AnswerForm.VALUE, [])

    assert result.rejected_reason == QuestionRejection.NOT_RECOVERABLE
    assert code(refused) == QuestionRejection.NOT_RECOVERABLE
    assert "half 2" in refused[1]


@pytest.mark.parametrize(
    "fields",
    [
        {"target_answer": "1,000 euros by letter"},
        {"parts": ((1, "What is the daily cash limit?", "1,000 euros"),)},
        {
            "parts": (
                (1, "What is the daily cash limit at a cash machine?", "1,000 euros"),
                (1, "How is an account closed?", "by a signed letter to the branch"),
            )
        },
    ],
)
def test_a_compound_key_not_in_its_halves_is_refused(fields: dict) -> None:
    """No split into the halves' answers, one half, or two halves on one passage."""
    recording = PerHalf({})

    result = build(recording).check(_compound("en", **fields))

    assert result.rejected_reason == QuestionRejection.MALFORMED
    assert recording.asked == []


@pytest.mark.parametrize(
    ("language", "question"),
    [
        ("en", "Who approves the request and how long may it take?"),
        ("de", "Wer genehmigt den Antrag und wie lange darf es dauern?"),
    ],
)
def test_an_ordinary_two_question_word_draft_is_still_refused_as_compound(
    language: str, question: str
) -> None:
    """Guard of today's gate: only the compound kind is let through it."""
    failed, _ = structural(
        question_text=question,
        target_answer="the board; two days",
        answerable=True,
        language=language,
        bounds=BOUNDS,
        forms=(AnswerForm.VALUE,),
    )

    assert code(failed) == QuestionRejection.COMPOUND


def test_the_relation_table_names_a_lemma_per_language_and_none_for_a_gap() -> None:
    """Keyed by ISO 639-1; a language with no row refuses nothing."""
    from question_generation.gates import relates

    assert relates("How do the fees differ?", "en") == "differ"
    assert relates("Worin unterscheiden sich die Gebühren?", "de") == "unterscheiden"
    assert relates("What is the limit, and how is an account closed?", "en") is None
    assert (
        relates("Was ist das Limit, und wie wird ein Konto geschlossen?", "de") is None
    )
    assert relates("Quel est le plafond, et ... both ... ?", "fr") is None


def test_a_relation_word_a_half_itself_asks_with_is_not_a_claim_of_relation() -> None:
    """`total` and `same-day` in a half are the half's; the joining span is what is read."""
    from question_generation.gates import relates

    question = "What is the total fee, and how long is same-day delivery?"
    halves = ("What is the total fee?", "How long is same-day delivery?")

    assert relates(question, "en", halves) is None
    assert relates("How do the fees and the delivery differ?", "en", halves) == "differ"
    assert (
        relates("Wie hoch sind beide Gebühren?", "de", ("Wie hoch ist die Gebühr?",))
        == "beide"
    )


def test_a_language_with_no_relation_row_is_logged_once(caplog) -> None:
    """A gate that silently never fires is the failure the language tables guard."""
    import logging

    from question_generation import gates

    gates._UNREAD.clear()
    with caplog.at_level(logging.WARNING, logger="question_generation.gates"):
        gates.relates("Quel est le plafond ?", "fr")
        gates.relates("Quel est le tarif ?", "fr")

    assert [r.getMessage() for r in caplog.records].count(
        "no relation words for language 'fr': a compound question is not checked for a claimed relation"
    ) == 1


def test_a_compound_key_is_held_to_its_form_part_by_part() -> None:
    """Two answers each inside the value bound are not one answer outside it."""
    first = "the form BR-12 at the branch counter desk"
    second = "the card hotline number 0800 123 456 line"
    parts = (
        (1, "What form closes an account?", first),
        (2, "What number blocks a card?", second),
    )
    bounds = {"value": (1, 60), "list": (3, 10), "explanation": (20, 600)}
    recording = PerHalf({one[1]: one[2] for one in parts})
    checker = QuestionChecker(
        embedder=recording,
        verifier=recording,
        nearest=lambda embedding, **_: None,
        threshold=0.93,
        phrasing=recording,
        bounds=bounds,
    )

    result = checker.check(
        _compound(
            "en",
            "What form closes an account, and what number blocks a card?",
            parts=parts,
            target_answer=f"{first}; {second}",
        )
    )

    assert result.rejected_reason is None
