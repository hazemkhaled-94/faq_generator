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
    ("questions", "aggregation"): ("22", "ac6d714b27db1560"),
    ("questions", "application"): ("22", "ea923927e8e0d614"),
    ("questions", "application (spans)"): ("22", "0d12641e703493f4"),
    ("questions", "application (compound)"): ("22", "330328b7a9e077ab"),
    ("questions", "comparison"): ("22", "5ca3cd850a43a492"),
    ("questions", "condition"): ("22", "c19325eb24c18137"),
    ("questions", "condition (spans)"): ("22", "7e86b1278c155409"),
    ("questions", "condition (compound)"): ("22", "f10789b8ae70a7d2"),
    ("questions", "consequence"): ("22", "e228559073f5685f"),
    ("questions", "consequence (spans)"): ("22", "2f44e0c1a3921928"),
    ("questions", "consequence (compound)"): ("22", "fdb442f803992711"),
    ("questions", "definition"): ("22", "655fb5dba3ac06c9"),
    ("questions", "definition (spans)"): ("22", "e9a182515106d843"),
    ("questions", "definition (compound)"): ("22", "a237e3c75d22fc18"),
    ("questions", "entity"): ("22", "83a3fd35e61604d7"),
    ("questions", "entity (spans)"): ("22", "d08a6f69d40bc43a"),
    ("questions", "entity (compound)"): ("22", "9c2f5d9bfc8a62a8"),
    ("questions", "enumeration"): ("22", "034979b861acbccd"),
    ("questions", "enumeration (spans)"): ("22", "e3406f55513d24fd"),
    ("questions", "enumeration (compound)"): ("22", "9f77456105cf31dc"),
    ("questions", "factoid"): ("22", "d0eaff4c19f18889"),
    ("questions", "factoid (spans)"): ("22", "bb6ebfe177deff82"),
    ("questions", "factoid (compound)"): ("22", "1a7023ff1bfc1af2"),
    ("questions", "implication"): ("22", "53e4a971d819b1b6"),
    ("questions", "procedure"): ("22", "cb5240ec3a63ca57"),
    ("questions", "procedure (spans)"): ("22", "c2a4845a2b7031b8"),
    ("questions", "procedure (compound)"): ("22", "b0b26f00e11780fd"),
    ("questions", "reason"): ("22", "a92befe39415e43e"),
    ("questions", "reason (spans)"): ("22", "57665481259717e1"),
    ("questions", "reason (compound)"): ("22", "a12d8eb5f472326c"),
    ("questions", "temporal"): ("22", "0ba9d068c1912bf6"),
    ("questions", "perturb"): ("22", "6bf400e31765f479"),
    ("questions", "follow"): ("22", "48e0ef5101c2010e"),
    ("questions", "phrasing: source"): ("4", "6551aead84a26ba0"),
    ("questions", "phrasing: names something"): ("4", "f31be9753115f3c0"),
    ("questions", "phrasing: self-contained"): ("4", "4929cdb590150f41"),
    ("questions", "verifier: recover"): ("9", "1bc67feb6b1558e6"),
    ("questions", "verifier: supported"): ("9", "c97daca1b67a1e12"),
    ("questions", "verifier: computes"): ("9", "2667ae6169e5343e"),
    ("questions", "verifier: follows"): ("9", "9941c681a2936bc1"),
    ("questions", "verifier: settles"): ("9", "eb2adab3fb5e9c8e"),
    ("questions", "verifier: same answer"): ("9", "054fa0307cf7bcd9"),
    ("questions", "verifier: stated"): ("1", "c3592b0d05a6e8e7"),
    ("extraction", "atomic"): ("12+cap4", "e2d56e73653bbf58"),
    ("extraction", "repair"): ("repair-1", "38641498eb9852d0"),
    ("extraction", "digest"): ("5", "d5d5657642500b66"),
    ("extraction", "bridge"): ("6", "1759d28349a16528"),
    ("topics", "label"): ("2", "7f8b54ef860bde4b"),
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
