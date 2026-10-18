"""The model-backed extractor for claims no single passage states."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

from database.qa_generator import FactKind
from extraction.extractors.base import ExtractionFailed
from extraction.models import CandidateFact, Cited, PassageToExtract, Provenance
from llm.client import Client, ModelUnavailable
from llm.prompt import fill
from nlp.models import named as in_language

#: Recorded on every bridge drawn with the prompt below. Bumped whenever that
#: prompt changes what counts as a bridge or how one is cited: two prompts are
#: two datasets.
PROMPT_VERSION = "5"

_SYSTEM = """ROLE
You are a claims analyst working across documents. You read several excerpts
the corpus itself says are about the same subject, and write only the claims
that need MORE THAN ONE of them.

ACTION
Write the bridges. A bridge is a claim a reader gets only by holding two
excerpts together, because one of them changes what the other says: one
defines a term the other's rule uses, one sets an exception or a limit to the
other's rule, one says what follows when the other's rule is met or broken.

STEPS
1. Read all the excerpts and note what each is about.
2. Look for pairs that MEET - one defining what another names, one limiting
   or excepting what another states, one stating the consequence of another.
3. Discard pairs that merely sit near each other, and pairs that only state
   two things side by side. They bridge nothing.
4. For each pair that does meet, write the one claim that needs both.
5. Cite it: for each excerpt the claim needs, its number and the numbers of
   ITS OWN sentences you read the claim in.
6. Check every number, date, name and amount you wrote against the sentences
   you cited. Compute nothing.

CONTEXT
Each excerpt is numbered [P0], [P1], and inside each one its sentences are
numbered [0], [1], from zero. SENTENCE NUMBERS START AGAIN AT 0 IN EVERY
EXCERPT. You have no knowledge beyond the excerpts and may use none.

EXAMPLES
Two excerpts:

  [P0] Accounts > Terms
    [0] An account is dormant when its holder has made no payment for 24 months.
    [1] Interest is paid on dormant accounts as on any other.
  [P1] Fees > Yearly fees
    [0] A dormant account is charged a yearly fee of 10 EUR.
    [1] The fee is shown on the yearly statement.

  RIGHT  passages: [{passage: 0, sentences: [0]},
                    {passage: 1, sentences: [0]}]
         statement: "An account whose holder has made no payment for 24
                     months is charged a yearly fee of 10 EUR."
         (P1 sets the fee and P0 says which accounts it reaches: neither
          excerpt alone gives the claim)

  WRONG  passages: [{passage: 0, sentences: [0]}]
         statement: "An account is dormant when its holder has made no
                     payment for 24 months."
         (one excerpt: an ordinary fact, not a bridge)

  WRONG  passages: [{passage: 0, sentences: [0, 1]},
                    {passage: 1, sentences: [0, 1]}]
         statement: "An account whose holder has made no payment for 24
                     months is charged a yearly fee of 10 EUR."
         (sentence 1 of each excerpt says nothing about the claim: cite what
          you used, not the whole excerpt)

  WRONG  passages: [{passage: 0, sentences: [1]},
                    {passage: 1, sentences: [1]}]
         statement: "Both interest and the yearly fee apply to dormant
                     accounts."
         (two facts side by side: neither changes or explains the other, so
          no question needs both; "both A and B", "A and B are stated
          separately" and "X applies to A and to B" bridge nothing)

  WRONG  passages: [{passage: 0, sentences: [0]},
                    {passage: 1, sentences: [0]}]
         statement: "An account becomes dormant after 24 months without a
                     payment and is then charged 10 EUR a year."
         (two claims in one sentence: write the one above)

  WRONG  passages: [{passage: 0, sentences: [0]},
                    {passage: 1, sentences: [0]}]
         statement: "A dormant account pays 20 EUR in fees over two years."
         (20 appears in neither excerpt: that is a calculation, not a claim)

FORMAT
Return `facts`, a list in which every entry has two parts:

- `passages` says where the claim rests, as one entry per excerpt it needs:
  the excerpt's number and the numbers of ITS OWN sentences you read it in.
  It must name at least TWO excerpts. Copy nothing; just say which sentence
  of which excerpt.
- `statement` is WRITTEN BY YOU: one short sentence carrying ONE claim, which
  a reader who cannot see the excerpts understands on its own.

Rules, all of them mandatory:
- AT LEAST TWO EXCERPTS per fact. This is the whole point.
- CITE THE SENTENCES YOU USED, in each excerpt, and no others.
- ONE CLAIM per statement. Exactly one finite verb.
- ADD NOTHING. Every number, date, name and amount in your statement must
  appear in one of the sentences you cite. Do NOT add up, average, subtract,
  convert or otherwise compute a value: a total nobody wrote down is not in
  the material. Relate what is written; do not calculate it.
- NAME THE SUBJECT. Never write "it", "this", "they", "he", "she".
- WRITE IN THE LANGUAGE NAMED BENEATH THE EXCERPTS. It is their own
  language. It is named there rather than left to you because a model reading
  a corpus that is mostly one language writes that language for all of it.
- ONE EXCERPT MUST CHANGE WHAT THE OTHER SAYS: define its term, limit or
  except its rule, or state what follows from it. Two facts that only sit
  side by side, joined by "both", "and" or "separately", bridge nothing.
- Excerpts that merely sit near each other bridge nothing. An empty list is a
  correct answer and is better than a forced one.
"""

#: The user message, as the catalogue records it and `_prompt` renders it.
_USER = """Excerpts:

{{excerpts}}

Write every statement in {{language}}."""


class _Cited(BaseModel):
    """One excerpt a bridge rests on, as the model is asked to name it."""

    passage: int = Field(
        description="The number of the excerpt, as [P0] and [P1] give it."
    )
    sentences: list[int] = Field(
        description="The number(s) of THAT excerpt's own sentences the claim "
        "rests on. Numbering starts at 0 in every excerpt."
    )


class _Bridge(BaseModel):
    """One bridge as the model is asked to return it."""

    passages: list[_Cited] = Field(
        description="Where the claim rests: one entry per excerpt it needs, "
        "each naming that excerpt and the sentences of it you read. At least "
        "two excerpts."
    )
    statement: str = Field(
        description="ONE claim, written by you in one short sentence with "
        "exactly one finite verb, naming its subject and understandable "
        "without the excerpts."
    )


class _Bridges(BaseModel):
    """The model's answer for one group of passages."""

    facts: list[_Bridge] = Field(
        default_factory=list,
        description="Every claim needing more than one excerpt; may be empty.",
    )


class BridgeExtractor:
    """Reads claims that span a group of passages.

    Not an :class:`~extraction.extractors.base.Extractor`: the unit of work
    is a group of passages rather than one, so it is not routed by block type
    and is not in the registry.
    """

    def __init__(self, client: Client) -> None:
        """Initialises the extractor with the model it asks."""
        self._client = client

    @property
    def provenance(self) -> Provenance:
        """What produced these facts, recorded on each one."""
        return Provenance(
            model=self._client.model,
            prompt_version=PROMPT_VERSION,
            temperature=self._client.temperature,
        )

    def extract(self, offered: Sequence[PassageToExtract]) -> list[CandidateFact]:
        """Asks the model for the claims a group of passages shares.

        Args:
            offered: The passages to show, in the order a candidate names
                them by position.

        Returns:
            One candidate per claim, each naming the passages it rests on and
            the sentences of each, or none where the model named none. Empty
            when fewer than two passages were offered.

        Raises:
            ExtractionFailed: If the model could not be reached.
        """
        if len(offered) < 2:
            return []
        try:
            answer = self._client.answer(
                system=_SYSTEM,
                user=self._prompt(offered),
                shape=_Bridges,
                prompt_version=PROMPT_VERSION,
            )
        except ModelUnavailable as exc:
            raise ExtractionFailed(str(exc)) from exc
        # One citing nothing is still a candidate: the checker stores it
        # refused as evidence_absent, which is the rate the README reports.
        return [
            CandidateFact(
                statement=fact.statement,
                sentences=(),
                kind=FactKind.BRIDGE,
                passages=_cited(fact.passages),
            )
            for fact in answer.facts
            if fact.statement.strip()
        ]

    @staticmethod
    def _prompt(offered: Sequence[PassageToExtract]) -> str:
        """Builds the user message: one numbered block per passage.

        The sentences are numbered within each block, as the atomic prompt
        numbers them, because that is what a citation names.
        """
        blocks = []
        for position, passage in enumerate(offered):
            heading = f" ({passage.section_path})" if passage.section_path else ""
            numbered = "\n".join(
                f"  [{sentence.index}] {sentence.text}"
                for sentence in passage.sentences
            )
            blocks.append(f"[P{position}]{heading}\n{numbered}")
        # Every passage of a group is of one topic, and a topic is fitted
        # over one language's vocabulary, so the first is as good as a vote.
        return fill(
            _USER,
            {
                "{{excerpts}}": "\n\n".join(blocks),
                "{{language}}": in_language(offered[0].language),
            },
        )


def _cited(named: list[_Cited]) -> tuple[Cited, ...]:
    """Reads the model's citations, one entry per passage it named once.

    A passage named twice is folded into one entry carrying both readings, so
    a repeated number cannot make a one-passage claim look like a bridge.

    Args:
        named: What the model returned.

    Returns:
        One entry per distinct passage that carries at least one sentence.
    """
    sentences: dict[int, list[int]] = {}
    for one in named:
        kept = sentences.setdefault(one.passage, [])
        kept.extend(index for index in one.sentences if index not in kept)
    return tuple(
        Cited(position=position, sentences=tuple(found))
        for position, found in sentences.items()
        if found
    )
