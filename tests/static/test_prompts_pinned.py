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
    ("questions", "aggregation"): ("35", "ce906b737dcf0d86"),
    ("questions", "application"): ("35", "ec0bcd5ea0248945"),
    ("questions", "application (spans)"): ("35", "cff487dcdcb55d37"),
    ("questions", "application (compound)"): ("35", "e6ebf5aa9c5e9622"),
    ("questions", "comparison"): ("35", "c012920321881433"),
    ("questions", "condition"): ("35", "a7e9017cffe856cd"),
    ("questions", "condition (spans)"): ("35", "51a01540e8e662db"),
    ("questions", "condition (compound)"): ("35", "9162b18871f3557b"),
    ("questions", "consequence"): ("35", "5af52df1457db8b7"),
    ("questions", "consequence (spans)"): ("35", "dee7d6875e37f6aa"),
    ("questions", "consequence (compound)"): ("35", "50b06aa519f7c071"),
    ("questions", "definition"): ("35", "90d1cc65d2a7d8fd"),
    ("questions", "definition (spans)"): ("35", "7019c1e4fb588c6c"),
    ("questions", "definition (compound)"): ("35", "2d7879431e59f86b"),
    ("questions", "entity"): ("35", "57eb4c7b6d7a5257"),
    ("questions", "entity (spans)"): ("35", "1c3d33c0a1fd842b"),
    ("questions", "entity (compound)"): ("35", "da1df93dbbd23e10"),
    ("questions", "enumeration"): ("35", "b2d6e3d5f84639a7"),
    ("questions", "enumeration (spans)"): ("35", "a5700fd3b32fb947"),
    ("questions", "enumeration (compound)"): ("35", "ca92b8f52a9df867"),
    ("questions", "factoid"): ("35", "5ecd30623a819ba9"),
    ("questions", "factoid (spans)"): ("35", "2e492eb1e0daee48"),
    ("questions", "factoid (compound)"): ("35", "625b43b768c7fe53"),
    ("questions", "implication"): ("35", "baf99cbe0a27239a"),
    ("questions", "procedure"): ("35", "6f5efa2dda982652"),
    ("questions", "procedure (spans)"): ("35", "96497fd2dc1b286e"),
    ("questions", "procedure (compound)"): ("35", "63e64147051ee466"),
    ("questions", "reason"): ("35", "e6613dad46eec28c"),
    ("questions", "reason (spans)"): ("35", "dbd20c41c3bf88db"),
    ("questions", "reason (compound)"): ("35", "be9f6eb158454e83"),
    ("questions", "temporal"): ("35", "c10e0916197a02e3"),
    ("questions", "perturb"): ("35", "64ff705b4830d7b0"),
    ("questions", "perturb (out-of-corpus)"): ("35", "72b6b9ea52c87bee"),
    ("questions", "perturb (false-presupposition)"): ("35", "abee393d890df70e"),
    ("questions", "perturb (underspecified)"): ("35", "f8dc7a5dac23b87a"),
    ("questions", "perturb (nonsensical)"): ("35", "48b1f99b1fc2e286"),
    ("questions", "follow"): ("35", "a5bdef00784bc62b"),
    ("questions", "phrasing: source"): ("8", "d0f96728bf8f96b4"),
    ("questions", "phrasing: names something"): ("8", "2694fdb6880539be"),
    ("questions", "phrasing: self-contained"): ("8", "df19602c6a43aeee"),
    ("questions", "verifier: recover"): ("17", "23e2fe64a1318a2e"),
    ("questions", "verifier: supported"): ("17", "878f2f66c9f02748"),
    ("questions", "verifier: computes"): ("17", "cb490a5be3baf6d9"),
    ("questions", "verifier: follows"): ("17", "81f7804379a4f105"),
    ("questions", "verifier: settles"): ("17", "15b4f1b1b287d323"),
    ("questions", "verifier: same answer"): ("17", "8582e3559198b878"),
    ("questions", "verifier: stated"): ("3", "5db0f19c9bd323dd"),
    ("extraction", "atomic"): ("12+cap4", "e2d56e73653bbf58"),
    ("extraction", "repair"): ("repair-1", "38641498eb9852d0"),
    ("extraction", "digest"): ("5", "d5d5657642500b66"),
    ("extraction", "bridge"): ("6", "1759d28349a16528"),
    ("topics", "label"): ("3", "a814733a7a2b243f"),
    ("assessment", "fact: hallucination"): ("5", "217dc127c24eca3e"),
    ("assessment", "fact: relevance"): ("5", "b3b165b0643bfd61"),
    ("assessment", "fact: toxicity"): ("5", "4f05eef49868eaf3"),
    ("assessment", "topic: summarization"): ("5", "79af66f22dc1d78a"),
    ("assessment", "topic: relevance"): ("5", "99fb3238292b29f9"),
    ("assessment", "question: hallucination"): ("5", "831dd4df69f31022"),
    ("assessment", "question: qa_correctness"): ("5", "2a52ed6638d5c514"),
    ("assessment", "question: refusal"): ("5", "f524884a160698d4"),
    ("assessment", "question: conciseness"): ("5", "d5c82af666fa54e2"),
    ("assessment", "question: toxicity"): ("5", "eb392c185d32eb90"),
    ("assessment", "question: rubric"): ("5", "776bc49a00f540d4"),
}


#: The notes a refused draft is written again with, a kind's included, by
#: the writer's version: the writer reads them on every retry, and no
#: catalogue entry holds them.
NOTES = ("35", "c9c5397c7935ac07")


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
