"""What each stage declares it sends, against what it can actually send.

The catalogue is what resolves `questions.prompt_version` and
`facts.prompt_version` to a text. A prompt missing from it is a version
that resolves to nothing for the calls that used it, and nothing else
would notice: the stage still sends it, the row still records the version,
and only the lookup comes back empty.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from assessment import prompts as assessment
from extraction import prompts as extraction
from extraction.extractors import bridge, digest, llm
from question_generation import phrasing, verifier
from question_generation import prompts as questions
from question_generation.types import _ROLE, PROMPT_VERSION, SPECS
from topic_modelling import labels
from topic_modelling import prompts as topics

BACKEND = Path(__file__).resolve().parents[3] / "backend"


@pytest.fixture(scope="module")
def catalogue() -> dict[str, object]:
    """Question generation's catalogue, by name."""
    return {one.name: one for one in questions.catalogue()}


def test_every_question_type_declares_its_prompt(catalogue) -> None:
    """A type added without one writes questions nothing can resolve."""
    missing = sorted(name for name in SPECS if name not in catalogue)

    assert not missing, f"{missing} can be sent and is not in the catalogue"


def test_a_spanning_variant_is_its_own_prompt(catalogue) -> None:
    """A type sent the spanning instruction was sent a different prompt.

    Recording only the plain one would be a record of half of what the
    stage sends: a single-passage type still gets the spanning prompt
    when its sample happens to cross passages.
    """
    spanning = [name for name in catalogue if name.endswith("(spans)")]

    assert spanning, "no spanning variant was declared"
    for name in spanning:
        plain = name.removesuffix(" (spans)")
        assert catalogue[name].text != catalogue[plain].text


def test_the_judges_are_declared_at_their_own_versions(catalogue) -> None:
    """Three modules, three versions, bumped for different reasons."""
    assert catalogue["factoid"].version == PROMPT_VERSION
    assert catalogue["phrasing: source"].version == phrasing.PROMPT_VERSION
    assert catalogue["verifier: recover"].version == verifier.PROMPT_VERSION


def test_every_prompt_a_module_holds_is_declared() -> None:
    """A prompt held at module level and in no catalogue resolves nothing.

    `types._ROLE` is the exception: the role block every type's prompt is
    composed from, never sent alone.
    """
    declared = {
        one.text
        for stage in (questions, extraction, topics, assessment)
        for one in stage.catalogue()
    }
    # ponytail: modules are found by a line ending in ROLE in their source,
    # so a heading built at run time is missed; import every backend module
    # if one ever is.
    held = {
        f"{module.__name__}.{name}": value
        for path in sorted(BACKEND.rglob("*.py"))
        if "ROLE\n" in path.read_text(encoding="utf-8")
        for module in [
            import_module(".".join(path.relative_to(BACKEND).with_suffix("").parts))
        ]
        for name, value in vars(module).items()
        if isinstance(value, str) and "\nROLE\n" in f"\n{value}"
    }
    missing = sorted(
        name for name, text in held.items() if text not in declared and text != _ROLE
    )

    assert held, "no module-level prompt was found"
    assert not missing, f"{missing} can be sent and is in no catalogue"


def test_a_declared_prompt_is_never_empty(catalogue) -> None:
    """An empty one resolves a version to nothing, which is worse than none."""
    for name, one in catalogue.items():
        assert one.text.strip(), name
        assert one.version, name


@pytest.mark.parametrize(
    "declared",
    [questions.catalogue, extraction.catalogue, topics.catalogue, assessment.catalogue],
    ids=["questions", "extraction", "topics", "assessment"],
)
def test_every_declared_prompt_carries_its_user_half(declared) -> None:
    """A call sends two messages and the row carried one of them.

    What that cost is what Phoenix showed: a published prompt was the
    instructions with nothing under them, because the user message - the
    passages, the facts, the question being judged - was never recorded.
    """
    for one in declared():
        assert one.user_text.strip(), one.name
        assert "{{" in one.user_text, (
            f"{one.name} records a user message with nothing substituted into "
            f"it, so it is one call's text and not the template"
        )


@pytest.mark.parametrize(
    "declared",
    [questions.catalogue, extraction.catalogue, topics.catalogue, assessment.catalogue],
    ids=["questions", "extraction", "topics", "assessment"],
)
def test_every_declared_prompt_carries_the_shape_it_asks_for(declared) -> None:
    """Every call asks for a Pydantic shape, and no row said which."""
    for one in declared():
        assert one.response_schema, one.name
        assert one.response_schema["type"] == "object", one.name


def test_the_topic_labeller_is_declared() -> None:
    """It sends a real prompt and had neither a version nor a row."""
    by_name = {one.name: one for one in topics.catalogue()}

    assert by_name["label"].version == labels.PROMPT_VERSION


def test_extraction_declares_each_extractor_at_its_own_version() -> None:
    """Three extractors, three versions."""
    by_name = {one.name: one for one in extraction.catalogue()}

    assert by_name["atomic"].version == llm.PROMPT_VERSION
    assert by_name["digest"].version == digest.PROMPT_VERSION
    assert by_name["bridge"].version == bridge.PROMPT_VERSION


def test_the_atomic_prompt_is_recorded_as_the_cap_makes_it() -> None:
    """The cap is appended to the prompt, so a capped run sends another.

    Recorded without it, the row would be a record of a prompt no model
    was given under any run that caps.
    """
    uncapped = {one.name: one for one in extraction.catalogue()}["atomic"]
    capped = {one.name: one for one in extraction.catalogue(4)}["atomic"]

    assert capped.text != uncapped.text
    assert "4" in capped.text.removeprefix(uncapped.text)


def test_each_extraction_prompt_names_the_model_it_is_sent_to() -> None:
    """The digest goes to its own model, and to the reader's when none is named."""
    from dataclasses import replace

    from extraction.config import Settings

    named = replace(Settings.load(), model="ollama/reader", digest_model="ollama/small")

    def models(settings: Settings) -> dict[str, str | None]:
        return {one.name: one.model for one in extraction.catalogue(None, settings)}

    assert models(named) == {
        "atomic": "ollama/reader",
        "digest": "ollama/small",
        "bridge": "ollama/reader",
    }
    assert models(replace(named, digest_model=None))["digest"] == "ollama/reader"


def test_the_phrasing_judgements_fall_back_to_the_verifiers_model() -> None:
    """As the factory sends them when no phrasing model is named."""
    from dataclasses import replace

    from question_generation.config import Settings

    settings = replace(
        Settings.load(), verifier_model="ollama/verifier", phrasing_model=None
    )

    phrasing_models = {
        one.model
        for one in questions.catalogue(settings)
        if one.name.startswith("phrasing: ")
    }
    assert phrasing_models == {"ollama/verifier"}
