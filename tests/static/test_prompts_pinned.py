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
    ("questions", "aggregation"): ("18", "5cab675d76a92585"),
    ("questions", "application"): ("18", "3f973e39a1e49c21"),
    ("questions", "application (spans)"): ("18", "eb3c7012088f1408"),
    ("questions", "application (compound)"): ("18", "d0df0f7413e46e3c"),
    ("questions", "comparison"): ("18", "87aba3d93b1b6605"),
    ("questions", "condition"): ("18", "452f3af4ad9ecef4"),
    ("questions", "condition (spans)"): ("18", "87771ad2e3715f20"),
    ("questions", "condition (compound)"): ("18", "64243222d1eebcac"),
    ("questions", "consequence"): ("18", "a2ee8f9ae452f4cb"),
    ("questions", "consequence (spans)"): ("18", "3f33f02ea19b3b89"),
    ("questions", "consequence (compound)"): ("18", "c87e0dc340a7a2f7"),
    ("questions", "definition"): ("18", "bf57ec7699b428b8"),
    ("questions", "definition (spans)"): ("18", "06674e695202746f"),
    ("questions", "definition (compound)"): ("18", "8b3ff8ad68f45fb2"),
    ("questions", "entity"): ("18", "b06830bc848964fe"),
    ("questions", "entity (spans)"): ("18", "5fa528ecab597184"),
    ("questions", "entity (compound)"): ("18", "675798c58199755e"),
    ("questions", "enumeration"): ("18", "141767b4d85d0d76"),
    ("questions", "enumeration (spans)"): ("18", "e43fa1e5f69424ea"),
    ("questions", "enumeration (compound)"): ("18", "0f5d2cd29f4766ec"),
    ("questions", "factoid"): ("18", "b1043d01f54fe96f"),
    ("questions", "factoid (spans)"): ("18", "1873b4cf213d9dbe"),
    ("questions", "factoid (compound)"): ("18", "dcbdbc9c2ba2b6e1"),
    ("questions", "implication"): ("18", "1443009438951d9e"),
    ("questions", "procedure"): ("18", "7b3931fb8d818534"),
    ("questions", "procedure (spans)"): ("18", "f24b9e9d124db138"),
    ("questions", "procedure (compound)"): ("18", "58c8e75286dbe336"),
    ("questions", "reason"): ("18", "db319fabbada15ac"),
    ("questions", "reason (spans)"): ("18", "365b03b99c21c153"),
    ("questions", "reason (compound)"): ("18", "3e43cf79a738d660"),
    ("questions", "temporal"): ("18", "4eb3229a438c4ed0"),
    ("questions", "perturb"): ("18", "aedd682c99963759"),
    ("questions", "follow"): ("18", "b01fef3538ce9a05"),
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
