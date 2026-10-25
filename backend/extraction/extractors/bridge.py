"""The model-backed extractor for claims no single passage states."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from textwrap import wrap
from typing import Literal

from pydantic import BaseModel, Field

from database.qa_generator import FactKind
from extraction.extractors.base import ExtractionFailed
from extraction.links import Link
from extraction.models import CandidateFact, Cited, PassageToExtract, Provenance
from llm.client import Client, ModelUnavailable
from llm.prompt import fill
from llm.spans import RELATIONS
from nlp.models import named as in_language

#: What the model may answer as the relation: none, or one of the table's.
_NAMES = ("none", *RELATIONS)

#: Recorded on every bridge drawn with the prompt below. Bumped whenever that
#: prompt changes what counts as a bridge or how one is cited: two prompts are
#: two datasets.
PROMPT_VERSION = "6"

_SYSTEM = """ROLE
You are a claims analyst working across documents. You read two excerpts the
documents link and decide whether ONE claim needs both of them.

ACTION
Write at most one bridge: a claim a reader gets only by holding both excerpts
together, joining ONE validated fact of each excerpt by a named relation. When
no question needs both excerpts, answer `none`. `none` is the usual answer.

STEPS
1. Read both excerpts, the facts listed under each, and the line that says
   how the documents link them.
2. Look for a relation between ONE fact of the first excerpt and ONE fact of
   the second:
{{relations}}
3. If no relation holds, or one excerpt alone answers every question the
   other would raise, answer `none`.
4. Otherwise name the relation, pick the two facts by their numbers, and
   write the statement that relates them.
5. Write the question only both excerpts answer, and its short answer in the
   excerpts' own words.
6. Check every number, date, name and amount you wrote against the two facts
   you picked. Compute nothing.

CONTEXT
Each excerpt is numbered [P0], [P1]; under it come its sentences, then its
validated facts as [F0], [F1], from zero in every excerpt. You have no
knowledge beyond the excerpts and may use none.

EXAMPLES
Two excerpts:

  [P0] Accounts > Terms
    [0] An account is dormant when its holder has made no payment for 24 months.
    [1] Interest is paid on dormant accounts as on any other.
    facts:
    [F0] An account is dormant when its holder has made no payment for 24 months.
  [P1] Fees > Yearly fees
    [0] A dormant account is charged a yearly fee of 10 EUR.
    [1] The fee is shown on the yearly statement.
    facts:
    [F0] A dormant account is charged a yearly fee of 10 EUR.

  RIGHT  relation: defines   facts: [{excerpt: 0, fact: 0}, {excerpt: 1, fact: 0}]
         statement: "An account whose holder has made no payment for 24
                     months is charged a yearly fee of 10 EUR."
         question: "What yearly fee is charged on an account whose holder has
                    made no payment for 24 months?"   answer: "10 EUR"
         (P1 sets the fee and P0 says which accounts it reaches: neither
          excerpt alone answers the question)

  RIGHT  relation: contrast
         [P0] Requests > Standard: Standard requests are answered within 48
         hours. [P1] Requests > Urgent: Urgent requests are answered within 4
         hours.
         statement: "Urgent requests are answered sooner than standard ones,
                     within 4 hours against 48 hours."
         question: "Which is answered sooner, a standard or an urgent
                    request?"   answer: "an urgent request"
         (each excerpt gives one side and the question needs both)

  WRONG -> none
         [P0] "Interest is paid on dormant accounts as on any other."
         [P1] "The fee is shown on the yearly statement."
         (no question needs both)

  WRONG  statement: "The yearly fee is stated in both Section 7 and the price
                     list."
         (about the documents, not about the subject)

  WRONG  statement: "A dormant account pays 20 EUR in fees over two years."
         (20 appears in neither fact: that is a calculation, not a claim)

FORMAT
Return ONE object:

{{relation_names}}
- `facts`: exactly two entries, one per excerpt: the excerpt's number
  (`excerpt`) and the number of the fact you picked (`fact`).
- `statement`: ONE claim relating the two facts, written by you, naming its
  subject. It keeps each fact's condition or exception (a subordinate clause
  is allowed), adds nothing, computes nothing, and says nothing about where
  the text is ("is stated in both", "section 7 says").
- `question`: a question a reader answers only by holding both excerpts.
- `answer`: its short answer, in the excerpts' words.

Rules, all of them mandatory:
- BOTH EXCERPTS are needed. This is the whole point.
- ADD NOTHING. Every number, date, name and amount in your statement must
  appear in one of the two facts. Do NOT add up, average, subtract, convert or
  otherwise compute a value.
- NAME THE SUBJECT. Never write "it", "this", "they", "he", "she".
- WRITE IN THE LANGUAGE NAMED BENEATH THE EXCERPTS. It is their own language.
- When in doubt, answer `none`.
""".replace(
    "{{relations}}",
    "\n".join(
        line
        for one in RELATIONS.values()
        for line in wrap(
            f"- {one.name}: {one.meaning}",
            width=79,
            initial_indent="   ",
            subsequent_indent="     ",
        )
    ),
).replace(
    "{{relation_names}}",
    "\n".join(
        wrap(
            f"- `relation`: one of {', '.join(_NAMES)}. With `none`, leave the rest "
            "empty.",
            width=79,
            subsequent_indent="  ",
        )
    ),
)

#: The user message, as the catalogue records it and `_prompt` renders it.
_USER = """Excerpts:

{{excerpts}}

{{link}}Write every statement in {{language}}."""


class _Chosen(BaseModel):
    """One validated fact the model joins, as it is asked to name it."""

    excerpt: int = Field(
        description="The number of the excerpt, as [P0] and [P1] give it."
    )
    fact: int = Field(
        description="The number of the fact under that excerpt, as [F0] gives it."
    )


class _Answer(BaseModel):
    """The model's answer for one pair of passages: one bridge, or none."""

    relation: Literal[_NAMES] = Field(  # pyright: ignore[reportInvalidTypeForm]
        description="How the two facts relate; none when no question needs both."
    )
    facts: list[_Chosen] = Field(
        default_factory=list,
        description="One fact of each excerpt: its excerpt number and fact number.",
    )
    statement: str = Field(
        default="",
        description="ONE claim relating the two facts, naming its subject, "
        "adding nothing and computing nothing.",
    )
    question: str = Field(
        default="", description="A question only both excerpts answer."
    )
    answer: str = Field(
        default="", description="Its short answer, in the excerpts' words."
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

    def extract(
        self,
        offered: Sequence[PassageToExtract],
        link: Link | None = None,
        facts: Mapping[int, Sequence[tuple[int, str, tuple[int, ...]]]] | None = None,
    ) -> list[CandidateFact]:
        """Asks the model for the one claim a pair of passages shares, or none.

        Args:
            offered: The passages to show, in the order a candidate names
                them by position.
            link: How the documents link them, named in the message.
            facts: Each passage's validated atomic facts by passage id, as
                (fact id, statement, sentence numbers): what the claim is
                composed from, and where it cites.

        Returns:
            At most one candidate, citing the sentences of the facts the
            model chose, with the question only both passages answer. Empty
            when fewer than two passages were offered or the model said none.

        Raises:
            ExtractionFailed: If the model could not be reached.
        """
        if len(offered) < 2:
            return []
        facts = facts or {}
        try:
            answer = self._client.answer(
                system=_SYSTEM,
                user=self._prompt(offered, link, facts),
                shape=_Answer,
                prompt_version=PROMPT_VERSION,
            )
        except ModelUnavailable as exc:
            raise ExtractionFailed(str(exc)) from exc
        if answer.relation == "none" or not answer.statement.strip():
            return []
        # One citing nothing is still a candidate: the checker stores it
        # refused as evidence_absent, which is the rate the README reports.
        chosen = []
        for one in answer.facts:
            held = (
                facts.get(offered[one.excerpt].id, ())
                if 0 <= one.excerpt < len(offered)
                else ()
            )
            if 0 <= one.fact < len(held):
                chosen.append((one.excerpt, held[one.fact][2]))
        return [
            CandidateFact(
                statement=answer.statement,
                sentences=(),
                kind=FactKind.BRIDGE,
                passages=_cited(chosen),
                probe=(answer.question.strip(), answer.answer.strip()),
                relation=answer.relation,
            )
        ]

    @staticmethod
    def _prompt(
        offered: Sequence[PassageToExtract],
        link: Link | None,
        facts: Mapping[int, Sequence[tuple[int, str, tuple[int, ...]]]],
    ) -> str:
        """Builds the user message: one numbered block per passage, then the link.

        The sentences are numbered within each block, as the atomic prompt
        numbers them, and the validated facts follow them.
        """
        blocks = []
        for position, passage in enumerate(offered):
            heading = f" ({passage.section_path})" if passage.section_path else ""
            numbered = "\n".join(
                f"  [{sentence.index}] {sentence.text}"
                for sentence in passage.sentences
            )
            held = facts.get(passage.id, ())
            listed = "".join(
                f"\n  [F{at}] {statement}" for at, (_, statement, _) in enumerate(held)
            )
            blocks.append(
                f"[P{position}]{heading}\n{numbered}"
                + (f"\n  facts:{listed}" if held else "")
            )
        return fill(
            _USER,
            {
                "{{excerpts}}": "\n\n".join(blocks),
                "{{link}}": _linked(link),
                "{{language}}": in_language(offered[0].language),
            },
        )


def _linked(link: Link | None) -> str:
    """The line that says how the documents link the first two passages."""
    if link is None:
        return ""
    if link.kind == "reference":
        return f'[P0] names the heading "{link.named}" of [P1].\n\n'
    if link.kind == "sibling":
        return f'[P0] and [P1] are sections under the same heading "{link.named}".\n\n'
    return f'[P0] and [P1] are among the few excerpts using "{link.named}".\n\n'


def _cited(named: list[tuple[int, Sequence[int]]]) -> tuple[Cited, ...]:
    """Reads the facts the model chose, one entry per passage named once.

    A passage named twice is folded into one entry carrying both readings, so
    a repeated number cannot make a one-passage claim look like a bridge.

    Args:
        named: Each chosen fact's excerpt position and the sentences it cites.

    Returns:
        One entry per distinct passage that carries at least one sentence.
    """
    sentences: dict[int, list[int]] = {}
    for position, cited in named:
        kept = sentences.setdefault(position, [])
        kept.extend(index for index in cited if index not in kept)
    return tuple(
        Cited(position=position, sentences=tuple(found))
        for position, found in sentences.items()
        if found
    )
