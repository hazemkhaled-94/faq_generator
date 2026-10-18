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
    ("questions", "aggregation"): ("16", "dd8addb7ebde2cb6"),
    ("questions", "application"): ("16", "15df13bccbcda643"),
    ("questions", "application (spans)"): ("16", "69ffd4594827eba9"),
    ("questions", "application (compound)"): ("16", "55db490a4a429ea6"),
    ("questions", "comparison"): ("16", "09a1f80d11ad6356"),
    ("questions", "condition"): ("16", "8b72967fc1ac4792"),
    ("questions", "condition (spans)"): ("16", "7e826bf39ed601a3"),
    ("questions", "condition (compound)"): ("16", "d4fab5a9850aa9af"),
    ("questions", "consequence"): ("16", "5ad1ef15dfdcf939"),
    ("questions", "consequence (spans)"): ("16", "f712c05dd840fc1a"),
    ("questions", "consequence (compound)"): ("16", "fa715f653722b817"),
    ("questions", "definition"): ("16", "717c1aff32f1d22e"),
    ("questions", "definition (spans)"): ("16", "0894c14202cbfe03"),
    ("questions", "definition (compound)"): ("16", "80796c83553fb37e"),
    ("questions", "entity"): ("16", "cef888c920f4aa4d"),
    ("questions", "entity (spans)"): ("16", "536eb8b7c766c45f"),
    ("questions", "entity (compound)"): ("16", "28a35017b066a714"),
    ("questions", "enumeration"): ("16", "d514c596482eea04"),
    ("questions", "enumeration (spans)"): ("16", "2fe21ff4d1996d62"),
    ("questions", "enumeration (compound)"): ("16", "15a07522b9133270"),
    ("questions", "factoid"): ("16", "f13da05cdddd168c"),
    ("questions", "factoid (spans)"): ("16", "a78f88aaf9bc9bd2"),
    ("questions", "factoid (compound)"): ("16", "f1c2226c61109ed4"),
    ("questions", "implication"): ("16", "50723d65da6efd97"),
    ("questions", "procedure"): ("16", "f6741e7978dee0b0"),
    ("questions", "procedure (spans)"): ("16", "b88004e760da911f"),
    ("questions", "procedure (compound)"): ("16", "552c01c71d57d6db"),
    ("questions", "reason"): ("16", "2834c3548fd44db1"),
    ("questions", "reason (spans)"): ("16", "f21e3f643c7f4883"),
    ("questions", "reason (compound)"): ("16", "dba4bbd919a1d63b"),
    ("questions", "temporal"): ("16", "f5aa4c9afb092255"),
    ("questions", "perturb"): ("16", "aedd682c99963759"),
    ("questions", "follow"): ("16", "b01fef3538ce9a05"),
    ("questions", "phrasing: source"): ("4", "6551aead84a26ba0"),
    ("questions", "phrasing: names something"): ("4", "f31be9753115f3c0"),
    ("questions", "phrasing: self-contained"): ("4", "4929cdb590150f41"),
    ("questions", "verifier: recover"): ("6", "3b55c01d7aa9e2b4"),
    ("questions", "verifier: supported"): ("6", "c97daca1b67a1e12"),
    ("questions", "verifier: computes"): ("6", "2667ae6169e5343e"),
    ("questions", "verifier: follows"): ("6", "9941c681a2936bc1"),
    ("questions", "verifier: settles"): ("6", "eb2adab3fb5e9c8e"),
    ("questions", "verifier: same answer"): ("6", "054fa0307cf7bcd9"),
    ("questions", "verifier: stated"): ("1", "c3592b0d05a6e8e7"),
    ("extraction", "atomic"): ("12+cap4", "e2d56e73653bbf58"),
    ("extraction", "repair"): ("repair-1", "38641498eb9852d0"),
    ("extraction", "digest"): ("5", "d5d5657642500b66"),
    ("extraction", "bridge"): ("6", "1759d28349a16528"),
    ("topics", "label"): ("2", "7f8b54ef860bde4b"),
    ("assessment", "fact: hallucination"): ("3", "ab72d40652bc51c4"),
    ("assessment", "fact: relevance"): ("3", "3a8b74aeaeb83dc5"),
    ("assessment", "fact: toxicity"): ("3", "dba712835cd5db91"),
    ("assessment", "topic: summarization"): ("3", "79af66f22dc1d78a"),
    ("assessment", "topic: relevance"): ("3", "99fb3238292b29f9"),
    ("assessment", "question: hallucination"): ("3", "3e9a0ea18c9eb0b1"),
    ("assessment", "question: qa_correctness"): ("3", "145aae25f81d7438"),
    ("assessment", "question: relevance"): ("3", "7c844240bd726f6d"),
    ("assessment", "question: refusal"): ("3", "f524884a160698d4"),
    ("assessment", "question: conciseness"): ("3", "d5c82af666fa54e2"),
    ("assessment", "question: toxicity"): ("3", "eb392c185d32eb90"),
    ("assessment", "question: rubric"): ("3", "80847438785d36fb"),
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
