"""What a question or a bridge over N passages needs from each: the relations a bridge may name and (B4) the per-passage reading. Shared by extraction and question generation, which may not import each other."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RelationName = Literal[
    "defines", "limits", "consequence", "applies", "parallel", "contrast"
]


@dataclass(frozen=True)
class Relation:
    """One way two excerpts may need each other, and where its answer comes from."""

    name: str
    meaning: str
    #: 'each': the answer has a part only each excerpt gives (two subjects);
    #: 'either': one excerpt's rule answers it once the other has fixed its terms.
    answer_from: Literal["each", "either"]
    statement_form: str = ""
    question_form: str = ""


RELATIONS: dict[str, Relation] = {
    one.name: one
    for one in (
        Relation(
            "defines", "one excerpt defines a term the other's rule uses.", "either"
        ),
        Relation(
            "limits",
            "one sets an exception or a condition to the other's rule.",
            "either",
        ),
        Relation(
            "consequence",
            "one states what follows when the other's rule is met or broken.",
            "either",
        ),
        Relation(
            "applies",
            "one states a general rule, the other a case it covers.",
            "either",
        ),
        Relation(
            "parallel",
            "the same rule for two subjects, each excerpt naming one, and only"
            " when a question about the two needs both excerpts.",
            "each",
        ),
        Relation(
            "contrast",
            "two subjects differ in one stated respect, each excerpt giving one side.",
            "each",
        ),
    )
}
