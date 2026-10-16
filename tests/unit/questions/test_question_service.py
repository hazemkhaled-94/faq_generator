"""What the service does with a topic, short of touching a database.

The paths worth covering here are the ones that produce nothing: a topic
somebody took out of coverage, a topic whose facts are all already asked
about, and a model that will not answer. Each has to leave the row in a state
something can move it out of, because a queue that never empties says nothing
and a row nothing can move is a stage that has stopped.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from factories import source

from database.qa_generator import (
    Difficulty,
    FactKind,
    QuestionRejection,
    QuestionType,
    Status,
)
from llm.client import ModelUnavailable
from question_generation.config import Settings
from question_generation.models import CheckedQuestion, FactGroup, TopicToCover
from question_generation.queue import QuestionQueue
from question_generation.service import QuestionGenerationService
from stages.queue import StageQueue
from stages.service import HEARTBEAT_SECONDS

pytestmark = pytest.mark.nlp

SETTINGS = Settings(
    per_topic=4,
    sample_size=4,
    samples_per_passage=1,
    fact_kinds=("atomic",),
    type_mix={QuestionType.FACTOID: 3, QuestionType.REASON: 1},
    difficulty_mix={Difficulty.EASY: 1, Difficulty.MEDIUM: 1},
    followup_types=(QuestionType.CONDITION, QuestionType.REASON),
    unanswerable_share=0.25,
    followup_share=0.5,
    max_followups=2,
    # Nothing is asked twice here. A retry is another model call, and these
    # tests count the calls a topic costs.
    retries=0,
    answer_chars={"value": (1, 80), "list": (3, 300), "explanation": (20, 600)},
    explanation_chars=(150, 900),
    answer_coverage=0.0,
    party_density=0.0,
    meets_floor=0.0,
    answer_overlap=0.6,
    off_topic_overlap=0.3,
    elsewhere_passages=0,
    long_answer_chars=60,
    boilerplate_cosine=0.0,
    duplicate_cosine=0.93,
    duplicate_floor=0.75,
    release_size=0,
    release_unanswerable=0.1,
    release_difficulty={Difficulty.EASY: 1, Difficulty.MEDIUM: 1, Difficulty.HARD: 1},
    embedding_model="stub",
    max_tokens=512,
    model=None,
    verifier_model="ollama/verifier",
)


class StubQueue:
    """A queue that answers from memory and records what it was told."""

    done = Status.GENERATED

    def __init__(self, topic: TopicToCover | None, facts=(), bridges=()) -> None:
        """Initialises the queue with one topic, its facts and its bridges."""
        self._topic = topic
        self._facts = list(facts)
        self._bridges = list(bridges)
        self.stored: list[list[list[CheckedQuestion]]] = []
        self.failed: list[tuple[int, str]] = []
        self.finished: list[int] = []

    def abandon(self) -> int:
        """Sweeps nothing; there is no earlier run here."""
        return 0

    def touch(self) -> bool:
        """Refreshes the claim this queue holds."""
        return True

    def claim(self) -> TopicToCover | None:
        """Hands over the one topic, once."""
        claimed, self._topic = self._topic, None
        return claimed

    def facts(self, topic_id: int):
        """The facts this topic is the subject of."""
        return list(self._facts)

    def bridging(self, topic_id: int):
        """The facts of passages bridging this topic to another."""
        return list(self._bridges)

    def store(self, topic_id: int, threads) -> int:
        """Records the threads the topic produced and finishes it."""
        self.stored.append([list(one) for one in threads])
        self.finished.append(topic_id)
        return sum(len(one) for one in threads)

    @property
    def written(self) -> list:
        """Every question of the last store, threads flattened."""
        return [one for thread in self.stored[-1] for one in thread]

    def fail(self, key: int, error: str) -> None:
        """Records the failure against the row."""
        self.failed.append((key, error))


class StubWriter:
    """A writer that answers, or refuses, and counts the asks."""

    def __init__(self, raises: Exception | None = None) -> None:
        """Initialises the writer with what it will do when asked."""
        self._raises = raises
        self.calls = 0
        self.plans: list = []

    @property
    def model(self) -> str:
        """The model this writer would call."""
        return "ollama/stub"

    def write(self, group, plan):
        """Writes one question of the kind the plan asked for, or refuses."""
        self.calls += 1
        self.plans.append(plan)
        if self._raises:
            raise self._raises
        from factories import candidate

        return candidate(
            question_text=f"Question {self.calls}?",
            target_answer=None if not plan.answerable else "4 kg",
            answerable=plan.answerable,
            facts=group,
            question_type=plan.spec.name,
            planned_difficulty=plan.band,
        )

    def follow_up(self, group, thread, plan, root_facts=(), parent_passages=()):
        """Writes the next question in a thread."""
        self.calls += 1
        self.plans.append(plan)
        if self._raises:
            raise self._raises
        from factories import candidate

        return candidate(
            question_text=f"And question {self.calls}?",
            target_answer="12 hours",
            answerable=True,
            facts=group,
            thread=thread,
            question_type=plan.spec.name,
            planned_difficulty=plan.band,
        )


class StubChecker:
    """A checker that accepts everything and counts what it saw."""

    def __init__(self) -> None:
        """Initialises the checker with nothing checked yet."""
        self.seen_sizes: list[int] = []

    def check(self, candidate, seen=()) -> CheckedQuestion:
        """Accepts the candidate, noting how much this run had accepted."""
        self.seen_sizes.append(len(seen))
        return CheckedQuestion(
            question_text=candidate.question_text,
            target_answer=candidate.target_answer,
            answerable=candidate.answerable,
            criteria=candidate.group.criteria(
                len(candidate.target_answer or "") or None,
                follows=candidate.follows,
            ),
            language=candidate.group.language,
            status="accepted",
            rejected_reason=None,
            fact_ids=tuple(one.id for one in candidate.group.facts),
            thread_position=candidate.thread_position,
            question_type=candidate.spec.name,
            answer_form=candidate.spec.form if candidate.answerable else None,
            planned_difficulty=candidate.planned_difficulty,
        )


def build(
    topic: TopicToCover | None, facts=(), writer=None, checker=None, settings=None
):
    """A service over a scripted queue and a scripted pair of collaborators."""
    queue = StubQueue(topic, facts)
    service = QuestionGenerationService(
        repository=queue,
        writer=writer or StubWriter(),
        checker=checker or StubChecker(),
        settings=settings or SETTINGS,
    )
    return service, queue


def topic(**fields) -> TopicToCover:
    """One claimed topic, in coverage unless a test says otherwise."""
    return TopicToCover(
        id=fields.pop("id", 7),
        language=fields.pop("language", "en"),
        label=fields.pop("label", "Support"),
        include_in_coverage=fields.pop("include_in_coverage", True),
        **fields,
    )


def test_an_empty_queue_is_not_an_error(written=None) -> None:
    """A drain stops when the queue does."""
    service, queue = build(None)

    assert service.process_next() is None
    assert queue.stored == []


def test_a_topic_out_of_coverage_is_finished_with_nothing_written() -> None:
    """Somebody said this is not a subject, which is an answer and not work.

    Left `new` it would read as outstanding forever, and the model would be
    called for a topic a person deliberately excluded.
    """
    writer = StubWriter()
    service, queue = build(topic(include_in_coverage=False), [source(1)], writer=writer)

    service.process_next()

    assert queue.stored == [[]]
    assert queue.finished == [7]
    assert writer.calls == 0, "the model was called for an excluded topic"
    assert queue.failed == []


def test_a_topic_with_nothing_left_to_ask_about_is_finished_not_failed() -> None:
    """Every fact already carries an accepted question, which is success."""
    writer = StubWriter()
    service, queue = build(topic(), [], writer=writer)

    service.process_next()

    assert queue.stored == [[]]
    assert writer.calls == 0
    assert queue.failed == []


def test_a_topic_writes_no_more_than_it_was_asked_for() -> None:
    """QUESTIONS_PER_TOPIC times the topic count is what a run costs."""
    facts = [source(n, document="ab"[n % 2], passage_id=n) for n in range(20)]
    service, queue = build(topic(), facts)

    service.process_next()

    assert len(queue.stored[0]) == SETTINGS.per_topic, "one thread per root"


def test_the_run_sees_what_it_has_already_accepted() -> None:
    """Nothing is stored until the topic is finished.

    Without carrying the accepted ones forward, the dedup gate compares each
    candidate only against what the database held when the run started.
    """
    facts = [source(n, document="ab"[n % 2], passage_id=n) for n in range(20)]
    checker = StubChecker()
    service, _ = build(topic(), facts, checker=checker)

    service.process_next()

    # Every accepted question joins the set, follow-ups included, so the
    # list only ever grows and each candidate sees one more than the last.
    assert checker.seen_sizes == sorted(checker.seen_sizes)
    assert checker.seen_sizes[0] == 0
    assert checker.seen_sizes[-1] == len(checker.seen_sizes) - 1


def test_the_unanswerable_share_reaches_the_writer() -> None:
    """A quarter of four is one, and it is the fourth."""
    facts = [source(n, document="ab"[n % 2], passage_id=n) for n in range(20)]
    service, queue = build(topic(), facts)

    service.process_next()

    roots = [thread[0] for thread in queue.stored[0]]
    assert [one.answerable for one in roots] == [True, True, True, False]
    assert roots[-1].target_answer is None


def test_a_model_that_will_not_answer_fails_the_topic(caplog) -> None:
    """Recorded against the row with a reason, so retry can move it."""
    writer = StubWriter(raises=ModelUnavailable("Timeout: the model did not answer"))
    service, queue = build(topic(), [source(1)], writer=writer)

    service.process_next()

    assert queue.stored == [], "a failed topic must not be marked done"
    assert len(queue.failed) == 1
    key, error = queue.failed[0]
    assert key == 7
    assert "did not answer" in error


class RefusesOnCalls(StubWriter):
    """A writer whose provider turns away the prompts of the calls named."""

    def __init__(self, *calls: int) -> None:
        """Initialises the writer with the calls to refuse, all when none."""
        super().__init__()
        self._refused = set(calls)

    def write(self, group, plan, note: str = ""):
        """Refuses as a content filter does, or writes."""
        if not self._refused or self.calls + 1 in self._refused:
            from llm.client import ModelRefused

            self.calls += 1
            raise ModelRefused("ContentPolicyViolationError: filtered")
        return super().write(group, plan)

    def follow_up(self, group, thread, plan, root_facts=(), parent_passages=()):
        """Refuses every follow-up, so a thread stops at its root."""
        from llm.client import ModelRefused

        self.calls += 1
        raise ModelRefused("ContentPolicyViolationError: filtered")


def test_a_refused_prompt_skips_its_slot_and_keeps_the_topic(caplog) -> None:
    """One prompt a content filter turns away costs one question, not the topic."""
    facts = [source(n, document="a", passage_id=n) for n in range(6)]
    service, queue = build(
        topic(),
        facts,
        writer=RefusesOnCalls(1),
        settings=replace(SETTINGS, per_topic=3, followup_share=0.0),
    )

    service.process_next()

    assert queue.failed == [], "one refused prompt failed the whole topic"
    assert len(queue.written) == 2, queue.written
    assert "refused" in caplog.text.lower()


def test_a_refused_retry_keeps_the_draft_it_was_retrying() -> None:
    """The draft a gate refused is stored even when its retry is turned away."""

    class RefusesRetries(RetryingWriter):
        def write(self, group, plan, note: str = ""):
            if note:
                from llm.client import ModelRefused

                raise ModelRefused("ContentPolicyViolationError: filtered")
            return super().write(group, plan, note)

    service, queue = build(
        topic(),
        [source(1, passage_id=1, language="en")],
        writer=RefusesRetries(),
        checker=RefusesTheFirstDraft(),
        settings=replace(SETTINGS, retries=1, per_topic=1, followup_share=0.0),
    )

    service.process_next()

    assert queue.failed == []
    assert [one.status for one in queue.written] == ["rejected"]


def test_a_refused_follow_up_ends_its_thread_and_keeps_its_root() -> None:
    """A thread whose next turn is turned away is the root alone."""

    class RefusesFollowUps(StubWriter):
        def follow_up(self, group, thread, plan, root_facts=(), parent_passages=()):
            from llm.client import ModelRefused

            raise ModelRefused("ContentPolicyViolationError: filtered")

    facts = [source(n, document="a", passage_id=n) for n in range(8)]
    service, queue = build(topic(), facts, writer=RefusesFollowUps())

    service.process_next()

    assert queue.failed == []
    assert all(len(thread) == 1 for thread in queue.stored[0])


def test_a_provider_that_refuses_everything_still_fails_the_topic() -> None:
    """A run of refusals is a model answering nothing, and the row says so."""
    facts = [source(n, document="a", passage_id=n) for n in range(12)]
    service, queue = build(
        topic(),
        facts,
        writer=RefusesOnCalls(),
        settings=replace(SETTINGS, per_topic=10, followup_share=0.0),
    )

    service.process_next()

    assert queue.stored == []
    assert len(queue.failed) == 1
    assert "ContentPolicyViolationError" in queue.failed[0][1]


def test_a_failure_names_the_kind_of_error_it_was() -> None:
    """One line on the row; the traceback goes to the log."""
    service, queue = build(
        topic(), [source(1)], writer=StubWriter(raises=RuntimeError("boom"))
    )

    service.process_next()

    assert queue.failed[0][1].startswith("RuntimeError:")


def test_a_drain_works_the_queue_until_it_is_empty() -> None:
    """Which is one topic here, and then nothing."""
    service, queue = build(topic(), [source(1)])

    assert service.drain() == 1
    assert queue.finished == [7]


@pytest.mark.parametrize("size", [0, -1])
def test_a_sample_size_below_one_never_yields_an_empty_group(size) -> None:
    """An empty group has no language to write in and no spread to read.

    QUESTIONS_FACT_SAMPLE is a number out of a settings file, and the one
    thing the deal must not do with a silly one is hand back a group nothing
    downstream can use.
    """
    from question_generation.selection import Deal

    deal = Deal([source(n, passage_id=n) for n in range(3)], wanted=5, size=size)
    formed = [deal.sample() for _ in range(3)]

    assert all(one is not None for one in formed), "every fact was dropped"
    assert all(one.facts for one in formed if one)
    assert all(one.language == "en" for one in formed if one)


def test_a_topic_is_held_by_the_beat_and_not_by_the_lease() -> None:
    """What a stranded topic used to cost, and no longer does.

    Nothing but the lease running out used to return an `in_progress` row:
    stop moves `pending`, retry moves `failed`, rerun skips what is held.
    A lease sized for the worst case a topic could cost was therefore also
    how long a killed worker's topic stayed unreachable - days of it.

    The queue takes the default now, and a worker says it is still there
    every `HEARTBEAT_SECONDS`, so the work may run as long as it likes.
    """
    assert QuestionQueue().lease == StageQueue.lease
    assert StageQueue.lease <= timedelta(minutes=5)
    assert HEARTBEAT_SECONDS * 2 < StageQueue.lease.total_seconds()


def test_the_phrasing_gate_is_off_when_the_phrasing_model_is_the_writer(
    monkeypatch,
) -> None:
    """The factory decides it from the model that holds the opinions.

    Through `build_service` itself, so the flag the checker ends up holding
    is the one the factory set, not a copy of the rule here.
    """
    from llm.config import Settings as ModelSettings
    from question_generation import factory

    monkeypatch.setattr(factory, "Embedder", lambda *args: object())
    model = ModelSettings(
        model="ollama/writer",
        base_url=None,
        structured_mode="JSON_SCHEMA",
        temperature=0.0,
        timeout_seconds=900.0,
        max_attempts=3,
        num_ctx=None,
        reasoning_effort=None,
    )

    def judges(verifier: str | None, phrasing: str | None) -> bool:
        """Whether a service wired for these models may judge phrasing."""
        service = factory.build_service(
            replace(
                SETTINGS,
                model=None,
                verifier_model=verifier,
                phrasing_model=phrasing,
            ),
            model,
        )
        return service._checker._judge_phrasing

    assert judges("ollama/verifier", None) is True
    assert judges(None, None) is False
    assert judges("ollama/writer", None) is False
    # The opinions come from the phrasing model, whoever verifies.
    assert judges(None, "ollama/phrasing") is True
    assert judges("ollama/verifier", "ollama/writer") is False


# ── Follow-up threads ──────────────────────────────────────────────────────


def test_a_thread_is_a_root_and_the_questions_that_follow_it() -> None:
    """Stored as a thread so each follow-up can be linked to its parent.

    A follow-up needs the parent's id and the parent has none until it is
    inserted, which is why the queue takes threads rather than a flat list.
    """
    facts = [source(n, document="a", passage_id=n) for n in range(8)]
    service, queue = build(topic(), facts)

    service.process_next()

    threads = queue.stored[0]
    followed = [one for one in threads if len(one) > 1]
    assert followed, "no thread ran past its root"
    for thread in followed:
        assert thread[0].thread_position == 1
        assert [one.thread_position for one in thread] == list(
            range(1, len(thread) + 1)
        )
        assert all(one.follows for one in thread[1:])


def test_a_thread_never_runs_past_the_maximum() -> None:
    """QUESTIONS_MAX_FOLLOWUPS is what a topic's worst case is priced from."""
    facts = [source(n, document="a", passage_id=n) for n in range(8)]
    service, queue = build(topic(), facts)

    service.process_next()

    assert all(len(thread) <= 1 + SETTINGS.max_followups for thread in queue.stored[0])


def test_an_unanswerable_question_is_never_followed() -> None:
    """There is nothing to follow on from.

    The chatbot was supposed to say it did not know, so a second question
    after that measures nothing.
    """
    facts = [source(n, document="a", passage_id=n) for n in range(8)]
    service, queue = build(topic(), facts)

    service.process_next()

    for thread in queue.stored[0]:
        if not thread[0].answerable:
            assert len(thread) == 1


def test_a_rejected_root_is_never_followed() -> None:
    """A conversation starting with a question nobody would ask."""

    class Refusing(StubChecker):
        """A checker that rejects everything it sees."""

        def check(self, candidate, seen=()):
            """Rejects the candidate."""
            checked = super().check(candidate, seen)
            return replace(checked, status="rejected", rejected_reason="malformed")

    facts = [source(n, document="a", passage_id=n) for n in range(8)]
    service, queue = build(topic(), facts, checker=Refusing())

    service.process_next()

    assert all(len(thread) == 1 for thread in queue.stored[0])


def test_a_follow_up_is_written_from_the_same_sample_as_its_root() -> None:
    """So the thread is about one subject rather than two in sequence."""
    facts = [source(n, document="a", passage_id=n // 3) for n in range(12)]
    passage_of = {one.id: one.passage_id for one in facts}
    service, queue = build(topic(), facts)

    service.process_next()

    followed = [thread for thread in queue.stored[0] if len(thread) > 1]
    assert followed, "no thread ran past its root"
    for root, *rest in followed:
        for one in rest:
            assert set(root.fact_ids) <= set(one.fact_ids)
            assert {passage_of[f] for f in one.fact_ids} <= {
                passage_of[f] for f in root.fact_ids
            }


def test_a_follow_up_is_shown_what_was_already_asked() -> None:
    """Without the thread it is a fresh question, not a follow-up."""
    seen: list = []

    class Watching(StubWriter):
        """Records the conversation each follow-up was written from."""

        def follow_up(self, group, thread, plan, root_facts=(), parent_passages=()):
            """Keeps the thread and writes as scripted."""
            seen.append(tuple(thread))
            return super().follow_up(group, thread, plan, root_facts, parent_passages)

    facts = [source(n, document="a", passage_id=n) for n in range(8)]
    service, _ = build(topic(), facts, writer=Watching())

    service.process_next()

    assert seen, "no follow-up was written"
    assert all(turns for turns in seen), "a follow-up was written with no thread"
    assert any(len(turns) > 1 for turns in seen), "no second follow-up saw two turns"


def test_a_follow_up_is_held_to_every_passage_its_thread_rested_on() -> None:
    """A third turn may come back to the root's passage after the second walked on."""
    held: list = []

    class Walking(StubWriter):
        """Cites a passage of its own on every follow-up."""

        def follow_up(self, group, thread, plan, root_facts=(), parent_passages=()):
            """Records what it is held to, and walks to a new passage."""
            held.append(set(parent_passages))
            written = super().follow_up(
                group, thread, plan, root_facts, parent_passages
            )
            step = 100 + len(held)
            return replace(
                written,
                group=FactGroup((source(step, document="a", passage_id=step),)),
            )

    class Resting(StubChecker):
        """Accepts, recording the passages each question rests on."""

        def check(self, candidate, seen=()) -> CheckedQuestion:
            """Accepts as scripted, with the passages kept."""
            checked = super().check(candidate, seen)
            resting = tuple(passage.id for passage in candidate.group.resting)
            return replace(checked, passage_ids=resting)

    facts = [source(n, document="a", passage_id=n) for n in range(8)]
    service, _ = build(topic(), facts, writer=Walking(), checker=Resting())

    service.process_next()

    assert len(held) >= 2, "no second follow-up was written"
    assert held[0], "the root rested on no passage"
    assert held[0] <= held[1], held


def test_the_turns_of_a_thread_take_the_kinds_they_were_configured_to() -> None:
    """A conversation that asks the same kind three times is one question.

    QUESTIONS_FOLLOWUP_TYPES is cycled down the thread, so it moves from a
    value to the circumstances it applies in to the reason behind it. The
    cycle starts where the thread sits among the followed ones rather than
    always at the first type, so a list longer than QUESTIONS_MAX_FOLLOWUPS
    is a rotation and not a prefix with a dead tail.
    """
    # Every fact states a reason, so a `reason` turn always has one to ask.
    facts = [
        source(n, document="a", passage_id=n, statement=REASONED) for n in range(8)
    ]
    writer = StubWriter()
    service, queue = build(topic(), facts, writer=writer)

    service.process_next()

    names = list(SETTINGS.followup_types)
    threads = [one for one in queue.stored[0] if len(one) > 1]
    assert threads, "no thread was followed up"
    for thread in threads:
        turns = [one.question_type for one in thread[1:]]
        start = names.index(turns[0])
        assert turns == [names[(start + n) % len(names)] for n in range(len(turns))], (
            "a thread repeated a kind instead of cycling the configured list"
        )


def test_every_configured_follow_up_kind_is_reached_over_a_run() -> None:
    """The defect the rotation fixes.

    A thread runs QUESTIONS_MAX_FOLLOWUPS turns. Starting every one of them
    at the first configured type means nothing past that many is ever
    written, however many are configured: three types and two turns left the
    third unwritten in a whole corpus.
    """
    names = (QuestionType.CONDITION, QuestionType.REASON, QuestionType.COMPARISON)
    # Enough slots that three threads are followed: the share takes every
    # other slot and the unanswerable ones are never followed, so a topic of
    # four reaches one thread and rotates nothing.
    settings = replace(SETTINGS, followup_types=names, max_followups=2, per_topic=12)
    facts = [
        source(n, document="a", passage_id=n, statement=REASONED) for n in range(40)
    ]
    service, queue = build(topic(), facts, writer=StubWriter(), settings=settings)

    service.process_next()

    written = {
        one.question_type for thread in queue.stored[0] for one in thread if one.follows
    }
    assert set(names) <= written, f"never wrote {set(names) - written}"


# ── A reason, which only material that states one can answer ──────────────

#: A fact whose evidence says why, and one that only states a rule.
REASONED = "Requests are confirmed in writing so that the agreed time can be evidenced."
RULES = (
    "A standard request is answered within 48 hours.",
    "An urgent request is answered within 4 hours.",
    "A request left unconfirmed for five days is closed.",
    "The site manager approves every change to the shift plan.",
    "A request may be raised by phone.",
)


class Handed(StubWriter):
    """Records the sample each slot was handed beside its plan."""

    def __init__(self) -> None:
        """Initialises the writer with nothing handed yet."""
        super().__init__()
        self.handed: list[tuple[FactGroup, object]] = []

    def write(self, group, plan):
        """Keeps what this slot was dealt, then writes as scripted."""
        self.handed.append((group, plan))
        return super().write(group, plan)


def test_a_list_slot_is_not_dealt_an_elided_passage() -> None:
    """A list asked of a copy with gaps in it is keyed with the items it kept."""
    facts = [
        source(
            1,
            document="a",
            passage_id=1,
            passage_text="The required documents are now: (…) a passport.",
        ),
        source(2, document="a", passage_id=2, statement="A passport is required."),
    ]
    writer = Handed()
    settings = replace(
        SETTINGS,
        per_topic=1,
        sample_size=1,
        type_mix={QuestionType.ENUMERATION: 1},
        unanswerable_share=0.0,
        followup_share=0.0,
    )
    service, _ = build(topic(), facts, writer=writer, settings=settings)

    service.process_next()

    ((dealt, _slot),) = writer.handed
    assert [one.passage_id for one in dealt.facts] == [2]


def reasons_only(**changes) -> Settings:
    """Root slots that are all `reason`, one fact each and no thread."""
    return replace(
        SETTINGS,
        **{
            "per_topic": 6,
            "sample_size": 1,
            "type_mix": {QuestionType.REASON: 1},
            "difficulty_mix": {Difficulty.EASY: 1},
            "unanswerable_share": 0.0,
            "followup_share": 0.0,
            **changes,
        },
    )


def test_a_reason_slot_is_never_handed_a_sample_that_states_no_reason() -> None:
    """Five passages state rules and one states why; that one is dealt.

    A why question written from a rule has a circular key or an invented
    one, and no gate can tell either from a sound reason.
    """
    facts = [
        source(n + 1, document="a", passage_id=n + 1, statement=text)
        for n, text in enumerate([*RULES, REASONED])
    ]
    writer = Handed()
    service, _ = build(topic(), facts, writer=writer, settings=reasons_only())

    service.process_next()

    reasons = [
        [one.statement for one in group.facts]
        for group, plan in writer.handed
        if plan.spec.name == QuestionType.REASON
    ]
    assert reasons == [[REASONED]]


def test_a_reason_slot_the_topic_cannot_supply_is_written_as_another_kind() -> None:
    """Swapped as an unanswerable slot is, to a kind that does not span."""
    facts = [
        source(n + 1, document="a", passage_id=n + 1, statement=text)
        for n, text in enumerate(RULES)
    ]
    writer = Handed()
    settings = reasons_only(
        type_mix={QuestionType.REASON: 1, QuestionType.FACTOID: 1}, per_topic=4
    )
    service, _ = build(topic(), facts, writer=writer, settings=settings)

    service.process_next()

    kinds = [plan.spec.name for _, plan in writer.handed]
    assert len(kinds) == 4, "a slot was dropped rather than swapped"
    assert set(kinds) == {QuestionType.FACTOID}


def test_a_language_with_no_markers_deals_a_reason_slot_as_before() -> None:
    """Nothing is known about how it states a reason, so nothing is filtered."""
    facts = [
        source(n + 1, document="a", passage_id=n + 1, language="es", statement=text)
        for n, text in enumerate(RULES)
    ]
    writer = Handed()
    service, _ = build(topic(), facts, writer=writer, settings=reasons_only())

    service.process_next()

    kinds = [plan.spec.name for _, plan in writer.handed]
    assert kinds == [QuestionType.REASON] * len(RULES)


def test_a_reason_turn_with_no_reason_to_ask_takes_the_next_kind() -> None:
    """A thread asks why only where the material it is on says why."""
    facts = [
        source(n + 1, document="a", passage_id=n + 1, statement=text)
        for n, text in enumerate(RULES)
    ]
    writer = StubWriter()
    settings = replace(
        SETTINGS,
        type_mix={QuestionType.FACTOID: 1},
        followup_types=(QuestionType.REASON, QuestionType.CONDITION),
        followup_share=1.0,
        max_followups=1,
        unanswerable_share=0.0,
    )
    service, queue = build(topic(), facts, writer=writer, settings=settings)

    service.process_next()

    turns = [one.question_type for thread in queue.stored[0] for one in thread[1:]]
    assert turns, "no thread was followed"
    assert QuestionType.REASON not in turns


def test_a_swapped_reason_slot_says_what_it_became(caplog) -> None:
    """A mix that came out short of reasons is a fact somebody wants to read."""
    facts = [
        source(n + 1, document="a", passage_id=n + 1, statement=text)
        for n, text in enumerate(RULES)
    ]
    settings = reasons_only(
        type_mix={QuestionType.REASON: 1, QuestionType.FACTOID: 1}, per_topic=2
    )
    service, _ = build(topic(id=11), facts, settings=settings)

    with caplog.at_level("INFO", logger="question_generation.service"):
        service.process_next()

    (said,) = [one for one in caplog.records if "states a reason" in one.message]
    assert said.levelname == "INFO"
    assert "topic 11" in said.message
    assert "reason" in said.message and "factoid" in said.message
    assert said.__dict__["topic.id"] == 11


def test_a_reason_slot_with_nothing_to_become_is_skipped_out_loud(caplog) -> None:
    """Writing nothing is a decision, and a quiet one reads as a short topic."""
    facts = [
        source(n + 1, document="a", passage_id=n + 1, statement=text)
        for n, text in enumerate(RULES)
    ]
    service, _ = build(topic(id=12), facts, settings=reasons_only(per_topic=1))

    with caplog.at_level("INFO", logger="question_generation.service"):
        service.process_next()

    (said,) = [one for one in caplog.records if "not written" in one.message]
    assert said.levelname == "WARNING"
    assert "topic 12" in said.message
    assert said.__dict__["topic.id"] == 12


def test_a_thread_with_no_kind_left_to_ask_is_skipped_out_loud(caplog) -> None:
    """The follow-up half of the same decision."""
    facts = [
        source(n + 1, document="a", passage_id=n + 1, statement=text)
        for n, text in enumerate(RULES)
    ]
    settings = replace(
        SETTINGS,
        per_topic=1,
        type_mix={QuestionType.FACTOID: 1},
        followup_types=(QuestionType.REASON,),
        followup_share=1.0,
        unanswerable_share=0.0,
    )
    service, _ = build(topic(id=13), facts, settings=settings)

    with caplog.at_level("INFO", logger="question_generation.service"):
        service.process_next()

    (said,) = [one for one in caplog.records if "not followed" in one.message]
    assert said.levelname == "WARNING"
    assert "topic 13" in said.message
    assert said.__dict__["topic.id"] == 13


def test_a_thread_without_a_reason_to_ask_never_repeats_a_kind() -> None:
    """The reason turn drops out of the cycle, not into another kind's place.

    Swapped turn by turn, the second thread took `comparison` for its reason
    turn and then `comparison` again as its own next turn.
    """
    facts = [
        source(n + 1, document="a", passage_id=n + 1, statement=RULES[n % len(RULES)])
        for n in range(12)
    ]
    settings = replace(
        SETTINGS,
        per_topic=4,
        type_mix={QuestionType.FACTOID: 1},
        followup_types=(
            QuestionType.CONDITION,
            QuestionType.REASON,
            QuestionType.COMPARISON,
        ),
        followup_share=1.0,
        max_followups=2,
        unanswerable_share=0.0,
    )
    service, queue = build(topic(), facts, settings=settings)

    service.process_next()

    threads = [
        [one.question_type for one in thread[1:]]
        for thread in queue.stored[0]
        if len(thread) > 2
    ]
    assert len(threads) >= 2, "too few threads reached a second turn"
    assert all(len(set(turns)) == len(turns) for turns in threads), threads


def test_a_reason_turn_on_material_that_says_why_is_still_asked() -> None:
    """The filter narrows what is asked; it does not turn the kind off."""
    facts = [
        source(1, document="a", passage_id=1, statement=RULES[0]),
        source(2, document="a", passage_id=1, statement=REASONED),
    ]
    settings = replace(
        SETTINGS,
        per_topic=1,
        sample_size=1,
        type_mix={QuestionType.FACTOID: 1},
        difficulty_mix={Difficulty.EASY: 1},
        followup_types=(QuestionType.REASON,),
        followup_share=1.0,
        max_followups=1,
        unanswerable_share=0.0,
    )
    service, queue = build(topic(), facts, settings=settings)

    service.process_next()

    (root, turn), *_ = queue.stored[0]
    assert root.question_type == QuestionType.FACTOID
    assert turn.question_type == QuestionType.REASON


# ── The plan, which is what makes the set configurable ────────────────────


def test_every_question_is_written_to_a_plan() -> None:
    """The kind and the band are decided before anything is written."""
    facts = [source(n, document="ab"[n % 2], passage_id=n) for n in range(20)]
    writer = StubWriter()
    service, _ = build(topic(), facts, writer=writer)

    service.process_next()

    assert writer.plans
    assert {one.spec.name for one in writer.plans} <= set(SETTINGS.type_mix) | set(
        SETTINGS.followup_types
    )


def test_the_kinds_written_are_the_kinds_that_were_asked_for() -> None:
    """A type with no weight is never planned, which is the switch."""
    facts = [source(n, document="ab"[n % 2], passage_id=n) for n in range(20)]
    service, queue = build(topic(), facts)

    service.process_next()

    roots = [thread[0] for thread in queue.stored[0]]
    assert {one.question_type for one in roots} <= set(SETTINGS.type_mix)


def test_what_the_plan_asked_for_is_stored_beside_what_came_out() -> None:
    """Two runs of one corpus have to be comparable on the same terms."""
    facts = [source(n, document="ab"[n % 2], passage_id=n) for n in range(20)]
    service, queue = build(topic(), facts)

    service.process_next()

    roots = [thread[0] for thread in queue.stored[0]]
    assert all(one.planned_difficulty in set(SETTINGS.difficulty_mix) for one in roots)


def test_a_topic_that_runs_out_of_passages_stops_rather_than_repeating() -> None:
    """A passage is asked about once, so a small topic yields few questions."""
    facts = [source(1, document="a", passage_id=1)]
    service, queue = build(topic(), facts)

    service.process_next()

    assert len(queue.stored[0]) == 1
    assert queue.finished == [7]


# ── Asking again ───────────────────────────────────────────────────────────


def test_a_gate_the_writer_could_have_satisfied_is_worth_asking_again() -> None:
    """A question thrown away for how it was written, not for what it is about.

    Saying what went wrong costs one call.
    """
    from question_generation.service import again

    refused = replace(
        accepted_question(),
        status="rejected",
        rejected_reason=QuestionRejection.COMPOUND,
    )

    assert again(refused) is not None


def test_an_unanswerable_question_answered_after_all_is_not_told_to_swap_parties() -> (
    None
):
    """A swapped party is the move a closed list or a general rule refutes.

    The note says what counted as an answer instead of prescribing the move
    that most often gets one.
    """
    from question_generation.service import again

    refused = replace(
        accepted_question(),
        answerable=False,
        status="rejected",
        rejected_reason=QuestionRejection.ANSWERABLE_AFTER_ALL,
    )

    note = again(refused)

    assert note is not None
    assert "party" not in note


def test_an_unanswerable_slot_is_dealt_an_atomic_fact() -> None:
    """A summary of a whole passage is the passage, and the passage answers it.

    Perturbed, the condensed fact moves a whole paragraph's worth of claims
    at once, and the move lands on one of them.
    """
    facts = [
        source(1, document="a", passage_id=1, statement="Refunds take 14 days."),
        source(
            2,
            document="a",
            passage_id=1,
            statement="The passage sets out how refunds are paid.",
            kind=FactKind.SUMMARY,
        ),
    ]
    writer = Handed()
    settings = replace(
        SETTINGS,
        per_topic=1,
        sample_size=1,
        type_mix={QuestionType.CONDITION: 1},
        unanswerable_share=1.0,
    )
    service, _ = build(topic(), facts, writer=writer, settings=settings)

    service.process_next()

    ((dealt, slot),) = writer.handed
    assert not slot.answerable
    assert [one.kind for one in dealt.facts] == [FactKind.ATOMIC]


def test_a_retry_note_shows_the_draft_it_is_about() -> None:
    """A writer told what was wrong, but not shown what it wrote, writes it again."""
    from question_generation.service import again

    refused = replace(
        accepted_question(),
        question_text="How long does a refund take?",
        target_answer="14 days",
        status="rejected",
        rejected_reason=QuestionRejection.NOT_RECOVERABLE,
    )

    note = again(refused)

    assert note is not None
    assert "How long does a refund take?" in note
    assert "14 days" in note


@pytest.mark.parametrize(
    "gate",
    [QuestionRejection.ANSWERABLE_ELSEWHERE, QuestionRejection.ANSWERABLE_AFTER_ALL],
)
def test_an_unanswerable_retry_note_reads_as_feedback_not_as_an_override(gate) -> None:
    """A retry note says what was wrong, never what the writer is "supposed" to do.

    Telling a writer what to produce whatever any document says is the
    wording a provider's prompt shield reads as a jailbreak.
    """
    from question_generation.service import again

    refused = replace(
        accepted_question(),
        answerable=False,
        target_answer=None,
        status="rejected",
        rejected_reason=gate,
    )

    note = again(refused)

    assert note is not None
    for override in ("supposed to", "no document would", "anywhere"):
        assert override not in note.lower(), note


def test_a_duplicate_is_not_worth_asking_again() -> None:
    """The same sample asked twice gives another twin of the same question."""
    from question_generation.service import again

    refused = replace(
        accepted_question(),
        status="rejected",
        rejected_reason=QuestionRejection.DUPLICATE,
    )

    assert again(refused) is None


def test_a_question_that_stood_is_left_alone() -> None:
    """Nothing to fix, and a second call would only risk the first draft."""
    from question_generation.service import again

    assert again(accepted_question()) is None


def test_an_honest_narrow_draft_is_not_asked_to_weld_facts_that_do_not_meet() -> None:
    """An accepted draft is never asked again, however narrow it came out.

    The slot asked for two passages and the dealt pair, cited whole, reaches
    its band - but the writer cited one fact, because the other has nothing
    to do with it. Asking it to cite both is asking for the weld the span
    rules forbid, and the accepted retry used to replace the honest draft.
    """
    from question_generation.service import again

    narrow = replace(
        accepted_question(band=Difficulty.EASY),
        question_type=QuestionType.APPLICATION,
        answer_form="explanation",
        planned_difficulty=Difficulty.MEDIUM,
        fact_ids=(1,),
        # Past QUESTIONS_LONG_ANSWER_CHARS, so the pair cited whole bands
        # medium and the slot's band was within reach.
        criteria=replace(accepted_question().criteria, answer_chars=72),
    )

    assert again(narrow) is None


def accepted_question(band: str = Difficulty.EASY) -> CheckedQuestion:
    """One accepted question, banded as a test asks."""
    from question_generation.models import Criteria

    return CheckedQuestion(
        question_text="How heavy is the device?",
        target_answer="4 kg",
        answerable=True,
        criteria=Criteria(
            passage_scope="single_passage",
            document_scope="single_document",
            topic_scope="single_topic",
            answer_chars=4,
            difficulty=band,
        ),
        language="en",
        status="accepted",
        rejected_reason=None,
        fact_ids=(1,),
        thread_position=1,
        question_type=QuestionType.FACTOID,
        answer_form="value",
        planned_difficulty=band,
    )


def test_the_follow_up_share_is_a_share_of_the_ACCEPTED_roots() -> None:
    """Not of the plan's slots, which is what it used to be.

    Picked over the slots, the share was decided before the question was
    written and the thread only happened where that question was then
    accepted - so what landed was the share TIMES the acceptance rate.
    """

    class EverySecondRoot(StubChecker):
        """Rejects every other ROOT, so slot number and accepted number part.

        A follow-up carries the thread it joins, which is how this tells
        the two apart without counting its own follow-up checks into the
        alternation.
        """

        def __init__(self) -> None:
            super().__init__()
            self.roots = 0

        def check(self, candidate, seen=()):
            """Accepts, then rejects, then accepts - roots only."""
            checked = super().check(candidate, seen)
            if candidate.thread:
                return checked
            self.roots += 1
            if self.roots % 2 == 0:
                return replace(checked, status="rejected", rejected_reason="malformed")
            return checked

    facts = [source(n, document="a", passage_id=n) for n in range(24)]
    settings = replace(SETTINGS, followup_share=1.0, max_followups=1)
    service, queue = build(topic(), facts, checker=EverySecondRoot(), settings=settings)

    service.process_next()

    threads = queue.stored[0]
    accepted_roots = [one for one in threads if one[0].accepted]
    followed = [one for one in threads if len(one) > 1]

    assert accepted_roots, "the fixture accepted no root to follow"
    # A share of 1.0 means EVERY accepted root, whatever the rejections
    # between them did to the slot numbering.
    assert len(followed) == len(accepted_roots)


def test_the_follow_up_share_is_a_share_of_the_answerable_roots() -> None:
    """An unanswerable root has no follow-up, so it takes no thread's place."""
    facts = [source(n, document="a", passage_id=n) for n in range(24)]
    settings = replace(
        SETTINGS,
        per_topic=8,
        unanswerable_share=0.5,
        followup_share=0.5,
        max_followups=1,
    )
    service, queue = build(topic(), facts, settings=settings)

    service.process_next()

    threads = queue.stored[0]
    answerable = [one for one in threads if one[0].accepted and one[0].answerable]
    followed = [one for one in threads if len(one) > 1]

    assert len(answerable) >= 2, "the fixture accepted too few answerable roots"
    assert len(followed) == len(answerable) // 2


# ── The credits page, which is not a subject ───────────────────────────────


def test_a_passage_of_names_is_never_asked_about() -> None:
    """The furniture the repetition reading cannot see.

    Every document thanks DIFFERENT people, so an acknowledgements section
    is identical in shape and different in words and no cross-document
    similarity reaches it. `names_parties` reads what it is made of.
    """
    credits = "Graham Bath, Judy McKay, Tauhida Parveen, Rex Black, Mike Smith"
    facts = [
        source(1, passage_id=1, passage_text=credits, language="en"),
        source(2, passage_id=2, language="en"),
    ]
    settings = replace(SETTINGS, party_density=0.25)
    service, queue = build(topic(), facts, settings=settings)

    service.process_next()

    asked = {fact for written in queue.written for fact in written.fact_ids}
    assert 1 not in asked, "a question was written about the credits page"


def test_a_density_of_zero_asks_about_every_passage() -> None:
    """Zero excludes nothing; QUESTIONS_PARTY_DENSITY ships at 0.25."""
    credits = "Graham Bath, Judy McKay, Tauhida Parveen, Rex Black, Mike Smith"
    facts = [source(1, passage_id=1, passage_text=credits, language="en")]
    service, queue = build(
        topic(), facts, settings=replace(SETTINGS, party_density=0.0)
    )

    service.process_next()

    assert queue.written, "nothing was written at all"


class RetryingWriter(StubWriter):
    """A writer that takes a retry note and says which draft it wrote."""

    def write(self, group, plan, note: str = ""):
        """The base writer, with the note recorded and the text varied."""
        written = super().write(group, plan)
        self.notes.append(note)
        return replace(
            written, question_text=f"draft {len(self.notes)}: {written.question_text}"
        )

    def __init__(self) -> None:
        """Initialises the writer with nothing asked yet."""
        super().__init__()
        self.notes: list[str] = []


class RefusesTheFirstDraft(StubChecker):
    """Refuses the first draft under a gate a retry can answer, then accepts."""

    def check(self, candidate, seen=()) -> CheckedQuestion:
        """Rejects draft one as compound, which `again` has a note for."""
        checked = super().check(candidate, seen)
        if candidate.question_text.startswith("draft 1"):
            return replace(
                checked,
                status="rejected",
                rejected_reason=QuestionRejection.COMPOUND,
            )
        return checked


def test_a_retry_is_numbered_by_the_draft_that_wrote_it() -> None:
    """And keeps that number after the best draft is moved to the end.

    `_attempt` reorders its drafts so the kept one is written last, which
    is what makes a row's position in the list stop saying which attempt
    produced it. Without the column nothing does: both drafts are stored
    and neither says whether the retry was the one that worked.
    """
    service, queue = build(
        topic(),
        [source(1, passage_id=1, language="en")],
        writer=RetryingWriter(),
        checker=RefusesTheFirstDraft(),
        settings=replace(SETTINGS, retries=1, per_topic=1, followup_share=0.0),
    )

    service.process_next()

    drafts = [
        (one.attempt, one.status)
        for one in queue.written
        if one.question_text.startswith("draft ")
    ]
    assert (1, "rejected") in drafts, "the first draft was not recorded as attempt 1"
    assert (2, "accepted") in drafts, "the retry was not recorded as attempt 2"
    # The accepted one is stored last, so position and attempt disagree -
    # which is the whole reason the column exists.
    assert drafts[-1][0] == 2


def test_a_release_spreads_over_its_own_kinds() -> None:
    """QUESTIONS_RELEASE_TYPES, where set, decides the kinds a release holds."""
    from uuid import uuid4

    from question_generation.balance import Row
    from question_generation.service import balance

    pool = [
        Row(id=at, answerable=True, difficulty=Difficulty.EASY, question_type=kind)
        for at, kind in enumerate(
            [QuestionType.FACTOID] * 30 + [QuestionType.REASON] * 30, start=1
        )
    ]

    class Catalog:
        """Offers the pool and keeps what was drawn."""

        drawn: tuple[int, ...] = ()

        def judged(self, within=None):
            return []

        def reject(self, verdicts):
            return 0

        def releasable(self, within=None):
            return pool

        def twins(self, floor):
            return []

        def release(self, ids):
            self.drawn = tuple(ids)
            return uuid4(), len(self.drawn)

    catalog = Catalog()
    balance(
        catalog,
        replace(
            SETTINGS,
            release_difficulty={Difficulty.EASY: 1},
            release_unanswerable=0.0,
            release_types={QuestionType.FACTOID: 1},
        ),
    )

    assert catalog.drawn
    assert {pool[at - 1].question_type for at in catalog.drawn} == {
        QuestionType.FACTOID
    }


def test_a_release_holds_and_reports_the_languages_its_pool_holds(caplog) -> None:
    """Unset QUESTIONS_RELEASE_LANGUAGES follows the pool: an even one, evenly.

    And the report says what came out, so a release that is mostly one
    language is visible in `make questions-balance` rather than only in a
    query afterwards.
    """
    from uuid import uuid4

    from question_generation.balance import Row
    from question_generation.service import balance

    pool = [
        Row(
            id=at,
            answerable=True,
            difficulty=Difficulty.EASY,
            question_type=QuestionType.FACTOID,
            language=language,
        )
        for at, language in enumerate(["de"] * 30 + ["en"] * 30, start=1)
    ]

    class Catalog:
        """Offers the pool and keeps what was drawn."""

        drawn: tuple[int, ...] = ()

        def judged(self, within=None):
            return []

        def reject(self, verdicts):
            return 0

        def releasable(self, within=None):
            return pool

        def twins(self, floor):
            return []

        def release(self, ids):
            self.drawn = tuple(ids)
            return uuid4(), len(self.drawn)

    catalog = Catalog()
    with caplog.at_level("INFO", logger="question_generation.service"):
        balance(
            catalog,
            replace(
                SETTINGS,
                release_size=20,
                release_difficulty={Difficulty.EASY: 1},
                release_unanswerable=0.0,
                release_types={QuestionType.FACTOID: 1},
            ),
        )

    german = sum(pool[at - 1].language == "de" for at in catalog.drawn)
    assert len(catalog.drawn) == 20
    assert german == 10
    assert any(
        "language" in line and "de 10" in line and "en 10" in line
        for line in caplog.messages
    ), caplog.messages


def _banded(counts: dict[str, int], unanswerable: int = 0):
    """Answerable factoids, this many in each band, then easy unanswerables."""
    from question_generation.balance import Row

    bands = [band for band, count in counts.items() for _ in range(count)]
    rows = [
        Row(
            id=at,
            answerable=True,
            difficulty=band,
            question_type=QuestionType.FACTOID,
            language="en",
        )
        for at, band in enumerate(bands, start=1)
    ]
    return rows + [
        Row(
            id=len(rows) + at,
            answerable=False,
            difficulty=Difficulty.EASY,
            question_type=QuestionType.FACTOID,
            language="en",
        )
        for at in range(1, unanswerable + 1)
    ]


@pytest.mark.parametrize(
    "unanswerable", [0, 50], ids=["answerable only", "with no-answer rows"]
)
def test_an_unset_band_mix_follows_the_answerable_pool(unanswerable) -> None:
    """Equal thirds drained the pool's few hard rows; its own split does not.

    Read over the answerable rows: unanswerable ones are all easy, so counted
    in they would push the easy share up by whatever share of the pool the
    writer happened to leave without an answer.
    """
    from question_generation.service import balance

    pool = _banded(
        {Difficulty.EASY: 80, Difficulty.MEDIUM: 15, Difficulty.HARD: 5}, unanswerable
    )
    catalog = _Pool(pool)

    balance(
        catalog,
        replace(
            SETTINGS,
            release_size=20,
            release_difficulty=None,
            release_unanswerable=0.0,
            release_types={QuestionType.FACTOID: 1},
        ),
    )

    drawn = [pool[at - 1].difficulty for at in catalog.drawn]
    assert len(drawn) == 20
    assert drawn.count(Difficulty.EASY) == 16
    assert drawn.count(Difficulty.MEDIUM) == 3
    assert drawn.count(Difficulty.HARD) == 1


class _Pool:
    """A catalogue offering one pool, holding no twin, and keeping what was drawn."""

    def __init__(self, pool) -> None:
        """Holds the pool; nothing drawn yet."""
        self.pool = pool
        self.drawn: tuple[int, ...] = ()

    def judged(self, within=None):
        """Nothing to re-check."""
        return []

    def reject(self, verdicts):
        """Nothing rejected."""
        return 0

    def releasable(self, within=None):
        """The pool."""
        return self.pool

    def twins(self, floor):
        """No twins."""
        return []

    def release(self, ids):
        """Keeps the draw."""
        from uuid import uuid4

        self.drawn = tuple(ids)
        return uuid4(), len(self.drawn)


def _spoken(counts: dict[str, int]):
    """Easy answerable factoids, this many in each language, one block each."""
    from question_generation.balance import Row

    languages = [language for language, count in counts.items() for _ in range(count)]
    return [
        Row(
            id=at,
            answerable=True,
            difficulty=Difficulty.EASY,
            question_type=QuestionType.FACTOID,
            language=language,
        )
        for at, language in enumerate(languages, start=1)
    ]


#: One band, one kind and no unanswerable share, so the language is the
#: only quota that can bind.
_ONE_BUCKET = {
    "release_difficulty": {Difficulty.EASY: 1},
    "release_unanswerable": 0.0,
    "release_types": {QuestionType.FACTOID: 1},
}


def test_an_unset_language_share_follows_the_pool_s_own_split() -> None:
    """A pool of 20,000 in one language and 400 in another releases about so."""
    from question_generation.service import balance

    catalog = _Pool(_spoken({"en": 20_000, "de": 400}))

    balance(catalog, replace(SETTINGS, release_size=510, **_ONE_BUCKET))

    german = sum(catalog.pool[at - 1].language == "de" for at in catalog.drawn)
    assert len(catalog.drawn) == 510
    assert abs(german - 10) <= 1, german


def test_an_unset_language_share_is_not_capped_at_twice_the_smaller_language() -> None:
    """The largest release the pool fills takes nearly all of it, not 2 x 20."""
    from question_generation.service import balance

    catalog = _Pool(_spoken({"en": 1_000, "de": 20}))

    balance(catalog, replace(SETTINGS, release_size=0, **_ONE_BUCKET))

    german = sum(catalog.pool[at - 1].language == "de" for at in catalog.drawn)
    assert len(catalog.drawn) > 900, len(catalog.drawn)
    assert abs(german - len(catalog.drawn) * 20 / 1_020) <= 1, german


def test_two_same_language_near_twins_are_not_both_released() -> None:
    """The release reads twins by the duplicate gate's own rule.

    Questions 1 and 2 rest on one fact and ask with one word, so they are
    twins. Questions 3 and 4 are as close and share only a passage, below
    QUESTIONS_DUPLICATE_COSINE, so they are two questions and both go out.
    """
    from uuid import uuid4

    from question_generation.balance import Row
    from question_generation.models import Neighbour
    from question_generation.service import balance

    pool = [
        Row(
            id=at,
            answerable=True,
            difficulty=Difficulty.EASY,
            question_type=QuestionType.FACTOID,
            language="en",
        )
        for at in range(1, 5)
    ]

    def side(at: int, similarity: float, **cited) -> Neighbour:
        return Neighbour(
            "What does the device weigh?",
            answerable=True,
            similarity=similarity,
            language="en",
            id=at,
            **cited,
        )

    class Catalog:
        """Offers the pool and two pairs, and keeps what was drawn."""

        drawn: tuple[int, ...] = ()

        def judged(self, within=None):
            return []

        def reject(self, verdicts):
            return 0

        def releasable(self, within=None):
            return pool

        def twins(self, floor):
            on_one_fact = {"fact_ids": frozenset({7}), "passage_ids": frozenset({7})}
            on_one_passage = {"fact_ids": frozenset(), "passage_ids": frozenset({8})}
            return [
                (side(1, 0.90, **on_one_fact), side(2, 0.90, **on_one_fact)),
                (side(3, 0.90, **on_one_passage), side(4, 0.90, **on_one_passage)),
            ]

        def release(self, ids):
            self.drawn = tuple(ids)
            return uuid4(), len(self.drawn)

    catalog = Catalog()
    balance(
        catalog,
        replace(
            SETTINGS,
            release_size=4,
            release_difficulty={Difficulty.EASY: 1},
            release_unanswerable=0.0,
            release_types={QuestionType.FACTOID: 1},
            duplicate_shared_cosine=0.88,
        ),
    )

    drawn = set(catalog.drawn)
    assert len(drawn & {1, 2}) == 1, drawn
    assert {3, 4} <= drawn, drawn


def test_a_pair_below_its_bar_is_not_parsed_for_its_question_words(
    monkeypatch,
) -> None:
    """The words can only raise the bar, so under the lowest one they decide nothing.

    A pair on one fact at 0.85, under the 0.88 a shared fact sets, is no twin
    whatever words it asks with; one at 0.90 is read as before.
    """
    from question_generation import gates
    from question_generation.models import Neighbour
    from question_generation.service import _twins

    read: list[str] = []
    compared = gates.asks_the_same

    def counted(first: str, second: str, language: str | None) -> bool:
        read.append(first)
        return compared(first, second, language)

    monkeypatch.setattr(gates, "asks_the_same", counted)

    def side(at: int, similarity: float) -> Neighbour:
        return Neighbour(
            f"What does device {at} weigh?",
            answerable=True,
            similarity=similarity,
            language="en",
            id=at,
            fact_ids=frozenset({7}),
            passage_ids=frozenset({7}),
        )

    class Catalog:
        def twins(self, floor):
            return [(side(1, 0.85), side(2, 0.85)), (side(3, 0.90), side(4, 0.90))]

    held = _twins(
        Catalog(),  # type: ignore[arg-type]
        replace(SETTINGS, duplicate_shared_cosine=0.88),
        _spoken({"en": 4}),
    )

    assert held == {3: {4}, 4: {3}}
    assert read == ["What does device 3 weigh?"]


def test_a_language_the_release_weighs_nothing_is_said_to_be_left_out(caplog) -> None:
    """QUESTIONS_RELEASE_LANGUAGES naming two of three leaves the third out whole.

    Which is what it says to do, and the draw says that it did, as it says
    so of a weight naming a language the pool has none of.
    """
    from uuid import uuid4

    from question_generation.balance import Row
    from question_generation.service import balance

    pool = [
        Row(
            id=at,
            answerable=True,
            difficulty=Difficulty.EASY,
            question_type=QuestionType.FACTOID,
            language=language,
        )
        for at, language in enumerate(["de"] * 10 + ["en"] * 10 + ["fr"] * 10, 1)
    ]

    class Catalog:
        """Offers the pool and keeps what was drawn."""

        drawn: tuple[int, ...] = ()

        def judged(self, within=None):
            return []

        def reject(self, verdicts):
            return 0

        def releasable(self, within=None):
            return pool

        def twins(self, floor):
            return []

        def release(self, ids):
            self.drawn = tuple(ids)
            return uuid4(), len(self.drawn)

    catalog = Catalog()
    with caplog.at_level("WARNING", logger="question_generation.service"):
        balance(
            catalog,
            replace(
                SETTINGS,
                release_size=10,
                release_difficulty={Difficulty.EASY: 1},
                release_unanswerable=0.0,
                release_types={QuestionType.FACTOID: 1},
                release_languages={"de": 1, "en": 1},
            ),
        )

    assert {pool[at - 1].language for at in catalog.drawn} == {"de", "en"}
    assert any(
        "fr" in line and "QUESTIONS_RELEASE_LANGUAGES" in line
        for line in caplog.messages
    ), caplog.messages


class EchoingWriter(RetryingWriter):
    """A writer that hands back its refused draft word for word when retried."""

    def write(self, group, plan, note: str = ""):
        """The first draft, again, whatever the note said."""
        written = super().write(group, plan, note)
        return replace(written, question_text="draft 1: Question 1?")


def test_a_retry_that_returns_the_refused_draft_unchanged_is_not_kept() -> None:
    """The same words meet the same gate: storing them twice proves nothing new."""
    writer = EchoingWriter()
    service, queue = build(
        topic(),
        [source(1, passage_id=1, language="en")],
        writer=writer,
        checker=RefusesTheFirstDraft(),
        settings=replace(SETTINGS, retries=2, per_topic=1, followup_share=0.0),
    )

    service.process_next()

    assert [(one.attempt, one.status) for one in queue.written] == [(1, "rejected")]
    assert len(writer.notes) == 2, "the retries went on after an unchanged draft"
