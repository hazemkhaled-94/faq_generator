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
    ("questions", "aggregation"): ("15", "dd8addb7ebde2cb6"),
    ("questions", "application"): ("15", "15df13bccbcda643"),
    ("questions", "application (spans)"): ("15", "69ffd4594827eba9"),
    ("questions", "comparison"): ("15", "09a1f80d11ad6356"),
    ("questions", "condition"): ("15", "8b72967fc1ac4792"),
    ("questions", "condition (spans)"): ("15", "7e826bf39ed601a3"),
    ("questions", "consequence"): ("15", "5ad1ef15dfdcf939"),
    ("questions", "consequence (spans)"): ("15", "f712c05dd840fc1a"),
    ("questions", "definition"): ("15", "717c1aff32f1d22e"),
    ("questions", "definition (spans)"): ("15", "0894c14202cbfe03"),
    ("questions", "entity"): ("15", "cef888c920f4aa4d"),
    ("questions", "entity (spans)"): ("15", "536eb8b7c766c45f"),
    ("questions", "enumeration"): ("15", "d514c596482eea04"),
    ("questions", "enumeration (spans)"): ("15", "2fe21ff4d1996d62"),
    ("questions", "factoid"): ("15", "f13da05cdddd168c"),
    ("questions", "factoid (spans)"): ("15", "a78f88aaf9bc9bd2"),
    ("questions", "implication"): ("15", "50723d65da6efd97"),
    ("questions", "procedure"): ("15", "f6741e7978dee0b0"),
    ("questions", "procedure (spans)"): ("15", "b88004e760da911f"),
    ("questions", "reason"): ("15", "2834c3548fd44db1"),
    ("questions", "reason (spans)"): ("15", "f21e3f643c7f4883"),
    ("questions", "temporal"): ("15", "f5aa4c9afb092255"),
    ("questions", "perturb"): ("15", "aedd682c99963759"),
    ("questions", "follow"): ("15", "b01fef3538ce9a05"),
    ("questions", "phrasing: source"): ("4", "6551aead84a26ba0"),
    ("questions", "phrasing: names something"): ("4", "f31be9753115f3c0"),
    ("questions", "phrasing: self-contained"): ("4", "4929cdb590150f41"),
    ("questions", "verifier: recover"): ("5", "3b55c01d7aa9e2b4"),
    ("questions", "verifier: supported"): ("5", "c97daca1b67a1e12"),
    ("questions", "verifier: computes"): ("5", "2667ae6169e5343e"),
    ("questions", "verifier: follows"): ("5", "9941c681a2936bc1"),
    ("questions", "verifier: settles"): ("5", "6599e13b065e85ab"),
    ("questions", "verifier: same answer"): ("5", "054fa0307cf7bcd9"),
    ("extraction", "atomic"): ("11+cap4", "a855ad279eaee08d"),
    ("extraction", "digest"): ("4", "ab0e93b11858a0e8"),
    ("extraction", "bridge"): ("4", "d93f5daae44104bb"),
    ("topics", "label"): ("2", "7f8b54ef860bde4b"),
    ("assessment", "fact: hallucination"): ("2", "ab72d40652bc51c4"),
    ("assessment", "fact: relevance"): ("2", "3a8b74aeaeb83dc5"),
    ("assessment", "fact: toxicity"): ("2", "dba712835cd5db91"),
    ("assessment", "topic: summarization"): ("2", "79af66f22dc1d78a"),
    ("assessment", "topic: relevance"): ("2", "99fb3238292b29f9"),
    ("assessment", "question: hallucination"): ("2", "3e9a0ea18c9eb0b1"),
    ("assessment", "question: qa_correctness"): ("2", "145aae25f81d7438"),
    ("assessment", "question: relevance"): ("2", "7c844240bd726f6d"),
    ("assessment", "question: refusal"): ("2", "f524884a160698d4"),
    ("assessment", "question: conciseness"): ("2", "d5c82af666fa54e2"),
    ("assessment", "question: toxicity"): ("2", "eb392c185d32eb90"),
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
