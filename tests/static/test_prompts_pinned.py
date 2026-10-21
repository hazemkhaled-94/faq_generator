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
    ("questions", "aggregation"): ("28", "159ffa77976313db"),
    ("questions", "application"): ("28", "24f1091f699aa0a2"),
    ("questions", "application (spans)"): ("28", "65803430364490c4"),
    ("questions", "application (compound)"): ("28", "20698b6222742d2d"),
    ("questions", "comparison"): ("28", "3ad2cb919dd21065"),
    ("questions", "condition"): ("28", "929efbfd28c07c72"),
    ("questions", "condition (spans)"): ("28", "6fd8222b93b19740"),
    ("questions", "condition (compound)"): ("28", "33df212d819d39d7"),
    ("questions", "consequence"): ("28", "c5c0bcad86bbf4dd"),
    ("questions", "consequence (spans)"): ("28", "971c5ebcc7fe09fc"),
    ("questions", "consequence (compound)"): ("28", "96d82a9ef9667db5"),
    ("questions", "definition"): ("28", "3cffe55fa0d46404"),
    ("questions", "definition (spans)"): ("28", "d35660d58b289255"),
    ("questions", "definition (compound)"): ("28", "c541010246886097"),
    ("questions", "entity"): ("28", "01b2d270a2f26c23"),
    ("questions", "entity (spans)"): ("28", "939e6ff29446de31"),
    ("questions", "entity (compound)"): ("28", "eb9fa598258dbdeb"),
    ("questions", "enumeration"): ("28", "35fe8722078dc38c"),
    ("questions", "enumeration (spans)"): ("28", "1d9af5dc6f5ec8c7"),
    ("questions", "enumeration (compound)"): ("28", "7b1ee6bc5f79fb03"),
    ("questions", "factoid"): ("28", "6b493a0d03d98860"),
    ("questions", "factoid (spans)"): ("28", "0cdcd8f7c4922988"),
    ("questions", "factoid (compound)"): ("28", "0fe590ec89fa65b1"),
    ("questions", "implication"): ("28", "d18dab93ff0f8364"),
    ("questions", "procedure"): ("28", "124b4eb115b354b2"),
    ("questions", "procedure (spans)"): ("28", "16fd07789cdc4f19"),
    ("questions", "procedure (compound)"): ("28", "5989bc5b7c712fd7"),
    ("questions", "reason"): ("28", "76b1ac67fd3241d8"),
    ("questions", "reason (spans)"): ("28", "57d9b2447c1a15c2"),
    ("questions", "reason (compound)"): ("28", "9176e61a9e42efdb"),
    ("questions", "temporal"): ("28", "36afed51ab80ebce"),
    ("questions", "perturb"): ("28", "1b56db0841285737"),
    ("questions", "follow"): ("28", "b01fef3538ce9a05"),
    ("questions", "phrasing: source"): ("4", "6551aead84a26ba0"),
    ("questions", "phrasing: names something"): ("4", "f31be9753115f3c0"),
    ("questions", "phrasing: self-contained"): ("4", "4929cdb590150f41"),
    ("questions", "verifier: recover"): ("12", "156f7f5590f99347"),
    ("questions", "verifier: supported"): ("12", "c97daca1b67a1e12"),
    ("questions", "verifier: computes"): ("12", "2667ae6169e5343e"),
    ("questions", "verifier: follows"): ("12", "9941c681a2936bc1"),
    ("questions", "verifier: settles"): ("12", "eb2adab3fb5e9c8e"),
    ("questions", "verifier: same answer"): ("12", "054fa0307cf7bcd9"),
    ("questions", "verifier: stated"): ("1", "c3592b0d05a6e8e7"),
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
