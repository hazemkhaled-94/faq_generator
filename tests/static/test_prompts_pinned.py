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
    ("questions", "aggregation"): ("13", "05970b20ebc3eb32"),
    ("questions", "application"): ("13", "de838bf56ffe48c3"),
    ("questions", "application (spans)"): ("13", "ff2011a6799ef52b"),
    ("questions", "comparison"): ("13", "118a27b27e54e3bb"),
    ("questions", "condition"): ("13", "d9c1eff02c508bbb"),
    ("questions", "condition (spans)"): ("13", "614e78fa87ce3ed7"),
    ("questions", "consequence"): ("13", "f52d3250507bbf7b"),
    ("questions", "consequence (spans)"): ("13", "a87744c064b750f2"),
    ("questions", "definition"): ("13", "1cd1dc1ef6024051"),
    ("questions", "definition (spans)"): ("13", "1deca374169f41ea"),
    ("questions", "entity"): ("13", "51f242a8d6080e9c"),
    ("questions", "entity (spans)"): ("13", "27f449c2ea4152ae"),
    ("questions", "enumeration"): ("13", "acd1abeb5d2a6a2a"),
    ("questions", "enumeration (spans)"): ("13", "2ecb00f7256dda47"),
    ("questions", "factoid"): ("13", "6009903fc261a5f4"),
    ("questions", "factoid (spans)"): ("13", "75cc36d1ddb6b854"),
    ("questions", "implication"): ("13", "d7a8cd6ec96b040c"),
    ("questions", "procedure"): ("13", "1bc9d1555c1185f2"),
    ("questions", "procedure (spans)"): ("13", "64d3f6e02fe71e8f"),
    ("questions", "reason"): ("13", "e80b0159ce9b2e70"),
    ("questions", "reason (spans)"): ("13", "39909223579093fe"),
    ("questions", "temporal"): ("13", "2bee1f3623741873"),
    ("questions", "perturb"): ("13", "d4d215155fec6be4"),
    ("questions", "follow"): ("13", "71e82cb87e9cbabc"),
    ("questions", "phrasing: source"): ("3", "8feff436a4b70d4d"),
    ("questions", "phrasing: names something"): ("3", "f31be9753115f3c0"),
    ("questions", "phrasing: self-contained"): ("3", "4929cdb590150f41"),
    ("questions", "verifier: recover"): ("4", "3b55c01d7aa9e2b4"),
    ("questions", "verifier: supported"): ("4", "c97daca1b67a1e12"),
    ("questions", "verifier: computes"): ("4", "2667ae6169e5343e"),
    ("questions", "verifier: follows"): ("4", "9941c681a2936bc1"),
    ("questions", "verifier: settles"): ("4", "69ed8bb1481bcec8"),
    ("extraction", "atomic"): ("10+cap4", "c25cb9725eac75db"),
    ("extraction", "digest"): ("3", "f7003be75e42b82e"),
    ("extraction", "bridge"): ("4", "d93f5daae44104bb"),
    ("topics", "label"): ("1", "744885b5f08d5066"),
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
