"""The order the gates are applied in, and the verdict that comes out.

Cheapest first, because each one that fires saves the cost of those behind
it:

  malformed       structural, free
  compound        free: it asks two things, so half an answer is neither
                  right nor wrong
  answer_too_short  free: nothing worth scoring against
  answer_too_long   free: not the form of answer that was asked for
  wrong_form        free: a value carrying a verb, an explanation with none
  off_topic       free: an unanswerable question about nothing the material
                  mentions, which any chatbot declines
  wrong_type      free: a question word asking for another kind, an entity
                  question asking after no party, an enumeration answered
                  with one thing
  restates_question  free: the answer carries almost nothing the question did
                  not
  explanation_unusable  free: the long answer is missing or the wrong
                  length, asserts a number the passages do not carry, or only
                  restates the key
  asks_nothing_new  free: a follow-up citing nothing its root did not, so a
                  thread asks one fact twice
  off_thread      free: a follow-up resting on no passage the turn before it
                  used, so the conversation changed subject
  duplicate       one index probe against the questions already accepted
  answerable_after_all  the same probe, when an unanswerable question has a
                  twin the corpus does answer; or one call, when the
                  passages it cites settle it
  leaks_source    free where the title is quoted, in the structural step;
                  the phrasing judge's otherwise
  unanchored      a question nobody could have asked without the passage
  not_recoverable  the answer is not in the evidence the question cites; or,
                  for a short search query, one probe and one more read find
                  a passage it does not cite answering it differently
  answer_incomplete  the key names much less than the round trip found
  answerable_elsewhere  one corpus-wide passage probe and a second call, on
                  the unanswerable share only: a passage it does not cite
                  settles it. Cosine over passages.embedding where the corpus
                  has been embedded, shared lemmas where it has not
  needs_both      never refuses: an accepted answerable question citing two
                  or more passages is read once for the parts of its answer
                  and the passages that state each, and one cited passage
                  that states every part the others state is cited alone and
                  stored single-passage; a bridge cited alone, or a follow-up
                  its thread would break, keeps both, with the reading on the
                  row

The free ones are in `gates`, which imports no client; the calls are the
`verifier`'s and `phrasing`'s. Recoverability is the one no similarity
measure makes: it asks whether the answer can be got back out of the
passages, which is what a question is for, and a paraphrase, a decomposition
and a resolved pronoun all survive it where a threshold would not.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace

from confidence import Measurement
from database.qa_generator import (
    AnswerForm,
    Derivation,
    QuestionRejection,
    QuestionStatus,
    QuestionType,
)
from llm.client import ModelUnavailable
from nlp.analysis import content, interrogatives, pointing
from nlp.embedding import Embedder, cosine
from nlp.text import _plain, holders
from nlp.text import held as _held
from question_generation.gates import (
    BOUNDS,
    COMPOSITE,
    COVERAGE,
    ENTAILMENT_OVERLAP,
    EXPLANATION_CHARS,
    NAMES_SOMETHING,
    OFF_TOPIC_OVERLAP,
    OVERLAP,
    SHADOWED,
    about,
    adds_to,
    adds_up,
    agrees,
    anchored,
    asserted,
    cites_source,
    coordinates,
    counts_a_list,
    counts_something_else,
    covered,
    deciding,
    explains,
    fitting,
    incomplete,
    moves_on,
    near_verdict,
    on_topic,
    recalled,
    relabelled,
    relates,
    restates,
    retyped,
    rivals,
    same_material,
    shared_lemmas,
    structural,
    subject,
    typed,
)
from question_generation.kinds import KINDS, stored
from question_generation.models import (
    LONG_ANSWER_CHARS,
    Candidate,
    CheckedQuestion,
    FactGroup,
    Neighbour,
    kind,
)
from question_generation.types import GATES, PASSED, REFUSED, annotation, spec
from question_generation.verifier import (
    STATED_VERSION,
    Part,
    Reading,
    Settled,
    Settling,
    Verifier,
)

log = logging.getLogger(__name__)

#: The gate order, and what one gate's verdict is called beside the others.
#: Declared in `types`, which loads neither the embedder nor the verifier,
#: so the api can read a stored question's sequence.
__all__ = ["GATES", "PASSED", "REFUSED", "QuestionChecker", "annotation"]


def heard(
    settled: Settled,
    question: str,
    language: str | None,
    question_id: int | None = None,
) -> Settled:
    """A `settles` verdict, silent where its answer only says the question back.

    A `why` the passage gives no reason for comes back as the rule it asks
    about, and declining that question is what a chatbot should do.
    `restates` is the reading the key is held to the same way. Only an
    `answers` verdict is read so: the quote of a `refutes` or a `rule` is
    the rule itself, which is how those settle a question. And only one
    asked with a question word: `May a card be used abroad?` is answered yes
    by `A card may be used abroad.`, which says it back and is the answer.

    The silenced quote is logged, with the question's id where it has one,
    because the row keeps only the silence.
    """
    if (
        settled.verdict == Settling.ANSWERS
        and settled.quote is not None
        and interrogatives(question, language)
        and restates(question, settled.quote, language)
    ):
        log.info(
            "reading question %s as silent: the verifier answered %r with %r, "
            "which only says it back",
            "unsaved" if question_id is None else question_id,
            question,
            settled.quote,
        )
        return Settled(verdict=Settling.SILENT, quote=None)
    return settled


def quoted(quote: str, text: str) -> bool:
    """Whether a text holds a quote, read piece by piece across an ellipsis."""
    held = _plain(text)
    pieces = [_plain(one) for one in quote.replace("...", "…").split("…")]
    return all(piece in held for piece in pieces if piece)


def shown(
    settled: Settled, passages: Sequence[str], question_id: int | None
) -> Settled:
    """A `settles` verdict, silent where its quote is in none of the passages shown.

    A model that knows the material from elsewhere can settle a question
    from memory, quoting words the passages a chatbot will read do not
    carry; they leave the question open, and so does this. A quote is looked
    for piece by piece, split where it joins two runs - see `_held` - and
    each piece as whole words, so `Ja` is not found in `Jahresgebühr`.
    """
    if settled.verdict == Settling.SILENT or settled.quote is None:
        return settled
    if _held(settled.quote, passages):
        return settled
    log.info(
        "reading question %s as silent: the verifier settled it with %r, "
        "which is not in the passages it was shown",
        "unsaved" if question_id is None else question_id,
        settled.quote,
    )
    return Settled(verdict=Settling.SILENT, quote=None)


def _narrowed(group: FactGroup, passage_id: int) -> FactGroup:
    """The facts resting on that passage alone: none, for a bridge cited alone."""
    return FactGroup(
        tuple(
            fact
            for fact in group.facts
            if all(one.id == passage_id for one in fact.passages)
        )
    )


def _holds(parts: Sequence[Part], texts: Sequence[str]) -> list[set[int]]:
    """For each passage, the numbers of the parts it holds a quote of."""
    holds: list[set[int]] = [set() for _ in texts]
    for number, part in enumerate(parts):
        for quote in part.quotes:
            for at in holders(quote, texts):
                holds[at].add(number)
    return holds


def tied(parts: Sequence[Part], texts: Sequence[str]) -> bool:
    """Whether some quote is held and every passage holds the same parts."""
    holds = _holds(parts, texts)
    return any(holds) and all(one == holds[0] for one in holds)


def needed(parts: Sequence[Part], texts: Sequence[str]) -> tuple[int, ...] | None:
    """The positions of the passages a question needs, read off the quotes.

    A passage holds a part when it holds one of the part's quotes whole, so a
    quote two passages hold counts for both. The passages needed are those
    holding a part no other passage holds; when none does, the one holding
    the most parts, the first on a tie. Then, for each part those leave
    uncovered, the first passage holding it: with three passages a part two
    others share is held by no owner. None where no quote is held anywhere.
    """
    holds = _holds(parts, texts)
    if not any(holds):
        return None
    keep = {
        at
        for at, mine in enumerate(holds)
        if mine - set().union(*(one for i, one in enumerate(holds) if i != at))
    } or {max(range(len(texts)), key=lambda at: (len(holds[at]), -at))}
    covered = set().union(*(holds[at] for at in keep))
    for part in sorted(set().union(*holds) - covered):
        if part not in covered:
            first = next(at for at, mine in enumerate(holds) if part in mine)
            keep.add(first)
            covered |= holds[first]
    # With three or more passages a subset of two or more needed keeps every
    # citation, until a three-passage kind narrows to subsets.
    return tuple(sorted(keep))


def settle(
    verifier: Verifier,
    question: str,
    language: str | None,
    passages: Sequence[str],
    probe: Callable[[], Sequence[str]] | None,
    question_id: int | None = None,
    found: list[Settled] | None = None,
    expected: str = Settling.SILENT,
) -> tuple[tuple[str, str] | None, list[Measurement]]:
    """Whether the material settles a question written to have no answer.

    Not "do the passages state an answer": a question whose premise they
    refute, or whose case a list or a rule in them covers, is answered too,
    and a chatbot saying so is right. First over the passages it cites, then,
    where those are silent, over what `probe` hands back: the corpus beyond
    them, called only then because it costs a query. None for no probe.

    The one sequence the checker and `make questions-rejudge` both run, so
    the two cannot read one verdict two ways. Returns the code and reason it
    refuses the question under, or None, and beside them the verdicts as the
    row keeps them. `found` collects the verdict that settled it, when one
    did, for a caller that writes from the words it was settled with.

    `expected` is the verdict its kind was written to get, `silent` unless
    its category says otherwise: a false presupposition is kept when its
    passages refute it, an underspecified question when they answer it by
    case, and only with words of the cited passages behind the verdict.
    Every verdict but `silent` answers a question, so another one refuses
    it as above; `silent` where the kind wanted another is a question of
    the wrong kind. The probe looks for an answer elsewhere, so beside it
    the kind's own verdict and `silent` both keep it.
    """
    settled = heard(
        shown(verifier.settles(question, passages), passages, question_id),
        question,
        language,
        question_id,
    )
    # With no words of the cited passages behind it, a refutation or an
    # answer by case may be the model's memory: `shown` drops a quote they
    # do not hold, and the reading may give none.
    if expected != Settling.SILENT and settled.quote is None:
        settled = Settled(verdict=Settling.SILENT, quote=None)
    opinions = [settled.reading("settles", expected)]
    if settled.verdict != expected:
        if settled.verdict == Settling.SILENT:
            return (
                QuestionRejection.WRONG_TYPE,
                (
                    f"the cited passages settle nothing, where its kind wants "
                    f"them to give {expected}"
                ),
            ), opinions
        if found is not None:
            found.append(settled)
        return (
            QuestionRejection.ANSWERABLE_AFTER_ALL,
            (
                f"the cited passages settle it after all ({settled.verdict}), "
                f"with {settled.quote!r}"
            ),
        ), opinions
    probed = probe() if probe is not None else ()
    if not probed:
        return None, opinions
    # Not filtered by the extractive reader first: it finds where an answer
    # is stated, and a refuted premise or a general rule that settles the
    # question is not a span it could find. The cited passages come first:
    # they set up the case, and a rule elsewhere settles it only read beside
    # them.
    shown_both = [*passages, *probed]
    settled = heard(
        shown(verifier.settles(question, shown_both), shown_both, question_id),
        question,
        language,
        question_id,
    )
    opinions.append(settled.reading("settles_elsewhere", expected, Settling.SILENT))
    if settled.verdict in (expected, Settling.SILENT):
        return None, opinions
    if found is not None:
        found.append(settled)
    # Read beside the probe, the cited passages can settle it after all: a
    # quote they hold is theirs, and the corpus beyond them was not needed.
    if settled.quote is not None and _held(settled.quote, passages):
        return (
            QuestionRejection.ANSWERABLE_AFTER_ALL,
            (
                f"the cited passages settle it after all ({settled.verdict}), "
                f"with {settled.quote!r}"
            ),
        ), opinions
    return (
        QuestionRejection.ANSWERABLE_ELSEWHERE,
        (
            f"a passage it does not cite settles it ({settled.verdict}), "
            f"with {settled.quote!r}, so the corpus is not silent about this"
        ),
    ), opinions


class QuestionChecker:
    """Puts one candidate through every gate, cheapest first."""

    def __init__(
        self,
        *,
        embedder: Embedder,
        verifier: Verifier,
        nearest,
        threshold: float,
        floor: float = 0.0,
        shared_threshold: float | None = None,
        judge_phrasing: bool = True,
        bounds: Mapping[str, tuple[int, int]] | None = None,
        explanation_chars: tuple[int, int] = EXPLANATION_CHARS,
        overlap: float = OVERLAP,
        coverage: float = COVERAGE,
        long_answer_chars: int = LONG_ANSWER_CHARS,
        elsewhere=None,
        elsewhere_passages: int = 0,
        off_topic_overlap: float = OFF_TOPIC_OVERLAP,
        entail: bool = True,
        phrasing=None,
        entailment=None,
        entailment_threshold: float = 0.5,
        about_overlap: float = ENTAILMENT_OVERLAP,
        extractive=None,
        extractive_confidence: float = 0.9,
    ) -> None:
        """Initialises the checker with its collaborators.

        `nearest` is a callable rather than the catalogue itself: what this
        needs of the database is one probe, and taking the whole repository
        for it would let a gate read anything.

        `judge_phrasing` is whether the phrasing judge's opinion of the
        question may reject one. Those gates are the only ones here that are
        an opinion rather than a measurement, and an opinion needs an
        independent holder: a writer marking its own work rejected `According
        to the ECB and NCAs, who conducts the due diligence check?` for
        naming nothing. The factory turns it off when QUESTIONS_PHRASING_MODEL
        resolves to the writer's model, and then the judgements are not asked
        for at all - see `_opinion`. Recoverability stays on regardless,
        because that one is checkable against the passage.

        `elsewhere` is the corpus-wide passage probe the unanswerable gate
        reads, taking the question's lemmas, its language, the passages it
        already cites and a limit. A callable and not the catalogue, for the
        same reason `nearest` is one. None, or a limit of 0, leaves an
        unanswerable question judged against its own passages alone.

        `shared_threshold` is the duplicate bar for two questions resting on
        the same fact, or None to hold them to `threshold`.
        """
        self._embedder = embedder
        self._verifier = verifier
        self._nearest = nearest
        self._floor = floor
        self._judge_phrasing = judge_phrasing
        self._bounds = dict(bounds or BOUNDS)
        self._explanation_chars = explanation_chars
        self._overlap = overlap
        self._coverage = coverage
        self._long_answer_chars = long_answer_chars
        self._threshold = threshold
        self._shared_threshold = shared_threshold
        self._elsewhere = elsewhere
        self._elsewhere_passages = elsewhere_passages
        self._off_topic_overlap = off_topic_overlap
        self._entail = entail
        self._phrasing_judge = phrasing
        self._entailment = entailment
        self._entailment_threshold = entailment_threshold
        self._about_overlap = about_overlap
        self._extractive = extractive
        self._extractive_confidence = extractive_confidence

    @property
    def _opinion(self):
        """The phrasing judge, or None when its answer could not be used.

        The three judgements are opinions, so `judge_phrasing` decides
        whether one may reject a question - and when it may not, none is
        asked for.

        A rule is unaffected. `cites_source` settles what a pattern can
        settle and still rejects on its own, because a measurement is not an
        opinion and needs no independent holder.
        """
        return self._phrasing_judge if self._judge_phrasing else None

    def check(
        self, candidate: Candidate, seen: Sequence[CheckedQuestion] = ()
    ) -> CheckedQuestion:
        """Judges one candidate, returning it stored either way.

        `seen` is what this run has already accepted. Without it the dedup
        gate would compare a candidate only against what was in the database
        when the run started, and a topic would happily write the same
        question four times.

        Raises:
            ModelUnavailable: If the verifier could not be reached.
        """
        # Appended to as each gate reads the question, so the span can say
        # what it got past and not only what stopped it. A list rather than
        # a fixed order read off the verdict: `off_topic` runs only for an
        # unanswerable question and `round_trip` only for what reaches it,
        # so the sequence is not derivable from the code that fired.
        ran: list[str] = ["structural"]
        # Appended to beside `ran`, and for the same reason: which gates
        # measured something is not derivable from the verdict either. Only
        # the gates that ARE measurements write here, and the `settles`
        # verdicts, which go in as opinions: kept on the row, with no margin
        # and no part in the confidence.
        readings: list[Measurement] = []
        # And the judgements that were asked for and could not be had. An
        # abstention leaves no other trace: the checker rejects on False and
        # an abstention is None, so a gate that could not run reads exactly
        # like one that passed and the question is ACCEPTED.
        abstained: list[str] = []
        # The verdict that settled a question written to have no answer,
        # when one did: the words a recycled answerable question is written
        # from.
        settled: list[Settled] = []
        kind = retyped(
            candidate.question_text, candidate.spec.name, candidate.group.language
        )
        if kind != candidate.spec.name:
            log.info(
                "typing question %r as %s: its opening asks for one, not %s",
                candidate.question_text,
                kind,
                candidate.spec.name,
            )
            candidate = replace(candidate, spec=spec(kind))
        failed, form = structural(
            question_text=candidate.question_text,
            target_answer=candidate.target_answer,
            answerable=candidate.answerable,
            language=candidate.group.language,
            statements=candidate.group.statements,
            forms=candidate.spec.forms,
            bounds=self._bounds,
            titles=candidate.group.titles,
            kind=candidate.kind,
            query=any(one.form == "query" for one in candidate.categories),
        )

        def done(
            failed: tuple[str, str] | None, embedding: list[float] | None = None
        ) -> CheckedQuestion:
            """The verdict, with everything read so far."""
            return self._verdict(
                candidate,
                failed,
                embedding,
                self._long_answer_chars,
                form,
                ran,
                readings,
                abstained,
                settled[0] if settled else None,
            )

        if failed:
            return done(failed)

        # What the kind checks of a draft, named in `kinds.KINDS`: a free
        # check right after the structural rules, and one after the round
        # trip. A tuple is a refusal; a candidate replaces the one read.
        dealt = KINDS[candidate.kind]
        if dealt.before is not None:
            outcome = getattr(self, dealt.before)(candidate, readings)
            if isinstance(outcome, tuple):
                return done(outcome)
            candidate = outcome

        # Free, and only an unanswerable question can fail it: an answerable
        # one is about its material by construction, because the answer came
        # out of it.
        if not candidate.answerable:
            ran.append("off_topic")
            share = shared_lemmas(
                candidate.question_text,
                candidate.group.lemmas,
                candidate.group.language,
            )
            if share is not None and self._off_topic_overlap > 0:
                readings.append(
                    Measurement("off_topic", share, self._off_topic_overlap)
                )
            if not on_topic(
                candidate.question_text,
                candidate.group.language,
                candidate.group.lemmas,
                self._off_topic_overlap,
            ):
                return done(
                    (
                        QuestionRejection.OFF_TOPIC,
                        (
                            "it names almost nothing the passages it was drawn from "
                            "name, so any chatbot declines it and declining it "
                            "proves nothing"
                        ),
                    )
                )

        # Free, and ahead of the embedding for that reason: each of these is
        # a rule reading what the writer already returned.
        ran.append("kind_and_thread")
        failed = self._kind(candidate) or self._thread(candidate)
        if failed:
            return done(failed)

        ran.append("near_duplicate")
        embedding = self._embedder.embed(candidate.question_text)
        probed = {
            "answerable": candidate.answerable,
            "threshold": self._threshold,
            "shared_threshold": self._shared_threshold,
            "question": candidate.question_text,
            "language": candidate.group.language,
            "passages": [passage.id for passage in candidate.group.resting],
            "facts": [fact.id for fact in candidate.group.facts],
        }
        found = deciding(self._near(embedding, seen, candidate), **probed)
        near, bar = found if found is not None else (None, None)
        if near is not None and bar is not None:
            # High is what refuses here: a question near an accepted one is
            # the duplicate. The first question of a run has no neighbour
            # and so no reading, which is an abstention and not a 1.0, and
            # neither does one whose neighbour cannot refuse it.
            #
            # Against the bar that applied to this pair, which what the two
            # cite decides. Measured from the floor two unrelated questions
            # score, not from 0, which no pair of embeddings reaches.
            readings.append(
                Measurement(
                    "near_duplicate",
                    near.similarity,
                    bar,
                    high_is_safe=False,
                    safe_end=self._floor,
                )
            )
        failed = near_verdict(near, **probed)
        if failed:
            return done(failed, embedding)

        # Before the round trip, because none of it reads a passage: a
        # question naming its own source is refused without ever paying for
        # the call that would have answered it.
        ran.append("phrasing")
        failed = self._phrasing(candidate, abstained)
        if failed:
            return done(failed, embedding)

        failed = None
        if dealt.round_trip:
            ran.append("round_trip")
            failed = self._round_trip(candidate, form, embedding, readings, settled)
        if failed is None and dealt.after is not None:
            outcome = getattr(self, dealt.after)(candidate, form, readings)
            if isinstance(outcome, tuple):
                failed = outcome
            else:
                candidate = outcome
        return done(failed, embedding)

    def _parted(
        self, candidate: Candidate, readings: list[Measurement]
    ) -> Candidate | tuple[str, str]:
        """Whether a compound draft is two halves on two passages, unrelated.

        Free. The key must be the halves' answers in order, joined by `; `,
        and the question must claim no relation between them: one that does
        is another kind of question, thrown away as the wrong type.
        """
        resting = {passage.id for passage in candidate.group.resting}
        parts = candidate.parts
        # The halves are the writer's and cannot be recomputed from the merged
        # question, so the row keeps them whatever verdict it gets.
        readings.append(
            Measurement(
                "halves",
                float(len(parts)),
                2.0,
                shadow=True,
                detail=[
                    {"passage_id": one, "question": two, "answer": three}
                    for one, two, three in parts
                ],
            )
        )
        if (
            len(parts) != 2
            or parts[0][0] == parts[1][0]
            or not {one[0] for one in parts} <= resting
        ):
            return (
                QuestionRejection.MALFORMED,
                (
                    "a compound question needs exactly two parts, one for each "
                    "of two different cited passages"
                ),
            )
        # A half's answer copied as a sentence may close with a stop the joined
        # key does not carry, so the closing marks are not compared.
        joined = "; ".join(one[2].strip().rstrip(".;:").strip() for one in parts)
        if (candidate.target_answer or "").strip().rstrip(
            ".;:"
        ).strip().casefold() != joined.casefold():
            return (
                QuestionRejection.MALFORMED,
                f"the key is not its halves' answers joined by '; ', {joined!r}",
            )
        for _, _, answer in parts:
            _, failed = fitting(
                answer.strip(),
                candidate.spec.forms,
                self._bounds,
                candidate.group.language,
            )
            if failed:
                return failed
        word = relates(
            candidate.question_text,
            candidate.group.language,
            [one[1] for one in parts],
        )
        if word is not None:
            return (
                QuestionRejection.WRONG_TYPE,
                (
                    f"a compound question claims no relation between its "
                    f"halves; it says {word!r}"
                ),
            )
        return candidate

    def _parts(
        self,
        candidate: Candidate,
        form: str,
        readings: list[Measurement],
        embedding: list[float] | None = None,
    ) -> Candidate | tuple[str, str]:
        """Whether each half is answered by its own passage read alone.

        The verifier is shown one half and one passage at a time, so a half
        that needed the other passage, or that the passage does not hold, is
        refused; the merged question is never read as one. A half recall did
        not find gets the rescue a single key gets, against its own passage.
        """
        by_id = {passage.id: passage for passage in candidate.group.resting}
        for number, (passage_id, question, answer) in enumerate(candidate.parts, 1):
            passage = by_id[passage_id]
            got = self._verifier.read(question, (passage.text,)).recovered
            half, _ = fitting(
                answer, candidate.spec.forms, self._bounds, candidate.group.language
            )
            if got is None or not (
                agrees(
                    got,
                    answer,
                    candidate.group.language,
                    half,
                    self._overlap,
                    question,
                    passage.section_path or "",
                    (passage.text,),
                )
                or self._backed(
                    replace(
                        candidate,
                        question_text=question,
                        group=_narrowed(candidate.group, passage_id),
                    ),
                    answer,
                    readings,
                )
            ):
                return (
                    QuestionRejection.NOT_RECOVERABLE,
                    (
                        f"half {number} ({question!r}) is not answered by its "
                        f"passage alone"
                    ),
                )
        return candidate

    def _needed(
        self, candidate: Candidate, form: str, readings: list[Measurement]
    ) -> Candidate:
        """Cites a question from the passages that hold a part of its answer.

        Citing two passages is the writer's report of what it used, and a
        second one that states nothing the first does not makes a question
        two-passage and harder than it is. So the question is read once for
        the parts of its answer and the words of every cited passage that
        state each, and code finds those words in the passages: one passage
        stating every part the others state is the only citation, the scope
        and the band following from it.

        Last, and only for a question about to be accepted, so a refused one
        never pays for the call. It never refuses: a question one passage
        answers is relabelled, not refused. A bridge cited alone, or a
        follow-up whose narrowed citation would ask nothing its root did not
        (`_thread` is read again on the narrowed group), keeps both passages,
        with the reading on the row. Where no quote is found in any passage
        nothing is decided and nothing is recorded. Where every passage states
        every part and the question joins cases with a conjunction, each may
        give the same answer for its own case, so both are kept.
        """
        resting = candidate.group.resting
        if not candidate.answerable or candidate.spec.derived or len(resting) < 2:
            return candidate
        texts = [passage.text for passage in resting]
        try:
            parts = self._verifier.stated(
                candidate.question_text,
                candidate.target_answer or "",
                texts,
                candidate.thread,
            )
        except ModelUnavailable as exc:
            # ModelRefused is one too. An opinion about the citation: losing
            # it must not lose a question the passages support.
            log.warning("no parts reading for %r: %s", candidate.question_text, exc)
            return candidate
        keep = needed(parts, texts)
        if keep is None:
            log.info(
                "%r: no passage holds a quoted part, kept as cited",
                candidate.question_text,
            )
            return candidate
        # shortcut: a tie on a question with a conjunction keeps both even when
        # the passages repeat each other (5 of 45 padded v0.3.12 rows); upgrade
        # when the reading lists the cases as parts.
        joined = (
            len(keep) == 1
            and tied(parts, texts)
            and coordinates(candidate.question_text, candidate.group.language)
        )
        if joined:
            log.info(
                "%r: every cited passage states every part and the question "
                "joins cases: kept two-passage",
                candidate.question_text,
            )
        both = len(keep) != 1 or joined
        readings.append(
            Measurement(
                "needs_both",
                1.0 if both else 0.0,
                0.5,
                opinion=True,
                version=STATED_VERSION,
            )
        )
        if both:
            return candidate
        assert len(keep) == 1
        keep_id = resting[keep[0]].id
        narrowed = _narrowed(candidate.group, keep_id)
        if not narrowed.facts:
            log.info(
                "%r is stated by one passage but cites a bridge: kept two-passage",
                candidate.question_text,
            )
            return candidate
        alone = replace(candidate, group=narrowed)
        if self._thread(alone) is not None:
            log.info(
                "%r is stated by one passage but its thread needs both: kept "
                "two-passage",
                candidate.question_text,
            )
            return candidate
        log.info(
            "%r is cited from passage %s alone",
            candidate.question_text,
            keep_id,
        )
        return alone

    def _kind(self, candidate: Candidate) -> tuple[str, str] | None:
        """What a rule can settle about the kind and the long answer.

        `typed`, which re-verify applies to a stored row too, and the long
        answer, which needs the passages. None calls anything. They sit ahead
        of the embedding because every one of them reads what the writer
        already returned, and a candidate refused here costs nothing at all.
        """
        failed = typed(
            candidate.question_text,
            candidate.target_answer,
            candidate.answerable,
            candidate.spec.name,
            candidate.group.language,
        )
        if failed or not candidate.answerable:
            return failed

        target = candidate.target_answer or ""
        language = candidate.group.language

        # Written now, so required: `explains` lets an empty one through
        # for a stored row read without one.
        if not (candidate.answer_explanation or "").strip():
            return (
                QuestionRejection.EXPLANATION_UNUSABLE,
                "it carries no long answer, the second answer every question carries",
            )
        if not explains(
            candidate.answer_explanation or "",
            target,
            candidate.group.passages,
            language,
            self._explanation_chars,
        ):
            return (
                QuestionRejection.EXPLANATION_UNUSABLE,
                (
                    "its long answer is outside the length a reading takes, "
                    "asserts a number or a name the passages do not carry, or "
                    "says nothing the target answer had not already said"
                ),
            )
        return None

    def _thread(self, candidate: Candidate) -> tuple[str, str] | None:
        """Whether a follow-up is one, read on the facts rather than the words.

        Nothing here applies to a root question, which follows nothing.

        Both readings are structural on purpose. A follow-up MAY lean on the
        conversation, so what makes it a good one cannot be read off its
        wording - `Und bei einem dringenden?` names nothing and is exactly
        the turn a thread exists to produce. What can be read is the
        material underneath it: a thread that walks forward cites something
        new, and a thread that stays a conversation keeps a passage.
        """
        if not candidate.follows:
            return None
        cited = [fact.id for fact in candidate.group.facts]
        # A summary or an outline holds several claims, so a turn citing one
        # again still walks on when its key says what no earlier turn did.
        walks = all(
            fact.kind in COMPOSITE for fact in candidate.group.facts
        ) and adds_to(
            candidate.target_answer or "", candidate.thread, candidate.group.language
        )
        if not moves_on(cited, candidate.root_facts) and not walks:
            return (
                QuestionRejection.ASKS_NOTHING_NEW,
                (
                    "it cites nothing the question it follows did not, so the "
                    "thread asks one fact twice in two shapes"
                ),
            )
        if not same_material(
            [passage.id for passage in candidate.group.resting],
            candidate.parent_passages,
        ):
            return (
                QuestionRejection.OFF_THREAD,
                (
                    "it rests on no passage an earlier turn of its thread "
                    "used, so it changes the subject rather than continuing"
                ),
            )
        return None

    def _phrasing(
        self, candidate: Candidate, abstained: list[str]
    ) -> tuple[str, str] | None:
        """What the question's own wording says, before any passage is read.

        `abstained` collects the judgements that were asked for and could
        not be had. Passed down rather than returned, the way `ran` and
        `readings` are, because this returns a verdict and an abstention is
        not one - it is the absence of one, and the caller records it on the
        row so the question does not read as having cleared a gate nobody
        ran.

        Ahead of the round trip because none of it needs the passages, so a
        question that carries its own source no longer pays for a call that
        reads them. The three judgements here used to be one field each on
        that call. See `phrasing.py`.

        Two of the three now need no model. `cites_source` settles the
        patterns and only the residue is asked; `anchored` is the whole of
        the naming verdict, where it used to be a veto on a model's opinion
        that was wrong about `According to the ECB and NCAs, who conducts the
        due diligence check?`.

        A rule is not an opinion, so `judge_phrasing` does not gate one. It
        gates what a model said, which is what needs an independent holder.
        """
        question = candidate.question_text
        language = candidate.group.language

        # A question carrying its own source has already done the work it
        # was meant to test. Judged for a follow-up too - leaning on the
        # conversation is allowed, naming the file is not.
        cited = cites_source(question, language)
        ruled = cited is not None
        if cited is None and (judge := self._opinion) is not None:
            cited = judge.names_its_source(question)
            if cited is None:
                abstained.append("names_its_source")
        if cited:
            reason = (
                "it names the material the answer is in, so it asks a question "
                "and answers half of it"
                + ("" if ruled else ", the phrasing judge says")
            )
            return QuestionRejection.LEAKS_SOURCE, reason

        # Never for a follow-up. `And for an urgent one?` names nothing and
        # is exactly the question a person asks second; leaning on the thread
        # is what a follow-up is for, so judging it as though it had been
        # asked cold would reject every one of them.
        if candidate.follows:
            return None

        # Still two holders, and the reason is measured in both directions.
        # The opinion alone rejected `According to the ECB and NCAs, who
        # conducts the due diligence check?` for naming nothing. The
        # measurement alone rejects `Why must a request be confirmed in
        # writing?`, because NAMES_SOMETHING was calibrated as a veto on
        # German questions, where one compound carries what two English
        # words do. Neither is a verdict on its own.
        #
        # What changed is which measurement: the parse reads what a question
        # names, where the model used to be asked to copy it out inside a
        # call about the passages.
        judge = self._opinion
        names = (
            judge.names_something(question)
            if judge is not None and not anchored(question, language)
            else True
        )
        if names is None:
            abstained.append("names_something")
        if names is False:
            reason = (
                f"it names nothing a person searching would know - the "
                f"parse finds {subject(question, language)!r} - and it "
                f"names no name, no number and fewer than "
                f"{NAMES_SOMETHING} things, so it could not have been "
                f"asked without the passage"
            )
            return QuestionRejection.UNANCHORED, reason

        # The other way a question fails to stand on its own: not naming too
        # little, but pointing at something the asker cannot see. The
        # measurement over-fires by design - a question that sets a case up
        # and refers back to it carries a pointer and is fine - so it only
        # ever asks the question, and the verdict is the model's.
        pointers = pointing(question, language)
        if not pointers or judge is None:
            return None
        contained = judge.self_contained(question, pointers)
        if contained is None:
            abstained.append("self_contained")
        if contained is False:
            reason = (
                f"it points outward with {', '.join(repr(one) for one in pointers)} "
                f"and there is nothing in the question to point at, so only "
                f"somebody holding the passage could have asked it"
            )
            return QuestionRejection.UNANCHORED, reason
        return None

    def _recovered(self, candidate: Candidate) -> Reading:
        """The answer the cited passages give back, from whichever reader.

        The extractive model first, where one is configured and the question
        was asked cold. SQuAD 2.0 is this task exactly - a question, a
        context, and a span or no answer - and a model trained on it answers
        in milliseconds with a span in the passage's own words, which is
        what the verifier's prompt asks for in a paragraph.

        It cannot replace the served model, and is not asked to. Every span
        it gives is contiguous and inside one passage, where the verifier is
        allowed to put an answer together from two sentences or two
        statements; and a follow-up is answered in a conversation, which an
        extractive model has nowhere to put. So a confident span is taken,
        and everything else falls through to something that can read.

        An ANSWERABLE question only. There a span agreeing with the target
        accepts the question, and the entailment pass is behind it either
        way. On an unanswerable one the same span is `answerable_after_all`,
        which is a rejection, and rejecting an unanswerable question wrongly
        marks a correct chatbot wrong - a verdict an extractor should not
        make alone. It is not asked here for that reason, and asking it
        would buy nothing: a span it does not find falls through to the
        verifier regardless. Nor is the verifier asked to read one:
        `_round_trip` asks an unanswerable question whether the passages
        settle it, and never calls this.

        shortcut: a span the extractive model gives is not read for whether a
        why has a reason, so `reason_given` holds; ask the verifier too if
        QA_MODEL is ever shipped on.
        """
        if self._extractive is not None and not candidate.thread:
            found = self._extractive.answer(
                candidate.question_text,
                candidate.group.passages,
                self._extractive_confidence,
            )
            if found is not None:
                log.debug(
                    "extracted %r at %.2f for %r",
                    found.text,
                    found.score,
                    candidate.question_text,
                )
                return Reading(recovered=found.text)
        return self._verifier.read(
            candidate.question_text,
            candidate.group.passages,
            candidate.thread,
        )

    def _round_trip(
        self,
        candidate: Candidate,
        form: str,
        embedding: list[float],
        readings: list[Measurement],
        settled: list[Settled] | None = None,
    ) -> tuple[str, str] | None:
        """Asks whether the passages give the answer back.

        `settled` collects the verdict that settled a question written to
        have no answer, when one did.
        """
        # A derived answer is not in the passages and is not meant to be.
        # Asking recall for it is asking the verifier to contradict the
        # type's own directive - `aggregation` says the total must be
        # something the material does not write down.
        #
        # Ahead of the recall call and not behind it, because `_computable`
        # does not read what that call returns.
        if candidate.answerable and candidate.spec.derived:
            return self._computable(candidate, candidate.target_answer or "")

        if candidate.answerable:
            read = self._recovered(candidate)
            target = candidate.target_answer or ""
            # What the verifier got back, against what the key claims, on
            # the same lemmas `agrees` compares. Recorded whichever way the
            # verdict went, because `agrees` has several branches and no
            # single threshold - this is the reading a reviewer wants beside
            # the verdict, not a restatement of it.
            #
            # Against the bar the form is held to. A value is compared
            # whole, so its bar is all of it, and one that came back whole
            # records nothing: its margin against all of itself is 0, which
            # would make every value key the weakest reading of its row.
            # One whose recovery fell short and which the entailment pass
            # then rescued keeps its reading, so its confidence is 0: it was
            # accepted on the rescue, not on recall.
            #
            # A list or an explanation recovered with no content lemma at all
            # reads 0 rather than abstaining: the key's lemmas were looked
            # for and none came back.
            if read.recovered is not None:
                language = candidate.group.language
                recall = recalled(
                    read.recovered,
                    target,
                    language,
                    form,
                    candidate.question_text,
                    candidate.group.headings,
                    candidate.group.passages,
                )
                if form != AnswerForm.VALUE:
                    if recall is not None:
                        readings.append(Measurement("recall", recall, self._overlap))
                elif recall is not None and recall < 1.0:
                    readings.append(Measurement("recall", recall, 1.0))
            # NOT IN PASSAGE is final. The verifier read the question against
            # the passages; the entailment pass scores the bare key against
            # each passage without it, so a fragment the passages happen to
            # contain is entailed whatever the question asked.
            if read.recovered is None:
                if candidate.spec.name == QuestionType.REASON:
                    return (
                        QuestionRejection.NOT_RECOVERABLE,
                        "asked why, the verifier found no reason in the cited passages",
                    )
                return (
                    QuestionRejection.NOT_RECOVERABLE,
                    "the verifier could not find the answer in the cited passages",
                )
            # Asked for a reason, the verifier says the passages give none
            # beyond the rule: a key restating the rule in the passage's own
            # words adds the lemmas `restates` counts, and passes it.
            if candidate.spec.name == QuestionType.REASON and not read.reason_given:
                return (
                    QuestionRejection.NOT_RECOVERABLE,
                    (
                        "asked why, the verifier found no reason in the cited "
                        "passages beyond the rule itself"
                    ),
                )
            # Asked for a reason, the verifier came back with the question's
            # own rule: the passages give no reason, and a key restating the
            # rule in other words is one the entailment pass would accept,
            # because the passages do entail the rule.
            if (
                read.recovered is not None
                and candidate.spec.name == QuestionType.REASON
                and restates(
                    candidate.question_text,
                    read.recovered,
                    candidate.group.language,
                )
            ):
                return (
                    QuestionRejection.NOT_RECOVERABLE,
                    (
                        f"asked why, the verifier found only the rule itself "
                        f"in the cited passages, {read.recovered!r}"
                    ),
                )
            # The completeness reading on a prose key, in shadow: stored so a
            # bar can be set on real keys, refusing nothing yet. Ahead of the
            # verdict, so a bar is measured on the keys refused here too.
            if form == AnswerForm.EXPLANATION and candidate.spec.name in SHADOWED:
                share = covered(read.recovered, target, candidate.group.language)
                readings.append(
                    Measurement("coverage", share, self._coverage, shadow=True)
                )
            # A key the entailment pass rescues goes on to the reading below:
            # the rescue says the key is true, not that it is the whole of
            # what the passages gave back.
            if not agrees(
                read.recovered,
                target,
                candidate.group.language,
                form,
                self._overlap,
                candidate.question_text,
                candidate.group.headings,
                candidate.group.passages,
            ) and not self._backed(candidate, target, readings):
                return (
                    QuestionRejection.NOT_RECOVERABLE,
                    (
                        f"the verifier recovered {read.recovered!r} where the "
                        f"target answer is {target!r}"
                    ),
                )
            # The same recovery read the other way. `agrees` asks whether
            # everything the target asserts came back; this asks whether
            # the target is most of what did. A key naming one of seven
            # parties agrees with the passage and still marks a chatbot
            # that names all seven wrong.
            if incomplete(
                read.recovered,
                target,
                candidate.group.language,
                form,
                self._coverage,
                candidate.question_text,
            ):
                return (
                    QuestionRejection.ANSWER_INCOMPLETE,
                    (
                        f"the target answer {target!r} names much less than "
                        f"the verifier found in the same passages, "
                        f"{read.recovered!r}"
                    ),
                )
            return self._ambiguous(candidate, target, form, embedding)

        told = kind(candidate.categories)
        failed, opinions = settle(
            self._verifier,
            candidate.question_text,
            candidate.group.language,
            candidate.group.passages,
            self._corpus(candidate, embedding),
            found=settled,
            expected=(told.settles if told else None) or Settling.SILENT,
        )
        readings.extend(opinions)
        return failed

    def _ambiguous(
        self, candidate: Candidate, target: str, form: str, embedding: list[float]
    ) -> tuple[str, str] | None:
        """Whether a passage a short search query does not cite answers it differently.

        A few keywords drop the qualifier that tells two cases apart, and the
        writer and the round trip read only the cited passages, so a chatbot
        answering from another passage the keywords fit equally is marked
        wrong for being right. One probe and one more read, for a query
        bounded to a few words only: the long queries' keys passed without it.
        """
        short = any(
            one.form == "query" and one.words[1] is not None
            for one in candidate.categories
        )
        probe = self._corpus(candidate, embedding) if short else None
        passages = probe() if probe is not None else ()
        if not passages:
            return None
        other = self._verifier.read(
            candidate.question_text, passages, candidate.thread
        ).recovered
        if other is None or agrees(
            other,
            target,
            candidate.group.language,
            form,
            self._overlap,
            candidate.question_text,
            "",
            passages,
        ):
            return None
        return (
            QuestionRejection.NOT_RECOVERABLE,
            (
                f"a passage it does not cite answers it differently, {other!r}, "
                f"and its keywords do not say which of the two is asked"
            ),
        )

    def _computable(self, candidate: Candidate, target: str) -> tuple[str, str] | None:
        """Whether a derived answer follows from what the passages do state.

        The gate a derived type gets instead of recoverability, because the
        two ask opposite questions. Recoverability asks whether the passages
        STATE the answer; these types are defined by their not doing so, and
        the answer is right when what it needs is there and the step from
        there to here holds.

        Which step is asked depends on how the type derives. Arithmetic is
        not entailment: `Do the arithmetic` is the wrong instruction for a
        conclusion drawn from two rules, and `does this follow` is the wrong
        one for a total, which follows from anything if the reader is
        generous about addition.

        Still a model's judgement, and still the verifier's rather than the
        writer's, so nothing here marks its own work.
        """
        if not target:
            return (
                QuestionRejection.NOT_RECOVERABLE,
                "it carries no answer to check the passages against",
            )
        if candidate.spec.derived == Derivation.ARITHMETIC:
            # A total no figures come to is refused here rather than asked:
            # it has a right value rather than a likely one, and a model
            # asked whether two numbers come to a third is being asked to
            # agree. One some figures do come to is still asked, because up
            # to four of the figures cited sum to most small totals whatever
            # each counts. None is an answer this cannot read - a total in
            # words, a range, a date, or a count of what passages holding
            # fewer than two figures list - and falls through to the model
            # too, as a count does whose passages' figures all count
            # something else.
            computed = (
                None
                if counts_something_else(
                    candidate.question_text,
                    candidate.group.passages,
                    candidate.group.language,
                )
                else adds_up(target, candidate.group.passages, candidate.group.language)
            )
            if computed is False:
                return (
                    QuestionRejection.NOT_RECOVERABLE,
                    (
                        f"{target!r} is not a total of any figures the cited "
                        f"passages state, or is two years added together"
                    ),
                )
        asked = (
            self._verifier.computes
            if candidate.spec.derived == Derivation.ARITHMETIC
            else self._verifier.follows
        )
        if asked(
            candidate.question_text,
            target,
            candidate.group.passages,
            candidate.thread,
        ):
            return None
        return (
            QuestionRejection.NOT_RECOVERABLE,
            (f"{target!r} does not follow from what the cited passages state"),
        )

    def _backed(
        self, candidate: Candidate, target: str, readings: list[Measurement]
    ) -> bool:
        """Whether the entailment pass rescues an answer recall did not find.

        Three guards, all of which have to hold, and the third is what the
        LMT case cost. Every number, date and name the target asserts must
        occur in the passages, which no opinion can overrule: that is what
        keeps `4 hours` from being confirmed against a passage that says 48.
        The passages must be ABOUT what the question asks about, which is
        `gates.about` - `Was ist ein Liquiditätsmanagementtool?` answered
        `eine einjährige Rückgabefrist` passes the first guard, because that
        phrase is lifted straight out of the passage, and the passages never
        mention a Liquiditätsmanagementtool at all. Only then is the
        judgement asked.

        It can only ever accept. A question reaching here was already being
        rejected, so a pass that says nothing leaves the verdict where it
        was and costs one judgement on the failures alone.
        """
        if not self._entail or not target:
            return False
        passages = candidate.group.passages
        language = candidate.group.language
        if not asserted(target, passages, language):
            return False
        if self._about_overlap > 0:
            asks = shared_lemmas(
                candidate.question_text,
                content("\n".join(passages), language),
                language,
            )
            if asks is not None:
                readings.append(Measurement("about", asks, self._about_overlap))
        if not about(candidate.question_text, passages, language, self._about_overlap):
            log.info(
                "not rescuing %r: the passages are not about what it asks",
                candidate.question_text,
            )
            return False
        entailed = self._entailed(target, passages)
        if entailed is None:
            backed = self._verifier.supports(
                candidate.question_text, target, passages, candidate.thread
            )
        else:
            # The encoder's own probability, which the threshold used to
            # discard. It is the one reading in this pipeline a model
            # produced rather than a rule, and the reason `nlp.entailment`
            # returns a number instead of a verdict.
            readings.append(
                Measurement("entailment", entailed, self._entailment_threshold)
            )
            backed = entailed >= self._entailment_threshold
        if backed:
            log.info(
                "keeping %r: recall missed it but the passages support %r",
                candidate.question_text,
                target,
            )
        return backed

    def _entailed(self, target: str, passages: Sequence[str]) -> float | None:
        """How strongly an encoder finds the answer entailed by any one passage.

        The probability rather than the verdict, so the caller can both
        decide and record what it decided from. None when no entailment
        model is configured, which leaves the judgement to the served model
        exactly as before.

        One passage at a time, and the best of them wins. Joining them is
        what a served model is shown, because a served model reads a list;
        an NLI model was trained on one premise and one hypothesis, and a
        premise of several passages joined is both longer than some heads
        accept and a worse question than the one being asked. An answer is
        supported when SOME passage supports it.
        """
        if self._entailment is None:
            return None
        verdicts = self._entailment.judge_all(
            [(passage, target) for passage in passages]
        )
        return max((one.entailment for one in verdicts), default=0.0)

    def _corpus(
        self, candidate: Candidate, embedding: list[float]
    ) -> Callable[[], Sequence[str]] | None:
        """The probe of the rest of the corpus, for what its passages do not settle.

        The one claim in this dataset that is about the whole corpus rather
        than about the passages a question cites. Every other gate is right
        to read the citation alone - what is being measured is the dataset
        and not a retriever - but "there is no answer to this anywhere" is
        not a property of two passages, and a question wrongly carrying it
        marks a correct chatbot wrong, which is the one failure the gates
        exist to stop.

        Costs one probe and one call, on the unanswerable share and on a
        short search query, whose keywords another passage may answer
        differently. None where no probe is configured.
        """
        if self._elsewhere is None or self._elsewhere_passages <= 0:
            return None
        elsewhere = self._elsewhere
        language = candidate.group.language

        def probe() -> Sequence[str]:
            """The passages the question does not cite, nearest first."""
            return elsewhere(
                sorted(content(candidate.question_text, language)),
                language,
                [passage.id for passage in candidate.group.resting],
                self._elsewhere_passages,
                embedding,
            )

        return probe

    def _near(
        self,
        embedding: list[float],
        seen: Sequence[CheckedQuestion],
        candidate: Candidate,
    ) -> list[Neighbour]:
        """The accepted questions of each kind that can refuse this one.

        Stored or written earlier in this run, in the candidate's language,
        for each answerability `rivals` names. Probed for apart, because the
        nearest question of any kind is often one that cannot refuse this
        one, and it would hide the one that can.

        The nearest of each kind, and beside it every question this run
        wrote that is over the lowest bar a pair can be held to. The bar is
        set by what the two cite, so a closer question on another fact can
        sit under its bar while a farther one on this question's own fact is
        over its own: `deciding` reads them all. The stored questions are
        probed for the nearest alone.

        ponytail: every candidate is scored against everything `seen`, so a
        topic costs O(n^2) cosines. Upgrade: hold `seen` as one matrix and
        score it in one product.
        """
        language = candidate.group.language
        shared = self._shared_threshold
        lowest = self._threshold if shared is None else min(self._threshold, shared)
        found: list[Neighbour] = []
        for answerable in rivals(candidate.answerable):
            near = self._nearest(embedding, language=language, answerable=answerable)
            over: list[Neighbour] = []
            for other in seen:
                if (
                    other.embedding is None
                    or other.language != language
                    or other.answerable != answerable
                ):
                    continue
                score = cosine(embedding, other.embedding)
                written = Neighbour(
                    other.question_text,
                    other.answerable,
                    score,
                    fact_ids=frozenset(other.fact_ids),
                    language=other.language,
                    passage_ids=frozenset(other.passage_ids),
                )
                if near is None or score > near.similarity:
                    if near is not None and near.similarity >= lowest:
                        over.append(near)
                    near = written
                elif score >= lowest:
                    over.append(written)
            if near is not None:
                found.append(near)
            found.extend(over)
        return found

    @staticmethod
    def _verdict(
        candidate: Candidate,
        failed: tuple[str, str] | None,
        embedding: list[float] | None,
        long_answer: int = LONG_ANSWER_CHARS,
        form: str | None = None,
        ran: Sequence[str] = (),
        readings: Sequence[Measurement] = (),
        abstained: Sequence[str] = (),
        settled: Settled | None = None,
    ) -> CheckedQuestion:
        """Assembles one judged question, kept whichever way it went.

        `form` is the one the answer turned out to fit, of those its type
        will take. Stored rather than the asked-for one, because it is what
        the gates read it against and a row saying otherwise could not be
        re-checked to the same verdict.

        `ran` is every gate that read it and `readings` is what the ones
        that MEASURED something read.
        """
        code, reason = failed if failed else (None, "")
        if code:
            log.info("rejected %r: %s (%s)", candidate.question_text, reason, code)
        kind = relabelled(
            candidate.spec.name,
            (form or candidate.spec.form) if candidate.answerable else None,
            candidate.target_answer,
            candidate.group.language,
        )
        # A count of what the fact asked about lists is looked up, not summed.
        if spec(kind).derived == Derivation.ARITHMETIC and counts_a_list(
            candidate.question_text,
            candidate.target_answer,
            candidate.group.statements,
            candidate.group.language,
        ):
            kind = QuestionType.FACTOID
        stored_kind = stored(candidate.kind, len(candidate.group.resting))
        return CheckedQuestion(
            question_text=candidate.question_text,
            target_answer=candidate.target_answer,
            answerable=candidate.answerable,
            criteria=candidate.group.criteria(
                len(candidate.target_answer) if candidate.target_answer else None,
                follows=candidate.follows,
                long_answer=long_answer,
                kind=stored_kind,
            ),
            language=candidate.group.language,
            status=QuestionStatus.REJECTED if code else QuestionStatus.ACCEPTED,
            rejected_reason=code,
            fact_ids=tuple(fact.id for fact in candidate.group.facts),
            answer_explanation=candidate.answer_explanation,
            passage_ids=tuple(passage.id for passage in candidate.group.resting),
            embedding=embedding,
            thread_position=candidate.thread_position,
            question_type=kind,
            # The stored kind's, so a count stored as the lookup it is
            # carries a lookup's level rather than the analysis it skipped.
            cognitive_level=spec(kind).level,
            # An unanswerable question has no answer, so it has no form: the
            # column says what shape the answer takes and there is none.
            answer_form=(form or candidate.spec.form) if candidate.answerable else None,
            planned_difficulty=candidate.planned_difficulty,
            categories=candidate.categories,
            gates_ran=tuple(ran),
            readings=tuple(readings),
            gates_abstained=tuple(abstained),
            settled_as=settled.verdict if settled else None,
            settled_by=settled.quote if settled else None,
            kind=stored_kind,
        )
