"""The relations a bridge may name. Here rather than in extraction, so question generation, which may not import it, can read the same table; today only the bridge pass does."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Relation:
    """One way two excerpts may need each other."""

    name: str
    meaning: str


RELATIONS: dict[str, Relation] = {
    one.name: one
    for one in (
        Relation("defines", "one excerpt defines a term the other's rule uses."),
        Relation(
            "limits",
            "one sets an exception or a condition to the other's rule.",
        ),
        Relation(
            "consequence",
            "one states what follows when the other's rule is met or broken.",
        ),
        Relation(
            "applies",
            "one states a general rule, the other a case it covers.",
        ),
        Relation(
            "parallel",
            "the same rule for two subjects, each excerpt naming one, and only"
            " when a question about the two needs both excerpts.",
        ),
        Relation(
            "contrast",
            "two subjects differ in one stated respect, each excerpt giving one side.",
        ),
    )
}
