"""The relations a bridge may name, shared by extraction and question generation."""

from __future__ import annotations


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
    """The migration's tuple is the table's names, so a new relation cannot drift from the column."""
    import importlib.util
    from pathlib import Path

    from llm.spans import RELATIONS

    root = Path(__file__).parents[3] / "backend/database/migrations/versions"
    (path,) = root.glob("*_a_bridge_keeps_its_reading.py")
    spec = importlib.util.spec_from_file_location("bridge_reading", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.RELATIONS_CHECKED == tuple(RELATIONS)
