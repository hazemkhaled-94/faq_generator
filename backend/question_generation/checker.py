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
  explanation_unusable  free: the long answer is the wrong length, asserts a
                  number the passages do not carry, or only restates the key
  asks_nothing_new  free: a follow-up citing nothing its root did not, so a
                  thread asks one fact twice
  off_thread      free: a follow-up resting on no passage the turn before it
                  used, so the conversation changed subject
  duplicate       one index probe against the questions already accepted
  answerable_after_all  the same probe, when an unanswerable question has a
                  twin the corpus does answer; or the round trip
  leaks_source    free where the title is quoted, in the structural step;
                  the phrasing judge's otherwise
  unanchored      a question nobody could have asked without the passage
  not_recoverable  the answer is not in the evidence the question cites
  answer_incomplete  the key names much less than the round trip found
  answerable_elsewhere  one corpus-wide passage probe and a second call, on
                  the unanswerable share only: a passage it does not cite
                  answers it. Cosine over passages.embedding where the corpus
                  has been embedded, shared lemmas where it has not

The free ones are in `gates`, which imports no client; the calls are the
`verifier`'s and `phrasing`'s. Recoverability is the one no similarity
measure makes: it asks whether the answer can be got back out of the
passages, which is what a question is for, and a paraphrase, a decomposition
and a resolved pronoun all survive it where a threshold would not.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

from confidence import Measurement
from database.qa_generator import (
    Derivation,
    QuestionRejection,
    QuestionStatus,
)
from nlp.analysis import content, pointing
from nlp.embedding import Embedder, cosine
from question_generation.gates import (
    BOUNDS,
    COVERAGE,
    ENTAILMENT_OVERLAP,
    EXPLANATION_CHARS,
    NAMES_SOMETHING,
    OFF_TOPIC_OVERLAP,
    OVERLAP,
    about,
    adds_up,
    agrees,
    anchored,
    asserted,
    cites_source,
    deciding,
    explains,
    incomplete,
    moves_on,
    near_verdict,
    on_topic,
    restates,
    rivals,
    same_material,
    shared_lemmas,
    structural,
    subject,
    typed,
)
from question_generation.models import (
    LONG_ANSWER_CHARS,
    Candidate,
    CheckedQuestion,
    Neighbour,
)
from question_generation.types import GATES, PASSED, REFUSED, annotation
from question_generation.verifier import Reading, Verifier

log = logging.getLogger(__name__)

#: The gate order, and what one gate's verdict is called beside the others.
#: Declared in `types`, which loads neither the embedder nor the verifier,
#: so the api can read a stored question's sequence.
__all__ = ["GATES", "PASSED", "REFUSED", "QuestionChecker", "annotation"]


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
        # the gates that ARE measurements write here.
        readings: list[Measurement] = []
        # And the judgements that were asked for and could not be had. An
        # abstention leaves no other trace: the checker rejects on False and
        # an abstention is None, so a gate that could not run reads exactly
        # like one that passed and the question is ACCEPTED.
        abstained: list[str] = []
        failed, form = structural(
            question_text=candidate.question_text,
            target_answer=candidate.target_answer,
            answerable=candidate.answerable,
            language=candidate.group.language,
            statements=candidate.group.statements,
            forms=candidate.spec.forms,
            bounds=self._bounds,
            titles=candidate.group.titles,
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
            )

        if failed:
            return done(failed)

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

        ran.append("round_trip")
        return done(self._round_trip(candidate, form, embedding, readings), embedding)

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
        if not moves_on(cited, candidate.root_facts):
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
                    "it rests on no passage the turn before it used, so it "
                    "changes the subject rather than continuing"
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

    def _recovered(self, candidate: Candidate) -> str | None:
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
        marks a correct chatbot wrong - the verdict `_answered_elsewhere`
        refuses to let an extractor make alone. It is not asked here for the
        same reason, and asking it would buy nothing: a span it does not
        find falls through to the verifier regardless.
        """
        if (
            self._extractive is not None
            and candidate.answerable
            and not candidate.thread
        ):
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
                return found.text
        return self._verifier.read(
            candidate.question_text,
            candidate.group.passages,
            candidate.thread,
        ).recovered

    def _round_trip(
        self,
        candidate: Candidate,
        form: str,
        embedding: list[float],
        readings: list[Measurement],
    ) -> tuple[str, str] | None:
        """Asks whether the passages give the answer back."""
        # A derived answer is not in the passages and is not meant to be.
        # Asking recall for it is asking the verifier to contradict the
        # type's own directive - `aggregation` says the total must be
        # something the material does not write down.
        #
        # Ahead of the recall call and not behind it, because `_computable`
        # does not read what that call returns.
        if candidate.answerable and candidate.spec.derived:
            return self._computable(candidate, candidate.target_answer or "")

        read = Reading(recovered=self._recovered(candidate))

        if candidate.answerable:
            target = candidate.target_answer or ""
            # What the verifier got back, against what the key claims, on
            # the same content lemmas `agrees` compares. Recorded whichever
            # way the verdict went, because `agrees` has several branches
            # and no single threshold - this is the reading a reviewer
            # wants beside the verdict, not a restatement of it.
            if read.recovered is not None:
                language = candidate.group.language
                recall = shared_lemmas(
                    target, content(read.recovered, language), language
                )
                if recall is not None:
                    readings.append(Measurement("recall", recall, self._overlap))
            if read.recovered is None:
                if self._backed(candidate, target, readings):
                    return None
                return (
                    QuestionRejection.NOT_RECOVERABLE,
                    "the verifier could not find the answer in the cited passages",
                )
            if not agrees(
                read.recovered,
                target,
                candidate.group.language,
                form,
                self._overlap,
                candidate.question_text,
            ):
                if self._backed(candidate, target, readings):
                    return None
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
            ):
                return (
                    QuestionRejection.ANSWER_INCOMPLETE,
                    (
                        f"the target answer {target!r} names much less than "
                        f"the verifier found in the same passages, "
                        f"{read.recovered!r}"
                    ),
                )
            return None

        # A recovery that only says the question back is not an answer: a
        # `why` the passage gives no reason for comes back as the rule it
        # asks about, and declining that question is what a chatbot should
        # do. `restates` is the reading the key is held to the same way.
        if read.recovered is not None and not restates(
            candidate.question_text, read.recovered, candidate.group.language
        ):
            return (
                QuestionRejection.ANSWERABLE_AFTER_ALL,
                f"the cited passages answer it after all, with {read.recovered!r}",
            )
        return self._corpus(candidate, embedding)

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
            # Done here rather than asked, when the answer is a figure. A
            # total has a right value rather than a likely one, and a model
            # asked whether two numbers come to a third is being asked to
            # agree. None is an answer this cannot read - a total in words, a
            # range, a date - and falls through to the model below.
            computed = adds_up(target, candidate.group.passages)
            if computed is True:
                return None
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
    ) -> tuple[str, str] | None:
        """Asks whether the rest of the corpus answers what its passages do not.

        The one claim in this dataset that is about the whole corpus rather
        than about the passages a question cites. Every other gate is right
        to read the citation alone - what is being measured is the dataset
        and not a retriever - but "there is no answer to this anywhere" is
        not a property of two passages, and a question wrongly carrying it
        marks a correct chatbot wrong, which is the one failure the gates
        exist to stop.

        Costs one probe and one call, on the unanswerable share only.
        """
        if self._elsewhere is None or self._elsewhere_passages <= 0:
            return None
        language = candidate.group.language
        passages = self._elsewhere(
            sorted(content(candidate.question_text, language)),
            language,
            [passage.id for passage in candidate.group.resting],
            self._elsewhere_passages,
            embedding,
        )
        if not passages:
            return None
        if not self._answered_elsewhere(candidate, passages):
            return None
        read = self._verifier.read(candidate.question_text, passages, candidate.thread)
        if read.recovered is None:
            return None
        return (
            QuestionRejection.ANSWERABLE_ELSEWHERE,
            (
                f"a passage it does not cite answers it, with "
                f"{read.recovered!r}, so the corpus is not silent about this"
            ),
        )

    def _answered_elsewhere(
        self, candidate: Candidate, passages: Sequence[str]
    ) -> bool:
        """Whether any uncited passage looks like it answers this question.

        This is where an extractive reader belongs, and the recall half is
        not. There the span had to be compared against a target the writer
        had composed, and a literal substring loses that comparison by
        construction. Here **there is no target**: the only question is
        whether some passage answers this at all, which is SQuAD 2.0's own
        task, no-answer head and all.

        It decides only that nothing answers the question, which is what a
        SQuAD 2.0 head was trained to say. A span found is not a rejection:
        the verifier is still asked, because rejecting here marks a correct
        chatbot wrong and that verdict is not one an extractor should make
        alone.

        True where no reader is configured, which leaves the gate exactly as
        it was.
        """
        if self._extractive is None or candidate.thread:
            return True
        found = self._extractive.answer(
            candidate.question_text, passages, self._extractive_confidence
        )
        if found is None:
            log.debug(
                "no uncited passage answers %r; not asking the verifier",
                candidate.question_text,
            )
            return False
        return True

    def _near(
        self,
        embedding: list[float],
        seen: Sequence[CheckedQuestion],
        candidate: Candidate,
    ) -> list[Neighbour]:
        """The nearest accepted question of each kind that can refuse this one.

        Stored or written earlier in this run, in the candidate's language,
        one per answerability `rivals` names. Probed for apart, because the
        nearest question of any kind is often one that cannot refuse this
        one, and it would hide the one that can.

        ponytail: every candidate is scored against everything `seen`, so a
        topic costs O(n^2) cosines. Upgrade: hold `seen` as one matrix and
        score it in one product.
        """
        language = candidate.group.language
        found: list[Neighbour] = []
        for answerable in rivals(candidate.answerable):
            near = self._nearest(embedding, language=language, answerable=answerable)
            for other in seen:
                if (
                    other.embedding is None
                    or other.language != language
                    or other.answerable != answerable
                ):
                    continue
                score = cosine(embedding, other.embedding)
                if near is None or score > near.similarity:
                    near = Neighbour(
                        other.question_text,
                        other.answerable,
                        score,
                        fact_ids=frozenset(other.fact_ids),
                        language=other.language,
                        passage_ids=frozenset(other.passage_ids),
                    )
            if near is not None:
                found.append(near)
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
        return CheckedQuestion(
            question_text=candidate.question_text,
            target_answer=candidate.target_answer,
            answerable=candidate.answerable,
            criteria=candidate.group.criteria(
                len(candidate.target_answer) if candidate.target_answer else None,
                follows=candidate.follows,
                long_answer=long_answer,
            ),
            language=candidate.group.language,
            status=QuestionStatus.REJECTED if code else QuestionStatus.ACCEPTED,
            rejected_reason=code,
            fact_ids=tuple(fact.id for fact in candidate.group.facts),
            answer_explanation=candidate.answer_explanation,
            passage_ids=tuple(passage.id for passage in candidate.group.resting),
            embedding=embedding,
            thread_position=candidate.thread_position,
            question_type=candidate.spec.name,
            cognitive_level=candidate.spec.level,
            # An unanswerable question has no answer, so it has no form: the
            # column says what shape the answer takes and there is none.
            answer_form=(form or candidate.spec.form) if candidate.answerable else None,
            planned_difficulty=candidate.planned_difficulty,
            gates_ran=tuple(ran),
            readings=tuple(readings),
            gates_abstained=tuple(abstained),
        )
