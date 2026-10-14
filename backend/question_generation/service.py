"""The generation flow: claim a topic, deal its facts, write, gate, store."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from typing import ClassVar

from opentelemetry.trace import Span

from confidence import Measurement, confidence
from database.qa_generator import (
    AnswerForm,
    QuestionRejection,
    QuestionStatus,
    QuestionType,
    ReviewVerdict,
)
from llm.client import ModelUnavailable
from nlp.analysis import content
from question_generation.balance import choose, composition, largest, quota_of
from question_generation.catalog import QuestionCatalog
from question_generation.checker import (
    PASSED,
    REFUSED,
    QuestionChecker,
    annotation,
    settle,
)
from question_generation.config import Settings
from question_generation.gates import (
    deciding,
    names_parties,
    near_bar,
    near_verdict,
    rivals,
    states_a_reason,
    structural,
    typed,
)
from question_generation.generation import QuestionWriter
from question_generation.models import (
    Candidate,
    CheckedQuestion,
    Criteria,
    FactGroup,
    JudgedQuestion,
    SourceFact,
    TopicToCover,
    Unanswered,
    criteria_of,
)
from question_generation.planning import Plan, instead, plans
from question_generation.queue import QuestionQueue
from question_generation.runs import ACCEPTED
from question_generation.selection import Deal, spread
from question_generation.types import PROMPT_VERSION, SPECS, spec
from question_generation.verifier import Verifier
from settings.runs import run_id
from stages import StageService
from telemetry import tracer, working
from telemetry.evaluations import Evaluations, Verdict, current_ids

log = logging.getLogger(__name__)
span = tracer(__name__)

#: How many re-checked questions to write at once.
_RECHECK_BATCH = 500

#: More refusals in a row than a filter's few neighbouring ids, so a dead model stops.
_GIVE_UP = 5

#: What to tell the writer about a draft a gate refused, by the gate that
#: refused it. Only the gates a second attempt can do anything about are
#: here: each of these is the writer having written the question badly
#: rather than the material not supporting one, and saying what went wrong
#: is worth one more call. `duplicate` is deliberately absent - the same
#: sample asked again produces another near-twin of the same question.
_NOTES: dict[str, str] = {
    QuestionRejection.MALFORMED: (
        "it was not one well-formed question. Write exactly one, ending in a "
        "single question mark, with the answer in the field for it."
    ),
    QuestionRejection.COMPOUND: (
        "it asked two things joined by 'and', so a chatbot answering half of "
        "it would be neither right nor wrong. Ask ONE thing. If the facts "
        "have no single question between them, ask about one fact alone and "
        "cite only that one."
    ),
    QuestionRejection.WRONG_FORM: (
        "the answer was not the shape this kind of question asks for. Read "
        "the answer rule again and write an answer of that shape."
    ),
    QuestionRejection.ANSWER_TOO_SHORT: (
        "the answer was too short to score anything against. Ask a question "
        "whose answer the material states in full."
    ),
    QuestionRejection.ANSWER_TOO_LONG: (
        "the answer ran far past the length this kind of question allows. "
        "Ask something narrower, with a shorter answer."
    ),
    QuestionRejection.LEAKS_SOURCE: (
        "it said WHERE the answer is - it named or quoted a document, a "
        "section or a heading. Name the subject instead: the thing, the "
        "party, the duty, the period."
    ),
    QuestionRejection.UNANCHORED: (
        "it named nothing a person searching would know to type. Name the "
        "subject in the question itself, so somebody who has not read the "
        "passage could have asked it."
    ),
    QuestionRejection.NOT_RECOVERABLE: (
        "a second reader could not get your answer back out of the passages. "
        "Ask about something the facts state plainly, and write the answer "
        "in the words of the material."
    ),
    QuestionRejection.OFF_TOPIC: (
        "it was about something this material never mentions, so any chatbot "
        "declines it and declining it proves nothing. Stay on the subject of "
        "the fact and move one detail of it out of reach."
    ),
    QuestionRejection.ANSWERABLE_AFTER_ALL: (
        "the passages answered it, and this question is supposed to have no "
        "answer. A passage answers it when it states the answer, contradicts "
        "its premise, or settles it by a closed list or a general rule. Ask "
        "for a detail of this subject that none of them settles."
    ),
    QuestionRejection.ANSWERABLE_ELSEWHERE: (
        "another part of the corpus answers it, and this question is "
        "supposed to have no answer anywhere. Ask for a detail of this "
        "subject that no document would carry."
    ),
}


def reverify(catalog: QuestionCatalog, settings: Settings, within=None) -> int:
    """Puts every stored question through the gates that need no model.

    The counterpart of `extract-revalidate`, and the same bargain: what the
    model wrote is the record of one generation and is kept, and only the
    verdict is replaced. The round trip is left out because it is the one
    gate that costs a call. What runs is what catches a change underneath a
    stored question - a fact re-judged and now rejected, a fact a person
    rejected in review, a citation deleted
    by a re-extraction, a duplicate written by a later run - and the type
    rules, so a rule added to them reaches the rows already stored.

    It only ever rejects. Accepting is a person's, and a re-check that
    un-rejected would quietly overturn somebody's decision on its next run.
    A question a person accepted is rejected only when a fact it rests on no
    longer holds; no other gate here overrules the person. A question a
    person rejected stays rejected.
    """
    verdicts: list[tuple[int, str]] = []
    written = 0

    def flush() -> None:
        """Writes what has piled up."""
        nonlocal written
        written += catalog.reject(verdicts)
        verdicts.clear()

    # ponytail: one HNSW probe per question. Upgrade: one lateral-join probe
    # per batch.
    for question in catalog.judged(within):
        if question.status == QuestionStatus.REJECTED:
            continue
        # What this pass has decided to reject and not yet written. Held out
        # of the duplicate probe, which reads the stored status and would
        # otherwise answer differently either side of a flush.
        pending = [question_id for question_id, _ in verdicts]
        failed = _recheck(catalog, settings, question, pending)
        if failed:
            code, reason = failed
            log.info("rejecting question %d: %s (%s)", question.id, reason, code)
            verdicts.append((question.id, code))
        if len(verdicts) >= _RECHECK_BATCH:
            flush()
    flush()
    log.info("re-checked and rejected %d question(s)", written)
    return written


def rescore(catalog: QuestionCatalog, settings: Settings, within=None) -> int:
    """Rewrites every stored question's scopes and band from what it cites now.

    No model is called. A question stores the criteria its facts made when it
    was written, and a fact that loses a citation - `make extract-dedup` takes
    out the ones a duplicate refusal folded in - leaves them describing
    evidence the question no longer has: a one-passage lookup banded as if it
    combined two. `reverify` rejects such a row as `source_changed`, so this
    runs first, reading the criteria as `reverify` reads them, through
    `criteria_of`, which is what `FactGroup.criteria` bands a new question
    with. Only the four columns move; the verdict is `reverify`'s.

    Every question, a rejected one included: the columns describe the row,
    whatever became of it. Bar one citing a fact that rests only on a fold,
    its own citation gone: its spread counts a passage the fact was only
    refused against, so the stored scope is left for `reverify` to compare.

    Args:
        catalog: Where the questions are read from and written back to.
        settings: The answer length a long answer is read against.
        within: A condition narrowing which questions are read, or None.

    Returns:
        How many questions were rewritten.
    """
    moved: list[tuple[int, Criteria]] = []
    for question in catalog.judged(within):
        if question.stranded:
            continue
        now = _cited(question, settings)
        if (
            question.passage_scope,
            question.document_scope,
            question.topic_scope,
            question.difficulty,
        ) != (now.passage_scope, now.document_scope, now.topic_scope, now.difficulty):
            moved.append((question.id, now))
    written = catalog.rescore(moved)
    log.info("rescored %d question(s) from what they cite now", written)
    return written


def _cited(question: JudgedQuestion, settings: Settings) -> Criteria:
    """The criteria a stored question's facts make today, read off its row."""
    return criteria_of(
        passages=question.passages,
        documents=question.documents,
        topics=question.topics,
        answer_chars=len(question.target_answer or "") or None,
        follows=question.follows_id is not None,
        long_answer=settings.long_answer_chars,
    )


def _recheck(
    catalog: QuestionCatalog,
    settings: Settings,
    question: JudgedQuestion,
    pending: Sequence[int] = (),
) -> tuple[str, str] | None:
    """Says why a stored question no longer holds, or None if it still does.

    `pending` is what this pass has already rejected and not yet written,
    which the duplicate probe must not offer back as an accepted twin.

    A question a person accepted is judged on its facts alone: no rule gate
    after that check overrules the person.
    """
    if not question.facts_validated:
        return (
            QuestionRejection.SOURCE_CHANGED,
            (
                "a fact this question rests on no longer passes its own checks, "
                "or a person rejected it"
            ),
        )
    if question.reviewed_verdict == ReviewVerdict.ACCEPTED:
        return None

    # A cross-document question that lost a citation is still a question and
    # is not deleted: the trigger takes one only when its last fact goes. It
    # is a question whose stored scopes stopped being true, which is a
    # quieter kind of wrong and so worth naming. Compared on the scopes and
    # not on the band, because two different spreads can land in one band
    # and the scopes are what a reader filters on. Not on the topic scope,
    # which a refit moves with no fact or citation changing.
    now = _cited(question, settings)
    moved = [
        f"{name} was {was} and is now {is_now}"
        for name, was, is_now in (
            ("passage_scope", question.passage_scope, now.passage_scope),
            ("document_scope", question.document_scope, now.document_scope),
        )
        if was and was != is_now
    ]
    if moved:
        return QuestionRejection.SOURCE_CHANGED, "; ".join(moved)

    failed, _ = structural(
        question_text=question.question_text,
        target_answer=question.target_answer,
        answerable=question.answerable,
        language=question.language,
        statements=question.statements,
        # The form the row was written under, not the ones its type will
        # take today: a type whose answer forms changed under a stored
        # question would otherwise re-judge every question written before
        # the change, and a re-check that moves a verdict for that reason
        # is measuring the settings rather than the row.
        forms=(question.answer_form or spec(question.question_type).form,),
        bounds=settings.answer_chars,
    )
    if failed:
        return failed

    if question.question_type is not None:
        failed = typed(
            question.question_text,
            question.target_answer,
            question.answerable,
            question.question_type,
            question.language,
        )
        if failed:
            return failed

    if question.embedding is None:
        return None
    probed = {
        "answerable": question.answerable,
        "threshold": settings.duplicate_cosine,
        "shared_threshold": settings.duplicate_shared_cosine,
        "question": question.question_text,
        "language": question.language,
        "passages": question.passage_ids,
        "facts": question.fact_ids,
    }
    # One probe per kind of question that can refuse this one, as the
    # checker probes: see `gates.rivals`. Earlier questions only among its
    # own kind, which is what keeps one of two duplicates rather than
    # neither; an answered question on its fact answers it whenever it was
    # written.
    found = deciding(
        [
            catalog.nearest(
                question.embedding,
                before=question.id if answerable == question.answerable else None,
                excluding=pending,
                language=question.language,
                answerable=answerable,
            )
            for answerable in rivals(question.answerable)
        ],
        **probed,
    )
    return near_verdict(found[0] if found else None, **probed)


def balance(catalog: QuestionCatalog, settings: Settings, within=None) -> int:
    """Draws a balanced release out of everything the run accepted.

    Args:
        catalog: Where the accepted questions are read and the draw written.
        settings: The shares the release is held to.
        within: A condition narrowing which questions may be drawn, or None.

    Re-verifies first, so the draw reads rows that pass today's gates, or
    that a person accepted and whose facts still hold.

    Returns:
        How many questions were drawn into the release.
    """
    reverify(catalog, settings, within)
    pool = catalog.releasable(within)
    if not pool:
        log.warning("no accepted question carries both a difficulty and a type")
        return 0

    bands = _supplied(pool, settings.release_difficulty, "band", "difficulty")
    types = _supplied(
        pool, settings.release_types or settings.type_mix, "kind", "question_type"
    )
    # Unset follows the pool's own language split, so a corpus mostly in one
    # language releases in proportion rather than at a multiple of its
    # smallest, and a third language is held to its share without anybody
    # naming it.
    languages = _supplied(
        pool,
        settings.release_languages or dict(Counter(row.language for row in pool)),
        "language",
        "language",
    )
    # The other way round from `_supplied`'s warning: a language the pool
    # holds and the setting gives no weight is left out whole, which is
    # what the setting asks for and worth saying all the same.
    unweighted = sorted({row.language for row in pool} - set(languages))
    if settings.release_languages and unweighted:
        log.warning(
            "the pool holds questions in %s, which QUESTIONS_RELEASE_LANGUAGES "
            "gives no weight, so the release holds none of %s.",
            ", ".join(unweighted),
            "them" if len(unweighted) > 1 else "it",
        )
    if not bands or not types or not languages:
        log.warning("nothing accepted can fill any quota; no release was drawn")
        catalog.release([])
        return 0
    twins = _twins(catalog, settings, pool)

    if settings.release_size:
        release = choose(
            pool,
            quota_of(
                settings.release_size,
                bands,
                types,
                settings.release_unanswerable,
                languages,
            ),
            twins,
        )
    else:
        release = largest(
            pool,
            bands,
            types,
            settings.release_unanswerable,
            languages=languages,
            twins=twins,
        )

    drawn, written = catalog.release(release.ids)
    _report(pool, release, drawn, written)
    return written


def _twins(catalog: QuestionCatalog, settings: Settings, pool) -> dict[int, set[int]]:
    """Which accepted questions the release may hold only one of.

    The duplicate gate's own rule, read over each question's few nearest
    rather than over the one neighbour the gate probed: a twin behind a
    closer question that is not one got past it.
    """
    shared = settings.duplicate_shared_cosine
    floor = (
        settings.duplicate_cosine
        if shared is None
        else min(shared, settings.duplicate_cosine)
    )
    offered = {row.id for row in pool}
    held: dict[int, set[int]] = {}
    for first, second in catalog.twins(floor):
        if first.id is None or second.id is None:
            continue
        if first.id not in offered or second.id not in offered:
            continue
        probed = {
            "answerable": first.answerable,
            "threshold": settings.duplicate_cosine,
            "shared_threshold": shared,
            "language": first.language,
            "passages": tuple(first.passage_ids),
            "facts": tuple(first.fact_ids),
        }
        # The bar before the question words are read, which can only raise
        # it: a pair already under it is no twin, so it is not parsed.
        bar = near_bar(second, **probed)
        if bar is None or second.similarity < bar:
            continue
        bar = near_bar(second, question=first.question_text, **probed)
        if bar is not None and second.similarity >= bar:
            held.setdefault(first.id, set()).add(second.id)
            held.setdefault(second.id, set()).add(first.id)
    if held:
        log.info(
            "%d accepted question(s) have a twin in the pool; the release holds "
            "one of each",
            len(held),
        )
    return held


def _supplied(pool, weights, what: str, attribute: str) -> dict[str, int]:
    """The weights narrowed to the buckets this pool can actually supply.

    A quota nothing can fill makes the whole draw empty rather than smaller:
    the choosing needs every bucket at zero together, so one bucket with no
    questions in it refuses every size, down to one.

    Dropping the bucket is the lesser wrong, and it is said out loud. What
    the release then holds is reported off the rows either way, so a missing
    kind or a missing band shows up in the composition rather than being
    promised and quietly not delivered.
    """
    present = {getattr(row, attribute) for row in pool}
    kept = {
        name: weight
        for name, weight in weights.items()
        if weight > 0 and name in present
    }
    dropped = [
        name for name, weight in weights.items() if weight > 0 and name not in present
    ]
    if dropped:
        log.warning(
            "no accepted question is of %s %s, so the release has no quota for "
            "%s. Generate more, or accept a set without %s.",
            what,
            ", ".join(sorted(dropped)),
            "them" if len(dropped) > 1 else "it",
            "them" if len(dropped) > 1 else "it",
        )
    return kept


def _report(pool, release, drawn, written: int) -> None:
    """Logs what the draw came out as, and what it could not fill."""
    log.info(
        "release %s: %d of %d accepted question(s), a yield of %.0f%%",
        drawn,
        written,
        len(pool),
        100.0 * written / len(pool),
    )
    for name, counted in composition(pool, release.ids).items():
        log.info(
            "  %-11s %s",
            name,
            ", ".join(
                f"{key} {value} ({100.0 * value / max(written, 1):.0f}%)"
                for key, value in sorted(counted.items())
            ),
        )
    if release.short:
        log.warning(
            "the pool could not fill: %s. Generate more, or lower the share "
            "that is short.",
            ", ".join(
                f"{name} short by {count}" for name, count in release.short.items()
            ),
        )


def rejudge(
    catalog: QuestionCatalog, settings: Settings, verifier: Verifier, within=None
) -> int:
    """Asks again whether the passages settle each accepted unanswerable question.

    The one re-check that costs a call, which is why it is not part of
    `reverify`. Each of these was accepted when the verifier, asked for an
    answer stated outright, found none; `Verifier.settles` asks whether its
    passages refute its premise or cover its case with a list or a rule as
    well - over the passages it cites, then over the corpus probe the
    checker reads.

    It only ever rejects, as `reverify` does, and a released question goes
    with the rest: one the material answers marks a correct chatbot wrong.
    A question a person accepted is left alone, for the reason `_recheck`
    gives, and so is one a person decides while the run is asking about it:
    `opine` reads the row again before it rejects.

    Each verdict is written to the row's `gate_scores` as it is reached,
    kept or rejected, and in one write with the rejection it decides. A
    question already carrying a `settles` verdict - from an earlier run, or
    from the checker since it asks the same - is not asked again. So a
    second run, or one after an interruption, pays only for what no run has
    judged.

    A question the model will not answer about - a passage a content filter
    always refuses - is logged and counted, and written nothing, so the run
    goes on past it and the next run asks it again. `_GIVE_UP` of them in a
    row is a model that answers nothing - the client raises the same for a
    refused key or an unknown model - and the run stops on the last error.

    Returns:
        How many questions were rejected.

    Raises:
        ModelUnavailable: If the verifier refused `_GIVE_UP` questions in a
            row.
    """
    written = 0
    unanswered = 0
    in_a_row = 0
    for question in catalog.unanswered(within):
        if question.reviewed_verdict == ReviewVerdict.ACCEPTED or question.judged:
            continue
        try:
            failed, opinions = _settled(catalog, settings, verifier, question)
        except ModelUnavailable as exc:
            log.warning(
                "left question %d unjudged: the verifier would not answer (%s)",
                question.id,
                exc,
            )
            unanswered += 1
            in_a_row += 1
            if in_a_row >= _GIVE_UP:
                raise
            continue
        in_a_row = 0
        code, reason = failed or (None, "")
        if code:
            log.info("rejecting question %d: %s (%s)", question.id, reason, code)
        # The verdicts and the rejection they decide in one write: apart, a
        # run dying between them left a settled row accepted and judged.
        if catalog.opine(question.id, opinions, rejected=code):
            written += 1
    log.info(
        "re-judged and rejected %d question(s), and left %d the model would not "
        "answer about to the next run",
        written,
        unanswered,
    )
    return written


def _settled(
    catalog: QuestionCatalog,
    settings: Settings,
    verifier: Verifier,
    question: Unanswered,
) -> tuple[tuple[str, str] | None, list[Measurement]]:
    """Why the material answers a question written to have none, or None.

    Beside it, the verdicts that decided it, as the row keeps them. Read as
    the checker reads it, by `settle`, over the probe the checker reads.
    """

    def probe() -> Sequence[str]:
        """The passages it does not cite, as the checker probes for them."""
        return catalog.elsewhere(
            sorted(content(question.question_text, question.language)),
            question.language,
            question.passage_ids,
            settings.elsewhere_passages,
            question.embedding,
        )

    return settle(
        verifier,
        question.question_text,
        question.language,
        question.passages,
        probe if settings.elsewhere_passages > 0 else None,
        question.id,
    )


def again(checked: CheckedQuestion) -> str | None:
    """What to tell the writer about this draft, or None to keep it as it is.

    Only a gate refusing it, and only a gate the writer could have satisfied.

    An accepted draft that came out below its band is left alone. Asking it
    to cite every passage it was offered is asking for the weld the span
    rules forbid: the writer narrowed because the facts did not meet, and a
    second draft citing them all was accepted in its place.
    """
    return _NOTES.get(checked.rejected_reason or "")


class QuestionGenerationService(StageService):
    """Writes one topic's questions, one topic at a time.

    The unit of work is a topic because a question's subject is one: the
    facts it may be written from are the ones whose passage has this topic as
    its strongest, and a group spanning two of that topic's documents is what
    makes a cross-document question. A topic yielding nothing is not a
    failure, and neither is a question a gate rejected - that one is stored
    with the gate's name, because the share that fails is how the writer is
    judged.
    """

    name: ClassVar[str] = "question_generation"
    unit: ClassVar[str] = "topic"

    def __init__(
        self,
        *,
        repository: QuestionQueue,
        writer: QuestionWriter,
        checker: QuestionChecker,
        settings: Settings,
    ) -> None:
        """Initialises the service with its collaborators."""
        super().__init__(repository)
        self._repository: QuestionQueue = repository
        self._writer = writer
        self._checker = checker
        self._settings = settings
        # Held for the life of the service rather than per topic: the
        # client is one HTTP connection and the batch spans topics, so a
        # topic writing nine questions does not cost a call of its own.
        self._evaluations = Evaluations()
        #: Whether each fact read so far says why, by fact id. A parse per
        #: fact, and the deal asks again for every `reason` slot.
        self._reasons: dict[int, bool] = {}

    def process_next(self) -> int | None:
        """Writes the questions for one queued topic and stores them."""
        topic = self._repository.claim()
        if topic is None:
            return None

        with working(
            span,
            "generate_questions",
            {
                "stage": self.name,
                "topic.id": topic.id,
                "topic.label": topic.label or "",
            },
        ) as current:
            try:
                threads = self._topic(topic, current)
                stored = self._repository.store(topic.id, threads)
                written = [one for thread in threads for one in thread]
                accepted = sum(1 for one in written if one.accepted)
                followups = sum(1 for one in written if one.follows)
                self._done(current)
                # Whatever is under the batch size, now that the topic is
                # finished. Without it the last topic of every run is the
                # one missing from Phoenix.
                self._evaluations.flush()
                current.set_attribute("questions.written", stored)
                current.set_attribute("questions.accepted", accepted)
                current.set_attribute("questions.followups", followups)
                log.info(
                    "topic %d: %d question(s) in %d thread(s), %d accepted "
                    "(%d rejected), %d follow-up(s)",
                    topic.id,
                    stored,
                    len(threads),
                    accepted,
                    stored - accepted,
                    followups,
                    extra={
                        "questions.written": stored,
                        "questions.threads": len(threads),
                        "questions.accepted": accepted,
                        "questions.rejected": stored - accepted,
                        "questions.followups": followups,
                    },
                )
            except Exception as exc:
                self._fail(topic.id, f"{type(exc).__name__}: {exc}", current)
                log.exception("failed topic %d", topic.id)
        return topic.id

    def _topic(self, topic: TopicToCover, current: Span) -> list[list[CheckedQuestion]]:
        """Writes and gates every question one topic is still missing.

        The plan comes first and the material second. Each slot says what kind
        of question to write and how wide a sample that needs; the deal
        supplies the widest sample the topic can actually offer, and the
        question is written to whatever came back. A topic sitting in one
        document has no cross-document question in it, and asking for one is
        not a reason to write nothing about that topic.
        """
        if not topic.include_in_coverage:
            # Finished with nothing written, not left `new`: somebody said
            # this topic is not a subject, which is an answer and not work
            # still to do. A queue that never empties says nothing.
            current.set_attribute("questions.skipped", "not in coverage")
            return []

        facts = self._subjects(self._repository.facts(topic.id))
        if not facts:
            current.set_attribute("questions.skipped", "no facts left to ask about")
            return []

        deal = Deal(
            facts,
            self._subjects(self._repository.bridging(topic.id)),
            wanted=self._settings.per_topic,
            size=self._settings.sample_size,
            rounds=self._settings.samples_per_passage,
            floor=self._settings.meets_floor,
        )
        planned = plans(
            wanted=self._settings.per_topic,
            types=self._settings.type_mix,
            bands=self._settings.difficulty_mix,
            unanswerable_share=self._settings.unanswerable_share,
        )

        threads: list[list[CheckedQuestion]] = []
        accepted: list[CheckedQuestion] = []
        written = 0
        followed = 0
        #: Accepted answerable roots so far, which is what the follow-up
        #: share is a share OF. Counted here rather than taken from `accepted`, which
        #: a follow-up joins as soon as it is kept.
        roots = 0
        swapped = 0
        for plan in planned:
            prefer = None
            if plan.answerable and plan.spec.name == QuestionType.REASON:
                # Only material that says why can answer a why: dealt a
                # rule, the writer returns the rule restated or a reason it
                # invented, and no gate tells either from a sound one. Where
                # nothing left states one, the slot is swapped, as an
                # unanswerable one is in the plan.
                if deal.holds(self._reasoned):
                    prefer = self._reasoned
                else:
                    other = instead(plan, self._settings.type_mix, swapped)
                    swapped += 1
                    if other is None:
                        log.warning(
                            "topic %d: a %s slot was not written: nothing left "
                            "in the topic states a reason, and "
                            "QUESTIONS_TYPE_MIX has no other kind that does not "
                            "span to write instead",
                            topic.id,
                            plan.spec.name,
                            extra={"topic.id": topic.id},
                        )
                        continue
                    log.info(
                        "topic %d: a %s slot is written as %s: nothing left in "
                        "the topic states a reason",
                        topic.id,
                        plan.spec.name,
                        other.spec.name,
                        extra={"topic.id": topic.id},
                    )
                    plan = other
            # A reading is written from a passage condensed, a value from
            # the claim carrying the number. Which facts are offered first
            # follows from that, and it is what the weld responds to. An
            # unanswerable one is moved out of reach of one claim: a summary
            # perturbed is a whole passage moved at once, and the move lands
            # on one of the claims it holds.
            sample = deal.sample(
                plan.shape,
                condensed=plan.answerable and plan.spec.form != AnswerForm.VALUE,
                prefer=prefer,
            )
            if sample is None:
                # The topic ran out of passages before the plan ran out of
                # slots. Everything it had has been asked about once.
                break
            written += 1
            drafts = self._attempt(sample, plan, accepted)
            # Every draft but the kept one goes in on its own, not as a turn
            # of the thread: a thread links each row to the one before it,
            # and a discarded attempt is drop-rate evidence rather than a
            # question somebody asked next.
            threads.extend([one] for one in drafts[:-1])
            checked = drafts[-1]
            thread = [checked]
            if checked.accepted:
                accepted.append(checked)
                # Spread over the accepted roots rather than over the plan's
                # slots. Over the slots the share was picked before the
                # question was written, so what landed was this share TIMES
                # the acceptance rate. A setting whose value moves with an
                # unrelated rate cannot be reasoned about, and both the
                # catalogue and the README already said it meant this.
                # Answerable roots only: an unanswerable one has no thread.
                if checked.answerable:
                    if spread(roots, self._settings.followup_share):
                        thread += self._followups(
                            deal.widen(sample),
                            plan,
                            checked,
                            accepted,
                            followed,
                            topic.id,
                        )
                        followed += 1
                    roots += 1
            threads.append(thread)
        current.set_attribute("questions.samples", written)
        return threads

    def _subjects(self, facts: list[SourceFact]) -> list[SourceFact]:
        """The facts whose passage is about a subject rather than about people.

        The credits page, which the repetition reading cannot see: every
        document thanks DIFFERENT people, so the section is identical in
        shape and different in words. `names_parties` reads what it is made
        of instead.

        Here and not in the queue, because it needs a tagger and a
        catalogue the api holds must not import the module that loads one.
        Read once per distinct passage rather than once per fact: the
        reading is the same for all of a passage's facts.
        """
        if self._settings.party_density <= 0:
            return facts
        seen: dict[int, bool] = {}
        kept = []
        for fact in facts:
            anchor = fact.anchor
            if anchor.id not in seen:
                seen[anchor.id] = names_parties(
                    anchor.text, anchor.language, self._settings.party_density
                )
            if not seen[anchor.id]:
                kept.append(fact)
        return kept

    def _reasoned(self, fact: SourceFact) -> bool:
        """Whether this fact's evidence says why, or its language cannot say.

        The evidence rather than the statement, which may have condensed the
        clause away. A language `states_a_reason` has no markers for counts,
        so its `reason` slots are dealt as they always were.
        """
        if fact.id not in self._reasons:
            self._reasons[fact.id] = (
                states_a_reason(fact.evidence or fact.statement, fact.language)
                is not False
            )
        return self._reasons[fact.id]

    def _checked(
        self, candidate: Candidate, accepted: list[CheckedQuestion]
    ) -> CheckedQuestion:
        """Puts one candidate through the gates, inside a span of its own.

        The verdict was in two places and neither could be queried: a column
        in Postgres, and a line in the log. Postgres answers how many of
        each gate fired - `question_generation.runs` is that query - and it
        cannot answer what a gate COST, because the calls, the tokens and
        the latency are in the spans.

        A span per question is what joins the two. The model calls this
        check makes are its children, so a run's `leaks_source` rejections
        carry the price of the calls they wasted, and Phoenix groups on the
        attributes below without anything being logged twice.

        Cheap: a question costs one to three model calls, each already a
        span, so this adds a third of what is there rather than doubling it.

        The verdict is recorded TWICE and the two are not redundant. An
        attribute is what a span is filtered and grouped by; an annotation
        is what Phoenix shows in its Evaluations view, with a label, a
        score and the reason, comparable across two projects without a
        query. Phoenix does not know an arbitrary attribute is a
        judgement, and the annotation cannot be filtered on in the trace
        view, so each does the half the other cannot.
        """
        with span.start_as_current_span("check_question") as current:
            checked = self._checker.check(candidate, accepted)
            current.set_attribute("run.id", run_id())
            # The gate that stopped it, or `accepted`. One attribute rather
            # than a boolean and a nullable code, because what every query
            # here groups on is "what became of it".
            current.set_attribute("question.gate", checked.rejected_reason or ACCEPTED)
            # And every gate that READ it, in order. The line above says
            # what stopped a question and can never say what it got past,
            # because the checker returns on the first failure - so a
            # question refused at the round trip and one refused at the
            # first rule were indistinguishable in how far they got.
            current.set_attribute("question.gates_ran", list(checked.gates_ran))
            # And the judgements that could not be had, which is the one
            # thing `gates_ran` cannot say: a gate that ran and abstained is
            # in both lists, and a question accepted with this non-empty
            # cleared a gate nobody actually ran.
            if checked.gates_abstained:
                current.set_attribute(
                    "question.gates_abstained", list(checked.gates_abstained)
                )
                log.warning(
                    "%r was judged without %s: the model would not answer, so it "
                    "is accepted on gates that did not run. `make "
                    "questions-reverify` re-reads the free gates; these are not "
                    "among them, so re-run the stage to have them asked again.",
                    checked.question_text,
                    ", ".join(checked.gates_abstained),
                )
            current.set_attribute("question.accepted", checked.accepted)
            # What the measuring gates read, so a trace can be filtered to
            # the questions that only just survived one. Per gate as well as
            # the aggregate: a Grafana panel charts one of these and a
            # person reading a trace wants the other.
            for one in checked.readings:
                current.set_attribute(f"question.score.{one.gate}", one.value)
            if (margin := confidence(checked.readings)) is not None:
                current.set_attribute("question.confidence", margin)
            current.set_attribute("question.answerable", checked.answerable)
            current.set_attribute("question.language", checked.language)
            current.set_attribute("question.follows", checked.follows)
            for name, value in (
                ("question.type", checked.question_type),
                ("question.form", checked.answer_form),
                ("question.difficulty", checked.criteria.difficulty),
                ("question.planned_difficulty", checked.planned_difficulty),
                ("question.cognitive_level", checked.cognitive_level),
            ):
                if value:
                    current.set_attribute(name, value)

            # On the ROW as well, which is the only durable end of the
            # link: the span is written now and aged out by Phoenix's own
            # retention, and the question is append-only and never
            # hard-deleted. Without them nothing joins the two - a span
            # carries no question id, because the question has none yet
            # when this runs.
            trace_id, span_id = current_ids()
            checked = replace(checked, trace_id=trace_id, span_id=span_id)

            # And as an annotation, which is the Evaluations view. CODE and
            # not LLM, the phrasing judgements included. The score is 1 or 0,
            # so a project's mean over this annotation IS its acceptance
            # rate.
            if span_id:
                self._evaluations.record(*self._verdicts(span_id, checked))
            return checked

    def _verdicts(self, span_id: str, checked: CheckedQuestion) -> list[Verdict]:
        """One verdict for the question, and one for each gate that read it.

        The summary says what became of it. The per-gate ones are what
        make the Evaluations view a table of the pipeline rather than one
        column: each gate is its own annotation, so its mean over a
        project IS its pass rate, and two runs compare gate by gate
        without a query.

        Only the gates that RAN. A question refused at `structural` never
        reached the round trip, and scoring it there as passed or failed
        would both be untrue - the absence is the fact. Which is also why
        the count is not fixed: a gate's mean is over the questions that
        reached it.

        The last gate that ran is the one that refused it, if anything
        did. That is what `check` guarantees by returning on the first
        failure, and it is the only reason a code can be turned back into
        a gate.
        """
        about = {
            "run_id": run_id(),
            "language": checked.language,
            "answerable": checked.answerable,
            "question_type": checked.question_type or "",
            "prompt_version": PROMPT_VERSION,
        }
        verdicts = [
            Verdict(
                span_id=span_id,
                name="gate",
                label=checked.rejected_reason or ACCEPTED,
                score=float(checked.accepted),
                explanation=self._why(checked),
                metadata=about | {"gates_ran": ",".join(checked.gates_ran)},
            )
        ]
        read = {one.gate: one for one in checked.readings}
        for position, gate in enumerate(checked.gates_ran, 1):
            stopped = not checked.accepted and gate == checked.gates_ran[-1]
            # Beside the pass or refuse, never instead of it: a Phoenix mean
            # over one of these annotations is the gate's pass rate, and
            # scoring the margin here would silently redefine every chart
            # already drawn on one.
            measured = read.get(gate)
            verdicts.append(
                Verdict(
                    span_id=span_id,
                    name=annotation(gate),
                    label=REFUSED if stopped else PASSED,
                    score=0.0 if stopped else 1.0,
                    # Only where it refused. A gate that let a question
                    # through has no reason to give, and the question's
                    # own text under every gate it passed is six copies
                    # of one string.
                    explanation=self._why(checked) if stopped else "",
                    metadata=about
                    | {"position": position}
                    | (measured.recorded() if measured else {}),
                )
            )
        # One more, so the Evaluations view can sort a project by what only
        # just survived. Absent where nothing measured anything, rather
        # than scored zero - see `confidence.py`.
        if (margin := confidence(checked.readings)) is not None:
            verdicts.append(
                Verdict(
                    span_id=span_id,
                    name="confidence",
                    label=checked.rejected_reason or ACCEPTED,
                    score=margin,
                    explanation="",
                    metadata=about,
                )
            )
        return verdicts

    @staticmethod
    def _why(checked: CheckedQuestion) -> str:
        """What to show a reader beside the verdict.

        The question itself for an accepted one - there is no reason to
        give, and a blank explanation column is worse than the thing it
        was reached about. The gate's own wording is not carried on
        `CheckedQuestion`: it is logged where it is decided and stored as
        a code, and re-deriving it here would be a second copy of every
        gate's sentence.
        """
        if checked.accepted:
            return checked.question_text
        return f"{checked.rejected_reason}: {checked.question_text}"

    def _attempt(
        self, sample: FactGroup, plan: Plan, accepted: list[CheckedQuestion]
    ) -> list[CheckedQuestion]:
        """Writes one question, and writes it again when a gate can be answered.

        Returns every draft with the one to keep last. All of them are
        stored: a draft a gate refused is the same drop-rate evidence as any
        other refusal, and quietly dropping it would make the writer look
        better than it is while hiding what the retry cost.

        A retry can only improve the outcome. Only a refused draft is asked
        again, so the drafts before the last were all refused, and the last
        is the one kept, accepted or not.
        """
        # Checked against what this run has accepted as well as what the
        # database holds: nothing is stored until the topic is finished, so
        # without it a topic would happily write the same question twice.
        drafts = [self._checked(self._writer.write(sample, plan), accepted)]
        for _ in range(self._settings.retries):
            note = again(drafts[-1])
            if note is None:
                break
            log.info("asking again for %r: %s", drafts[-1].question_text, note)
            # Numbered as it is written, so a stored row says which attempt
            # produced it.
            drafts.append(
                replace(
                    self._checked(self._writer.write(sample, plan, note), accepted),
                    attempt=len(drafts) + 1,
                )
            )
        return drafts

    def _followups(
        self,
        sample: FactGroup,
        plan: Plan,
        root: CheckedQuestion,
        accepted: list[CheckedQuestion],
        followed: int,
        topic_id: int,
    ) -> list[CheckedQuestion]:
        """Writes the questions somebody would ask after this one.

        Each turn takes the next type in QUESTIONS_FOLLOWUP_TYPES, so a thread
        moves from a value to the circumstances it applies in to the reason
        behind it rather than asking the same kind of thing three times.

        The cycle starts where this thread sits among the followed ones, not
        at zero. Starting every thread at the first type means a run never
        reaches past QUESTIONS_MAX_FOLLOWUPS of them.

        Counted over the threads that were followed rather than over the plan,
        because QUESTIONS_FOLLOWUP_SHARE picks by position too: a share of 0.5
        takes every odd slot, so offsetting by the slot number would hold
        `index % 2` at 1 forever and rotate nothing.

        Only after an accepted, answerable root. A thread whose first turn
        has no answer has nothing to follow on from - the chatbot was
        supposed to say it did not know - and a thread whose root a gate
        refused is a conversation starting with a question nobody would ask.

        Stops at the first follow-up a gate refuses. The refused one is
        stored, because it is drop-rate evidence like any other, but nothing
        is written after it: a third turn following a second that was thrown
        out is a conversation with a hole in it.
        """
        if not root.answerable or not self._settings.followup_types:
            return []

        turns: list[tuple[str, str | None]] = [(root.question_text, root.target_answer)]
        written: list[CheckedQuestion] = []
        # What the two thread gates read. The root's facts stay the root's
        # all the way down - a third turn re-asking the first is the defect
        # either way - while the passages are the turn before this one's,
        # because a thread is allowed to walk from one passage to the next.
        cited = root.fact_ids
        previous = root.passage_ids
        names = self._settings.followup_types
        if QuestionType.REASON in names and not any(
            self._reasoned(one) for one in sample.facts
        ):
            # The filter a root `reason` slot gets: a thread asks why only
            # where the material it is on says why. Decided once for the
            # thread, whose material does not change, so the cycle runs over
            # the other kinds and never repeats one in a reason's place.
            names = tuple(one for one in names if one != QuestionType.REASON)
            if not names:
                log.warning(
                    "topic %d: a thread was not followed: its material states "
                    "no reason, and QUESTIONS_FOLLOWUP_TYPES names no other kind",
                    topic_id,
                    extra={"topic.id": topic_id},
                )
                return []
        for turn in range(self._settings.max_followups):
            candidate = self._writer.follow_up(
                sample,
                tuple(turns),
                Plan(
                    spec=SPECS[names[(followed + turn) % len(names)]],
                    band=plan.band,
                    shape=plan.shape,
                    answerable=True,
                ),
                root_facts=cited,
                parent_passages=previous,
            )
            checked = self._checked(candidate, accepted)
            written.append(checked)
            if not checked.accepted:
                break
            accepted.append(checked)
            turns.append((checked.question_text, checked.target_answer))
            previous = checked.passage_ids
        return written
