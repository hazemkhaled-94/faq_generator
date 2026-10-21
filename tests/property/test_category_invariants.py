"""What a slot is told of the categories it was dealt, for any plan.

`plans` deals every slot one category of each categorization; the writer
tells it only the ones the slot can hold (`_held`) and stores what it told.
These hold that over every plan the strategy builds through `plans` itself:
a query is never told on a spanning slot or on a type whose question word is
the ask, a premise never beside a query or a capped phrasing, an
unanswerable or compound question is told none, and what is told is always
a sub-sequence of what was dealt.
"""

from __future__ import annotations

import pytest
from factories import group, source
from hypothesis import given
from hypothesis import strategies as st

from database.qa_generator import Difficulty, QuestionKind
from question_generation.generation import QuestionWriter
from question_generation.models import Categorization, Category
from question_generation.planning import plans
from question_generation.types import SPECS

pytestmark = pytest.mark.nlp


class Model:
    """A served model that writes the same question for any slot, citing every fact."""

    model = "ollama/stub"
    temperature = 0.0

    def __init__(self, facts: list[int]) -> None:
        """Initialises the model with the facts it says it used."""
        self.facts = facts

    def answer(self, *, system: str, user: str, shape, prompt_version=None):
        """Answers in the shape asked for."""
        fields = {
            "question": "Ich bin Kundin: was kostet die Karte?",
            "answer": "10 EUR",
            "explanation": "",
            "facts": self.facts,
        }
        return shape(**{k: v for k, v in fields.items() if k in shape.model_fields})


_FORMS = {
    "query": Category("Phrasing", "query", "keywords.", 1.0, form="query"),
    "short-query": Category(
        "Phrasing", "short-query", "few keywords.", 1.0, words=(None, 6), form="query"
    ),
    "concise": Category("Phrasing", "concise", "short.", 1.0, words=(None, 9)),
    "verbose": Category("Phrasing", "verbose", "long.", 1.0),
    "premise": Category("Premise", "premise", "with a premise.", 1.0, form="premise"),
    "direct": Category("Premise", "direct", "no premise.", 1.0),
    "novice": Category("Asker", "novice", "a novice.", 1.0, role="user"),
}


def _categorization(name: str, picked: list[str]) -> Categorization:
    share = 1 / len(picked)
    return Categorization(
        name,
        tuple(
            Category(name, key, _FORMS[key].description, share, _FORMS[key].role,
                     _FORMS[key].words, _FORMS[key].form)
            for key in picked
        ),
    )


_PHRASINGS = st.lists(
    st.sampled_from(["query", "short-query", "concise", "verbose"]),
    min_size=1,
    max_size=4,
    unique=True,
)
_PREMISES = st.lists(st.sampled_from(["premise", "direct"]), min_size=1, unique=True)
_TYPES = st.dictionaries(st.sampled_from(sorted(SPECS)), st.integers(0, 3), min_size=1).filter(
    lambda mix: any(mix.values())
)
_KINDS = st.sampled_from(
    [
        {QuestionKind.NEEDS_BOTH: 1},
        {QuestionKind.NEEDS_BOTH: 1, QuestionKind.COMPOUND: 1},
        {QuestionKind.COMPOUND: 1},
    ]
)


def _sample(spans: bool):
    if not spans:
        return group(source(1, statement="Die Karte kostet 10 EUR.", language="de"))
    return group(
        source(1, document="a", passage_id=11, statement="Die Karte kostet 10 EUR.",
               language="de"),
        source(2, document="b", passage_id=22, statement="Die Ersatzkarte kostet 15 EUR.",
               language="de"),
    )


@given(
    types=_TYPES,
    kinds=_KINDS,
    phrasings=_PHRASINGS,
    premises=_PREMISES,
    asker=st.booleans(),
    unanswerable=st.sampled_from([0.0, 0.25]),
    seed=st.text(max_size=6),
)
def test_every_told_category_holds_on_its_slot(
    types, kinds, phrasings, premises, asker, unanswerable, seed
) -> None:
    """Told is dealt, less what cannot hold: never a query on a spanning or reason slot."""
    categorizations = [
        _categorization("Phrasing", phrasings),
        _categorization("Premise", premises),
    ] + ([_categorization("Asker", ["novice"])] if asker else [])
    dealt = plans(
        wanted=8,
        types=types,
        bands={Difficulty.EASY: 1, Difficulty.MEDIUM: 1, Difficulty.HARD: 1},
        unanswerable_share=unanswerable,
        kinds=kinds,
        categorizations=categorizations,
        seed=seed,
    )
    for slot in dealt:
        sample = _sample(slot.spans)
        facts = [one.id for one in sample.facts]
        written = QuestionWriter(Model(facts)).write(sample, slot)
        told = written.categories

        # A sub-sequence of what was dealt, in the order dealt.
        assert [one for one in slot.categories if one in told] == list(told)
        if not slot.answerable or slot.kind == QuestionKind.COMPOUND:
            assert told == (), slot
            continue
        queried = [one for one in told if one.form == "query"]
        if slot.spans or slot.spec.spans or not slot.spec.keywords:
            assert not queried, (slot.spec.name, slot.shape, told)
        if queried or any(
            one.form != "premise" and one.words[1] is not None for one in told
        ):
            assert not any(one.form == "premise" for one in told), told
        # What holds is told: a category no rule refuses on this slot is not dropped.
        for one in slot.categories:
            refused = (
                one.form == "query"
                and (slot.spans or slot.spec.spans or not slot.spec.keywords)
            ) or (one.form == "premise")
            if not refused:
                assert one in told, (one, told)
