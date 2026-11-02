"""Every prompt a stage writes with, pinned to its version.

Every prompt each stage's `catalogue()` records is pinned over all three
halves `_write` in `stages/prompts.py` calls drift: system prompt, user
template and response schema.

"Two prompts are two datasets" is what PROMPT_VERSION is for, and nothing
checked it: a rule could be added to `types.py`, every question written
after it would differ from every question written before, and both would
carry version 8.

So each prompt is pinned by digest. Changing one fails this file, and the
only way to make it pass is to bump PROMPT_VERSION and write the new digest
down - which is the decision the version exists to record.

The digest and not the text, because the prompts are eight hundred lines
and a copy of them here would be a second place for them to drift. Which
one moved is what the per-prompt entries say; `test_prompts_name_no_domain`
is what reads their content.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from question_generation.types import SPECS
from stages.prompts import Composed
from tests.static.prompt_catalogues import recorded

#: Every prompt a stage records, by service and name: its version, and the
#: digest over its system prompt, user template and response schema.
RECORDED = {
    ("questions", "aggregation"): ("34", "a54683ac29242992"),
    ("questions", "application"): ("34", "6bbe3d54ad77b802"),
    ("questions", "application (spans)"): ("34", "531530aa0955fc01"),
    ("questions", "application (compound)"): ("34", "cae4a7d920389493"),
    ("questions", "comparison"): ("34", "cc1ee33c3aa3f02c"),
    ("questions", "condition"): ("34", "4d770e88cb3e27d5"),
    ("questions", "condition (spans)"): ("34", "77f1b83c66a29864"),
    ("questions", "condition (compound)"): ("34", "a7d502b2bdb745e3"),
    ("questions", "consequence"): ("34", "7fcb9327db8d916b"),
    ("questions", "consequence (spans)"): ("34", "51f531cbf9f9ae4d"),
    ("questions", "consequence (compound)"): ("34", "0b5bd8541eef77ca"),
    ("questions", "definition"): ("34", "2d5d8d18c77eeda4"),
    ("questions", "definition (spans)"): ("34", "0d9d942c89b4d5dd"),
    ("questions", "definition (compound)"): ("34", "5ee651acd5624d1a"),
    ("questions", "entity"): ("34", "ef9f33f2e9861c75"),
    ("questions", "entity (spans)"): ("34", "ead497b2203bc237"),
    ("questions", "entity (compound)"): ("34", "97ffdecc9d584d4b"),
    ("questions", "enumeration"): ("34", "3e22416bd23fa5ae"),
    ("questions", "enumeration (spans)"): ("34", "a237e299f4ca0488"),
    ("questions", "enumeration (compound)"): ("34", "c30cf718beba31e7"),
    ("questions", "factoid"): ("34", "a9a13d2674b597c7"),
    ("questions", "factoid (spans)"): ("34", "a5a6037885739fb7"),
    ("questions", "factoid (compound)"): ("34", "b3f8c595fe2a55cc"),
    ("questions", "implication"): ("34", "2b93f06712f9503c"),
    ("questions", "procedure"): ("34", "fa50b119d818ba94"),
    ("questions", "procedure (spans)"): ("34", "bd6186ded5502ebb"),
    ("questions", "procedure (compound)"): ("34", "142669337d62681f"),
    ("questions", "reason"): ("34", "9beed2a3bb7a9210"),
    ("questions", "reason (spans)"): ("34", "820b72ea05c1f5f6"),
    ("questions", "reason (compound)"): ("34", "22dbef73fc46c70a"),
    ("questions", "temporal"): ("34", "0d5d0af6fdb74e7e"),
    ("questions", "perturb"): ("34", "d7fd4f487ebdc608"),
    ("questions", "perturb (out-of-corpus)"): ("34", "916072bd9cc15329"),
    ("questions", "perturb (false-presupposition)"): ("34", "d39e9c3fbb23f17f"),
    ("questions", "perturb (underspecified)"): ("34", "67d2e1a896e9cad1"),
    ("questions", "perturb (nonsensical)"): ("34", "5dfec102e622043a"),
    ("questions", "follow"): ("34", "b01fef3538ce9a05"),
    ("questions", "phrasing: source"): ("7", "4d668af2c985c95b"),
    ("questions", "phrasing: names something"): ("7", "f31be9753115f3c0"),
    ("questions", "phrasing: self-contained"): ("7", "e422dc3b785fe4e8"),
    ("questions", "verifier: recover"): ("16", "9272a4a927eb80b4"),
    ("questions", "verifier: supported"): ("16", "c97daca1b67a1e12"),
    ("questions", "verifier: computes"): ("16", "2667ae6169e5343e"),
    ("questions", "verifier: follows"): ("16", "9941c681a2936bc1"),
    ("questions", "verifier: settles"): ("16", "f7678e6f719cd3ed"),
    ("questions", "verifier: same answer"): ("16", "8582e3559198b878"),
    ("questions", "verifier: stated"): ("1", "e71ab946327ded58"),
    ("extraction", "atomic"): ("12+cap4", "e2d56e73653bbf58"),
    ("extraction", "repair"): ("repair-1", "38641498eb9852d0"),
    ("extraction", "digest"): ("5", "d5d5657642500b66"),
    ("extraction", "bridge"): ("6", "1759d28349a16528"),
    ("topics", "label"): ("3", "a814733a7a2b243f"),
    ("assessment", "fact: hallucination"): ("4", "ab72d40652bc51c4"),
    ("assessment", "fact: relevance"): ("4", "3a8b74aeaeb83dc5"),
    ("assessment", "fact: toxicity"): ("4", "dba712835cd5db91"),
    ("assessment", "topic: summarization"): ("4", "79af66f22dc1d78a"),
    ("assessment", "topic: relevance"): ("4", "99fb3238292b29f9"),
    ("assessment", "question: hallucination"): ("4", "3e9a0ea18c9eb0b1"),
    ("assessment", "question: qa_correctness"): ("4", "145aae25f81d7438"),
    ("assessment", "question: refusal"): ("4", "f524884a160698d4"),
    ("assessment", "question: conciseness"): ("4", "d5c82af666fa54e2"),
    ("assessment", "question: toxicity"): ("4", "eb392c185d32eb90"),
    ("assessment", "question: rubric"): ("4", "80847438785d36fb"),
}


#: The notes a refused draft is written again with, a kind's included, by
#: the writer's version: the writer reads them on every retry, and no
#: catalogue entry holds them.
NOTES = ("34", "c9c5397c7935ac07")


def halves(one: Composed) -> str:
    """One digest over the three halves `_write` compares."""
    schema = json.dumps(one.response_schema, sort_keys=True)
    return digest(f"{one.text}\0{one.user_text}\0{schema}")


def digest(text: str) -> str:
    """The first sixteen hex characters of one prompt's SHA-256."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@pytest.mark.parametrize(("service", "name"), sorted(RECORDED))
def test_a_recorded_prompt_is_the_one_pinned_under_its_version(
    service: str, name: str
) -> None:
    """Any of the three halves moving under one version is drift."""
    key = (service, name)
    every = recorded()
    assert key in every, f"{key} is pinned here and no stage records it"

    version, pinned = RECORDED[key]
    assert every[key].version == version, (
        f"{key} is at version {every[key].version} and this file pins "
        f"{version}. Write the new version and digest here."
    )
    assert halves(every[key]) == pinned, (
        f"{key} changed under version {version}: its system prompt, user "
        f"template or response schema. Bump its module's PROMPT_VERSION and "
        f"write the new digest here."
    )


def test_every_prompt_a_stage_records_is_pinned() -> None:
    """A prompt added to a catalogue with no digest is one nothing watches."""
    found = set(recorded())

    assert found == set(RECORDED), (
        f"added: {sorted(found - set(RECORDED))}, gone: {sorted(set(RECORDED) - found)}"
    )


def test_the_shared_rules_reach_every_type() -> None:
    """One rule block, so two prompts cannot come to disagree.

    The pinning above would pass if `READS` were dropped from one type and
    that type's digest updated, which is the drift this is about.
    """
    for name, spec in SPECS.items():
        written = spec.system()
        assert "NEVER SAY WHERE THE ANSWER IS" in written, name
        assert "ONE question, ending in a question mark" in written, name
        assert "You write TWO answers" in written, name


def test_a_type_that_spans_is_told_to_span() -> None:
    """The row otherwise carries a spread the question never used."""
    for name, spec in SPECS.items():
        if spec.spans:
            assert "MORE THAN ONE PASSAGE" in spec.system(), name


def test_a_single_passage_type_is_told_to_span_only_when_the_sample_does() -> None:
    """A factoid drawn from two documents is a cross-document factoid."""
    factoid = SPECS["factoid"]

    assert "MORE THAN ONE PASSAGE" not in factoid.system()
    assert "MORE THAN ONE PASSAGE" in factoid.system(spans=True)


def test_the_retry_notes_are_the_ones_pinned_under_the_writers_version() -> None:
    """A note moving under one writer version is drift, as a prompt moving is."""
    from question_generation.service import _KIND_NOTES, _NOTES, _QUERY_NOTES
    from question_generation.types import PROMPT_VERSION

    version, pinned = NOTES
    notes = json.dumps([_NOTES, _QUERY_NOTES, _KIND_NOTES], sort_keys=True)

    assert PROMPT_VERSION == version, (
        f"the writer is at version {PROMPT_VERSION} and this file pins its notes "
        f"under {version}"
    )
    assert digest(notes) == pinned, (
        f"the retry notes moved under version {version}: bump PROMPT_VERSION and "
        f"pin {digest(notes)}"
    )
