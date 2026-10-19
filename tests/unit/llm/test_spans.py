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
