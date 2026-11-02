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
    ("questions", "aggregation"): ("33", "06e68c9ee0ca6c28"),
    ("questions", "application"): ("33", "e0b48c2037eb4854"),
    ("questions", "application (spans)"): ("33", "42895fe4cc844e96"),
    ("questions", "application (compound)"): ("33", "8aabbe08b477a27a"),
    ("questions", "comparison"): ("33", "360cfd8b1ff8d78b"),
    ("questions", "condition"): ("33", "21163a0582d6478c"),
    ("questions", "condition (spans)"): ("33", "f0d27b26577717ea"),
    ("questions", "condition (compound)"): ("33", "fb2e37dd762f6548"),
    ("questions", "consequence"): ("33", "a5582787ccce4a23"),
    ("questions", "consequence (spans)"): ("33", "e68016866910c6f1"),
    ("questions", "consequence (compound)"): ("33", "3783d2af381729de"),
    ("questions", "definition"): ("33", "362f5581481dae21"),
    ("questions", "definition (spans)"): ("33", "0486b7f52e7c028e"),
    ("questions", "definition (compound)"): ("33", "7237ec5509b1501d"),
    ("questions", "entity"): ("33", "dedbb7dc28dcf935"),
    ("questions", "entity (spans)"): ("33", "d009fd43afff023f"),
    ("questions", "entity (compound)"): ("33", "51e3e0e4a16ef143"),
    ("questions", "enumeration"): ("33", "04f14d0f91238086"),
    ("questions", "enumeration (spans)"): ("33", "f172024b61420ffc"),
    ("questions", "enumeration (compound)"): ("33", "fb81b910b1067eba"),
    ("questions", "factoid"): ("33", "1512b9d57a7b34be"),
    ("questions", "factoid (spans)"): ("33", "7dbc0a4f7607dc6e"),
    ("questions", "factoid (compound)"): ("33", "2e3273912049cebc"),
    ("questions", "implication"): ("33", "6f218884dee81e24"),
    ("questions", "procedure"): ("33", "add3e43528249a1d"),
    ("questions", "procedure (spans)"): ("33", "191feecb4eac5064"),
    ("questions", "procedure (compound)"): ("33", "d72b1b44dd4dc9b6"),
    ("questions", "reason"): ("33", "129525eca9e42345"),
    ("questions", "reason (spans)"): ("33", "595c34aa5408ea2f"),
    ("questions", "reason (compound)"): ("33", "54bfda0f8273148f"),
    ("questions", "temporal"): ("33", "e930b59db9825501"),
    ("questions", "perturb"): ("33", "81439bc59f39da73"),
    ("questions", "perturb (out-of-corpus)"): ("33", "e3e3f2797151a2f8"),
    ("questions", "perturb (false-presupposition)"): ("33", "b6db7a81bd49ff62"),
    ("questions", "perturb (underspecified)"): ("33", "c1cc74f2cbb18133"),
    ("questions", "perturb (nonsensical)"): ("33", "a5eef73817b5cc44"),
    ("questions", "follow"): ("33", "b01fef3538ce9a05"),
    ("questions", "phrasing: source"): ("6", "4d668af2c985c95b"),
    ("questions", "phrasing: names something"): ("6", "f31be9753115f3c0"),
    ("questions", "phrasing: self-contained"): ("6", "50e7b75480d3ff6a"),
    ("questions", "verifier: recover"): ("15", "156f7f5590f99347"),
    ("questions", "verifier: supported"): ("15", "c97daca1b67a1e12"),
    ("questions", "verifier: computes"): ("15", "2667ae6169e5343e"),
    ("questions", "verifier: follows"): ("15", "9941c681a2936bc1"),
    ("questions", "verifier: settles"): ("15", "522d2a5d2f939279"),
    ("questions", "verifier: same answer"): ("15", "054fa0307cf7bcd9"),
    ("questions", "verifier: stated"): ("1", "c3592b0d05a6e8e7"),
    ("extraction", "atomic"): ("12+cap4", "e2d56e73653bbf58"),
    ("extraction", "repair"): ("repair-1", "38641498eb9852d0"),
    ("extraction", "digest"): ("5", "d5d5657642500b66"),
    ("extraction", "bridge"): ("6", "1759d28349a16528"),
    ("topics", "label"): ("3", "a814733a7a2b243f"),
    ("assessment", "fact: hallucination"): ("5", "ab72d40652bc51c4"),
    ("assessment", "fact: relevance"): ("5", "3a8b74aeaeb83dc5"),
    ("assessment", "fact: toxicity"): ("5", "dba712835cd5db91"),
    ("assessment", "topic: summarization"): ("5", "79af66f22dc1d78a"),
    ("assessment", "topic: relevance"): ("5", "99fb3238292b29f9"),
    ("assessment", "question: hallucination"): ("5", "3e9a0ea18c9eb0b1"),
    ("assessment", "question: qa_correctness"): ("5", "145aae25f81d7438"),
    ("assessment", "question: refusal"): ("5", "f524884a160698d4"),
    ("assessment", "question: conciseness"): ("5", "d5c82af666fa54e2"),
    ("assessment", "question: toxicity"): ("5", "eb392c185d32eb90"),
    ("assessment", "question: rubric"): ("5", "86a10ed2121fe83a"),
}


#: The notes a refused draft is written again with, a kind's included, by
#: the writer's version: the writer reads them on every retry, and no
#: catalogue entry holds them.
NOTES = ("33", "c9c5397c7935ac07")


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
