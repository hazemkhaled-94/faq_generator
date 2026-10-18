"""The model-backed extractor for the claims a passage carries."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from pydantic import BaseModel, Field

from extraction.extractors.base import ExtractionFailed, Extractor
from extraction.models import CandidateFact, CheckedFact, PassageToExtract, Provenance
from llm.client import Client, ModelUnavailable
from llm.prompt import fill
from nlp.models import named

#: Recorded on every fact drawn with the prompt below. Bumped whenever that
#: prompt changes what counts as a fact. 11 keeps a rule whole with its
#: conditions, its exception and the set an "only" closes, carries a list's
#: lead-in into each item, and leaves out claims about the document itself.
#: 12 gives the heading trail as the situation a rule may hold only in, and
#: keeps a list whose lead-in closes it as one fact.
PROMPT_VERSION = "12"

#: Recorded on every fact the repair prompt wrote, which is how a later reader
#: tells a claim split out of a refused statement from one the prompt above
#: wrote. Its own version, bumped apart: what a fact is and how a refused one
#: is split are two decisions.
REPAIR_PROMPT_VERSION = "repair-1"

_SYSTEM = """ROLE
You are a claims analyst. You read one numbered excerpt of a document and
separate out the individual claims it makes.

ACTION
Break the excerpt down into the separate claims it makes. Each claim becomes
one fact, written by you and citing the numbered sentence you read it in.

STEPS
1. Read the section context, then the excerpt.
2. Go through it CLAIM BY CLAIM, not sentence by sentence. One sentence
   often carries several claims, and each of them is its own fact:

     "The device weighs 4 kg, runs for 12 hours and ships in March."
       -> three facts: the weight, the runtime, the shipping month.

   Split only where what the sentence says holds for each part on its own.
   Where it does not, the parts are ONE claim and stay in one fact:
   - a set closed by "only": "Refunds are issued only for faulty goods,
     wrong deliveries or missing parts." is one fact. "Refunds are issued
     only for faulty goods" alone is false.
   - conditions that are needed together: "A transfer is released if the
     payee is verified and the daily limit is not reached." is one fact.
     Either condition alone does not release it.
   - a rule and its exception: "Card payments settle within 2 days unless
     flagged for review." is one fact.
3. A list under a lead-in ("Required to open an account:") makes one fact
   per item, and each item's fact says the lead-in's situation again and
   cites the lead-in's sentence as well as the item's. A lead-in that closes
   the list ("only", "the only exceptions are") is not repeated into the
   items: such a list is one fact.
4. Drop anything that states nothing: a question, a checklist item, a heading
   written as a question, a sentence with no factual content.
5. Write each claim as one sentence of your own, naming its subject. Keep
   the strength of what the excerpt says: "should" stays "should", "may"
   stays "may", and a hedge such as "possibly" stays.
6. Check every number, date, name and amount you wrote against the sentences
   you cited, and drop whatever they do not carry.
7. Read each statement on its own and ask: would it be true, and as strong,
   if the excerpt said nothing else? If not, put back the condition, the
   exception, the "only" or the situation it dropped.

CONTEXT
You are given the section context the excerpt sits under, and the excerpt
itself with its sentences numbered from zero. The context says what the
excerpt is about and is NOT part of it, so no sentence number belongs to it.
You have no knowledge beyond what you are shown and may use none.

EXAMPLES
Excerpt, under the context "Support > Response times":

  [0] Standard requests are answered within 48 hours on working days.
  [1] Urgent requests are answered within 4 hours and may be raised by phone.

  WRONG  statement: "Standard enquiries receive a reply within 48 hours on
                     business days, and urgent ones within 4 hours."
         (two claims in one sentence, and it restates rather than decomposes)

  RIGHT  four facts, each one claim:
    1. sentences: [0]
       statement: "A standard support request is answered within 48 hours."
    2. sentences: [0]
       statement: "The 48-hour reply time for standard support requests
                   counts working days only."
    3. sentences: [1]
       statement: "An urgent support request is answered within 4 hours."
    4. sentences: [1]
       statement: "An urgent support request may be raised by phone."

Excerpt, under the context "Accounts > Opening an account":

  [0] Required to open an account:
  [1] - a valid passport
  [2] - proof of address

  RIGHT  two facts, each carrying the lead-in:
    1. sentences: [0, 1]
       statement: "A valid passport is required to open an account."
    2. sentences: [0, 2]
       statement: "Proof of address is required to open an account."

Excerpt, under the context "Returns":

  [0] Refunds are issued only for faulty goods, wrong deliveries or missing
      parts.
  [1] Staff should log every refund.

  WRONG  statement: "Refunds are issued only for faulty goods."
         (false on its own: the "only" closes the whole list)
  WRONG  statement: "Staff must log every refund."
         (the excerpt says "should")
  RIGHT  two facts:
    1. sentences: [0]
       statement: "Refunds are issued only for faulty goods, wrong
                   deliveries or missing parts."
    2. sentences: [1]
       statement: "Staff should log every refund."

A SENTENCE THAT ASKS SOMETHING STATES NOTHING, and is not to be turned round
into the claim it would be if the answer were yes:

  "Are imported data checked for validity?"
    -> no fact. The excerpt asks this; it does not say it happens.

FORMAT
Return `facts`, a list in which every entry has two parts:

- `sentences` is the NUMBER of the sentence the claim comes from, as a list.
  Copy nothing; just say which numbered sentence you read it in. Add the
  sentence of a lead-in or a condition the claim restates. Several facts may
  cite the same sentence, which is normal and correct.
- `statement` is WRITTEN BY YOU: one sentence carrying ONE claim, which a
  reader who cannot see the excerpt understands on its own.

Rules, all of them mandatory:
- ONE CLAIM per statement: one main clause. Its conditions, its exception
  and the set an "only" closes stay inside it. Two things that are each true
  on their own, joined by "and", are two facts.
- NAME THE SUBJECT. Never write "it", "this", "they", "he", "she". Replace
  every one with what the excerpt means, taking it from the section context
  when the sentence leaves it out.
- ADD NOTHING. Every number, date, name and amount in your statement must
  appear in the sentences you cite. Do not round, convert, infer or complete.
- KEEP THE SCOPE. Carry the qualifiers that make the claim true on its own:
  the date, the place, the party, the unit, the condition, the exception,
  the "only", and the situation a lead-in or heading sets.
- A number, a date, a name, a limit, a duty and a definition are each a claim
  worth a fact of its own.
- ABOUT THE SUBJECT, NOT THE DOCUMENT. Leave out claims about the document
  itself: how it is published, licensed, laid out, translated or obtained,
  what its parts contain, and how its changes are marked.
- WRITE IN THE LANGUAGE NAMED BENEATH THE EXCERPT. It is the excerpt's own
  language. It is named there rather than left to you because a model reading
  a corpus that is mostly one language writes that language for all of it,
  and a statement in the wrong language is a fact nothing downstream can use.
- Do not copy the sentence out when it carries several claims. A statement
  that repeats such a sentence has to carry ONE of its claims and leave the
  rest.
- A sentence with no factual content yields no facts. An empty list is a
  correct answer and is better than a weak one.
"""

#: The user message, as the catalogue records it and `_prompt` renders it.
#: One source, so the recorded template and the sent text cannot drift.
_USER = """{{context}}Excerpt:
{{excerpt}}

Write every statement in {{language}}."""

#: Appended when EXTRACTION_MIN_OTHER_SHARE caps how many atomic facts a
#: passage keeps. Asked for here as well as enforced on what comes back,
#: because the facts over the cap are thrown away and a model told to write
#: fewer spends fewer tokens reaching the same set. Left off entirely when
#: there is no cap, rather than written as a large number: a ceiling nothing
#: is near still changes what a model writes.
#:
#: The number is the passage's own room, `PassageToExtract.room`: the cap, or
#: its sentences and list items where they are more, so a list is asked for
#: every item rather than for the first few.
_CAP = """
MOST IMPORTANT RULE, ABOVE ALL THE OTHERS:

- AT MOST {cap} FACTS from this excerpt, however long it is. Returning fewer
  is correct; returning more is not.
- CHOOSE THE {cap} SOMEBODY WOULD LOOK UP. A claim carrying a number, a date,
  a name, a limit, a duty or a definition comes first.
"""

#: Sent once for a passage whose statements were refused as `not_atomic`,
#: with those statements. Without it the rule a joined statement carried was
#: lost: the counter is right that two finite verbs are two claims, and
#: nothing asked for the two.
_REPAIR_SYSTEM = """ROLE
You are a claims analyst. Statements written from one numbered excerpt of a
document were refused, because each joins several claims in one sentence.
You write the claims each of them joined as facts of their own.

ACTION
Rewrite every refused statement as one fact per claim it makes, each citing
the numbered sentence it comes from.

STEPS
1. Read the section context, the excerpt, then each refused statement and
   the reason it was refused.
2. Find the claims a refused statement joins. Each action, duty, permission,
   limit or value it states with a verb of its own is one claim.
3. Write each claim as one sentence that stands alone. Repeat in it the
   subject the claims shared, and the condition, the exception or the
   situation they were stated under: a claim that loses the "if" or the
   "unless" it was made under says more than the excerpt does.
4. Split only the claims. A condition, an exception and the set an "only"
   closes are not claims of their own: each stays whole inside every fact
   it governs.
5. Check every number, date, name and amount you wrote against the sentences
   you cited, and drop whatever they do not carry.

CONTEXT
You are given the section context the excerpt sits under, the excerpt itself
with its sentences numbered from zero, and the statements refused for it,
each with the reason. The context says what the excerpt is about and is NOT
part of it, so no sentence number belongs to it. You have no knowledge
beyond what you are shown and may use none.

EXAMPLES
Excerpt, under the context "Payments > Disputes":

  [0] If a card payment is disputed, the bank freezes the amount and
      informs the merchant within 3 days.

  Refused: "If a card payment is disputed, the bank freezes the amount and
            informs the merchant within 3 days."
  Reason:  the statement carries 2 claims

  WRONG  statement: "The bank informs the merchant within 3 days."
         (drops the condition the claim was made under)
  RIGHT  two facts, each repeating the subject and the condition:
    1. sentences: [0]
       statement: "If a card payment is disputed, the bank freezes the
                   amount."
    2. sentences: [0]
       statement: "If a card payment is disputed, the bank informs the
                   merchant within 3 days."

Excerpt, under the context "Delivery > Neighbours":

  [0] A parcel may be left with a neighbour.
  [1] It must then be signed for and must not be opened unless the
      customer agrees.

  Refused: "A parcel left with a neighbour must be signed for and must not
            be opened unless the customer agrees."
  Reason:  the statement carries 2 claims

  RIGHT  two facts, each keeping the situation, and the second its
         exception:
    1. sentences: [0, 1]
       statement: "A parcel left with a neighbour must be signed for."
    2. sentences: [0, 1]
       statement: "A parcel left with a neighbour must not be opened unless
                   the customer agrees."

FORMAT
Return `facts`, a list in which every entry has two parts:

- `sentences` is the NUMBER of the sentence the claim comes from, as a list.
  Copy nothing; just say which numbered sentence you read it in. Add the
  sentence of a lead-in or a condition the claim restates.
- `statement` is WRITTEN BY YOU: one sentence carrying ONE claim, which a
  reader who cannot see the excerpt understands on its own.

Rules, all of them mandatory:
- ONE CLAIM per statement: one main clause. Two things that are each true
  on their own, joined by "and", are two facts.
- NAME THE SUBJECT. Never write "it", "this", "they", "he", "she". Replace
  every one with what the excerpt means, taking it from the section context
  when the sentence leaves it out.
- ADD NOTHING. Every number, date, name and amount in your statement must
  appear in the sentences you cite. Do not round, convert, infer or complete.
- KEEP THE STRENGTH. "should" stays "should", "may" stays "may", and a hedge
  such as "possibly" stays.
- WRITE IN THE LANGUAGE NAMED BENEATH THE EXCERPT. It is the excerpt's own
  language, and a statement in another is a fact nothing downstream can use.
- Rewrite only what was refused. A claim no refused statement makes is not
  asked for here.
"""

#: The repair's user message: the excerpt as `_USER` shows it, and what was
#: refused in it.
_REPAIR_USER = """{{context}}Excerpt:
{{excerpt}}

Refused statements:
{{refused}}

Write every statement in {{language}}."""


class _Fact(BaseModel):
    """One fact as the model is asked to return it."""

    sentences: list[int] = Field(
        description="The number(s) of the excerpt sentence this claim comes "
        "from. Usually one."
    )
    statement: str = Field(
        description="ONE claim, written by you in one sentence with one main "
        "clause, keeping its conditions, its exception and the set an 'only' "
        "closes, naming its subject and understandable without the excerpt."
    )


class _Facts(BaseModel):
    """The model's answer for one passage."""

    facts: list[_Fact] = Field(
        default_factory=list, description="Every fact in the excerpt; may be empty."
    )


def composed(cap: int | None = None) -> str:
    """This extractor's system prompt, as it is sent under one cap.

    A function because two callers need the same text and neither may
    rebuild it: the extractor, which sends it with each passage's own room
    as the cap, and `extraction.prompts`, which records it with the cap
    itself - the text a passage within the cap is sent. Written twice, the
    record and what was sent could drift apart.
    """
    return _SYSTEM + _CAP.format(cap=cap) if cap else _SYSTEM


def version(cap: int | None = None) -> str:
    """The version this prompt is recorded under for one cap, as "10+cap4".

    The cap named is the one EXTRACTION_MIN_OTHER_SHARE works out to, and the
    text recorded under it is what a passage stating no more than that is
    sent. A passage stating more is sent the same text with its own count.
    """
    return f"{PROMPT_VERSION}+cap{cap}" if cap else PROMPT_VERSION


class LlmExtractor(Extractor):
    """Reads a passage's claims one at a time with a served model.

    The fallback for every passage the deterministic readers do not claim.
    The model sees one passage's numbered sentences and its heading trail,
    never the whole document, and cites a sentence by number rather than
    quoting it.
    """

    block_types: ClassVar[tuple[str, ...]] = ()
    method: ClassVar[str] = "llm"

    def __init__(self, client: Client, cap: int | None = None) -> None:
        """Initialises the extractor with the model it asks.

        Args:
            client: The model that reads a passage.
            cap: The most facts one passage may yield, or None for no
                ceiling. What EXTRACTION_MIN_OTHER_SHARE works out to; a
                passage stating more sentences and list items is asked for those.
        """
        self._client = client
        self._cap = cap
        self._version = version(cap)

    @property
    def provenance(self) -> Provenance:
        """What produced these facts, recorded on each one."""
        return Provenance(
            model=self._client.model,
            prompt_version=self._version,
            temperature=self._client.temperature,
        )

    def extract(self, passage: PassageToExtract) -> list[CandidateFact]:
        """Asks the model for the claims in one passage.

        Args:
            passage: The passage to read.

        Returns:
            One atomic candidate per claim, each citing the sentences it was
            drawn from, or none where the model named none. Empty when the
            passage carries none.

        Raises:
            ExtractionFailed: If the model could not be reached.
        """
        return self._ask(
            composed(passage.room(self._cap)), self._prompt(passage), self._version
        )

    @property
    def repair_provenance(self) -> Provenance:
        """What produced a fact a repair call wrote, recorded on each one."""
        return Provenance(
            model=self._client.model,
            prompt_version=REPAIR_PROMPT_VERSION,
            temperature=self._client.temperature,
        )

    def repair(
        self, passage: PassageToExtract, refused: Sequence[CheckedFact]
    ) -> list[CandidateFact]:
        """Asks the model once more for the claims refused statements joined.

        Args:
            passage: The passage as `extract` was shown it.
            refused: What the checker refused from it as `not_atomic`.

        Returns:
            One candidate per claim, each citing the sentences it was drawn
            from, as `extract` returns them.

        Raises:
            ExtractionFailed: If the model could not be reached.
        """
        listed = "\n".join(
            f'- Refused: "{fact.statement}"\n  Reason: {fact.validation_error}'
            for fact in refused
        )
        return self._ask(
            _REPAIR_SYSTEM,
            self._prompt(passage, _REPAIR_USER, {"{{refused}}": listed}),
            REPAIR_PROMPT_VERSION,
        )

    def _ask(self, system: str, user: str, version: str) -> list[CandidateFact]:
        """Sends one prompt and reads the facts it answers with."""
        try:
            answer = self._client.answer(
                system=system, user=user, shape=_Facts, prompt_version=version
            )
        except ModelUnavailable as exc:
            raise ExtractionFailed(str(exc)) from exc
        # One citing nothing is still a candidate: the checker stores it
        # refused as evidence_absent, which is the rate the README reports.
        return [
            CandidateFact(
                statement=fact.statement, sentences=tuple(dict.fromkeys(fact.sentences))
            )
            for fact in answer.facts
            if fact.statement.strip()
        ]

    @staticmethod
    def _prompt(
        passage: PassageToExtract,
        template: str = _USER,
        more: dict[str, str] | None = None,
    ) -> str:
        """Builds the user message: the heading trail and numbered sentences.

        The heading is fenced off and labelled as context: run together with
        the excerpt, the model cited it as a sentence that does not exist.
        `more` fills the placeholders a template has beyond those.
        """
        heading = (
            f"Context (not part of the excerpt): {passage.section_path}. It "
            f"names the situation the excerpt sits in; when a rule holds only "
            f"in that situation, the statement names it.\n\n"
            if passage.section_path
            else ""
        )
        numbered = "\n".join(
            f"[{sentence.index}] {sentence.text}" for sentence in passage.sentences
        )
        return fill(
            template,
            {
                "{{context}}": heading,
                "{{excerpt}}": numbered,
                "{{language}}": named(passage.language),
            }
            | (more or {}),
        )
