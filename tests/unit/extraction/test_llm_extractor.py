"""The message a passage becomes, and what comes back from it.

The model sees one passage's numbered sentences and its heading trail, never
the whole document, and cites a sentence by number rather than quoting it.
"""

from __future__ import annotations

import pytest
from factories import passage

from extraction.extractors.base import ExtractionFailed
from extraction.extractors.llm import PROMPT_VERSION, LlmExtractor
from llm.client import ModelUnavailable

pytestmark = pytest.mark.nlp


class _Fact:
    """One fact as the model returns it."""

    def __init__(self, statement: str, sentences: list[int]) -> None:
        """Initialises the fact."""
        self.statement, self.sentences = statement, sentences


class _Answer:
    """The model's answer for one passage."""

    def __init__(self, *facts: _Fact) -> None:
        """Initialises the answer."""
        self.facts = list(facts)


class _Client:
    """A model that answers whatever it was told to, and records the ask."""

    model = "ollama/test-model"
    temperature = 0.0

    def __init__(self, answer: _Answer | Exception) -> None:
        """Initialises the client."""
        self._answer, self.asked = answer, {}

    def answer(self, **kwargs: object) -> _Answer:
        """Answers, and records what it was sent."""
        self.asked = kwargs
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer


def test_the_provenance_names_the_model_and_the_prompt() -> None:
    """Two prompts are two datasets, so the version is recorded per fact."""
    provenance = LlmExtractor(_Client(_Answer())).provenance

    assert provenance.model == "ollama/test-model"
    assert provenance.prompt_version == PROMPT_VERSION
    assert provenance.temperature == 0.0


def test_a_capped_prompt_is_recorded_under_a_version_of_its_own() -> None:
    """The cap paragraph is part of the text the model is sent."""
    from extraction.prompts import catalogue

    def recorded(cap: int | None) -> str:
        return next(one for one in catalogue(cap) if one.name == "atomic").version

    client = _Client(_Answer())
    capped = LlmExtractor(client, cap=4)
    capped.extract(passage())

    assert capped.provenance.prompt_version == recorded(4)
    assert client.asked["prompt_version"] == recorded(4)
    assert recorded(4) != recorded(None) == PROMPT_VERSION


def test_a_passage_stating_more_than_the_cap_is_told_its_own_count() -> None:
    """A list of eight is asked for eight, under the version the cap names."""
    from extraction.prompts import catalogue

    listed = passage(
        "A customer is charged a fee for:\n- a card\n- a transfer\n- a statement\n"
        "- a closure\n- a reminder\n- a cheque\n- a search\n- a letter"
    )
    client = _Client(_Answer())
    capped = LlmExtractor(client, cap=4)

    capped.extract(listed)

    recorded = next(one for one in catalogue(4) if one.name == "atomic")
    assert "AT MOST 9 FACTS" in client.asked["system"]
    assert client.asked["prompt_version"] == recorded.version


def test_a_short_passage_is_told_the_cap_itself() -> None:
    """The recorded text is exactly what such a passage is sent."""
    from extraction.prompts import catalogue

    client = _Client(_Answer())
    LlmExtractor(client, cap=4).extract(passage())

    recorded = next(one for one in catalogue(4) if one.name == "atomic")
    assert client.asked["system"] == recorded.text


def test_the_sentences_are_sent_numbered() -> None:
    """The number is what a citation resolves against."""
    client = _Client(_Answer())
    LlmExtractor(client).extract(passage())

    assert "[0] The device weighs 4 kg and runs for 12 hours." in client.asked["user"]
    assert (
        "[1] It arrives in March 2026 from the Hamburg plant." in client.asked["user"]
    )


def test_a_heading_trail_is_fenced_off_and_labelled() -> None:
    """Run together with the excerpt, the model cited it as a sentence."""
    client = _Client(_Answer())
    LlmExtractor(client).extract(passage(section_path="Support > Response times"))

    sent = client.asked["user"]
    assert sent.startswith("Context (not part of the excerpt")
    assert "Support > Response times" in sent
    assert sent.index("Context") < sent.index("Excerpt:")


def test_the_context_is_given_as_the_situation_a_rule_holds_in() -> None:
    """Labelled only as what the excerpt is about, a heading's scope was dropped."""
    client = _Client(_Answer())
    LlmExtractor(client).extract(passage(section_path="Accounts > Students"))

    assert client.asked["user"].startswith(
        "Context (not part of the excerpt): Accounts > Students. It names the "
        "situation the excerpt sits in; when a rule holds only in that "
        "situation, the statement names it."
    )


def test_an_exclusive_lead_in_is_not_copied_into_items() -> None:
    """Copied into each item, "the only exceptions are" makes each one false."""
    client = _Client(_Answer())
    LlmExtractor(client).extract(passage())

    assert (
        'A lead-in that closes the list ("only", "the only exceptions are") '
        "is not repeated into the items: such a list is one fact."
    ) in " ".join(client.asked["system"].split())


def test_a_passage_with_no_heading_is_all_excerpt() -> None:
    """Nothing is invented to fill the context in."""
    client = _Client(_Answer())
    LlmExtractor(client).extract(passage())

    assert client.asked["user"].startswith("Excerpt:")


def test_a_returned_fact_becomes_a_candidate() -> None:
    """The statement and the cited numbers, and nothing else."""
    client = _Client(_Answer(_Fact("The device weighs 4 kg.", [0])))
    facts = LlmExtractor(client).extract(passage())

    assert len(facts) == 1
    assert facts[0].statement == "The device weighs 4 kg."
    assert facts[0].sentences == (0,)


@pytest.mark.parametrize("returned", [_Fact("", [0]), _Fact("   ", [0])])
def test_a_fact_with_no_statement_is_dropped(returned) -> None:
    """Nothing was said, so there is nothing to check."""
    assert LlmExtractor(_Client(_Answer(returned))).extract(passage()) == []


def test_a_fact_citing_nothing_reaches_the_checker() -> None:
    """It is stored refused as evidence_absent, so the refusal rate counts it."""
    from database.qa_generator import Rejection
    from extraction.models import WRITTEN
    from extraction.validation import FactChecker

    read = passage()
    (candidate,) = LlmExtractor(
        _Client(_Answer(_Fact("A statement citing nothing.", [])))
    ).extract(read)

    assert candidate.sentences == ()
    checked = FactChecker(0.6).check(read, candidate, WRITTEN)
    assert checked.rejection_code == Rejection.EVIDENCE_ABSENT


def test_a_repeated_citation_is_kept_once_and_in_order() -> None:
    """The same sentence named twice is one citation."""
    client = _Client(_Answer(_Fact("The device weighs 4 kg.", [1, 0, 1])))
    facts = LlmExtractor(client).extract(passage())

    assert facts[0].sentences == (1, 0)


def test_an_empty_answer_is_a_correct_answer() -> None:
    """A sentence with no factual content yields no facts."""
    assert LlmExtractor(_Client(_Answer())).extract(passage()) == []


def test_a_model_that_will_not_answer_fails_the_passage() -> None:
    """The row is failed with the reason, not left mid-extraction."""
    client = _Client(ModelUnavailable("Timeout: took too long"))

    with pytest.raises(ExtractionFailed, match="took too long"):
        LlmExtractor(client).extract(passage())


def _refused(read, statement: str):
    """One statement the checker refused as more than one claim."""
    from extraction.models import WRITTEN, CandidateFact
    from extraction.validation import FactChecker

    return FactChecker(0.6).check(
        read, CandidateFact(statement=statement, sentences=(0,)), WRITTEN
    )


def test_a_repair_shows_the_numbered_excerpt_the_refusal_and_why() -> None:
    """As the atomic call shows the passage, with the statement and its reason."""
    from extraction.extractors.llm import REPAIR_PROMPT_VERSION

    read = passage(section_path="Devices > Specifications")
    joined = "The device weighs 4 kg and runs for 12 hours."
    client = _Client(_Answer(_Fact("The device weighs 4 kg.", [0, 0])))

    facts = LlmExtractor(client, cap=4).repair(read, [_refused(read, joined)])

    sent = client.asked["user"]
    assert sent.startswith("Context (not part of the excerpt): Devices")
    assert "[0] The device weighs 4 kg and runs for 12 hours." in sent
    assert f'"{joined}"' in sent
    assert "the statement carries 2 claims" in sent
    assert sent.endswith("Write every statement in English.")
    assert client.asked["prompt_version"] == REPAIR_PROMPT_VERSION
    assert "AT MOST" not in client.asked["system"], "the cap is not the repair's"
    assert [(one.statement, one.sentences) for one in facts] == [
        ("The device weighs 4 kg.", (0,))
    ]


def test_a_repaired_fact_names_the_repair_prompt() -> None:
    """So a later reader can tell a repair from what the atomic prompt wrote."""
    from extraction.extractors.llm import REPAIR_PROMPT_VERSION

    extractor = LlmExtractor(_Client(_Answer()), cap=4)

    assert extractor.repair_provenance.prompt_version == REPAIR_PROMPT_VERSION
    assert extractor.repair_provenance.model == extractor.provenance.model
    assert REPAIR_PROMPT_VERSION != extractor.provenance.prompt_version


def test_a_repair_the_model_will_not_answer_is_a_failed_extraction() -> None:
    """The service decides what a failed repair costs; the reader only says so."""
    read = passage()
    client = _Client(ModelUnavailable("Timeout: took too long"))

    with pytest.raises(ExtractionFailed, match="took too long"):
        LlmExtractor(client).repair(
            read, [_refused(read, "The device weighs 4 kg and runs for 12 hours.")]
        )
