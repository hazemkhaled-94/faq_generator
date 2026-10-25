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
    ("questions", "aggregation"): ("32", "5ca8bc599a18e799"),
    ("questions", "application"): ("32", "ad475cf371e93a60"),
    ("questions", "application (spans)"): ("32", "4550c3d557f044a6"),
    ("questions", "application (compound)"): ("32", "05fea2aeabbca545"),
    ("questions", "comparison"): ("32", "c60d9beb0119e72e"),
    ("questions", "condition"): ("32", "e228ab949947cc3a"),
    ("questions", "condition (spans)"): ("32", "942539244fb53a6c"),
    ("questions", "condition (compound)"): ("32", "9797d40c2f5120ba"),
    ("questions", "consequence"): ("32", "374b5525a387f136"),
    ("questions", "consequence (spans)"): ("32", "8cf5a1325fe8f7e2"),
    ("questions", "consequence (compound)"): ("32", "08b65046124886be"),
    ("questions", "definition"): ("32", "e92fa37b0dd8068f"),
    ("questions", "definition (spans)"): ("32", "c9b09346094a67f0"),
    ("questions", "definition (compound)"): ("32", "24715606913bf0b2"),
    ("questions", "entity"): ("32", "b2d8413ee8fd2d70"),
    ("questions", "entity (spans)"): ("32", "d1556082ff70d89f"),
    ("questions", "entity (compound)"): ("32", "b195269b85a5dfa8"),
    ("questions", "enumeration"): ("32", "6f58d335a446e5cf"),
    ("questions", "enumeration (spans)"): ("32", "4a01fbae4c281b1b"),
    ("questions", "enumeration (compound)"): ("32", "1869b712e66a8dd8"),
    ("questions", "factoid"): ("32", "606315ac0db97bc7"),
    ("questions", "factoid (spans)"): ("32", "6c1078e1017294b1"),
    ("questions", "factoid (compound)"): ("32", "6f98801c5addb1ad"),
    ("questions", "implication"): ("32", "758d7fd29b8cffe4"),
    ("questions", "procedure"): ("32", "8407a4474286c1e9"),
    ("questions", "procedure (spans)"): ("32", "56393aedda47a0b8"),
    ("questions", "procedure (compound)"): ("32", "871c9fa7343e6687"),
    ("questions", "reason"): ("32", "d9a60f09bacd50d4"),
    ("questions", "reason (spans)"): ("32", "dd99b89d59b87a52"),
    ("questions", "reason (compound)"): ("32", "32ed5d351fd7ffe3"),
    ("questions", "temporal"): ("32", "19cf63ed99c2ba58"),
    ("questions", "perturb"): ("32", "b1779ff0300538e1"),
    ("questions", "perturb (out-of-corpus)"): ("32", "480f4413943b1943"),
    ("questions", "perturb (false-presupposition)"): ("32", "b0fbd8db45406d1d"),
    ("questions", "perturb (underspecified)"): ("32", "d8e063c4452248c3"),
    ("questions", "perturb (nonsensical)"): ("32", "cf85371ac7313970"),
    ("questions", "follow"): ("32", "b01fef3538ce9a05"),
    ("questions", "phrasing: source"): ("5", "6551aead84a26ba0"),
    ("questions", "phrasing: names something"): ("5", "f31be9753115f3c0"),
    ("questions", "phrasing: self-contained"): ("5", "76a87ab5ca1cc8af"),
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
NOTES = ("32", "c9c5397c7935ac07")


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
