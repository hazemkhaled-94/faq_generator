"""Writing one question from a sample of facts, to the plan that asked for it.

Three kinds of call, one rendering. A question the facts answer, a question
they deliberately do not, and the question somebody would ask next. Each is
one call against one sample with one shape back.

What each asks for comes from the plan's type, in `types.py`. Nothing about a
domain is written here: a type says what kind of thing to ask for, and the
same thirteen types are askable of a manual, a contract or a report.

The writer is shown the passage each fact came from, and says which facts its
question needs. Neither was true of the first version of this module, and both
failures had the same cause: a single atomic statement is one triple, so the
only question that can be built out of it is that statement with one part
replaced by a question word. The passage is what a question can be phrased
from; the fact is what it has to be answered by.
"""

from __future__ import annotations

import json
import logging
import re

from pydantic import BaseModel, Field

from database.qa_generator import QuestionKind
from llm.client import Client
from llm.prompt import fill
from nlp.analysis import asked
from nlp.models import named
from nlp.pipelines import pipeline
from question_generation.config import OUT_OF_CORPUS, UNANSWERABLE_CATEGORIZATION
from question_generation.kinds import KINDS, _Answered, stored
from question_generation.models import Candidate, Category, FactGroup, kind
from question_generation.planning import Plan
from question_generation.types import PROMPT_VERSION, READS, TypeSpec

__all__ = ["PROMPT_VERSION", "QuestionWriter"]

log = logging.getLogger(__name__)

_PERTURB = (
    """ROLE
You are a test-question writer. The questions you write measure whether a
document-search chatbot handles a question it should not simply answer,
instead of inventing an answer.

ACTION
{{action}}

STEPS
1. Read the FACT and the PASSAGE it came from.
2. {{change}}
3. {{check}}
4. Read the question back against every rule under FORMAT.

CONTEXT
You are given one FACT and the PASSAGE it came from, and nothing else. The
person you are writing for has not read the passage. They do not know which
document answers them - finding that out is the whole reason they are asking.

THE KIND OF QUESTION TO ASK: {{asks}}

EXAMPLES
{{examples}}
FORMAT
Return `question`, and nothing else.

"""
    + READS
    + """{{must}}

- A question about an unrelated subject tests nothing, because any chatbot
  declines that one.
"""
)

#: Step 2 for a slot told an unanswerable kind, whose block says what to write.
_TOLD = (
    "Write a question as the WHAT MAKES IT A TEST block under the passages describes."
)

#: The ACTION of a slot told no kind. A kind's ACTION says only what to
#: write: whether it must be plausible is its description's to say, and a
#: nonsensical one must not be.
_UNTOLD = (
    "Write ONE test question that the material does NOT answer anywhere, and that\n"
    "is still a plausible thing to ask of it."
)

#: The worked example's fact and passage, which the out-of-reach and the
#: refuted kinds share.
_SUPPORT_DESK = """  FACT: A standard support request is answered within 48 hours.
  PASSAGE: Standard requests are answered within 48 hours on working days.
  Only account holders may raise a request. These times are set out in the
  service agreement.

  WRONG  "How long does a standard support request take to answer?"
         (that is the fact itself, and it is answered)
"""

#: The two wrong questions every kind shares: one any chatbot declines, and
#: one naming its source.
_UNRELATED = """  WRONG  "What is the top speed of a swallow?"
         (nothing to do with this material; declining it tests nothing)
"""
_SOURCED = """  WRONG  "What does the service agreement say about public holidays?"
         (names its source, which no asker would know to do)
"""

#: What the passages beside are told under a kind that must be refuted or
#: answered by case: only what the probe checks for every kind.
_AS_ASKED = "none of them may answer your question as asked"

#: Out-of-corpus's lines, version 28's text, which a slot told no kind is
#: written with too.
_MOVED = {
    "{{action}}": "Write ONE test question that the material does NOT answer anywhere.",
    "{{check}}": """Answer your own question from the fact and the passage. They ANSWER it
   when they state the answer, and ALSO when they:
   - contradict or refute its premise - a question about something the
     material says does not happen is answered "it does not";
   - name a closed list or rule its case falls outside - "only", "every",
     "no other", in whatever language the material is written - which
     answers it "nobody else" or "not there";
   - state a general rule that covers its case.
   If either of them answers it in any of these ways, you have written the
   wrong question - go back to step 2.""",
    "{{examples}}": _SUPPORT_DESK
    + """  WRONG  "How long is allowed for answering a request raised by a visitor?"
         (only account holders may raise one: the material answers that a
          visitor cannot, which is an answer)
  WRONG  "How long is allowed for answering a standard support request raised
          on a public holiday?"
         (the 48 hours count working days - a general rule that settles the
          holiday)
"""
    + _UNRELATED
    + _SOURCED
    + """
  RIGHT  "Through which channel is the answer to a standard support request
          sent?"
         (same subject, a detail no fact, list or rule in the material
          settles)
""",
    "{{must}}": """- IT MUST NOT BE ANSWERABLE from the fact or the passage. If reading either
  answers your question - states the answer, contradicts its premise, or
  settles it by a closed list or a general rule - you have written the wrong
  question.""",
    "{{fact}}": "the question moves this one detail out of reach",
    "{{reads}}": "no sentence of it may answer your question, contradict its "
    "premise or cover its case by a rule.",
    "{{holds}}": "the same holds for every sentence of them",
}

#: What an unanswerable question's kind changes in the writer's two prompts
#: and in what the passages beside are told, by the kinds of UAEval4RAG
#: (Peng et al., ACL 2025, Section 3.1) as `UNANSWERABLE_CATEGORIZATION`
#: names them; `written_as` says which a slot is written with.
_KINDS: dict[str, dict[str, str]] = {
    "out-of-corpus": _MOVED,
    "false-presupposition": {
        "{{action}}": "Write ONE test question that takes for granted something "
        "the material says\nis not so.",
        "{{check}}": """Find the sentence of the fact or the passage that says what your question
   takes for granted is not so. If there is none, if it only fails to mention
   it, or if either of them states an answer to the question as asked, you
   have written the wrong question - go back to step 2.
   Then look the other way: if any sentence of the fact, the passage or the
   passages beside it says that what your question takes for granted IS so in a
   case it names - an exception, an option, a party or a period it allows,
   however the material words it - you have written the wrong question - go
   back to step 2.""",
        "{{examples}}": _SUPPORT_DESK
        + """  WRONG  "Through which channel is the answer to a standard support request
          sent?"
         (the material says nothing either way: a premise it does not
          mention is not one it says is false)
"""
        + _UNRELATED
        + _SOURCED
        + """
  RIGHT  "How long does it take to answer a request a visitor raises?"
         (only account holders may raise one: what the question takes for
          granted is not so)
""",
        "{{must}}": """- IT MUST TAKE FOR GRANTED something a sentence of the fact or the passage
  says is not so in every case they name, and nothing in them may answer it as
  asked or grant it in an exception.""",
        "{{fact}}": "the question takes for granted something this or its "
        "passage says is not so",
        "{{reads}}": "one sentence of it must say that what your question takes "
        "for granted is not so, and none may answer it as asked.",
        "{{holds}}": "none of them may answer your question as asked, or say that "
        "what it takes for granted is so in a case they name",
    },
    "underspecified": {
        "{{action}}": "Write ONE test question that the material answers "
        "differently depending on\na detail the question leaves out.",
        "{{check}}": """Name the cases the fact or the passage tells apart (two kinds of account,
   two products, two periods) and the answer each gets. If they give one
   answer whatever the case, or if your question names the case, you have
   written the wrong question - go back to step 2.""",
        "{{examples}}": """  FACT: An urgent support request is answered within 4 hours.
  PASSAGE: Standard requests are answered within 48 hours on working days,
  urgent ones within 4 hours. Only account holders may raise a request.

  WRONG  "How long does an urgent support request take to answer?"
         (it names the case, and it is answered)
  WRONG  "Who may raise a support request?"
         (one answer whatever the case)
"""
        + _UNRELATED
        + """
  RIGHT  "How long does it take to answer a support request?"
         (standard and urgent requests get different times, and the
          question does not say which)
""",
        "{{must}}": """- IT MUST LEAVE OUT the detail that decides between cases the fact or the
  passage tells apart, so each case has its own answer.""",
        "{{fact}}": "the question leaves open a case this or its passage tells apart",
        "{{reads}}": "it must give a different answer for each case your question "
        "leaves open, and no sentence may say which case is meant.",
        "{{holds}}": _AS_ASKED,
    },
    # Out-of-corpus's verdict and rule, and its check after one that asks
    # whether the question could be so at all; nothing that tells it to move a
    # detail out of reach or shows it a plausible question.
    "nonsensical": _MOVED
    | {
        "{{action}}": "Write ONE test question that makes no sense as asked: it asks "
        "of a thing\nthe material names something that cannot be so of that kind "
        "of thing.",
        "{{check}}": """Say what your question asks of what. If it could be so of that thing - a
   party doing a task, a rule applying to another case, a count of things that
   come in numbers - it makes sense, and you have written the wrong question -
   go back to step 2.
   """
        + _MOVED["{{check}}"],
        "{{fact}}": "the question joins things this fact and its passage name in a "
        "way that cannot be so",
        "{{examples}}": _SUPPORT_DESK
        + """  WRONG  "How long does a standrad support reqest take to answer?"
         (a typing or grammar slip: read past it, the question is answered)
  WRONG  "Why do account holders answer standard requests within 48 hours?"
         (it swaps who does what: a false premise, and it makes sense)
  WRONG  "How many working days does a standard request take to answer?"
         (a count that fits: the material answers it)
"""
        + _UNRELATED
        + _SOURCED
        + """
  RIGHT  "Why does a working day hold an account?"
         (a day cannot hold anything, so no reason fits)
""",
    },
}

#: The verdict each shipped kind settles by, off the one place that ships
#: them, and the shipped kind each verdict is written as for a kind of
#: another name: the first of it, so out-of-corpus for `silent`.
_SHIPPED: dict[str, str] = {
    one["name"]: one["settles"]
    for one in json.loads(UNANSWERABLE_CATEGORIZATION)["categories"]
}
_BY_VERDICT: dict[str, str] = {}
for _name, _verdict in _SHIPPED.items():
    _BY_VERDICT.setdefault(_verdict, _name)


def written_as(told: Category | None) -> str:
    """The shipped kind whose lines a slot told `told` is written with.

    Its own name, where a shipped kind has it and settles as it does; else
    the shipped kind of its verdict; out-of-corpus where it is told none.
    Nonsensical is the one read by name: it shares out-of-corpus's verdict.
    """
    if told is None or told.settles is None:
        return "out-of-corpus"
    if _SHIPPED.get(told.name) == told.settles:
        return told.name
    return _BY_VERDICT[told.settles]


def _perturbation(told: Category | None) -> tuple[str, str]:
    """The unanswerable writer's system prompt and user template for one kind.

    `told` is the kind the slot is told, or None: told none, a slot moves
    its fact out of reach, as before kinds; told one, it writes what its
    block describes, checked and shown examples as `written_as` says. The
    type's `{{asks}}` is left to fill.
    """
    lines = _KINDS[written_as(told)]
    system = fill(
        _PERTURB,
        lines
        | (
            {"{{change}}": OUT_OF_CORPUS, "{{action}}": _UNTOLD}
            if told is None
            else {"{{change}}": _TOLD}
        ),
    )
    return system, fill(_USER_PERTURB, lines)


_FOLLOW = """ROLE
You are a test-question writer. You write the question somebody would ask
NEXT, as the following turn of a conversation already under way.

ACTION
Write the next question in that conversation, and TWO answers to it - the
short key its reply is marked against, and an explanation for a reader who
has never seen the material.

STEPS
1. Read the CONVERSATION so far, then the FACTS and the PASSAGE.
2. Work out what somebody just told the last answer would want to know next
   about the same material.
3. Write that question, of the kind named below.
4. Write `answer`, then `explanation`.
5. Check that the FACTS answer your question, and that the conversation does
   not already.

CONTEXT
You are given the FACTS, the PASSAGE they came from, and the CONVERSATION so
far: one or more questions already asked and the answers they got. Somebody
has just been told the last answer and wants to know one more thing about the
same material.

This question is different from one asked cold, and the difference is the
point: it MAY rely on the conversation. "And for urgent requests?" is a
perfectly good follow-up. You do not have to name the subject again, because
the person you are talking to already knows it.

{{type}}

FORMAT
Rules, all of them mandatory:
- ONE QUESTION WORD, and one only. Count them before you answer. Two of
  them is two questions however it is punctuated, and joining them with
  "and" or "or" does not make them one.
- ONE question, ending in a question mark.
- It must be answered by the FACTS, like any other. A follow-up whose answer
  is not in the material tests nothing.
- NEVER SAY WHERE THE ANSWER IS. No naming or quoting a document, a report, a
  section or a heading, here as anywhere else.
- DO NOT REPEAT a question already in the conversation, and do not ask one
  the last answer already gave. It has to want something new.
- ONE THING ASKED. Do not weld two questions together with "and" because two
  facts were offered: a chatbot answering half of one is neither right nor
  wrong. If the facts have no single honest question between them, ask about
  one of them and name only the facts you used.
- ASK THE KIND OF QUESTION NAMED ABOVE, and mean it. If the facts hold no
  answer of that kind - no circumstance to give, no reason stated, two things
  that are not comparable - ask what they do hold rather than forcing the
  shape onto them. A question whose answer does not fit what it asked is
  worse than a plainer one, and the worst of all is one whose answer repeats
  it back: "Why is X done by Y?" answered "Because X is done by Y" has asked
  nothing.
- WRITE IN THE LANGUAGE NAMED UNDER THE FACTS. It is named there rather
  than left to you because a model reading a corpus that is mostly one
  language writes that language for all of it, and a question in the wrong
  language is thrown away.
- `facts` is the NUMBERS of the facts your question needs.

THE WORKED EXAMPLE ABOVE IS WRITTEN FOR A QUESTION ASKED COLD, because the
same one serves both. Take from it WHAT THE KIND ASKS FOR and WHAT ITS ANSWER
LOOKS LIKE. Ignore anything in it about naming the subject or naming both
sides: this question is the next turn of a conversation that has already
named them, and repeating them is what makes a follow-up read like a form.
"""


#: The user message both answerable kinds are asked with, as the catalogue
#: records it and `_prompt` renders it.
_USER = (
    "FACTS - your question must be answered by these:\n"
    "{{facts}}\n"
    "\n"
    "PASSAGE(S) - context only, so you know what the material is "
    "about. Phrase the question from these; never quote or name a "
    "heading or a title out of them, and never ask about anything "
    "here that the facts above do not state:\n"
    "{{passages}}\n"
    "{{profile}}"
    "\n"
    "Write the question and both answers in {{language}}.{{note}}"
)

#: What the categories a slot was dealt ask of its question, one line each:
#: the DataMorgana paper's descriptions, under the rules rather than over
#: them. A category asking for fewer than ten words does not license
#: dropping the subject a searcher has to name.
_ASKED = (
    "\nTHE QUESTION - besides every rule you were given, it must be:\n"
    "{{lines}}\n"
    "{{query}}"
    "Where one of these conflicts with a rule you were given, the rule wins.\n"
)

#: What an unanswerable slot's kind asks of its question, in place of
#: `_ASKED`: its kind is the point of the question, so it wins where a rule
#: of FORMAT would undo it, a nonsensical one over the plausible, but for the
#: two that keep a question testing anything at all.
_KIND = (
    "\nWHAT MAKES IT A TEST - it must be:\n"
    "{{lines}}\n"
    "Where it conflicts with a rule under FORMAT, it wins; two rules still hold: "
    "never name a source, and never ask about an unrelated subject.\n"
)

#: Told a slot dealt a search query, in its question block. Without it the
#: rules win over a category that asks for no punctuation, and the writer
#: ends its keywords with the question mark the rules ask of a question.
_QUERY = (
    "This one is typed into a search box: keywords, no question mark. The rule "
    "about the question mark does not apply to it; every other rule does.\n"
)

#: Who is asking, as the categories of role `user` describe them: the paper's
#: Figure 4 block, with its rule that the answer ignores the asker. Apart from
#: the question block because that rule is its own: the verifier reads the
#: question and the passages only, so an answer leaning on an asker the
#: question does not describe cannot be got back out of them.
_ASKER = (
    "\nTHE ASKER - write the question as this person would ask it:\n"
    "{{lines}}\n"
    "Use this only to write the question. The answer and the explanation must "
    "ignore it: they assume nothing about the asker that the question does not "
    "say.\n"
)

#: The note a draft told a premise is written again with, once, when its
#: premise says nothing of the asker.
_UNADDRESSED = (
    'The previous draft was "{{question}}". A reviewer found that it does not '
    "open on a premise about the asker's own situation: it names a topic or a "
    "setting, says what the asker wants to know or that they are reading or "
    "checking something, or nothing at all. Open on a short premise in which "
    "the asker states, in the first person, something they have, did, bought "
    'or plan - "I ordered a sofa last week, ...", "Meine Karte wurde gestern '
    'im Ausland gestohlen, ..." - and then ask.'
)

#: The user message an unanswerable question is asked with, its kind's
#: `{{fact}}` and `{{reads}}` filled by `_perturbation`.
_USER_PERTURB = (
    "FACT - {{fact}}:\n"
    "{{facts}}\n"
    "\n"
    "PASSAGE(S) - what the chatbot will read: {{reads}} "
    "Never quote or name a heading or a title out of them:\n"
    "{{passages}}\n"
    "{{beside}}"
    "{{profile}}"
    "\n"
    "Write the question in {{language}}.{{note}}"
)

#: The passages either side of a perturbed fact's own, which a search for
#: the question reaches as well.
_BESIDE = (
    "\nBESIDE IT - the passages either side in the same document, which the "
    "chatbot reads too; {{holds}}:\n{{texts}}\n"
)

#: Appended to the conversation for a follow-up, after the facts.
_USER_FOLLOW = "{{sample}}\n\n{{conversation}}"


def _typed(spec: TypeSpec) -> str:
    """What one question type contributes to the follow-up prompt."""
    return (
        f"WHAT TO ASK NEXT: {spec.asks}\n"
        f"{spec.guidance}\n"
        f"THE ANSWER IS {spec.answer_rule}\n\n"
        f"EXAMPLES\n{spec.example}"
    )


def _profile(categories: tuple[Category, ...]) -> str:
    """The asker block, then the question block, each only where it has lines.

    Nothing rather than an empty block, so a slot dealt no category is sent
    the message it was sent before categories existed. The asker comes
    first, as the paper's Figure 4 puts it: who is asking, then what they
    ask. A search query is told that it is exempt from the question mark,
    which the gates lift for it too. An unanswerable kind, one carrying
    `settles`, is told in a block of its own.
    """
    query = _QUERY if any(one.form == "query" for one in categories) else ""
    asked = _KIND if kind(categories) else _ASKED
    return "".join(
        fill(
            template,
            {
                "{{lines}}": "\n".join(f"- {one.description}" for one in told),
                "{{query}}": query,
            },
        )
        for template, role in ((_ASKER, "user"), (asked, "question"))
        if (told := [one for one in categories if one.role == role])
    )


def _held(
    categories: tuple[Category, ...], spec: TypeSpec, spans: bool
) -> tuple[Category, ...]:
    """The categories a slot can hold, in the order dealt.

    One that cannot hold on the slot is not told, and so is stored as no
    category of its categorization, as a compound slot is told none. A
    search query cannot ask what needs two passages, because its keywords
    cannot say how the two meet, nor a type whose question word is the ask.
    A premise needs words of its own: beside a category capping the
    question's words it shrinks to a label naming a setting, as 31 of the 33
    such labels in one calibration did on concise slots, and a search query
    has no sentence to open on one. An unanswerable kind, one carrying
    `settles`, holds only on an unanswerable slot.
    """
    queried = spec.keywords and not (spans or spec.spans)
    kept = tuple(
        one
        for one in categories
        if (one.form != "query" or queried) and one.settles is None
    )
    crowded = any(
        one.form == "query" or (one.form != "premise" and one.words[1] is not None)
        for one in kept
    )
    return tuple(one for one in kept if one.form != "premise" or not crowded)


#: The first- and second-person pronouns and possessive determiners, by ISO
#: 639-1 code, in lower case: the words by which an asker speaks of
#: themselves. A closed class, and a table because the German parse marks
#: `Meine` and `Unser` with no person. German's polite `Sie` and `Ihr` are
#: left out: written in lower case they are the third person.
_SPEAKING: dict[str, frozenset[str]] = {
    "de": frozenset(
        {
            *("ich", "mich", "mir", "wir", "uns", "du", "dich", "dir", "euch"),
            *("mein", "meine", "meinen", "meinem", "meiner", "meines"),
            *("unser", "unsere", "unseren", "unserem", "unserer", "unseres"),
            *("dein", "deine", "deinen", "deinem", "deiner", "deines"),
            *("euer", "eure", "euren", "eurem", "eurer", "eures"),
        }
    ),
    "en": frozenset(
        {
            *("i", "me", "my", "mine", "myself", "we", "us", "our", "ours"),
            *("ourselves", "you", "your", "yours", "yourself", "yourselves"),
        }
    ),
}

#: A dash set off by spaces, which joins a premise to its question as a colon
#: or a comma does, and which `asked` may read no question word after.
_DASH = re.compile(r"\s[-\u2013\u2014]\s")


def _premise(question: str, language: str | None) -> str:
    """What a question opens on before the question itself, or nothing.

    Before the question `asked` finds, or, where it finds none after a clause
    end, before the first dash set off by spaces.
    """
    behind = asked(question, language)
    if behind != question:
        return question[: len(question) - len(behind)]
    dashed = _DASH.search(question)
    return question[: dashed.start()] if dashed else ""


#: The verbs of wanting, trying, checking and understanding, by ISO 639-1
#: code, as lemmas: a premise whose verbs are only these, followed through
#: the infinitives they take, says what the asker wants to know and nothing
#: of their situation. Wanting to return a jacket is a plan; wanting to know
#: is not.
_ENQUIRING: dict[str, frozenset[str]] = {
    "de": frozenset(
        {
            *("wollen", "möchten", "mögen", "wünschen", "versuchen", "prüfen"),
            *("überprüfen", "kontrollieren", "lesen", "informieren"),
            *("verstehen", "wissen", "erfahren", "lernen"),
        }
    ),
    "en": frozenset(
        {
            *("want", "wish", "like", "try", "attempt", "check", "verify"),
            *("review", "read", "look", "study", "understand", "know", "learn"),
            "wonder",
        }
    ),
}


def _enquiring(question: str, language: str | None) -> bool:
    """Whether a question's premise only wants, tries, checks or understands.

    Read off each sentence's main verb, and through the infinitive one of
    these verbs takes, so `I want to know` is read to `know` and `I want to
    return` to `return`. A premise with no verb, and a language with no row
    in `_ENQUIRING`, is never read so.
    """
    enquiring = _ENQUIRING.get(language or "")
    premise = _premise(question, language)
    if not enquiring or not premise.strip():
        return False
    roots = [
        one.root
        for one in pipeline(language)(premise).sents
        if one.root.pos_ in ("VERB", "AUX")
    ]
    for verb in roots:
        while verb.lemma_.casefold() in enquiring:
            then = next(
                (
                    one
                    for one in verb.children
                    if one.pos_ in ("VERB", "AUX")
                    and "Inf" in one.morph.get("VerbForm", [])
                ),
                None,
            )
            if then is None:
                break
            verb = then
        if verb.lemma_.casefold() not in enquiring:
            return False
    return bool(roots)


def _addressed(question: str, language: str | None) -> bool:
    """Whether a question's premise holds a word by which the asker speaks.

    A language with no row in `_SPEAKING` is never read as not addressed: no
    note is better than a false one.
    """
    speaking = _SPEAKING.get(language or "")
    if speaking is None:
        return True
    return any(
        word in speaking
        for word in re.findall(r"\w+", _premise(question, language).casefold())
    )


def _under(position: int, statement: str) -> str:
    """One fact under its number, every later line indented beneath it.

    An outline is one fact carrying several `- ` lines. Interpolated flat
    into a numbered list it reads as several facts, and the writer cites a
    number the sample does not have; indenting the rest under the label
    keeps the numbering the writer answers with intact. Every other kind is
    one line and comes back unchanged.
    """
    label = f"[{position}] "
    first, *rest = statement.splitlines() or [""]
    return "\n".join([label + first, *(" " * len(label) + one for one in rest)])


class Declined(Exception):
    """The writer said these facts cannot answer a question of the kind asked."""


class _Unanswered(BaseModel):
    """The test question, written to the kind asked for."""

    question: str = Field(
        description="The test question: ONE question, ending in a question mark, "
        "that reads as if it belongs to this material."
    )


class QuestionWriter:
    """Writes one question per sample of facts with a served model."""

    def __init__(self, client: Client) -> None:
        """Initialises the writer with the model it asks."""
        self._client = client

    @property
    def model(self) -> str:
        """The model writing the questions."""
        return self._client.model

    def write(self, sample: FactGroup, plan: Plan, note: str = "") -> Candidate:
        """Asks the model for one question of the kind the plan wants.

        Returns whatever came back, unjudged. An empty question is a
        candidate like any other: the gates reject it and the rejection is
        what the drop rate is measured from.

        The returned candidate carries the facts the model said it used, not
        the whole sample. A sample is an offer; a question that needed one
        fact of three is a single-passage question, and recording it as
        anything else is a difficulty nobody can reproduce.

        `note` is what a gate said about the last draft, on a second
        attempt. The same sample and the same plan: what is being asked for
        has not changed, only what to avoid this time.

        The plan's categories are rendered for an answerable slot, and the
        candidate carries what was rendered. An unanswerable question is
        dealt them and told only its kind, the category carrying `settles`,
        if one was configured: the paper asks only questions that have an
        answer. A compound question is told none either, as the comment at
        the call says, and a category the slot cannot hold is not told, as
        `_held` says.

        Raises:
            ModelUnavailable: If the model could not be reached or would not
                answer in the shape.
            Declined: If the model said these facts cannot answer a question
                of this kind.
        """
        if not plan.answerable:
            return self._unanswerable(sample, plan, note)

        kind = KINDS[plan.kind]
        spans = plan.spans
        if plan.kind == QuestionKind.COMPOUND and len(sample.resting) < kind.passages:
            # Short of the passages it asks about, as any spanning slot is:
            # it is written as the single-passage question it can only be.
            kind, spans = KINDS[QuestionKind.SINGLE], False
        # A compound reply is ONE question joining two asks, which a category
        # written for one ask, such as a concise phrasing, would contradict:
        # it is told none. Keyed on the kind asked for, so a compound slot
        # short of its partner, written single, is told its categories.
        told = (
            ()
            if kind.name == QuestionKind.COMPOUND
            else _held(plan.categories, plan.spec, spans)
        )
        system = plan.spec.system(spans=spans, instruction=kind.instruction or None)
        written = self._client.answer(
            system=system,
            user=self._prompt(sample, note, categories=told),
            shape=kind.shape,
            prompt_version=PROMPT_VERSION,
        )
        if written.declined:
            raise Declined(plan.spec.name)
        # A note and never a refusal: a premise naming nobody is a category
        # not followed, and the question may be sound all the same. Once, on
        # the first draft, whose note is this one and not a gate's.
        question = written.question.strip()
        if (
            not note
            and any(one.form == "premise" for one in told)
            and (
                not _addressed(question, sample.language)
                or _enquiring(question, sample.language)
            )
        ):
            log.info(
                "asking again for %r: its premise states nothing of the asker",
                question,
            )
            again = self._client.answer(
                system=system,
                user=self._prompt(
                    sample,
                    fill(_UNADDRESSED, {"{{question}}": question}),
                    categories=told,
                ),
                shape=kind.shape,
                prompt_version=PROMPT_VERSION,
            )
            if not again.declined:
                written = again
        return self._candidate(
            plan,
            question=written.question,
            answer=written.answer,
            explanation=written.explanation,
            group=self._used(sample, written.facts),
            kind=plan.kind,
            parts=tuple(
                (
                    sample.resting[one.passage - 1].id,
                    one.question.strip(),
                    one.answer.strip(),
                )
                for one in getattr(written, "parts", [])
                if 1 <= one.passage <= len(sample.resting)
                and one.question.strip()
                and one.answer.strip()
            ),
            categories=told,
        )

    def follow_up(
        self,
        sample: FactGroup,
        thread: tuple[tuple[str, str | None], ...],
        plan: Plan,
        root_facts: tuple[int, ...] = (),
        parent_passages: tuple[int, ...] = (),
    ) -> Candidate:
        """Asks the model for the question somebody would ask next.

        Written from the same sample as the thread it joins, so a follow-up
        is about the same material rather than a fresh question that happens
        to come after one. Its own type, so a thread can move from a value to
        the reason behind it. Stored `needs_both` only where the root's kind
        is: a compound pair's follow-up is no weld, and the check that
        narrows a weld is not run on it.

        Raises:
            ModelUnavailable: If the model could not be reached or would not
                answer in the shape.
        """
        written = self._client.answer(
            system=_FOLLOW.replace("{{type}}", _typed(plan.spec)),
            user=fill(
                _USER_FOLLOW,
                {
                    "{{sample}}": self._prompt(sample),
                    "{{conversation}}": self._conversation(thread),
                },
            ),
            shape=_Answered,
            prompt_version=PROMPT_VERSION,
        )
        if written.declined:
            raise Declined(plan.spec.name)
        return self._candidate(
            plan,
            question=written.question,
            answer=written.answer,
            explanation=written.explanation,
            group=self._used(sample, written.facts),
            thread=thread,
            root_facts=root_facts,
            parent_passages=parent_passages,
            kind=(
                QuestionKind.NEEDS_BOTH
                if plan.kind == QuestionKind.NEEDS_BOTH
                else QuestionKind.SINGLE
            ),
        )

    def _unanswerable(self, sample: FactGroup, plan: Plan, note: str = "") -> Candidate:
        """Moves one fact out of reach and asks about where it went, or writes its kind.

        From one fact and not from the sample: moving a claim just out of
        reach is a change to one claim, and a reader given two would have two
        ways to notice.
        """
        first = FactGroup(sample.facts[:1], beside=sample.beside)
        told = kind(plan.categories)
        system, user = _perturbation(told)
        written = self._client.answer(
            system=fill(system, {"{{asks}}": plan.spec.asks}),
            user=self._prompt(
                first,
                note,
                user,
                categories=(told,) if told else (),
                holds=_KINDS[written_as(told)]["{{holds}}"],
            ),
            shape=_Unanswered,
            prompt_version=PROMPT_VERSION,
        )
        return Candidate(
            question_text=written.question.strip(),
            # An unanswerable question is scored on behaviour and not on
            # content, which the questions table enforces with a CHECK.
            target_answer=None,
            answerable=False,
            group=first,
            spec=plan.spec,
            planned_difficulty=plan.band,
            categories=(told,) if told else (),
        )

    @staticmethod
    def _candidate(
        plan: Plan,
        *,
        question: str,
        answer: str,
        group: FactGroup,
        kind: str,
        explanation: str = "",
        thread: tuple[tuple[str, str | None], ...] = (),
        root_facts: tuple[int, ...] = (),
        parent_passages: tuple[int, ...] = (),
        parts: tuple[tuple[int, str, str], ...] = (),
        categories: tuple[Category, ...] = (),
    ) -> Candidate:
        """Assembles one written question, whatever kind it was."""
        return Candidate(
            question_text=question.strip(),
            target_answer=answer.strip() or None,
            answer_explanation=explanation.strip() or None,
            answerable=True,
            group=group,
            thread=thread,
            root_facts=root_facts,
            parent_passages=parent_passages,
            spec=plan.spec,
            planned_difficulty=plan.band,
            kind=stored(kind, len(group.resting)),
            parts=parts,
            categories=categories,
        )

    @staticmethod
    def _conversation(thread: tuple[tuple[str, str | None], ...]) -> str:
        """Renders the turns already asked, oldest first."""
        turns = "\n".join(
            f"  Q: {question}\n  A: {answer or 'no answer in the material'}"
            for question, answer in thread
        )
        return f"CONVERSATION so far:\n{turns}"

    @staticmethod
    def _used(sample: FactGroup, numbered: list[int]) -> FactGroup:
        """The facts the model said its question needs, in citation order.

        A number the sample does not have is dropped rather than refused, and
        naming none is read as the first: the answer still has to rest on
        something, and a candidate with no facts is one the orphan trigger
        would never reach.
        """
        chosen = tuple(
            sample.facts[one - 1]
            for one in dict.fromkeys(numbered)
            if 1 <= one <= len(sample.facts)
        )
        return FactGroup(chosen or sample.facts[:1])

    @staticmethod
    def _prompt(
        sample: FactGroup,
        note: str = "",
        template: str = _USER,
        categories: tuple[Category, ...] = (),
        holds: str = _MOVED["{{holds}}"],
    ) -> str:
        """Renders one sample: the facts numbered, then their passages.

        The passages are fenced and labelled, as extraction fences a heading
        trail, because a model shown them unlabelled asks about them instead
        of about the facts.

        `categories` follow the passages, as who is asking and what the
        question itself must be. Their descriptions are an operator's text,
        and the one-pass fill sends a placeholder written in one as written.
        `holds` is what the passages beside a perturbed fact are told, which
        follows an unanswerable slot's kind.

        `note` goes last, where a model weighs it most: it is what went
        wrong with the draft before this one, and it is the only thing that
        differs between the two attempts.
        """
        numbered = "\n".join(
            _under(position, fact.statement)
            for position, fact in enumerate(sample.facts, 1)
        )
        context = "\n\n".join(
            f"[{position}] {heading}{text}"
            for position, (heading, text) in enumerate(sample.context, 1)
        )
        # Framed as a reviewer's feedback on a draft: a note in capitals
        # telling the writer to set aside what it was asked reads, to a
        # provider's prompt shield, like an attempt to override its rules.
        again = (
            f"\n\nFEEDBACK ON THE PREVIOUS DRAFT\n{note}\nWrite a different "
            f"question from the same facts, following the instructions above."
            if note
            else ""
        )
        return fill(
            template,
            {
                "{{facts}}": numbered,
                "{{passages}}": context,
                "{{beside}}": fill(
                    _BESIDE,
                    {
                        "{{texts}}": "\n\n".join(f"- {one}" for one in sample.beside),
                        "{{holds}}": holds,
                    },
                )
                if sample.beside
                else "",
                "{{profile}}": _profile(categories),
                "{{language}}": named(sample.language),
                "{{note}}": again,
            },
        )
