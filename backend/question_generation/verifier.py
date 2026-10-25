"""The second model, asked to get the answer back out of the passages.

Recoverability comes out of one call here, and may cost a second: recalling
an answer cold and checking one put in front of you are different tasks.
`read` asks for the answer; when that comes back empty or different,
`supports` shows the model the answer and asks only whether the passages
back it.

A question written to have no answer is asked something else. `settles`
asks whether the passages settle it at all - by stating the answer, by
refuting its premise, or by a general rule that covers its case - because a
question the material refutes is answered, and "not stated" is not "no
answer".

Two things are load-bearing. The verifier is meant to be a different model
from the writer, because a model marking its own work agrees with itself. And
it sees only the cited passages, never the corpus: what is being measured is
the dataset, not a retriever.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field

from confidence import Measurement
from llm.client import Client

#: Bumped whenever a prompt here changes what the round trip asks for.
#: Version 1 is what these have always been; they had no version at all
#: until the gate verdicts needed to say which prompt reached them, and a
#: run recorded under no version cannot be told from one recorded under
#: the next. Pinned by `tests/static/test_prompts_pinned.py`.
PROMPT_VERSION = "15"

#: The version of `_STATED` alone, so a change to it re-asks nothing `rejudge`
#: keys on PROMPT_VERSION. Pinned by `tests/static/test_prompts_pinned.py`.
STATED_VERSION = "1"

_VERIFY = """ROLE
You are an independent verifier for a document-search chatbot's test set. You
answer a test question from the material it was drawn from, without having
seen the answer somebody wrote for it.

ACTION
Answer the QUESTION using ONLY the PASSAGES, say whether they gave you the
answer at all, and, where it asks why, say whether the passages give a
reason.

STEPS
1. Read the passages.
2. Read the question, and the conversation before it when there is one.
3. Look for the answer across ALL the passages, not only the first. It may be
   spread over two sentences or worded differently from the question.
4. If you found it, set `in_passage` true and write it out in the words of
   the passages.
5. If you would need something the passages do not contain, set `in_passage`
   false and leave `answer` empty.
6. Where the question asks why, or what something is for, say whether the
   passages give a reason: something they say about why the rule is there,
   beyond the rule itself. A rule said again with "because" is no reason.

CONTEXT
You have no knowledge outside the passages and may use none.

Saying it is not in the passages is a correct answer whenever it is true, and
inventing one is the failure. But so is refusing an answer that IS there
because it took two sentences to find: look before you decline.

Besides the answer, this call asks only whether a why has a reason to give,
because a key saying the rule again marks a chatbot that gives the real
reason wrong. Three judgements about the question's own phrasing used to
share it, and what that cost is measured in `evaluation/README.md`: answered
here they were right 7 times out of 7 in English and 6 out of 12 in German,
in a call whose recall half is good in both. They are `gates.subject`,
`gates.cites_source` and `phrasing.py` now.

EXAMPLES
IN PASSAGE:     passages "Requests are answered within 48 hours." and "The
                          48 hours count working days only."
                question "How long is allowed for answering a request?"
                answer   "48 hours"
NOT IN PASSAGE: same passages
                question "How long is allowed on a public holiday?"
                (the passages never mention public holidays)
NO REASON:      passages "The shop only accepts returns that were announced
                          before sending."
                question "Why must a return be announced before the parcel is
                          sent?"
                (the rule, and nothing on why it is there)

FORMAT
- `in_passage` is true when the passages give the answer. READING IS ALLOWED:
  the answer may be spread over two sentences, worded differently from the
  question, or put together from two statements that are both in the
  passages. Doing that is reading them, not guessing.
- It is false when you would need something the passages do not contain - a
  fact you know from elsewhere, a number you would have to estimate or
  round, a party or a period they never name.
- Answer only when the passages answer the question as it is asked, not a
  narrower one: passages giving what card payments in a foreign currency
  cost do not say what card payments abroad cost.
- `answer` is the answer, taken from the passages, when in_passage is true.
  Leave it empty otherwise. IN THE WORDS OF THE PASSAGES, and so in their
  language, whatever it is: an answer translated into any other language is
  compared against a target in the material's own and agrees with nothing.
- `reason_given` is for a question asking why or what for (step 6): true when
  the passages give a reason beyond the rule asked about, false when all they
  give is the rule itself, however it is worded. True for any other question.
"""


_SUPPORT = """ROLE
You are an independent verifier for a document-search chatbot's test set. You
check one proposed answer against the material it claims to come from.

ACTION
Say whether these PASSAGES support this specific ANSWER to this QUESTION.

STEPS
1. Read the passages, then the question and the answer proposed for it.
2. Look for what the passages say about what the question asks.
3. Compare that with the answer, allowing for wording: a paraphrase, another
   inflection, a shorter form, or the same thing said across two sentences.
4. Answer true only when the passages say what the answer says.

CONTEXT
You are not writing an answer and you are not judging whether it is the best
one. One thing only: do these passages say what this answer says?

You have no knowledge outside the passages. An answer that is true in the
world but that these passages do not give is not supported.

The passages and the answer may be in any language, and the examples below
are in English only because these instructions are. Judge what they say.

EXAMPLES
  TRUE:  passages "Requests are answered within 48 hours."
         answer   "48 hours"
  TRUE:  passages "The site manager approves every change."
         answer   "the site manager"
  FALSE: passages "Requests are answered within 48 hours."
         answer   "4 hours"
  FALSE: passages "Requests are answered within 48 hours."
         answer   "within 48 hours, on working days"
         (the working-day part is not in the passages)

FORMAT
Return `supported`, true or false, and nothing else.

- `supported` is true when the passages say what the answer says. The wording
  does not have to match, and an answer that puts together two statements the
  passages both make counts.
- `supported` is false when the passages say something DIFFERENT - another
  number, another party, another period, another condition - or when they do
  not address it at all. A different number is never a paraphrase: if the
  answer says 4 hours and the passages say 48 hours, that is false.
"""


_COMPUTES = """ROLE
You are an independent verifier for a document-search chatbot's test set. You
check one answer that had to be CALCULATED from the material.

ACTION
Say whether this ANSWER can be worked out from these PASSAGES.

STEPS
1. Read the passages, then the question and the answer proposed for it.
2. Work out which figures the calculation needs.
3. Find each of those figures in the passages. If one is missing, answer
   false.
4. Do the arithmetic yourself.
5. Answer true only when your result is this answer.

CONTEXT
The answer is deliberately not written in the passages. It is a total, a
count or a sum that somebody has to compute from figures that ARE there.
That it does not appear is expected and is not a reason to say no.

You have no knowledge outside the passages. Do not supply a missing figure
from anywhere else.

The passages and the answer may be in any language, and the examples below
are in English only because these instructions are.

EXAMPLES
  TRUE:  passages "The northern site employs 40 people." and "The southern
                   site employs 25 people."
         answer   "65"
  FALSE: same passages, answer "68"           (the arithmetic gives 65)
  FALSE: passages naming only the northern site, answer "65"
                                               (the other figure is missing)

FORMAT
Return `supported`, true or false, and nothing else.

- `supported` is true when every figure the computation needs is in the
  passages AND the arithmetic gives this answer.
- It is false when a figure is missing from the passages, or when they are
  all there and come to something else.
"""


_FOLLOWS = """ROLE
You are an independent verifier for a document-search chatbot's test set. You
check one answer that had to be REASONED OUT from the material.

ACTION
Say whether this ANSWER follows from these PASSAGES.

STEPS
1. Read the passages, then the question and the answer proposed for it.
2. Work out which premises the conclusion needs.
3. Find each of those premises in the passages. If one is missing, answer
   false.
4. Reason the conclusion through from them.
5. Answer false if the passages settle the question differently, if the
   conclusion is merely plausible, or if the answer is simply STATED in the
   passages. Otherwise answer true.

CONTEXT
The answer is deliberately not written in the passages. The passages state
the premises; the answer is what they come to when put together, or what a
rule in them says about a case they do not mention. That it does not appear
is expected and is not a reason to say no.

An answer the passages state outright derived nothing, and the question is a
lookup wearing this kind's name.

The passages and the answer may be in any language, and the examples below
are in English only because these instructions are.

EXAMPLES
  TRUE:  passages "Requests are answered within 48 hours." and "The 48 hours
                   count working days only."
         answer   "a request raised on Friday is due on Tuesday, because the
                   weekend does not count"
  FALSE: same passages, answer "on Sunday"      (the weekend does not count)
  FALSE: passages naming only the 48 hours, answer "on Tuesday"
                                                (the working-day premise is
                                                 not there)

FORMAT
Return `supported`, true or false, and nothing else.

- `supported` is true when every premise the conclusion needs is in the
  passages AND the conclusion really follows from them.
- It is false when a premise is missing, when the passages settle the
  question differently, when the answer needs something you know from outside
  them, or when the passages state the answer outright.
"""

_SETTLES = """ROLE
You are an independent verifier for a document-search chatbot's test set. You
check whether the material settles a test question, before the question is
used.

ACTION
Say whether these PASSAGES settle the QUESTION, and how.

STEPS
1. Read the passages, then the question.
2. Write the best reply a careful chatbot could give from these passages
   alone, in their language, as it would answer a user. If they give it
   nothing to go on, say so.
3. Look for a statement that answers it, across ALL the passages. It may be
   spread over two sentences, worded differently from the question, or given
   in another form than the one asked for: an event where a period is asked,
   a position where a distance is asked, "any" or "every" party where one is
   asked, "never" or "always" where a condition is asked.
4. Check its premise: does a passage say that what the question takes for
   granted is not so? A rule stated with "must", "always", "never", "every"
   or "only" rules out the exception, condition, amount or party a question
   assumes it has.
5. Check for a closed list or an exception: does a passage say "only",
   "every", "no other", or name the cases a rule leaves out, so that the
   case asked about is decided by it?
6. Check for a general rule: does a passage state a rule that covers the
   case asked about, even though it never names that case?
7. Where the question asks why, or what a rule is for, look for a reason:
   something a passage says about why the rule is there, beyond the rule
   itself. A rule said again, with "because" or not, is no reason.
8. Give the first of these that holds, or `silent` when none does. Your
   reply in step 2 is the test: a reply that tells the user what the
   passages decide is not `silent`, and a reply that only repeats the rule a
   why asks about decides nothing.

CONTEXT
A chatbot asked this question is marked RIGHT for saying the material does
not answer it. Where the material does settle it, the chatbot that says so
is marked WRONG for a correct reply, and that is the failure this check
exists to stop. It costs more than losing this one test question: when a
passage answers the question, contradicts its premise, or decides its case
by a list or a rule, say so.

Settling is not the same as stating outright. "Only account holders may raise
a request" settles a question about a visitor's request - a visitor cannot
raise one - as surely as a sentence naming the visitor would.

A list or rule about the same subject that does not decide this case is
`silent`. So is a why question over a rule whose passage gives no reason: the
rule is stated, and what the question asks for is not.

You have no knowledge outside the passages and may use none. A question the
world answers and these passages do not is `silent`, and a quote must be
words the passages carry. The passages and the
question may be in any language, and the examples below are in English only
because these instructions are.

EXAMPLES
  passages "Standard requests are answered within 48 hours on working days."
           and "Only account holders may raise a request."

  answers  "How long is allowed for answering a standard request?"
  refutes  "How long is allowed for answering a request raised by a visitor?"
           (only account holders may raise one)
  rule     "How long is allowed for a standard request raised on a public
            holiday?"
           (the 48 hours count working days, which settles the holiday)
  answers  "Within how many days is a standard request answered?"
           (the passages give hours on working days, not days: the reply
           "within 48 hours on working days" answers it in another form)
  refutes  "Under what circumstances is a request from a visitor accepted?"
           (none: only account holders may raise one, which rules out the
           circumstances the question assumes)
  silent   "Through which channel is the answer to a standard request sent?"
           (no passage says, and no list or rule in them reaches it)
  silent   passage "The shop only accepts returns that were announced before
           sending."
           "Why must a return be announced before the parcel is sent?"
           (the rule, and nothing on why it is there)
  silent   passage "A standing order can be changed in online banking until
           the day before it is executed."
           "Why can a standing order not be changed on the day it is executed?"
           (the cut-off, and no reason for it)

FORMAT
Return `reply`, `quote` and `verdict`, in that order.

- `reply` is the reply of step 2.
- `quote` is the words of the passage that settle it, as they stand. Empty
  when the verdict is `silent`.
- `verdict` is one of:
  - `answers` - a passage states the answer;
  - `refutes` - a passage contradicts the question's premise, or a closed
    list or exception in one decides the case it asks about;
  - `rule` - a general rule in a passage covers the case, though no passage
    names it;
  - `silent` - none of these.
"""

_STATED = """ROLE
You are an independent verifier for a document-search chatbot's test set. You
check which of the passages a test question cites state each part of its
answer.

ACTION
List the parts a complete answer to the QUESTION gives, and quote, for each
part, the words of every PASSAGE that states it.

STEPS
1. Read the question, the conversation before it when there is one, and the
   KEY: the answer a chatbot's reply is marked against.
2. List the parts, reading them off the key and the question:
   - each value, item, condition, limit or exception the key gives in answer
     to what is asked;
   - each case, party or item the question names, as a part of its own, even
     when the key gives one answer for all of them;
   - each condition the question sets that the answer holds only under, when
     a passage is needed to tie the question's situation to the answer's rule.
3. Leave out what the key adds that the question does not ask for, a part
   that only says again in other words what another part says, and a title,
   section or document the question names only to say what it is about.
4. For each part, look in EVERY passage and quote each passage that states
   it: the sentence or clause as it stands, with the case it applies to, not
   a bare value or name. When two passages state the same part, quote both.
   A part stated in other words, in another sentence, in a list item or in a
   table row is still stated.
5. A part no passage states gets no quote. Quote only words a passage holds:
   never the key, the question or your own words.

CONTEXT
A question citing two passages is stored as one that needs both. When one
passage states every part, the other is not needed and the question is a
one-passage question; when each passage states a part the other does not, it
needs both. Your quotes decide which: each one is looked up in the passages,
so a quote no passage holds counts for none, and a quote two passages hold
counts for both. Missing a part a passage does state is as wrong as quoting
one it does not.

The passages and the question may be in any language; quote in the language
of the passages. The examples are in English only because these
instructions are.

EXAMPLES
  [1] "An account with no payment for 24 months is dormant."
  [2] "A dormant account is charged 30 EUR a year."
  question "What does an account cost a year after 24 months without a
            payment?"
  key      "30 EUR a year"
  -> "the account counts as dormant": ["An account with no payment for 24
     months is dormant."]
     "the yearly charge": ["A dormant account is charged 30 EUR a year."]

  [1] "A standing order can be changed in online banking until the day
       before it is executed."
  [2] "A direct debit can be stopped in online banking until the day before
       it is debited."
  question "Until when can a standing order be changed and a direct debit be
            stopped?"
  key      "until the day before"
  -> "changing a standing order": ["A standing order can be changed in
     online banking until the day before it is executed."]
     "stopping a direct debit": ["A direct debit can be stopped in online
     banking until the day before it is debited."]

  [1] "Returns are accepted within 30 days of delivery."
  [2] "A return is accepted within 30 days of delivery and refunded to the
       card used."
  question "Within how many days can a purchase be returned?"
  key      "within 30 days of delivery, refunded to the card used"
  -> "the return period": ["Returns are accepted within 30 days of
     delivery.", "A return is accepted within 30 days of delivery"]
     (the refund is not asked, so it is not a part)

  [1] "Orders over 50 EUR are shipped free of charge."
  [2] "Gift cards cannot be exchanged for cash."
  question "From what order value is shipping free?"
  key      "over 50 EUR"
  -> "the order value": ["Orders over 50 EUR are shipped free of charge."]

FORMAT
Return `parts`, one entry per part, in the order the key gives them.
- `part` names the part in a few words.
- `quotes` holds the words of each passage that states the part, as they
  stand, one entry per passage; empty when no passage states it.
"""

#: The user messages, as the catalogue records them and the two calls below
#: render them.
_USER_JUDGE = "Passages:\n{{passages}}\n\n{{conversation}}Question: {{question}}\nAnswer: {{answer}}"
_USER_VERIFY = "Passages:\n{{passages}}\n\n{{question}}"
_USER_STATED = (
    "Passages:\n{{passages}}\n\n{{conversation}}Question: {{question}}\nKey: {{key}}"
)


_SAME = """ROLE
You are an independent reviewer for a document-search chatbot's test set. You
compare two test questions that will both be put to the chatbot.

ACTION
Say whether the two questions want the SAME ANSWER: whether one correct reply
is right for both, so a test set holding the two tests one thing twice.

STEPS
1. Read both questions, each with the answer it is keyed with.
2. Work out what each asks for: the value, the party, the rule, the condition
   or the reason its answer states.
3. Compare those, not the wording. The same rule asked from the other side,
   in other words, or about the same rule as another document states it, is
   the same answer.
4. Answer true only when one correct reply serves both.

CONTEXT
The two are in one language and sit close to each other, which is why they
are compared; being close says nothing on its own. Two questions about one
subject that ask for different things about it want two answers: what a
transfer abroad costs and how long it takes are two tests.

The questions may be in any language, and the examples below are in English
only because these instructions are. Judge what they ask.

EXAMPLES
  TRUE:  A "How long may the bank take to answer an urgent request?" - "4 hours"
         B "Within what time must an urgent support request be answered?"
           - "within 4 hours"
  TRUE:  A "Who approves a change to the shift plan?" - "the site manager"
         B "Whose approval does a change to the shift plan need?"
           - "the site manager's"
  FALSE: A "How long may the bank take to answer an urgent request?" - "4 hours"
         B "How long may it take to answer a standard request?" - "48 hours"
  FALSE: A "What does a transfer abroad cost?" - "a flat fee of 5 euros"
         B "How long does a transfer abroad take?" - "two working days"

FORMAT
Return `same`, true or false, and nothing else."""

#: The user message `same_answer` sends.
_USER_SAME = """QUESTION A: {{first}}
ANSWER A: {{first_answer}}

QUESTION B: {{second}}
ANSWER B: {{second_answer}}"""


class _Same(BaseModel):
    """Whether two questions want one answer."""

    same: bool = Field(
        description="True only when one correct reply is right for both questions."
    )


class _Supported(BaseModel):
    """Whether the passages back one proposed answer."""

    supported: bool = Field(
        description="True only when the passages say what the answer says. "
        "A different number, party or period is not support."
    )


class _Recovered(BaseModel):
    """What the verifier got back, and what it made of the question."""

    in_passage: bool = Field(
        description="True only when the passages state the answer outright. "
        "False is NOT IN PASSAGE, and is a correct answer."
    )
    answer: str = Field(
        default="",
        description="The answer, taken from the passages and in their "
        "language. Empty when in_passage is false.",
    )
    reason_given: bool = Field(
        default=True,
        description="For a question asking why or what for: True only when "
        "the passages give a reason beyond the rule asked about. True for any "
        "other question.",
    )


class _Quoted(BaseModel):
    """One part of an answer, and the passages' words that state it."""

    part: str = Field(description="The part, in a few words.")
    quotes: list[str] = Field(
        default_factory=list,
        description="The words of each passage that states this part, as they "
        "stand, one entry per passage. Empty when no passage states it.",
    )


class _Stated(BaseModel):
    """The parts a complete answer gives, with the passages stating each."""

    parts: list[_Quoted] = Field(
        default_factory=list,
        description="One entry per part a complete answer to the question "
        "gives, in the order the key gives them.",
    )


class Settling(StrEnum):
    """How the passages settle a question written to have no answer."""

    ANSWERS = "answers"
    REFUTES = "refutes"
    RULE = "rule"
    SILENT = "silent"


class _Settled(BaseModel):
    """Whether the passages settle one question, and with what words."""

    reply: str = Field(
        default="",
        description="The best reply a careful chatbot could give from these "
        "passages alone, written before the verdict.",
    )
    quote: str = Field(
        default="",
        description="The words of the passage that settle it, as they stand. "
        "Empty when the verdict is silent.",
    )
    verdict: Settling = Field(
        description="answers, refutes, rule, or silent when the passages "
        "settle nothing."
    )


@dataclass(frozen=True)
class Settled:
    """What the verifier made of a question written to have no answer.

    `quote` is what the passages said, or None where they settle nothing:
    the words that answered it are what a reviewer of the rejection needs.
    """

    verdict: Settling
    quote: str | None

    def reading(self, gate: str, *kept: str) -> Measurement:
        """This verdict as the row keeps it: 1 where it keeps the question.

        `kept` are the verdicts that keep it, `silent` unless its kind says
        otherwise, so a kept refutation reads 1 as a kept silence does. An
        opinion and not a measure, so it is stored with no margin and moves
        no confidence; it is kept so a row says what the verifier made of it,
        which a code and a log line could not.
        """
        return Measurement(
            gate,
            1.0 if self.verdict in (kept or (Settling.SILENT,)) else 0.0,
            0.5,
            opinion=True,
            version=PROMPT_VERSION,
        )


@dataclass(frozen=True)
class Reading:
    """What the verifier got back out of one question's passages.

    `recovered` is the answer, or None for NOT IN PASSAGE. `reason_given` is
    whether the passages give a why a reason beyond its own rule, which no
    overlap can say of a key restating that rule in the passage's words; True
    where nobody read it. What a question's own phrasing amounts to is read
    off its parse in `gates` and asked in `phrasing`.
    """

    recovered: str | None
    reason_given: bool = True


@dataclass(frozen=True)
class Part:
    """One part of an answer, and the words of the passages that state it."""

    name: str
    quotes: tuple[str, ...]


class Verifier:
    """A second model, asked to get the answer back out of the passages."""

    def __init__(self, client: Client) -> None:
        """Initialises the verifier with the model it asks."""
        self._client = client

    @property
    def model(self) -> str:
        """The model doing the verifying."""
        return self._client.model

    def computes(
        self,
        question: str,
        answer: str,
        passages: Sequence[str],
        thread: Sequence[tuple[str, str | None]] = (),
    ) -> bool:
        """Whether a derived answer follows from the figures in the passages.

        What an `aggregation` is judged by instead of recoverability. That
        type's answer is a total the material does not write down anywhere,
        so asking whether the passages state it refuses every one of them.

        Raises:
            ModelUnavailable: If the model could not be reached or would not
                answer in the shape.
        """
        return self._judge(_COMPUTES, question, answer, passages, thread)

    def follows(
        self,
        question: str,
        answer: str,
        passages: Sequence[str],
        thread: Sequence[tuple[str, str | None]] = (),
    ) -> bool:
        """Whether a conclusion follows from the premises in the passages.

        The entailment half of what `computes` does for arithmetic. An
        `implication` puts two statements together and an `application`
        puts a rule to a case, and in both the answer is absent from the
        material by construction - so recoverability, which asks whether
        the passages state it, would refuse every one of them.

        Raises:
            ModelUnavailable: If the model could not be reached or would not
                answer in the shape.
        """
        return self._judge(_FOLLOWS, question, answer, passages, thread)

    def supports(
        self,
        question: str,
        answer: str,
        passages: Sequence[str],
        thread: Sequence[tuple[str, str | None]] = (),
    ) -> bool:
        """Whether the passages back this exact answer, asked as a yes or no.

        The second half of the recoverability gate, and the reason that gate
        is two calls. Recalling an answer out of a passage cold is a harder
        task than checking one that is put in front of you.

        Only ever asked after `read` has failed, and only ever able to
        rescue: a question this refuses was already being refused.

        Raises:
            ModelUnavailable: If the model could not be reached or would not
                answer in the shape.
        """
        return self._judge(_SUPPORT, question, answer, passages, thread)

    def _judge(
        self,
        system: str,
        question: str,
        answer: str,
        passages: Sequence[str],
        thread: Sequence[tuple[str, str | None]],
    ) -> bool:
        """Puts one answer to the model as a yes or no under these rules.

        Written once because two gates ask it: whether the passages support
        an answer, and whether they let one be worked out. The two differ
        only in what they expect of an answer the passages do not contain.
        """
        numbered = "\n\n".join(
            f"[{position}] {passage}" for position, passage in enumerate(passages, 1)
        )
        conversation = (
            "\n".join(f"Q: {q}\nA: {a or 'not in the material'}" for q, a in thread)
            + "\n"
            if thread
            else ""
        )
        got = self._client.answer(
            system=system,
            user=(
                _USER_JUDGE.replace("{{passages}}", numbered)
                .replace("{{conversation}}", conversation)
                .replace("{{question}}", question)
                .replace("{{answer}}", answer)
            ),
            shape=_Supported,
            prompt_version=PROMPT_VERSION,
        )
        return got.supported

    def same_answer(
        self, first: tuple[str, str | None], second: tuple[str, str | None]
    ) -> bool:
        """Whether two questions, each with its key, want one answer.

        What the release reads twins off where no measure can: two questions
        restating one rule as two documents state it share no citation and
        sit no closer than a pair asking two things. A question written to
        have no answer is put with "not in the material" for its key.

        Raises:
            ModelUnavailable: If the model could not be reached or would not
                answer in the shape.
        """
        got = self._client.answer(
            system=_SAME,
            user=(
                _USER_SAME.replace("{{first}}", first[0])
                .replace("{{first_answer}}", first[1] or "not in the material")
                .replace("{{second}}", second[0])
                .replace("{{second_answer}}", second[1] or "not in the material")
            ),
            shape=_Same,
            prompt_version=PROMPT_VERSION,
        )
        return got.same

    def settles(self, question: str, passages: Sequence[str]) -> Settled:
        """Whether these passages settle a question written to have none.

        What an unanswerable question is judged by instead of `read`. Stated
        outright is one way to be answered of three: a premise the passages
        refute and a case a list or a rule in them covers are answered too,
        and `read` comes back "not in the passages" for both.

        No conversation: an unanswerable question is never a follow-up.

        Raises:
            ModelUnavailable: If the model could not be reached or would not
                answer in the shape.
        """
        numbered = "\n\n".join(
            f"[{position}] {passage}" for position, passage in enumerate(passages, 1)
        )
        got = self._client.answer(
            system=_SETTLES,
            user=_USER_VERIFY.replace("{{passages}}", numbered).replace(
                "{{question}}", f"Question: {question}"
            ),
            shape=_Settled,
            prompt_version=PROMPT_VERSION,
        )
        silent = got.verdict == Settling.SILENT
        return Settled(
            verdict=got.verdict,
            quote=None if silent else (got.quote.strip() or None),
        )

    def read(
        self,
        question: str,
        passages: Sequence[str],
        thread: Sequence[tuple[str, str | None]] = (),
    ) -> Reading:
        """Answers one question from these passages.

        Raises:
            ModelUnavailable: If the model could not be reached or would not
                answer in the shape.
        """
        numbered = "\n\n".join(
            f"[{position}] {passage}" for position, passage in enumerate(passages, 1)
        )
        # A follow-up is asked in a conversation, so it is judged in one. Read
        # alone, `And for an urgent one?` has no answer in any passage.
        asked = (
            "\n".join(f"Q: {q}\nA: {a or 'not in the material'}" for q, a in thread)
            + f"\nQ: {question}"
            if thread
            else f"Question: {question}"
        )
        got = self._client.answer(
            system=_VERIFY,
            user=_USER_VERIFY.replace("{{passages}}", numbered).replace(
                "{{question}}", asked
            ),
            shape=_Recovered,
            prompt_version=PROMPT_VERSION,
        )
        return Reading(
            recovered=(
                got.answer.strip() if got.in_passage and got.answer.strip() else None
            ),
            reason_given=got.reason_given,
        )

    def stated(
        self,
        question: str,
        key: str,
        passages: Sequence[str],
        thread: Sequence[tuple[str, str | None]] = (),
    ) -> tuple[Part, ...]:
        """The parts a complete answer gives, each with the quotes stating it.

        Raises:
            ModelUnavailable: If the model could not be reached or would not
                answer in the shape.
        """
        numbered = "\n\n".join(
            f"[{position}] {passage}" for position, passage in enumerate(passages, 1)
        )
        conversation = (
            "\n".join(f"Q: {q}\nA: {a or 'not in the material'}" for q, a in thread)
            + "\n"
            if thread
            else ""
        )
        got = self._client.answer(
            system=_STATED,
            user=(
                _USER_STATED.replace("{{passages}}", numbered)
                .replace("{{conversation}}", conversation)
                .replace("{{question}}", question)
                .replace("{{key}}", key)
            ),
            shape=_Stated,
            prompt_version=STATED_VERSION,
        )
        return tuple(
            Part(
                one.part.strip(),
                tuple(quote.strip() for quote in one.quotes if quote.strip()),
            )
            for one in got.parts
        )
