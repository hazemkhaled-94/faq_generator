"""What a kind of question is: the one place that owns it.

A kind says, per question, how many passages are dealt (N is 2 today; a
three-passage kind is one more entry here and one more check), what the writer
is told, the shape it answers in, the checks a draft gets beyond the shared
ones, and the band the kind fixes. The plan deals a kind to every slot; the
writer, the checker and the store look it up here instead of counting the
passages a question happened to cite.

Two kinds are written today, `single` and `needs_both`. `compound` and
`false_premise` are named in `QuestionKind` so the column needs no second
migration, and each is one entry added to `KINDS` by the change that writes it.

The checks are named, not passed: a `QuestionChecker` method is looked up by
name so this module imports nothing from the checker.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from database.qa_generator import QuestionKind
from question_generation.types import _SPAN

__all__ = ["KINDS", "KindSpec", "stored"]


class _Answered(BaseModel):
    """A question the facts answer, as the model is asked to return it."""

    question: str = Field(
        description="ONE question, ending in a question mark, naming what it "
        "asks about the way a searcher would have to."
    )
    answer: str = Field(description="The answer, in the form the instructions ask for.")
    explanation: str = Field(
        default="",
        description="The same answer said at length, three to six sentences, "
        "for a reader who has not seen the material. Says why and not only "
        "what, and asserts no number or name the material does not.",
    )
    facts: list[int] = Field(
        default_factory=list,
        description="The NUMBERS of the facts this question needs.",
    )
    declined: bool = Field(
        default=False,
        description="True when these facts cannot answer a question of this "
        "kind honestly; the question and the answer are then left empty.",
    )


@dataclass(frozen=True)
class KindSpec:
    """One kind of question, as the plan, the writer and the checker read it."""

    name: str
    #: How many passages a slot of this kind is dealt.
    passages: int
    #: Appended to the writer's system prompt where the span clause goes;
    #: empty means the kind adds nothing.
    instruction: str
    #: What the writer answers in: `_Answered`, or a subclass adding what the
    #: kind asks the writer to say beside the answer.
    shape: type[_Answered]
    #: A free `QuestionChecker` method run right after the structural rules
    #: pass, `(candidate, readings) -> Candidate | tuple[str, str]`: a tuple
    #: refuses the draft, a candidate replaces it. None runs nothing.
    before: str | None = None
    #: A `QuestionChecker` method run when no gate refused the draft,
    #: `(candidate, form, readings) -> Candidate | tuple[str, str]`, read the
    #: same way. None runs nothing.
    after: str | None = None
    #: False where the kind's `after` check does its own recovery and the
    #: shared round trip is skipped.
    round_trip: bool = True
    #: The band the kind fixes, or None where the points rule decides.
    band: str | None = None


#: Every kind written. `needs_both` has no `after` here until the check that
#: narrows a question one passage answers exists to name.
KINDS: dict[str, KindSpec] = {
    QuestionKind.SINGLE: KindSpec(QuestionKind.SINGLE, 1, "", _Answered),
    QuestionKind.NEEDS_BOTH: KindSpec(QuestionKind.NEEDS_BOTH, 2, _SPAN, _Answered),
}


def stored(kind: str, passages: int) -> str:
    """The kind a question is stored as: `single` once it rests on one passage.

    A kind is what a slot was dealt; what a question cites is what it turned
    out to be, and a question resting on one passage needs only one.
    """
    return QuestionKind.SINGLE if passages < 2 else kind
