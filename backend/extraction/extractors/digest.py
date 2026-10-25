"""The model-backed extractor for what a passage is about."""

from __future__ import annotations

import re
from typing import ClassVar

from pydantic import BaseModel, Field

from database.qa_generator import FactKind
from extraction.extractors.base import ExtractionFailed, Extractor
from extraction.models import BULLET, CandidateFact, PassageToExtract, Provenance
from llm.client import Client, ModelUnavailable
from llm.prompt import fill
from nlp.models import named

#: Recorded on every summary and outline drawn with the prompt below. 4 asks
#: what the excerpt establishes, about its subject, where 3 asked what it is
#: about and got summaries describing "the excerpt". 5 keeps "should" and
#: "may" as the excerpt wrote them.
PROMPT_VERSION = "5"

_SYSTEM = """ROLE
You are a technical editor. You condense one excerpt of a document into
something a reader can read instead of it.

ACTION
Return two readings of the same excerpt: a short prose summary of what it
establishes, and an outline of the separate points it makes.

STEPS
1. Read the section context, then the excerpt.
2. Work out what the excerpt establishes: the rules, values, conditions,
   parties and outcomes it states.
3. Write the summary from that, in two or three sentences.
4. List the separate points behind the excerpt's sentences, one short line
   each, between two and six of them.
5. Check every number, date, name and amount in both against the excerpt,
   and drop whatever the excerpt does not carry.

CONTEXT
You are given the section context the excerpt sits under and the excerpt
itself. The context says what the excerpt is about and is NOT part of it.
You have no knowledge beyond what you are shown and may use none.

EXAMPLES
Excerpt, under the context "Support > Response times":

  Standard requests are answered within 48 hours on working days. Urgent
  requests are answered within 4 hours and may be raised by phone.

  summary: "Support response times differ by urgency. Standard requests are
            answered within 48 hours counting working days only, and urgent
            requests within 4 hours. Urgent requests may also be raised by
            phone."
  outline: ["Standard requests: answered within 48 hours",
            "The 48-hour time counts working days only",
            "Urgent requests: answered within 4 hours",
            "Urgent requests may be raised by phone"]

FORMAT
Return two fields about the same excerpt:

- `summary`: two or three sentences stating what the excerpt establishes,
  written about its subject matter. The first sentence opens on that subject
  matter - a party, a thing, a limit, a procedure - never on the excerpt,
  the section, the passage, the text or the document. Someone who reads only
  this knows what the excerpt decided.

    WRONG  "The excerpt describes support response times."
    RIGHT  "Support response times differ by urgency."
- `outline`: the separate points the excerpt makes, one short line each,
  between two and six of them. Not sentences from the excerpt: the points
  behind them.

Rules, all of them mandatory:
- ADD NOTHING. Every number, date, name and amount you write must appear in
  the excerpt. Do not round, convert, infer or complete.
- Be shorter than the excerpt. A summary as long as what it summarises is of
  no use to anybody.
- Name the subject the excerpt is about, not the excerpt. Do not open with
  "it", "this" or "they".
- WRITE IN THE LANGUAGE NAMED BENEATH THE EXCERPT. It is the excerpt's own
  language. It is named there rather than left to you because a model reading
  a corpus that is mostly one language writes that language for all of it.
- Keep the qualifiers that make a point true: the date, the place, the
  party, the unit, the condition.
- Keep the strength of what the excerpt says: should stays should, may
  stays may.
- Say what the excerpt says, not what it implies and not what you know.
"""

#: The user message, as the catalogue records it and `_prompt` renders it.
_USER = """{{context}}Excerpt:
{{excerpt}}

Write the summary and the outline in {{language}}."""


class _Digest(BaseModel):
    """The model's answer for one passage."""

    summary: str = Field(
        default="",
        description="Two or three sentences stating what the excerpt "
        "establishes, opening on its subject matter, never on the excerpt.",
    )
    outline: list[str] = Field(
        default_factory=list,
        description="The separate points the excerpt makes, one short line "
        "each, between two and six of them.",
    )


class DigestExtractor(Extractor):
    """Reads a passage's summary and outline with a served model.

    One call produces both: they are the same reading of the same passage,
    and asking twice costs twice.
    """

    block_types: ClassVar[tuple[str, ...]] = ()
    method: ClassVar[str] = "llm"

    def __init__(self, client: Client, kinds: tuple[str, ...]) -> None:
        """Initialises the extractor.

        Args:
            client: The model it asks.
            kinds: Which of the summary and the outline to keep.
        """
        self._client = client
        self._kinds = kinds

    @property
    def provenance(self) -> Provenance:
        """What produced these facts, recorded on each one."""
        return Provenance(
            model=self._client.model,
            prompt_version=PROMPT_VERSION,
            temperature=self._client.temperature,
        )

    def extract(self, passage: PassageToExtract) -> list[CandidateFact]:
        """Asks the model what one passage is about.

        Args:
            passage: The passage to condense.

        Returns:
            One candidate per kind this extractor was built for, citing every
            sentence of the passage. Empty when the model returned neither.

        Raises:
            ExtractionFailed: If the model could not be reached.
        """
        try:
            answer = self._client.answer(
                system=_SYSTEM,
                user=self._prompt(passage),
                shape=_Digest,
                prompt_version=PROMPT_VERSION,
            )
        except ModelUnavailable as exc:
            raise ExtractionFailed(str(exc)) from exc

        cited = tuple(sentence.index for sentence in passage.sentences)
        written: dict[str, str] = {
            FactKind.SUMMARY: answer.summary.strip(),
            FactKind.OUTLINE: _bulleted(answer.outline),
        }
        return [
            CandidateFact(statement=written[kind], sentences=cited, kind=kind)
            for kind in self._kinds
            if written[kind]
        ]

    @staticmethod
    def _prompt(passage: PassageToExtract) -> str:
        """Builds the user message: the heading trail and the passage text."""
        heading = (
            f"Context (not part of the excerpt, use it only to name the "
            f"subject): {passage.section_path}\n\n"
            if passage.section_path
            else ""
        )
        return fill(
            _USER,
            {
                "{{context}}": heading,
                "{{excerpt}}": passage.text,
                "{{language}}": named(passage.language),
            },
        )


def _bulleted(points: list[str]) -> str:
    """Joins the points into one statement, one bullet per line."""
    kept = [re.sub(r"^[-•*]\s+", "", point.strip()) for point in points]
    return "\n".join(f"{BULLET}{point}" for point in kept if point)
