"""The relations a bridge may name, shared by extraction and question generation."""

from __future__ import annotations

import importlib
import re
from typing import get_args


def test_the_relations_are_prompt_six_s_in_its_order() -> None:
    """The table is prompt 6's six relations, and the prompt renders its meanings verbatim."""
    from extraction.extractors import bridge
    from llm.spans import RELATIONS

    assert list(RELATIONS) == [
        "defines",
        "limits",
        "consequence",
        "applies",
        "parallel",
        "contrast",
    ]
    assert (
        RELATIONS["parallel"].answer_from == RELATIONS["contrast"].answer_from == "each"
    )
    assert {
        RELATIONS[n].answer_from
        for n in ("defines", "limits", "consequence", "applies")
    } == {"either"}
    flat = " ".join(bridge._SYSTEM.split())
    for relation in RELATIONS.values():
        assert " ".join(relation.meaning.split()) in flat


def test_the_check_constraint_names_exactly_the_relations() -> None:
    """The facts table's CHECK is the table's names: a new relation comes with a new revision."""
    from database.qa_generator import Fact
    from llm.spans import RELATIONS

    (check,) = [
        one
        for one in Fact.__table__.constraints
        if one.name == "facts_bridge_reading_valid"
    ]
    (listed,) = re.findall(r"IN \(([^)]*)\)", str(check.sqltext))

    assert tuple(re.findall(r"'([^']+)'", listed)) == tuple(RELATIONS)


def test_a_relation_added_to_the_table_is_one_the_bridge_schema_takes(
    monkeypatch,
) -> None:
    """The prompt's list, its FORMAT line and the answer's schema are read off the one table."""
    from extraction.extractors import bridge
    from llm import spans

    added = spans.Relation(
        "requires", "one names what the other's rule needs.", "either"
    )
    monkeypatch.setitem(spans.RELATIONS, "requires", added)
    fresh = importlib.reload(bridge)
    try:
        offered = set(get_args(fresh._Answer.model_fields["relation"].annotation))
        assert "requires: one names" in " ".join(fresh._SYSTEM.split())
        assert offered == {"none", *spans.RELATIONS}, offered
        named = fresh._SYSTEM.split("`relation`: one of", 1)[1].split("\n\n")[0]
        assert "requires" in named, named
    finally:
        monkeypatch.undo()
        importlib.reload(bridge)
